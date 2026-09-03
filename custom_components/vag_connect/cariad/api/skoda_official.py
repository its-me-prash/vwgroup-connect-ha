# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda **official** public vehicle API — opt-in, first-party, attestation-free.

Distinct from :mod:`skoda` (the unofficial reverse-engineered ``mysmob`` client):
this talks to Škoda's own public gateway ``public.api.connect.skoda-auto.cz``
using a user-minted **API key** (``X-API-Key`` header), created in the MyŠkoda app
(Settings → Smart Home → API Keys, app v8.16+). No OAuth, no password, no
attestation — a durable official channel. See ``docs/research/skoda-official-api.md``
for the full grounded surface (generated from the live OpenAPI spec).

Two hard properties shape the design:

* **No list endpoint** — the key is bound to specific vehicles at creation time,
  and the only read is ``GET /vehicles/{vin}``. So the VIN(s) the key covers must
  be supplied by the user; :meth:`get_vehicles` just returns them.
* **20 requests / hour / key** rate limit (server states it is "not final"). Every
  response carries ``RateLimit-Remaining``; :attr:`rate_limit_remaining` tracks it
  so the coordinator can poll conservatively and leave headroom for commands. This
  is a low-frequency official channel, **not** a mysmob replacement.

Factory plumbing: to reuse the existing ``create(session, brand, email, password,
spin)`` signature without a new arg, the VIN(s) ride the ``email`` slot
(comma-separated) and the API key rides the ``password`` slot.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .._util import drop_charge_sentinel, safe_int
from ..exceptions import APIError, AuthenticationError
from ..models import VehicleData

_BASE = "https://public.api.connect.skoda-auto.cz/api/v1"
_TIMEOUT = ClientTimeout(total=30)
_USER_AGENT = "vwgroup-connect-ha (Home Assistant)"


def _to_bool_open(value: Any) -> bool | None:
    """Map an overall-status string to open=True / closed=False."""
    if not isinstance(value, str):
        return None
    v = value.strip().upper()
    if v in ("OPEN", "UNLOCKED", "YES", "ON"):
        return True
    if v in ("CLOSED", "LOCKED", "NO", "OFF", "UNSUPPORTED"):
        return False
    return None


def _open_strict(value: Any) -> bool | None:
    """OPEN→True / CLOSED→False / anything else (incl. UNSUPPORTED)→None.

    For optional body parts (sunroof, bonnet) where UNSUPPORTED must stay None so a
    car without the part doesn't spawn a phantom "closed" binary sensor — unlike
    ``_to_bool_open`` which maps UNSUPPORTED→False (fine for the universal trunk).
    """
    if isinstance(value, str):
        up = value.strip().upper()
        if up == "OPEN":
            return True
        if up == "CLOSED":
            return False
    return None


