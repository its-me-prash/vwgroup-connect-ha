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

from typing import Any

from aiohttp import ClientSession, ClientTimeout

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


class SkodaOfficialClient:
    """Read + command client for the official Škoda public API (opt-in)."""

    def __init__(
        self,
        session: ClientSession,
        email: str,          # factory ``email`` slot = comma-separated VIN(s)
        password: str,       # factory ``password`` slot = the X-API-Key
        spin: str = "",
    ) -> None:
        self._session = session
        self._api_key = (password or "").strip()
        self._vins = [v.strip().upper() for v in (email or "").split(",") if v.strip()]
        self._spin = (spin or "").strip()
        # Populated from every response's RateLimit-Remaining header; None until
        # the first call. The coordinator reads this to pace itself (20/hour/key).
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset_s: int | None = None

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

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AuthenticationError("Škoda official API: no API key configured")
        return {
            "X-API-Key": self._api_key,
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }

    def _note_rate_limit(self, resp: Any) -> None:
        rem = resp.headers.get("RateLimit-Remaining")
        rst = resp.headers.get("RateLimit-Reset")
        if rem is not None and str(rem).lstrip("-").isdigit():
            self.rate_limit_remaining = int(rem)
        if rst is not None and str(rst).lstrip("-").isdigit():
            self.rate_limit_reset_s = int(rst)

    async def _request(self, method: str, path: str, json_body: Any = None) -> tuple[int, Any]:
        async with self._session.request(
            method, f"{_BASE}/{path}", headers=self._headers(),
            json=json_body, timeout=_TIMEOUT,
        ) as resp:
            self._note_rate_limit(resp)
            try:
                body = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001 — problem+json / text on errors
                body = await resp.text()
            return resp.status, body

    async def _get(self, path: str) -> tuple[int, Any]:
        return await self._request("GET", path)

    async def _post(self, path: str, json_body: Any = None) -> tuple[int, Any]:
        return await self._request("POST", path, json_body)

    # -- reads ----------------------------------------------------------------

    async def get_vehicles(self) -> list[str]:
        """The API has no list endpoint — the key is vehicle-bound, so return the
        VIN(s) the user configured for this key."""
        return list(self._vins)

    async def get_status(self, vin: str) -> VehicleData:
        status, body = await self._get(f"vehicles/{vin}")
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
        if isinstance(prim.get("currentFuelLevelInPercent"), (int, float)):
            d.primary_engine_fuel_level_pct = int(prim["currentFuelLevelInPercent"])
            d.fuel_level = int(prim["currentFuelLevelInPercent"])
        if isinstance(prim.get("currentSoCInPercent"), (int, float)):
            d.primary_engine_soc_pct = int(prim["currentSoCInPercent"])
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

        # -- air conditioning / climate --------------------------------------
        ac = v.get("airConditioning") or {}
        if isinstance(ac.get("state"), str):
            d.climatisation_state = ac["state"]
            # spec: OFF | COOLING | HEATING | HEATING_AUXILIARY | VENTILATION |
            # COMPLETED | UNKNOWN — active only while it's actually conditioning.
            d.climatisation_active = ac["state"].strip().upper() in (
                "COOLING", "HEATING", "HEATING_AUXILIARY", "VENTILATION",
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

        # -- parking position (the GPS the EU-DA channel can't get) ----------
        pos = v.get("parkingPosition") or {}
        gps = pos.get("gpsCoordinates") or {}
        if isinstance(gps.get("latitude"), (int, float)) and isinstance(
            gps.get("longitude"), (int, float)
        ):
            d.latitude = float(gps["latitude"])
            d.longitude = float(gps["longitude"])
        return d

    # -- commands -------------------------------------------------------------

    async def _command(self, vin: str, path: str, body: Any = None) -> bool:
        status, resp = await self._post(f"vehicles/{vin}/{path}", body)
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
        body: dict[str, Any] = {}
        if target_c is not None:
            body["targetTemperature"] = {"value": target_c, "unit": "CELSIUS"}
        return await self._command(vin, "air-conditioning/start", body or None)

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
