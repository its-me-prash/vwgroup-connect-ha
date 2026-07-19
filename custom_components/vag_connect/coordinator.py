# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coordinator for VAG Connect — async polling via own CARIAD API client.

Data flow:
  CARIAD client polls VAG API → poll_loop pushes to HA via async_set_updated_data
  → asyncio.run_coroutine_threadsafe → async_set_updated_data → entities update.

Thread safety:
  _vehicles_lock (threading.Lock) guards self.vehicles.
  CARIAD client (async) writes vehicles dict; HA entities read via coordinator data.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import threading
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BRAND,
    CONF_COUNTRY,
    CONF_ENABLE_PUSH_AUDI_VW,
    CONF_ENABLE_PUSH_FCM,
    CONF_ENABLE_PUSH_MQTT,
    CONF_ENABLE_REVERSE_GEOCODING,
    CONF_FORCE_PPE_CLIMATE,
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MEB_COMMANDS_UNAVAILABLE,
    CONF_PASSWORD,
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    CONF_SPIN_BY_VIN,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from homeassistant.helpers import device_registry as dr
from .cariad._error_reporter import ErrorRingBuffer, record_error
from .cariad._reporter_pipeline import (
    ensure_error_reporter_issue,
    ensure_unexpected_keys_issue,
)
from .cariad._unexpected_keys import UnexpectedField, detect_unexpected
from .cariad._util import mask_email, mask_vin
from .cariad.exceptions import CommandFailureReason, CommandProfile
from .cariad.models import VehicleData

_LOGGER = logging.getLogger(__name__)


def _is_selfhealing_poll_error(err: object) -> bool:
    """True for a poll error that must NOT be escalated to the public Error
    Reporter, because it self-heals and is not our bug:

    - a transient VW-backend 5xx (``UpstreamUnavailableError`` or an ``APIError``
      with ``status >= 500``), or
    - a status-0 transient NETWORK error — DNS timeout / connection refused /
      mid-stream disconnect — which ``base._request`` tags ``"transient:"`` in the
      ``APIError`` body AFTER exhausting its own retries. (#814 was exactly a
      "Timeout while contacting DNS servers" on a user's Home Assistant host.)

    Auth-interaction errors are de-escalated separately (they trigger reauth).
    """
    from .cariad.exceptions import APIError, UpstreamUnavailableError  # noqa: PLC0415

    if isinstance(err, UpstreamUnavailableError):
        return True
    if isinstance(err, APIError):
        status = getattr(err, "status", 0)
        if status >= 500:
            return True
        body = getattr(err, "body", None)
        if status == 0 and isinstance(body, str) and body.lstrip().startswith(
            "transient:"
        ):
            return True
    return False

# v2.17.2 (#666) — how long an optimistically-set command value is held across
# polls before the backend state is trusted again. Long enough to cover a
# couple of poll cycles (VW reflects a command in ~10-60 s), short enough that a
# command that silently didn't take effect self-corrects within a few minutes.
_OPTIMISTIC_HOLD_SECONDS = 150.0

# Minimum interval enforced by Audi/VW connector (Sekunden)
_CC_MIN_INTERVAL_S = 180

# Capabilities are mostly static (subscription tier, vehicle features) but
# can change when a user renews/cancels online services. 24h is a balance
# between picking up legitimate changes and avoiding unnecessary calls.
_CAPABILITIES_TTL = timedelta(hours=24)

# Per-VIN failure tolerance before marking the vehicle unavailable.
# Pattern from `mitch-dc/volkswagen_we_connect_id` #215: a single failed
# poll should not flip every entity on the vehicle to "unavailable" because
# the VAG backend is intermittently flaky (especially weekends and during
# software maintenance windows). Three consecutive failures is the same
# threshold the official We Connect ID app uses before showing an offline
# state to the user.
_FAILURE_TOLERANCE = 3

# Stale-cache window: even after exceeding the failure tolerance, keep
# reporting the vehicle as available if we have data younger than this
# window. Pattern from `skodaconnect/homeassistant-myskoda` #731: users
# strongly prefer "old but visible" over "unavailable" — automations
# triggered by the last known state are still useful, and the user can see
# from `last_updated_at` that the data is stale. 6 hours covers normal
# weekend backend outages without serving truly outdated data.
_STALE_CACHE_WINDOW = timedelta(hours=6)

# v1.12.0 (#55) — Smart-Wake budget. The vehicle limits remote wake-ups
# per day (typically 3-5 depending on backend) to protect the 12V
# battery. After the limit, the car silently ignores wake requests until
# midnight (UTC). Soft-cap at 3 to leave headroom for emergencies + match
# what upstream CC-* maintainers documented as safe for their
# backends. Reset is per-VIN at UTC midnight.
_WAKE_BUDGET_PER_DAY = 3

# v1.13.0 (#63 Phase 3) — anti-double-click cooldown for wake_vehicle.
# 5 minutes between wake-up triggers per VIN. User clicking the wake
# button twice in 30s would otherwise blow through the day budget.
_WAKE_COOLDOWN = timedelta(minutes=5)

# v1.13.0 (#63 Phase 2) — per-VIN per-command-class lock timeout.
# Holds the lock no longer than this many seconds before falling back
# (typical CARIAD command roundtrip is 10-30s; 60s is a safe upper bound
# even for slow weekend backend windows).
_COMMAND_LOCK_TIMEOUT = 60.0


def _parse_trip_statistics(
    short_resp: Any, long_resp: Any
) -> dict[str, Any]:
    """v1.14.0 (#24) — Pure parser for CARIAD-BFF tripstatistics responses.

    Returns a dict of ``last_trip_*`` + ``lifetime_*`` + ``recent_trips``
    fields ready to merge into ``coordinator.vehicles[vin]``. Empty dict
    on no usable data (preserves stale cache).

    Both endpoints share the same ``{tripDataList: {tripData: [...]}}``
    shape — sorted by ``overallMileage`` desc, ``[0]`` is the most
    recent. Consumption fields come back as integers ×10 (sources:
    upstream audi_services.py + upstream + ioBroker/vw-connect)
    so we divide by 10 to get human numbers (l/100km, kWh/100km).

    Pure function — safe to test in isolation, no I/O, no logging.
    """
    out: dict[str, Any] = {}

    def _extract_trips(resp: Any) -> list[dict[str, Any]]:
        if not isinstance(resp, dict):
            return []
        wrapper = resp.get("tripDataList")
        if not isinstance(wrapper, dict):
            return []
        trips = wrapper.get("tripData")
        if not isinstance(trips, list):
            return []
        # defensive: drop non-dict entries
        good = [t for t in trips if isinstance(t, dict)]
        # sort by overallMileage descending — newest at [0]
        good.sort(
            key=lambda t: t.get("overallMileage", 0)
            if isinstance(t.get("overallMileage"), (int, float))
            else 0,
            reverse=True,
        )
        return good

    def _div10(val: Any) -> float | None:
        if isinstance(val, (int, float)) and val > 0:
            return round(val / 10.0, 1)
        return None

    short_trips = _extract_trips(short_resp)
    long_trips = _extract_trips(long_resp)
    out["_shortterm_count"] = len(short_trips)
    out["_longterm_count"] = len(long_trips)

    # Last trip — from shortTerm (per-ignition cycle)
    if short_trips:
        last = short_trips[0]
        out["last_trip_distance_km"] = (
            float(last["mileage"]) if isinstance(last.get("mileage"), (int, float)) else None
        )
        out["last_trip_duration_min"] = (
            int(last["traveltime"]) if isinstance(last.get("traveltime"), (int, float)) else None
        )
        out["last_trip_avg_speed_kmh"] = (
            float(last["averageSpeed"])
            if isinstance(last.get("averageSpeed"), (int, float))
            else None
        )
        out["last_trip_avg_fuel_consumption_l_100km"] = _div10(
            last.get("averageFuelConsumption")
        )
        out["last_trip_avg_electric_consumption_kwh_100km"] = _div10(
            last.get("averageElectricEngineConsumption")
        )
        ts = last.get("timestamp")
        out["last_trip_timestamp"] = ts if isinstance(ts, str) else None

        # Keep only the 5 most-recent in extra_state_attributes (255-char
        # state limit avoidance, plus recorder bloat protection).
        out["recent_trips"] = [
            {
                "timestamp": t.get("timestamp"),
                "distance_km": t.get("mileage"),
                "duration_min": t.get("traveltime"),
                "avg_speed_kmh": t.get("averageSpeed"),
                "avg_fuel_l_100km": _div10(t.get("averageFuelConsumption")),
                "avg_electric_kwh_100km": _div10(
                    t.get("averageElectricEngineConsumption")
                ),
            }
            for t in short_trips[:5]
        ]

    # Lifetime — from longTerm (since-last-reset aggregate, take [0])
    if long_trips:
        agg = long_trips[0]
        out["lifetime_distance_km"] = (
            float(agg["overallMileage"])
            if isinstance(agg.get("overallMileage"), (int, float))
            else None
        )
        out["lifetime_avg_fuel_consumption_l_100km"] = _div10(
            agg.get("averageFuelConsumption")
        )
        out["lifetime_avg_electric_consumption_kwh_100km"] = _div10(
            agg.get("averageElectricEngineConsumption")
        )

    return out


def _parse_charging_history(resp: Any) -> dict[str, Any]:
    """v1.15.0 (#35) — Pure parser for Skoda mysmob charging-history.

    Response shape (verified myskoda/models/charging_history.py):
        {nextCursor, periods: [{totalChargedInKWh, sessions: [
            {startAt, chargedInKWh, durationInMinutes, currentType: AC|DC}
        ]}]}

    Returns dict ready for ``coordinator.vehicles[vin]``:
    - ``total_charged_energy_kwh`` — sum of every session's chargedInKWh
      across all periods (HA Energy Dashboard / TOTAL_INCREASING)
    - ``last_charging_session_*`` — the most-recent session by ``startAt``
    - ``recent_charging_sessions`` — last 5 sessions for attributes

    Empty dict on no usable data so callers can keep stale cache. Pure
    function — safe to test in isolation.
    """
    out: dict[str, Any] = {}
    if not isinstance(resp, dict):
        return out
    periods = resp.get("periods")
    if not isinstance(periods, list):
        return out

    # Collect all sessions across all periods, plus running cumulative.
    all_sessions: list[dict[str, Any]] = []
    total_kwh = 0.0
    has_any = False
    for period in periods:
        if not isinstance(period, dict):
            continue
        for s in period.get("sessions", []) or []:
            if not isinstance(s, dict):
                continue
            kwh = s.get("chargedInKWh")
            if isinstance(kwh, (int, float)):
                total_kwh += float(kwh)
                has_any = True
            all_sessions.append(s)

    if not has_any:
        return out

    out["total_charged_energy_kwh"] = round(total_kwh, 2)

    # Sort by start timestamp desc (newest first) for "last session" data
    def _start_key(s: dict[str, Any]) -> str:
        v = s.get("startAt")
        return v if isinstance(v, str) else ""

    all_sessions.sort(key=_start_key, reverse=True)
    if all_sessions:
        last = all_sessions[0]
        kwh = last.get("chargedInKWh")
        if isinstance(kwh, (int, float)):
            out["last_charging_session_kwh"] = round(float(kwh), 2)
        dur = last.get("durationInMinutes")
        if isinstance(dur, (int, float)):
            out["last_charging_session_duration_min"] = int(dur)
        ct = last.get("currentType")
        if isinstance(ct, str):
            out["last_charging_session_current_type"] = ct
        st = last.get("startAt")
        if isinstance(st, str):
            out["last_charging_session_start"] = st

        out["recent_charging_sessions"] = [
            {
                "start": s.get("startAt"),
                "kwh": (
                    round(float(s["chargedInKWh"]), 2)
                    if isinstance(s.get("chargedInKWh"), (int, float))
                    else None
                ),
                "duration_min": (
                    int(s["durationInMinutes"])
                    if isinstance(s.get("durationInMinutes"), (int, float))
                    else None
                ),
                "current_type": s.get("currentType")
                if isinstance(s.get("currentType"), str)
                else None,
            }
            for s in all_sessions[:5]
        ]

    return out


def _parse_charging_profiles(resp: Any) -> dict[str, Any]:
    """v1.16.0 (#25, #31) — Pure parser for Skoda charging-profiles
    response. Returns dict ready to merge into ``coordinator.vehicles[vin]``.

    The killer field is ``currentVehiclePositionProfile`` — the backend
    decides which of the user's profiles is active right now based on
    the vehicle's GPS position. That solves #25 (location-based target
    SoC) without us needing to do GPS-zone matching client-side.

    Empty dict on no usable data so callers can keep stale cache.
    Pure function — safe to test in isolation.
    """
    out: dict[str, Any] = {}
    if not isinstance(resp, dict):
        return out
    profiles = resp.get("chargingProfiles")
    if isinstance(profiles, list):
        # Project each profile to a flat attr-friendly dict (drop nested
        # objects that don't serialize cleanly into HA state attributes).
        flat_profiles: list[dict[str, Any]] = []
        for p in profiles:
            if not isinstance(p, dict):
                continue
            settings = p.get("settings") or {}
            min_soc = settings.get("minBatteryStateOfCharge") or {}
            location = p.get("location") or {}
            flat_profiles.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "target_soc_pct": settings.get("targetStateOfChargeInPercent"),
                "max_charging_current": settings.get("maxChargingCurrent"),
                "auto_unlock_plug": settings.get("autoUnlockPlugWhenCharged"),
                "min_battery_soc_pct": min_soc.get(
                    "minimumBatteryStateOfChargeInPercent"
                ),
                # Round GPS to 2 decimals for attribute storage — full
                # precision lives in the device_tracker only.
                "location_lat": (
                    round(float(location["latitude"]), 2)
                    if isinstance(location.get("latitude"), (int, float))
                    else None
                ),
                "location_lon": (
                    round(float(location["longitude"]), 2)
                    if isinstance(location.get("longitude"), (int, float))
                    else None
                ),
                "preferred_times_count": len(
                    p.get("preferredChargingTimes") or []
                ),
                "timers_count": len(p.get("timers") or []),
            })
        out["charging_profiles"] = flat_profiles
        out["charging_profiles_count"] = len(flat_profiles)

    current = resp.get("currentVehiclePositionProfile")
    active_name: str | None = None
    if isinstance(current, dict):
        name = current.get("name")
        if isinstance(name, str):
            out["active_charging_profile_name"] = name
            active_name = name
        target = current.get("targetStateOfChargeInPercent")
        if isinstance(target, (int, float)):
            out["active_charging_profile_target_soc_pct"] = int(target)
        nxt = current.get("nextChargingTime")
        if isinstance(nxt, str) and nxt:
            out["next_charging_time"] = nxt

    # v2.15.10 — expose a top-level ``max_charging_current`` so the Skoda
    # charge-current select can read the current MAXIMUM/REDUCED state
    # without walking the nested ``charging_profiles`` list. The value is
    # only nested per-profile in the API (settings.maxChargingCurrent), so
    # we resolve the *active* profile: prefer the one whose name matches
    # ``currentVehiclePositionProfile.name``; else, if there's exactly one
    # profile, use it. Ambiguous multi-profile cases leave the field unset.
    flat = out.get("charging_profiles")
    if isinstance(flat, list) and flat:
        chosen: dict[str, Any] | None = None
        if active_name is not None:
            chosen = next(
                (p for p in flat if p.get("name") == active_name), None
            )
        if chosen is None and len(flat) == 1:
            chosen = flat[0]
        if isinstance(chosen, dict):
            mcc = chosen.get("max_charging_current")
            if isinstance(mcc, str) and mcc:
                out["max_charging_current"] = mcc
    return out


@dataclass
class FeatureState:
    """Per-VIN per-command state, populated lazily as commands are tried.

    Three orthogonal questions:

    - ``supported_by_vehicle`` — does the VIN have the capability registered
      in the manufacturer backend? Cleared by ``MISSING_CAPABILITY`` errors.
    - ``entitled_by_account`` — does the account currently have permission
      to invoke it? Cleared by ``SUBSCRIPTION_EXPIRED`` / ``NOT_ENTITLED``.
    - ``available_now`` — is the vehicle reachable / awake / responsive
      right now? Transient — reset on success or on every reload.

    ``None`` means "not yet determined" for all three. Don't infer anything
    from a None value; only use this once a real attempt has been made.

    v2.5.10 (#325 roberttco) — when a "definitive no" flag flips to False,
    the entity becomes permanently unavailable for the session. Pre-v2.5.10
    this required a HA restart to clear. v2.5.10 adds ``retry_after`` —
    24 hours after the flag flip, ``is_command_known_unsupported`` returns
    False again so the entity becomes available for one re-attempt. If the
    backend still says no, the flag re-flips immediately. If the backend
    now says yes (e.g. subscription renewed, model-year update), the
    entity stays available — auto-recovery without restart.
    """

    supported_by_vehicle: bool | None = None
    entitled_by_account: bool | None = None
    available_now: bool | None = None
    last_error: CommandFailureReason | None = None
    last_error_at: datetime | None = None
    # v2.5.10 (#325) — auto-recovery timestamp. None means "no recovery
    # attempt scheduled" (i.e. command has never been definitively
    # disabled OR command is currently working). When a definitive-no
    # flag is set, this is populated with now + 24h. ``is_command_known
    # _unsupported`` returns False once this is reached, prompting one
    # re-attempt cycle.
    retry_after: datetime | None = None


