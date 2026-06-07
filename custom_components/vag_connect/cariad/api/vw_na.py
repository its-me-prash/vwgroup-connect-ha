# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Volkswagen North America API client — b-h-s.spr.{country}00.p.con-veh.net.

Endpoints from matpoulin/CarConnectivity-connector-volkswagen-na (Apache-2.0).
Clean-room reimplementation using aiohttp + IDK PKCE auth.
Source: https://github.com/matpoulin/CarConnectivity-connector-volkswagen-na
"""

from __future__ import annotations

import asyncio
import hashlib
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
    # v2.11.0 (zackcornelius source-verified) - scope must be
    # "openid profile cars vin", not bare "openid". The NA IDP
    # returns reduced consent + missing claims when only "openid"
    # is requested.
    scope="openid profile cars vin",
)

# v2.11.0 (zackcornelius source-verified) - Canada needs its own
# OAuth client_id. matpoulin's old shared client_id worked for some
# accounts but the NA IDP rejects CA accounts that authenticate with
# the US client_id on newer firmware revisions.
_CA_CLIENT_ID = "69eb3c39-d2be-4006-8197-37cc4971e8fe_MYVW_ANDROID"

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
        # VW NA uses IDK auth but against a country-specific endpoint.
        # v2.11.0 - CA gets the dedicated CA client_id per zackcornelius.
        client_id = (
            _CA_CLIENT_ID if self._country == "ca" else BRAND_VW_NA.client_id
        )
        brand = BrandConfig(
            name=f"volkswagen_{self._country}",
            client_id=client_id,
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
        # v2.10.0 (Group C). user_id for the NA-specific endpoints that
        # are addressed by user-id rather than VIN/UUID. Populated from
        # the IDK auth redirect or by decoding the id_token ``sub``
        # claim. Refer to the privileges + SPIN flow comments below for
        # the endpoints that consume it.
        self._user_id: str | None = None

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """IDK PKCE login against VW NA endpoint."""
        self._tokens = await self._auth.authenticate(self._email, self._password)
        # v2.10.0 (Group C). Capture the user_id once auth completes.
        # The NA stack exposes a per-user privileges endpoint and a
        # per-user SPIN-challenge endpoint that both need it; pulling
        # it from the IDK redirect or id_token now avoids re-decoding
        # on every command.
        await self._capture_user_id()
        _LOGGER.debug("VW NA auth complete (%s)", self._country.upper())

    async def _capture_user_id(self) -> None:
        """v2.10.0 (Group C). Populate ``self._user_id``.

        Three-step fallback chain mirrors the SEAT/CUPRA pattern in
        ``seat_cupra._fetch_user_id``:

        1. The IDK redirect-URI scan inside ``IDKAuth`` already records
           a ``user_id`` query-string parameter when the NA IDP includes
           it. Reuse that.
        2. If that didn't fire (NA IDP does not always echo the
           ``user_id`` param), decode the id_token's ``sub`` claim
           locally.
        3. If neither yielded a value, leave ``self._user_id`` as None.
           The privileges + SPIN endpoints simply won't be reachable
           in that case and ``get_subscription_privileges`` returns an
           empty dict so the cross-brand subscription sensors stay at
           ``None`` (phantom-protected).
        """
        if self._auth.user_id:
            self._user_id = self._auth.user_id
            return
        if self._tokens and self._tokens.id_token:
            try:
                import base64  # noqa: PLC0415
                import json as _json  # noqa: PLC0415
                payload_b64 = self._tokens.id_token.split(".")[1]
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
                sub = payload.get("sub")
                if isinstance(sub, str) and sub:
                    self._user_id = sub
            except Exception:  # noqa: BLE001
                _LOGGER.debug("VW NA: could not decode id_token sub claim")

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

    async def get_subscription_privileges(self, vin: str) -> dict[str, Any]:
        """v2.10.0 (Group C). VW NA Cox-backend privileges endpoint.

        ``GET /rrs/v1/privileges/user/{user_id}/vehicle/{uuid}`` returns
        the per-vehicle subscription + capability map for the signed-in
        user. Reference: zackcornelius/CarConnectivity-connector-
        volkswagen-na scan 2026-06-02.

        Response shape (sanitised from the NA app traffic):

            {
              "subscription": {
                "active": true,
                "expiresAt": "2027-08-14T00:00:00Z",
                ...
              },
              "capabilities": {
                "remoteLockUnlock": "ENABLED",
                ...
              }
            }

        Returned dict carries normalised fields the parser drains in
        ``get_status``. Empty dict on any HTTP error so callers stay
        defensive: the cross-brand ``subscription_*`` fields default
        to ``None`` so the gated sensors stay hidden when the call
        fails or the user_id is unavailable.
        """
        if not self._user_id:
            _LOGGER.debug(
                "VW NA: get_subscription_privileges skipped (no user_id captured)"
            )
            return {}
        uuid = self._vin_to_uuid.get(vin, vin)
        url = (
            f"{self._base}/rrs/v1/privileges/user/{self._user_id}"
            f"/vehicle/{uuid}"
        )
        try:
            data = await self._get(url)
        except APIError as err:
            # 401 / 403 / 404 are expected on accounts without an active
            # Car-Net subscription or on legacy firmware that does not
            # expose this endpoint. 5xx is also benign here, the rest
            # of the polling cycle still completes.
            _LOGGER.debug(
                "VW NA privileges fetch returned %s for vin ***%s, "
                "leaving subscription fields at None",
                err.status, vin[-6:],
            )
            return {}
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "VW NA privileges fetch errored for vin ***%s: %s",
                vin[-6:], exc,
            )
            return {}
        if not isinstance(data, dict):
            return {}
        # Walk the optional ``data`` envelope (Cox convention) so the
        # caller sees a flat dict either way.
        nested = data.get("data")
        body: dict[str, Any] = nested if isinstance(nested, dict) else data

        out: dict[str, Any] = {}
        raw_sub = body.get("subscription")
        sub_block: dict[str, Any] = raw_sub if isinstance(raw_sub, dict) else {}
        if not sub_block:
            # Some firmware nests under ``privileges``
            raw_priv = body.get("privileges")
            if isinstance(raw_priv, dict):
                sub_block = raw_priv
        if sub_block:
            # Active flag (multiple key variants observed)
            active: bool | None = None
            raw_active = sub_block.get("active")
            if isinstance(raw_active, bool):
                active = raw_active
            else:
                state = sub_block.get("status") or sub_block.get("state")
                if isinstance(state, str):
                    active = state.upper() in ("ACTIVE", "VALID", "ENABLED")
            if active is not None:
                out["subscription_active"] = active
            # Expiry timestamp (multiple key variants observed)
            expiry = (
                sub_block.get("expiresAt")
                or sub_block.get("expirationDate")
                or sub_block.get("validUntil")
                or sub_block.get("endDate")
            )
            if isinstance(expiry, str) and len(expiry) >= 10 and "T" in expiry:
                out["subscription_expiry_at"] = expiry

        capabilities = body.get("capabilities")
        if isinstance(capabilities, dict) and capabilities:
            # Counted as a diagnostic value, the number of capability
            # flags the backend advertises for this vehicle/user combo.
            # Mirrors the EU CARIAD-BFF ``capabilities_count`` sensor.
            out["capabilities_count"] = len(capabilities)

        return out

    async def get_status(self, vin: str) -> VehicleData:
        """Fetch vehicle status using UUID."""
        v = self._val
        uuid = self._vin_to_uuid.get(vin, vin)
        d = VehicleData(vin=vin, manufacturer="Volkswagen")

        results = await asyncio.gather(
            self._get(f"{self._base}/rvs/v1/vehicle/{uuid}"),
            self._get(f"{self._base}/ev/v1/vehicle/{uuid}/charge/summary"),
            self._get(f"{self._base}/ev/v1/vehicle/{uuid}/climate/summary"),
            self.get_subscription_privileges(vin),
            return_exceptions=True,
        )
        vehicle_raw, charge, climate, privileges = results

        # ── Vehicle status ────────────────────────────────────────────────────
        if isinstance(vehicle_raw, dict):
            power = v(vehicle_raw, "powerStatus") or {}
            # v2.10.0 (#322) — modern VW NA backend ships odometer as a
            # root-level ``currentMileage`` field in addition to (or
            # instead of) the legacy ``powerStatus.odometer`` nested
            # path. Try both, root-level first since that is what
            # current firmware sends.
            d.odometer_km = (
                v(vehicle_raw, "currentMileage")
                or v(power, "odometer")
            )
            d.fuel_level  = v(power, "fuelPercentRemaining")
            # v2.11.0 (zackcornelius source-verified) - cruiseRangeUnits
            # is "KM" or "MI"; pre-v2.11.0 we unconditionally treated
            # the value as km, miles users got their range under-
            # reported by ~38%.
            range_raw = v(power, "cruiseRange")
            range_unit = (v(power, "cruiseRangeUnits") or "KM").upper()
            if isinstance(range_raw, (int, float)):
                if range_unit == "MI":
                    d.range_km = int(range_raw * 1.609344)
                else:
                    d.range_km = int(range_raw)

            # Battery
            bat = v(vehicle_raw, "batteryStatus") or {}
            d.battery_soc = v(bat, "stateOfChargePercent")
            d.has_battery = d.battery_soc is not None

            # v2.10.0 (#322 roberttco — 2023 ID.4 US) — VW NA RVS
            # response shape migration. Pre-v2.10.0 we read doors and
            # windows from ``data.doorStatus`` / ``data.windowStatus``
            # at root, which worked on the 2023-era myVW backend. Newer
            # firmware (and the parallel zackcornelius VW NA work)
            # confirms the modern shape is ``data.exteriorStatus.*``.
            # Try both: root for the legacy install base, exteriorStatus
            # for current firmware. First non-empty wins.
            door_status = (
                v(vehicle_raw, "exteriorStatus", "doorStatus")
                or v(vehicle_raw, "doorStatus")
                or {}
            )
            overall_lock = (
                v(vehicle_raw, "exteriorStatus", "doorLockStatus")
                or v(door_status, "overallStatus")
            )
            if isinstance(overall_lock, str):
                d.doors_locked = overall_lock.upper() == "LOCKED"
            # zackcornelius iterates the doorStatus dict items so
            # firmware-specific door-id sets work without an enum list.
            # We keep both: explicit ID list first for the legacy
            # shape, dict-iteration fallback for the modern one.
            door_keys = ("frontLeftDoor", "frontRightDoor", "rearLeftDoor", "rearRightDoor")
            door_states = [v(door_status, k) for k in door_keys]
            if not any(isinstance(s, str) for s in door_states) and isinstance(door_status, dict):
                door_states = [
                    val for key, val in door_status.items()
                    if key != "doorStatusTimestamp" and val != "NOTAVAILABLE"
                ]
            if any(isinstance(s, str) for s in door_states):
                d.doors_open = any(
                    isinstance(s, str) and s.upper() == "OPEN" for s in door_states
                )
            trunk = v(door_status, "trunk")
            if isinstance(trunk, str):
                d.trunk_open = trunk.upper() == "OPEN"
            hood = v(door_status, "hood") or v(vehicle_raw, "exteriorStatus", "hood")
            if isinstance(hood, str):
                d.hood_open = hood.upper() == "OPEN"

            # v2.10.0 (#322) — Windows, same root + exteriorStatus
            # fallback chain.
            win = (
                v(vehicle_raw, "exteriorStatus", "windowStatus")
                or v(vehicle_raw, "windowStatus")
                or {}
            )
            window_keys = (
                "frontLeftWindow", "frontRightWindow",
                "rearLeftWindow", "rearRightWindow",
            )
            window_states = [v(win, k) for k in window_keys]
            if not any(isinstance(s, str) for s in window_states) and isinstance(win, dict):
                window_states = [
                    val for key, val in win.items()
                    if not key.endswith("Timestamp") and val != "NOTAVAILABLE"
                ]
            if any(isinstance(s, str) for s in window_states):
                d.windows_open = any(
                    isinstance(s, str) and s.upper() == "OPEN" for s in window_states
                )

            # v2.10.0 (#322) — Parking light from exteriorStatus.lightStatus.
            light_status = v(vehicle_raw, "exteriorStatus", "lightStatus")
            if isinstance(light_status, dict):
                # Older firmware reports per-light keys (parkingLight,
                # leftFrontTurnSignal, ...); roll up to a single "any
                # external light on" boolean for the parking_light
                # entity. We pick the parkingLight specifically when
                # present, otherwise fall through to any non-OFF state.
                parking_l = light_status.get("parkingLight")
                if isinstance(parking_l, str):
                    d.parking_light = parking_l.upper() == "ON"
            elif isinstance(light_status, str):
                d.parking_light = light_status.upper() == "ON"

            # GPS — v2.10.0 (#322) — lastParkedLocation fallback for
            # offline cars. Modern VW NA backend caches the last known
            # parking GPS under ``data.lastParkedLocation`` even when
            # the car is OFFLINE and ``vehicleLocation`` is null.
            # v2.11.0 (zackcornelius source-verified) - canonical key
            # is ``location`` (without "vehicle" prefix); kept old key
            # as fallback for any firmware that does ship it.
            pos = (
                v(vehicle_raw, "location")
                or v(vehicle_raw, "vehicleLocation")
                or v(vehicle_raw, "lastParkedLocation")
                or {}
            )
            d.latitude  = v(pos, "latitude")
            d.longitude = v(pos, "longitude")

            # Connection — v2.0.1 (#131 follow-up): defensive parsing.
            # v2.11.0 (zackcornelius source-verified) - canonical online
            # signal is `readiness.readinessStatus.value.connectionState.isOnline`
            # (boolean). Pre-v2.11.0 we read `connectionStatus.connectionState`
            # as a string ("CONNECTED" check) which is a scout-derived
            # guess; the legacy path stays as fallback.
            ready_online = v(
                vehicle_raw, "readiness", "readinessStatus", "value",
                "connectionState", "isOnline",
            )
            if isinstance(ready_online, bool):
                d.is_online = ready_online
            else:
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
            # v2.11.0 (zackcornelius source-verified) - canonical
            # last-seen field on RVS is `data.timestamp` as epoch-ms.
            # Try epoch-ms first then fall back to ISO strings.
            ts_ms = v(vehicle_raw, "timestamp")
            if isinstance(ts_ms, (int, float)) and ts_ms > 1e12:
                from datetime import datetime as _dt2  # noqa: PLC0415
                try:
                    d.last_seen_at = _dt2.fromtimestamp(
                        ts_ms / 1000, tz=timezone.utc
                    ).isoformat()
                except (ValueError, OSError):
                    pass
            ts_clamp = v(vehicle_raw, "clampStateTimestamp")
            if not d.last_seen_at and isinstance(ts_clamp, (int, float)) and ts_clamp > 1e12:
                from datetime import datetime as _dt2  # noqa: PLC0415
                try:
                    d.last_seen_at = _dt2.fromtimestamp(
                        ts_clamp / 1000, tz=timezone.utc
                    ).isoformat()
                except (ValueError, OSError):
                    pass
            if not d.last_seen_at:
                # Note: upstream zackcornelius uses the field name
                # `instrumentCluserTime` (with the typo - missing 't').
                for path in (
                    ("instrumentCluserTime",),
                    ("vehicleStatusTime",),
                    ("connectionStatus", "lastConnectionTime"),
                    ("connectionStatus", "timestamp"),
                    ("carCapturedTimestamp",),
                    ("powerStatus", "carCapturedTimestamp"),
                    ("lastUpdated",),
                    ("dataTimestamp",),
                ):
                    ts = v(vehicle_raw, *path)
                    if isinstance(ts, str) and len(ts) >= 10 and "T" in ts:
                        d.last_seen_at = ts
                        break

        # ── Charging ──────────────────────────────────────────────────────────
        if isinstance(charge, dict):
            # v2.11.0 (zackcornelius source-verified):
            #   currentChargeState (NOT chargingState)
            #   chargePower (NOT chargePower_kW)
            #   chargeSettings.targetSOCPercentage (NOT chargingSettings.targetSOC_pct)
            d.charging_state    = (
                v(charge, "chargingStatus", "currentChargeState")
                or v(charge, "chargingStatus", "chargingState")
            )
            # v2.0.1 (#131 follow-up) — defensive parsing.
            if isinstance(d.charging_state, str):
                d.is_charging = d.charging_state.upper() == "CHARGING"
            d.charging_power_kw = (
                v(charge, "chargingStatus", "chargePower")
                or v(charge, "chargingStatus", "chargePower_kW")
            )
            plug = v(charge, "plugStatus", "plugConnectionState")
            if isinstance(plug, str):
                d.plug_connected = plug.upper() == "CONNECTED"
                d.plug_state = plug
            d.target_soc = (
                v(charge, "chargeSettings", "targetSOCPercentage")
                or v(charge, "chargingSettings", "targetSOC_pct")
            )
            # v2.11.0 (zackcornelius source-verified): battery_soc lives
            # on the charging endpoint at chargingStatus.currentSOCPct,
            # NOT on the RVS endpoint (we attempted to read it from the
            # wrong endpoint before).
            soc_charge = v(charge, "chargingStatus", "currentSOCPct")
            if isinstance(soc_charge, (int, float)) and d.battery_soc is None:
                d.battery_soc = int(soc_charge)
            # v1.24.2 (audit): safe_int + safe_float defensive coerce
            remaining_min = safe_int(v(charge, "chargingStatus", "remainingChargingTimeToComplete_min"))
            if remaining_min is not None and remaining_min > 0:
                d.charge_complete_eta = datetime.now(tz=timezone.utc) + timedelta(minutes=remaining_min)

        # ── Climate ────────────────────────────────────────────────────────────
        # v2.10.0 (#322 roberttco) — VW NA climate response uses the
        # ``climateStatusReport`` / ``climateSettings`` naming instead of
        # the EU-style ``climatisationStatus`` / ``climatisationSettings``
        # that the pre-v2.10.0 parser looked for. Try the NA naming
        # first (current backend), fall back to the EU naming for any
        # legacy install that still ships the older shape.
        if isinstance(climate, dict):
            d.climatisation_state = (
                # v2.11.0 (zackcornelius source-verified) - canonical
                # key is `climateStatusInd` (NOT climateState).
                v(climate, "climateStatusReport", "climateStatusInd")
                or v(climate, "climateStatusReport", "climateState")
                or v(climate, "climateStatusReport", "state")
                or v(climate, "climatisationStatus", "climatisationState")
            )
            d.climatisation_active = d.climatisation_state not in (None, "OFF", "off")
            # Settings block: target temperature. NA backend reports
            # this in either Celsius (modern firmware on ID.4) or
            # Fahrenheit + Kelvin depending on the user's app preference.
            settings = (
                v(climate, "climateSettings")
                or v(climate, "climatisationSettings")
                or {}
            )
            if isinstance(settings, dict):
                # Try Celsius first (already converted), then Kelvin (EU
                # historical), then Fahrenheit (NA user-pref case).
                temp_c = settings.get("targetTemperatureInCelsius")
                if isinstance(temp_c, (int, float)):
                    d.target_temperature = float(temp_c)
                else:
                    temp_k_val = settings.get("targetTemperature_K") or settings.get(
                        "targetTemperatureInKelvin"
                    )
                    temp_k = safe_float(temp_k_val) if temp_k_val is not None else None
                    if temp_k is not None and temp_k > 200:
                        d.target_temperature = round(temp_k - 273.15, 1)
                    else:
                        temp_f = settings.get("targetTemperatureInFahrenheit")
                        if isinstance(temp_f, (int, float)):
                            d.target_temperature = round((temp_f - 32) * 5 / 9, 1)

        d.is_electric    = d.has_battery and not d.has_combustion
        d.is_hybrid      = d.has_battery and d.has_combustion

        # v2.10.0 (Group C). Privileges + subscription block.
        # Soft-fail by design (see get_subscription_privileges docstring):
        # any HTTP error returned an empty dict so we just skip the
        # parser block here. The cross-brand sensors (subscription_*,
        # capabilities_count) stay None / hidden when this dict is empty
        # because of the existing phantom-protection gate.
        if isinstance(privileges, dict) and privileges:
            if privileges.get("subscription_active") is not None:
                d.subscription_active = privileges["subscription_active"]
            if privileges.get("subscription_expiry_at"):
                d.subscription_expiry_at = privileges["subscription_expiry_at"]
                # Derive days-remaining from the timestamp so HA can render
                # a "Connect renews in N days" sensor. Same calculation as
                # the SEAT/CUPRA + VW EU branches.
                try:
                    exp_dt = datetime.fromisoformat(
                        privileges["subscription_expiry_at"].replace("Z", "+00:00")
                    )
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(tz=timezone.utc)
                    d.subscription_days_remaining = (exp_dt - now_utc).days
                    # If the privileges payload omitted the active flag,
                    # derive it from the expiry: past = False, future = True.
                    if d.subscription_active is None:
                        d.subscription_active = exp_dt > now_utc
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "VW NA: could not parse subscription expiry %s (%s)",
                        privileges["subscription_expiry_at"], exc,
                    )
            cap_count = privileges.get("capabilities_count")
            if isinstance(cap_count, int) and cap_count >= 0:
                d.capabilities_count = cap_count

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

    async def _get_na_spin_session_token(
        self, vin: str, spin: str  # noqa: ARG002
    ) -> str | None:
        """v2.10.0 (Group C). VW NA two-step SPIN verification.

        NA uses a DIFFERENT SPIN protocol from EU. The EU flow puts the
        raw SPIN into the action payload; NA requires a challenge /
        response handshake against a per-user endpoint:

            1. ``POST /ss/v1/user/{user_id}/challenge`` returns a
               single-use ``nonce``/``challenge`` string.
            2. Compute ``SHA1(spin + nonce).upper()`` as the response.
            3. ``POST /ss/v1/user/{user_id}/spin`` with the response.
               On success the backend returns a short-lived
               ``sessionToken`` that subsequent lock/unlock POSTs must
               present as the ``X-Spin-Session`` header.

        Pattern verified against the matpoulin reference + a smali
        excerpt from the MyVW APK. Both ``challenge`` and ``response``
        key names have shipped, defensive walk tries the known variants.

        Returns ``None`` on any error. Caller falls back to attempting
        the action without a session token (some firmware will still
        accept a privileged token unprompted).
        """
        if not self._user_id or not spin:
            _LOGGER.debug(
                "VW NA SPIN flow skipped (user_id=%s, spin_set=%s)",
                bool(self._user_id), bool(spin),
            )
            return None
        try:
            challenge_resp = await self._post(
                f"{self._base}/ss/v1/user/{self._user_id}/challenge", json={}
            )
        except APIError as err:
            _LOGGER.debug(
                "VW NA SPIN challenge failed (%s) for vin ***%s",
                err.status, vin[-6:],
            )
            return None
        if not isinstance(challenge_resp, dict):
            return None
        # Defensive walk: backend has shipped at least 3 key names for
        # the same field over the past 18 months.
        nonce = (
            challenge_resp.get("challenge")
            or challenge_resp.get("nonce")
            or challenge_resp.get("challengeData")
        )
        if not isinstance(nonce, str) or not nonce:
            return None
        # v2.11.0 (zackcornelius source-verified) - the SPIN hash is
        # SHA-512 of ``"{challenge}.{spin}"`` (challenge first, then
        # the dot separator, then the spin), NOT SHA-1 of (spin+nonce).
        # Try the modern shape first; fall back to legacy SHA-1 if
        # the modern path returns 4xx (kept so users whose accounts
        # still respond to the old algorithm don't regress).
        response = hashlib.sha512(
            f"{nonce}.{spin}".encode("utf-8")
        ).hexdigest().upper()
        response_legacy = hashlib.sha1(  # noqa: S324
            (spin + nonce).encode("utf-8")
        ).hexdigest().upper()
        # v2.11.0 - try modern (SHA-512) first; on 4xx fall back to
        # legacy (SHA-1) which the older endpoint still expects on
        # some firmwares.
        spin_resp = None
        try:
            spin_resp = await self._post(
                f"{self._base}/ss/v1/user/{self._user_id}/spin",
                json={"challenge": nonce, "response": response},
            )
        except APIError as err:
            if 400 <= (err.status or 0) < 500:
                try:
                    spin_resp = await self._post(
                        f"{self._base}/ss/v1/user/{self._user_id}/spin",
                        json={"challenge": nonce, "response": response_legacy},
                    )
                except APIError as legacy_err:
                    _LOGGER.debug(
                        "VW NA SPIN both modern + legacy failed (%s/%s) for vin ***%s",
                        err.status, legacy_err.status, vin[-6:],
                    )
                    return None
            else:
                _LOGGER.debug(
                    "VW NA SPIN POST failed (%s) for vin ***%s",
                    err.status, vin[-6:],
                )
                return None
        if not isinstance(spin_resp, dict):
            return None
        # v2.11.0 (zackcornelius source-verified) - canonical token
        # field is `carnetVehicleToken` (NOT sessionToken). Kept the
        # other variants as defensive fallbacks for non-canonical
        # firmware responses.
        token = (
            spin_resp.get("carnetVehicleToken")
            or spin_resp.get("sessionToken")
            or spin_resp.get("spinSessionToken")
            or spin_resp.get("token")
        )
        if isinstance(token, str) and token:
            return token
        return None

    async def _post_with_ab_fallback(
        self,
        *,
        primary_url: str,
        primary_json: dict[str, Any] | None,
        fallback_url: str,
        fallback_json: dict[str, Any] | None,
        label: str,
        vin: str,
        primary_headers: dict[str, str] | None = None,
        fallback_headers: dict[str, str] | None = None,
    ) -> None:
        """v2.10.0 (Group C). Generic A/B fallback POST.

        Mirrors the v1.17.1 SEAT/CUPRA pattern. Try ``primary_url`` first.
        On 404 only, fall back to ``fallback_url``. Non-404 errors
        propagate so the caller can surface auth / SPIN / privilege
        problems instead of masking them as endpoint drift.
        """
        primary_kwargs: dict[str, Any] = {"json": primary_json}
        if primary_headers:
            primary_kwargs["headers"] = primary_headers
        try:
            await self._post(primary_url, **primary_kwargs)
            return
        except APIError as err:
            if err.status != 404:
                raise
            _LOGGER.debug(
                "VW NA %s: 404 on primary %s, falling back to legacy %s "
                "(vin ***%s)",
                label, primary_url, fallback_url, vin[-6:],
            )
        fallback_kwargs: dict[str, Any] = {"json": fallback_json}
        if fallback_headers:
            fallback_kwargs["headers"] = fallback_headers
        await self._post(fallback_url, **fallback_kwargs)

    async def command_lock(self, vin: str) -> None:
        """v2.10.0 (Group C). NA lockunlock endpoint with EU fallback.

        Modern Cox firmware exposes ``/lockunlock/v1/vehicle/{uuid}``
        as the lock/unlock action endpoint. Older firmware (legacy
        Cox) only knows ``/ev/v1/vehicle/{uuid}/lock``. Try the
        modern path first, fall back to the legacy one on 404 so
        existing installs keep working through the firmware
        transition window.
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post_with_ab_fallback(
            primary_url=f"{self._base}/lockunlock/v1/vehicle/{uuid}",
            primary_json={"action": "lock"},
            fallback_url=f"{self._base}/ev/v1/vehicle/{uuid}/lock",
            fallback_json={"action": "lock"},
            label="lock",
            vin=vin,
        )

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        """v2.10.0 (Group C). NA unlock with two-step SPIN handshake.

        Pre-v2.10.0 we put the SPIN directly into the unlock body which
        worked for some firmware but failed on Cox post-2024 builds. NA
        actually requires the two-step ``/challenge`` + ``/spin``
        handshake to obtain a session token, then the unlock POST
        carries that token as an ``X-Spin-Session`` header. The body
        no longer needs to contain the SPIN itself.

        If the SPIN session token cannot be fetched (no user_id, no
        SPIN configured, backend down), we fall back to the legacy
        in-body SPIN behaviour so existing accounts that worked on
        older firmware keep working.
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        spin_to_use = spin or self._spin
        session_token = await self._get_na_spin_session_token(vin, spin_to_use)

        primary_headers: dict[str, str] | None = None
        if session_token:
            primary_headers = {"X-Spin-Session": session_token}

        primary_payload: dict[str, Any] = {"action": "unlock"}
        legacy_payload: dict[str, Any] = {"action": "unlock"}
        # Legacy path keeps the in-body SPIN for older Cox firmware
        # that doesn't honour the X-Spin-Session header.
        if spin_to_use:
            legacy_payload["spin"] = spin_to_use

        await self._post_with_ab_fallback(
            primary_url=f"{self._base}/lockunlock/v1/vehicle/{uuid}",
            primary_json=primary_payload,
            fallback_url=f"{self._base}/ev/v1/vehicle/{uuid}/lock",
            fallback_json=legacy_payload,
            label="unlock",
            vin=vin,
            primary_headers=primary_headers,
        )

    async def command_start_climate(self, vin: str) -> None:
        """v2.10.0 (Group C). NA pretripclimate naming, EU fallback.

        NA's Cox backend uses the explicit ``/pretripclimate/start``
        path. We already used this path pre-v2.10.0, but some users
        with older firmware reported it returning 404. In that case
        we fall back to the EU-style ``/climatisation/start`` which
        the legacy Cox build accepts as an alias.
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post_with_ab_fallback(
            primary_url=f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/start",
            primary_json={},
            fallback_url=f"{self._base}/ev/v1/vehicle/{uuid}/climatisation/start",
            fallback_json={},
            label="start_climate",
            vin=vin,
        )

    async def command_stop_climate(self, vin: str) -> None:
        """v2.10.0 (Group C). See command_start_climate for the A/B rationale."""
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post_with_ab_fallback(
            primary_url=f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/stop",
            primary_json={},
            fallback_url=f"{self._base}/ev/v1/vehicle/{uuid}/climatisation/stop",
            fallback_json={},
            label="stop_climate",
            vin=vin,
        )

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
        """v2.10.0 (Group C). Dedicated NA windowheating endpoint.

        ``/pretripclimate/windowheating/start`` is the NA-specific path
        (verified against the zackcornelius reference). Older firmware
        only exposed ``/climatisation/windowheating/start``; try the
        NA path first, fall back on 404.
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post_with_ab_fallback(
            primary_url=(
                f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/windowheating/start"
            ),
            primary_json={},
            fallback_url=(
                f"{self._base}/ev/v1/vehicle/{uuid}/climatisation/windowheating/start"
            ),
            fallback_json={},
            label="start_window_heating",
            vin=vin,
        )

    async def command_stop_window_heating(self, vin: str) -> None:
        """v2.10.0 (Group C). See command_start_window_heating doc."""
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._post_with_ab_fallback(
            primary_url=(
                f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/windowheating/stop"
            ),
            primary_json={},
            fallback_url=(
                f"{self._base}/ev/v1/vehicle/{uuid}/climatisation/windowheating/stop"
            ),
            fallback_json={},
            label="stop_window_heating",
            vin=vin,
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
