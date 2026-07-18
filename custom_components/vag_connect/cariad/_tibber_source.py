# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tibber Data API — supplementary EV source (read-only gap-fill).

The Tibber Data API (``data-api.tibber.com``, OAuth2) exposes a paired EV's state
of charge, target SoC, range, plug + charging status via Tibber's *licensed* OEM
access — the commercial channel that outlives the VW direct-API lockdown. It is
brand-agnostic (VW / Audi / Škoda / SEAT / CUPRA, per the account's paired cars)
and strictly **read-only** — no vehicle command exists on any Tibber surface, so
this is a data source only; charge start/stop + target-SoC stay on the OEM side.

We use it as a **lowest-trust gap-fill supplier**: it only fills fields our
first-party channels (MBB / EU-Data-Act portal / authproxy) left ``None``, never
overwrites, and every value it contributes is attributed to the ``tibber``
channel by ``_channel_merge``.

CAVEAT (why lowest priority): Tibber refreshes vehicle telemetry mainly while the
car is connected/charging, so it goes stale when the car is parked and idle. The
merge must therefore never let a stale Tibber value shadow a fresher first-party
reading.

Auth: OAuth2 authorization-code (+PKCE). The user registers a Data API client at
``data-api.tibber.com/clients/manage`` (redirect URI, scopes) and completes the
code exchange in the config flow; this module owns the token REFRESH (rotating
refresh token) + the reads. Scopes are read-only (``data-api-*-read``) — there is
no write/command scope.

Field / capability mapping (from the evcc + HA-core + pyTibber consumers):
  storage.stateOfCharge       -> battery_soc (%)
  storage.targetStateOfCharge -> target_soc (%)
  range.remaining             -> range_km + electric_range_km (metres -> km; mi supported)
  connector.status            -> plug_connected  (== "connected")
  charging.status             -> charging_state + is_charging  (== "charging")
  charging.current.max        -> charge_max_ac_setting (A)
  isOnline                    -> is_online
VIN is NOT a capability — it rides ``device.externalId`` as the ``:``-tail.
GPS / odometer / climate / charge-power(kW) are NOT exposed by Tibber (any surface).
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .models import VehicleData

_LOGGER = logging.getLogger(__name__)

TIBBER_DATA_BASE = "https://data-api.tibber.com/v1"
TIBBER_TOKEN_URL = "https://thewall.tibber.com/connect/token"
TIBBER_AUTHORIZE_URL = "https://thewall.tibber.com/connect/authorize"
# Read-only scopes only — Tibber has no write/command scope for vehicles.
TIBBER_SCOPES = (
    "openid profile email offline_access "
    "data-api-user-read data-api-homes-read data-api-vehicles-read"
)
# Tibber asks every client to send a descriptive User-Agent.
_USER_AGENT = "VWGroupConnectHA/tibber (+home-assistant)"
_TIMEOUT = ClientTimeout(total=20)


def _to_int_pct(value: Any) -> int | None:
    """Coerce a Tibber percentage capability value to a 0-100 int."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= v <= 100:
        return int(round(v))
    return None


def _range_to_km(value: Any, unit: Any) -> int | None:
    """Tibber ``range.remaining`` is metres by default (evcc divides by 1000);
    a ``mi`` unit means miles. Convert either to whole km."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    u = (unit or "").strip().lower()
    if u in ("mi", "mile", "miles"):
        return int(round(v * 1.609344))
    if u in ("km", "kilometre", "kilometer", "kilometres"):
        return int(round(v))
    # default: metres (Tibber's native unit). Guard against an already-km value.
    if v >= 3000:
        return int(round(v / 1000))
    return int(round(v))


def vin_from_external_id(external_id: Any) -> str | None:
    """Tibber encodes VIN as the ``:``-separated tail of ``device.externalId``
    (evcc-proven, e.g. ``tibber:WVWZZZ…``)."""
    if not isinstance(external_id, str) or not external_id.strip():
        return None
    tail = external_id.strip().rsplit(":", 1)[-1].strip()
    # A VW-group VIN is 17 alphanumerics; accept a plausible tail only.
    if 11 <= len(tail) <= 17 and tail.isalnum():
        return tail.upper()
    return None


def map_tibber_device(device: dict[str, Any]) -> VehicleData | None:
    """Map ONE Tibber Data-API vehicle *device detail* to a sparse VehicleData.

    Returns ``None`` if the device is not a vehicle or carries no usable VIN —
    the caller must only merge a VehicleData whose VIN matches an existing car.
    Every field left ``None`` is intentional: the gap-fill merge leaves the rich
    first-party data untouched for those.
    """
    if not isinstance(device, dict):
        return None
    info = device.get("info") or {}
    category = (device.get("category") or info.get("category") or "").lower()
    # Some payloads carry the category on the device, some only imply it via the
    # vehicle capabilities; accept either but never map a non-vehicle.
    caps_list = device.get("capabilities") or []
    caps: dict[str, dict[str, Any]] = {
        c["id"]: c
        for c in caps_list
        if isinstance(c, dict) and isinstance(c.get("id"), str)
    }
    is_vehicle = category == "vehicle" or "storage.stateOfCharge" in caps
    if not is_vehicle:
        return None

    vin = vin_from_external_id(device.get("externalId"))
    if not vin:
        return None

    d = VehicleData(vin=vin)

    def _cap(cid: str) -> tuple[Any, Any]:
        c = caps.get(cid) or {}
        return c.get("value"), c.get("unit")

    soc, _ = _cap("storage.stateOfCharge")
    _soc = _to_int_pct(soc)
    if _soc is not None:
        d.battery_soc = _soc
        d.has_battery = True

    tsoc, _ = _cap("storage.targetStateOfCharge")
    _tsoc = _to_int_pct(tsoc)
    if _tsoc is not None:
        d.target_soc = _tsoc

    rng_v, rng_u = _cap("range.remaining")
    _rng = _range_to_km(rng_v, rng_u)
    if _rng is not None:
        d.range_km = _rng
        d.electric_range_km = _rng
        d.has_battery = True

    conn, _ = _cap("connector.status")
    if isinstance(conn, str) and conn.strip():
        d.plug_connected = conn.strip().lower() == "connected"

    chg, _ = _cap("charging.status")
    if isinstance(chg, str) and chg.strip():
        d.charging_state = chg.strip()
        d.is_charging = chg.strip().lower() == "charging"

    cur, _ = _cap("charging.current.max")
    try:
        if cur is not None:
            d.charge_max_ac_setting = int(round(float(cur)))
    except (TypeError, ValueError):
        pass

    online, _ = _cap("isOnline")
    if isinstance(online, bool):
        d.is_online = online
    elif isinstance(online, str) and online.strip():
        d.is_online = online.strip().lower() in ("true", "online", "1")

    return d


class TibberDataSource:
    """Read-only Tibber Data-API client — fetches paired vehicles, refreshes the
    OAuth2 token, maps each to a sparse VehicleData. Never raises out of
    ``fetch_vehicles`` (a supplementary source must never break the poll)."""

    def __init__(
        self,
        session: ClientSession,
        *,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str = "",
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def refresh_token(self) -> str:
        """The (rotating) refresh token — persist it after each fetch."""
        return self._refresh_token

    async def _refresh(self) -> bool:
        """Rotate the access token. Returns True on success; on failure the
        caller falls back to skipping this poll (no crash)."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret
        try:
            async with self._session.post(
                TIBBER_TOKEN_URL, data=data,
                headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("Tibber token refresh HTTP %s", resp.status)
                    return False
                body = await resp.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Tibber token refresh failed: %s", err)
            return False
        at = body.get("access_token")
        if not isinstance(at, str) or not at:
            return False
        self._access_token = at
        # Tibber rotates the refresh token — keep the new one if present.
        rt = body.get("refresh_token")
        if isinstance(rt, str) and rt:
            self._refresh_token = rt
        return True

    async def _get(self, path: str, *, _retried: bool = False) -> Any:
        try:
            async with self._session.get(
                f"{TIBBER_DATA_BASE}{path}",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "User-Agent": _USER_AGENT,
                },
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 401 and not _retried:
                    if await self._refresh():
                        return await self._get(path, _retried=True)
                    return None
                if resp.status != 200:
                    _LOGGER.debug("Tibber GET %s -> HTTP %s", path, resp.status)
                    return None
                return await resp.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Tibber GET %s failed: %s", path, err)
            return None

    async def fetch_vehicles(self) -> dict[str, VehicleData]:
        """Return ``{vin: sparse VehicleData}`` for every paired vehicle. Empty
        dict on any failure — Tibber is supplementary, never blocks the poll."""
        result: dict[str, VehicleData] = {}
        homes = await self._get("/homes")
        home_list = (homes or {}).get("homes") if isinstance(homes, dict) else homes
        if not isinstance(home_list, list):
            return result
        seen: set[str] = set()
        for home in home_list:
            home_id = home.get("id") if isinstance(home, dict) else None
            if not home_id:
                continue
            devices = await self._get(f"/homes/{home_id}/devices")
            dev_list = (
                (devices or {}).get("devices") if isinstance(devices, dict) else devices
            )
            if not isinstance(dev_list, list):
                continue
            for dev in dev_list:
                dev_id = dev.get("id") if isinstance(dev, dict) else None
                if not dev_id or dev_id in seen:
                    continue
                seen.add(dev_id)
                detail = await self._get(f"/homes/{home_id}/devices/{dev_id}")
                vd = map_tibber_device(detail if isinstance(detail, dict) else dev)
                if vd is not None and vd.vin not in result:
                    result[vd.vin] = vd
        return result
