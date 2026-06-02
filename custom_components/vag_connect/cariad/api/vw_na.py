# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Volkswagen North America API client — b-h-s.spr.{country}00.p.con-veh.net.

Endpoints from matpoulin/CarConnectivity-connector-volkswagen-na (Apache-2.0).
Clean-room reimplementation using aiohttp + IDK PKCE auth.
Source: https://github.com/matpoulin/CarConnectivity-connector-volkswagen-na
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from aiohttp import ClientSession

from .._util import mask_vin as _mask_vin
from .._util import safe_float, safe_int
from ..models import VehicleData
from ..exceptions import AuthenticationError, APIError, TokenExpiredError
from ..auth.idk import IDKAuth
from ..models import BrandConfig, TokenSet

_LOGGER = logging.getLogger(__name__)

# Country → API base: US=us, CA=ca
_COUNTRY_BASES: dict[str, str] = {
    "us": "https://b-h-s.spr.us00.p.con-veh.net",
    "ca": "https://b-h-s.spr.ca00.p.con-veh.net",
}

BRAND_VW_NA = BrandConfig(
    name="volkswagen_na",
    client_id="59992128-69a9-42c3-8621-7942041ba824_MYVW_ANDROID",
    redirect_uri="kombi:///login",
    user_agent="MyVW/1.0 Android",
    api_base="https://b-h-s.spr.us00.p.con-veh.net",
    # v2.3.0 (#269 roberttco, 2026-05-21) — single ``openid`` scope per
    # matpoulin/CarConnectivity-connector-volkswagen-na (Apache-2.0).
    # Previously we sent the wider VW EU-style scope chain
    # (``openid profile email offline_access mbb vin cars dealers``)
    # which the NA IDP rejected as part of its HTTP 400 response.
    scope="openid",
)

# v2.3.0 (#269) — VW NA-specific IDP host: identity.na.vwgroup.io
# (NOT identity.vwgroup.io). When the authorize-redirect lands on the
# NA IDP, the signin-service URL uses a hardcoded NA client GUID
# distinct from our API client_id. Per matpoulin's working flow.
_NA_IDP_BASE = "https://identity.na.vwgroup.io"
_NA_SIGNIN_CLIENT_GUID = "b680e751-7e1f-4008-8ec1-3a528183d215@apps_vw-dilab_com"


