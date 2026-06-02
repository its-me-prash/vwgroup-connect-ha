# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Porsche Connect API client — api.ppa.porsche.com.

Endpoints from CJNE/pyporscheconnectapi (Apache-2.0).
Clean-room reimplementation using aiohttp.
Source: https://github.com/CJNE/pyporscheconnectapi
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .._util import mask_vin as _mask_vin
from ..auth.porsche import PorscheAuth
from ..exceptions import APIError, AuthenticationError, TokenExpiredError
from ..models import VehicleData, TokenSet

_LOGGER = logging.getLogger(__name__)

_API_BASE   = "https://api.ppa.porsche.com"
_X_CLIENT   = "41843fb4-691d-4970-85c7-2673e8ecef40"
_USER_AGENT = "My Porsche/2.1.0 (iPhone; iOS 17.0; Scale/3.00)"

# v1.25.0 PR-B: storm-protection constants (mirror of base.py)
_REFRESH_MAX_PER_HOUR = 3
_REFRESH_WINDOW_S = 3600


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

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """Auth0 PKCE login."""
        self._tokens = await self._auth.authenticate(self._email, self._password)
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
        """Fetch full vehicle status from Porsche API."""
        v = self._val
        d = VehicleData(vin=vin)

        # Fetch vehicle details + measurements in parallel
        results = await asyncio.gather(
            self._get(f"{_API_BASE}/app/connect/v1/vehicles/{vin}"),
            self._get(f"{_API_BASE}/app/connect/v1/vehicles/{vin}/measurements", params={
                "fields": ",".join([
                    "BATTERY_LEVEL", "E_RANGE", "FUEL_LEVEL", "MILEAGE",
                    "CHARGING_SUMMARY", "CHARGING_STATE", "CLIMATIZER_STATE",
                    "GPS_LOCATION", "LOCK_STATE_VEHICLE", "OPEN_STATE_DOOR_FRONT_LEFT",
                    "OPEN_STATE_DOOR_FRONT_RIGHT", "OPEN_STATE_DOOR_REAR_LEFT",
                    "OPEN_STATE_DOOR_REAR_RIGHT", "OPEN_STATE_LID_FRONT",
                    "OPEN_STATE_LID_REAR", "OPEN_STATE_SUNROOF",
                    "MAIN_SERVICE_RANGE", "OIL_SERVICE_RANGE",
                    # v2.0.0 (Big-Bang) — TPMS, parsed below into the
                    # tire_pressure_* fields on VehicleData.
                    "TIRE_PRESSURE",
                ])
            }),
            return_exceptions=True,
        )
        vehicle_data, measurements = results

        # ── Vehicle meta ─────────────────────────────────────────────────────
        if isinstance(vehicle_data, dict):
            d.model        = vehicle_data.get("modelName")
            d.model_year   = v(vehicle_data, "modelType", "year")
            d.manufacturer = "Porsche"
            engine = v(vehicle_data, "modelType", "engine", default="")
            d.is_electric    = engine == "BEV"
            d.is_hybrid      = engine == "PHEV"
            d.has_battery    = engine in ("BEV", "PHEV")
            d.has_combustion = engine in ("PHEV", "COMBUSTION")

        # ── Measurements ──────────────────────────────────────────────────────
        if isinstance(measurements, (list, dict)):
            m = {item["key"]: item.get("value", {}) for item in (measurements if isinstance(measurements, list) else [])}

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
            d.odometer_km   = v(m, "MILEAGE", "mileage")

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
            d.target_soc        = v(ch, "targetSoc")

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
        await self._command(vin, "LOCK")

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        await self._command(vin, "UNLOCK")

    async def command_start_climate(self, vin: str) -> None:
        await self._command(vin, "REMOTE_CLIMATIZER_START")

    async def command_stop_climate(self, vin: str) -> None:
        await self._command(vin, "REMOTE_CLIMATIZER_STOP")

    async def command_start_charging(self, vin: str) -> None:
        await self._command(vin, "DIRECT_CHARGING_START")

    async def command_stop_charging(self, vin: str) -> None:
        await self._command(vin, "DIRECT_CHARGING_STOP")

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,  # noqa: ARG002
        longitude: float | None = None,  # noqa: ARG002
    ) -> None:
        await self._command(vin, "HONK_FLASH")

    async def command_wake(self, vin: str) -> None:
        # Porsche doesn't have a dedicated wake — flash serves as ping
        await self._command(vin, "HONK_FLASH")

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        await self._post(
            f"{_API_BASE}/app/connect/v1/vehicles/{vin}/commands",
            json={"commandName": "CHARGING_SETTINGS_EDIT", "payload": {"targetSoc": target}},
        )

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        await self._post(
            f"{_API_BASE}/app/connect/v1/vehicles/{vin}/commands",
            json={"commandName": "REMOTE_CLIMATIZER_START", "payload": {"temperature": temp_c}},
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
        await self._post(
            f"{_API_BASE}/app/connect/v1/vehicles/{vin}/commands",
            json={"commandName": "DEPARTURES_EDIT" if enabled else "TIMERS_DISABLE", "payload": payload},
        )

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    async def _command(self, vin: str, command: str, payload: dict | None = None) -> None:
        await self._post(
            f"{_API_BASE}/app/connect/v1/vehicles/{vin}/commands",
            json={"commandName": command, **(payload or {})},
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
                    wait = (2 ** _attempt) * 5
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
            raise APIError(0, url, f"transient: {type(err).__name__}: {err}") from err

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
