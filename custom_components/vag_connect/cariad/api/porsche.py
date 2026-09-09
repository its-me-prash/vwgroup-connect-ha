# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche Connect API client — api.ppa.porsche.com.

Endpoints from CJNE/pyporscheconnectapi (Apache-2.0).
Clean-room reimplementation using aiohttp.
Source: https://github.com/CJNE/pyporscheconnectapi
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .._util import drop_odometer_sentinel
from .._util import mask_vin as _mask_vin
from ..auth.porsche import PorscheAuth
from ..exceptions import APIError, AuthenticationError, SpinError, TokenExpiredError, VehicleCommandError
from ..models import VehicleData, TokenSet

_LOGGER = logging.getLogger(__name__)

_API_BASE   = "https://api.ppa.porsche.com"
_X_CLIENT   = "41843fb4-691d-4970-85c7-2673e8ecef40"
_USER_AGENT = "My Porsche/2.1.0 (iPhone; iOS 17.0; Scale/3.00)"

# v1.25.0 PR-B: storm-protection constants (mirror of base.py)
_REFRESH_MAX_PER_HOUR = 3
_REFRESH_WINDOW_S = 3600

# b19 (CJNE-comparison #3) — bounded command-status poll. CJNE polls up to
# 240s for a terminal PERFORMED/ERROR state; that is too long to block a HA
# service call on. We poll for a much shorter window: an ERROR within it is
# still caught (the whole point — a rejected command no longer looks
# identical to a successful one), but a command still pending when the
# window closes is left for the next coordinator poll instead of blocking.
_COMMAND_POLL_INTERVAL_S = 2
_COMMAND_POLL_TIMEOUT_S = 20

# b19 (CJNE-comparison #13) — widened from a 17-key subset to CJNE's fuller
# set (const.py::MEASUREMENTS, Apache-2.0), so windows/parking-brake/alarm/
# convertible-top/charging-profile fields become available to parse. Not
# every key maps to a VehicleData field yet (see get_status) — requesting
# them is cheap and unblocks adding entities later without another
# request-shape change. NOT LIVE-VERIFIED beyond the fields already parsed
# before b19 — a vehicle owner's report is what confirms the rest actually
# come back populated.
#
# b20 (2026-09-08, full androguard enum dump of the real
# `de.porsche.app.api.connect.vehicledata.model.MeasurementType` class —
# vag-connect-porsche-full-endpoint-inventory-2026-09-08.md) — TWO
# corrections against that ground truth:
#   1. "CHARGING_STATE" was never a real measurement key (not in the 86/87
#      -member real enum, not in CJNE's own list either, and this project
#      never actually parsed it into anything — `charging_state` below has
#      always come from `CHARGING_SUMMARY.status`). Dropped — it was inert.
#   2. "TIRE_PRESSURE" (a single aggregate key) does not exist. The real
#      enum has four separate keys instead — see the TIRE_PRESSURE_* entries
#      below and the rewritten TPMS parsing in get_status. This is very
#      likely why TPMS sensors have been reporting nothing: the previous key
#      was requesting a measurement that doesn't exist.
# b20 follow-up (2026-09-08) — the 29 other genuinely-new keys that dump
# surfaced (+ CHARGING_SESSION_HISTORY, ROW-only) ARE requested below even
# though none of them are parsed into a VehicleData field yet. Requesting
# an unparsed key is zero-risk (this project's parser only ever reads keys
# it explicitly knows about; anything else just sits unused in the raw
# response) and it populates ``last_raw_responses`` (the Vehicle Data
# Scout capture) with the real payload shape — the fastest path to
# eventually building a sensor for any of these is a real user's
# diagnostics export showing what actually comes back, not guessing.
# Deliberately still NOT requested:
#   - MDK_ACTIVATION_STATE/MDK_CARD_STATE/MDK_PAIRING_PASSWORD/
#     MDK_PAIRING_STATE (Mobile Digital Key pairing) — MDK_PAIRING_PASSWORD
#     in particular plausibly carries a live pairing credential; pulling
#     that into diagnostics exports for zero HA benefit is a privacy risk
#     this project's own redaction discipline argues against, not just
#     "low relevance."
#   - VTS_CERTIFICATE_LIST/VTS_CONFIGURATION (theft-tracking-system
#     certs/config) and GUIDANCE_SETTINGS (in-car nav UI settings) — pure
#     provisioning/app-UI data, genuinely nothing for a wider request to
#     set up here even at the raw-capture level.
# See the inventory doc for the full triage.
_MEASUREMENTS = (
    "BATTERY_LEVEL", "E_RANGE", "FUEL_LEVEL", "FUEL_RESERVE", "MILEAGE",
    "CHARGING_SUMMARY", "CHARGING_RATE", "CHARGING_SETTINGS",
    "CHARGING_PROFILES", "CLIMATIZER_STATE", "HVAC_STATE", "HEATING_STATE",
    "GPS_LOCATION", "LOCK_STATE_VEHICLE", "ALARM_STATE", "THEFT_STATE",
    "PARKING_BRAKE", "PARKING_LIGHT", "GLOBAL_PRIVACY_MODE",
    "REMOTE_ACCESS_AUTHORIZATION", "DEPARTURES", "TIMERS",
    "OPEN_STATE_DOOR_FRONT_LEFT", "OPEN_STATE_DOOR_FRONT_RIGHT",
    "OPEN_STATE_DOOR_REAR_LEFT", "OPEN_STATE_DOOR_REAR_RIGHT",
    "OPEN_STATE_LID_FRONT", "OPEN_STATE_LID_REAR", "OPEN_STATE_SUNROOF",
    "OPEN_STATE_SUNROOF_REAR", "OPEN_STATE_SPOILER", "OPEN_STATE_TOP",
    "OPEN_STATE_SERVICE_FLAP", "OPEN_STATE_CHARGE_FLAP_LEFT",
    "OPEN_STATE_CHARGE_FLAP_RIGHT",
    "OPEN_STATE_WINDOW_FRONT_LEFT", "OPEN_STATE_WINDOW_FRONT_RIGHT",
    "OPEN_STATE_WINDOW_REAR_LEFT", "OPEN_STATE_WINDOW_REAR_RIGHT",
    "MAIN_SERVICE_RANGE", "MAIN_SERVICE_TIME", "OIL_SERVICE_RANGE",
    "OIL_SERVICE_TIME", "INTERMEDIATE_SERVICE_RANGE",
    "INTERMEDIATE_SERVICE_TIME", "SERVICE_PREDICTIONS",
    "OIL_LEVEL_CURRENT", "OIL_LEVEL_MAX", "OIL_LEVEL_MIN_WARNING",
    "TIRE_PRESSURE_FRONT_LEFT", "TIRE_PRESSURE_FRONT_RIGHT",
    "TIRE_PRESSURE_REAR_LEFT", "TIRE_PRESSURE_REAR_RIGHT",
    # b20 follow-up — requested for Scout raw-capture only, not parsed yet.
    "BATTERY_CONDITION", "BEM_LEVEL", "BIDIRECTIONAL_CHARGING",
    "CAR_ALARMS_HISTORY", "CHARGING_SESSION", "CHARGING_SESSION_HISTORY",
    "CONNECT_CONTRACT", "DESTINATIONS", "DIRECT_CHARGING",
    "GLOBAL_TIMESTAMP", "HVAC_SUMMARY", "INSTRUMENT_CLUSTER_ALERTS",
    "LOCATION_ALARMS", "LOCATION_ALARMS_HISTORY", "OTA_CONSENT_STATUS",
    "OTA_UPDATE_DETAILS", "SPEED_ALARMS", "SPEED_ALARMS_HISTORY",
    "TIMEZONE", "TRIP_STATISTICS_MONTHLY_REPORT", "VALET_ALARM",
    "VALET_ALARM_HISTORY",
)