class SkodaOfficialClient:
    """Read + command client for the official Škoda public API (opt-in)."""

    def __init__(
        self,
        session: ClientSession,
        email: str,          # factory ``email`` slot = comma-separated VIN(s)
        password: str,       # factory ``password`` slot = the X-API-Key
        spin: str = "",
        keys_by_vin: dict[str, str] | None = None,
    ) -> None:
        self._session = session
        self._api_key = (password or "").strip()
        # Keys are VIN-bound (minted per VIN, max 5/VIN). ``keys_by_vin`` carries the
        # auto-enrolled per-VIN keys; the single ``_api_key`` is the manual fallback
        # applied to any VIN not in the map. _key_for(vin) picks the right one.
        self._keys_by_vin = {
            k.strip().upper(): (val or "").strip()
            for k, val in (keys_by_vin or {}).items()
            if k and (val or "").strip()
        }
        self._vins = [v.strip().upper() for v in (email or "").split(",") if v.strip()]
        # A per-VIN map is itself an authoritative VIN list (used when no explicit
        # email/VIN slot was passed, i.e. the auto-enroll path).
        if not self._vins and self._keys_by_vin:
            self._vins = sorted(self._keys_by_vin)
        self._spin = (spin or "").strip()
        # Populated from every response's RateLimit-Remaining header; None until
        # the first call. The coordinator reads this to pace itself (20/hour/key).
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset_s: int | None = None
        self.retry_after_s: int | None = None
        # Local self-block window (monotonic deadline) — set when the server says
        # the budget is exhausted (RateLimit-Remaining 0, or a 429/503 Retry-After),
        # so the failover never breaches the 20/hour/key quota. Mirrors the openHAB
        # MySkoda binding's client-side rate limiter.
        self._blocked_until: float = 0.0

    def _key_for(self, vin: str) -> str:
        """The X-API-Key to use for one VIN: its own minted key, else the single
        manual key as a fallback."""
        return self._keys_by_vin.get((vin or "").strip().upper(), self._api_key)

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """No OAuth — the ``X-API-Key`` is itself the credential. Validate it with
        a single read of the first configured VIN so a wrong / wrong-vehicle /
        expired key fails at setup instead of silently returning nothing (costs
        one of the 20 requests/hour budget). Interface parity with the other
        clients the factory returns."""
        if not self._vins:
            return
        # get_status raises AuthenticationError on 401 and APIError on 404/others
        await self.get_status(self._vins[0])

    # -- transport ------------------------------------------------------------

    def _headers(self, api_key: str | None = None) -> dict[str, str]:
        key = api_key or self._api_key
        if not key:
            raise AuthenticationError("Škoda official API: no API key configured")
        return {
            "X-API-Key": key,
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }

    def _note_rate_limit(self, resp: Any) -> None:
        rem = resp.headers.get("RateLimit-Remaining")
        rst = resp.headers.get("RateLimit-Reset")
        ra = resp.headers.get("Retry-After")  # sent on 429 / 503
        if rem is not None and str(rem).lstrip("-").isdigit():
            self.rate_limit_remaining = int(rem)
        if rst is not None and str(rst).lstrip("-").isdigit():
            self.rate_limit_reset_s = int(rst)
        if ra is not None and str(ra).isdigit():
            self.retry_after_s = int(ra)
        # Self-block when the server says we're out of budget. Prefer the explicit
        # Retry-After (429/503); else block for the reset window once remaining==0.
        wait = 0
        if self.retry_after_s and str(resp.status).startswith(("4", "5")):
            wait = self.retry_after_s
        elif self.rate_limit_remaining == 0 and self.rate_limit_reset_s:
            wait = self.rate_limit_reset_s
        if wait > 0:
            self._blocked_until = time.monotonic() + wait

    @property
    def over_rate_limit(self) -> bool:
        """True while the local self-block window (from RateLimit-Remaining 0 or a
        Retry-After) is still open — the failover read skips instead of breaching
        the 20/hour/key quota."""
        return time.monotonic() < self._blocked_until

    async def _request(
        self, method: str, path: str, json_body: Any = None, api_key: str | None = None,
    ) -> tuple[int, Any]:
        async with self._session.request(
            method, f"{_BASE}/{path}", headers=self._headers(api_key),
            json=json_body, timeout=_TIMEOUT,
        ) as resp:
            self._note_rate_limit(resp)
            try:
                body = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001 — problem+json / text on errors
                body = await resp.text()
            return resp.status, body

    async def _get(self, path: str, api_key: str | None = None) -> tuple[int, Any]:
        return await self._request("GET", path, api_key=api_key)

    async def _post(
        self, path: str, json_body: Any = None, api_key: str | None = None,
    ) -> tuple[int, Any]:
        return await self._request("POST", path, json_body, api_key=api_key)

    # -- reads ----------------------------------------------------------------

    async def get_vehicles(self) -> list[str]:
        """The API has no list endpoint — the key is vehicle-bound, so return the
        VIN(s) the user configured for this key."""
        return list(self._vins)

    async def get_status(self, vin: str) -> VehicleData:
        status, body = await self._get(f"vehicles/{vin}", api_key=self._key_for(vin))
        if status == 401:
            raise AuthenticationError(
                "Škoda official API: key rejected (401) — expired or wrong vehicle"
            )
        if status != 200 or not isinstance(body, dict):
            raise APIError(status, f"{_BASE}/vehicles/{vin}", str(body)[:200])
        return self._parse_vehicle(vin, body.get("vehicle") or body)

    # -- parse ----------------------------------------------------------------

    @staticmethod
    def _parse_vehicle(vin: str, v: dict[str, Any]) -> VehicleData:
        d = VehicleData(vin=vin)
        d.model = v.get("name") or d.model
        if isinstance(v.get("licensePlate"), str):
            d.license_plate = v["licensePlate"]
        # b7 — the render image URL rides the same response; the image entity reads it.
        if isinstance(v.get("renderUrl"), str) and v["renderUrl"]:
            d.render_url = v["renderUrl"]

        # -- opening / lock status (overall + detail) -------------------------
        status = v.get("status") or {}
        overall = status.get("overall") or {}
        detail = status.get("detail") or {}
        # Grounded on the spec's documented values (the fields are plain strings
        # with no enum type, but each field's description enumerates them):
        #   doorsLocked / locked = YES | NO | OPENED | UNKNOWN  (YES == all
        #     supported doors AND trunk LOCKED+CLOSED) — NOT "LOCKED".
        #   doors / windows / detail.trunk = OPEN | CLOSED | UNKNOWN.
        _dl = overall.get("doorsLocked") or overall.get("locked")
        if isinstance(_dl, str):
            d.doors_locked = _dl.strip().upper() == "YES"
        _do = _to_bool_open(overall.get("doors"))
        if _do is not None:
            d.doors_open = _do
        _wo = _to_bool_open(overall.get("windows"))
        if _wo is not None:
            d.windows_open = _wo
        _trunk = _to_bool_open(detail.get("trunk"))
        if _trunk is not None:
            d.trunk_open = _trunk
        # b7 — status fields the official parser was dropping (all in the response).
        _lights = overall.get("lights")
        if isinstance(_lights, str):
            _lu = _lights.strip().upper()
            if _lu == "ON":
                d.lights_on = True
            elif _lu == "OFF":
                d.lights_on = False
        _sun = _open_strict(detail.get("sunroof"))
        if _sun is not None:
            d.sunroof_open = _sun
        _bon = _open_strict(detail.get("bonnet"))  # official "bonnet" → our "hood"
        if _bon is not None:
            d.hood_open = _bon
        if isinstance(status.get("carCapturedTimestamp"), str):
            d.last_seen_at = status["carCapturedTimestamp"]

        # -- odometer ---------------------------------------------------------
        odo = v.get("odometer") or {}
        if isinstance(odo.get("mileageInKm"), (int, float)):
            d.odometer_km = int(odo["mileageInKm"])

        # -- fuel / engine ----------------------------------------------------
        fuel = v.get("fuelStatus") or {}
        if isinstance(fuel.get("carType"), str):
            d.car_type = fuel["carType"]
        if isinstance(fuel.get("totalRangeInKm"), (int, float)):
            d.total_range_km = int(fuel["totalRangeInKm"])
        prim = fuel.get("primaryEngineRange") or {}
        sec = fuel.get("secondaryEngineRange") or {}
        etype = prim.get("engineType")
        if isinstance(etype, str):
            d.primary_engine_type = etype
        _fuel_pct = prim.get("currentFuelLevelInPercent")
        if isinstance(_fuel_pct, (int, float)):
            d.primary_engine_fuel_level_pct = int(_fuel_pct)
            d.fuel_level = int(_fuel_pct)
        _soc_pct = prim.get("currentSoCInPercent")
        if isinstance(_soc_pct, (int, float)):
            # #1310 — apply the SAME combustion fuel-mirror guard as the mysmob path
            # (indigomejor): on a combustion primary engine the backend mirrors the
            # fuel level into currentSoCInPercent, so a "SoC" equal to the fuel level
            # is the fuel duplicated, not a 12V reading. Reuse the one guard so the
            # official channel cannot re-introduce the mirror we fixed on mysmob.
            from .skoda import _primary_soc_or_none  # noqa: PLC0415
            _guarded = _primary_soc_or_none(
                int(_soc_pct),
                int(_fuel_pct) if isinstance(_fuel_pct, (int, float)) else None,
                etype,
            )
            if _guarded is not None:
                d.primary_engine_soc_pct = _guarded
        if isinstance(prim.get("remainingRangeInKm"), (int, float)):
            if isinstance(etype, str) and etype.upper() == "ELECTRIC":
                d.electric_range_km = int(prim["remainingRangeInKm"])
            else:
                d.combustion_range_km = int(prim["remainingRangeInKm"])
        # electric / hybrid classification from the engine mix
        types = {str(t.get("engineType", "")).upper() for t in (prim, sec) if t}
        types.discard("")
        if types == {"ELECTRIC"}:
            d.is_electric = True
        elif "ELECTRIC" in types and len(types) > 1:
            d.is_hybrid = True
        # b7 — AdBlue + the whole secondary engine (a PHEV loses its second engine on
        # an official-only cycle without these). All already in the response.
        if isinstance(fuel.get("adBlueRange"), (int, float)):
            d.adblue_range_km = int(fuel["adBlueRange"])
        _sec_type = sec.get("engineType")
        if isinstance(_sec_type, str):
            d.secondary_engine_type = _sec_type
        if isinstance(sec.get("currentFuelLevelInPercent"), (int, float)):
            d.secondary_engine_fuel_level_pct = int(sec["currentFuelLevelInPercent"])
        if isinstance(sec.get("remainingRangeInKm"), (int, float)):
            d.secondary_engine_range_km = int(sec["remainingRangeInKm"])

        # -- charging ---------------------------------------------------------
        charging = v.get("charging") or {}
        cstat = charging.get("status") or {}
        cset = charging.get("settings") or {}
        cstate = cstat.get("state")
        if isinstance(cstate, str):
            d.charging_state = cstate
            d.is_charging = cstate.strip().upper() in ("CHARGING", "CONSERVING")
        if isinstance(cstat.get("chargePowerInKw"), (int, float)):
            d.charging_power_kw = float(cstat["chargePowerInKw"])
        batt = cstat.get("battery") or {}
        if isinstance(batt.get("stateOfChargeInPercent"), (int, float)):
            d.battery_soc = int(batt["stateOfChargeInPercent"])
            d.has_battery = True
        if isinstance(batt.get("remainingCruisingRangeInMeters"), (int, float)):
            d.electric_range_km = int(batt["remainingCruisingRangeInMeters"] // 1000)
        if isinstance(cset.get("targetStateOfChargeInPercent"), (int, float)):
            d.target_soc = int(cset["targetStateOfChargeInPercent"])
        if isinstance(cset.get("batteryCareModeTargetValueInPercent"), (int, float)):
            d.battery_care_target_soc_pct = int(cset["batteryCareModeTargetValueInPercent"])
        if isinstance(cset.get("preferredChargeMode"), str):
            d.preferred_charge_mode = cset["preferredChargeMode"]
        if isinstance(cset.get("maxChargeCurrentAcAmpere"), (int, float)):
            d.max_charge_current = float(cset["maxChargeCurrentAcAmpere"])
        # b7 — charging status/settings the official parser was dropping (all in the
        # response; on an official-only cycle these entities otherwise go dark).
        _saved = charging.get("isVehicleInSavedLocation")
        if isinstance(_saved, bool):
            d.vehicle_at_saved_location = _saved
        if isinstance(cstat.get("chargingRateInKilometersPerHour"), (int, float)):
            d.charging_rate_kmh = float(cstat["chargingRateInKilometersPerHour"])
        _ctype = drop_charge_sentinel(cstat.get("chargeType"))  # AC/DC, #1104 sentinel
        if isinstance(_ctype, str) and _ctype:
            d.charging_type = _ctype
        _fully = cstat.get("fullyChargedAt")
        if isinstance(_fully, str) and _fully:
            try:
                d.charge_complete_eta = datetime.fromisoformat(
                    _fully.replace("Z", "+00:00"))
            except ValueError:
                pass
        if not d.charge_complete_eta:
            _rem = safe_int(cstat.get("remainingTimeToFullyChargedInMinutes"))
            if _rem:
                d.charge_complete_eta = datetime.now(tz=timezone.utc) + timedelta(
                    minutes=_rem)
        _care = cset.get("chargingCareMode")
        if isinstance(_care, str):
            _cu = _care.strip().upper()
            if _cu in ("ACTIVATED", "ACTIVE", "ON", "TRUE"):
                d.battery_care_enabled = True
            elif _cu in ("DEACTIVATED", "INACTIVE", "OFF", "FALSE"):
                d.battery_care_enabled = False
        _autolock = cset.get("autoUnlockPlugWhenCharged")
        if isinstance(_autolock, str):
            _au = _autolock.strip().upper()
            if _au in ("ON", "PERMANENT", "TRUE", "YES"):
                d.auto_unlock_when_charged = True
            elif _au in ("OFF", "FALSE", "NO"):
                d.auto_unlock_when_charged = False
        _modes = cset.get("availableChargeModes")
        if isinstance(_modes, list) and _modes:
            d.available_charge_modes = [str(m) for m in _modes if m is not None]

        # -- air conditioning / climate --------------------------------------
        ac = v.get("airConditioning") or {}
        if isinstance(ac.get("state"), str):
            d.climatisation_state = ac["state"]
            # spec: OFF | COOLING | HEATING | HEATING_AUXILIARY | VENTILATION |
            # COMPLETED | UNKNOWN — active only while it's actually conditioning.
            d.climatisation_active = ac["state"].strip().upper() in (
                "COOLING", "HEATING", "HEATING_AUXILIARY", "VENTILATION",
            )
            # b7 — coarse aux-heating flag from the AC enum (mirrors mysmob); the
            # dedicated auxiliaryHeating block below refines it when present.
            d.aux_heating_active = (
                ac["state"].strip().upper() == "HEATING_AUXILIARY"
            )
        tt = ac.get("targetTemperature") or {}
        if isinstance(tt.get("value"), (int, float)):
            d.target_temperature = float(tt["value"])
        wh = ac.get("windowHeating") or {}
        _whf = _to_bool_open(wh.get("front"))
        if _whf is not None:
            d.window_heating_front = _whf
        _whr = _to_bool_open(wh.get("rear"))
        if _whr is not None:
            d.window_heating_back = _whr
        # b7 — climate booleans/timestamps the official parser was dropping.
        _whenabled = wh.get("enabled")
        if isinstance(_whenabled, bool):
            d.window_heating_enabled = _whenabled
        _reach = ac.get("estimatedReachOfTargetTemperatureAt")
        if isinstance(_reach, str) and _reach:
            d.climate_ready_at = _reach
        _noext = ac.get("airConditioningWithoutExternalPower")
        if isinstance(_noext, bool):
            d.air_conditioning_without_external_power = _noext
        _atunlock = ac.get("airConditioningAtUnlock")
        if isinstance(_atunlock, bool):
            d.climate_at_unlock = _atunlock

        # -- auxiliary heating / active ventilation (Škoda product gaps) -----
        # Both blocks arrive in the same GET response but the parser dropped them, so
        # the dedicated auxiliary_heating_status sensor and the active-ventilation
        # state/switch read "unknown" on Škoda (they were vw_eu-only). Parse them.
        aux = v.get("auxiliaryHeating") or {}
        _aux_state = aux.get("state")
        if isinstance(_aux_state, str) and _aux_state:
            d.auxiliary_heating_status = _aux_state
            d.aux_heating_active = _aux_state.strip().lower() in (
                "heating", "on", "active", "started", "heatingon",
                "heating_auxiliary",
            )
        vent = v.get("activeVentilation") or {}
        _vent_state = vent.get("state")
        if isinstance(_vent_state, str) and _vent_state:
            d.active_ventilation_state = _vent_state
        _vent_dur = vent.get("durationInSeconds")
        if isinstance(_vent_dur, (int, float)) and not isinstance(_vent_dur, bool):
            d.active_ventilation_remaining_time_min = int(_vent_dur // 60)

        # -- parking position (the GPS the EU-DA channel can't get) ----------
        pos = v.get("parkingPosition") or {}
        gps = pos.get("gpsCoordinates") or {}
        if isinstance(gps.get("latitude"), (int, float)) and isinstance(
            gps.get("longitude"), (int, float)
        ):
            d.latitude = float(gps["latitude"])
            d.longitude = float(gps["longitude"])
        # b7 — the human-readable parking address rides the same block (redacted in
        # diagnostics via _REDACT_KEYS; surfaced as the device_tracker attribute).
        if isinstance(pos.get("formattedAddress"), str) and pos["formattedAddress"]:
            d.parking_address = pos["formattedAddress"]
        return d

    # -- commands -------------------------------------------------------------

    async def _command(self, vin: str, path: str, body: Any = None) -> bool:
        status, resp = await self._post(
            f"vehicles/{vin}/{path}", body, api_key=self._key_for(vin))
        if status in (200, 201, 202, 204):
            return True
        if status == 401:
            raise AuthenticationError("Škoda official API: key rejected (401)")
        raise APIError(status, f"{_BASE}/vehicles/{vin}/{path}", str(resp)[:200])

    async def command_start_charging(self, vin: str) -> bool:
        return await self._command(vin, "charging/start")

    async def command_stop_charging(self, vin: str) -> bool:
        return await self._command(vin, "charging/stop")

    async def command_start_climate(self, vin: str, target_c: float | None = None) -> bool:
        # air-conditioning/start has requestBody required:true; StartAirConditioning
        # Configuration has no required inner field, so an empty {} is a valid
        # instance. Send {} unconditionally — a None body omits the JSON entirely
        # and the server rejects it with 400.
        body: dict[str, Any] = {}
        if target_c is not None:
            body["targetTemperature"] = {"value": target_c, "unit": "CELSIUS"}
        return await self._command(vin, "air-conditioning/start", body)

    async def command_stop_climate(self, vin: str) -> bool:
        return await self._command(vin, "air-conditioning/stop")

    async def command_start_aux_heating(self, vin: str, target_c: float | None = None) -> bool:
        # Privileged: the S-PIN is required in the body.
        if not self._spin:
            raise AuthenticationError(
                "Škoda official API: auxiliary heating requires the vehicle S-PIN"
            )
        body: dict[str, Any] = {"spin": self._spin}
        if target_c is not None:
            body["targetTemperature"] = {"value": target_c, "unit": "CELSIUS"}
        return await self._command(vin, "auxiliary-heating/start", body)

    async def command_stop_aux_heating(self, vin: str) -> bool:
        return await self._command(vin, "auxiliary-heating/stop")

    async def command_start_active_ventilation(self, vin: str) -> bool:
        return await self._command(vin, "active-ventilation/start")

    async def command_stop_active_ventilation(self, vin: str) -> bool:
        return await self._command(vin, "active-ventilation/stop")