class VWNAClient:
    """VW North America client.

    Uses a country-specific auth endpoint (b-h-s.spr.{cc}00.p.con-veh.net/oidc/v1/).
    Vehicle data uses UUID (not VIN directly in path) — VIN is mapped after garage fetch.
    """

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
        country: str = "us",
    ) -> None:
        self._session  = session
        self._email    = email
        self._password = password
        self._spin     = spin
        self._country  = country.lower()
        self._base     = _COUNTRY_BASES.get(self._country, _COUNTRY_BASES["us"])
        self._tokens: TokenSet | None = None
        # VW NA uses IDK auth but against a country-specific endpoint
        brand = BrandConfig(
            name=f"volkswagen_{self._country}",
            client_id=BRAND_VW_NA.client_id,
            redirect_uri=BRAND_VW_NA.redirect_uri,
            user_agent=BRAND_VW_NA.user_agent,
            api_base=self._base,
            scope=BRAND_VW_NA.scope,
        )
        # v2.3.0 (#269 roberttco, 2026-05-21) — VW NA auth requires four
        # IDP overrides vs the default identity.vwgroup.io (EU) flow:
        #
        #   1. authorize_url_override → ``{api_base}/oidc/v1/authorize``
        #      (per-country host b-h-s.spr.{us|ca}00.p.con-veh.net,
        #      NOT identity.vwgroup.io). The MYVW_ANDROID client_id is
        #      only registered against this host — sending it to the EU
        #      IDP returns HTTP 400 (user's log on #269).
        #
        #   2. token_url_override → ``{api_base}/oidc/v1/token`` — same
        #      host for both code-exchange and refresh-token calls. The
        #      default fallback (emea.bff.cariad.digital/login/v1/idk/
        #      token) does not know NA client_ids.
        #
        #   3. idk_base_override → identity.na.vwgroup.io. The authorize
        #      step redirects to the NA IDP host, and our resolution of
        #      relative form-actions + the ``Origin`` header must point
        #      at the right base.
        #
        #   4. signin_client_id_override → hardcoded NA GUID
        #      ``b680e751-7e1f-4008-8ec1-3a528183d215@apps_vw-dilab_com``.
        #      The signin-service URL embeds a "browser IDP client" that
        #      is distinct from our "device API client" (MYVW_ANDROID).
        #
        # Source: matpoulin/CarConnectivity-connector-volkswagen-na
        # (Apache-2.0), cited at the top of this file.
        self._auth = IDKAuth(
            session,
            brand,
            authorize_url_override=f"{self._base}/oidc/v1/authorize",
            token_url_override=f"{self._base}/oidc/v1/token",
            idk_base_override=_NA_IDP_BASE,
            signin_client_id_override=_NA_SIGNIN_CLIENT_GUID,
        )
        # UUID cache: VIN → UUID (returned by garage)
        self._vin_to_uuid: dict[str, str] = {}
        # v2.4.1 (#285) — human-friendly metadata from garage payload.
        # vehicleNickName + modelName per matpoulin's response shape.
        # Used by get_status() / device-info to enrich the entity model.
        self._vin_to_nickname: dict[str, str] = {}
        self._vin_to_model: dict[str, str] = {}

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """IDK PKCE login against VW NA endpoint."""
        self._tokens = await self._auth.authenticate(self._email, self._password)
        _LOGGER.debug("VW NA auth complete (%s)", self._country.upper())

    async def get_vehicles(self) -> list[str]:
        """Return VINs from VW NA garage.

        v2.4.1 (#285 roberttco, 2026-05-24) — the actual API response
        shape per matpoulin/CarConnectivity-connector-volkswagen-na
        (the Apache-2.0 reference cited at the top of this file) is:

            {"data": {"vehicles": [{"vin": ..., "vehicleId": ..., ...}]}}

        Our previous parser read ``data.get("vehicles", [])`` (top-
        level), which returned ``[]`` and raised ``ConfigEntryNotReady
        ("No vehicles found")`` even though the auth flow + token
        exchange had succeeded perfectly. roberttco's debug log on #285
        confirmed: full auth chain works, but garage call result was
        treated as empty. Fix: walk through the ``data`` envelope with
        defensive fallback to top-level for forward-compat if VW NA
        ever flattens the shape.

        Bonus per matpoulin: response also carries ``vehicleNickName``
        and ``modelName`` per vehicle — cache them for device-info /
        entity-naming downstream.
        """
        data = await self._get(f"{self._base}/account/v1/garage")
        # Defensive envelope walk: prefer data.data.vehicles (matpoulin
        # confirmed), fall back to data.vehicles (legacy / forward-
        # compat if VW NA flattens), else empty list.
        payload = (
            (data.get("data") or {}).get("vehicles")
            or data.get("vehicles")
            or []
        )
        vins = []
        for vehicle_dict in payload:
            vin = vehicle_dict.get("vin")
            uuid = vehicle_dict.get("uuid") or vehicle_dict.get("vehicleId")
            if vin:
                if uuid:
                    self._vin_to_uuid[vin] = uuid
                # v2.4.1 — cache the human-friendly fields per matpoulin.
                # Surfaced as sensors in v2.4.1 audit (T1 entities).
                nickname = vehicle_dict.get("vehicleNickName")
                if isinstance(nickname, str) and nickname:
                    self._vin_to_nickname[vin] = nickname
                model = vehicle_dict.get("modelName")
                if isinstance(model, str) and model:
                    self._vin_to_model[vin] = model
                vins.append(vin)
                _LOGGER.debug(
                    "VW NA: found VIN %s uuid=%s nickname=%s model=%s",
                    _mask_vin(vin), uuid, nickname, model,
                )
        if not vins and payload == []:
            # Empty envelope OR shape didn't match — log diagnostically
            # so the next user-report includes the actual top-level
            # keys for diagnosis.
            _LOGGER.warning(
                "VW NA garage returned no vehicles (top-level keys=%s) — "
                "if this is unexpected, please open an issue with the "
                "DEBUG log so we can adjust the parser shape",
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
        return vins

    async def get_status(self, vin: str) -> VehicleData:
        """Fetch vehicle status using UUID."""
        v = self._val
        uuid = self._vin_to_uuid.get(vin, vin)
        d = VehicleData(vin=vin, manufacturer="Volkswagen")

        results = await asyncio.gather(
            self._get(f"{self._base}/rvs/v1/vehicle/{uuid}"),
            self._get(f"{self._base}/ev/v1/vehicle/{uuid}/charge/summary"),
            self._get(f"{self._base}/ev/v1/vehicle/{uuid}/climate/summary"),
            return_exceptions=True,
        )
        vehicle_raw, charge, climate = results

        # ── Vehicle status ────────────────────────────────────────────────────
        if isinstance(vehicle_raw, dict):
            power = v(vehicle_raw, "powerStatus") or {}
            d.odometer_km = v(power, "odometer")
            d.fuel_level  = v(power, "fuelPercentRemaining")
            d.range_km    = v(power, "cruiseRange")

            # Battery
            bat = v(vehicle_raw, "batteryStatus") or {}
            d.battery_soc = v(bat, "stateOfChargePercent")
            d.has_battery = d.battery_soc is not None

            # Doors — v2.0.1 (#131 follow-up): defensive parsing.
            # Only assign safety-critical booleans when the source is
            # an actual string; otherwise leave the dataclass default
            # ``None`` so the entity stays "unknown" instead of falsely
            # reporting "Unlocked"/"Closed" for an actually-locked car.
            door_status = v(vehicle_raw, "doorStatus") or {}
            overall_lock = v(door_status, "overallStatus")
            if isinstance(overall_lock, str):
                d.doors_locked = overall_lock.upper() == "LOCKED"
            door_keys = ("frontLeftDoor", "frontRightDoor", "rearLeftDoor", "rearRightDoor")
            door_states = [v(door_status, k) for k in door_keys]
            if any(isinstance(s, str) for s in door_states):
                d.doors_open = any(
                    isinstance(s, str) and s.upper() == "OPEN" for s in door_states
                )
            trunk = v(door_status, "trunk")
            if isinstance(trunk, str):
                d.trunk_open = trunk.upper() == "OPEN"
            hood = v(door_status, "hood")
            if isinstance(hood, str):
                d.hood_open = hood.upper() == "OPEN"

            # Windows — v2.0.1 (#131 follow-up): same defensive shape.
            win = v(vehicle_raw, "windowStatus") or {}
            window_keys = (
                "frontLeftWindow", "frontRightWindow",
                "rearLeftWindow", "rearRightWindow",
            )
            window_states = [v(win, k) for k in window_keys]
            if any(isinstance(s, str) for s in window_states):
                d.windows_open = any(
                    isinstance(s, str) and s.upper() == "OPEN" for s in window_states
                )

            # GPS
            pos = v(vehicle_raw, "vehicleLocation") or {}
            d.latitude  = v(pos, "latitude")
            d.longitude = v(pos, "longitude")

            # Connection — v2.0.1 (#131 follow-up): defensive parsing.
            conn_state = v(vehicle_raw, "connectionStatus", "connectionState")
            if isinstance(conn_state, str):
                d.is_online = conn_state.upper() == "CONNECTED"

            # Drivetrain type
            engine = v(vehicle_raw, "vehicleType", "engine") or ""
            d.is_electric    = engine in ("BEV", "ELECTRIC")
            d.is_hybrid      = engine == "PHEV"
            d.has_battery    = d.is_electric or d.is_hybrid or d.has_battery
            d.has_combustion = engine in ("PHEV", "ICE", "GASOLINE", "DIESEL") or (
                d.fuel_level is not None
            )

            # v2.5.10 (#323 roberttco — 2023 ID.4 US) — populate
            # last_seen_at from the VW NA RVS response. Pre-v2.5.10 we
            # never set this field for VW NA, so the user-visible
            # "Last Update" sensor effectively showed our local poll
            # time instead of when the car actually reported data to
            # the cloud. Defensive parser: VW NA RVS API has shipped at
            # least 4 different timestamp field-name conventions across
            # firmware generations — try them in priority order, first
            # ISO-8601-looking string wins.
            for path in (
                ("vehicleStatusTime",),                  # myVW 2024+
                ("connectionStatus", "lastConnectionTime"),  # legacy myVW
                ("connectionStatus", "timestamp"),
                ("carCapturedTimestamp",),               # CARIAD-aligned newer firmware
                ("powerStatus", "carCapturedTimestamp"), # sub-block timestamp
                ("lastUpdated",),
                ("dataTimestamp",),
            ):
                ts = v(vehicle_raw, *path)
                if isinstance(ts, str) and len(ts) >= 10 and "T" in ts:
                    d.last_seen_at = ts
                    break

        # ── Charging ──────────────────────────────────────────────────────────
        if isinstance(charge, dict):
            d.charging_state    = v(charge, "chargingStatus", "chargingState")
            # v2.0.1 (#131 follow-up) — defensive parsing.
            if isinstance(d.charging_state, str):
                d.is_charging = d.charging_state.upper() == "CHARGING"
            d.charging_power_kw = v(charge, "chargingStatus", "chargePower_kW")
            plug = v(charge, "plugStatus", "plugConnectionState")
            if isinstance(plug, str):
                d.plug_connected = plug.upper() == "CONNECTED"
                d.plug_state = plug
            d.target_soc        = v(charge, "chargingSettings", "targetSOC_pct")
            # v1.24.2 (audit): safe_int + safe_float defensive coerce
            remaining_min = safe_int(v(charge, "chargingStatus", "remainingChargingTimeToComplete_min"))
            if remaining_min is not None and remaining_min > 0:
                d.charge_complete_eta = datetime.now(tz=timezone.utc) + timedelta(minutes=remaining_min)

        # ── Climate ────────────────────────────────────────────────────────────
        if isinstance(climate, dict):
            d.climatisation_state  = v(climate, "climatisationStatus", "climatisationState")
            d.climatisation_active = d.climatisation_state not in (None, "OFF")
            temp_k = safe_float(v(climate, "climatisationSettings", "targetTemperature_K"))
            d.target_temperature = round(temp_k - 273.15, 1) if temp_k is not None else None

        d.is_electric    = d.has_battery and not d.has_combustion
        d.is_hybrid      = d.has_battery and d.has_combustion

        # v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation.
        # VW NA Kombi doesn't ship a direct `carType` enum — derive
        # from has_battery + has_combustion. Never overwrites.
        from .._util import derive_car_type_if_missing  # noqa: PLC0415

        derive_car_type_if_missing(d)

        return d

    async def get_capabilities(self, vin: str) -> dict[str, Any]:  # noqa: ARG002
        """VW NA does not expose a discrete capabilities endpoint.

        Returning ``{}`` keeps the interface consistent with the other
        clients so the coordinator can call this without feature
        detection. Buttons will not be capability-gated for VW NA until
        an endpoint is documented.
        """
        return {}

    async def command_lock(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/lock", json={"action": "lock"})

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        payload: dict[str, Any] = {"action": "unlock"}
        if spin or self._spin:
            payload["spin"] = spin or self._spin
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/lock", json=payload)

    async def command_start_climate(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/start", json={})

    async def command_stop_climate(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/stop", json={})

    async def command_start_charging(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/charging/start", json={})

    async def command_stop_charging(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/charging/stop", json={})

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,  # noqa: ARG002
        longitude: float | None = None,  # noqa: ARG002
    ) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/horn-and-lights", json={"action": "FLASH_ONLY"})

    async def command_wake(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(f"{self._base}/ev/v1/vehicle/{uuid}/wakeup", json={})

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(
            f"{self._base}/ev/v1/vehicle/{uuid}/charging/settings",
            json={"targetSOC_pct": target},
        )

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(
            f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/settings",
            json={"targetTemperature_K": temp_c + 273.15, "tempUnit": "C"},
        )

    async def command_start_window_heating(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(
            f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/windowheating/start", json={}
        )

    async def command_stop_window_heating(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post(
            f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/windowheating/stop", json={}
        )

    async def command_set_departure_timer(
        self,
        vin: str,
        timer_id: int,
        enabled: bool,
        departure_time: str | None,
        recurring_on: list[str] | None = None,
    ) -> None:
        # v2.0.0 (Big-Bang) — VW NA's MyVW Cloud accepts the same
        # ``recurringOn`` field shape as the EU CARIAD-BFF backend
        # (verified against MyVW 2.x app traffic).
        uuid = self._vin_to_uuid.get(vin, vin)
        payload: dict[str, Any] = {"id": timer_id, "enabled": enabled}
        if departure_time:
            payload["departureTime"] = {"time": departure_time}
        if recurring_on:
            valid = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                     "FRIDAY", "SATURDAY", "SUNDAY"}
            cleaned = [d.upper() for d in recurring_on if d.upper() in valid]
            if cleaned:
                payload["recurringOn"] = cleaned
                payload["type"] = "RECURRING"
        await self._post(
            f"{self._base}/ev/v1/vehicle/{uuid}/climatisation/timers",
            json=payload,
        )

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    async def _get(self, url: str, **kwargs: Any) -> Any:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> Any:
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, retry: bool = True, **kwargs: Any) -> Any:
        from aiohttp import ClientTimeout  # noqa: PLC0415
        if not self._tokens:
            raise AuthenticationError("Not authenticated")
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {self._tokens.access_token}",
            "User-Agent":    BRAND_VW_NA.user_agent,
            "Accept":        "application/json",
        })
        async with self._session.request(
            method, url, headers=headers, timeout=ClientTimeout(total=30), **kwargs
        ) as resp:
            if resp.status == 401 and retry:
                await self._refresh()
                return await self._request(method, url, retry=False, **kwargs)
            if resp.status == 204:
                return {}
            if resp.status not in (200, 202, 207):
                body = await resp.text()
                raise APIError(resp.status, url, body)
            return await resp.json()

    async def _refresh(self) -> None:
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
