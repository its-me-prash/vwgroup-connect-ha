# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BRAND,
    CONF_ENABLE_PUSH_AUDI_VW,
    CONF_ENABLE_PUSH_FCM,
    CONF_ENABLE_PUSH_MQTT,
    CONF_ENABLE_REVERSE_GEOCODING,
    CONF_FORCE_PPE_CLIMATE,
    CONF_PASSWORD,
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
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
from .cariad._util import mask_vin
from .cariad.exceptions import CommandFailureReason, CommandProfile
from .cariad.models import VehicleData

_LOGGER = logging.getLogger(__name__)

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
# what tillsteinbach CC-* maintainers documented as safe for their
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
    audi_connect_ha audi_services.py + audiconnectpy + ioBroker/vw-connect)
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
    if isinstance(current, dict):
        name = current.get("name")
        if isinstance(name, str):
            out["active_charging_profile_name"] = name
        target = current.get("targetStateOfChargeInPercent")
        if isinstance(target, (int, float)):
            out["active_charging_profile_target_soc_pct"] = int(target)
        nxt = current.get("nextChargingTime")
        if isinstance(nxt, str) and nxt:
            out["next_charging_time"] = nxt
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
    """

    supported_by_vehicle: bool | None = None
    entitled_by_account: bool | None = None
    available_now: bool | None = None
    last_error: CommandFailureReason | None = None
    last_error_at: datetime | None = None


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

        session = async_get_clientsession(self.hass)
        self._cariad_client = CariadClientFactory.create(
            brand, session, username, password, spin,
            ola_app_version_override=ola_app_v,
            ola_user_agent_override=ola_ua,
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
        if persisted is not None:
            self._cariad_client.set_persisted_tokens(persisted)
        # Fire-and-forget save callback — never blocks API path.
        self._cariad_client.on_tokens_changed = self._token_storage.save

        try:
            # If persisted tokens were loaded successfully, the next
            # API call will use them directly; the 401 path triggers
            # _refresh_tokens which writes back. We still call
            # authenticate() if NO persisted tokens exist (first setup,
            # storage cleared, or version mismatch).
            if persisted is None:
                await self._cariad_client.authenticate()
            else:
                _LOGGER.debug(
                    "VAG Connect: using persisted IDK tokens for %s "
                    "— skipping fresh login",
                    brand,
                )
            vins = await self._cariad_client.get_vehicles()
            if not vins:
                return False

            # Fetch status for all vehicles
            results = await asyncio.gather(
                *[self._cariad_client.get_status(vin) for vin in vins],
                return_exceptions=True,
            )

            with self._vehicles_lock:
                for vin, result in zip(vins, results):
                    if isinstance(result, Exception):
                        _LOGGER.warning("Could not fetch status for %s: %s", mask_vin(vin), result)
                        if hasattr(self, "vehicle_success"):
                            self.vehicle_success[vin] = False
                        continue
                    if isinstance(result, VehicleData):
                        data = result.to_dict()
                        data["_client"] = self._cariad_client
                        self.vehicles[vin] = await self._enrich(data)
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
        except AuthenticationError as err:
            raise ValueError("invalid_credentials") from err
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("VAG Connect setup failed: %s", err)
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

    async def _poll_loop(self) -> None:
        """Background polling loop — runs independently of HA scheduler.

        Re-reads scan_interval from entry.options on every iteration so that
        Options-Flow changes take effect without a full integration reload.

        Nightly reduction (22:00–05:00): doubles the polling interval to reduce
        API calls and avoid rate limits during low-activity hours.
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
                        try:
                            record_error(
                                self.error_buffer,
                                exception=result,
                                brand=self.entry.data.get(CONF_BRAND, ""),
                                vin=vin,
                                model_year=self.vehicles.get(vin, {}).get("model_year"),
                                firmware=self.vehicles.get(vin, {}).get("firmware_version"),
                                endpoint="get_status",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    elif isinstance(result, VehicleData):
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
                                    model_year=self.vehicles.get(vin, {}).get("model_year"),
                                    firmware=self.vehicles.get(vin, {}).get("firmware_version"),
                                    endpoint="parse",
                                )
                            except Exception:  # noqa: BLE001
                                pass
                            continue
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
                            self._scan_for_unexpected_keys(vin)
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
                # v1.9.0 — Refresh the two reporter repair issues. Cheap to
                # call: ``ensure_*_issue`` deletes when empty and updates
                # in-place when the IDs already exist.
                self._refresh_reporter_issues()
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
            except Exception as err:  # noqa: BLE001
                # Auth failure that survived the client's refresh-then-relogin
                # fallback means the credentials are stale. Trigger HA reauth.
                from .cariad.exceptions import AuthenticationError  # noqa: PLC0415
                if isinstance(err, AuthenticationError):
                    self._trigger_reauth(str(err) or type(err).__name__)
                    await self._async_push_update({}, success=False)
                    return
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

        All three push manager implementations are currently SCAFFOLDING
        (stub ``_connect_and_listen``) — wiring the lifecycle now means
        the moment a tester confirms FCM keys / MQTT broker auth the
        live activation lands behind a single inner-method change with
        zero coordinator-side refactor.
        """
        options = dict(getattr(self.entry, "options", {}) or {})
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
            """Coordinator-side push callback — refresh the affected VIN."""
            _LOGGER.debug(
                "VAG push: event vin=***%s type=%s — requesting refresh",
                (event.vin or "??????")[-6:],
                event.event_type,
            )
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

    def _scan_for_unexpected_keys(self, vin: str) -> None:
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

    def _refresh_reporter_issues(self) -> None:
        """Recreate / delete the two HA repair issues from current buffers.

        Called after every poll cycle. The pipeline functions handle the
        empty case (delete the issue) and the populated case (create or
        refresh in-place — registry de-dupes by issue_id).

        Wrapped here so a registry hiccup can't take down the poll loop.
        """
        brand = self.entry.data.get(CONF_BRAND, "")
        entry_id = getattr(self.entry, "entry_id", "") or ""

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
        """
        state = self.get_feature_state(vin, command)
        state.last_error = reason
        state.last_error_at = datetime.now(tz=timezone.utc)
        if reason is CommandFailureReason.MISSING_CAPABILITY:
            state.supported_by_vehicle = False
        elif reason in (
            CommandFailureReason.SUBSCRIPTION_EXPIRED,
            CommandFailureReason.NOT_ENTITLED,
        ):
            state.entitled_by_account = False

    def record_command_success(self, vin: str, command: str) -> None:
        """Mark a command as known-good for *vin*."""
        state = self.get_feature_state(vin, command)
        state.supported_by_vehicle = True
        state.entitled_by_account = True
        state.available_now = True
        state.last_error = None
        state.last_error_at = None

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
        (missing capability, expired subscription, not entitled). The
        2A foundation populated ``FeatureState`` but no entity yet read
        from it; Phase 2 wires the read side.

        Conservative: returns ``True`` *only* when at least one of the
        explicit "definitive no" flags is set. Transient backend errors
        leave both flags as ``None`` so the entity stays visible.
        """
        states = getattr(self, "feature_states", None)
        if not states:
            return False
        state = states.get(vin, {}).get(command)
        if state is None:
            return False
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

    async def refresh_capabilities(self, vin: str, force: bool = False) -> None:
        """Best-effort fetch of the per-VIN capabilities document.

        Failure is logged at debug and never blocks setup or polling. The
        cache stays as-is on error so we don't lose previously known data.
        Only SEAT/CUPRA's OLA endpoint is implemented in this PR; other
        brands return silently from the client side.
        """
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
    _CHARGING_PROFILES_BRANDS = ("skoda",)  # mysmob only — CARIAD/OLA TBD

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
                    self.entry.data.get("username", ""),
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
                    self.entry.data.get("username", ""),
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
        ``WulfgarW/homeassistant-pycupra`` v0.2.14 ("if a previously-
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
        options = getattr(self.entry, "options", None) or {}
        data = getattr(self.entry, "data", None) or {}
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
            with self._vehicles_lock:
                for vin, result in zip(vins, results):
                    if isinstance(result, Exception):
                        _LOGGER.debug("Refresh failed for %s: %s", mask_vin(vin), result)
                        continue
                    if isinstance(result, VehicleData):
                        data = result.to_dict()
                        data["_client"] = self._cariad_client
                        self.vehicles[vin] = await self._enrich(data)
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
        options = getattr(self.entry, "options", None) or {}
        data = getattr(self.entry, "data", None) or {}
        spin = ""
        if isinstance(options, dict):
            spin = str(options.get(CONF_SPIN) or "")
        if not spin and isinstance(data, dict):
            spin = str(data.get(CONF_SPIN) or "")
        if brand in ("seat", "cupra") and not spin:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="spin_required",
            )
        # v1.11.1 (3B-Part-3) — optimistic UI: assume the lock will succeed
        # so the HA card flips to "locked" immediately. Reverts on failure.
        cmd_kwargs = {"spin": spin} if (brand in ("audi", "volkswagen") and spin) else {}
        await self._cariad_cmd_optimistic(
            vin, "command_lock",
            optimistic={"doors_locked": True},
            **cmd_kwargs,
        )

    async def async_unlock(self, vin: str) -> None:
        # Prefer options (Options Flow) over data (initial config). Use real
        # dict semantics so MagicMock values in tests don't accidentally pass
        # the truthiness check.
        options = getattr(self.entry, "options", None) or {}
        data = getattr(self.entry, "data", None) or {}
        spin = ""
        if isinstance(options, dict):
            spin = str(options.get(CONF_SPIN) or "")
        if not spin and isinstance(data, dict):
            spin = str(data.get(CONF_SPIN) or "")
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
            options = getattr(self.entry, "options", None) or {}
            data = getattr(self.entry, "data", None) or {}
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
        # ⚠️ [Inference] We pass the **vehicle's** last-known position
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

    async def async_set_climatisation_temperature(self, vin: str, temp_c: float) -> None:
        await self._cariad_cmd(vin, "command_set_climate_temperature", temp_c=temp_c)

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

    async def async_start_aux_heating(self, vin: str) -> None:
        """v1.17.1 — SEAT/CUPRA Webasto auxiliary heating start.

        Pre-flight S-PIN check (analog to ``async_unlock``) so HA shows
        a clean translation key rather than a low-level SpinError trace.
        """
        spin = self._spin_from_entry()
        if not spin:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="spin_required",
            )
        await self._cariad_cmd(vin, "command_start_aux_heating", spin=spin)

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

    def _spin_from_entry(self) -> str:
        """Return the configured S-PIN preferring Options over Data."""
        options = getattr(self.entry, "options", None) or {}
        data = getattr(self.entry, "data", None) or {}
        if isinstance(options, dict):
            spin = str(options.get(CONF_SPIN) or "")
            if spin:
                return spin
        if isinstance(data, dict):
            return str(data.get(CONF_SPIN) or "")
        return ""

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

    def is_read_only(self) -> bool:
        """v1.12.0 (#63) — return True if user enabled Read-only Mode.

        When True, command-bound entity platforms (lock, switch, button,
        climate, number) skip entity creation entirely. Sensor +
        binary_sensor + device_tracker platforms create normal status
        entities. Service calls that would send commands raise
        ServiceValidationError before reaching the API.

        Lookup order: options (Options Flow) > data (initial config) >
        False default. Pattern matches the existing reverse-geocoding
        opt-in (v1.8.0).
        """
        options = getattr(self.entry, "options", None) or {}
        data = getattr(self.entry, "data", None) or {}
        return (
            (isinstance(options, dict) and options.get(CONF_READ_ONLY) is True)
            or (isinstance(data, dict) and data.get(CONF_READ_ONLY) is True)
        )

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
        try:
            self.async_set_updated_data(dict(self.vehicles))
        except Exception:  # noqa: BLE001
            pass

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
        "command_start_charging": "charging",
        "command_stop_charging": "charging",
        "command_set_target_soc": "charging",
        "command_set_charge_mode": "charging",
        "command_set_min_soc": "charging",
        "command_set_max_charge_current": "charging",
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
            raise

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
        # from runaway loops). The "max 3/day" mirrors what tillsteinbach
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

