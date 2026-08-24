# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DataPlug / plug&play cloud reader — Audi connect plug&play (acpp) + VW We Connect Go (wcg).

The plug&play apps (``de.audi.connectplugandplay`` / ``de.volkswagen.vwconnect``) pair a
TEXA OBD dongle with OLD cars that have **no built-in connectivity**. Those cars are invisible
to the modern CARIAD BFF and to the EU-Data-Act portal, so this is the ONLY cloud read path for
a dongle-equipped Touareg / e-up! / pre-connectivity A4/A5/Golf, etc.

Auth is a plain OAuth2 ``authorization_code``+PKCE against the VW-Group IDP, exchanged at the
plug&play backend's OWN token endpoint — crucially WITHOUT the Play-Integrity / ``x-qmauth``
attestation the BFF token endpoint requires, and it returns a durable ``refresh_token``.

Coverage / validation
---------------------
* **Audi (acpp)** — LIVE-VALIDATED 2026-08-24 against a real enrolled A5 B8. Reads the
  enroll/sync SNAPSHOT (odometer, 12V battery voltage, fuel litres, service dates, tyres,
  warning lights). NOT the live PIDs — those stay dongle-local (read over Bluetooth).
* **VW (wcg)** — client + endpoints mapped from the APK but the login is NOT wired: it uses
  the LEGACY ``signin-service`` IDP (``identity.legacy.vwgroup.io``), not Auth0, so
  ``IDKAuth.authenticate()`` returns HTTP 400 at the identifier step. TESTER-GATED — see
  ``docs/research/plugandplay_cloud_reader.md`` for the signin-service legs to implement.

