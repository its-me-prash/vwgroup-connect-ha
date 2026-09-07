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
_MEASUREMENTS = (
    "BATTERY_LEVEL", "E_RANGE", "FUEL_LEVEL", "FUEL_RESERVE", "MILEAGE",
    "CHARGING_SUMMARY", "CHARGING_STATE", "CHARGING_RATE", "CHARGING_SETTINGS",
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
    "TIRE_PRESSURE",
)


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

            # ── v2.0.0 (Big-Bang) — TPMS ─────────────────────────────────
            # PPA returns ``TIRE_PRESSURE`` as a dict with per-corner
            # entries: ``frontLeft``/``frontRight``/``rearLeft``/``rearRight``,
            # each carrying ``currentPressure`` (kPa or bar depending on
            # vehicle locale — observed in the wild as kPa float, e.g.
            # 235.0 → 2.35 bar) and ``warning`` (bool). Defensive: only
            # populate if the dict actually has corner entries — older
            # PPA variants ship an empty dict for non-TPMS-equipped cars.
            tp = m.get("TIRE_PRESSURE", {})
            if isinstance(tp, dict) and tp:
                def _bar(corner: str) -> float | None:
                    raw = v(tp, corner, "currentPressure")
                    if raw is None:
                        return None
                    try:
                        n = float(raw)
                    except (TypeError, ValueError):
                        return None
                    # kPa heuristic: anything > 10 is kPa, divide by 100
                    return round(n / 100.0, 2) if n > 10 else round(n, 2)
                d.tire_pressure_front_left_bar  = _bar("frontLeft")
                d.tire_pressure_front_right_bar = _bar("frontRight")
                d.tire_pressure_rear_left_bar   = _bar("rearLeft")
                d.tire_pressure_rear_right_bar  = _bar("rearRight")
                d.tire_pressure_warning = any(
                    bool(v(tp, c, "warning"))
                    for c in ("frontLeft", "frontRight", "rearLeft", "rearRight")
                )

        # v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation.
        # Porsche PPA doesn't ship a direct `carType` enum — derive
        # from has_battery + has_combustion (already set above from
        # `VEHICLE.engine` BEV/PHEV/COMBUSTION). Never overwrites.
        from .._util import derive_car_type_if_missing  # noqa: PLC0415

        derive_car_type_if_missing(d)

        return d

    async def get_capabilities(self, vin: str) -> dict[str, Any]:  # noqa: ARG002
        """Porsche PPA does not expose a discrete capabilities endpoint.

        Returning ``{}`` keeps the interface consistent with the
        CARIAD/OLA clients so the coordinator can call this without
        feature detection. Buttons will not be capability-gated for
        Porsche until/unless an endpoint is found.
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
        if not spin:
            raise SpinError("Porsche unlock requires an S-PIN")
        challenge = await self._spin_challenge(vin)
        if not challenge:
            raise VehicleCommandError("UNLOCK", "no SPIN challenge returned")
        pinhash = hashlib.sha512(bytes.fromhex(spin + challenge)).hexdigest().upper()
        await self._command(
            vin, "UNLOCK", {"spin": {"challenge": challenge, "hash": pinhash}},
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