class VagConnectCoordinator(DataUpdateCoordinator):
    """Coordinates vehicle data via own CARIAD API client (direct async polling).

    update_interval=None — polling is handled by _poll_loop(), not HA scheduler.
    Updates flow: CARIAD client → _poll_loop → async_set_updated_data → Entities.
    """

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        """Initialise coordinator."""
        self.entry = entry
        self._started = False
        self._was_available: bool = True  # tracks availability for log_when_unavailable
        self._cariad_client: Any = None

        # v2.0.0 (Big-Bang) — Push manager lifecycle slots.
        # Wired by ``async_start_push_manager`` after the first
        # successful poll once the OAuth user_id + VIN list are known.
        # Each is None when the brand doesn't match, the OptionsFlow
        # toggle is OFF, or the lifecycle has been torn down.
        # ``state`` attribute on each manager is consumed by
        # system_health.py for at-a-glance push-channel diagnostics.
        self._skoda_push: Any = None
        self._cupra_seat_push: Any = None
        self._audi_vw_push: Any = None

        # v1.25.0 PR-D Phase 1A: command dispatcher owns lock-map +
        # wake-cooldown state. Coordinator delegates lock acquisition
        # + cooldown checks through the dispatcher. See
        # ``_command_dispatcher.py`` module docstring for refactor plan.
        from ._command_dispatcher import CommandDispatcher  # noqa: PLC0415
        self._dispatcher = CommandDispatcher(self)

        # Thread-safe dict for vehicle data
        self.vehicles: dict[str, Any] = {}
        self._vehicles_lock = threading.Lock()
        # v2.17.2 (#666) — optimistic-command hold: {vin: {key: (value, expiry)}}.
        # Keeps an optimistically-set value in place across polls until the
        # backend confirms it or the window elapses, so a command's UI effect
        # doesn't snap back for the ~10-60 s VW takes to reflect it.
        self._optimistic_hold: dict[str, dict[str, tuple[Any, float]]] = {}

        # Per-VIN poll success tracking — entities use this for availability
        # so a single failing vehicle doesn't blank out the others.
        self.vehicle_success: dict[str, bool] = {}

        # Per-VIN consecutive-failure counter (v1.8.7). Reset to 0 on every
        # successful poll. Used by ``is_vehicle_available`` to apply
        # ``_FAILURE_TOLERANCE`` before flipping availability — prevents
        # single-poll flicker from breaking automations.
        self.vehicle_failure_count: dict[str, int] = {}

        # Per-VIN timestamp of the last successful poll (v1.8.7). Used by
        # ``is_vehicle_available`` together with ``_STALE_CACHE_WINDOW`` to
        # keep entities visible during transient backend outages. Also
        # exposed in diagnostics so users can see how stale the cached
        # state is.
        self.vehicle_last_good_at: dict[str, datetime] = {}

        # v2.15.5 — ABRP (A Better Routeplanner) per-VIN last-successfully-
        # sent telemetry fingerprint. The "ABRP data changed" binary sensor
        # is ON when the current telemetry fingerprint differs from this; the
        # abrp_send service writes the fresh fingerprint here on a 200 so the
        # sensor flips back OFF (idempotent automation trigger). Empty until
        # the first successful send for a VIN.
        self.abrp_last_sent_fingerprint: dict[str, tuple[Any, ...]] = {}

        # Per-VIN capabilities cache. Hydrated best-effort during setup.
        # Read by Capability-Filter Phase 3 (v1.13.0) at PRE-entity-
        # creation gating in ``cariad/_capabilities.py:cap_id_for`` and
        # consumed by ``is_command_known_unsupported`` (line ~1010).
        self.vehicle_capabilities: dict[str, dict[str, Any]] = {}
        self._capabilities_fetched_at: dict[str, datetime] = {}

        # Per-VIN per-command feature state. Hydrated lazily as commands
        # succeed or fail; entry creation is deferred to keep memory tight.
        self.feature_states: dict[str, dict[str, FeatureState]] = {}

        # Per-VIN command profile (Session 3A). Brand clients read this to
        # pick the right URL prefix — e.g. AudiClient swaps /vehicle/v1/
        # for /vehicle/v2/ on PPE/Premium models that 404 the v1 paths.
        # Default UNKNOWN means "use the brand client's current default
        # and let it auto-detect". Persisted only in memory — gets re-
        # learned on every restart, which is cheap (one extra 404 per
        # cold start per VIN).
        self.vehicle_command_profile: dict[str, CommandProfile] = {}

        # Reverse-geocoding cache: {(round(lat,3), round(lon,3)): result}
        self._geocode_cache: dict[tuple[float, float], dict[str, str | None]] = {}

        # v1.9.0 — Vehicle Data Scout state. Per-VIN dict of
        # {path -> UnexpectedField}, de-duped so the same drift seen on
        # every poll only reports once. Surfaced via the
        # ``api_observer_findings`` sensor and the
        # ``vehicle_data_scout_findings`` HA repair issue.
        self.unexpected_findings: dict[str, dict[str, UnexpectedField]] = {}

        # v1.9.0 — Error Reporter ring buffer (last 20 captured exceptions).
        # Surfaced via the ``error_reporter_count`` sensor and the
        # ``error_reporter_findings`` HA repair issue. Bounded so memory
        # and the diagnostics export size stay predictable.
        self.error_buffer: ErrorRingBuffer = ErrorRingBuffer()

        # update_interval=None: no HA-level polling
        # Updates arrive reactively via _on_cc_update → async_set_updated_data
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=None,
        )


    async def async_setup(self) -> bool:
        """Authenticate and fetch initial vehicle data via own CARIAD client."""
        from homeassistant.helpers.aiohttp_client import async_get_clientsession  # noqa: PLC0415
        from .cariad import CariadClientFactory  # noqa: PLC0415
        from .cariad.exceptions import (  # noqa: PLC0415
            AuthenticationError,
            EmailTwoFactorRequiredError,
            PortalInteractionRequiredError,
            TermsAndConditionsError,
            MarketingConsentError,
            TwoFactorRequiredError,
            RateLimitError,
        )

        brand    = self.entry.data[CONF_BRAND]
        username = self.entry.data[CONF_USERNAME]
        password = self.entry.data[CONF_PASSWORD]
        spin     = self.entry.data.get(CONF_SPIN) or ""

        # v2.4.1 (#281+#282) — OLA defense-in-depth Layer 2: read the
        # advanced power-user overrides from entry.data (or empty if not
        # set). Forwarded only to SEAT/CUPRA clients via the factory;
        # other brands ignore the kwargs cleanly. Empty string / missing
        # = use _ola_headers.py built-in defaults.
        from .const import CONF_OLA_APP_VERSION_OVERRIDE, CONF_OLA_USER_AGENT_OVERRIDE  # noqa: PLC0415
        ola_app_v = self.entry.data.get(CONF_OLA_APP_VERSION_OVERRIDE) or None
        ola_ua    = self.entry.data.get(CONF_OLA_USER_AGENT_OVERRIDE) or None

        # v2.10.4 — read OAuth client_id override from entry options
        # (preferred, set via OptionsFlow) with fallback to entry.data
        # (legacy / config-flow-time override).
        from .const import CONF_CLIENT_ID_OVERRIDE  # noqa: PLC0415
        client_id_override = (
            self.entry.options.get(CONF_CLIENT_ID_OVERRIDE)
            or self.entry.data.get(CONF_CLIENT_ID_OVERRIDE)
            or ""
        ).strip() or None

        session = async_get_clientsession(self.hass)
        self._cariad_client = CariadClientFactory.create(
            brand, session, username, password, spin,
            # v2.15.1 (#503) — Volkswagen US/Canada region. Only the
            # volkswagen_na client consumes it; every other brand ignores
            # the kwarg. Default "us" for entries created before this field.
            country=self.entry.data.get(CONF_COUNTRY, "us"),
            ola_app_version_override=ola_app_v,
            ola_user_agent_override=ola_ua,
        )
        # v2.10.4 — push the user-supplied OAuth client_id override
        # onto the underlying IDKAuth instance so the AuthConfigResolver
        # prepends it to the chain. No-op when override is None.
        if client_id_override and hasattr(self._cariad_client, "_auth"):
            inner_auth = getattr(self._cariad_client, "_auth", None)
            if inner_auth is not None and hasattr(
                inner_auth, "set_user_client_id_override"
            ):
                inner_auth.set_user_client_id_override(client_id_override)

        # v2.14.0 — OPT-IN, BETA. When the entry was created via the
        # "Volkswagen.de website (beta)" config-flow option, flip the brand
        # client into website-authproxy mode BEFORE the first authenticate().
        # Gated on the explicit per-entry flag + brand == volkswagen + the
        # client supporting the setter, so this is a no-op for every other
        # entry and leaves all existing strategy paths untouched.
        from .const import (  # noqa: PLC0415
            CONF_WEBSITE_AUTHPROXY,
            CONF_WEBSITE_COOKIES,
        )
        if (
            brand == "volkswagen"
            and self.entry.data.get(CONF_WEBSITE_AUTHPROXY)
            and hasattr(self._cariad_client, "set_website_authproxy_mode")
        ):
            # v2.14.3 — hand the brand client the cookies the config flow
            # persisted after its login (incl. email-OTP). _arm_website_proxy
            # hydrates them before begin_login() so the session resumes without
            # re-prompting the OTP on this setup/restart. Empty list / absent =
            # the prior fresh-login behaviour (which re-raised on 2FA).
            persisted_cookies = self.entry.data.get(CONF_WEBSITE_COOKIES) or []
            self._cariad_client.set_website_authproxy_mode(
                True, cookies=persisted_cookies,
            )
            _LOGGER.info(
                "VAG Connect: volkswagen.de website-authproxy mode enabled "
                "(opt-in, read-only beta) for this entry%s.",
                " — resuming from persisted cookies" if persisted_cookies
                else "",
            )

        # v1.19.2 (#118 eismarkt) — token persistence wire-up.
        # Load any persisted IDK tokens from HA storage BEFORE the
        # first authenticate() so HACS updates / HA restarts don't
        # force a full re-login (was burning ~2-3s + counting against
        # daily quota + occasionally triggering the v1.8.7 token-
        # refresh-storm protection on consecutive transient failures).
        # Hook the persistence callback so every successful refresh
        # writes back automatically.
        from homeassistant.helpers.storage import Store  # noqa: PLC0415
        from .cariad.auth._token_storage import (  # noqa: PLC0415
            TokenStorage,
            storage_key_for_entry,
            _STORAGE_VERSION,
        )
        store: Store[dict[str, Any]] = Store(
            self.hass,
            _STORAGE_VERSION,
            storage_key_for_entry(self.entry.entry_id),
        )
        self._token_storage = TokenStorage(store)
        persisted = await self._token_storage.load()

        # b13 — Portal-safety: restore the last-known-good vehicle snapshot so
        # entities show their recorded values immediately on restart (not
        # "unknown" until the first poll completes), and a first-poll outage
        # still has a cache to fall back to. Best-effort; never blocks setup.
        from homeassistant.helpers.json import JSONEncoder  # noqa: PLC0415
        from .cariad.vehicle_cache import (  # noqa: PLC0415
            VEHICLE_CACHE_VERSION,
            vehicle_cache_key,
        )
        self._vehicle_store: Store[dict[str, Any]] = Store(
            self.hass,
            VEHICLE_CACHE_VERSION,
            vehicle_cache_key(self.entry.entry_id),
            encoder=JSONEncoder,
        )
        try:
            cached = await self._vehicle_store.async_load()
        except Exception:  # noqa: BLE001
            cached = None
        if cached and isinstance(cached.get("vehicles"), dict):
            with self._vehicles_lock:
                for vin, vdata in cached["vehicles"].items():
                    if vin == "_meta" or vin in self.vehicles:
                        continue
                    if isinstance(vdata, dict):
                        restored = dict(vdata)
                        restored["_restored"] = True
                        restored["_poll_failed"] = False
                        self.vehicles[vin] = restored
            _LOGGER.debug(
                "VAG Connect portal-safety: restored %d cached vehicle(s) "
                "for %s", len(self.vehicles), brand,
            )

        # b13 — MEB/ID known-limitation. Setup flags an entry when the user
        # asked for MBB commands but the car is MEB-ineligible (the portal
        # entry was created read-only). Surface a clear repair so it's a known
        # limit, not a silent missing-command-entities failure.
        if self.entry.data.get(CONF_MEB_COMMANDS_UNAVAILABLE):
            from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"meb_commands_unavailable_{self.entry.entry_id}",
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="meb_commands_unavailable",
                translation_placeholders={"brand": self.entry.data.get(CONF_BRAND, "")},
            )

        # v2.7.0 — config_flow's browser-login (DAG) flow stashes the
        # initial tokens in entry.data["dag_initial_tokens"] because
        # the persistent storage hadn't been set up yet at that point.
        # Promote those into the persistent store on the first run, then
        # behave like a normal restart from cached tokens.
        if persisted is None:
            dag_initial = self.entry.data.get("dag_initial_tokens")
            if dag_initial:
                from .cariad.models import TokenSet  # noqa: PLC0415
                persisted = TokenSet(
                    access_token=str(dag_initial.get("access_token", "")),
                    refresh_token=str(dag_initial.get("refresh_token", "")),
                    id_token=str(dag_initial.get("id_token", "")),
                    expires_at=float(dag_initial.get("expires_at", 0.0)),
                    strategy=str(dag_initial.get("strategy", "")),
                )
                _LOGGER.debug(
                    "VAG Connect: bootstrapping with DAG initial tokens "
                    "for %s (strategy=%s)", brand, persisted.strategy,
                )
                # Save immediately so the entry.data copy can be cleaned
                # up on a subsequent config_flow update.
                await self._token_storage.save(persisted)

        if persisted is not None:
            self._cariad_client.set_persisted_tokens(persisted)
            # v2.15.0 — thread the registered MBB X-Client-Id into the client
            # so the durable MBB strategy's refresh + VSR read + RLU command
            # all send the same client id that minted the bearer (a mismatch
            # 403s). No-op for every non-MBB entry (attribute defaults to "").
            if getattr(persisted, "strategy", "") == "mbb":
                self._cariad_client._mbb_client_id = self.entry.data.get(
                    "mbb_client_id", ""
                )
                # User-supplied VIN(s) — the fal-scoped MBB bearer can't list
                # the garage, so get_vehicles returns these directly.
                from .const import CONF_MBB_VINS  # noqa: PLC0415
                mbb_vins = self.entry.data.get(CONF_MBB_VINS) or []
                if isinstance(mbb_vins, str):
                    mbb_vins = [
                        v.strip().upper()
                        for v in mbb_vins.replace(",", " ").split()
                        if v.strip()
                    ]
                self._cariad_client._mbb_manual_vins = list(mbb_vins)
        # Fire-and-forget save callback — never blocks API path.
        self._cariad_client.on_tokens_changed = self._token_storage.save

        try:
            # If persisted tokens were loaded successfully, the next
            # API call will use them directly; the 401 path triggers
            # _refresh_tokens which writes back. We still call
            # authenticate() if NO persisted tokens exist (first setup,
            # storage cleared, or version mismatch).
            # v2.12.1 (#393) — the EU Data Act portal strategy persists a
            # cookie-session SENTINEL token (no usable bearer, and the
            # cookie jar isn't restored across restarts). Reusing it skips
            # the portal login, so the connector is never rebuilt and
            # get_vehicles falls through to the dead CARIAD BFF with the
            # sentinel → HTTP 400 "missing or invalid auth header". Force a
            # fresh login for that strategy so the cookie session + the
            # portal connector are re-established on every restart.
            # v2.14.0 — the website-authproxy sentinel is the same shape: a
            # cookie session, no usable bearer, and the cookie jar isn't
            # restored across restarts. Reusing it would skip the login and
            # leave _website_proxy unarmed → get_status falls through to the
            # dead BFF. Force a fresh login so the connector is rebuilt.
            persisted_is_portal = (
                persisted is not None
                and persisted.strategy in (
                    "data_act_portal", "website_authproxy",
                )
            )
            if persisted is None or persisted_is_portal:
                await self._cariad_client.authenticate()
                # v2.14.3 — the website-authproxy login rotates the cookie jar;
                # persist the fresh cookies back so the NEXT setup/restart
                # resumes the session (and keeps skipping the OTP prompt).
                # Guarded so it only ever touches website-authproxy entries.
                self._persist_website_cookies()
            else:
                _LOGGER.debug(
                    "VAG Connect: using persisted IDK tokens for %s "
                    "— skipping fresh login",
                    brand,
                )
            # v2.15.0b1 (C1) — arm any supplementary read channel (e.g. vw.de)
            # AFTER the primary authenticate, so the per-poll merge has it.
            # No-op when none configured; fail-soft (primary unaffected).
            await self._arm_supplementary_channels()
            # v2.15.0b7 — pre-warm the EU Data Act dictionary cache OFF the event
            # loop so the Scout report's describe() lookups (which run in-loop)
            # never trigger a blocking 288 KB file read. lru_cached → one warm-up.
            try:
                from .cariad.auth import eu_data_dictionary as _dd  # noqa: PLC0415
                await self.hass.async_add_executor_job(_dd._load)
            except Exception:  # noqa: BLE001
                pass
            vins = await self._cariad_client.get_vehicles()
            if not vins:
                return False

            # Fetch status for all vehicles
            results = await asyncio.gather(
                *[self._cariad_client.get_status(vin) for vin in vins],
                return_exceptions=True,
            )

            # v2.18.0 (A1) — merge + enrich BEFORE taking the lock, then only
            # assign while holding it.
            #
            # Two reasons. (1) This path never merged at all: the poll loop
            # unions the armed supplementary channels onto the primary, this
            # one stored the raw primary, so the first snapshot after every
            # setup/restart was primary-only and supplementary fields stayed
            # blank until the first poll tick. (2) ``_vehicles_lock`` is a
            # threading.Lock, and awaiting while holding one parks the whole
            # event loop for any other task that tries to acquire it — the
            # merge does network I/O, so it must not run inside.
            prepared: list[tuple[str, dict[str, Any] | None, bool]] = []
            for vin, result in zip(vins, results):
                if isinstance(result, Exception):
                    _LOGGER.warning("Could not fetch status for %s: %s", mask_vin(vin), result)
                    prepared.append((vin, None, True))
                    continue
                if isinstance(result, VehicleData):
                    merged = await self._merge_supplementary(vin, result)
                    data = merged.to_dict()
                    data["_client"] = self._cariad_client
                    prepared.append((vin, await self._enrich(data), False))

            with self._vehicles_lock:
                for vin, prepared_data, failed in prepared:
                    if failed or prepared_data is None:
                        if hasattr(self, "vehicle_success"):
                            self.vehicle_success[vin] = False
                        continue
                    self.vehicles[vin] = self._apply_optimistic_hold(vin, prepared_data)
                    if hasattr(self, "vehicle_success"):
                        self.vehicle_success[vin] = True

            # Best-effort capabilities prefetch — never blocks setup.
            # Result lives in self.vehicle_capabilities for entity platforms
            # to read in Session 2B. Failure is debug-logged and ignored.
            await asyncio.gather(
                *[self.refresh_capabilities(vin) for vin in self.vehicles],
                return_exceptions=True,
            )

            # v1.20.0 Bundle 2 Phase A — Skoda static-info prefetch.
            # Only Skoda gets the vehicle-information + equipment 24h
            # cache (other brands return early in refresh_static_info).
            # Failure debug-logged, never blocks setup.
            await asyncio.gather(
                *[self.refresh_static_info(vin) for vin in self.vehicles],
                return_exceptions=True,
            )

            self._started = True
            found = len(self.vehicles)
            _LOGGER.info("VAG Connect: setup complete — %d vehicle(s)", found)

            # v2.10.5 — EU Data Act portal Custom Data Request first-time
            # kickoff. Fires unless (a) the user turned OFF the OptionsFlow
            # toggle CONF_EU_DATA_ACT_AUTO_KICKOFF (v2.17.1: default ON) and
            # only when (b) we actually authenticated via a portal strategy.
            # Best-effort: any failure is debug-logged and never blocks
            # setup. Session-expiry surfaces a Repairs issue.
            try:
                await self._ensure_data_act_custom_request_kickoff()
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Data Act kickoff helper raised - non-fatal, continuing",
                    exc_info=True,
                )

            # Start background polling — use background task so HA bootstrap doesn't wait
            self.hass.async_create_background_task(self._poll_loop(), f"{DOMAIN}_poll")
            return found > 0

        except TermsAndConditionsError as err:
            raise ValueError("terms_and_conditions") from err
        except MarketingConsentError as err:
            raise ValueError("marketing_consent") from err
        # v2.2.0 PR #7/20 (#183 follow-on) — Email-OTP subclass MUST be
        # caught BEFORE the generic TwoFactorRequiredError parent (Python
        # exception-handler order is first-match).
        except EmailTwoFactorRequiredError as err:
            raise ValueError("email_two_factor_required") from err
        except TwoFactorRequiredError as err:
            raise ValueError("two_factor_required") from err
        except RateLimitError as err:
            raise ValueError("too_many_requests") from err
        # v2.15.4 (#527) — a non-credential EU Data Act portal stop
        # (onboarding/region/soft-block, or a portal error with a real
        # errorCode). Subclass of AuthenticationError, so it MUST be caught
        # before the credential catch-all — otherwise valid-credential users
        # get told to fix their password.
        except PortalInteractionRequiredError as err:
            raise ValueError("portal_interaction_required") from err
        except AuthenticationError as err:
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            # v2.7.2 — never log the raw exception message at ERROR
            # level. aiohttp.InvalidURL and similar carry the full
            # request URL in __str__, which on the OAuth callback path
            # is `weconnect://authenticated#access_token=<JWT>&id_token=
            # <JWT>&code=<JWT>...`. Those JWTs base64-decode to the
            # user's email and a working access token. Log type only at
            # ERROR; route the message to DEBUG for triage.
            _LOGGER.error(
                "VAG Connect setup failed: %s "
                "(message redacted, see DEBUG for details)",
                type(err).__name__,
            )
            _LOGGER.debug("VAG Connect setup failed details: %s", err)
            return False

    def _trigger_reauth(self, reason: str) -> None:
        """Stop the poll loop and ask HA to start the reauth flow.

        Used when refresh + re-login both fail at runtime so the user gets a
        proper UI prompt instead of a silently failing integration that floods
        the log with retries.
        """
        self._started = False
        for vin in list(self.vehicles.keys()):
            self.vehicle_success[vin] = False
        try:
            self.entry.async_start_reauth(self.hass)
        except Exception:  # noqa: BLE001
            # entry may not support reauth in tests; the loop stop is enough.
            pass
        _LOGGER.error("VAG Connect: stopping poll loop, reauth required (%s)", reason)

    # v2.9.0 - provenance canary, see ``_canaries.py``. Class-level
    # attribute so any port of the silent-recovery watchdog logic
    # carries the marker into the destination repo.
    _PROVENANCE_WATCHDOG = "watchdog_silentauth_provenance_n2vpw9c3_2026"

    async def _maybe_run_stale_watchdog(self) -> None:
        """v2.8.0 — silent re-authenticate when hybrid_full goes stale.

        VW EU users on the `hybrid_full` strategy have no real
        refresh_token (Play Integrity walls the BFF token endpoint).
        The access_token expires after ~2 hours and the integration
        starts returning failed polls. Before this watchdog, the
        symptom was a silently dead integration that users had to
        reload by hand (a common pattern in the upstream VW HA
        community ran on template-trigger automations).

        Gating logic:
          - Active strategy must be `hybrid_full`. Other strategies
            (`device_grant`, `classic`, `data_act_portal`) handle
            their own refresh paths via refresh_token / re-fetch.
          - All VINs must have failure_count >= 2 (single transient
            hiccups do not trigger).
          - All VINs must have last_good_at older than
            2x scan_interval (ensures we are not racing a temporary
            network blip).

        On match, fires `self._cariad_client.authenticate()` again
        using the same Brand-ID credentials stored in entry.data. On
        success, the access_token is refreshed in place and the next
        poll cycle succeeds without user interaction. On failure,
        we fall through to standard behaviour, the existing outer
        exception handler then triggers the HA reauth dialog.
        """
        if not self._started or self._cariad_client is None:
            return
        tokens = getattr(self._cariad_client, "_tokens", None)
        if tokens is None or getattr(tokens, "strategy", "") != "hybrid_full":
            return
        if not getattr(self, "vehicle_last_good_at", None):
            return
        if not self.vehicle_last_good_at:
            return

        interval_s = max(
            int(
                self.entry.options.get(CONF_SCAN_INTERVAL)
                or self.entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ) * 60,
            _CC_MIN_INTERVAL_S,
        )
        stale_threshold_s = 2 * interval_s
        now = datetime.now(tz=timezone.utc)

        all_stale = True
        for vin, last_good in self.vehicle_last_good_at.items():
            elapsed = (now - last_good).total_seconds()
            if elapsed < stale_threshold_s:
                all_stale = False
                break
            if self.vehicle_failure_count.get(vin, 0) < 2:
                all_stale = False
                break
        if not all_stale:
            return

        _LOGGER.info(
            "VAG Connect: hybrid_full watchdog — every VIN stale for "
            ">%ds with >=2 consecutive failures. Triggering silent "
            "re-authenticate before next poll attempt.",
            stale_threshold_s,
        )
        try:
            await self._cariad_client.authenticate()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "VAG Connect: watchdog silent re-auth raised %s. "
                "Falling through to standard poll behaviour; if the "
                "next poll also fails, the existing reauth handler "
                "will surface to the user.",
                type(err).__name__,
            )
            return
        # Reset failure counts so the next poll iteration has a
        # clean slate; otherwise we would re-trigger the watchdog
        # immediately even after a successful re-auth.
        for vin in list(self.vehicle_failure_count.keys()):
            self.vehicle_failure_count[vin] = 0
        _LOGGER.info(
            "VAG Connect: watchdog silent re-auth succeeded, "
            "failure counts cleared. Next poll should recover."
        )

    async def _ensure_data_act_custom_request_kickoff(
        self, *, force: bool = False
    ) -> None:
        """v2.10.5 - check + first-time kickoff for the EU Data Act
        portal's 15-min Custom Data Request per VIN.

        No-op unless ALL three conditions hold:

        1. ``CONF_EU_DATA_ACT_AUTO_KICKOFF`` is True in entry.options
           (v2.17.1: default True — the integration can't receive data in
           portal mode without a request, so we provision one unless the
           user explicitly turned auto-kickoff off) OR ``force`` is set
           (the user pressed the manual "create data request" button, an
           explicit intent that bypasses the toggle).
        2. The active auth strategy is ``"data_act_portal"`` (the
           coordinator only knows how to consume the portal's ZIP
           dumps in that mode; for the live BFF strategies there is
           no need to ever go through the portal).
        3. The DataActScraper is available (always true since
           v2.10.0; defensive check kept for future refactors).

        For each VIN: try ``get_active_custom_request_identifier``,
        and if it returns None, call ``kickoff_custom_data_request``.
        Resulting Identifiers are persisted to
        ``entry.options[CONF_DATA_ACT_IDENTIFIERS]`` keyed by VIN so
        subsequent polls can match without another metadata round-trip.

        Session expiry (HTTP 401) opens a Repairs issue
        ``data_act_session_expired`` and the kickoff is skipped this
        cycle.
        """
        from .const import (  # noqa: PLC0415
            CONF_DATA_ACT_IDENTIFIERS,
            CONF_EU_DATA_ACT_AUTO_KICKOFF,
            CONF_SUPPLEMENTARY_EU_PORTAL,
        )

        # v2.17.1 — default ON. The integration is useless in portal mode
        # without an active Custom Data Request, and the other community
        # EU-Data-Act readers simply refuse to install without one — so a user
        # who installs us but hasn't set one up manually just gets empty
        # entities. We ship the only provisioner that CAN create it, so we do,
        # unless the user explicitly turned it off. A one-time notification
        # tells them a request was created (see _notify_data_act_kickoff).
        if not force and not self.entry.options.get(
            CONF_EU_DATA_ACT_AUTO_KICKOFF,
            self.entry.data.get(CONF_EU_DATA_ACT_AUTO_KICKOFF, True),
        ):
            return

        tokens = getattr(self._cariad_client, "_tokens", None)
        active_strategy = getattr(tokens, "strategy", "") if tokens else ""
        # v2.13.0 — device-code/QR portal entries (device_grant_portal) use the
        # same EU-Data-Act portal proxy_api, so they need the continuous
        # data-request kickoff too, not just the cookie data_act_portal path.
        # b12 — AND a portal SUPPLEMENTARY armed on a non-portal primary (e.g.
        # MBB for commands) needs it too: without an active Custom Data Request
        # the portal returns no identifier → no_request → zero reads merged. The
        # kickoff scraper shares the client session, where the supplementary
        # portal already logged in (armed before this runs), so it's authed.
        supp_portal = self.entry.data.get(CONF_SUPPLEMENTARY_EU_PORTAL)
        if (
            active_strategy not in ("data_act_portal", "device_grant_portal")
            and not supp_portal
        ):
            _LOGGER.debug(
                "Data Act kickoff: skipped (strategy %r, no supplementary "
                "portal)", active_strategy,
            )
            return

        from .cariad.auth._data_act_scraper import (  # noqa: PLC0415
            DataActScraper,
            DataActSessionExpiredError,
        )
        from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
            async_get_clientsession,
        )

        session = async_get_clientsession(self.hass)
        brand = self.entry.data[CONF_BRAND]
        scraper = DataActScraper(session, brand_name=brand)

        # v2.18.0 — options THEN data. The write below lands in entry.options,
        # but the update-listener immediately folds options into entry.data and
        # blanks entry.options (__init__.py), so an options-only read never
        # found the cached map and every setup re-probed the portal for
        # identifiers it had already resolved.
        existing_map = dict(
            self.entry.options.get(CONF_DATA_ACT_IDENTIFIERS)
            or self.entry.data.get(CONF_DATA_ACT_IDENTIFIERS)
            or {}
        )
        new_map = dict(existing_map)
        changed = False

        for vin in list(self.vehicles):
            try:
                active = await scraper.get_active_custom_request_identifier(vin)
                if active:
                    if new_map.get(vin) != active:
                        new_map[vin] = active
                        changed = True
                        _LOGGER.info(
                            "Data Act kickoff: VIN %s already has active "
                            "15min Custom Request (Identifier=%s...), "
                            "adopting it.",
                            mask_vin(vin), active[:8],
                        )
                    continue
                # No active request - kick one off.
                new_id = await scraper.kickoff_custom_data_request(vin)
                if new_id:
                    new_map[vin] = new_id
                    changed = True
                    _LOGGER.info(
                        "Data Act: created a continuous 15-min Custom Data "
                        "Request for VIN %s (Identifier=%s...) so data can flow.",
                        mask_vin(vin), new_id[:8],
                    )
                    self._notify_data_act_kickoff(vin)
            except DataActSessionExpiredError:
                self._raise_data_act_session_expired_repair()
                return  # stop processing further VINs this cycle
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Data Act kickoff: VIN %s probe failed (%s) - skipping",
                    mask_vin(vin), exc,
                )

        if changed:
            self.hass.config_entries.async_update_entry(
                self.entry,
                options={**self.entry.options, CONF_DATA_ACT_IDENTIFIERS: new_map},
            )

    def _notify_data_act_kickoff(self, vin: str) -> None:
        """One-time transparency notice that we created a portal data request."""
        try:
            from homeassistant.components import (  # noqa: PLC0415
                persistent_notification,
            )
            persistent_notification.async_create(
                self.hass,
                (
                    "VAG Connect enabled a **continuous 15-minute data request** "
                    "on your VW Group EU Data Act portal account so the "
                    "integration can receive data. The first delivery can take "
                    "15–60 minutes. You can turn automatic provisioning off under "
                    "the integration's **Configure → EU Data Act auto-kickoff**."
                ),
                title="VAG Connect: data request created",
                notification_id=f"vag_connect_dataact_kickoff_{vin[-6:]}",
            )
        except Exception:  # noqa: BLE001
            pass

    async def async_request_historical_export(self, vin: str) -> bool:
        """Phase C — ask the portal for a ONE-TIME historical export of *vin*.

        Distinct from the 15-min feed: this is a config snapshot (timers, charge
        profiles, climate settings) in the legacy Car-Net dialect. The portal
        builds the ZIP asynchronously (observed ~30 min, up to 24h). Once ready,
        ``async_import_historical_export`` fetches + merges it. Returns True when
        the request was accepted.
        """
        from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
            async_get_clientsession,
        )

        from .cariad.auth._data_act_scraper import (  # noqa: PLC0415
            DataActScraper,
            DataActSessionExpiredError,
        )

        session = async_get_clientsession(self.hass)
        scraper = DataActScraper(session, brand_name=self.entry.data[CONF_BRAND])
        try:
            return await scraper.kickoff_historical_export(vin)
        except DataActSessionExpiredError:
            self._raise_data_act_session_expired_repair()
            return False

    async def async_import_historical_export(self, vin: str) -> bool:
        """Phase C — fetch a READY one-time export for *vin* and merge its config
        fields into the live snapshot.

        Gap-fill only: a field is taken from the historical export ONLY where the
        live snapshot has none, so live telemetry (SoC, charging state, the
        drivetrain flags) is never overwritten by the older config dump — this is
        also why the legacy dialect's missing-combustion evidence can't flip a
        live PHEV to electric. Returns True if anything merged, False if the ZIP
        isn't ready yet (the portal generates it asynchronously).
        """
        portal = getattr(self._cariad_client, "_eu_portal", None)
        if portal is None or not hasattr(portal, "get_vehicle_data"):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="historical_portal_not_ready",
            )
        historical = await portal.get_vehicle_data(vin, request_type="all")
        if getattr(historical, "no_data", True):
            return False
        hist = historical.to_dict()
        merged_any = False
        with self._vehicles_lock:
            current = self.vehicles.get(vin)
            if not isinstance(current, dict):
                # A portal-only car we had nothing for yet — take the snapshot.
                self.vehicles[vin] = hist
                merged_any = True
            else:
                for key, val in hist.items():
                    if val is None:
                        continue
                    if current.get(key) is None:  # never clobber a live value
                        current[key] = val
                        merged_any = True
        if merged_any:
            self.async_set_updated_data(dict(self.vehicles))
            _LOGGER.info(
                "EU Data Act: merged one-time historical export config fields "
                "for VIN %s", mask_vin(vin),
            )
        return merged_any

    async def _maybe_runtime_data_act_kickoff(self) -> None:
        """Re-provision the portal Custom Data Request at RUNTIME when a poll
        came back ``no_request`` (no active request on the portal).

        The startup kickoff handles the common case; this catches a request
        that never existed or disappeared while the integration is running, so
        "no data comes in" self-heals instead of sitting on empty entities.
        Rate-limited to once per 6 h so we never hammer the portal (which
        allows at most one active request per VIN anyway)."""
        import time  # noqa: PLC0415
        now = time.monotonic()
        # None sentinel = never fired → always allow the first runtime kickoff.
        # (Comparing against 0.0 would suppress it for the host's first 6 h of
        # uptime, because monotonic() starts near 0 on a fresh boot.)
        last = getattr(self, "_last_runtime_kickoff", None)
        if last is not None and now - last < 6 * 3600:
            return
        self._last_runtime_kickoff = now
        try:
            await self._ensure_data_act_custom_request_kickoff()
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Data Act runtime kickoff raised — non-fatal", exc_info=True,
            )

    async def async_create_data_act_request(self) -> None:
        """User-triggered (button): (re)create/refresh the EU-Data-Act
        continuous data request now. Runs even when automatic provisioning
        is turned off — pressing the button is explicit intent (``force``)."""
        import time  # noqa: PLC0415
        # Rate-limit the runtime auto-path after a manual press (a request
        # now exists), but the create itself always runs via force=True.
        self._last_runtime_kickoff = time.monotonic()
        await self._ensure_data_act_custom_request_kickoff(force=True)
        await self.async_request_refresh()

    def _raise_data_act_session_expired_repair(self) -> None:
        """v2.10.5 - open a Repairs issue when the portal session
        cookies expired and the integration needs the user to
        reauthenticate via the OptionsFlow re-login button.
        """
        from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"data_act_session_expired_{self.entry.entry_id}",
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="data_act_session_expired",
            translation_placeholders={
                "brand": self.entry.data[CONF_BRAND],
            },
        )

    def _update_data_act_no_data_repair(self) -> None:
        """v2.12.2 (#393/#424) — raise/clear the "portal returned no data"
        repair issue for EU Data Act portal mode.

        The portal connector records ``last_no_data_reason`` each poll. When
        it's non-empty the portal logged in but delivered nothing — usually
        the VW-side all-brands outage that started late May 2026, or the
        user hasn't created a continuous data request yet. We surface a
        single actionable repair issue pointing them to check the portal
        website themselves; it auto-clears the moment data arrives.
        """
        from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

        # b12 — also surface the reason for a portal SUPPLEMENTARY (it records
        # the same last_no_data_reason); previously only the PRIMARY portal was
        # checked, so a supplementary portal returning no_request/empty failed
        # SILENTLY (the user saw "added but no data" with nothing in the log).
        portal = (
            getattr(self._cariad_client, "_eu_portal", None)
            or getattr(self._cariad_client, "_supplementary_eu_portal", None)
        )
        issue_id = f"data_act_no_data_{self.entry.entry_id}"
        reason = getattr(portal, "last_no_data_reason", "") if portal else ""
        if portal is None or not reason:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="data_act_no_data",
            translation_placeholders={
                "brand": self.entry.data[CONF_BRAND],
            },
        )

    def _primary_channel_name(self) -> str:
        """v2.15.0b1 (C1) — label for the primary channel, for merge provenance.

        The primary is the command-capable (or first-configured) channel; it
        stays highest priority in the merge so read-only supplementary channels
        only ever fill gaps."""
        from .const import CONF_WEBSITE_AUTHPROXY  # noqa: PLC0415
        data = self.entry.data
        if data.get(CONF_WEBSITE_AUTHPROXY):
            return "website_authproxy"
        dag = data.get("dag_initial_tokens") or {}
        if dag.get("strategy") == "mbb":
            return "mbb"
        if getattr(self._cariad_client, "_eu_portal", None) is not None:
            return "eu_data_act"
        return str(data.get(CONF_BRAND, "")) or "primary"

    async def _arm_supplementary_channels(self) -> None:
        """v2.15.0b1 (C1) — arm configured supplementary read channels on the
        client. No-op when none configured → single-channel setup unchanged;
        fail-soft so a supplementary channel never blocks setup."""
        from .const import (  # noqa: PLC0415
            CONF_SUPPLEMENTARY_AUTHPROXY,
            CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
            CONF_SUPPLEMENTARY_EU_PORTAL,
            CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
            CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
            CONF_SUPPLEMENTARY_TIBBER,
            CONF_SUPPLEMENTARY_TIBBER_TOKENS,
        )
        data = self.entry.data
        client = self._cariad_client

        # ── vw.de supplementary (cookie-based, OTP-bound) ───────────────────
        arm_web = getattr(client, "arm_supplementary_authproxy", None)
        if data.get(CONF_SUPPLEMENTARY_AUTHPROXY) and arm_web is not None:
            cookies = data.get(CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES) or []
            armed = False
            try:
                armed = bool(await arm_web(cookies))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "VAG Connect: supplementary vw.de arming failed (%s)"
                    " — primary channel unaffected.", type(err).__name__,
                )
            # v2.15.0b5 — graceful "re-login" Repair when the OTP-bound vw.de
            # session can't resume; cleared once it arms again.
            from .repairs import (  # noqa: PLC0415
                clear_supplementary_reauth_issue,
                raise_issue_supplementary_reauth,
            )
            if not armed and getattr(client, "_supplementary_needs_reauth", False):
                raise_issue_supplementary_reauth(self.hass, self.entry.entry_id)
            else:
                clear_supplementary_reauth_issue(self.hass, self.entry.entry_id)
        else:
            # b11 — vw.de not configured (or just removed via the off-switch):
            # clear any stale "re-login" Repair so a removed channel stops nagging.
            from .repairs import (  # noqa: PLC0415
                clear_supplementary_reauth_issue,
            )
            clear_supplementary_reauth_issue(self.hass, self.entry.entry_id)

        # ── EU Data Act portal supplementary (email/pw, reliable) ───────────
        arm_portal = getattr(client, "arm_supplementary_eu_portal", None)
        if data.get(CONF_SUPPLEMENTARY_EU_PORTAL) and arm_portal is not None:
            try:
                await arm_portal(
                    data.get(CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME),
                    data.get(CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD),
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "VAG Connect: supplementary portal arming failed (%s)"
                    " — primary channel unaffected.", type(err).__name__,
                )

        # ── v2.19.0: TIBBER supplementary (OAuth2, read-only gap-fill) ──────
        arm_tibber = getattr(client, "arm_supplementary_tibber", None)
        if data.get(CONF_SUPPLEMENTARY_TIBBER) and arm_tibber is not None:
            try:
                armed = bool(
                    await arm_tibber(data.get(CONF_SUPPLEMENTARY_TIBBER_TOKENS))
                )
                if armed:
                    # the OAuth2 refresh token rotates in place — persist it back
                    # to entry.data so a restart never replays a consumed token.
                    src = getattr(client, "_supplementary_tibber", None)
                    if src is not None:
                        src.on_tokens_changed = self._persist_tibber_tokens
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "VAG Connect: supplementary Tibber arming failed (%s)"
                    " — primary channel unaffected.", type(err).__name__,
                )

        # ── b12: MBB COMMAND channel (commands on a read-only primary) ──────
        arm_cmd = getattr(client, "arm_mbb_command_channel", None)
        if data.get(CONF_MBB_COMMAND_CHANNEL) and arm_cmd is not None:
            from .cariad.models import TokenSet  # noqa: PLC0415
            from .const import (  # noqa: PLC0415
                CONF_MBB_COMMAND_CLIENT_ID,
                CONF_MBB_COMMAND_TOKENS,
                CONF_MBB_VINS,
            )
            tok = data.get(CONF_MBB_COMMAND_TOKENS) or {}
            cmd_tokens = TokenSet(
                access_token=str(tok.get("access_token", "")),
                refresh_token=str(tok.get("refresh_token", "")),
                id_token=str(tok.get("id_token", "")),
                expires_at=float(tok.get("expires_at", 0.0) or 0.0),
                strategy="mbb",
            )
            vins = data.get(CONF_MBB_VINS) or []
            if isinstance(vins, str):
                vins = [
                    v.strip().upper()
                    for v in vins.replace(",", " ").split() if v.strip()
                ]
            try:
                armed = bool(await arm_cmd(
                    cmd_tokens,
                    data.get(CONF_MBB_COMMAND_CLIENT_ID, ""),
                    list(vins),
                    # v2.17.x (#666) — options-first so an S-PIN added later via
                    # Options (lands in entry.options) is captured at arm time,
                    # not just one set in the initial config data.
                    self._spin_from_entry(),
                ))
                if armed:
                    # persist the rotated MBB bearer (durable refresh survives
                    # restarts) — separate slot from the primary's tokens.
                    cmd = getattr(client, "_mbb_command", None)
                    if cmd is not None:
                        cmd.on_tokens_changed = self._persist_mbb_command_tokens
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "VAG Connect: MBB command channel arming failed (%s)"
                    " — reads unaffected.", type(err).__name__,
                )

    async def _persist_mbb_command_tokens(self, tokens: Any) -> None:
        """b12 — write the MBB command channel's rotated bearer back to
        entry.data[CONF_MBB_COMMAND_TOKENS] so the durable refresh survives a
        restart. Separate from the primary's token storage. Fail-soft."""
        from .const import CONF_MBB_COMMAND_TOKENS  # noqa: PLC0415
        try:
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    **self.entry.data,
                    CONF_MBB_COMMAND_TOKENS: {
                        "access_token": tokens.access_token,
                        "refresh_token": tokens.refresh_token,
                        "id_token": tokens.id_token,
                        "expires_at": tokens.expires_at,
                        "strategy": "mbb",
                    },
                },
            )
        except Exception:  # noqa: BLE001
            pass

    async def _persist_tibber_tokens(self, tokens: Any) -> None:
        """v2.19.0 — write the Tibber channel's rotated OAuth2 bundle back to
        entry.data[CONF_SUPPLEMENTARY_TIBBER_TOKENS] so the durable refresh
        survives a restart. Fail-soft. The bundle is never logged."""
        from .const import CONF_SUPPLEMENTARY_TIBBER_TOKENS  # noqa: PLC0415
        if not isinstance(tokens, dict):
            return
        try:
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    **self.entry.data,
                    CONF_SUPPLEMENTARY_TIBBER_TOKENS: {
                        "access_token": tokens.get("access_token", ""),
                        "refresh_token": tokens.get("refresh_token", ""),
                        "client_id": tokens.get("client_id", ""),
                        "client_secret": tokens.get("client_secret", ""),
                    },
                },
            )
        except Exception:  # noqa: BLE001
            pass

    async def _merge_supplementary(self, vin: str, primary: VehicleData) -> VehicleData:
        """v2.15.0b1 (C1) — union armed supplementary read-only channels onto
        the primary snapshot. No-op (returns ``primary`` unchanged) when no
        supplementary channel is armed, so single-channel polling is untouched.
        Fail-soft: any merge error keeps the primary — a read-only fallback must
        never sink the poll, and command routing is never touched."""
        from .cariad._channel_merge import annotate_provenance  # noqa: PLC0415

        client = self._cariad_client
        readers = getattr(client, "supplementary_readers", None)
        if readers is None:
            return annotate_provenance(self._primary_channel_name(), primary)
        suppliers = readers(vin)
        if not suppliers:
            # v2.18.0 (B2) — no supplementary channel to union, but the reading
            # still has an origin. Record it so a single-channel car can name
            # its source like everyone else; nothing else about the snapshot is
            # touched.
            return annotate_provenance(self._primary_channel_name(), primary)
        from .cariad._channel_merge import gather_and_merge  # noqa: PLC0415
        try:
            return await gather_and_merge(
                self._primary_channel_name(), primary, suppliers,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "C1 supplementary merge failed for %s — keeping primary: %s",
                mask_vin(vin), err,
            )
            # Still attribute what we did get — losing provenance exactly when
            # a channel misbehaves is when it's most worth having.
            return annotate_provenance(self._primary_channel_name(), primary)

    async def _revive_from_supplementary(
        self, vin: str, empty_primary: VehicleData
    ) -> VehicleData | None:
        """v2.16.2 (rafaelhutter v0.5.20 parity — GAP 2.1) — when the PRIMARY
        channel returned ``no_data`` (e.g. EU Data Act portal outage), try to
        keep the entry live from a SUPPLEMENTARY read-only channel (e.g. vw.de
        authproxy) instead of dropping straight to stale-cache.

        Runs the same C1 gap-fill merge as :meth:`_merge_supplementary` but over
        the *empty* primary, then returns the merged snapshot ONLY if a
        supplementary channel actually contributed live data. In that case the
        stale ``no_data`` flag is cleared so the merged result flows through the
        normal success path. Returns ``None`` when no supplementary channel is
        armed or all of them failed/were empty — the caller then keeps the
        previous good data visible exactly as before.

        This does NOT alter source-priority in the healthy case: it only fires
        when the primary carries nothing, so it is pure gap-fill with no channel
        outranked. Single-channel entries have no suppliers → returns ``None`` →
        behaviour is byte-for-byte unchanged. Fail-soft: any error → ``None``.
        """
        try:
            merged = await self._merge_supplementary(vin, empty_primary)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "GAP-2.1 supplementary revive failed for %s: %s",
                mask_vin(vin), err,
            )
            return None
        # A supplementary channel contributed IFF the merge added a
        # provenance contributor beyond the (empty) primary. The empty
        # primary is never a contributor (all fields at construction
        # default), so any non-None source_channel means live data arrived.
        if merged is empty_primary or not getattr(merged, "source_channel", None):
            return None
        # Live supplementary data arrived — this is no longer a no-data poll.
        merged.no_data = False
        _LOGGER.debug(
            "GAP-2.1 %s: primary no_data but supplementary channel(s) %s "
            "served live data — keeping entry live.",
            mask_vin(vin), merged.source_channel,
        )
        return merged

    async def _poll_loop(self) -> None:
        """Background polling loop — runs independently of HA scheduler.

        Re-reads scan_interval from entry.options on every iteration so that
        Options-Flow changes take effect without a full integration reload.

        Nightly reduction (22:00–05:00): doubles the polling interval to reduce
        API calls and avoid rate limits during low-activity hours.

        v2.8.0 — pre-flight `_maybe_run_stale_watchdog()` runs before
        each poll attempt. See that method's docstring.
        """
        while self._started:
            # Re-read interval every iteration — picks up Options-Flow changes live
            interval_s = max(
                int(
                    self.entry.options.get(CONF_SCAN_INTERVAL)
                    or self.entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ) * 60,
                _CC_MIN_INTERVAL_S,
            )
            # Nightly reduction: double interval between 22:00 and 05:00
            hour = datetime.now().hour
            if hour >= 22 or hour < 5:
                interval_s = interval_s * 2
                _LOGGER.debug("Nightly reduction active — interval doubled to %ds", interval_s)
            await asyncio.sleep(interval_s)
            if not self._started:
                break
            # v2.8.0 — pre-flight watchdog. If we are on the
            # hybrid_full strategy and every VIN has been stale +
            # failing for >2x scan_interval, silently re-authenticate
            # before attempting the next poll. No-op for every other
            # strategy and for healthy hybrid_full sessions.
            try:
                await self._maybe_run_stale_watchdog()
            except Exception as wd_err:  # noqa: BLE001
                # Watchdog must NEVER break the poll loop.
                _LOGGER.debug(
                    "VAG Connect: stale watchdog itself raised %s, "
                    "ignored.",
                    type(wd_err).__name__,
                )
            try:
                # Lazy-initialise per-VIN tracking so tests bypassing __init__ work.
                if not hasattr(self, "vehicle_success"):
                    self.vehicle_success = {}
                vins = list(self.vehicles.keys())
                results = await asyncio.gather(
                    *[self._cariad_client.get_status(vin) for vin in vins],
                    return_exceptions=True,
                )
                fresh: dict[str, Any] = {}
                any_success = False
                # Lazy-initialise v1.8.7 tracking dicts so tests that bypass
                # __init__ (and pre-1.8.7 instances reloaded after upgrade)
                # still work.
                if not hasattr(self, "vehicle_failure_count"):
                    self.vehicle_failure_count = {}
                if not hasattr(self, "vehicle_last_good_at"):
                    self.vehicle_last_good_at = {}
                for vin, result in zip(vins, results):
                    if isinstance(result, Exception):
                        _LOGGER.debug("Poll failed for %s: %s", mask_vin(vin), result)
                        old = self.vehicles.get(vin, {})
                        old["_poll_failed"] = True
                        fresh[vin] = old
                        self.vehicle_success[vin] = False
                        self.vehicle_failure_count[vin] = (
                            self.vehicle_failure_count.get(vin, 0) + 1
                        )
                        # v1.9.0 — Error Reporter capture. Per-VIN poll failure
                        # gets logged in the ring buffer with masked context so
                        # users can 1-click report it. Wrapped in try/except —
                        # error reporting must NEVER raise.
                        # v2.12.4 (#438) — but DON'T escalate a transient
                        # VW-backend 5xx (token-endpoint UpstreamUnavailableError,
                        # or a data endpoint that exhausted its 5xx retries) to
                        # the Error Reporter. It's not our bug and not actionable;
                        # this is what spammed #435-#439 during the late-May
                        # outage. The vehicle still keeps its last-known data
                        # (above) and recovers on the next poll.
                        from .cariad.exceptions import (  # noqa: PLC0415
                            AuthenticationError,
                        )
                        # v2.19.0 (#814) — de-escalate self-healing errors (5xx
                        # AND status-0 transient network/DNS errors) from the
                        # public Error Reporter; see _is_selfhealing_poll_error.
                        is_transient_upstream = _is_selfhealing_poll_error(result)
                        # v2.15.9 (#596) — a user-actionable auth-interaction
                        # (T&C / marketing-consent / 2FA / portal-interaction)
                        # re-hit on EVERY poll (the portal re-login walks into
                        # the same consent wall) used to fire record_error once
                        # per VIN per poll, flooding the Error Reporter (~20x).
                        # These already surface as a fixable Repair issue at
                        # setup (raise_issue_auth_required), and the OUTER
                        # poll-loop handler already de-escalates the same family
                        # (isinstance(err, AuthenticationError) → reauth, no
                        # record_error). The per-VIN handler was missing that
                        # guard. All five interaction classes subclass
                        # AuthenticationError, so one isinstance covers them.
                        # It is NOT a bug and NOT actionable by us — only by the
                        # user, via the Repair — so it must NOT be error-reported.
                        # Genuine failures (data-plane 403/500, parse errors,
                        # unexpected exceptions) are none of these types and
                        # still fall through to record_error below.
                        is_auth_interaction = isinstance(
                            result, AuthenticationError
                        )
                        if not is_transient_upstream and not is_auth_interaction:
                            try:
                                record_error(
                                    self.error_buffer,
                                    exception=result,
                                    brand=self.entry.data.get(CONF_BRAND, ""),
                                    vin=vin,
                                    model=self.vehicles.get(vin, {}).get("model"),
                                    model_year=self.vehicles.get(vin, {}).get("model_year"),
                                    firmware=self.vehicles.get(vin, {}).get("firmware_version"),
                                    endpoint="get_status",
                                )
                            except Exception:  # noqa: BLE001
                                pass
                    elif isinstance(result, VehicleData):
                        # v2.17.1 — on a portal no-data poll, make sure a
                        # continuous data request actually EXISTS on the portal
                        # and (re)provision it if not, so "no data comes in"
                        # self-heals instead of sitting on empty entities. Safe
                        # on transient outages too: it's rate-limited (6 h) and a
                        # no-op when a request already exists (it's just adopted,
                        # never duplicated), and it respects the auto-kickoff
                        # toggle + portal-strategy gate inside the helper.
                        if getattr(result, "no_data", False):
                            await self._maybe_runtime_data_act_kickoff()
                        # v2.15.0a10 (#481-residue) — a no-data poll (e.g. EU
                        # Data Act portal timeout/outage) returns a bare
                        # VehicleData carrying only the VIN. If we already hold
                        # good data for this car, keep it VISIBLE ("old but
                        # visible") and count this as a failed poll so the
                        # stale-cache watchdog engages — instead of overwriting
                        # SoC/odometer with blanks and resetting the failure
                        # counter + last-good timestamp. A VIN we've never seen
                        # falls through so a brand-new car still appears.
                        if getattr(result, "no_data", False) and self.vehicles.get(vin):
                            # v2.16.2 (rafaelhutter v0.5.20 parity — GAP 2.1) —
                            # RESILIENCE: an EU-DA-primary outage must NOT hide a
                            # healthy vw.de (or other) SUPPLEMENTARY channel. His
                            # website_portal keeps serving when EU-DA fails
                            # (coordinator.py:163-179); we mirror that with our
                            # OWN code. Before falling back to "old but visible"
                            # stale-cache, attempt the supplementary merge onto
                            # this empty primary. If a supplementary channel is
                            # armed AND actually returned live data, that merged
                            # snapshot flows through the normal success path
                            # below (fresh + last-good + counter reset). This
                            # does NOT change source-priority in the healthy
                            # case: the primary is empty here, so nothing higher
                            # trust is overridden — it is pure gap-fill. Single-
                            # channel entries have no suppliers → merge is a
                            # no-op → the stale-cache path is byte-for-byte
                            # unchanged.
                            revived = await self._revive_from_supplementary(
                                vin, result
                            )
                            if revived is not None:
                                result = revived
                            else:
                                old = self.vehicles.get(vin, {})
                                old["_poll_failed"] = True
                                fresh[vin] = old
                                self.vehicle_success[vin] = False
                                self.vehicle_failure_count[vin] = (
                                    self.vehicle_failure_count.get(vin, 0) + 1
                                )
                                continue
                        else:
                            # v2.15.0b1 (C1) — multi-channel merge: union any
                            # armed supplementary read-only channel (e.g. vw.de
                            # authproxy) onto the primary snapshot before
                            # storing. No-op for single-channel entries →
                            # returns result unchanged.
                            result = await self._merge_supplementary(vin, result)
                        # v1.10.1 (#58 Phase 2) — wrap to_dict + _enrich
                        # in their own try/except. A single VehicleData
                        # field with an unexpected type used to crash
                        # the whole vehicle's poll mid-update; now the
                        # vehicle stays available with its previous data
                        # and the failure goes to the Error Reporter.
                        try:
                            data = result.to_dict()
                            data["_client"] = self._cariad_client
                            data["_poll_failed"] = False
                            enriched = await self._enrich(data)
                        except Exception as parse_err:  # noqa: BLE001
                            _LOGGER.warning(
                                "VAG Connect: post-parse failure for %s — "
                                "keeping previous data: %s",
                                mask_vin(vin), parse_err,
                            )
                            old = self.vehicles.get(vin, {})
                            old["_poll_failed"] = True
                            fresh[vin] = old
                            self.vehicle_success[vin] = False
                            self.vehicle_failure_count[vin] = (
                                self.vehicle_failure_count.get(vin, 0) + 1
                            )
                            try:
                                record_error(
                                    self.error_buffer,
                                    exception=parse_err,
                                    brand=self.entry.data.get(CONF_BRAND, ""),
                                    vin=vin,
                                    model=self.vehicles.get(vin, {}).get("model"),
                                    model_year=self.vehicles.get(vin, {}).get("model_year"),
                                    firmware=self.vehicles.get(vin, {}).get("firmware_version"),
                                    endpoint="parse",
                                )
                            except Exception:  # noqa: BLE001
                                pass
                            continue
                        # b13 — Portal-safety: reconcile the fresh poll over
                        # the last-known-good snapshot — carry cumulative
                        # telemetry (SoC/odometer/range/…) forward when this
                        # poll omitted it, and reject a backwards odometer —
                        # so a partial portal payload never blanks a field and
                        # a glitched "km" reading never jumps down.
                        from .cariad.vehicle_cache import reconcile  # noqa: PLC0415
                        enriched, _discrepancies = reconcile(
                            self.vehicles.get(vin), enriched
                        )
                        if _discrepancies:
                            _LOGGER.debug(
                                "VAG Connect portal-safety %s: %s",
                                mask_vin(vin), "; ".join(_discrepancies),
                            )
                        fresh[vin] = enriched
                        any_success = True
                        self.vehicle_success[vin] = True
                        self.vehicle_failure_count[vin] = 0
                        self.vehicle_last_good_at[vin] = datetime.now(tz=timezone.utc)
                        # v2.5.2 — Silent scout-channel expansion. Once per
                        # _PROBE_INTERVAL_S per VIN (default 1h), issue
                        # GETs against documented public open-source
                        # endpoints we don't currently call. Responses
                        # land in last_raw_responses and the scout walk
                        # below picks them up. Best-effort, fail-safe,
                        # never blocks production polling. Brand client
                        # gates on token-budget + circuit-breaker.
                        try:
                            if hasattr(self._cariad_client, "run_v3_probe_pass"):
                                await self._cariad_client.run_v3_probe_pass(vin)
                        except Exception:  # noqa: BLE001
                            pass
                        # v1.9.0 — Vehicle Data Scout. Inspect raw responses
                        # the brand client opted to stash; never blocks the
                        # poll if the detector itself raises.
                        try:
                            self._scan_for_unexpected_keys(vin, fresh.get(vin))
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        fresh[vin] = self.vehicles.get(vin, {})
                        self.vehicle_success[vin] = False
                        self.vehicle_failure_count[vin] = (
                            self.vehicle_failure_count.get(vin, 0) + 1
                        )
                with self._vehicles_lock:
                    self.vehicles.update(fresh)
                # b13 — Portal-safety: persist the merged snapshot (debounced)
                # so the recorded values survive a HA restart. Best-effort.
                try:
                    self._save_vehicle_cache()
                except Exception:  # noqa: BLE001
                    pass
                # v1.9.0 — Refresh the two reporter repair issues. Cheap to
                # call: ``ensure_*_issue`` deletes when empty and updates
                # in-place when the IDs already exist.
                self._refresh_reporter_issues()
                # v2.12.2 — raise/clear the "EU Data Act portal: no data"
                # repair issue based on the portal connector's last outcome.
                try:
                    self._update_data_act_no_data_repair()
                except Exception:  # noqa: BLE001
                    pass  # a repair-issue update must never break the poll
                # v1.14.0 (#24) — Trip Stats refresh, best-effort + cached
                # 1h. Brand-restricted to audi/volkswagen inside helper.
                # Runs after vehicle update so newest VINs are present
                # in self.vehicles when the parser merges back.
                try:
                    await asyncio.gather(
                        *[
                            self.refresh_trip_statistics(vin)
                            for vin in self.vehicles
                        ],
                        return_exceptions=True,
                    )
                except Exception:  # noqa: BLE001
                    pass  # never let trip-stats break the poll
                # v1.15.0 (#35) — Skoda Charging History, same best-effort
                # 1h-cache pattern. Brand-restriction inside helper means
                # this is no-op for non-Skoda accounts.
                try:
                    await asyncio.gather(
                        *[
                            self.refresh_charging_history(vin)
                            for vin in self.vehicles
                        ],
                        return_exceptions=True,
                    )
                except Exception:  # noqa: BLE001
                    pass
                # v1.16.0 (#25, #31) — Skoda Charging Profiles 1h-cache.
                # Same brand-restricted best-effort pattern.
                try:
                    await asyncio.gather(
                        *[
                            self.refresh_charging_profiles(vin)
                            for vin in self.vehicles
                        ],
                        return_exceptions=True,
                    )
                except Exception:  # noqa: BLE001
                    pass
                # v1.17.1 (Bruno seq 10/11) — SEAT/CUPRA Battery Care
                # 1h-cache. Same defensive pattern.
                try:
                    await asyncio.gather(
                        *[
                            self.refresh_battery_care(vin)
                            for vin in self.vehicles
                        ],
                        return_exceptions=True,
                    )
                except Exception:  # noqa: BLE001
                    pass
                await self._async_push_update(fresh, success=any_success)

                # v2.4.1 (#281+#282) — OLA defense-in-depth Layer 4:
                # check if the SEAT/CUPRA client has flagged itself for
                # a Repair issue (persistent 403s after all fallbacks).
                # Cheap attribute check — no-op for non-OLA brands.
                try:
                    ola_flag = getattr(self._cariad_client, "ola_headers_repair_needed", False)
                    consecutive_403 = getattr(self._cariad_client, "_ola_consecutive_403", 0)
                    if ola_flag and consecutive_403 > 0:
                        from .repairs import raise_issue_ola_headers_outdated  # noqa: PLC0415
                        raise_issue_ola_headers_outdated(
                            self.hass, self.entry.entry_id,
                            self.entry.data.get(CONF_BRAND, "unknown"),
                            consecutive_403,
                        )
                    elif not ola_flag and consecutive_403 == 0:
                        # Successful response cleared the flag — clear the issue too.
                        from .repairs import clear_ola_headers_issue  # noqa: PLC0415
                        clear_ola_headers_issue(self.hass, self.entry.entry_id)
                except Exception:  # noqa: BLE001
                    pass

                # v2.15.4 (#503) — VW NA read-path entitlement surfacing.
                # login + garage succeed but per-vehicle reads 403; the client
                # classifies the 403 (markers-only) and the privileges outcome
                # into vw_na_data_forbidden + a value-free reason. Raise/clear a
                # Repair issue so the user sees an honest entitlement state
                # instead of a silent-empty vehicle. Cheap attr check — no-op
                # for non-VW-NA brands. Mirrors the OLA block above.
                try:
                    na_forbidden = getattr(
                        self._cariad_client, "vw_na_data_forbidden", False
                    )
                    na_reason = getattr(
                        self._cariad_client, "vw_na_data_forbidden_reason", ""
                    )
                    if na_forbidden:
                        from .repairs import raise_issue_vw_na_data_forbidden  # noqa: PLC0415
                        raise_issue_vw_na_data_forbidden(
                            self.hass, self.entry.entry_id, na_reason,
                        )
                    else:
                        from .repairs import clear_vw_na_data_forbidden_issue  # noqa: PLC0415
                        clear_vw_na_data_forbidden_issue(
                            self.hass, self.entry.entry_id,
                        )
                except Exception:  # noqa: BLE001
                    pass
            except Exception as err:  # noqa: BLE001
                # Auth failure that survived the client's refresh-then-relogin
                # fallback means the credentials are stale. Trigger HA reauth.
                from .cariad.exceptions import (  # noqa: PLC0415
                    AuthenticationError,
                )
                if isinstance(err, AuthenticationError):
                    self._trigger_reauth(str(err) or type(err).__name__)
                    await self._async_push_update({}, success=False)
                    return
                # v2.12.4 (#438) — a transient VW-backend 5xx that escaped the
                # per-VIN handler (UpstreamUnavailableError, or a 5xx APIError)
                # is logged but NOT escalated to the Error Reporter: it's a
                # server-side outage symptom, not our bug, and escalating it
                # spammed #435-#439. Entities stay available via the
                # failure-tolerance window below.
                # v2.19.0 (#814) — de-escalate self-healing errors (5xx AND
                # status-0 transient network/DNS errors) from the public Error
                # Reporter; see _is_selfhealing_poll_error.
                is_transient_upstream = _is_selfhealing_poll_error(err)
                if is_transient_upstream:
                    _LOGGER.warning(
                        "VAG Connect: VW backend temporarily unavailable — %s", err
                    )
                else:
                    _LOGGER.error("VAG Connect poll error: %s", err)
                    # v1.9.0 — Error Reporter: outer poll-loop crash gets a
                    # buffer entry too. Critical because these are the kind of
                    # errors users hit and never know about (silent except).
                    try:
                        record_error(
                            self.error_buffer,
                            exception=err,
                            brand=self.entry.data.get(CONF_BRAND, ""),
                            endpoint="poll_loop",
                        )
                        self._refresh_reporter_issues()
                    except Exception:  # noqa: BLE001
                        pass
                if not hasattr(self, "vehicle_success"):
                    self.vehicle_success = {}
                if not hasattr(self, "vehicle_failure_count"):
                    self.vehicle_failure_count = {}
                # Mark all known VINs as failed — avoids stale-as-fresh.
                # ``is_vehicle_available`` still tolerates this for up to
                # ``_FAILURE_TOLERANCE`` consecutive failures and within
                # ``_STALE_CACHE_WINDOW`` so single-poll backend hiccups
                # don't ripple through every entity (we_connect_id #215).
                for vin in list(self.vehicles.keys()):
                    self.vehicle_success[vin] = False
                    self.vehicle_failure_count[vin] = (
                        self.vehicle_failure_count.get(vin, 0) + 1
                    )
                await self._async_push_update({}, success=False)

    async def async_shutdown(self) -> None:
        """Stop polling loop and release resources."""
        self._started = False
        # v2.0.0 (Big-Bang) — stop push managers before dropping client.
        await self.async_stop_push_managers()
        # v2.15.0b1 (C1) — close the dedicated supplementary vw.de session so
        # we don't leak an aiohttp session on unload/reload.
        close_supp = getattr(self._cariad_client, "close_supplementary", None)
        if close_supp is not None:
            try:
                await close_supp()
            except Exception:  # noqa: BLE001
                pass
        self._cariad_client = None
        _LOGGER.debug("VAG Connect: shutdown complete")

    # ── v2.0.0 (Big-Bang) — Push-manager lifecycle ────────────────────────
    # Wired in __init__ to None; instantiated lazily after the first
    # successful poll once we know the user_id + VIN list. Three brand-
    # specific classes share the same ``PushManager`` interface so the
    # lifecycle hooks below stay brand-agnostic. Each manager carries the
    # ``state`` attribute consumed by system_health.py.

    async def async_start_push_managers(self) -> None:
        """Spawn the brand-appropriate push manager(s) if opted in.

        Called from the platform's ``async_setup_entry`` after the first
        coordinator refresh. Idempotent — subsequent calls return
        immediately if a manager is already running.

        Opt-in is per-brand via OptionsFlow toggles:
        - Skoda → ``CONF_ENABLE_PUSH_MQTT``
        - CUPRA/SEAT → ``CONF_ENABLE_PUSH_FCM``
        - Audi/VW EU → ``CONF_ENABLE_PUSH_AUDI_VW``

        All three push managers now have their real ``_connect_and_listen``
        wired (opt-in BETA, default-off toggles). Škoda MQTT + CUPRA/SEAT
        FCM are grounded against upstream (myskoda / pycupra); Audi/VW EU
        ships GATED (subscription host/path/body unverified off-device) with
        a runtime warning. Live activation is confirmed per-brand by a tester
        with a real car; the circuit-breaker keeps a wrong body inert.
        """
        # v2.18.0 — data THEN options, mirroring the merge the update-listener
        # itself performs. The listener folds options into entry.data and blanks
        # entry.options (__init__.py), so reading options alone meant all three
        # toggles were permanently False and no push manager could ever start:
        # the feature was unreachable from the UI for as long as it has shipped.
        options = {
            **dict(getattr(self.entry, "data", {}) or {}),
            **dict(getattr(self.entry, "options", {}) or {}),
        }
        brand = self.entry.data.get(CONF_BRAND, "")
        client = self._cariad_client
        if client is None:
            return
        # User-id is captured by the brand client after the first auth
        # cycle; bail quietly if not yet available (next refresh re-tries).
        user_id = getattr(client, "user_id", None) or getattr(client, "_user_id", None)
        vins = list(getattr(self, "vehicles", {}).keys())
        if not user_id or not vins:
            return

        async def _on_push_event(event: Any) -> None:
            """Coordinator-side push callback.

            v2.8.0 Action #4: fires the event onto the HA bus as
            ``vag_connect_push_event`` so users can wire automations
            keyed on ``event_type`` + ``vin`` filters. Then requests
            a coordinator refresh so live entities update without
            waiting for the next poll cycle.
            """
            _LOGGER.debug(
                "VAG push: event vin=***%s type=%s; firing on bus + "
                "requesting refresh",
                (event.vin or "??????")[-6:],
                event.event_type,
            )
            # v2.8.0 Action #4: HA bus emission. Wrapped so a bus
            # failure cannot break the refresh path.
            try:
                self.hass.bus.async_fire(
                    "vag_connect_push_event",
                    {
                        "vin": event.vin,
                        "event_type": event.event_type,
                        "topic": event.topic,
                        "timestamp": event.timestamp,
                        "brand": brand,
                        "raw_payload": event.raw_payload,
                    },
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("VAG push: bus emission failed")
            try:
                await self.async_request_refresh()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("VAG push: refresh after event failed")

        token_provider = getattr(client, "async_get_access_token", None)
        if token_provider is None:
            async def token_provider() -> str:  # type: ignore[no-redef]
                tokens = getattr(client, "_tokens", None)
                return getattr(tokens, "access_token", "") or ""

        if brand == "skoda" and options.get(CONF_ENABLE_PUSH_MQTT) and self._skoda_push is None:
            from .cariad.push.skoda_mqtt import SkodaPushManager  # noqa: PLC0415
            self._skoda_push = SkodaPushManager(
                _on_push_event,
                user_id=user_id,
                access_token_provider=token_provider,
                vins=vins,
            )
            await self._skoda_push.start()

        if brand in ("cupra", "seat") and options.get(CONF_ENABLE_PUSH_FCM) and self._cupra_seat_push is None:
            from .cariad.push.cupra_seat_fcm import CupraSeatPushManager  # noqa: PLC0415
            self._cupra_seat_push = CupraSeatPushManager(
                _on_push_event,
                user_id=user_id,
                access_token_provider=token_provider,
                vins=vins,
                brand=brand,
            )
            await self._cupra_seat_push.start()

        if brand in ("audi", "volkswagen") and options.get(CONF_ENABLE_PUSH_AUDI_VW) and self._audi_vw_push is None:
            from .cariad.push.audi_vw_fcm import AudiVWPushManager  # noqa: PLC0415
            self._audi_vw_push = AudiVWPushManager(
                _on_push_event,
                user_id=user_id,
                access_token_provider=token_provider,
                vins=vins,
                brand=brand,
            )
            await self._audi_vw_push.start()

    async def async_stop_push_managers(self) -> None:
        """Stop any running push managers. Idempotent.

        Called from ``async_shutdown`` so unload-or-reload is clean.
        """
        for attr in ("_skoda_push", "_cupra_seat_push", "_audi_vw_push"):
            mgr = getattr(self, attr, None)
            if mgr is None:
                continue
            try:
                await mgr.stop()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("VAG push: stop %s raised — ignoring", attr)
            setattr(self, attr, None)

    # ── Vehicle Data Scout + Error Reporter (v1.9.0) ───────────────────────

    def _scan_for_unexpected_keys(
        self, vin: str, vehicle: dict | None = None
    ) -> None:
        """Run ``detect_unexpected`` over the brand client's stashed responses.

        Brand clients opt in by populating ``last_raw_responses`` in
        ``get_status`` with logical endpoint names matching the
        ``EXPECTED_KEYS`` table. Findings are de-duped per VIN — the same
        drift seen on every poll only takes one slot in the buffer and one
        line in the report.

        Caller wraps in try/except so a detector bug never breaks polling.
        """
        client = self._cariad_client
        if client is None or not hasattr(client, "last_raw_responses"):
            return
        brand = self.entry.data.get(CONF_BRAND, "")
        if not brand:
            return
        if not hasattr(self, "unexpected_findings"):
            self.unexpected_findings = {}
        per_vin = self.unexpected_findings.setdefault(vin, {})
        for endpoint, payload in (client.last_raw_responses or {}).items():
            for finding in detect_unexpected(brand, endpoint, payload):
                # De-dupe by path — keep the first observation timestamp.
                per_vin.setdefault(finding.path, finding)
        # b6 — feed the EU Data Act portal fields the curated parser did NOT map
        # (the A6 raw-discovery set) into the SAME Scout report, so the unmapped
        # long tail is visible/reportable and we learn what to map next. Endpoint
        # isn't in EXPECTED_KEYS so detect_unexpected skips it — surface directly.
        raw = (vehicle or {}).get("raw_unmapped_fields")
        if isinstance(raw, dict) and raw:
            from datetime import datetime, timezone  # noqa: PLC0415

            from .cariad._unexpected_keys import mask_value  # noqa: PLC0415
            now = datetime.now(tz=timezone.utc).isoformat()
            for name, value in raw.items():
                path = f"eu_data_act.{name}"
                per_vin.setdefault(path, UnexpectedField(
                    path=path,
                    sample_masked=mask_value(value),
                    endpoint="eu_data_act",
                    first_seen_at=now,
                ))

    def _refresh_reporter_issues(self) -> None:
        """Recreate / delete the two HA repair issues from current buffers.

        Called after every poll cycle. The pipeline functions handle the
        empty case (delete the issue) and the populated case (create or
        refresh in-place — registry de-dupes by issue_id).

        Wrapped here so a registry hiccup can't take down the poll loop.
        """
        brand = self.entry.data.get(CONF_BRAND, "")
        entry_id = getattr(self.entry, "entry_id", "") or ""

        # Vehicle model name (e.g. "ID.4") makes the GitHub issue recognizable
        # at a glance and doubles as the maintainer's private per-model stat.
        # NOT PII (generic), VIN stays masked. Entries are typically one car;
        # pick the first vehicle that carries a model name.
        model: str | None = None
        for vdata in getattr(self, "vehicles", {}).values():
            if isinstance(vdata, dict):
                m = vdata.get("model")
                if m:
                    model = m
                    break

        # Flatten per-VIN findings into a single chronological list.
        all_findings = []
        for per_vin in getattr(self, "unexpected_findings", {}).values():
            all_findings.extend(per_vin.values())

        try:
            ensure_unexpected_keys_issue(
                self.hass,
                entry_id=entry_id,
                findings=all_findings,
                brand=brand,
                model=model,
            )
        except Exception:  # noqa: BLE001
            pass

        try:
            buffer = getattr(self, "error_buffer", None)
            records = list(buffer.records) if buffer is not None else []
            ensure_error_reporter_issue(
                self.hass,
                entry_id=entry_id,
                records=records,
                brand=brand,
                model=model,
            )
        except Exception:  # noqa: BLE001
            pass

    def reporter_findings_count(self) -> int:
        """Return the total number of distinct unexpected-key findings.

        Surfaced by the ``api_observer_findings`` sensor as its native
        value. Counting distinct paths (not raw observations) avoids
        misleadingly large numbers when the same drift hits every poll.
        """
        total = 0
        for per_vin in getattr(self, "unexpected_findings", {}).values():
            total += len(per_vin)
        return total

    def reporter_error_count(self) -> int:
        """Return the number of records in the error reporter ring buffer."""
        buffer = getattr(self, "error_buffer", None)
        return len(buffer) if buffer is not None else 0

    @property
    def is_active(self) -> bool:
        """Return True if the CARIAD polling loop is active."""
        return self._started

    def _push_managers(self) -> dict[str, Any]:
        """Return the live push managers, keyed by channel name."""
        return {
            name: mgr
            for name, mgr in (
                ("skoda_mqtt", getattr(self, "_skoda_push", None)),
                ("cupra_seat_fcm", getattr(self, "_cupra_seat_push", None)),
                ("audi_vw_fcm", getattr(self, "_audi_vw_push", None)),
            )
            if mgr is not None
        }

    @property
    def push_states(self) -> dict[str, str]:
        """Per-channel push lifecycle state, for diagnostics.

        v2.18.0 (#747) — the managers have carried a diagnostics-shaped
        ``state`` since v2.2.0, but nothing ever exported it.
        """
        return {name: str(mgr.state) for name, mgr in self._push_managers().items()}

    @property
    def cloud_push_active(self) -> bool:
        """Return True when at least one push channel is actually connected.

        v2.18.0 (#747) — diagnostics used to report ``is_active`` under this
        name, which is the *polling loop* flag: it read true on every setup,
        including entries with all three push toggles off.
        """
        from .cariad.push.base import PushManagerState  # noqa: PLC0415

        return any(
            mgr.state is PushManagerState.CONNECTED
            for mgr in self._push_managers().values()
        )

    def is_vehicle_available(self, vin: str) -> bool:
        """Return True if *vin* should be reported available to entities.

        Two-stage tolerance (v1.8.7):

        1. Up to ``_FAILURE_TOLERANCE`` consecutive failed polls do not
           flip the vehicle to unavailable. Single-poll backend hiccups
           are common on the CARIAD BFF and would otherwise break
           automations watching binary sensors (we_connect_id #215).
        2. Even past the tolerance threshold, if we still have a recent
           successful poll within ``_STALE_CACHE_WINDOW``, keep the
           vehicle visible. The cached state is shown with its
           ``last_updated_at`` so the user can tell it is stale; this
           matches the UX preference documented in myskoda #731.

        Defaults to True for unknown VINs (covers initial setup).
        """
        failures: dict[str, int] = getattr(self, "vehicle_failure_count", {}) or {}
        count = failures.get(vin, 0)
        if count < _FAILURE_TOLERANCE:
            return True
        last_good_map: dict[str, datetime] = (
            getattr(self, "vehicle_last_good_at", {}) or {}
        )
        last_good = last_good_map.get(vin)
        if last_good is not None:
            age = datetime.now(tz=timezone.utc) - last_good
            if age < _STALE_CACHE_WINDOW:
                return True
        # Truly unavailable — past tolerance and stale-cache window.
        return False

    # ── Capabilities & feature-state plumbing (Session 2A foundation) ──────

    def get_feature_state(self, vin: str, command: str) -> FeatureState:
        """Return (or lazily create) the FeatureState for *vin*+*command*.

        2A only sets the dict structure up; later sessions will read from it
        in entity platforms to gate creation/availability.
        """
        states = getattr(self, "feature_states", None)
        if states is None:
            self.feature_states = {}
            states = self.feature_states
        per_vin = states.setdefault(vin, {})
        if command not in per_vin:
            per_vin[command] = FeatureState()
        return per_vin[command]

    def record_command_failure(
        self, vin: str, command: str, reason: CommandFailureReason
    ) -> None:
        """Update the FeatureState after a command failed.

        Conservative — only flips ``supported_by_vehicle`` to False on an
        explicit ``MISSING_CAPABILITY`` response. Other reasons leave the
        flag untouched so a transient backend hiccup never permanently
        hides an entity.

        v2.5.10 (#325 roberttco) — when a definitive-no flag is flipped,
        schedule ``retry_after`` 24h from now so the entity can re-
        evaluate itself without requiring a HA restart. Auto-recovery
        for backend changes (subscription renewed, model-year firmware
        update, OTA-pushed feature unlock).
        """
        state = self.get_feature_state(vin, command)
        state.last_error = reason
        state.last_error_at = datetime.now(tz=timezone.utc)
        retry_at = state.last_error_at + timedelta(hours=24)
        if reason is CommandFailureReason.MISSING_CAPABILITY:
            state.supported_by_vehicle = False
            state.retry_after = retry_at
        elif reason in (
            CommandFailureReason.SUBSCRIPTION_EXPIRED,
            CommandFailureReason.NOT_ENTITLED,
            # b13 — attestation lock is a backend-access denial, not a vehicle
            # capability gap: keep the entity (reads continue) and re-probe in
            # 24h in case VW rolls it back, like an entitlement wall.
            CommandFailureReason.ATTESTATION_LOCKED,
        ):
            state.entitled_by_account = False
            state.retry_after = retry_at

    def record_command_success(self, vin: str, command: str) -> None:
        """Mark a command as known-good for *vin*."""
        state = self.get_feature_state(vin, command)
        state.supported_by_vehicle = True
        state.entitled_by_account = True
        state.available_now = True
        state.last_error = None
        state.last_error_at = None
        state.retry_after = None  # v2.5.10 — clear retry schedule on success

    def is_capabilities_cache_fresh(self, vin: str) -> bool:
        """Return True if cached capabilities for *vin* are within TTL."""
        fetched_at: datetime | None = getattr(
            self, "_capabilities_fetched_at", {}
        ).get(vin)
        if fetched_at is None:
            return False
        return bool(datetime.now(tz=timezone.utc) - fetched_at < _CAPABILITIES_TTL)

    def is_command_known_unsupported(self, vin: str, command: str) -> bool:
        """Return True only if a previous attempt established the command
        is *definitely* not available for *vin*.

        v1.9.1 (Capability-Filter Phase 2, #56) — entity platforms read
        this in their ``available`` property to gracefully hide commands
        that the backend has already rejected with a definitive reason
        (missing capability, expired subscription, not entitled).

        v2.5.10 (#325 roberttco) — respect the ``retry_after`` field.
        After 24h the entity becomes available again for one re-attempt
        cycle. If the backend still says no, the next failure resets the
        retry-after timestamp. If it now says yes (subscription renewed,
        feature unlocked via OTA), the entity stays available. This
        replaces the pre-v2.5.10 "permanent disable until HA restart"
        behaviour that frustrated users with intermittent backend
        permission grants.
        """
        states = getattr(self, "feature_states", None)
        if not states:
            return False
        state = states.get(vin, {}).get(command)
        if state is None:
            return False
        # v2.5.10 — auto-recovery window. After retry_after passes,
        # surface the entity as available again for one re-attempt.
        if state.retry_after is not None:
            try:
                if datetime.now(tz=timezone.utc) >= state.retry_after:
                    return False  # let the entity re-attempt
            except Exception:  # noqa: BLE001 — defensive
                pass
        if state.supported_by_vehicle is False:
            return True
        if state.entitled_by_account is False:
            return True
        return False

    def get_command_profile(self, vin: str) -> CommandProfile:
        """Return the cached command profile for *vin*, or ``UNKNOWN``.

        Brand clients consult this before dispatching a command so they
        can pick the right URL prefix without re-discovering it on every
        call. ``UNKNOWN`` means "use the brand client's current default"
        and lets the client auto-learn on the first 404.
        """
        profiles: dict[str, CommandProfile] = (
            getattr(self, "vehicle_command_profile", {}) or {}
        )
        return profiles.get(vin, CommandProfile.UNKNOWN)

    def set_command_profile(self, vin: str, profile: CommandProfile) -> None:
        """Cache the detected command profile for *vin*.

        Called by brand clients after a successful endpoint probe (e.g. a
        v1 404 followed by a v2 200 on Audi premium models). Persisted
        only in memory; cheap to re-learn on restart.
        """
        if not hasattr(self, "vehicle_command_profile"):
            self.vehicle_command_profile = {}
        previous = self.vehicle_command_profile.get(vin, CommandProfile.UNKNOWN)
        self.vehicle_command_profile[vin] = profile
        if previous is not profile:
            _LOGGER.info(
                "VAG Connect: command profile for %s = %s (was %s)",
                mask_vin(vin),
                profile.value,
                previous.value,
            )

    def vehicle_supports_capability(
        self, vin: str, capability_id: str
    ) -> bool | None:
        """Return ``True`` / ``False`` / ``None`` for a capability lookup.

        - ``True``  — capability is present in the cached document and has
          no documented limitations (empty ``status`` array on OLA, or
          ``active=True`` AND ``user-enabled != False`` on Skoda mysmob).
        - ``False`` — capability is present but the backend lists explicit
          limitations, OR the cache is populated and the capability is not
          listed at all (callers can treat both as "do not show entity").
        - ``None``  — no cached document for this VIN yet (e.g. brand has
          no capabilities endpoint, or the prefetch failed). Callers must
          NOT hide entities in this case — the data simply isn't there.

        Conservative on purpose: returns ``None`` for unknown rather than
        guessing. Only an explicit cache hit warrants gating decisions.

        v1.13.0 (#56 Phase 3 prerequisite) — extended schema-tolerance:
        Skoda mysmob uses ``{active, editable, user-enabled, status,
        license-issue, parameters}`` instead of CARIAD-BFF's bare
        ``{id, status}``. This helper now treats:
        - ``status``: empty list / missing → True (CARIAD pattern)
        - ``active``: explicit False → False (Skoda pattern)
        - ``user-enabled``: explicit False → False (Skoda pattern)
        - ``license-issue``: present + truthy → False (Skoda paid feature)
        Mixed cases (e.g. CARIAD vehicle whose response has ``active``
        too) require ALL truthy signals to return True.

        v1.15.0 — additionally tolerates the new transient-state values
        documented in ``skodaconnect/myskoda/models/capability.py`` post
        PR #533: ``INSUFFICIENT_BATTERY_LEVEL``, ``LOCATION_DATA_DISABLED``,
        ``VEHICLE_DISABLED`` are status entries that mean "currently
        can't" (not "permanently can't"). They still count as "gated
        right now" — but logged so a future surface-feature can show
        the user "your battery is too low to start climate" instead of
        the entity just disappearing. Also tolerates the new top-level
        ``errors[]`` block on capabilities responses (introduced in
        myskoda PR #543) — explicit error means False without crashing.
        """
        caps = getattr(self, "vehicle_capabilities", {}).get(vin)
        if not isinstance(caps, dict):
            return None
        # v1.15.0 — top-level ``errors`` array on capabilities response
        # (myskoda PR #543). When the whole capabilities document failed
        # to load (MISSING_RENDER / UNAVAILABLE_SERVICE_PLATFORM_CAPABILITIES
        # / UNAVAILABLE_SOFTWARE_VERSION), bail to ``None`` so we don't
        # falsely gate every entity.
        if isinstance(caps.get("errors"), list) and caps["errors"]:
            return None
        items = caps.get("capabilities")
        if not isinstance(items, list):
            return None
        for entry in items:
            if not isinstance(entry, dict):
                continue
            if entry.get("id") != capability_id:
                continue
            # Skoda extra signals — explicit False on active/user-enabled
            # OR a non-empty license-issue means the capability is gated.
            if entry.get("active") is False:
                return False
            if entry.get("user-enabled") is False:
                return False
            if entry.get("license-issue"):
                return False
            status = entry.get("status")
            # Empty list / missing → fully usable. Anything in status[] is
            # a limitation. v1.15.0 known status enum values:
            # ``DEACTIVATED``, ``LICENSE_REQUIRED``, ``UNSUPPORTED``,
            # ``INSUFFICIENT_BATTERY_LEVEL``, ``LOCATION_DATA_DISABLED``,
            # ``VEHICLE_DISABLED``, ``NOT_ACTIVATED``. All of them mean
            # "right now no" — we treat them uniformly as gated. Future
            # work could distinguish transient (battery, location) vs
            # permanent (license) for richer UX hints.
            return not bool(status)
        # Cache is populated but capability isn't listed — explicit absence.
        return False

    def capability_gating_reason(
        self, vin: str, capability_id: str
    ) -> tuple[str, str] | None:
        """Return ``(category, human_reason)`` for WHY a capability is gated.

        Companion to ``vehicle_supports_capability`` — it does NOT change the
        gating decision, only explains it. Reads the same cached capabilities
        document and decodes the capability's ``status`` array (or, for Skoda,
        its ``license-issue`` / ``active`` / ``user-enabled`` flags) into a
        legible reason via ``_capability_status``. Returns ``None`` when there
        is nothing to explain (no cache, capability usable, or absent with no
        status detail). Never raises — pure read of cached data.
        """
        from .cariad._capability_status import (  # noqa: PLC0415
            capability_status_reason,
        )

        caps = getattr(self, "vehicle_capabilities", {}).get(vin)
        if not isinstance(caps, dict):
            return None
        items = caps.get("capabilities")
        if not isinstance(items, list):
            return None
        for entry in items:
            if not isinstance(entry, dict) or entry.get("id") != capability_id:
                continue
            reason = capability_status_reason(entry.get("status"))
            if reason is not None:
                return reason
            # Skoda mysmob expresses gating via flags, not a status array —
            # synthesise the equivalent status tokens and reuse the decoder.
            synth: list[str] = []
            if entry.get("license-issue"):
                synth.append("licenseRequired")
            if entry.get("active") is False:
                synth.append("deactivated")
            if entry.get("user-enabled") is False:
                synth.append("disabledByUser")
            return capability_status_reason(synth)
        return None

    def command_gating_reason(
        self, vin: str, command_id: str
    ) -> tuple[str, str] | None:
        """``capability_gating_reason`` keyed by integration command-id.

        Translates the command-id to the brand's capability-id (same lookup as
        ``command_capability_supported``) and returns the decoded gating reason,
        so a failed command can tell the user *why* instead of a bare 404.
        """
        from .cariad._capabilities import cap_id_for  # noqa: PLC0415

        try:
            brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        except Exception:  # noqa: BLE001
            return None
        cap_id = cap_id_for(brand, command_id) if brand else None
        if cap_id is None:
            return None
        return self.capability_gating_reason(vin, cap_id)

    def command_capability_supported(
        self, vin: str, command_id: str
    ) -> bool | None:
        """v1.13.0 (#56 Phase 3) — translate command-id → capability-id
        per brand and return capability support status.

        Used by platform ``async_setup_entry`` functions to filter
        command-bound entities BEFORE creation:

            if coordinator.command_capability_supported(vin, "command_flash") is False:
                continue  # don't register this entity
            entities.append(VagFlashButton(coordinator, vin))

        Tri-state semantics intentional:
        - ``True``  → backend confirms capability supported
        - ``False`` → backend confirms capability missing/limited (HIDE)
        - ``None``  → cache empty / brand without capability map / unknown
                      → DON'T hide (Phase 2 catches it post-failure)

        Pattern matches the existing ``vehicle_supports_capability`` API
        but adds the brand → cap-id lookup so platforms don't need to
        know brand-specific capability vocabulary themselves.

        v2.2.0 PR #5 — additionally consults the MY/Platform quirk
        table (``cariad/_my_quirks.py``) for known-broken firmware
        combinations the backend STILL advertises as supported (e.g.
        CUPRA Born MY24-MY25 unlock — pycupra #79). If quirks
        suppress the command, returns False BEFORE the backend-cap
        check so platforms hide the entity even on accounts where
        the backend lies about capability.
        """
        from .cariad._capabilities import cap_id_for  # noqa: PLC0415
        from .cariad._my_quirks import is_command_suppressed  # noqa: PLC0415

        brand = ""
        try:
            brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        except Exception:  # noqa: BLE001
            return None
        if not brand:
            return None

        # v2.2.0 — MY-quirk check FIRST. If a known-broken firmware
        # suppresses this command, no point asking the backend.
        # Defensive ``getattr`` because some unit-tests construct the
        # coordinator via ``__new__`` without populating ``vehicles``.
        vehicles_map = getattr(self, "vehicles", None) or {}
        vehicle = vehicles_map.get(vin) or {}
        if is_command_suppressed(
            brand,
            vehicle.get("model"),
            vehicle.get("model_year"),
            command_id,
        ):
            return False

        cap_id = cap_id_for(brand, command_id)
        if cap_id is None:
            # No mapping registered → don't filter (Phase 2 fallback)
            return None
        return self.vehicle_supports_capability(vin, cap_id)

    # v2.8.0 quick win E — declared vs observed capability snapshot.
    #
    # When a user reports "my Audi doesn't have a charging sensor" the
    # diagnostics dump previously told us what the vehicle reported but
    # not what the integration *expected* the brand to support. Without
    # the expected-baseline we couldn't distinguish:
    #   (a) brand never supported it (declared=False)
    #   (b) vehicle does not have it on this trim (declared=True,
    #       observed=False, but no parser hit on ANY VIN)
    #   (c) parser broke (declared=True, observed=False, ran fine before)
    #
    # The snapshot returns the declared baseline (from
    # _capabilities.DECLARED_CAPABILITIES) alongside the observed signal
    # for each capability (whichever VehicleData field is the canonical
    # surface for that capability is non-None on at least one VIN). The
    # ``drift`` list is the diagnostics shortcut: any capability where
    # declared=True but observed=False on every known VIN.
    #
    # Mapping capability key -> VehicleData field name to check. The
    # field-name is the canonical "this capability has parsed at least
    # once" signal — when the parser populates it on a real poll, we
    # know the integration's pipeline understood the response. Push and
    # auth capabilities don't have a VehicleData field; they're checked
    # against the coordinator's push-manager slots / token strategy.
    _CAPABILITY_FIELD_MAP: dict[str, tuple[str, ...]] = {
        "auxiliary_heating": ("aux_heating_active",),
        "charging": ("battery_soc", "charging_state", "is_charging"),
        "climatisation": ("climatisation_state", "climatisation_active"),
        "trip_statistics": (
            "last_trip_avg_speed_kmh",
            "last_trip_distance_km",
            "lifetime_distance_km",
        ),
        "brake_service": ("service_due_in_days", "service_due_at"),
    }

    def _observe_capability(self, capability: str) -> bool:
        """Return True if the integration has observed this capability.

        For vehicle-data capabilities, scan every VIN's most-recent dict
        and return True if any mapped field is non-None.

        For push/auth capabilities, inspect coordinator-level state
        (push-manager slots, persisted token strategy).
        """
        # Push channels live on the coordinator instance directly.
        if capability == "ola_push":
            # OLA push is wired through the SEAT/CUPRA FCM manager today
            # — there's no separate slot. Treat the cupra_seat_push
            # manager being live as the observed signal.
            return getattr(self, "_cupra_seat_push", None) is not None
        if capability == "fcm_push":
            return (
                getattr(self, "_audi_vw_push", None) is not None
                or getattr(self, "_cupra_seat_push", None) is not None
            )
        if capability == "mqtt_push":
            return getattr(self, "_skoda_push", None) is not None
        if capability == "dag_login":
            client = getattr(self, "_cariad_client", None)
            if client is None:
                return False
            tokens = getattr(client, "_tokens", None)
            strategy = getattr(tokens, "strategy", "") if tokens else ""
            # Hybrid_full / data_act_portal / device_grant(_portal) all flow
            # through the browser-based DAG/IDP path (v2.6.0+).
            return strategy in (
                "hybrid_full", "data_act_portal", "device_grant",
                "device_grant_portal",
            )

        # Vehicle-data capabilities: scan VINs for a non-None field.
        fields = self._CAPABILITY_FIELD_MAP.get(capability)
        if not fields:
            # Unknown capability key — no observation possible. Returning
            # False is the safe default; drift detection will then flag
            # it only if declared=True (which is the caller's intent).
            return False
        vehicles_map = getattr(self, "vehicles", None) or {}
        for vdata in vehicles_map.values():
            if not isinstance(vdata, dict):
                continue
            for field_name in fields:
                if vdata.get(field_name) is not None:
                    return True
        return False

    def capabilities_snapshot(self) -> dict[str, dict[str, dict[str, Any] | list[str]]]:
        """Return declared + observed capabilities for this coordinator's brand.

        Shape (compatible with multi-entry diagnostics aggregation):

            {
                "<brand>": {
                    "declared": {"auxiliary_heating": True, ...},
                    "observed": {"auxiliary_heating": True, ...},
                    "drift": ["climatisation"],
                },
            }

        A brand without an entry in ``DECLARED_CAPABILITIES`` (e.g. a
        future brand that ships before the table is updated) still
        produces a well-formed snapshot: ``declared`` is an empty dict,
        ``observed`` runs as normal against whatever capability keys
        the runtime knows about, ``drift`` is always an empty list.

        ``drift`` lists capabilities the integration *expected* (declared=True)
        but did NOT observe on any known VIN this coordinator owns.
        Useful as a Repairs-flow trigger and a debug shortcut in the
        diagnostics dump.
        """
        from .cariad._capabilities import DECLARED_CAPABILITIES  # noqa: PLC0415

        try:
            brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        except Exception:  # noqa: BLE001
            brand = ""

        declared = DECLARED_CAPABILITIES.get(brand, {})

        # Observed runs over the union of declared keys plus everything
        # the field-map knows about — that way a parser populating a
        # field for a brand that hasn't declared it yet still surfaces.
        observed_keys = set(declared.keys()) | set(self._CAPABILITY_FIELD_MAP.keys())
        # Also include push/auth keys explicitly so an unknown-brand
        # snapshot still surfaces them when active.
        observed_keys |= {"ola_push", "fcm_push", "mqtt_push", "dag_login"}
        observed = {
            key: self._observe_capability(key) for key in sorted(observed_keys)
        }

        drift = sorted(
            key
            for key, declared_value in declared.items()
            if declared_value is True and observed.get(key) is False
        )

        return {
            brand: {
                "declared": dict(declared),
                "observed": observed,
                "drift": drift,
            },
        }

    async def refresh_capabilities(self, vin: str, force: bool = False) -> None:
        """Best-effort fetch of the per-VIN capabilities document.

        Failure is logged at debug and never blocks setup or polling. The
        cache stays as-is on error so we don't lose previously known data.
        Only SEAT/CUPRA's OLA endpoint is implemented in this PR; other
        brands return silently from the client side.
        """
        # v2.12.7 — in EU Data Act portal mode the BFF capabilities endpoint
        # is unreachable (the portal sentinel token isn't a real BFF token),
        # so the call always 400s with "missing or invalid auth header".
        # Skip it to drop the debug-log noise; the portal serves its own
        # field set. Gated on the portal STRATEGY specifically (not the
        # broader read-only flag) so a user-toggled read-only native session
        # — which still has a real token — keeps fetching capabilities.
        portal_strategy = getattr(
            getattr(self._cariad_client, "_tokens", None), "strategy", ""
        )
        # v2.15.0 — the durable MBB strategy has no BFF capabilities endpoint
        # and its bearer must not be sent to the dead CARIAD BFF host; skip it
        # the same way the portal strategies are skipped.
        if portal_strategy in ("data_act_portal", "device_grant_portal", "mbb"):
            return
        if not force and self.is_capabilities_cache_fresh(vin):
            return
        client = self._cariad_client
        if client is None or not hasattr(client, "get_capabilities"):
            return
        try:
            data = await client.get_capabilities(vin)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Capabilities fetch failed for %s: %s",
                mask_vin(vin),
                err,
            )
            return
        if not isinstance(data, dict):
            return
        if not hasattr(self, "vehicle_capabilities"):
            self.vehicle_capabilities = {}
        if not hasattr(self, "_capabilities_fetched_at"):
            self._capabilities_fetched_at = {}
        self.vehicle_capabilities[vin] = data
        self._capabilities_fetched_at[vin] = datetime.now(tz=timezone.utc)
        _LOGGER.debug(
            "Capabilities cached for %s (%d entries)",
            mask_vin(vin),
            len(data),
        )

    # ── v1.20.0 Bundle 2 Phase A — Skoda static info 24h cache ───────────
    _STATIC_INFO_REFRESH_INTERVAL = timedelta(hours=24)
    _STATIC_INFO_BRANDS = ("skoda",)  # mysmob only — CARIAD/OLA equivalents TBD

    def is_static_info_cache_fresh(self, vin: str) -> bool:
        """Return True if static-info was fetched within last 24h."""
        if not hasattr(self, "_static_info_fetched_at"):
            return False
        last = self._static_info_fetched_at.get(vin)
        if last is None:
            return False
        return (datetime.now(tz=timezone.utc) - last) < self._STATIC_INFO_REFRESH_INTERVAL

    async def refresh_static_info(self, vin: str, force: bool = False) -> None:
        """v1.20.0 Bundle 2 Phase A — fetch + cache vehicle-information +
        equipment endpoints for ``vin``.

        Same best-effort pattern as ``refresh_capabilities``: errors
        logged at debug, never blocks. Cache stays on error. Only
        Skoda's mysmob backend is wired in this release.
        """
        brand = (self.entry.data.get(CONF_BRAND) or "").lower()
        if brand not in self._STATIC_INFO_BRANDS:
            return
        if not force and self.is_static_info_cache_fresh(vin):
            return
        client = self._cariad_client
        if client is None or not hasattr(client, "get_vehicle_static_info"):
            return
        try:
            data = await client.get_vehicle_static_info(vin)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Static info fetch failed for %s: %s", mask_vin(vin), err,
            )
            return
        if not isinstance(data, dict):
            return
        if not hasattr(self, "vehicle_static_info"):
            self.vehicle_static_info: dict[str, dict[str, Any]] = {}
        if not hasattr(self, "_static_info_fetched_at"):
            self._static_info_fetched_at: dict[str, datetime] = {}
        self.vehicle_static_info[vin] = data
        self._static_info_fetched_at[vin] = datetime.now(tz=timezone.utc)
        info = data.get("info") or {}
        equip = data.get("equipment") or []
        _LOGGER.debug(
            "Static info cached for %s — model=%r, year=%r, equipment=%d",
            mask_vin(vin),
            info.get("model"),
            info.get("modelYear"),
            len(equip),
        )

    # ── v1.14.0 (#24) — Trip Statistics 1h cache + parser ────────────────
    _TRIP_STATS_REFRESH_INTERVAL = timedelta(hours=1)
    _TRIP_STATS_BRANDS = ("audi", "volkswagen")  # CARIAD-BFF only
    _RECENT_TRIPS_LIMIT = 5  # how many trips to keep in extra_state_attributes

    # ── v1.15.0 (#35) — Skoda Charging History 1h cache ────────────────
    _CHARGING_HISTORY_REFRESH_INTERVAL = timedelta(hours=1)
    _CHARGING_HISTORY_BRANDS = ("skoda",)  # mysmob only — CARIAD/OLA TBD
    _RECENT_SESSIONS_LIMIT = 5

    # ── v1.16.0 (#25, #31) — Skoda Charging Profiles 1h cache ────────
    _CHARGING_PROFILES_REFRESH_INTERVAL = timedelta(hours=1)
    # v2.10.0 Group B - SEAT + CUPRA OLA now expose the same shape via
    # /v1/vehicles/{vin}/charging/profiles. ``get_charging_profiles``
    # is wired on SeatCupraClient and returns the same dict that
    # ``_parse_charging_profiles`` expects, so the existing helper
    # works unchanged for both brands.
    _CHARGING_PROFILES_BRANDS = ("skoda", "seat", "cupra")

    async def refresh_trip_statistics(
        self, vin: str, force: bool = False
    ) -> None:
        """v1.14.0 (#24) — Best-effort fetch + parse of CARIAD-BFF trip
        statistics. Failure is logged at debug and never blocks polling.

        Brand-restricted to ``audi`` and ``volkswagen`` (the only brands
        whose backends we've verified to expose ``GET /vehicle/v1/vehicles/
        {vin}/tripstatistics``). Other brands return silently.

        Cache: ``self._trip_stats_fetched_at[vin]`` — refresh only if
        more than 1h has passed since last successful fetch (or
        ``force=True``). Trip data changes rarely (per-ignition-cycle for
        shortTerm, even rarer for longTerm) so polling at the standard
        coordinator interval would waste API calls + subscription quota.

        Capability gate: if Phase 3 (#56) reports
        ``command_trip_stats: False`` for this VIN we skip — saves a
        guaranteed 403 against subscription-less accounts.
        """
        brand = ""
        try:
            brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        except Exception:  # noqa: BLE001
            return
        if brand not in self._TRIP_STATS_BRANDS:
            return
        # v2.15.0 — the durable MBB strategy reads via the legacy VSR endpoint
        # and has no BFF trip-statistics equivalent; without this gate the
        # brand-only check would send the MBB bearer to the dead CARIAD BFF
        # host every poll. Skip entirely for MBB entries.
        if getattr(
            getattr(self._cariad_client, "_tokens", None), "strategy", ""
        ) == "mbb":
            return
        if not hasattr(self, "_trip_stats_fetched_at"):
            self._trip_stats_fetched_at: dict[str, datetime] = {}
        if not force:
            last = self._trip_stats_fetched_at.get(vin)
            if last is not None:
                if datetime.now(tz=timezone.utc) - last < self._TRIP_STATS_REFRESH_INTERVAL:
                    return
        # Phase 3 (#56) capability gate — saves a guaranteed 403.
        if self.command_capability_supported(vin, "command_trip_stats") is False:
            return
        client = self._cariad_client
        if client is None or not hasattr(client, "get_trip_statistics"):
            return
        # Fetch shortTerm (per-ignition trips, "Seit Start") and longTerm
        # (since-last-reset aggregates, "Seit Tanken / Gesamt") in parallel.
        try:
            results = await asyncio.gather(
                client.get_trip_statistics(vin, "shortTerm"),
                client.get_trip_statistics(vin, "longTerm"),
                return_exceptions=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Trip stats fetch failed for %s: %s", mask_vin(vin), err
            )
            return
        # ``return_exceptions=True`` — drop exceptions to None so the parser
        # treats them as empty responses (keeps stale cache).
        short_resp: Any = (
            results[0] if not isinstance(results[0], BaseException) else None
        )
        long_resp: Any = (
            results[1] if not isinstance(results[1], BaseException) else None
        )
        parsed = _parse_trip_statistics(short_resp, long_resp)
        if not parsed:
            return  # empty response — keep stale cache
        with self._vehicles_lock:
            v = self.vehicles.get(vin)
            if isinstance(v, dict):
                v.update(parsed)
        self._trip_stats_fetched_at[vin] = datetime.now(tz=timezone.utc)
        _LOGGER.debug(
            "Trip stats updated for %s: %d short / %d long term",
            mask_vin(vin),
            parsed.get("_shortterm_count", 0),
            parsed.get("_longterm_count", 0),
        )

    async def refresh_charging_history(
        self, vin: str, force: bool = False
    ) -> None:
        """v1.15.0 (#35) — Best-effort fetch + parse of Skoda mysmob
        charging-history. Brand-restricted to ``skoda``; CARIAD-BFF + OLA
        equivalent endpoints not yet verified (Research 2026-05-02).

        Cache: 1h via ``_charging_history_fetched_at[vin]`` — sessions
        change at most once per day for typical users.
        """
        brand = ""
        try:
            brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        except Exception:  # noqa: BLE001
            return
        if brand not in self._CHARGING_HISTORY_BRANDS:
            return
        if not hasattr(self, "_charging_history_fetched_at"):
            self._charging_history_fetched_at: dict[str, datetime] = {}
        if not force:
            last = self._charging_history_fetched_at.get(vin)
            if last is not None:
                if datetime.now(tz=timezone.utc) - last < self._CHARGING_HISTORY_REFRESH_INTERVAL:
                    return
        # Capability gate (#56 Phase 3) — saves a guaranteed 403 for
        # accounts without the charging entitlement.
        if (
            self.command_capability_supported(vin, "command_charging_history") is False
        ):
            return
        client = self._cariad_client
        if client is None or not hasattr(client, "get_charging_history"):
            return
        try:
            resp = await client.get_charging_history(vin)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Charging-history fetch failed for %s: %s", mask_vin(vin), err
            )
            return
        parsed = _parse_charging_history(resp)
        if not parsed:
            return  # empty → keep stale cache
        with self._vehicles_lock:
            v = self.vehicles.get(vin)
            if isinstance(v, dict):
                v.update(parsed)
        self._charging_history_fetched_at[vin] = datetime.now(tz=timezone.utc)
        _LOGGER.debug(
            "Charging-history updated for %s: total %.2f kWh, last session %s",
            mask_vin(vin),
            parsed.get("total_charged_energy_kwh", 0),
            parsed.get("last_charging_session_start", "n/a"),
        )

    # ── v1.17.1 (Bruno-Collection) — SEAT/CUPRA Battery Care 1h cache ─
    _BATTERY_CARE_REFRESH_INTERVAL = timedelta(hours=1)
    _BATTERY_CARE_BRANDS = ("cupra", "seat")  # OLA only

    async def refresh_battery_care(
        self, vin: str, force: bool = False
    ) -> None:
        """v1.17.1 (Bruno seq 10/11) — Battery Care status + target SoC.

        SEAT/CUPRA-only. Reads two thin endpoints in parallel and merges
        into ``vehicle["battery_care_*"]`` fields. Best-effort: failure
        logged at debug, never blocks polling.

        Cache: 1h via ``_battery_care_fetched_at[vin]`` — battery care
        toggles change at most a few times per year for typical users.
        """
        brand = ""
        try:
            brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        except Exception:  # noqa: BLE001
            return
        if brand not in self._BATTERY_CARE_BRANDS:
            return
        if not hasattr(self, "_battery_care_fetched_at"):
            self._battery_care_fetched_at: dict[str, datetime] = {}
        if not force:
            last = self._battery_care_fetched_at.get(vin)
            if last is not None:
                if (
                    datetime.now(tz=timezone.utc) - last
                    < self._BATTERY_CARE_REFRESH_INTERVAL
                ):
                    return
        # Capability gate (#56 Phase 3) — saves a guaranteed 403 for
        # accounts without the charging entitlement.
        if (
            self.command_capability_supported(vin, "command_battery_care_read")
            is False
        ):
            return
        client = self._cariad_client
        if client is None or not hasattr(client, "get_battery_care"):
            return
        try:
            results = await asyncio.gather(
                client.get_battery_care(vin),
                client.get_battery_care_target(vin),
                return_exceptions=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Battery-care fetch failed for %s: %s", mask_vin(vin), err
            )
            return
        # ``return_exceptions=True`` — drop exceptions to None so we
        # treat them as empty responses (keeps stale cache). Same
        # pattern as v1.14.0 trip-stats parsing fix.
        status: Any = (
            results[0] if not isinstance(results[0], BaseException) else None
        )
        target: Any = (
            results[1] if not isinstance(results[1], BaseException) else None
        )
        update: dict[str, Any] = {}
        if isinstance(status, dict) and "enabled" in status:
            update["battery_care_enabled"] = bool(status["enabled"])
        if isinstance(target, dict):
            tgt = target.get("targetSocPercentage")
            if isinstance(tgt, (int, float)):
                update["battery_care_target_soc_pct"] = int(tgt)
        if not update:
            return  # both 404'd or empty — keep stale cache
        with self._vehicles_lock:
            v = self.vehicles.get(vin)
            if isinstance(v, dict):
                v.update(update)
        self._battery_care_fetched_at[vin] = datetime.now(tz=timezone.utc)

    async def refresh_charging_profiles(
        self, vin: str, force: bool = False
    ) -> None:
        """v1.16.0 (#25, #31) — Best-effort fetch + parse of Skoda mysmob
        charging-profiles. Brand-restricted to ``skoda``; CARIAD-BFF +
        OLA equivalent endpoints not yet verified (Research 2026-05-02).

        Cache: 1h via ``_charging_profiles_fetched_at[vin]`` — profiles
        change at most a few times per year for typical users (after
        installing a new home charger / configuring a workplace charger).
        """
        brand = ""
        try:
            brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        except Exception:  # noqa: BLE001
            return
        if brand not in self._CHARGING_PROFILES_BRANDS:
            return
        if not hasattr(self, "_charging_profiles_fetched_at"):
            self._charging_profiles_fetched_at: dict[str, datetime] = {}
        if not force:
            last = self._charging_profiles_fetched_at.get(vin)
            if last is not None:
                if (
                    datetime.now(tz=timezone.utc) - last
                    < self._CHARGING_PROFILES_REFRESH_INTERVAL
                ):
                    return
        # Capability gate (#56 Phase 3) — v1.15.0 cap-id
        # ``command_charging_profiles`` → ``EXTENDED_CHARGING_SETTINGS``.
        if (
            self.command_capability_supported(vin, "command_charging_profiles")
            is False
        ):
            return
        client = self._cariad_client
        if client is None or not hasattr(client, "get_charging_profiles"):
            return
        try:
            resp = await client.get_charging_profiles(vin)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Charging-profiles fetch failed for %s: %s",
                mask_vin(vin),
                err,
            )
            return
        parsed = _parse_charging_profiles(resp)
        if not parsed:
            return  # empty → keep stale cache
        with self._vehicles_lock:
            v = self.vehicles.get(vin)
            if isinstance(v, dict):
                v.update(parsed)
        self._charging_profiles_fetched_at[vin] = datetime.now(tz=timezone.utc)
        _LOGGER.debug(
            "Charging-profiles updated for %s: %d profiles, active=%s",
            mask_vin(vin),
            parsed.get("charging_profiles_count", 0),
            parsed.get("active_charging_profile_name", "none"),
        )

    async def _async_push_update(self, data: dict, success: bool = True) -> None:
        """Push vehicle data to HA.

        Implements log_when_unavailable: logs once when going offline,
        once when coming back online — never fills logs with repeated errors.
        Also removes stale devices when vehicles disappear from the account.
        """
        if success:
            if not self._was_available:
                _LOGGER.info(
                    "VAG Connect: vehicle reachable again (%s)",
                    mask_email(self.entry.data.get("username", "")),
                )
                self._was_available = True

            # Remove devices for VINs no longer present in the account
            await self._async_remove_stale_devices(set(data.keys()))

            self.async_set_updated_data(data)
            _LOGGER.debug("VAG Connect: pushed %d vehicle(s) to HA", len(data))
        else:
            if self._was_available:
                _LOGGER.warning(
                    "VAG Connect: vehicle unreachable — entities set to unavailable (%s)",
                    mask_email(self.entry.data.get("username", "")),
                )
                self._was_available = False
            self.last_update_success = False
            self.async_update_listeners()

    async def _async_remove_stale_devices(self, current_vins: set) -> None:
        """Remove device registry entries for VINs no longer in the account.

        Implements the stale-devices Gold quality scale rule.
        Only removes devices that were previously seen (in coordinator.data)
        but are no longer returned by the API.

        v1.17.0 — when a vehicle disappears from the account (sold,
        ownership transferred, deactivated by manufacturer), raise a
        persistent_notification BEFORE removing the device so the user
        knows why their entities just vanished. Pattern adapted from
        ``upstream/homeassistant-pycupra`` v0.2.14 ("if a previously-
        configured vehicle is not found or is deactivated at startup,
        log a warning and raise a HA notification") — applied here on
        every poll, not just startup, so account changes mid-session
        also surface.
        """
        if not self.data:
            return  # First run — nothing to clean up

        device_reg = dr.async_get(self.hass)
        previous_vins = set(self.data.keys()) - {"_meta"}

        for stale_vin in previous_vins - current_vins:
            device_entry = device_reg.async_get_device(
                identifiers={(DOMAIN, stale_vin)}
            )
            if device_entry is not None:
                _LOGGER.warning(
                    "VAG Connect: vehicle %s removed from account — "
                    "device + entities will be deleted",
                    mask_vin(stale_vin),
                )
                # v1.17.0 — surface a persistent notification BEFORE
                # the device gets removed so the user knows why their
                # entities just vanished. Best-effort: notification
                # must never block device removal.
                try:
                    from homeassistant.components import persistent_notification  # noqa: PLC0415
                    persistent_notification.async_create(
                        self.hass,
                        message=(
                            f"Das Fahrzeug **{mask_vin(stale_vin)}** ist "
                            f"nicht mehr in deinem VAG-Konto verfügbar "
                            f"({self.entry.data.get(CONF_USERNAME, 'unbekannt')}). "
                            f"Mögliche Ursachen:\n\n"
                            f"- Verkauft / Eigentümerwechsel\n"
                            f"- Connect-Subscription ist abgelaufen\n"
                            f"- Vom Hersteller deaktiviert\n\n"
                            f"Alle Entities + Geräte für diese VIN werden "
                            f"jetzt entfernt. Long-term-Statistik-Historie "
                            f"bleibt erhalten und kann nach erneutem "
                            f"Hinzufügen weiterverwendet werden."
                        ),
                        title="VAG Connect — Fahrzeug entfernt",
                        notification_id=f"vag_connect_vehicle_removed_{stale_vin}",
                    )
                except Exception:  # noqa: BLE001
                    pass  # Notification is informational only
                device_reg.async_remove_device(device_entry.id)



    async def _enrich(self, data: dict) -> dict:
        """Universal post-processing after every get_status() call.

        Sets fields that every brand should have but individual clients may omit:
        - last_updated_at: always UTC now
        - vehicle_state: derived from is_driving / charging_state / connection
        - is_driving: if not set by client, derive from vehicle_state
        - parking_address / parking_city: reverse geocode if lat/lon available (best-effort)
        """

        # Always stamp when we fetched
        data["last_updated_at"] = datetime.now(tz=timezone.utc)

        # v1.20.0 Bundle 2 Phase A — Skoda static-info enrichment.
        # If we have a cached vehicle-information + equipment block
        # for this VIN, surface the most-useful fields onto the data
        # dict for HA DeviceInfo + new sensors. Brand-restricted
        # (Skoda only currently). Lazy refresh: trigger a 24h-cache
        # check so the next poll picks up changes (model rename in
        # MyŠkoda app, software update, retrofit).
        vin = data.get("vin")
        if isinstance(vin, str) and vin:
            # v2.19.0 — rich device model from the vgql image fetch. The
            # userVehicles GraphQL (already fetched for render images) returns
            # ``media.longName`` ("Audi S6 Avant TDI quattro tiptronic") +
            # ``core.modelYear`` — far richer than the garage nickname a portal-
            # only car falls back to. Prefer it whenever available (zero extra
            # auth: it rides the image fetch that already ran).
            _img_map = getattr(self._cariad_client, "_image_data", None)
            if isinstance(_img_map, dict):
                _vimg = _img_map.get(vin)
                _long = getattr(_vimg, "long_name", None) if _vimg else None
                _short = getattr(_vimg, "short_name", None) if _vimg else None
                _iyear = getattr(_vimg, "model_year", None) if _vimg else None
                # Prefer the rich long name ("Audi S6 Avant TDI quattro
                # tiptronic"); fall back to the short model name ("S6 Avant").
                # Some cars (e.g. the Audi S6 Avant) return core.modelYear +
                # media.shortName but a NULL media.longName — long_name-only
                # left the model empty, so the device page fell back to the
                # bare brand ("Audi") even though shortName held the model.
                if isinstance(_long, str) and _long.strip():
                    data["model"] = _long.strip()
                elif isinstance(_short, str) and _short.strip():
                    data["model"] = _short.strip()
                if _iyear and not data.get("model_year"):
                    data["model_year"] = _iyear
            static = getattr(self, "vehicle_static_info", {}).get(vin)
            if isinstance(static, dict):
                info = static.get("info") or {}
                equip = static.get("equipment") or []
                # Don't clobber widget-derived license_plate (which
                # is fresher) — only fill if not already set
                if not data.get("license_plate"):
                    plate = info.get("licensePlate")
                    if isinstance(plate, str) and plate:
                        data["license_plate"] = plate
                if not data.get("model") and isinstance(info.get("model"), str):
                    data["model"] = info["model"]
                if not data.get("model_year") and info.get("modelYear"):
                    data["model_year"] = info["modelYear"]
                if not data.get("software_version") and isinstance(
                    info.get("softwareVersion"), str
                ):
                    data["software_version"] = info["softwareVersion"]
                if isinstance(equip, list):
                    data["equipment"] = equip
                    data["equipment_count"] = len(equip)
                # v1.22.x foundation (myskoda PR #571) — multi-angle
                # composite renders. Parse compositeRenders[].layers[]
                # into a flat dict keyed by lowercased viewPoint, value
                # = highest-order REAL layer URL. Defensive against
                # empty list (older firmware), missing layers (corrupt
                # entries), missing viewPoint (forward-compat unknown
                # types), missing url (backend hiccup).
                renders = static.get("renders") or {}
                if isinstance(renders, dict):
                    composites = renders.get("compositeRenders")
                    if isinstance(composites, list) and composites:
                        flat: dict[str, str] = {}
                        for entry in composites:
                            if not isinstance(entry, dict):
                                continue
                            layers = entry.get("layers")
                            if not isinstance(layers, list) or not layers:
                                continue
                            # Pick the lowest-order REAL layer (order=0
                            # is the base render — additional layers
                            # are overlays we don't surface here).
                            real_layers = [
                                layer for layer in layers
                                if isinstance(layer, dict)
                                and layer.get("type") == "REAL"
                                and isinstance(layer.get("url"), str)
                                and isinstance(layer.get("viewPoint"), str)
                            ]
                            if not real_layers:
                                continue
                            base = min(
                                real_layers,
                                key=lambda layer: layer.get("order", 0)
                                if isinstance(layer.get("order"), int) else 0,
                            )
                            view = base["viewPoint"].lower()
                            flat[view] = base["url"]
                        if flat:
                            data["composite_render_urls"] = flat
                            # v1.24.0 — Merge composite renders into
                            # ``image_urls`` so the unified image-
                            # platform entity-creation path picks them
                            # up via the same "leftover key" branch
                            # that catches CUPRA/SEAT OLA viewPoints.
                            # ``setdefault`` keeps any pre-existing
                            # value (defensive — mysmob does not write
                            # ``image_urls`` directly, but if that
                            # changes upstream, the explicit set wins).
                            existing = data.get("image_urls")
                            merged: dict[str, str] = (
                                dict(existing)
                                if isinstance(existing, dict) else {}
                            )
                            for view, url in flat.items():
                                merged.setdefault(view, url)
                            data["image_urls"] = merged
            # Trigger lazy 24h cache refresh — if fresh, no-op
            try:
                await self.refresh_static_info(vin)
            except Exception:  # noqa: BLE001
                pass  # Best-effort, never blocks _enrich

        # v1.19.1 — Pycupra-style API quota visibility. Copy the brand-
        # client's last-observed X-RateLimit-Remaining header onto each
        # vehicle's data dict so the coordinator-bound sensor mapping
        # works without a per-VIN lookup. Same value for all vehicles
        # of a given brand (auth cookie is brand-scoped, not VIN-scoped).
        # ``None`` means we've never seen the header (older backend or
        # endpoint) — sensor stays ``unknown`` instead of showing 0.
        client = self._cariad_client
        if client is not None:
            remaining = getattr(client, "last_rate_limit_remaining", None)
            limit = getattr(client, "last_rate_limit_limit", None)
            data["requests_remaining_today"] = remaining
            data["requests_limit_today"] = limit
            data["requests_reset_at"] = getattr(
                client, "last_rate_limit_reset_at", None,
            )

            # v1.19.4 Bundle 1 — Quota-Warning Repair-Issue trigger.
            # Pattern matches v1.13.0 stale-vehicle persistent_notification:
            # idempotent issue creation when threshold crossed, idempotent
            # delete when remaining recovers (e.g. midnight reset).
            #
            # Defensive: only fires when remaining is an actual int (not
            # None = backend doesn't send the header; not MagicMock =
            # existing TestEnrich tests stub the client). Same isinstance
            # check applies to limit so the safe-divide in repairs.py
            # never sees garbage.
            if isinstance(remaining, int):
                from .repairs import (  # noqa: PLC0415
                    raise_issue_quota_low,
                    clear_quota_issue,
                    QUOTA_WARN_THRESHOLD,
                    QUOTA_CRITICAL_THRESHOLD,
                )
                quota_limit = limit if isinstance(limit, int) else None
                if remaining < QUOTA_CRITICAL_THRESHOLD:
                    raise_issue_quota_low(
                        self.hass, self.entry.entry_id,
                        remaining=remaining, limit=quota_limit, critical=True,
                    )
                elif remaining < QUOTA_WARN_THRESHOLD:
                    raise_issue_quota_low(
                        self.hass, self.entry.entry_id,
                        remaining=remaining, limit=quota_limit, critical=False,
                    )
                else:
                    # Quota recovered — clear any stale warning
                    clear_quota_issue(self.hass, self.entry.entry_id)

        # v2.9.0 - VW account-lock detector. The brand client flips
        # ``account_lock_detected`` from inside _refresh_tokens once we
        # see 3 HTTP 423 or 403-with-throttle-marker responses in
        # 30 minutes. Surface as a Repair issue so the user knows why
        # their integration went silent and gets actionable next steps.
        client = getattr(self, "_cariad_client", None)
        if client is not None:
            from .repairs import (  # noqa: PLC0415
                raise_issue_account_locked,
                clear_account_locked_issue,
            )
            if getattr(client, "account_lock_detected", False):
                # Pull the last status from the lock_history if any
                history = getattr(client, "_lock_history", [])
                last_status = history[-1][1] if history else 423
                raise_issue_account_locked(
                    self.hass, self.entry.entry_id,
                    brand=self.entry.data.get("brand", "unknown"),
                    last_status=last_status,
                )
            else:
                clear_account_locked_issue(self.hass, self.entry.entry_id)

        # Fix #32: Defensive is_charging reset.
        # When plug is disconnected, charging MUST be False regardless of API state.
        # Prevents is_charging staying stuck on "True" after charging ends.
        if not data.get("plug_connected") and data.get("is_charging"):
            data["is_charging"] = False
            _LOGGER.debug(
                "is_charging reset to False — plug not connected (defensive fix #32)"
            )

        # Derive vehicle_state if not set by client
        if not data.get("vehicle_state"):
            if not data.get("is_online", True):
                data["vehicle_state"] = "OFFLINE"
            elif data.get("is_driving"):
                data["vehicle_state"] = "DRIVING"
            elif data.get("is_charging"):
                data["vehicle_state"] = "CHARGING"
            else:
                data["vehicle_state"] = "PARKED"

        # Derive is_driving from vehicle_state if client didn't set it
        if not data.get("is_driving") and data.get("vehicle_state") == "DRIVING":
            data["is_driving"] = True

        # Reverse geocode parking position — opt-in, privacy-aware (#60).
        # Default OFF: vehicle GPS is sensitive and would otherwise be sent
        # to a third-party service (OpenStreetMap Nominatim) on every poll.
        if self._reverse_geocoding_enabled():
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat and lon and not data.get("parking_address"):
                try:
                    result = await self._reverse_geocode(float(lat), float(lon))
                    if result:
                        data["parking_address"] = result.get("address")
                        data["parking_city"] = result.get("city")
                except Exception:  # noqa: BLE001
                    pass  # geocoding is optional — never fail an update because of it

        return data

    def _reverse_geocoding_enabled(self) -> bool:
        """Return True if the user explicitly opted into reverse geocoding."""
        # Use direct comparison to True so MagicMock entries in tests don't
        # accidentally evaluate as truthy and trigger an HTTP call.
        options = dict(getattr(self.entry, "options", None) or {})
        data = dict(getattr(self.entry, "data", None) or {})
        return (
            options.get(CONF_ENABLE_REVERSE_GEOCODING, False) is True
            or data.get(CONF_ENABLE_REVERSE_GEOCODING, False) is True
        )

    async def _reverse_geocode(
        self, lat: float, lon: float
    ) -> dict[str, str | None] | None:
        """Reverse geocode lat/lon via Nominatim using HA's shared aiohttp session.

        Coordinates are rounded to 3 decimals (~110m precision) for caching
        so we do not hit Nominatim every poll for the same parking spot.
        """
        from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
            async_get_clientsession,
        )

        # Lazy initialisation so tests bypassing __init__ still work.
        if not hasattr(self, "_geocode_cache"):
            self._geocode_cache = {}

        cache_key = (round(lat, 3), round(lon, 3))
        if cache_key in self._geocode_cache:
            return self._geocode_cache[cache_key]

        from aiohttp import ClientTimeout  # noqa: PLC0415

        session = async_get_clientsession(self.hass)
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lon}&format=json&addressdetails=1"
        )
        headers = {"User-Agent": "VAGConnect/1.x (+https://github.com/its-me-prash/vwgroup-connect-ha)"}
        try:
            async with session.get(
                url, headers=headers, timeout=ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return None
                payload = await resp.json()
        except Exception:  # noqa: BLE001
            return None

        addr = payload.get("address", {}) if isinstance(payload, dict) else {}
        road = addr.get("road") or addr.get("pedestrian") or addr.get("path", "")
        house = addr.get("house_number", "")
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality", "")
        )
        display = payload.get("display_name", "") if isinstance(payload, dict) else ""

        street = f"{road} {house}".strip() if house else road
        address = (
            f"{street}, {city}".strip(", ")
            if street and city
            else (city or display[:60])
        )

        result: dict[str, str | None] = {
            "address": address or None,
            "city": city or None,
        }
        self._geocode_cache[cache_key] = result
        return result

    def _save_vehicle_cache(self) -> None:
        """Persist the last-known-good vehicle snapshot (debounced 30s).

        Portal-safety: strips runtime-only keys and writes the recorded values
        to ``.storage`` so they survive a Home Assistant restart. Scheduled via
        ``async_delay_save`` so it never blocks the poll.
        """
        store = getattr(self, "_vehicle_store", None)
        if store is None:
            return

        def _snapshot() -> dict[str, Any]:
            from .cariad.vehicle_cache import strip_runtime  # noqa: PLC0415
            with self._vehicles_lock:
                vehicles = {
                    vin: strip_runtime(v)
                    for vin, v in self.vehicles.items()
                    if vin != "_meta" and isinstance(v, dict)
                }
            return {
                "saved_at": datetime.now(tz=timezone.utc).isoformat(),
                "vehicles": vehicles,
            }

        store.async_delay_save(_snapshot, 30)

    async def _async_update_data(self) -> dict[str, Any]:
        """Manual refresh — fetches fresh status for all known VINs."""
        if not self._started or self._cariad_client is None:
            with self._vehicles_lock:
                return dict(self.vehicles)
        try:
            vins = list(self.vehicles.keys())
            results = await asyncio.gather(
                *[self._cariad_client.get_status(vin) for vin in vins],
                return_exceptions=True,
            )
            # v2.18.0 (A1) — same shape as the setup fetch: merge + enrich
            # outside the lock, assign inside.
            #
            # This path runs on every async_request_refresh(), i.e. after every
            # command. It stored the raw primary, so locking the car made its
            # supplementary fields (vw.de odometer, portal SoC, …) blank out
            # until the next poll tick — data we already had, thrown away.
            refreshed: list[tuple[str, dict[str, Any]]] = []
            for vin, result in zip(vins, results):
                if isinstance(result, Exception):
                    _LOGGER.debug("Refresh failed for %s: %s", mask_vin(vin), result)
                    continue
                if isinstance(result, VehicleData):
                    merged = await self._merge_supplementary(vin, result)
                    data = merged.to_dict()
                    data["_client"] = self._cariad_client
                    refreshed.append((vin, await self._enrich(data)))

            with self._vehicles_lock:
                for vin, data in refreshed:
                    self.vehicles[vin] = self._apply_optimistic_hold(vin, data)
            # v2.14.3 — a mid-poll 401 may have silently re-logged the
            # website-authproxy session (rotating its cookie jar). Persist the
            # fresh cookies so the next restart keeps skipping the OTP prompt.
            # No-op (and cheap) for every non-website-authproxy entry.
            self._persist_website_cookies()
            _LOGGER.debug("VAG Connect: Manual refresh OK")
            return dict(self.vehicles)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("VAG Connect: Manual refresh failed: %s", err)
            with self._vehicles_lock:
                return dict(self.vehicles)


    async def async_lock(self, vin: str) -> None:
        # SEAT/CUPRA lock requires a SecToken obtained from S-PIN verify.
        # Surface the missing-PIN case before the API call so HA shows a
        # clean translation key rather than a low-level SpinError trace.
        #
        # v1.9.1 (#92): Audi/VW EU also need the S-PIN for lock on premium
        # models (CARIAD BFF returns ``403 spin_error`` otherwise). We pass
        # the configured S-PIN through to ``command_lock``; if it's empty
        # the call still goes through (older/non-premium models that don't
        # enforce S-PIN on lock keep working) but premium models will
        # hit the 403 with ``spinState=DEFINED`` — that's then a clear
        # signal to configure the S-PIN, not an integration bug.
        brand = self.entry.data.get(CONF_BRAND, "").lower()
        spin = self._spin_from_entry(vin)  # #759 — per-VIN override, else shared
        if brand in ("seat", "cupra") and not spin:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="spin_required",
            )
        # v1.11.1 (3B-Part-3) — optimistic UI: assume the lock will succeed
        # so the HA card flips to "locked" immediately. Reverts on failure.
        #
        # v2.18.0 (#759) — seat/cupra added: their command_lock now takes a spin
        # (mirroring their command_unlock, which always has). Before this, the
        # per-VIN S-PIN was resolved and presence-checked above, then dropped
        # here, so seat/cupra lock silently used the shared PIN. The brands
        # whose command_lock does NOT accept spin (skoda lock needs none;
        # porsche/vw_na) are correctly excluded — passing it would TypeError.
        cmd_kwargs = (
            {"spin": spin}
            if (brand in ("audi", "volkswagen", "seat", "cupra") and spin)
            else {}
        )
        await self._cariad_cmd_optimistic(
            vin, "command_lock",
            optimistic={"doors_locked": True},
            **cmd_kwargs,
        )

    async def async_unlock(self, vin: str) -> None:
        # v2.17.5 (#759) — per-VIN S-PIN override, else the shared per-entry
        # S-PIN (Options over Data). Same result as before for single-S-PIN setups.
        spin = self._spin_from_entry(vin)
        if not spin:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="spin_required",
            )
        # v1.11.1 (3B-Part-3) — optimistic UI: assume unlock will succeed.
        await self._cariad_cmd_optimistic(
            vin, "command_unlock",
            optimistic={"doors_locked": False},
            spin=spin,
        )

    async def async_start_climatisation(self, vin: str) -> None:
        # v1.11.1 (3B-Part-3) — optimistic UI: climate flips to active
        # immediately. Backend value will overwrite on next poll if it
        # disagrees (which is rare — start succeeds for entitled VINs).
        # v1.14.0 (#29) — PPE/PPC body shape conditional. User option
        # ``force_ppe_climate`` forces the new body shape (no
        # targetTemperature*, climatisationMode mandatory) for Audi
        # vehicles on PPC platforms (Q6 e-tron, A6 e-tron, RS e-tron GT
        # Facelift, A3 2024+ PHEV). VW EU and other brands ignore the
        # option — only Audi's CARIAD backend differentiates.
        cmd_kwargs: dict[str, Any] = {}
        brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        if brand in ("audi", "volkswagen"):
            options = dict(getattr(self.entry, "options", None) or {})
            data = dict(getattr(self.entry, "data", None) or {})
            ppe_mode = False
            if isinstance(options, dict):
                ppe_mode = bool(options.get(CONF_FORCE_PPE_CLIMATE, False))
            if not ppe_mode and isinstance(data, dict):
                ppe_mode = bool(data.get(CONF_FORCE_PPE_CLIMATE, False))
            if ppe_mode:
                cmd_kwargs["ppe_mode"] = True
        await self._cariad_cmd_optimistic(
            vin, "command_start_climate",
            optimistic={
                "climatisation_state": "VENTILATION",
                "climatisation_active": True,
            },
            **cmd_kwargs,
        )

    async def async_stop_climatisation(self, vin: str) -> None:
        # v1.11.1 (3B-Part-3) — optimistic UI.
        await self._cariad_cmd_optimistic(
            vin, "command_stop_climate",
            optimistic={
                "climatisation_state": "OFF",
                "climatisation_active": False,
            },
        )

    async def async_start_climate_control(
        self,
        vin: str,
        *,
        temp_c: float | None = None,
        glass_heating: bool | None = None,
        seat_fl: bool | None = None,
        seat_fr: bool | None = None,
        seat_rl: bool | None = None,
        seat_rr: bool | None = None,
        climatisation_at_unlock: bool | None = None,
        climatisation_mode: str | None = None,
    ) -> None:
        """v2.10.0 - rich climate-start with per-seat + mode payload.

        Only applicable for Audi + VW EU (CARIAD BFF accepts the full
        payload). Other brands fall through to the basic
        ``async_start_climatisation`` method - the extra payload fields are
        silently dropped because the OLA / mysmob / PPA backends reject
        them. Coordinator-level optimistic state matches the basic start
        path so the climate sensors flip immediately.
        """
        if self._cariad_client is None:
            _LOGGER.error(
                "VAG Connect: no CARIAD client - cannot execute "
                "command_start_climate_control"
            )
            return
        brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        if brand in ("audi", "volkswagen"):
            await self._cariad_cmd_optimistic(
                vin, "command_start_climate_control",
                optimistic={
                    "climatisation_state": "VENTILATION",
                    "climatisation_active": True,
                },
                temp_c=temp_c,
                glass_heating=glass_heating,
                seat_fl=seat_fl,
                seat_fr=seat_fr,
                seat_rl=seat_rl,
                seat_rr=seat_rr,
                climatisation_at_unlock=climatisation_at_unlock,
                climatisation_mode=climatisation_mode,
            )
        else:
            # Fall through to the basic climatisation start for other
            # brands. Extra payload fields are silently dropped because
            # the non-CARIAD backends reject them on the wire.
            await self.async_start_climatisation(vin)

    async def async_start_charging(self, vin: str) -> None:
        # v1.11.1 (3B-Part-3) — optimistic UI. Backend usually
        # transitions through READY_FOR_CHARGING → CHARGING within
        # 5–15 s; we set the final value optimistically.
        await self._cariad_cmd_optimistic(
            vin, "command_start_charging",
            optimistic={"charging_state": "CHARGING", "is_charging": True},
        )

    async def async_stop_charging(self, vin: str) -> None:
        # v1.11.1 (3B-Part-3) — optimistic UI.
        await self._cariad_cmd_optimistic(
            vin, "command_stop_charging",
            optimistic={"charging_state": "NOT_CHARGING", "is_charging": False},
        )

    async def async_flash_lights(self, vin: str) -> None:
        # SEAT/CUPRA require the user position in the honk-and-flash payload
        # (HTTP 400 otherwise). Other brands accept and ignore it.
        #
        # ️ [Inference] We pass the **vehicle's** last-known position
        # (cached from the most recent status poll) into the OLA
        # ``userPosition`` field. This is verified to work on the OLA
        # endpoint and matches the pycupra/myskoda implementations.
        # It is NOT verified that the official My SEAT / My CUPRA mobile
        # apps populate this field the same way (they may use phone GPS
        # instead). See ``cariad/api/seat_cupra.py:command_flash`` for
        # the full caveat. Pragmatic fix that passes server validation
        # — semantic correctness against the official apps is unverified.
        vehicle = self.vehicles.get(vin, {})
        await self._cariad_cmd(
            vin,
            "command_flash",
            latitude=vehicle.get("latitude"),
            longitude=vehicle.get("longitude"),
        )

    async def async_set_target_soc(self, vin: str, target: int) -> None:
        await self._cariad_cmd(vin, "command_set_target_soc", target=target)

    async def async_set_battery_care(self, vin: str, enabled: bool) -> None:
        """v2.18.0 — toggle battery-care (preservation) mode.

        The read side has shipped since v2.10.0 (``refresh_battery_care``
        fills ``battery_care_enabled`` + ``battery_care_target_soc_pct``) and
        the brand client has had the command just as long — nothing was ever
        wired between them, so the state was visible but not settable.
        """
        await self._cariad_cmd_optimistic(
            vin, "command_set_battery_care",
            optimistic={"battery_care_enabled": enabled},
            enabled=enabled,
        )

    async def async_set_battery_care_target(self, vin: str, target_pct: int) -> None:
        """v2.18.0 — set the battery-care top-charge target in percent.

        Not clamped here: the backend enforces 50-100 and rejects anything
        else, and a silent clamp would hide that constraint from the user.
        """
        await self._cariad_cmd_optimistic(
            vin, "command_set_battery_care_target",
            optimistic={"battery_care_target_soc_pct": target_pct},
            target_pct=target_pct,
        )

    async def async_set_climatisation_temperature(self, vin: str, temp_c: float) -> None:
        await self._cariad_cmd(vin, "command_set_climate_temperature", temp_c=temp_c)

    async def async_update_charging_settings(
        self,
        vin: str,
        target_soc: int | None = None,
        max_charge_current: str | None = None,
        auto_unlock_charge: bool | None = None,
    ) -> None:
        """v2.10.0 Group B - SEAT/CUPRA settable charge plan.

        Dispatches to ``command_update_charging_settings`` on the brand
        client. Wired on SeatCupraClient against POST
        /v1/vehicles/{vin}/charging/actions/update-settings; other
        brands raise AttributeError which Phase 2's
        ``record_command_failure`` classifies as MISSING_CAPABILITY.
        """
        await self._cariad_cmd(
            vin,
            "command_update_charging_settings",
            target_soc=target_soc,
            max_charge_current=max_charge_current,
            auto_unlock_charge=auto_unlock_charge,
        )

    async def async_find_charging_stations(
        self,
        latitude: float,
        longitude: float,
        radius_m: int = 5000,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """v2.0.0 (Big-Bang) — POI lookup for nearby charging stations.

        Returns a list of station dicts (raw backend fields). Currently
        wired for CARIAD-BFF brands (VW EU + Audi); other brands raise
        ``AttributeError`` which Phase-2 bookkeeping classifies as
        ``MISSING_CAPABILITY`` so users get a clean error message in
        the service-call response.
        """
        client = self._cariad_client
        if not hasattr(client, "find_charging_stations"):
            raise AttributeError(
                "find_charging_stations not supported for this brand "
                "(CARIAD-BFF only — Audi + VW EU)"
            )
        # ``client`` is typed Any (brand-polymorphic), so cast through
        # an explicit local for mypy's --warn-return-any.
        result: list[dict[str, Any]] = await client.find_charging_stations(
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            max_results=max_results,
        )
        return result

    async def async_set_departure_timer(
        self,
        vin: str,
        timer_id: int,
        enabled: bool,
        departure_time: str | None,
        recurring_on: list[str] | None = None,
    ) -> None:
        """Set a departure timer via CARIAD API.

        v2.0.0 (Big-Bang) — accepts optional ``recurring_on`` list of
        weekday strings (``MONDAY``, ``TUESDAY``, …) so users can wire
        weekly preheat schedules via the ``vag_connect.set_departure_timer``
        service. Forwarded as-is to the brand client; clients that don't
        support per-weekday schedules ignore the param.
        """
        await self._cariad_cmd(
            vin,
            "command_set_departure_timer",
            timer_id=timer_id,
            enabled=enabled,
            departure_time=departure_time,
            recurring_on=recurring_on,
        )

    async def async_engine_start(self, vin: str) -> None:
        """v1.14.0 (#28) — Audi ICE Remote Engine Start.

        Audi-only — the underlying client method is implemented on
        ``AudiClient`` (CARIAD-BFF ``/vehicle/v1/engine/{VIN}/...``).
        Other brands' clients don't expose ``command_engine_start`` so
        the dispatch will raise ``AttributeError``, which Phase 2's
        ``record_command_failure`` then classifies as
        ``MISSING_CAPABILITY``.

        Capability gating (Phase 3, v1.13.0) is recommended on the
        platform side — see ``cariad/_capabilities.py``.
        """
        await self._cariad_cmd(vin, "command_engine_start")

    async def async_engine_stop(self, vin: str) -> None:
        """v1.14.0 (#28) — Audi ICE Remote Engine Stop. No S-PIN required."""
        await self._cariad_cmd(vin, "command_engine_stop")

    # ── v1.17.1 (Bruno-Collection) — SEAT/CUPRA new commands ───────────

    async def async_start_ventilation(self, vin: str) -> None:
        """v1.17.1 — SEAT/CUPRA cabin ventilation (without aux-heating)."""
        await self._cariad_cmd(vin, "command_start_ventilation")

    async def async_stop_ventilation(self, vin: str) -> None:
        await self._cariad_cmd(vin, "command_stop_ventilation")

    async def async_start_aux_heating(
        self,
        vin: str,
        duration_min: int | None = None,
        target_c: float | None = None,
    ) -> None:
        """Start engine pre-heater (Standheizung).

        v1.17.1: SEAT/CUPRA Webasto auxiliary heating start. Pre-flight
        S-PIN check (analog to ``async_unlock``) so HA shows a clean
        translation key rather than a low-level SpinError trace.

        v2.8.0: extended for Audi + VW EU. CARIAD-BFF accepts
        ``duration_in_min`` + ``target_temperature_in_kelvin`` in the
        body, no S-PIN required on this surface. SEAT/CUPRA's OLA
        endpoint silently drops these kwargs (see
        ``seat_cupra.command_start_aux_heating``).

        When the caller does not pass ``duration_min`` / ``target_c``
        the integration reads the per-config ``auxheat_duration`` /
        ``auxheat_target_temp`` numbers stored under ``entry.options``
        (written by the new v2.8.0 ``VagConnectNumber`` sliders). If
        those are absent we fall back to the spec defaults (30 min,
        21 C), matching the numbers the Audi + VW phone apps preselect.
        """
        brand = str(self.entry.data.get(CONF_BRAND, "")).lower()
        cariad_brand = brand in {"volkswagen", "audi"}

        # SEAT/CUPRA needs S-PIN, Audi + VW EU don't. Only enforce on
        # the SEAT/CUPRA path so VW/Audi users without S-PIN configured
        # can still use the engine pre-heater.
        if not cariad_brand:
            spin = self._spin_from_entry(vin)  # #759 per-VIN
            if not spin:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="spin_required",
                )
            await self._cariad_cmd(vin, "command_start_aux_heating", spin=spin)
            return

        options = dict(getattr(self.entry, "options", None) or {})
        if duration_min is None:
            opt_dur = options.get("auxheat_duration") if isinstance(options, dict) else None
            try:
                duration_min = int(opt_dur) if opt_dur is not None else 30
            except (TypeError, ValueError):
                duration_min = 30
        if target_c is None:
            opt_temp = options.get("auxheat_target_temp") if isinstance(options, dict) else None
            try:
                target_c = float(opt_temp) if opt_temp is not None else 21.0
            except (TypeError, ValueError):
                target_c = 21.0
        await self._cariad_cmd(
            vin,
            "command_start_aux_heating",
            duration_min=int(duration_min),
            target_c=float(target_c),
        )

    async def async_stop_aux_heating(self, vin: str) -> None:
        """v1.17.1 — Aux heating stop (no S-PIN per Bruno seq 30)."""
        await self._cariad_cmd(vin, "command_stop_aux_heating")

    async def async_send_destination(
        self,
        vin: str,
        latitude: float,
        longitude: float,
        name: str,
        **address_fields: str,
    ) -> None:
        """v1.17.1 (#36) — Send navigation destination to vehicle.

        SEAT/CUPRA only initially (Bruno-confirmed). Other brands raise
        AttributeError on the client, which Phase 2's
        ``classify_command_failure`` then records as
        ``MISSING_CAPABILITY`` and the user gets a clear notification.
        """
        await self._cariad_cmd(
            vin,
            "command_send_destination",
            latitude=latitude,
            longitude=longitude,
            name=name,
            **address_fields,
        )

    def _spin_from_entry(self, vin: str | None = None) -> str:
        """Return the configured S-PIN, preferring Options over Data.

        v2.17.5 (#759) — when *vin* is given and a per-VIN override exists in
        ``CONF_SPIN_BY_VIN``, that wins; otherwise the shared per-entry S-PIN is
        returned (so single-S-PIN setups behave exactly as before).

        v2.18.0 (#806, found by lucson) — the real reason every S-PIN command
        used to fail with ``spin_required``: ``entry.data`` and ``entry.options``
        are handed out by HA as ``MappingProxyType``, which is NOT a ``dict``
        subclass. The guards below gated every lookup on ``isinstance(..., dict)``,
        which is False for a real config entry, so this returned ``""`` on every
        live install — the S-PIN was stored fine, but never read back. The tests
        faked plain dicts, so it looked verified. Normalising to a real dict at
        the top (above) fixes it; the ``dict`` guards below now hold for the
        top-level maps, and ``by_vin`` is a genuine nested dict so its guard was
        always correct. This was NOT a 2.17.5 regression — the guard predates it.
        """
        options = dict(getattr(self.entry, "options", None) or {})
        data = dict(getattr(self.entry, "data", None) or {})
        if vin:
            # Read options THEN data: the options update-listener folds options
            # into entry.data and blanks entry.options (__init__.py), so the map
            # lives in data by read time. (Even with options preserved, the old
            # code could never have found it — see the MappingProxyType note.)
            by_vin: Any = None
            if isinstance(options, dict):
                by_vin = options.get(CONF_SPIN_BY_VIN)
            if not isinstance(by_vin, dict) and isinstance(data, dict):
                by_vin = data.get(CONF_SPIN_BY_VIN)
            if isinstance(by_vin, dict):
                per = str(by_vin.get(vin) or "")
                if per:
                    return per
        if isinstance(options, dict):
            spin = str(options.get(CONF_SPIN) or "")
            if spin:
                return spin
        if isinstance(data, dict):
            return str(data.get(CONF_SPIN) or "")
        return ""

    def _refresh_mbb_command_spin(self) -> None:
        """Push the current (options-first) S-PIN into an already-armed MBB
        command connector so an S-PIN added or changed via Options takes effect
        without a restart (#666). Fail-soft: no-op if nothing is armed.

        Without this, the connector captured its S-PIN once at arm time, so a
        later Options edit was invisible until a reload and the user got the
        'configure your S-PIN' error even though they had configured it.
        """
        client = getattr(self, "_cariad_client", None)
        target = getattr(client, "_mbb_command_target", None)
        cmd = target() if callable(target) else None
        if cmd is not None:
            cmd._spin = self._spin_from_entry()

    def _ensure_dispatcher(self) -> Any:  # CommandDispatcher (avoid TYPE_CHECKING import)
        """Return ``self._dispatcher``, lazily creating one if missing.

        v1.25.0 PR-D: tests that bypass __init__ via __new__() may not
        have a dispatcher set; this fallback ensures coord-level
        delegations still work. Production __init__ sets it eagerly.
        """
        from ._command_dispatcher import CommandDispatcher  # noqa: PLC0415
        d = getattr(self, "_dispatcher", None)
        if d is None:
            d = CommandDispatcher(self)
            self._dispatcher = d
        return d

    def _get_command_lock(self, vin: str, command_class: str) -> asyncio.Lock:
        """v1.13.0 (#63 Phase 2) — per-VIN per-command-class asyncio.Lock.

        v1.25.0 PR-D: state moved to ``self._dispatcher`` (CommandDispatcher).
        See ``_command_dispatcher.py`` module docstring for refactor plan.
        """
        return self._ensure_dispatcher().get_command_lock(vin, command_class)  # type: ignore[no-any-return]

    def is_command_in_flight(self, vin: str, command_class: str) -> bool:
        """v1.13.0 (#63 Phase 2) / v1.25.0 PR-D delegated — True if a
        command for this VIN+command-class is currently locked."""
        return self._ensure_dispatcher().is_command_in_flight(vin, command_class)  # type: ignore[no-any-return]

    def _persist_website_cookies(self) -> None:
        """v2.14.3 — write the live website-authproxy cookies back to the entry.

        The website-authproxy session cookie jar rotates on each successful
        login/refresh. After such a login we export the fresh cookies and store
        them on ``entry.data[CONF_WEBSITE_COOKIES]`` so the next setup/restart
        resumes the session and keeps skipping the email-OTP prompt.

        STRICTLY guarded: a no-op unless this is a website-authproxy entry and
        the client actually exported a non-empty cookie set, and it only writes
        when the cookies actually changed (avoids a pointless entry update +
        listener churn on every poll). Never raises — a persistence hiccup must
        not break polling; the in-memory session stays valid regardless.
        """
        from .const import (  # noqa: PLC0415
            CONF_WEBSITE_AUTHPROXY,
            CONF_WEBSITE_COOKIES,
        )

        if not self.entry.data.get(CONF_WEBSITE_AUTHPROXY):
            return
        client = getattr(self, "_cariad_client", None)
        if client is None or not hasattr(client, "get_website_proxy_cookies"):
            return
        try:
            fresh: list[dict[str, Any]] = client.get_website_proxy_cookies()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "VAG Connect: website-authproxy cookie export failed (%s) "
                "— session still valid in-memory", type(err).__name__,
            )
            return
        if not fresh:
            return
        if fresh == (self.entry.data.get(CONF_WEBSITE_COOKIES) or []):
            return
        try:
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, CONF_WEBSITE_COOKIES: fresh},
            )
            _LOGGER.debug(
                "VAG Connect: persisted %d refreshed website-authproxy "
                "cookie(s) back to the entry.", len(fresh),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "VAG Connect: could not persist website-authproxy cookies "
                "(%s) — will retry next login.", type(err).__name__,
            )

    def is_read_only(self) -> bool:
        """v1.12.0 (#63) — return True if user enabled Read-only Mode.

        When True, command-bound entity platforms (lock, switch, button,
        climate, number) skip entity creation entirely. Sensor +
        binary_sensor + device_tracker platforms create normal status
        entities. Service calls that would send commands raise
        ServiceValidationError before reaching the API.

        Lookup order: portal strategy (structural) > options (Options Flow) >
        data (initial config) > False default. Pattern matches the existing
        reverse-geocoding opt-in (v1.8.0).

        v2.13.0 — the EU-Data-Act portal strategies (cookie ``data_act_portal``
        and device-code ``device_grant_portal``) are STRUCTURALLY read-only:
        their token is rejected by the command BFF (403 "clientId not
        whitelisted"), so command entities could only ever fail. Force
        read-only for them regardless of the user toggle, so lock/switch/
        button/climate/number/time platforms skip creation entirely.
        """
        client = getattr(self, "_cariad_client", None)
        tokens = getattr(client, "_tokens", None) if client else None
        strategy = getattr(tokens, "strategy", "") if tokens else ""
        # v2.14.0 — the volkswagen.de website authproxy (opt-in beta) is a
        # read-only channel too: the confidential web OAuth client has no
        # command surface, so command entities could only ever fail. Force
        # read-only structurally alongside the EU-Data-Act portal strategies.
        if strategy in (
            "data_act_portal", "device_grant_portal", "website_authproxy"
        ):
            # b12 — UNLESS an MBB command channel is armed on this read-only
            # primary: then lock/climate/charge DO have a path (they route to
            # the MBB connector), so command entities should exist. Fall through
            # to the user toggle below instead of forcing read-only.
            if not (
                self.entry.data.get(CONF_MBB_COMMAND_CHANNEL)
                and getattr(client, "_mbb_command", None) is not None
            ):
                return True
        options = dict(getattr(self.entry, "options", None) or {})
        data = dict(getattr(self.entry, "data", None) or {})
        # #543 — honour the documented precedence: an explicit Options-Flow
        # value (True OR False) wins over the initial config ``data``. The old
        # OR collapsed both to True, so disabling read-only in the Options Flow
        # was ignored whenever ``data`` had been force-set True at first setup.
        if isinstance(options, dict) and CONF_READ_ONLY in options:
            return options.get(CONF_READ_ONLY) is True
        if isinstance(data, dict) and CONF_READ_ONLY in data:
            return data.get(CONF_READ_ONLY) is True
        return False

    def is_structural_read_only(self) -> bool:
        """#543 — True when read-only is forced by the portal/website branch.

        Returns True exactly when ``is_read_only()`` is forced by the
        STRUCTURAL portal/website-authproxy branch above — i.e. the active
        strategy is one of ``data_act_portal`` / ``device_grant_portal`` /
        ``website_authproxy`` AND no MBB command channel is armed. In that
        case the read-only state is NOT a user toggle: the portal token is
        rejected by the command BFF, so there is no command path at all and
        the Options-Flow read-only switch can't change anything.

        Service-call handlers use this to pick an honest error message
        (``read_only_portal_active``) instead of the misleading
        "disable it in the options" message (``read_only_mode_active``).
        """
        client = getattr(self, "_cariad_client", None)
        tokens = getattr(client, "_tokens", None) if client else None
        strategy = getattr(tokens, "strategy", "") if tokens else ""
        if strategy in (
            "data_act_portal", "device_grant_portal", "website_authproxy"
        ):
            if not (
                self.entry.data.get(CONF_MBB_COMMAND_CHANNEL)
                and getattr(client, "_mbb_command", None) is not None
            ):
                return True
        return False

    # ── v2.15.5 — ABRP (A Better Routeplanner) telemetry push ───────────────

    def _abrp_credentials(
        self, vin: str, *, api_key: str | None = None, token: str | None = None
    ) -> tuple[str, str]:
        """Resolve the ABRP api_key + per-VIN token for *vin*.

        Inline service params win; otherwise fall back to the config-flow
        options. The token option may be a per-VIN dict ``{vin: token}`` or a
        bare single-VIN string. Returns ``("", "")`` when nothing is set.
        Never logs either value.
        """
        from .const import (  # noqa: PLC0415
            CONF_ABRP_API_KEY,
            CONF_ABRP_USER_TOKEN,
        )

        opts = getattr(self.entry, "options", None) or {}
        data = dict(getattr(self.entry, "data", None) or {})

        resolved_key = api_key or opts.get(CONF_ABRP_API_KEY) or data.get(
            CONF_ABRP_API_KEY
        ) or ""

        resolved_token = token or ""
        if not resolved_token:
            stored = opts.get(CONF_ABRP_USER_TOKEN)
            if stored is None:
                stored = data.get(CONF_ABRP_USER_TOKEN)
            if isinstance(stored, dict):
                resolved_token = str(stored.get(vin) or "")
            elif isinstance(stored, str):
                resolved_token = stored
        return str(resolved_key), str(resolved_token)

    async def async_abrp_send(
        self, vin: str, *, api_key: str | None = None, token: str | None = None
    ) -> None:
        """Build + POST the current telemetry for *vin* to ABRP.

        On a successful send the per-VIN fingerprint is recorded so the
        "ABRP data changed" binary sensor flips OFF (idempotent trigger).
        Raises ``HomeAssistantError`` on a missing credential / unknown VIN /
        missing core data / send failure so the service surfaces it; never
        logs the api_key or token.
        """
        from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
            async_get_clientsession,
        )

        from . import abrp as _abrp  # noqa: PLC0415

        vehicle = self.vehicles.get(vin)
        if not isinstance(vehicle, dict):
            raise HomeAssistantError(f"Vehicle '{vin}' not found for ABRP send.")

        resolved_key, resolved_token = self._abrp_credentials(
            vin, api_key=api_key, token=token
        )
        if not resolved_key or not resolved_token:
            raise HomeAssistantError(
                "ABRP send needs both an api_key and a per-vehicle token. "
                "Set them in the integration options (ABRP section) or pass "
                "them to the service. "
                f"(api_key={_abrp.redact(resolved_key)}, "
                f"token={_abrp.redact(resolved_token)})"
            )

        # Core field gate — never POST without soc (ABRP rejects it).
        if vehicle.get("battery_soc") is None:
            raise HomeAssistantError(
                f"ABRP send skipped for ...{vin[-4:]}: no battery state-of-"
                "charge available yet."
            )

        now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
        sample_utc = _abrp.resolve_sample_utc(vehicle, now_epoch=now_epoch)
        tlm = _abrp.build_tlm(vehicle, sample_utc)

        session = async_get_clientsession(self.hass)
        try:
            await _abrp.send_telemetry(
                session, resolved_key, resolved_token, tlm
            )
        except _abrp.AbrpError as exc:
            # exc text is already credential-free by construction.
            raise HomeAssistantError(str(exc)) from exc

        # Success — record the fingerprint so the data-changed sensor resets.
        self.abrp_last_sent_fingerprint[vin] = _abrp.telemetry_fingerprint(
            vehicle
        )
        # Nudge listeners so the binary sensor re-evaluates immediately.
        self.async_update_listeners()
        _LOGGER.debug("ABRP telemetry sent for ...%s", vin[-4:])

    def _optimistic_set(self, vin: str, fields: dict[str, Any]) -> dict[str, Any]:
        """v1.11.1 (3B-Part-3 — myskoda #832 pattern) — push expected
        post-command values into ``self.vehicles[vin]`` immediately so
        the HA UI reflects the user action without waiting 10–30 s for
        the API roundtrip. Returns a snapshot of the previous values
        so the caller can revert on failure.

        Notifies HA listeners (``async_set_updated_data``) right away —
        the entity ``is_locked`` / ``hvac_mode`` / etc. flips before
        the actual command reaches the backend. Pattern lifted from
        ``skodaconnect/myskoda`` PR #832 ("Optimistic state for lock
        and air-conditioning"), where users complained that the lock
        switch felt unresponsive without it.
        """
        previous: dict[str, Any] = {}
        with self._vehicles_lock:
            current = self.vehicles.get(vin)
            if not isinstance(current, dict):
                return previous
            for key, value in fields.items():
                previous[key] = current.get(key)
                current[key] = value
        # v2.17.2 (#666) — hold these values across the next few polls so a
        # slow backend reflecting the command doesn't snap the UI back.
        import time  # noqa: PLC0415
        expiry = time.monotonic() + _OPTIMISTIC_HOLD_SECONDS
        hold_root = getattr(self, "_optimistic_hold", None)
        if hold_root is None:
            hold_root = self._optimistic_hold = {}
        holds = hold_root.setdefault(vin, {})
        for key, value in fields.items():
            holds[key] = (value, expiry)
        # Push the optimistic snapshot to HA so entities update now.
        try:
            self.async_set_updated_data(dict(self.vehicles))
        except Exception:  # noqa: BLE001
            # async_set_updated_data may be a no-op in some test contexts —
            # the data dict mutation above is what really matters.
            pass
        return previous

    def _optimistic_revert(self, vin: str, previous: dict[str, Any]) -> None:
        """Restore the snapshot returned by ``_optimistic_set`` after a
        failed command. Same notify-after-mutate pattern."""
        if not previous:
            return
        with self._vehicles_lock:
            current = self.vehicles.get(vin)
            if not isinstance(current, dict):
                return
            for key, value in previous.items():
                current[key] = value
        # Command failed → drop the hold so the backend state takes over at once.
        hold_root = getattr(self, "_optimistic_hold", None)
        if hold_root:
            holds = hold_root.get(vin)
            if holds:
                for key in previous:
                    holds.pop(key, None)
                if not holds:
                    hold_root.pop(vin, None)
        try:
            self.async_set_updated_data(dict(self.vehicles))
        except Exception:  # noqa: BLE001
            pass

    def _apply_optimistic_hold(
        self, vin: str, fresh: dict[str, Any]
    ) -> dict[str, Any]:
        """Reconcile a freshly-polled vehicle dict with any optimistic holds.

        For each held key: drop the hold once the window elapses OR the backend
        value matches the optimistic one (confirmed); otherwise keep the
        optimistic value in ``fresh`` so a command's effect doesn't snap back
        while VW's backend catches up (#666). Mutates + returns ``fresh``."""
        hold_root = getattr(self, "_optimistic_hold", None)
        if not hold_root:
            return fresh
        holds = hold_root.get(vin)
        if not holds:
            return fresh
        import time  # noqa: PLC0415
        now = time.monotonic()
        for key in list(holds):
            value, expiry = holds[key]
            if now >= expiry:
                del holds[key]                     # window elapsed → trust backend
            elif key in fresh and fresh[key] == value:
                del holds[key]                     # backend caught up → confirmed
            else:
                fresh[key] = value                 # still pending → hold optimistic
        if not holds:
            hold_root.pop(vin, None)
        return fresh

    async def _cariad_cmd_optimistic(
        self,
        vin: str,
        method: str,
        optimistic: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Optimistic-UI variant of ``_cariad_cmd``.

        Sets the expected post-command state immediately, dispatches the
        actual API command, and reverts the UI state on failure. Used by
        actuator wrappers (``async_lock``, ``async_start_climatisation``
        etc.) where the API takes 10–30 s and the UI would otherwise feel
        unresponsive.

        The downstream ``_cariad_cmd`` already records command outcome
        into ``FeatureState`` (Phase 2), so this layer adds nothing new
        beyond UI responsiveness.
        """
        previous = self._optimistic_set(vin, optimistic)
        try:
            await self._cariad_cmd(vin, method, **kwargs)
        except Exception:
            self._optimistic_revert(vin, previous)
            raise

    # Map command-method-name → command-class for per-VIN-per-class lock.
    # v1.13.0 (#63 Phase 2). Same class = mutually-exclusive (e.g. you
    # can't start_climate while stop_climate is mid-flight). Different
    # class = parallel (you CAN unlock while charging command runs).
    _COMMAND_CLASS = {
        "command_lock": "lock",
        "command_unlock": "lock",
        "command_start_climate": "climate",
        "command_stop_climate": "climate",
        "command_set_climate_temperature": "climate",
        # v2.10.0 - rich climate-start (Audi + VW EU). Same class as the
        # basic start so the per-VIN lock serializes start <-> rich-start
        # and prevents the user double-firing both in quick succession.
        "command_start_climate_control": "climate",
        "command_start_charging": "charging",
        "command_stop_charging": "charging",
        "command_set_target_soc": "charging",
        "command_set_charge_mode": "charging",
        "command_set_min_soc": "charging",
        "command_set_max_charge_current": "charging",
        # v2.18.0 — battery care caps the top of the charge, so it shares the
        # charging lock: firing it against an in-flight target-SoC change would
        # have the two settings racing on the same backend object.
        "command_set_battery_care": "charging",
        "command_set_battery_care_target": "charging",
        "command_start_window_heating": "window_heating",
        "command_stop_window_heating": "window_heating",
        "command_flash": "flash",
        "command_wake": "wake",
        "command_set_departure_timer": "departure_timer",
        # v1.14.0 (#28) — Audi ICE Remote Engine Start/Stop. Both share
        # the "engine" class so a stop request waits for an in-flight
        # start (and vice versa) instead of overlapping.
        "command_engine_start": "engine",
        "command_engine_stop": "engine",
        # v1.17.1 (Bruno-Collection) — cabin ventilation (SEAT/CUPRA).
        # Separate class from window_heating because the OLA backend
        # accepts both concurrently.
        "command_start_ventilation": "ventilation",
        "command_stop_ventilation": "ventilation",
        # v1.17.1 (Bruno-Collection + pycupra) — Webasto aux heating.
        # SEAT/CUPRA only. Separate "aux_heating" class so it doesn't
        # block normal climatisation commands.
        "command_start_aux_heating": "aux_heating",
        "command_stop_aux_heating": "aux_heating",
        # v1.17.1 (#36) — Navigation send-destination. Own class so it
        # doesn't serialise with other commands (it's a fire-and-forget
        # PUT, no need to coordinate with locks/climate/etc.).
        "command_send_destination": "destination",
    }

    async def _cariad_cmd(self, vin: str, method: str, **kwargs: Any) -> None:
        """Dispatch a command to the CARIAD client then refresh state.

        v1.9.1 (Capability-Filter Phase 2, #56) — every command outcome
        flows into ``FeatureState`` automatically:

        - **Success** → ``record_command_success(vin, method)`` flips
          ``supported_by_vehicle`` and ``entitled_by_account`` to ``True``
          and clears ``last_error``. So a once-broken command that starts
          working again (e.g. after subscription renewal) re-appears
          without a HA restart.
        - **Failure** → ``classify_command_failure(err)`` derives a
          ``CommandFailureReason`` from the body content (spin_error,
          subscription, entitlement keywords) plus HTTP status, and
          ``record_command_failure(vin, method, reason)`` updates the
          ``FeatureState`` flags accordingly. The exception still
          propagates so HA shows the user a service-call error — auto-
          classification is purely additive bookkeeping.

        v1.13.0 (#63 Phase 2) — wraps every command in a per-VIN
        per-command-class asyncio.Lock with 60s timeout. Prevents
        double-click storms from generating overlapping API calls (which
        the CARIAD backend rate-limits and frequently rejects with 429
        once they pile up).
        """
        if self._cariad_client is None:
            _LOGGER.error("VAG Connect: no CARIAD client — cannot execute %s", method)
            return
        # v1.13.0 (#63 Phase 2) — acquire per-VIN per-class lock.
        # Different classes (lock / climate / charging / etc.) can run
        # in parallel; same-class commands serialize. asyncio.timeout
        # (Python 3.11+) prevents deadlock if a hung command never
        # releases the lock — after 60s we proceed anyway.
        cmd_class = self._COMMAND_CLASS.get(method, method)
        lock = self._get_command_lock(vin, cmd_class)
        try:
            async with asyncio.timeout(_COMMAND_LOCK_TIMEOUT):
                async with lock:
                    await self._dispatch_cmd_locked(vin, method, **kwargs)
        except TimeoutError:
            _LOGGER.warning(
                "VAG Connect: %s(%s) lock timeout (%ss) — proceeding without lock",
                method, mask_vin(vin), _COMMAND_LOCK_TIMEOUT,
            )
            await self._dispatch_cmd_locked(vin, method, **kwargs)

    async def _dispatch_cmd_locked(self, vin: str, method: str, **kwargs: Any) -> None:
        """Inner dispatch — assumes per-VIN-per-class lock already held.

        Extracted so the lock-with-timeout wrapper in ``_cariad_cmd``
        stays readable. Same try/except as v1.9.1 + Phase 2 + v1.10.1
        parse-guard pipeline.
        """
        try:
            fn = getattr(self._cariad_client, method)
            await fn(vin, **kwargs)
            await self.async_request_refresh()
            try:
                self.record_command_success(vin, method)
            except Exception:  # noqa: BLE001
                pass  # bookkeeping must never affect command outcome
            _LOGGER.debug("VAG Connect: %s(%s) OK", method, mask_vin(vin))
        except Exception as err:  # noqa: BLE001
            from .cariad.exceptions import classify_command_failure  # noqa: PLC0415

            try:
                reason = classify_command_failure(err)
                self.record_command_failure(vin, method, reason)
                _LOGGER.info(
                    "VAG Connect: %s(%s) classified as %s",
                    method, mask_vin(vin), reason.value,
                )
            except Exception:  # noqa: BLE001
                pass
            _LOGGER.error("VAG Connect: %s(%s) failed: %s", method, mask_vin(vin), err)
            # v2.18.0 (#659) — surface the failure instead of letting the raw
            # APIError escape. HA doesn't know our exception types, so it logged
            # "Unexpected exception" and showed the user a Python traceback for
            # pressing a button; a reporter's log caught it verbatim. We already
            # classified the failure one line up — the least we can do is say so.
            #
            # Deliberately narrow. Only a backend REFUSAL becomes a user-facing
            # error:
            # - HomeAssistantError subclasses (our own pre-flight guards) already
            #   render cleanly and carry a translation key — pass them through.
            # - APIError is the car saying no. That belongs in front of the user.
            # - Anything else is OUR bug (a TypeError, a bad assumption). Those
            #   must keep bubbling as a traceback: wrapping them would disguise
            #   a programming error as a normal command failure and we'd never
            #   hear about it.
            from .cariad.exceptions import APIError  # noqa: PLC0415

            if isinstance(err, HomeAssistantError) or not isinstance(err, APIError):
                raise
            # v2.20.0 (#752) — if the vehicle's own capabilities document
            # explains WHY this command is gated (subscription inactive, car
            # doesn't offer it, T&C pending, …), append that so the user gets an
            # actionable reason instead of a bare backend 404. Purely additive:
            # any failure in the lookup leaves the original message untouched.
            # Only enrich when the failure actually classifies as a
            # capability/entitlement gate — otherwise a stale cached limitation
            # could be misattributed to a transient failure (e.g. the car is
            # briefly offline while the cached caps still say licenseExpired).
            msg = str(err)
            try:
                from .cariad.exceptions import (  # noqa: PLC0415
                    CommandFailureReason,
                    classify_command_failure,
                )

                if classify_command_failure(err) in (
                    CommandFailureReason.MISSING_CAPABILITY,
                    CommandFailureReason.NOT_ENTITLED,
                    CommandFailureReason.SUBSCRIPTION_EXPIRED,
                ):
                    gate = self.command_gating_reason(vin, method)
                    if gate is not None:
                        msg = f"{msg} — {gate[1]}"
            except Exception:  # noqa: BLE001
                pass  # enrichment must never change the command outcome
            raise HomeAssistantError(msg) from err

    async def async_set_charge_mode(self, vin: str, mode: str) -> None:
        """Set charging mode (MANUAL / TIMER / PREFERRED_CHARGING_TIMES)."""
        await self._cariad_cmd(vin, "command_set_charge_mode", mode=mode)

    async def async_set_min_soc(self, vin: str, min_soc: int) -> None:
        """Set minimum SoC for PHEV departure timer."""
        await self._cariad_cmd(vin, "command_set_min_soc", min_soc=min_soc)

    async def async_set_max_charge_current(self, vin: str, ampere: int) -> None:
        """Set max AC charge current in Amperes.

        v1.12.0 (#91 follow-up) — actual API call now wired (was raise
        ServiceValidationError pre-1.12.0 because the CARIAD command
        didn't exist). Goes through ``_cariad_cmd`` so v1.10.1 parse-
        guard + v1.9.1 FeatureState auto-recording apply.
        """
        await self._cariad_cmd(vin, "command_set_max_charge_current", ampere=ampere)

    async def async_start_window_heating(self, vin: str) -> None:
        # v1.11.1 (3B-Part-3) — optimistic UI for window heating switch.
        await self._cariad_cmd_optimistic(
            vin, "command_start_window_heating",
            optimistic={"window_heating_front": True, "window_heating_back": True},
        )

    async def async_stop_window_heating(self, vin: str) -> None:
        # v1.11.1 (3B-Part-3) — optimistic UI.
        await self._cariad_cmd_optimistic(
            vin, "command_stop_window_heating",
            optimistic={"window_heating_front": False, "window_heating_back": False},
        )

    async def async_wake_vehicle(self, vin: str) -> None:
        # v1.12.0 (#55) — wake_count_today counter + soft cap.
        #
        # The vehicle limits remote wake-ups per day (typically 3-5,
        # depending on backend) to protect the 12V battery. Once
        # exceeded the car silently ignores wake requests until midnight.
        # Pre-1.12.0 we polled blindly; now:
        #
        # 1. Track per-VIN wake count today (UTC midnight reset)
        # 2. Soft-cap at ``_WAKE_BUDGET_PER_DAY`` (default 3) — raise
        #    ServiceValidationError before hitting the API to spare a
        #    pointless wake attempt that would just fail
        # 3. Sensor ``wake_count_today`` surfaces the count for users +
        #    automations to budget
        #
        # Hard cap is conservative — users who want 5 can override via
        # service call directly (this method only protects automations
        # from runaway loops). The "max 3/day" mirrors what upstream
        # CC-* maintainers documented for the underlying backend limits.
        from datetime import datetime, timezone  # noqa: PLC0415

        now = datetime.now(tz=timezone.utc)
        today = now.date()
        # v1.13.0 (#63 Phase 3) — 5-minute anti-double-click cooldown
        # per VIN. Catches "user pressed wake button twice quickly" or
        # automation-bug repeat triggers BEFORE incrementing the daily
        # budget. In-memory only (restart resets — that's fine, restart
        # is intentional).
        # v1.25.0 PR-D: state moved to ``self._dispatcher`` (CommandDispatcher).
        last_at = self._ensure_dispatcher()._wake_last_at.get(vin)
        if last_at is not None and (now - last_at) < _WAKE_COOLDOWN:
            remaining_s = int((_WAKE_COOLDOWN - (now - last_at)).total_seconds())
            _LOGGER.warning(
                "VAG Connect: wake cooldown active for %s (%ds remaining). "
                "Last wake at %s. Refusing to spare 12V battery.",
                mask_vin(vin), remaining_s, last_at.isoformat(timespec="seconds"),
            )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="wake_cooldown_active",
                translation_placeholders={
                    "remaining_s": str(remaining_s),
                    "cooldown_min": str(int(_WAKE_COOLDOWN.total_seconds() // 60)),
                },
            )

        if not hasattr(self, "_wake_counts"):
            self._wake_counts: dict[str, tuple[Any, int]] = {}
        last_date, count = self._wake_counts.get(vin, (today, 0))
        if last_date != today:
            count = 0
            last_date = today
        if count >= _WAKE_BUDGET_PER_DAY:
            _LOGGER.warning(
                "VAG Connect: wake budget exhausted for %s (%d/%d today). "
                "Refusing further wake calls until midnight UTC to protect "
                "the 12V battery. See sensor.wake_count_today.",
                mask_vin(vin), count, _WAKE_BUDGET_PER_DAY,
            )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="wake_budget_exhausted",
                translation_placeholders={
                    "count": str(count),
                    "budget": str(_WAKE_BUDGET_PER_DAY),
                },
            )
        # Increment optimistically — if the API call fails we DON'T
        # decrement (the wake-attempt itself counted from the backend's
        # perspective, e.g. it still got logged + may still have woken
        # the modem partially).
        count += 1
        self._wake_counts[vin] = (today, count)
        # v1.13.0 (#63 Phase 3) — record cooldown timestamp.
        # v1.25.0 PR-D: state moved to dispatcher.
        self._ensure_dispatcher()._wake_last_at[vin] = now
        # Push count into vehicle data so the sensor sees it on next read.
        with self._vehicles_lock:
            current = self.vehicles.get(vin)
            if isinstance(current, dict):
                current["wake_count_today"] = count
        try:
            self.async_set_updated_data(dict(self.vehicles))
        except Exception:  # noqa: BLE001
            pass
        await self._cariad_cmd(vin, "command_wake")