# ── b23 (competitor-triage ADOPT #1) — wire already-fetched `mf` fields ──────
# porsche.py already REQUESTS the full mf set above but ``get_status`` dropped
# the windows / spoiler / charge-flap / service-flap / parking-brake / parking-
# light / oil-level / service-time measurements. The helpers below wire them
# onto VehicleData fields that already drive entities for other brands.
#
# INNER-VALUE SHAPES — GROUNDED against a REAL Taycan mf capture (a public CJNE
# ha-porscheconnect issue paste, corroborated across every measurement in it and
# matching CJNE's own parsing). The open-state family is ``{"isOpen": bool}``
# (an earlier revision guessed an ``openState`` STRING from the androguard enum
# names — wrong; the enum dump gives the KEYS, not the value field names), and
# parking brake/light are ``{"isOn": bool}``. Service-time is ``{"days": int}``.
# Only OIL_LEVEL_CURRENT was disabled on that capture, so its inner shape stays
# unverified behind the defensive numeric reader. Every helper fail-softs to
# ``None`` so a not-yet-seen shape degrades to "unknown", never a crash or a
# wrong reading.


def _mf_is_open(value: Any) -> bool | None:
    """OPEN_STATE_* → bool (True == open). Real shape ``{"isOpen": bool}``."""
    if isinstance(value, dict):
        is_open = value.get("isOpen")
        if isinstance(is_open, bool):
            return is_open
    return None


def _mf_is_on(value: Any) -> bool | None:
    """PARKING_BRAKE / PARKING_LIGHT → bool. Real shape ``{"isOn": bool}``."""
    if isinstance(value, dict):
        is_on = value.get("isOn")
        if isinstance(is_on, bool):
            return is_on
    return None


def _mf_number(value: Any, candidate_keys: tuple[str, ...]) -> float | None:
    """Fail-soft numeric from a measurement value dict (or a bare number).

    ``bool`` is rejected (it's an ``int`` subclass but never a real reading);
    numeric-as-string ("80", "5.5") is accepted. ``None`` when nothing usable.
    """
    src: Any = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        src = value
    elif isinstance(value, dict):
        for key in candidate_keys:
            raw = value.get(key)
            if isinstance(raw, bool):
                continue
            if isinstance(raw, (int, float)):
                src = raw
                break
            if isinstance(raw, str):
                try:
                    src = float(raw)
                    break
                except ValueError:
                    continue
    if isinstance(src, (int, float)) and not isinstance(src, bool):
        return float(src)
    return None