The acpp access token is NOT BFF-whitelisted (``emea.bff.cariad.digital`` → 403 "clientId in
the token claim is either unknown or not whitelisted"), so this does not open the modern data
plane — it is its own silo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ..auth.idk import IDKAuth
from ..exceptions import APIError, AuthenticationError
from ..models import BrandConfig, TokenSet, VehicleData

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = ClientTimeout(total=30)

# carport ``brandCode`` → proper manufacturer name (A = Audi, confirmed live).
_ACPP_BRAND_CODES = {"A": "Audi", "V": "Volkswagen"}


def _epoch_ms_to_date(val: Any) -> str | None:
    """acpp carport dates (deliveryDate/warranty) are epoch-millisecond strings.

    Return the ISO date (``YYYY-MM-DD``), or None on anything unparseable.
    """
    try:
        ms = int(str(val))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


class PlugAndPlayCloudClient:
    """Read-only cloud client for the Audi connect plug&play (acpp) backend.

    Interface-compatible with the brand clients the coordinator drives
    (``authenticate()`` + ``get_status(vin)``) so it can be slotted into
    ``api/factory.py`` once a config-flow picker exposes the source. The
    constructor mirrors ``BaseClient.__init__`` — ``(session, brand, email,
    password, spin="")``.
    """

    #: acpp backend that serves BOTH the token exchange and the vehicle data.
    API_BASE = "https://prod.acpp.cariad.digital"

    def __init__(
        self,
        session: ClientSession,
        brand: BrandConfig,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        self._session = session
        self._brand = brand
        self._email = email
        self._password = password
        self._spin = spin  # unused (read-only source); kept for interface parity
        self._tokens: TokenSet | None = None
        # brand.name is deliberately NOT 'audi'/'volkswagen' (see BRAND_AUDI_ACPP)
        # so IDKAuth._exchange_code() takes the plain-OAuth branch (no CARIAD
        # x-qmauth attestation) and honours token_url_override below.
        self._auth = IDKAuth(session, brand, token_url_override=f"{self.API_BASE}/token")

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """Log in (authorization_code+PKCE) and cache the durable token set."""
        self._tokens = await self._auth.authenticate(
            self._email, self._password, mfa_code=mfa_code
        )

    @property
    def tokens(self) -> TokenSet | None:
        return self._tokens

    async def _get(self, path: str) -> tuple[int, Any]:
        if not self._tokens or not self._tokens.access_token:
            raise AuthenticationError("plug&play client is not authenticated")
        headers = {
            "Authorization": f"Bearer {self._tokens.access_token}",
            "Accept": "application/json",
            # The carport (master-data) endpoint 500s without an Accept-Language;
            # all other endpoints ignore it, so send it on every request.
            "Accept-Language": "de-DE, en-US;q=0.9",
            "User-Agent": self._brand.user_agent,
        }
        async with self._session.get(
            f"{self.API_BASE}/{path}", headers=headers, timeout=_TIMEOUT
        ) as resp:
            try:
                body = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001 — error bodies may be text
                body = await resp.text()
            return resp.status, body

    async def get_raw_snapshot(self, vin: str) -> dict[str, Any]:
        """Return the full acpp snapshot for a VIN.

        Only VINs enrolled in THIS account exist; an unknown VIN returns HTTP 404
        ``{"message": "Vehicle with vin ... does not exist"}``. Live engine PIDs
        are never here (dongle-local) — this is the odometer / 12V-battery / fuel /
        service / tyre / warning snapshot the dongle uploads on sync.

        Shape (observed on a real A5 B8, 2026-08-24)::

            {"vehicle": {"vehicle": {"id", "vin", "carPlatform": "KWP2000"},
                         "odometer": 369290.0, "batteryVoltage": 11.76,
                         "tankFuelAmount": 3.0, "registrationDate", "mainCheck",
                         "vehicleSpecificDealer": {...}},
             "tires": [...], "warning_lights": {"warningLights": []},
             "last_parking_position": {"gpsLocation": {...}}, "app_services": {...}}
        """
        status, body = await self._get(f"vehicle/{vin}")
        if status != 200 or not isinstance(body, dict):
            # 404 here specifically means the VIN is not enrolled in THIS account
            # ("Vehicle with vin: '...' does not exist").
            raise APIError(status, f"{self.API_BASE}/vehicle/{vin}", str(body))
        snap: dict[str, Any] = {"vehicle": body}
        # Best-effort sub-resources; a missing one must not fail the whole read.
        for key, sub in (
            ("tires", f"vehicle/{vin}/tires"),
            ("warning_lights", f"vehicle/{vin}/warning-lights"),
            ("last_parking_position", f"vehicle/{vin}/last-parking-position"),
            ("app_services", f"vehicle/{vin}/vehicle_app_services"),
            # carport = factory master data (model, engine, fuel, power) for the
            # proper "ab Haus" model designation.
            ("carport", f"vehicle/{vin}/carport"),
        ):
            try:
                s, b = await self._get(sub)
                if s == 200:
                    snap[key] = b
            except Exception as exc:  # noqa: BLE001 — defence-in-depth
                _LOGGER.debug("plug&play sub-resource %s failed: %s", sub, exc)
        return snap

    async def get_vehicles(self) -> list[str]:
        """Return the VINs enrolled in this account (the coordinator's entry point).

        acpp exposes no per-user ``user/…`` garage resource (all data endpoints
        are VIN-addressed). The enrolled cars are listed by ``GET /vehicles``
        — grounded live against a real account, 2026-08-24 — which returns an
        array of the same snapshot shape as ``vehicle/{vin}``. We take just the
        VINs; the coordinator then calls :meth:`get_status` per car.
        """
        status, body = await self._get("vehicles")
        if status != 200 or not isinstance(body, list):
            return []
        vins: list[str] = []
        for entry in body:
            if not isinstance(entry, dict):
                continue
            vin = (entry.get("vehicle") or {}).get("vin")
            if isinstance(vin, str) and vin:
                vins.append(vin)
        return vins

    async def get_status(self, vin: str) -> VehicleData:
        """Map the acpp snapshot onto :class:`VehicleData` (fields acpp actually provides).

        acpp exposes only a coarse snapshot, so most ``VehicleData`` columns stay
        ``None``. Fields WITHOUT a home in the current model — the 12V
        ``batteryVoltage``, ``tankFuelAmount`` in litres, service/registration dates,
        per-tyre records — are returned by :meth:`get_raw_snapshot` for the
        coordinator to surface. See the mapping TODOs in
        ``docs/research/plugandplay_cloud_reader.md`` (add columns, or expose via
        an extra-attributes dict).
        """
        snap = await self.get_raw_snapshot(vin)
        veh: dict[str, Any] = snap.get("vehicle", {}) or {}
        warnings = (snap.get("warning_lights") or {}).get("warningLights") or []

        data = VehicleData(vin=vin)
        odometer = veh.get("odometer")
        if isinstance(odometer, (int, float)):
            data.odometer_km = int(round(odometer))
        # carPlatform (e.g. "KWP2000") = a pre-connectivity combustion/PHEV car.
        if (veh.get("vehicle") or {}).get("carPlatform"):
            data.has_combustion = True
        data.warning_count = len(warnings)
        data.warning_active = len(warnings) > 0
        my = _vin_model_year(vin)
        if my is not None:
            data.model_year = my

        # 12V battery voltage — the dongle reads the OBD 12V rail on sync
        # (observed 11.76 on the B8). A real reading is a positive float; a
        # missing/zero value means the dongle had no sample.
        bv = veh.get("batteryVoltage")
        if isinstance(bv, (int, float)) and not isinstance(bv, bool) and bv > 0:
            data.voltage_12v = float(bv)

        # Last parking position the dongle uploaded. Some dongles report 0/0
        # ("null island") when they never got a fix — treat that as no position
        # so the device tracker stays unknown instead of pinning to the Atlantic.
        gps = (snap.get("last_parking_position") or {}).get("gpsLocation") or {}
        lat, lon = gps.get("latitude"), gps.get("longitude")
        if (
            isinstance(lat, (int, float)) and not isinstance(lat, bool)
            and isinstance(lon, (int, float)) and not isinstance(lon, bool)
            and (lat, lon) != (0, 0)
        ):
            data.latitude = float(lat)
            data.longitude = float(lon)

        # Absolute fuel in the tank (litres) — the dongle reports litres, not %.
        tank = veh.get("tankFuelAmount")
        if isinstance(tank, (int, float)) and not isinstance(tank, bool) and tank >= 0:
            data.fuel_level_liters = float(tank)

        # Factory ("ab Haus") model designation from the carport master-data
        # record — e.g. brandCode "A" + modelDesc "A5" + engType "TDI CR".
        cp = snap.get("carport") or {}
        if isinstance(cp, dict):
            brand_name = _ACPP_BRAND_CODES.get(str(cp.get("brandCode") or "").upper())
            if brand_name:
                data.manufacturer = brand_name
            desc = str(cp.get("modelDesc") or "").strip()
            eng = str(cp.get("engType") or "").strip()
            hp: int | None = None
            for p in (cp.get("power") or []):
                if (isinstance(p, dict)
                        and str(p.get("unit") or "").lower() in ("hp", "ps")
                        and isinstance(p.get("value"), (int, float))
                        and not isinstance(p.get("value"), bool)):
                    hp = int(round(p["value"]))
            model = " ".join(x for x in (desc, eng) if x)
            if model and hp:
                model = f"{model} · {hp} PS"   # e.g. "A5 TDI CR · 239 PS"
            if model:
                data.model = model
            # deliveryDate = the real first-delivery date (epoch-ms string, e.g.
            # 2008 for this A5) — reliable, unlike the /vehicles registrationDate
            # which is just the dongle-enrollment time. Feeds the service calendar.
            reg = _epoch_ms_to_date(cp.get("deliveryDate"))
            if reg:
                data.registration_date = reg
        return data


class WCGCloudClient(PlugAndPlayCloudClient):
    """VW We Connect Go (wcg) variant — **TESTER-GATED, login NOT wired**.

    Same shape as acpp but the VW backend authenticates against the LEGACY
    ``signin-service`` IDP (``identity.legacy.vwgroup.io``), not Auth0, so
    ``IDKAuth.authenticate()`` returns HTTP 400 at the identifier step. Implement
    the signin-service legs (identifier → authenticate → code, see
    ``auth/_vweu_twoway_login.py``) before enabling.

    Data lives at ``prod.wcg.cariad.digital/vehicles/{vin}/...`` — note the
    ``vehicles`` **plural** and the ``measurements`` / ``warnings`` / ``config`` /
    ``series/measurements`` sub-paths — and the garage is listed via
    ``api/v1/users/{user_id}/vehicles``.
    """

    API_BASE = "https://prod.wcg.cariad.digital"

    async def authenticate(self, mfa_code: str | None = None) -> None:
        raise NotImplementedError(
            "VW We Connect Go uses the legacy signin-service login flow, which is "
            "not implemented yet. See docs/research/plugandplay_cloud_reader.md."
        )


def _vin_model_year(vin: str) -> int | None:
    """Decode SAE VIN position 10 → model year (coarse hint).

    Digits 1-9 map to 2001-2009 (the pre-connectivity era these dongle cars live
    in). Letters A..Y map to 2010..2030. The 2031+ digit reuse is ignored — refine
    in integration if a >2030 car ever appears here.
    """
    if len(vin) < 10:
        return None
    code = vin[9].upper()
    letters = "ABCDEFGHJKLMNPRSTVWXY"  # SAE year letters (no I,O,Q,U,Z)
    if code.isdigit():
        return 2000 + int(code)
    if code in letters:
        return 2010 + letters.index(code)
    return None