class PorscheClient:
    """Porsche Connect API client.

    Uses Auth0 PKCE (identity.porsche.com) — completely separate from IDK/CARIAD.
    Not a subclass of CariadBaseClient because the auth system is different.
    """

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        self._session = session
        self._email   = email
        self._password = password
        self._spin    = spin
        self._tokens: TokenSet | None = None
        self._auth = PorscheAuth(session)
        # v1.25.0 PR-B: refresh-storm protection state
        self._refresh_lock: asyncio.Lock | None = None
        self._refresh_history: list[float] = []
        # v1.25.0 PR-B: rate-limit header capture (read by coordinator
        # for the requests_remaining_today sensor — matches CariadBase
        # surface so coordinator code stays brand-agnostic).
        self.last_rate_limit_remaining: int | None = None
        self.last_rate_limit_limit: int | None = None
        self.last_rate_limit_reset_at: int | None = None
        # v3.0.0 — raw responses for the Vehicle Data Scout + diagnostics export,
        # so a Porsche reporter's "Download diagnostics" surfaces its API shape
        # for grounding once the read path is unblocked. Redacted at export time.
        self.last_raw_responses: dict[str, Any] = {}

    async def authenticate(
        self,
        mfa_code: str | None = None,  # noqa: ARG002 — Porsche has no MFA on this path
        *,
        captcha_code: str | None = None,
        resume_state: str | None = None,
        resume_verifier: str | None = None,
    ) -> None:
        """Auth0 PKCE login.

        ``captcha_code``/``resume_state``/``resume_verifier`` resume a login
        that was interrupted by :class:`PorscheCaptchaRequiredError` — see
        ``PorscheAuth.authenticate`` for why the state/verifier must be the
        ones captured when the captcha was first raised, not fresh ones.
        """
        self._tokens = await self._auth.authenticate(
            self._email, self._password,
            captcha_code=captcha_code,
            resume_state=resume_state,
            resume_verifier=resume_verifier,
        )
        _LOGGER.debug("Porsche Connect auth complete")

    async def get_vehicles(self) -> list[str]:
        """Return list of VINs from Porsche Connect garage."""
        data = await self._get(f"{_API_BASE}/app/connect/v1/vehicles")
        vins = []
        for v in data if isinstance(data, list) else []:
            vin = v.get("vin") or v.get("VIN")
            if vin:
                vins.append(vin)
                _LOGGER.debug("Porsche: found VIN %s model=%s", _mask_vin(vin), v.get("modelName"))
        return vins

    async def get_status(self, vin: str) -> VehicleData:
        """Fetch full vehicle status from Porsche API.

        b19 (CJNE-comparison #1/#2, corrected 2026-09-07): switched from two
        separate calls (a bare ``/vehicles/{vin}`` for meta + a
        ``/vehicles/{vin}/measurements?fields=...`` for measurements) to
        CJNE's live-proven single-call shape: one GET on ``/vehicles/{vin}``
        with repeated ``mf=`` query params (one per requested measurement
        key) plus a ``wakeUpJob`` UUID to force a live read rather than a
        cached one. The response carries both the base vehicle fields (vin,
        modelName, modelType, ...) and a top-level ``measurements`` array in
        the SAME payload — the previous two-call shape was never live-
        verified and may well have been hitting a non-existent sub-path.
        NOT LIVE-VERIFIED beyond the 2026-09-07 login test (which did not
        reach a vehicle) — this needs a real account with a car to confirm.
        """
        v = self._val
        d = VehicleData(vin=vin)

        params = [("mf", key) for key in _MEASUREMENTS]
        params.append(("wakeUpJob", str(uuid.uuid4())))
        try:
            overview = await self._get(
                f"{_API_BASE}/app/connect/v1/vehicles/{vin}", params=params,
            )
        except Exception as err:  # noqa: BLE001 — never crash a poll on one bad read
            _LOGGER.debug("Porsche get_status failed: %s", type(err).__name__)
            return d

        # v3.0.0 — capture the raw Porsche response for the Scout + diagnostics.
        if not hasattr(self, "last_raw_responses"):
            self.last_raw_responses = {}
        if isinstance(overview, dict):
            self.last_raw_responses["overview"] = overview

        if not isinstance(overview, dict):
            return d

        # ── Vehicle meta ─────────────────────────────────────────────────────
        d.model        = overview.get("modelName")
        d.model_year   = v(overview, "modelType", "year")
        d.manufacturer = "Porsche"
        engine = v(overview, "modelType", "engine", default="")
        d.is_electric    = engine == "BEV"
        d.is_hybrid      = engine == "PHEV"
        d.has_battery    = engine in ("BEV", "PHEV")
        d.has_combustion = engine in ("PHEV", "COMBUSTION")

        # ── Measurements ──────────────────────────────────────────────────────
        # CJNE only trusts entries whose own status says isEnabled (a disabled/
        # unsupported measurement can still appear in the array with a stale
        # or meaningless value) — mirror that filter.
        raw_measurements = overview.get("measurements")
        if isinstance(raw_measurements, list):
            m = {
                item["key"]: item.get("value", {})
                for item in raw_measurements
                if isinstance(item, dict)
                and item.get("key")
                and v(item, "status", "isEnabled", default=True)
            }

            d.battery_soc   = v(m, "BATTERY_LEVEL", "percent")
            # v2.2.1 Phase 8 PR #3 — split electric / combustion range
            # for Porsche cross-brand parity. Before this PR Porsche
            # only populated the aggregate `range_km` (or-fallback);
            # Skoda, VW EU, Audi, CUPRA, SEAT all expose per-source
            # split since v1.10.0+. Now Porsche EV (Taycan, Macan EV,
            # 911 Cayenne EV) + PHEV (Cayenne E-Hybrid, Panamera
            # E-Hybrid) join the parity.
            #
            # PPA measurement keys (verified per pcommit/iccarus +
            # porsche-connect-cli traces):
            # - E_RANGE.distance → battery-only range in km
            # - FUEL_LEVEL.distanceToEmpty → combustion-only range in km
            #
            # The existing aggregate range_km keeps its or-fallback
            # for back-compat (Porsche users on this sensor today
            # see no change).
            electric_range = v(m, "E_RANGE", "distance")
            combustion_range = v(m, "FUEL_LEVEL", "distanceToEmpty")
            if isinstance(electric_range, (int, float)):
                d.electric_range_km = int(electric_range)
            if isinstance(combustion_range, (int, float)):
                d.combustion_range_km = int(combustion_range)
            d.range_km      = electric_range or combustion_range
            d.fuel_level    = v(m, "FUEL_LEVEL", "percent")
            d.odometer_km   = drop_odometer_sentinel(v(m, "MILEAGE", "mileage"))

            # Charging
            ch = m.get("CHARGING_SUMMARY", {})
            d.charging_state    = v(ch, "status")
            # v2.0.1 (#131 follow-up) — defensive parsing.
            if isinstance(d.charging_state, str):
                d.is_charging = d.charging_state.upper() in (
                    "CHARGING", "CHARGING_AC", "CHARGING_DC"
                )
            d.charging_power_kw = v(ch, "chargingPower")
            plug_state = v(ch, "plugState")
            if isinstance(plug_state, str):
                d.plug_connected = plug_state.upper() == "CONNECTED"
                d.plug_state = plug_state

            # b19 (CJNE-comparison #3.3) — target-SoC precedence chain ported
            # from CJNE's ``_update_vehicle_data`` (Apache-2.0): which field
            # actually carries the active target has been changing across
            # Porsche's live payloads within the last 8 days of CJNE's own
            # commit history (newer vehicles expose it directly on
            # CHARGING_SUMMARY; others need CHARGING_SETTINGS or the active
            # CHARGING_PROFILES entry). Checked defensively in both castings
            # CJNE's and this repo's code have each used (targetSoC/targetSoc)
            # since neither has been live-verified against a current payload.
            # NOT LIVE-VERIFIED.
            target_soc = v(ch, "targetSoC")
            if target_soc is None:
                target_soc = v(ch, "targetSoc")
            if target_soc is None and v(ch, "mode") == "PROFILE":
                target_soc = v(ch, "chargingProfile", "minSoC")
            settings = m.get("CHARGING_SETTINGS", {})
            if (
                target_soc is None
                and "DEPARTURES" in m
                and v(settings, "targetSoc") is not None
            ):
                target_soc = v(settings, "targetSoc")
            if (
                target_soc is None
                and "DEPARTURES" not in m
                and v(ch, "mode") == "DIRECT"
            ):
                target_soc = 100
            d.target_soc = target_soc

            # Lock — v2.0.1 (#131 follow-up): defensive parsing.
            # Only assign when the source is an actual string; otherwise
            # leave the dataclass default ``None`` so the entity stays
            # "unknown" instead of falsely reporting "Unlocked".
            lock = v(m, "LOCK_STATE_VEHICLE", "lockState")
            if isinstance(lock, str):
                d.doors_locked = lock.upper() == "LOCKED"

            # Doors — v2.0.1: only assign when at least one door
            # actually publishes its openState. PPA sometimes returns
            # the LOCK_STATE_VEHICLE block but skips the per-door blocks
            # for a few minutes after wake (observed against Taycan).
            door_states = [
                v(m, f"OPEN_STATE_DOOR_{pos}", "openState")
                for pos in ("FRONT_LEFT", "FRONT_RIGHT", "REAR_LEFT", "REAR_RIGHT")
            ]
            if any(isinstance(s, str) for s in door_states):
                d.doors_open = any(
                    isinstance(s, str) and s.upper() == "OPEN" for s in door_states
                )
            d.hood_open   = v(m, "OPEN_STATE_LID_FRONT",  "openState") == "OPEN"
            d.trunk_open  = v(m, "OPEN_STATE_LID_REAR",   "openState") == "OPEN"
            d.sunroof_open = v(m, "OPEN_STATE_SUNROOF",   "openState") == "OPEN"

            # Climate
            clim = m.get("CLIMATIZER_STATE", {})
            d.climatisation_state  = v(clim, "climatisationState")
            d.climatisation_active = d.climatisation_state not in (None, "OFF")

            # GPS
            gps = m.get("GPS_LOCATION", {})
            d.latitude  = v(gps, "latitude")
            d.longitude = v(gps, "longitude")

            # Service
            d.service_km    = v(m, "MAIN_SERVICE_RANGE", "distance")
            d.oil_service_km = v(m, "OIL_SERVICE_RANGE", "distance")

            # ── TPMS ───────────────────────────────────────────────────────
            # b20 (2026-09-08, androguard enum dump of the real
            # MeasurementType class) — CORRECTED. There is no aggregate
            # ``TIRE_PRESSURE`` key; the real app requests four separate
            # top-level measurement keys, one per corner
            # (``TIRE_PRESSURE_FRONT_LEFT`` etc., each with its own
            # ``TirePressureFrontLeftMeasurement`` model class). The v2.0.0
            # parsing below assumed a single aggregate dict keyed by corner
            # name, which was requesting a measurement key that doesn't
            # exist — very likely why TPMS has been silently empty.
            # NOT LIVE-VERIFIED: the per-corner KEYS are androguard-confirmed
            # real; the exact field names inside each one's value
            # (``currentPressure``/``warning``) are carried over unchanged
            # from the old aggregate shape as the best available guess — a
            # live capture is what confirms whether that inner shape moved
            # too when the key was split.
            def _corner_bar(key: str) -> float | None:
                raw = v(m, key, "currentPressure")
                if raw is None:
                    return None
                try:
                    n = float(raw)
                except (TypeError, ValueError):
                    return None
                # kPa heuristic: anything > 10 is kPa, divide by 100
                return round(n / 100.0, 2) if n > 10 else round(n, 2)
            d.tire_pressure_front_left_bar  = _corner_bar("TIRE_PRESSURE_FRONT_LEFT")
            d.tire_pressure_front_right_bar = _corner_bar("TIRE_PRESSURE_FRONT_RIGHT")
            d.tire_pressure_rear_left_bar   = _corner_bar("TIRE_PRESSURE_REAR_LEFT")
            d.tire_pressure_rear_right_bar  = _corner_bar("TIRE_PRESSURE_REAR_RIGHT")
            if any(
                b is not None for b in (
                    d.tire_pressure_front_left_bar, d.tire_pressure_front_right_bar,
                    d.tire_pressure_rear_left_bar, d.tire_pressure_rear_right_bar,
                )
            ):
                d.tire_pressure_warning = any(
                    bool(v(m, key, "warning"))
                    for key in (
                        "TIRE_PRESSURE_FRONT_LEFT", "TIRE_PRESSURE_FRONT_RIGHT",
                        "TIRE_PRESSURE_REAR_LEFT", "TIRE_PRESSURE_REAR_RIGHT",
                    )
                )

            # ── b23 (competitor-triage ADOPT #1) — already-fetched mf fields ──
            # These keys were requested all along (see ``_MEASUREMENTS``) but
            # the parser mapped none of them. Pure wiring onto VehicleData
            # fields that already drive entities for other brands; no new
            # request/auth. Inner shapes grounded on a real Taycan capture
            # (see the module helpers); OIL_LEVEL stays defensive (unverified).

            # Windows — individual + aggregate. Real shape {"isOpen": bool};
            # stored True == CLOSED (mirrors doors_individual / SEAT-CUPRA
            # windows_individual) so a WINDOW-device_class binary_sensor reads
            # open correctly.
            window_individual: dict[str, bool] = {}
            for key, pos in (
                ("OPEN_STATE_WINDOW_FRONT_LEFT", "frontLeft"),
                ("OPEN_STATE_WINDOW_FRONT_RIGHT", "frontRight"),
                ("OPEN_STATE_WINDOW_REAR_LEFT", "rearLeft"),
                ("OPEN_STATE_WINDOW_REAR_RIGHT", "rearRight"),
            ):
                is_open = _mf_is_open(m.get(key))
                if is_open is not None:
                    window_individual[pos] = not is_open
            if window_individual:
                d.windows_individual = window_individual
                d.windows_open = any(not closed for closed in window_individual.values())

            # Spoiler + service hatch (opening binary_sensors).
            spoiler = _mf_is_open(m.get("OPEN_STATE_SPOILER"))
            if spoiler is not None:
                d.spoiler_open = spoiler
            service_flap = _mf_is_open(m.get("OPEN_STATE_SERVICE_FLAP"))
            if service_flap is not None:
                d.service_hatch_open = service_flap

            # Charge-port flaps → the existing (string) plug-flap state fields.
            # Porsche dual-port cars (Taycan) have a LEFT and a RIGHT flap →
            # map LEFT→plug1, RIGHT→plug2 so both surface; a single-port car
            # leaves plug2 None (never a phantom). The measurement is a bool
            # ({"isOpen": ...}); render it as the "OPEN"/"CLOSED" string the
            # plug-flap sensors expect.
            for flap_key, flap_attr in (
                ("OPEN_STATE_CHARGE_FLAP_LEFT", "charging_plug1_flap_state"),
                ("OPEN_STATE_CHARGE_FLAP_RIGHT", "charging_plug2_flap_state"),
            ):
                flap_open = _mf_is_open(m.get(flap_key))
                if flap_open is not None:
                    setattr(d, flap_attr, "OPEN" if flap_open else "CLOSED")

            # Parking brake + parking light — real shape {"isOn": bool}.
            parking_brake = _mf_is_on(m.get("PARKING_BRAKE"))
            if parking_brake is not None:
                d.parking_brake_engaged = parking_brake
            parking_light = _mf_is_on(m.get("PARKING_LIGHT"))
            if parking_light is not None:
                d.parking_light = parking_light

            # Engine oil level → percent. OIL_LEVEL_CURRENT was DISABLED on the
            # grounding capture, so its inner shape is still unverified — keep a
            # defensive reader. OIL_LEVEL_CURRENT/_MAX/_MIN_WARNING is a triad,
            # so CURRENT may be an absolute value on a 0..MAX scale rather than a
            # bare percent — normalise against MAX when available and it isn't
            # itself a 0..100 percent. Only ever yields 0..100 or None.
            _oil_keys = ("percent", "percentage", "currentValue", "value",
                         "level", "current")
            oil_cur = _mf_number(m.get("OIL_LEVEL_CURRENT"), _oil_keys)
            oil_max = _mf_number(m.get("OIL_LEVEL_MAX"), _oil_keys + ("max", "maximum"))
            oil_pct: float | None = None
            if oil_cur is not None:
                if 0.0 < oil_cur <= 1.0:                       # ratio 0..1
                    oil_pct = oil_cur * 100.0
                elif oil_max is not None and 0 < oil_max != 100 and oil_cur <= oil_max:
                    oil_pct = oil_cur / oil_max * 100.0        # absolute on 0..max
                elif 0.0 <= oil_cur <= 100.0:                  # already a percent
                    oil_pct = oil_cur
            if oil_pct is not None and 0.0 <= oil_pct <= 100.0:
                d.oil_level_pct = int(round(oil_pct))

            # Service-time intervals → days-remaining ints. Mirrors the
            # *_SERVICE_RANGE→*_km mapping above: MAIN→service_due_in_days,
            # OIL→oil_service_due_in_days. Negative = overdue (allowed);
            # implausible magnitudes (a timestamp slipping into a day field)
            # are rejected rather than shipped as a nonsense sensor.
            for key, attr in (
                ("MAIN_SERVICE_TIME", "service_due_in_days"),
                ("OIL_SERVICE_TIME", "oil_service_due_in_days"),
            ):
                days = _mf_number(
                    m.get(key),
                    ("days", "remainingDays", "daysRemaining", "value", "time"),
                )
                if days is not None and -3650 <= days <= 3650:
                    setattr(d, attr, int(round(days)))

        # v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation.
        # Porsche PPA doesn't ship a direct `carType` enum — derive
        # from has_battery + has_combustion (already set above from
        # `VEHICLE.engine` BEV/PHEV/COMBUSTION). Never overwrites.
        from .._util import derive_car_type_if_missing  # noqa: PLC0415

        derive_car_type_if_missing(d)

        return d

    async def get_capabilities(self, vin: str) -> dict[str, Any]:  # noqa: ARG002
        """Still returns ``{}`` — but NOT because no endpoint exists.

        CORRECTION (b20, 2026-09-08, androguard disassembly of the real
        vehicle-connect service class,
        ``vag-connect-porsche-full-endpoint-inventory-2026-09-08.md`` §3.1/
        §3.2): this docstring used to claim "Porsche PPA does not expose a
        discrete capabilities endpoint" — that is WRONG. Two real
        capability-related surfaces exist: (1) the same
        ``GET /vehicles/{vin}`` overview call ``get_status`` already makes
        can also carry a ``cf=`` (command-flags) query param alongside
        ``mf=``/``wakeUpJob`` — the real app sends all three in one request;
        this project only ever sends ``mf=``+``wakeUpJob``. (2) A separate
        ``GET /v1/config/capabilities/defaults`` +
        ``/v1/config/capabilities/suggestions`` cluster exists too.

        Neither is wired up here yet: the response envelope for ``cf=``
        results and the exact shape of the capabilities-defaults/suggestions
        response were NOT captured in that pass (only that the endpoints
        exist) — implementing against a guessed response shape risks
        silently-wrong parsing, which is worse than the honest ``{}`` this
        already returns. Wiring either one up needs a live capture from a
        real account first. Buttons stay capability-ungated for Porsche
        until then.
        """
        return {}

    async def command_lock(self, vin: str) -> None:
        # b19 (CJNE-comparison): CJNE's LOCK payload always carries a
        # (null) "spin" field — no real PIN needed, but the key is present.
        await self._command(vin, "LOCK", {"spin": None})

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        """Unlock — requires the SPIN-challenge/response protocol.

        b19 (#1337, CJNE-comparison #1 — the highest-priority finding of that
        pass): the ``spin`` parameter existed in this signature but was never
        read or forwarded anywhere; no challenge was ever requested and no
        ``payload.spin`` object was ever attached to the UNLOCK command. This
        very likely made every unlock attempt silently fail or be rejected,
        independent of the login-layer issues tracked under #1337/#13.
        Protocol ported from CJNE's ``unlock_vehicle``/``_get_challenge``
        (Apache-2.0): request a ``SPIN_CHALLENGE``, then
        ``sha512(pin + challenge).hexdigest().upper()`` as the response hash.
        NOT LIVE-VERIFIED — needs a real account with a car and an S-PIN set.
        """
        await self._spin_command(vin, "UNLOCK", spin)

    async def command_unlock_trunk(self, vin: str, spin: str = "") -> None:
        """Unlock the trunk/frunk only — separate from the full-vehicle
        ``UNLOCK``.

        b20 (2026-09-08, androguard enum dump) — ``TRUNK_UNLOCK`` is a real
        command in the app (dedicated ``TrunkUnlock``/``$$serializer`` model
        class), not requested by CJNE or previously implemented here.
        Assumed to need the same SPIN-challenge/response protocol as
        ``UNLOCK`` since it's also an unlock-class action under Porsche's
        security model — that assumption is NOT confirmed (the payload
        class's exact fields weren't captured, only that it exists).
        NOT LIVE-VERIFIED at all.
        """
        await self._spin_command(vin, "TRUNK_UNLOCK", spin)

    async def _spin_command(self, vin: str, key: str, spin: str) -> None:
        """Shared SPIN-challenge/response protocol for unlock-class commands."""
        if not spin:
            raise SpinError(f"Porsche {key} requires an S-PIN")
        challenge = await self._spin_challenge(vin)
        if not challenge:
            raise VehicleCommandError(key, "no SPIN challenge returned")
        pinhash = hashlib.sha512(bytes.fromhex(spin + challenge)).hexdigest().upper()
        await self._command(
            vin, key, {"spin": {"challenge": challenge, "hash": pinhash}},
        )

    async def _spin_challenge(self, vin: str) -> str | None:
        """Request a SPIN_CHALLENGE and return the challenge string, or
        ``None`` if the response didn't carry one."""
        response = await self._post(
            f"{_API_BASE}/app/connect/v1/vehicles/{vin}/commands",
            json={"key": "SPIN_CHALLENGE", "payload": {"spin": None}},
        )
        if isinstance(response, dict):
            challenge = response.get("data", {}).get("challenge")
            if isinstance(challenge, str):
                return challenge
        return None

    async def command_open_windows(self, vin: str) -> None:
        """b20 (2026-09-08, androguard enum dump) — WINDOWS_SUNROOF_OPEN is a
        real command (dedicated ``WindowsSunroofOpen`` model class), not
        requested by CJNE or previously implemented here. This project
        already tracks window/sunroof OPEN-state measurements but had no
        command to actually move them — this closes that gap. NOT
        LIVE-VERIFIED — the payload shape (e.g. whether it takes a
        which-window selector) wasn't captured, so this sends no extra
        payload fields, matching the "no per-command payload beyond the
        common spin field" pattern most other simple commands use."""
        await self._command(vin, "WINDOWS_SUNROOF_OPEN")

    async def command_close_windows(self, vin: str) -> None:
        """See ``command_open_windows``. NOT LIVE-VERIFIED."""
        await self._command(vin, "WINDOWS_SUNROOF_CLOSE")

    async def command_vent_windows(self, vin: str) -> None:
        """See ``command_open_windows``. NOT LIVE-VERIFIED."""
        await self._command(vin, "WINDOWS_SUNROOF_VENT")

    async def command_charging_start(self, vin: str) -> None:
        """b20 (2026-09-08, androguard enum dump) — a SEPARATE, plain
        ``CHARGING_START`` command exists alongside the already-implemented
        ``DIRECT_CHARGING_START``/``DIRECT_CHARGING_STOP`` pair (deliberately
        NOT named ``command_start_charging`` — that name is already taken by
        the existing ``DIRECT_CHARGING_START`` method below). How the two
        differ (scheduled vs. immediate charging, maybe) is not confirmed.
        Payload assumed to match its charging-family siblings
        (``{"spin": None}``) since nothing else is evidenced. NOT
        LIVE-VERIFIED, and the semantic difference from DIRECT_CHARGING_*
        is genuinely unknown, not just untested."""
        await self._command(vin, "CHARGING_START", {"spin": None})

    async def command_start_ota_update(self, vin: str) -> None:
        """b20 (2026-09-08) — ``OTA_UPDATE_REMOTE_START``, real command
        (software-update-available flow). No payload fields evidenced.
        NOT LIVE-VERIFIED."""
        await self._command(vin, "OTA_UPDATE_REMOTE_START")

    async def command_give_ota_consent(self, vin: str) -> None:
        """b20 (2026-09-08) — ``OTA_CONSENT_GIVE``. NOT LIVE-VERIFIED."""
        await self._command(vin, "OTA_CONSENT_GIVE")

    async def command_revoke_ota_consent(self, vin: str) -> None:
        """b20 (2026-09-08) — ``OTA_CONSENT_REVOKE``. NOT LIVE-VERIFIED."""
        await self._command(vin, "OTA_CONSENT_REVOKE")

    async def command_reset_service_predictions(self, vin: str) -> None:
        """b20 (2026-09-08) — ``SERVICE_PREDICTIONS_RESET``, presumably
        clears/recalculates the service-due predictions after maintenance.
        No payload fields evidenced. NOT LIVE-VERIFIED."""
        await self._command(vin, "SERVICE_PREDICTIONS_RESET")

    async def command_disable_valet_alarm(self, vin: str) -> None:
        """b21 (2026-09-08) — ``VALET_ALARM_DISABLE``. NOT LIVE-VERIFIED."""
        await self._command(vin, "VALET_ALARM_DISABLE")

    async def command_edit_valet_alarm(
        self, vin: str, speed_limit: int, latitude: float, longitude: float, radius: int,
    ) -> None:
        """Configure/enable valet mode: a geofence + speed limit.

        b21 (2026-09-08, disassembly of ``EditValetAlarmCommandPayload``'s
        ``$$serializer`` — vag-connect-porsche-edit-commands-payload-
        2026-09-08.md §3) — GROUNDED field names and structure:
        ``{spin, speedLimit: Int, area: {circle: {location: Location, radius: Int}}}``.
        The nested ``Location`` class's own fields were not independently
        disassembled this pass; ``{"latitude": ..., "longitude": ...}`` is
        inferred by analogy to the sibling ``Point`` class in the same app
        (confirmed ``{latitude: Double, longitude: Double}``), NOT
        independently confirmed for ``Location`` specifically — flagged so
        a live test knows exactly what to check if this fails.
        ``speedLimit`` living on this payload (not just a geofence) is
        real and confirmed, not a guess — valet mode apparently combines
        both. NOT LIVE-VERIFIED overall.
        """
        await self._command(vin, "VALET_ALARM_EDIT", {
            "spin": None,
            "speedLimit": speed_limit,
            "area": {"circle": {
                "location": {"latitude": latitude, "longitude": longitude},
                "radius": radius,
            }},
        })

    async def command_edit_speed_alarms(
        self, vin: str, alarms: list[dict[str, Any]],
    ) -> None:
        """Replace the vehicle's speed-alarm list.

        b21 (2026-09-08, disassembly of ``EditSpeedAlarmsCommandPayload``'s
        ``$$serializer``) — GROUNDED, flat, no polymorphism:
        ``{spin, list: [{id: String, isEnabled: Boolean, speedLimit: Int}]}``.
        The cleanest of the new edit commands — every field independently
        confirmed on both the write side and the matching read-side
        ``SpeedAlarmsMeasurementValue``. ``alarms`` takes the list of
        ``{"id": ..., "isEnabled": ..., "speedLimit": ...}`` dicts verbatim.
        NOT LIVE-VERIFIED (the shape is grounded; sending it to a real
        vehicle has not been).
        """
        await self._command(
            vin, "SPEED_ALARMS_EDIT", {"spin": None, "list": alarms},
        )

    async def command_edit_location_alarms(
        self, vin: str, alarms: list[dict[str, Any]],
    ) -> None:
        """Replace the vehicle's location-alarm (geofence) list.

        b21 (2026-09-08, disassembly of ``EditLocationAlarmsCommandPayload``'s
        ``$$serializer`` and its ``Circle``/``Rectangle`` variant classes) —
        GROUNDED field names, with two specific unconfirmed details flagged
        below. Each entry in ``alarms`` must be a dict shaped as either::

            {"id": ..., "isEnabled": ..., "name": ...,
             "circle": {"location": "<lat>,<lng>", "radius": <int>}}
            {"id": ..., "isEnabled": ..., "name": ...,
             "rectangle": {"topLeft": "<lat>,<lng>", "bottomRight": "<lat>,<lng>"}}

        Confirmed: ``id``/``isEnabled``/``name`` on every entry;
        ``circle.radius`` is Int; ``circle.location``/``rectangle.topLeft``/
        ``rectangle.bottomRight`` are confirmed String fields (not nested
        objects) on both the write side and the matching read-side
        ``LocationAlarmsMeasurementValue``. The ``"<lat>,<lng>"`` STRING
        FORMAT itself is inferred by analogy to this same API's
        ``GPS_LOCATION.location`` field (a confirmed comma-separated
        "lat,lng" string, per this project's own ``get_status`` parsing and
        CJNE's ``vehicle.py::location``), not independently disassembled for
        this field. Also unconfirmed: whether the wire format needs a
        polymorphic class-discriminator key (conventionally ``"type"``) to
        distinguish circle vs. rectangle entries, since kotlinx.serialization
        sealed classes normally add one at the outer level rather than in
        either variant's own ``addElement`` calls — this payload is sent
        WITHOUT one (the presence of ``circle`` vs. ``rectangle`` may be
        sufficient on its own); if the real backend rejects it, adding a
        discriminator is the first thing to try. NOT LIVE-VERIFIED.
        """
        await self._command(
            vin, "LOCATION_ALARMS_EDIT", {"spin": None, "list": alarms},
        )

    async def command_delete_destination(self, vin: str, uuid: str, snapshot_id: str) -> None:
        """Delete a saved destination.

        b21 (2026-09-08, disassembly of ``DestinationDeleteCommandPayload``'s
        ``$$serializer``) — GROUNDED, flat, no gaps:
        ``{spin, uuid: String, snapshotId: String}``. ``uuid`` is the
        destination entry's own id (not the vehicle's VIN); ``snapshotId``
        is a sync/concurrency token for the destinations list — the
        existing (already-requested, unparsed) ``DESTINATIONS`` measurement
        is where a caller would read the current ``snapshotId`` from once
        this project parses that field (not done yet). NOT LIVE-VERIFIED.

        See ``command_edit_destination`` for the sibling add/update command
        (was a gap here, now grounded and implemented).
        """
        await self._command(
            vin, "DESTINATIONS_DELETE",
            {"spin": None, "uuid": uuid, "snapshotId": snapshot_id},
        )

    async def command_edit_destination(
        self, vin: str, destination_entry: dict[str, Any], snapshot_id: str,
    ) -> None:
        """Add or update a saved destination.

        b22 (2026-09-08, disassembly of ``DestinationEntry``'s
        ``$$serializer`` and its 4 direct nested classes — the one gap left
        open in b21 above) — GROUNDED:
        ``{spin, destinationEntry: DestinationEntry, snapshotId: String}``.

        ``DestinationEntry`` itself is fully field-named:
        ``{uuid?, destination: Destination?, attributes: Attributes,
        createTime, lastModifiedTime, lastUsedTime, googleReference?,
        vwPoiReference?}`` (the three timestamp fields are REQUIRED, not
        optional — an edit send must include all three). 3 of its 4 nested
        object types are also fully grounded (``Attributes``:
        ``{attributes, phoneNumbers, aliases}``; ``GoogleReference``:
        ``{placeId, language, expirationTime?}``; ``VwPoiReference``:
        ``{vwGroupId}``). The 4th, ``Destination`` itself, is grounded at
        its own top level (7 named fields: ``entryType``, ``tokens``,
        ``metaTokens``, ``locationTokens``, ``entryFlags``,
        ``isFromOnlineSearch: Boolean``, ``chargingStationInformation``) but
        its own sub-objects were not expanded — genuinely richer than the
        ``Waypoint``/``Point`` shape once guessed by analogy for this, which
        turned out to be wrong; do not reconstruct ``Destination`` from
        those.

        Given that remaining depth, ``destination_entry`` is deliberately
        NOT modelled as separate keyword arguments here — the realistic and
        only safe use of this command is reading an existing entry from the
        (already-requested, unparsed) ``DESTINATIONS`` measurement, mutating
        only the field(s) actually being changed, and sending the whole
        object back verbatim with a fresh ``snapshot_id``. Hand-constructing
        a ``destination_entry`` from scratch is NOT recommended until a live
        ``DESTINATIONS`` capture shows a real example. NOT LIVE-VERIFIED.
        """
        await self._command(vin, "DESTINATIONS_EDIT", {
            "spin": None,
            "destinationEntry": destination_entry,
            "snapshotId": snapshot_id,
        })

    async def command_start_climate(self, vin: str) -> None:
        await self._command(vin, "REMOTE_CLIMATIZER_START")

    async def command_stop_climate(self, vin: str) -> None:
        await self._command(vin, "REMOTE_CLIMATIZER_STOP")

    async def command_start_charging(self, vin: str) -> None:
        await self._command(vin, "DIRECT_CHARGING_START", {"spin": None})

    async def command_stop_charging(self, vin: str) -> None:
        await self._command(vin, "DIRECT_CHARGING_STOP", {"spin": None})

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,  # noqa: ARG002
        longitude: float | None = None,  # noqa: ARG002
        duration_s: int = 10,  # noqa: ARG002 - value not grounded for this brand
        honk: bool = False,
    ) -> None:
        # b19 (CJNE-comparison): CJNE's flash_indicators/honk_and_flash_indicators
        # are the SAME "HONK_FLASH" key, distinguished only by payload.mode —
        # "FLASH" vs "HONK_AND_FLASH". ``honk`` already existed on this
        # signature but was previously dropped on the floor.
        mode = "HONK_AND_FLASH" if honk else "FLASH"
        await self._command(vin, "HONK_FLASH", {"mode": mode, "spin": None})

    async def command_wake(self, vin: str) -> None:
        # Porsche doesn't have a dedicated wake — flash serves as ping
        await self._command(vin, "HONK_FLASH")

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        """Set the charging target SoC.

        b19 (CJNE-comparison #14): clamp to Porsche's accepted 25-100 range
        (CJNE's ``update_charging_setting``/``update_charging_profile``), and
        branch on which model the vehicle actually uses — some vehicles
        expose the target via ``CHARGING_PROFILES`` (edit the whole list,
        keyed on the active/isEnabled profile) rather than
        ``CHARGING_SETTINGS``/``DEPARTURES``. Needs one extra read to know
        which applies; that's cheap next to getting silently ignored on the
        wrong model. NOT LIVE-VERIFIED on either branch.
        """
        target = min(max(int(target), 25), 100)
        probe = await self._get(
            f"{_API_BASE}/app/connect/v1/vehicles/{vin}",
            params=[("mf", "DEPARTURES"), ("mf", "CHARGING_PROFILES")],
        )
        measurements = probe.get("measurements") if isinstance(probe, dict) else None
        m = {
            item["key"]: item.get("value", {})
            for item in (measurements or [])
            if isinstance(item, dict) and item.get("key")
        }
        if "CHARGING_PROFILES" in m and "DEPARTURES" not in m:
            profiles = m["CHARGING_PROFILES"].get("list", [])
            active = next((p for p in profiles if p.get("isEnabled")), None)
            if active is None:
                raise VehicleCommandError(
                    "CHARGING_PROFILES_EDIT", "no active charging profile found"
                )
            active["minSoc"] = target
            await self._command(vin, "CHARGING_PROFILES_EDIT", {"list": profiles})
            return
        await self._command(
            vin, "CHARGING_SETTINGS_EDIT", {"targetSoc": target, "spin": None},
        )

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        await self._command(
            vin, "REMOTE_CLIMATIZER_START", {"temperature": temp_c},
        )

    async def command_start_window_heating(self, vin: str) -> None:
        await self._command(vin, "REMOTE_HEATING_START")

    async def command_stop_window_heating(self, vin: str) -> None:
        await self._command(vin, "REMOTE_HEATING_STOP")

    async def command_set_departure_timer(
        self,
        vin: str,
        timer_id: int,
        enabled: bool,
        departure_time: str | None,
        recurring_on: list[str] | None = None,  # noqa: ARG002
    ) -> None:
        # v2.0.0 (Big-Bang) — accepts ``recurring_on`` to keep the
        # cross-brand interface uniform; PPA's DEPARTURES_EDIT command
        # doesn't expose a weekday list field today, so the parameter
        # is silently ignored for Porsche.
        payload: dict[str, Any] = {"timerId": timer_id, "enabled": enabled}
        if departure_time:
            payload["departureTime"] = departure_time
        await self._command(
            vin, "DEPARTURES_EDIT" if enabled else "TIMERS_DISABLE", payload,
        )

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    async def _command(self, vin: str, key: str, payload: dict | None = None) -> None:
        """POST a remote-service command and best-effort verify it wasn't
        rejected outright or by a terminal error within a bounded poll.

        b19 (found while porting SPIN support, #1337) — TWO bugs fixed here:
        1. The wire field is ``key``, confirmed against CJNE's
           ``remote_services.py`` (every payload there uses it) — this
           method previously sent ``commandName`` instead. Since Porsche's
           login was blocked until #1337's fix today, no command had ever
           been live-tested, so this was never caught: it likely made every
           single Porsche command (lock, unlock, climate, charging, honk,
           timers) silently fail or get ignored, not just the missing-SPIN
           unlock case this was originally found while fixing.
        2. If the response carries a ``status.id`` with ``status.result ==
           "ACCEPTED"``, poll ``/commands/{id}`` for a terminal state (see
           ``_poll_command``) so a rejected command is no longer silently
           indistinguishable from a successful one (CJNE-comparison #3).
        """
        response = await self._post(
            f"{_API_BASE}/app/connect/v1/vehicles/{vin}/commands",
            json={"key": key, "payload": payload or {}},
        )
        status = response.get("status", {}) if isinstance(response, dict) else {}
        status_id = status.get("id")
        result = status.get("result")
        if status_id and result == "ACCEPTED":
            await self._poll_command(vin, key, status_id)
        elif result == "ERROR":
            raise VehicleCommandError(key, "rejected immediately by Porsche")

    async def _poll_command(self, vin: str, key: str, status_id: str) -> None:
        """Poll a command's status until PERFORMED/ERROR or the (short,
        deliberately bounded) timeout — see ``_COMMAND_POLL_TIMEOUT_S``."""
        deadline = time.monotonic() + _COMMAND_POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(_COMMAND_POLL_INTERVAL_S)
            try:
                msg = await self._get(
                    f"{_API_BASE}/app/connect/v1/vehicles/{vin}/commands/{status_id}",
                )
            except APIError:
                # A status-poll hiccup shouldn't fail a command that was
                # already accepted — best-effort verification only.
                return
            result = (
                msg.get("status", {}).get("result") if isinstance(msg, dict) else None
            )
            if result == "ERROR":
                raise VehicleCommandError(key, "rejected by Porsche")
            if result == "PERFORMED":
                return
        _LOGGER.debug(
            "Porsche command %s (%s) still pending after %ds — leaving it "
            "to the next coordinator poll instead of blocking further",
            key, status_id, _COMMAND_POLL_TIMEOUT_S,
        )

    # v1.25.0 PR-B: HTTP machinery hardening — port retry / storm-protection
    # / quota-tracking patterns from CariadBaseClient.
    #
    # Pre-v1.25.0 PorscheClient duplicated a much simpler `_request` (no
    # 5xx retry, no 429 backoff, no quota header capture, no refresh-storm
    # protection). Audit Agent A flagged this as the highest-impact gap
    # for PorscheClient. Big-bang abstract-class extract was deemed too
    # risky for v1.25.0; this PR applies the same battle-tested patterns
    # in-line so Porsche users get parity.

    async def _get(self, url: str, **kwargs: Any) -> Any:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> Any:
        return await self._request("POST", url, **kwargs)

    async def _request(
        self, method: str, url: str,
        retry: bool = True, _attempt: int = 0, **kwargs: Any,
    ) -> Any:
        """Execute authenticated request with retry for transient errors.

        v1.25.0 PR-B parity with CariadBaseClient._request:

        - HTTP 401 → token refresh + 1 retry. Refresh itself throttled to
          ``_REFRESH_MAX_PER_HOUR`` per rolling hour (storm protection).
        - HTTP 429 → exponential backoff up to 3 attempts (5s/10s/20s).
        - HTTP 500/502/503/504 → exponential backoff up to 3 attempts
          (3s/6s/12s).
        - Transient network errors (DNS / connection refused / mid-stream
          disconnects / asyncio timeouts) → same backoff as server errors.
        - X-RateLimit-Remaining / Limit / Reset headers captured on 2xx
          responses → exposed via ``last_rate_limit_*`` properties for
          the coordinator's quota sensor.
        """
        from aiohttp import (  # noqa: PLC0415
            ClientConnectorError, ClientPayloadError, ServerDisconnectedError,
        )
        _TRANSIENT = (
            ClientConnectorError, ServerDisconnectedError,
            ClientPayloadError, asyncio.TimeoutError,
        )
        if not self._tokens:
            raise AuthenticationError("Not authenticated")
        # b19 (CJNE-comparison #11) — proactive refresh: TokenSet.needs_refresh()
        # was already available (used by other brands) but never called here,
        # so Porsche only ever refreshed reactively off an observed 401,
        # eating one wasted round trip every natural expiry cycle. Only on
        # the first attempt, so a mid-retry-chain call doesn't re-trigger it.
        if _attempt == 0 and retry and self._tokens.needs_refresh():
            await self._refresh()
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {self._tokens.access_token}",
            "X-Client-ID":   _X_CLIENT,
            "User-Agent":    _USER_AGENT,
            "Accept":        "application/json",
        })
        try:
            async with self._session.request(
                method, url, headers=headers,
                timeout=ClientTimeout(total=30), **kwargs,
            ) as resp:
                if resp.status == 401 and retry:
                    await self._refresh()
                    return await self._request(method, url, retry=False, **kwargs)
                if resp.status == 429 and _attempt < 3:
                    # b19 (CJNE-comparison #5) — honor a server-sent
                    # Retry-After if present; a CJNE maintainer's commit
                    # message states Porsche's backend does send one in
                    # practice. Falls back to the existing fixed schedule.
                    retry_after = resp.headers.get("Retry-After", "")
                    wait = (
                        int(retry_after) if retry_after.isdigit()
                        else (2 ** _attempt) * 5
                    )
                    _LOGGER.debug("Porsche 429 — retrying in %ds", wait)
                    await asyncio.sleep(wait)
                    return await self._request(
                        method, url, retry=retry, _attempt=_attempt + 1, **kwargs,
                    )
                if resp.status in (500, 502, 503, 504) and _attempt < 3:
                    wait = (2 ** _attempt) * 3
                    _LOGGER.debug("Porsche %d — retrying in %ds", resp.status, wait)
                    await asyncio.sleep(wait)
                    return await self._request(
                        method, url, retry=retry, _attempt=_attempt + 1, **kwargs,
                    )
                if resp.status == 204:
                    self._capture_rate_limit_headers(resp.headers)
                    return {}
                if resp.status not in (200, 202):
                    body = await resp.text()
                    raise APIError(resp.status, url, body)
                self._capture_rate_limit_headers(resp.headers)
                return await resp.json()
        except _TRANSIENT as err:
            if _attempt < 3:
                wait = (2 ** _attempt) * 3
                _LOGGER.debug(
                    "Porsche transient (%s) — retrying in %ds",
                    type(err).__name__, wait,
                )
                await asyncio.sleep(wait)
                return await self._request(
                    method, url, retry=retry, _attempt=_attempt + 1, **kwargs,
                )
            # drop the raw {err} — it would sit in self.body; class name suffices.
            raise APIError(0, url, f"transient: {type(err).__name__}") from err

    # v1.25.0 PR-B: rate-limit header capture (mirror of base.py:_capture_rate_limit_headers)
    def _capture_rate_limit_headers(self, headers: Any) -> None:
        """Store latest X-RateLimit-* headers if present.

        Porsche PPA backend may or may not send these — defensive parsing
        accepts ints, floats-as-strings ("1499.5"), garbage ("unlimited")
        without raising. Coordinator reads ``last_rate_limit_remaining``
        as the ``requests_remaining_today`` sensor source.
        """
        for header_name, attr in (
            ("X-RateLimit-Remaining", "last_rate_limit_remaining"),
            ("X-RateLimit-Limit",     "last_rate_limit_limit"),
            ("X-RateLimit-Reset",     "last_rate_limit_reset_at"),
        ):
            raw = headers.get(header_name) if hasattr(headers, "get") else None
            if raw is None:
                continue
            try:
                # int first (most common), then float, then leave as string
                # for "Reset" which is sometimes a Unix timestamp string.
                value: Any = int(float(str(raw)))
            except (ValueError, TypeError):
                continue
            setattr(self, attr, value)

    async def _refresh(self) -> None:
        """Refresh tokens with storm protection (v1.25.0 PR-B parity).

        Pre-v1.25.0 there was no throttle — repeated 401s would spam refresh
        attempts and could trigger Porsche-side IP rate-limiting. Now mirrors
        CariadBaseClient: ``_REFRESH_MAX_PER_HOUR`` (3) attempts per
        ``_REFRESH_WINDOW_S`` (3600) sliding window, then raises
        AuthenticationError so coordinator triggers HA reauth flow.
        """
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            now = time.monotonic()
            cutoff = now - _REFRESH_WINDOW_S
            self._refresh_history = [t for t in self._refresh_history if t > cutoff]
            if len(self._refresh_history) >= _REFRESH_MAX_PER_HOUR:
                _LOGGER.error(
                    "Porsche token refresh storm: %d attempts in last %ds — "
                    "pausing to prevent IP ban; please reauthenticate from the UI",
                    len(self._refresh_history), _REFRESH_WINDOW_S,
                )
                raise AuthenticationError(
                    "Porsche token refresh storm — please reauthenticate",
                )
            self._refresh_history.append(now)

            if self._tokens and self._tokens.refresh_token:
                try:
                    self._tokens = await self._auth.refresh(self._tokens.refresh_token)
                    return
                except TokenExpiredError:
                    pass
            await self.authenticate()

    @staticmethod
    def _val(data: dict, *path: str, default: Any = None) -> Any:
        node: Any = data
        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
            if node is None:
                return default
        return node
