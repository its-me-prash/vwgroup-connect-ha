# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda API client — mysmob.api.connect.skoda-auto.cz.

API endpoints verified against skodaconnect/myskoda (MIT) model classes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import uuid
from typing import Any

from aiohttp import ClientSession

from .._util import (
    first_not_none,
    compose_workshop_address,
    compute_connection_state,
    days_or_date_to_iso,
    drop_charge_sentinel,
    drop_odometer_sentinel,
    normalize_workshop_string,
    safe_float,
    safe_int,
    workshop_phone_from_contact,
)
from ..exceptions import APIError, AuthenticationError
from ..models import BRAND_SKODA, VehicleData
from .base import CariadBaseClient

_LOGGER = logging.getLogger(__name__)
_BASE = "https://mysmob.api.connect.skoda-auto.cz"

# Official public-API key management (mysmob BFF, RE'd from MyŠkoda 8.16 —
# cz.myskoda.api.bff_public_api_keys.v2), path /api/v2/public-api-keys. Rides the
# same mysmob Bearer this client already holds. POST creates a key (returns the
# secret once), GET lists remaining quota per VIN, DELETE removes one by id. Keys
# are VIN-bound; max 5 per VIN. Path inlined at each call site (literal, so the
# Bruno drift-check resolves it) — kept here for documentation.
_OFFICIAL_KEY_NAME = "Home Assistant (vag_connect)"
# The key-management route is only exercised by the MyŠkoda app (v8.16+); spoof the
# real app User-Agent on these calls so a possible min-app-version gate is satisfied
# (verbatim from the 8.16 APK; MySkoda/Android/{versionName}/{versionCode}).
_KEYGEN_USER_AGENT = "MySkoda/Android/8.16.0/260821007"

# driving-range.carType enum values that are pure-combustion (no HV battery, no
# plug). EVs report "electric", PHEVs "hybrid" — deliberately absent, so a plug-in
# car is NEVER matched. Used to skip the battery-only /charging read on a confirmed
# combustion Škoda (stops the permanent 403 storm — a diesel Octavia reported this
# via the HA Tipps und Tricks Facebook group).
_COMBUSTION_ONLY_CAR_TYPES = frozenset({"diesel", "gasoline", "petrol", "cng", "gas"})
_CHARGING_SKIPPED: object = object()  # sentinel: /charging deliberately not attempted


async def _skipped_charging() -> object:
    """Placeholder awaitable so the /charging slot keeps its gather index when the
    read is skipped on a combustion car (performs no network I/O)."""
    return _CHARGING_SKIPPED


def parse_skoda_warning_lights(lights: Any) -> dict[str, Any]:
    """Reduce a Škoda health `warningLights` list to warning flags.

    #649 (source-verified against MySkoda "Vehicle Health Report"):
    the health endpoint returns ONE entry per monitored category
    (ENGINE/BRAKES/TYRE/…) whether or not a defect exists — a healthy
    car still has a full list, each entry with an EMPTY `defects` array.
    So "list is non-empty" does NOT mean "something is wrong". A category
    counts as a real warning only when its own `defects` list is
    non-empty. `warning_active`/`warning_count` therefore key off the set
    of *defective* categories, not the raw list length. An all-good car
    (every `defects` empty) yields all-False, matching the app's
    "All good" state.

    Returns a dict of the fields to assign onto VehicleData; empty dict
    when there's nothing usable to parse.
    """
    if not isinstance(lights, list) or not lights:
        return {}
    warning_messages: list[str] = []
    defective_categories: set[str] = set()
    for light in lights:
        if not isinstance(light, dict):
            continue
        cat = str(light.get("category", "")).upper()
        defects = light.get("defects") or []
        if not isinstance(defects, list) or not defects:
            # Category present but healthy — no defect. Do NOT flag.
            continue
        if cat:
            defective_categories.add(cat)
        for defect in defects:
            if isinstance(defect, dict):
                text = defect.get("text") or ""
                if isinstance(text, str) and text:
                    warning_messages.append(text)
    result: dict[str, Any] = {
        "warning_active": bool(defective_categories),
        "warning_count": len(defective_categories),
        "warning_engine": "ENGINE" in defective_categories,
        "warning_brakes": (
            "BRAKES" in defective_categories or "BRAKE" in defective_categories
        ),
        "warning_tyre": (
            "TYRE" in defective_categories or "TIRE" in defective_categories
        ),
        "warning_oil": (
            "OIL" in defective_categories or "FLUID" in defective_categories
        ),
    }
    if warning_messages:
        result["warning_messages"] = " | ".join(warning_messages[:5])
    return result


class SkodaClient(CariadBaseClient):
    """Škoda API client."""

    def __init__(
        self, session: ClientSession, email: str, password: str, spin: str = ""
    ) -> None:
        super().__init__(session, BRAND_SKODA, email, password, spin)
        # #602 (thiete) — the MQTT push manager needs the account user-id: it is
        # the MQTT username AND the topic prefix (``{user_id}/{vin}/#``). Škoda
        # was the only push-capable brand that never captured one, and the
        # coordinator's push setup bails out silently when it is missing — so
        # the Škoda push channel could never arm, with nothing in the log to say
        # why. SEAT/CUPRA and VW US/CA already carry this attribute.
        self._user_id: str | None = None
        # Per-VIN powertrain learned from driving-range.carType. Lets get_status
        # skip the battery-only /charging read on a confirmed combustion car so it
        # stops 403-hammering that endpoint. Empty on a fresh restart → charging is
        # attempted once, carType is learned, then skipped from poll 2 on.
        self._powertrain: dict[str, str] = {}
        # Škoda OFFICIAL public-API client, armed opt-in as a FAILOVER-ONLY read
        # source (see arm_supplementary_official). None unless the user configured
        # an API key. Never consulted on a healthy poll — only when the primary
        # mysmob read hard-fails — because the official API is rate-limited to
        # 20 req/hour/key.
        self._supplementary_official: Any = None

    def arm_supplementary_official(
        self, api_key: str = "", keys_by_vin: dict[str, str] | None = None,
    ) -> None:
        """Arm the official Škoda public API as a failover source (opt-in). Keys are
        vehicle-bound server-side, so ``get_status(vin)`` is called per-VIN on
        failover. ``keys_by_vin`` carries the auto-enrolled per-VIN keys; ``api_key``
        is the single manual-fallback key (applied to any VIN without its own)."""
        if not api_key and not keys_by_vin:
            self._supplementary_official = None
            return
        from .skoda_official import SkodaOfficialClient  # noqa: PLC0415
        self._supplementary_official = SkodaOfficialClient(
            self._session, email="", password=api_key, spin=self._spin,
            keys_by_vin=keys_by_vin,
        )

    async def official_failover_read(self, vin: str) -> "VehicleData | None":
        """Read one VIN via the official public API — the FAILOVER path, invoked
        only when the primary channel raised. Fail-soft: any error returns None so
        the failover can never itself sink the poll."""
        off = self._supplementary_official
        if off is None:
            return None
        # Honour the official channel's 20/hour/key budget: if the server has told
        # us we're out (RateLimit-Remaining 0, or a 429/503 Retry-After), skip the
        # failover read until the window resets rather than breaching the quota.
        if getattr(off, "over_rate_limit", False) is True:
            return None
        try:
            return await off.get_status(vin)  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001
            return None

    # -- official public-API key minting (mysmob BFF) -------------------------
    # Auto-enrollment: mint the official X-API-Key from the user's existing mysmob
    # login so an already-logged-in Škoda owner gets the durable official channel
    # with zero effort. RE'd from MyŠkoda 8.16 (bff_public_api_keys.v2).

    @property
    def can_mint_official_key(self) -> bool:
        """True only on a NATIVE mysmob login. The keygen POST needs a real mysmob
        Bearer (a JWT); a portal-fallback entry holds the cookie-session sentinel
        (strategy ``data_act_portal``, ``_eu_portal`` set), so minting there would
        401. Gate on: no portal connector, empty token strategy, JWT access token."""
        if getattr(self, "_eu_portal", None) is not None:
            return False
        tok = self._tokens
        if tok is None or getattr(tok, "strategy", "") != "":
            return False
        at = getattr(tok, "access_token", "") or ""
        return isinstance(at, str) and at.startswith("ey")

    async def mint_api_key(
        self, vin: str, name: str = _OFFICIAL_KEY_NAME
    ) -> dict[str, Any] | None:
        """Create an official public-API key for one VIN via the mysmob BFF, using
        the existing login. Returns ``{id, key, name, validUntil}`` — the ``key``
        secret is returned ONLY here, never on a later list — or None on any
        failure (fail-soft: auto-enroll must never sink the poll). Spoofs the real
        app User-Agent in case the route is app-version-gated.

        Records a PII-free outcome label under ``probe_outcomes`` on every path
        (``skoda_official_keygen``) so the integration diagnostics tell us what the
        live mysmob key-mint route actually did — we RE'd it from the 8.16 app but
        never ran it against the backend, so real-world outcomes come back as
        probes. Only the HTTP status and the response's top-level KEY names are
        recorded — never a body, VIN, or the key secret."""
        if not self.can_mint_official_key or not vin:
            return None
        try:
            body = await self._post(
                f"{_BASE}/api/v2/public-api-keys",
                json={"name": name, "vin": vin.strip().upper()},
                headers={"User-Agent": _KEYGEN_USER_AGENT},
            )
        except APIError as err:
            self.probe_outcomes["skoda_official_keygen"] = f"POST {err.status}"
            _LOGGER.debug(
                "official-API key mint failed for %s: HTTP %s", vin[-6:], err.status
            )
            return None
        except Exception as err:  # noqa: BLE001
            self.probe_outcomes["skoda_official_keygen"] = f"POST err:{type(err).__name__}"
            _LOGGER.debug(
                "official-API key mint failed for %s: %s", vin[-6:], type(err).__name__
            )
            return None
        if isinstance(body, dict) and body.get("key"):
            self.probe_outcomes["skoda_official_keygen"] = (
                "POST 2xx key+validUntil" if body.get("validUntil") else "POST 2xx key"
            )
            return body
        # 2xx but no key secret — record the shape (key NAMES only, no values).
        shape = ",".join(sorted(body.keys())) if isinstance(body, dict) else "non-dict"
        self.probe_outcomes["skoda_official_keygen"] = f"POST 2xx no-key [{shape}]"
        return None

    async def list_api_keys(self) -> dict[str, Any] | None:
        """List official-API keys + remaining per-VIN quota (``maxKeys`` 5). Returns
        the response dict (``{maxKeys, vehicleKeys:[{vin, keysRemaining}]}``) or
        None. Returns no key secrets. Used to check quota before minting. Records a
        PII-free ``skoda_official_keygen_list`` probe outcome (HTTP status + counts
        only) so diagnostics show whether the live list route answers."""
        if not self.can_mint_official_key:
            return None
        try:
            body = await self._get(
                f"{_BASE}/api/v2/public-api-keys",
                headers={"User-Agent": _KEYGEN_USER_AGENT},
            )
        except APIError as err:
            self.probe_outcomes["skoda_official_keygen_list"] = f"GET {err.status}"
            _LOGGER.debug("official-API key list failed: HTTP %s", err.status)
            return None
        except Exception as err:  # noqa: BLE001
            self.probe_outcomes["skoda_official_keygen_list"] = (
                f"GET err:{type(err).__name__}"
            )
            _LOGGER.debug("official-API key list failed: %s", type(err).__name__)
            return None
        if isinstance(body, dict):
            vk = body.get("vehicleKeys")
            self.probe_outcomes["skoda_official_keygen_list"] = (
                f"GET 2xx maxKeys={body.get('maxKeys')} "
                f"vins={len(vk) if isinstance(vk, list) else '?'}"
            )
            return body
        self.probe_outcomes["skoda_official_keygen_list"] = "GET 2xx non-dict"
        return None

    async def delete_api_key(self, key_id: str) -> bool:
        """Delete one official-API key by id (to free a slot before re-minting an
        expired one). True on success. Only keys we minted are deletable — the list
        endpoint returns no foreign ids."""
        if not self.can_mint_official_key or not key_id:
            return False
        try:
            await self._request(
                "DELETE", f"{_BASE}/api/v2/public-api-keys/{key_id}",
                headers={"User-Agent": _KEYGEN_USER_AGENT},
            )
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("official-API key delete failed: %s", type(err).__name__)
            return False

    @staticmethod
    def _sub_from_id_token(id_token: str | None) -> str | None:
        """Decode the ``sub`` claim of an id_token (the account user-id)."""
        if not isinstance(id_token, str) or not id_token:
            return None
        try:
            import base64  # noqa: PLC0415
            import json as _json  # noqa: PLC0415

            payload_b64 = id_token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            sub = _json.loads(base64.urlsafe_b64decode(payload_b64)).get("sub")
            return sub if isinstance(sub, str) and sub else None
        except Exception:  # noqa: BLE001
            return None

    @property
    def user_id(self) -> str | None:
        """Account user-id for the push channel (MQTT username + topic prefix).

        #602 — ``authenticate()`` captures it on an *interactive* login, but a
        persisted-token restart never runs that path, so the id was lost and the
        Škoda push channel silently never armed after a restart (Marco Schmidt,
        HA Tipps und Tricks Facebook group). Decode the id_token ``sub`` lazily
        here too, off whatever tokens are loaded, and cache it.
        """
        if not self._user_id:
            self._user_id = self._sub_from_id_token(
                getattr(getattr(self, "_tokens", None), "id_token", None)
            )
        return self._user_id

    async def _capture_user_id(self) -> None:
        """Fetch the account user-id from the mysmob ``/v1/users`` endpoint.

        This is where the MySkoda app and the ``myskoda`` library get it
        (``GET /api/v1/users`` -> ``.id``), and it is the MQTT username + topic
        prefix (``{user_id}/{vin}/#``). #602: decoding the id_token ``sub`` was
        unreliable on a classic mysmob login — it came back empty, so the push
        channel silently never armed (Marco Schmidt, HA Tipps und Tricks
        Facebook group; still dead on v3.2.0 with the sub-only capture).
        Best-effort: a miss only leaves push unarmed, never breaks a poll.
        """
        if self._user_id:
            return
        try:
            data = await self._get(f"{_BASE}/api/v1/users")
            uid = data.get("id") if isinstance(data, dict) else None
            if isinstance(uid, str) and uid:
                self._user_id = uid
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Škoda: /v1/users user-id fetch failed", exc_info=True)

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """Authenticate, then capture the account user-id for the push channel.

        #602 — mirrors ``vw_na._capture_user_id`` / ``seat_cupra._fetch_user_id``:
        prefer the id the IDK redirect carried, otherwise decode the ``sub``
        claim of the id_token (Škoda's scope includes ``openid``, so one is
        always minted). Best-effort — a miss only leaves push unarmed, which is
        the status quo, and must never fail the login.
        """
        await super().authenticate(mfa_code)
        if self._user_id:
            return
        auth_uid = getattr(self._auth, "user_id", None)
        if isinstance(auth_uid, str) and auth_uid:
            self._user_id = auth_uid
            return
        self._user_id = self._sub_from_id_token(
            getattr(self._tokens, "id_token", None)
        )

    async def get_vehicles(self) -> list[str]:
        """Return VINs from Škoda garage."""
        # v2.12.6 — EU Data Act portal mode (read-only fallback). If the
        # native Škoda backend is blocked, VIN enumeration comes from the
        # portal connector on ``self._eu_portal`` (same pattern as VW EU) so
        # the entry doesn't end with "no vehicles" after a portal login.
        portal = getattr(self, "_eu_portal", None)
        if portal is not None:
            try:
                portal_vins: list[str] = await portal.list_vehicle_vins()
            except AuthenticationError:
                if self._tokens and self._tokens.strategy == "device_grant_portal":
                    await self._refresh_tokens()
                else:
                    await portal.login(self._email, self._password)
                portal_vins = await portal.list_vehicle_vins()
            return portal_vins
        params = {
            "connectivityGenerations": ["MOD1", "MOD2", "MOD3", "MOD4"],
        }
        data = await self._get(f"{_BASE}/api/v2/garage", params=params)
        vehicles: list[dict[str, Any]] = data.get("vehicles", [])
        vins = [v["vin"] for v in vehicles if v.get("vin")]
        # #602 — capture the push user-id from /v1/users while we are on the
        # native backend and authenticated, so it is set before the push manager
        # arms after the first refresh. Runs once (guarded on _user_id).
        await self._capture_user_id()
        await self.fetch_images()
        return vins

    async def get_charging_profiles(self, vin: str) -> dict[str, Any]:
        """v1.16.0 (#25, #31) — Skoda charging profiles (read-only).

        Endpoint: ``GET /api/v1/charging/{vin}/profiles``
        Response shape (verified myskoda/models/chargingprofiles.py):
            {
              "chargingProfiles": [
                {"id": 1, "name": "Home",
                 "settings": {
                   "maxChargingCurrent": "MAXIMUM"|"REDUCED",
                   "minBatteryStateOfCharge": {"minimumBatteryStateOfChargeInPercent": 20},
                   "targetStateOfChargeInPercent": 80,
                   "autoUnlockPlugWhenCharged": "PERMANENT"|"ON"|"OFF"
                 },
                 "preferredChargingTimes": [{"id": 1, "enabled": true,
                    "startTime": "22:00", "endTime": "06:00"}],
                 "timers": [{"id": 1, "enabled": false, "time": "07:30",
                    "type": "RECURRING"|"ONE_OFF",
                    "recurringOn": ["MONDAY", ...]}],
                 "location": {"latitude": 47.39, "longitude": 8.21} | None
                },
                ...
              ],
              "currentVehiclePositionProfile": {
                "id": 1, "name": "Home",
                "targetStateOfChargeInPercent": 80,
                "nextChargingTime": "22:00" | None
              } | None,
              "carCapturedTimestamp": "..." | None
            }

        ``currentVehiclePositionProfile`` is the killer field for #25
        (location-based target SoC) — backend tells us which of the user's
        registered profiles is active right now based on the car's
        current GPS position.

        Best-effort: 404 / 403 → exception in caller's gather. Returns
        ``{}`` for non-dict responses.
        """
        url = f"{_BASE}/api/v1/charging/{vin}/profiles"
        data = await self._get(url)
        return data if isinstance(data, dict) else {}

    async def get_charging_history(
        self, vin: str, limit: int = 50
    ) -> dict[str, Any]:
        """v1.15.0 (#35) — Skoda charging history (myskoda PR shipped 2026).

        Endpoint: ``GET /api/v1/charging/{vin}/history?userTimezone=UTC&limit={N}``

        v2.11.0 (myskoda issue #585): the Skoda app update on 2026-05-15
        broke this endpoint with HTTP 500 for many users. The replacement
        path is now ``get_charging_statistics`` which lives on a different
        host (charging.cariad.digital, the same vhost SEAT/CUPRA already
        use) and is wired via myskoda PR #586. We keep the legacy
        endpoint as a fallback for accounts where it still works.

        Response shape (verified via myskoda/models/charging_history.py):
            {
              "nextCursor": "<ISO datetime>" | null,
              "periods": [
                {"totalChargedInKWh": 12.5, "sessions": [
                   {"startAt": "...", "chargedInKWh": 12.5,
                    "durationInMinutes": 45, "currentType": "AC"|"DC"},
                   ...
                ]},
                ...
              ]
            }

        Best-effort: 404 / 403 on accounts without the cap → exception
        in caller's gather. Returns ``{}`` for non-dict responses.
        """
        url = f"{_BASE}/api/v1/charging/{vin}/history"
        data = await self._get(
            url, params={"userTimezone": "UTC", "limit": limit}
        )
        return data if isinstance(data, dict) else {}

    async def get_charging_statistics(
        self, vin: str, days_back: int = 90
    ) -> dict[str, Any]:
        """v2.11.0 (myskoda PR #586 source-verified, rsa-wusel
        reverse-engineered). Skoda charging-statistics replacement for
        the legacy /v1/charging/{vin}/history endpoint that started
        returning HTTP 500 after the Skoda app update on 2026-05-15.

        Endpoint: ``POST prod.emea.mobile.charging.cariad.digital/charging_statistics``
        Same vhost we already use for SEAT/CUPRA charging stats but
        with Skoda-specific X-Brand header + a structured POST body
        carrying VIN-filtered date range.

        Body shape:
            {
              "started_after": "YYYY-MM-DD",
              "started_before": "YYYY-MM-DD",
              "selected_filter_options": [
                {"filter_type": "VEHICLE", "vin": "<VIN>"}
              ],
              "fetch_filter_options": true
            }

        Response shape (verified via myskoda PR #586):
            {
              "applicableFilterOptions": [...],
              "missingElliConsent": false,
              "monthSections": [
                {
                  "entries": [
                    {
                      "id": "...", "title": "...",
                      "primaryValue": {"value": 12.5, "unit": "kWh"},
                      "secondaryValue": {"value": 45, "unit": "min"},
                      "sessionDetails": {
                        "startedAt": "...", "isCurveAvailable": true,
                        ...
                      }
                    }
                  ]
                }
              ]
            }

        Best-effort: 401/403/404 soft-fail to ``{}`` so older accounts
        without the cap stay clean. Returns the raw parsed dict for the
        coordinator to consume.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415
        from datetime import date, timedelta  # noqa: PLC0415

        today = date.today()
        started_before = today.isoformat()
        started_after = (today - timedelta(days=days_back)).isoformat()
        url = (
            "https://prod.emea.mobile.charging.cariad.digital/charging_statistics"
        )
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Content-Type": "application/json",
            "X-Brand": "skoda",
            # v2.11.4 — myskoda PR #586 latest revision uses "GMT" (not
            # a full Olson zone). Upstream switched after a server-side
            # parser tightening; "Europe/Berlin" still works on most
            # accounts but "GMT" is the canonical value.
            "X-Device-Timezone": "GMT",
            "X-Api-Version": "1",
        }
        body = {
            "started_after": started_after,
            "started_before": started_before,
            "selected_filter_options": [
                {"filter_type": "VEHICLE", "vin": vin},
            ],
            "fetch_filter_options": True,
        }
        try:
            # We use the parent client's _request with explicit JSON
            # body. The auth Bearer header is injected by base.
            resp = await self._request(
                "POST", url, json=body, headers=headers,
                timeout=ClientTimeout(total=30),
            )
        except Exception:  # noqa: BLE001
            return {}
        return resp if isinstance(resp, dict) else {}

    async def get_latest_fueling(self) -> dict[str, Any]:
        """Latest completed fill-up (READ-ONLY) — MyŠkoda pay-at-pump history.

        ``GET api/v2/fueling/sessions/latest`` → ``FuelingSessionDto``
        (account-level, no VIN). Surfaces past-consumption data only —
        ``dateTime, fuelName, quantity/quantityUnit, price{total,currency,
        pricePerUnit}, gasStation.name`` (the masked ``formattedCardName`` is
        deliberately NOT read). This read moves no money.

        We NEVER call ``POST api/v2/fueling/sessions`` — that starts a stored-card
        pre-authorisation/charge at the pump via the ACI PayON gateway, i.e. a
        financial transaction, which the house rules prohibit. There is no write
        method in this client on purpose.

        Best-effort: 404/403 (account without pay-at-pump enrolment — most
        accounts) → ``{}``, so the sensors simply never spawn.
        """
        try:
            data = await self._get(f"{_BASE}/api/v2/fueling/sessions/latest")
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    async def get_my_parking(self) -> Any:
        """The user's current paid-parking session (READ-ONLY) — pay-to-park.

        ``GET api/v1/parking/sessions/mine`` → a SINGLE ``ParkingSessionDto``
        object (account-level, no VIN): ``{id, location{name}, priceAmount,
        priceCurrency, startTime, stopTime, licencePlate}`` — NOT a list. Surfaces
        where/when you paid to park + the cost, and whether the session is still
        active (``stopTime`` null). This read moves no money.

        We NEVER call ``POST api/v1/parking/sessions`` — that starts/pays a
        parking session (a financial transaction, house-rule prohibited); no
        write method exists here. Best-effort: 404/403 (no pay-to-park enrolment
        — most accounts) → ``{}``.
        """
        try:
            data = await self._get(f"{_BASE}/api/v1/parking/sessions/mine")
        except Exception:  # noqa: BLE001
            return {}
        return data

    async def get_predictive_maintenance(self, vin: str) -> dict[str, Any]:
        """Service reminders (READ-ONLY) — MyŠkoda predictive maintenance.

        ``GET api/v2/predictive-maintenance/vehicles/{vin}`` →
        ``PredictiveMaintenanceDto{reminders: [ReminderDto{type, dueDate,
        status, description, ...}]}``. type ∈ TECHNICAL_INSPECTION /
        SEASONAL_TYRE_CHANGE / FIRST_AID_KIT / TYRE_REPAIR_KIT. Best-effort → {}.
        """
        try:
            data = await self._get(
                f"{_BASE}/api/v2/predictive-maintenance/vehicles/{vin}"
            )
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    async def get_departure_timers(self, vin: str) -> dict[str, Any]:
        """Configured departure timers (READ-ONLY).

        ``GET api/v1/vehicle-automatization/{vin}/departure/timers`` →
        ``DepartureTimersDto{timers: [DepartureTimerDto{id, time, type, enabled,
        charging, climatisation, targetBatteryStateOfChargeInPercent, ...}]}``.
        The two optional queries default null, so we omit them. Best-effort → {}.
        """
        try:
            data = await self._get(
                f"{_BASE}/api/v1/vehicle-automatization/{vin}/departure/timers"
            )
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    async def get_consents(self) -> dict[str, Any]:
        """Account consent state (READ-ONLY) — mandatory + marketing.

        ``GET api/v2/consents/mandatory`` → ``{consented, termsAndConditionsLink,
        dataPrivacyLink}`` and ``GET api/v2/consents/marketing`` → ``{consented,
        title, text}`` (both account-level, no VIN). Returns
        ``{"mandatory": {...}, "marketing": {...}}``; missing halves → absent.
        Read-only: consent CHANGES go through the separate PATCH flow (a Repair),
        never automatically. Best-effort per half.
        """
        out: dict[str, Any] = {}
        for kind in ("mandatory", "marketing"):
            try:
                data = await self._get(f"{_BASE}/api/v2/consents/{kind}")
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, dict):
                out[kind] = data
        return out

    async def get_capabilities(self, vin: str) -> dict[str, Any]:
        """Return the mysmob capabilities list for *vin*.

        v2.31.0 (8.15.0 APK) — the standalone ``vehicle-access/{vin}/capabilities``
        GET no longer exists in 8.15.0 (grep of every ``*Api.smali`` for
        "capabilit" matches ONLY GarageApi; the sole capabilities route is a POST
        toggle). It returned ``{}`` on every poll, so capability gating silently
        degraded to permissive. Capabilities now live embedded in the garage
        vehicle document: ``GET api/v2/garage/vehicles/{vin}`` → ``VehicleDto``
        → ``capabilities`` (``VehicleCapabilitiesDto{capabilities: [CapabilityDto
        {id, serviceExpiration, statuses}], errors}``).

        We normalise to the ``{"capabilities": [{"id", "statuses"}]}`` shape the
        coordinator's gate reads. We deliberately do NOT synthesise an ``active``
        flag from ``statuses``: the 8.15.0 statics carry no groundable
        status→available vocabulary, and defaulting to "supported" (no
        ``active: False``) keeps the gate permissive — it can never wrongly HIDE a
        control. Status-based hiding can be layered on once a live capabilities
        sample pins the status enum. Best-effort: any failure → ``{}``.
        """
        data = await self._get(f"{_BASE}/api/v2/garage/vehicles/{vin}")
        if not isinstance(data, dict):
            return {}
        caps = data.get("capabilities")
        items = caps.get("capabilities") if isinstance(caps, dict) else None
        if not isinstance(items, list):
            return {}
        return {
            "capabilities": [
                {"id": c.get("id"), "statuses": c.get("statuses") or []}
                for c in items
                if isinstance(c, dict) and isinstance(c.get("id"), str)
            ]
        }

    async def get_widget(self, vin: str) -> dict[str, Any]:
        """v1.20.0 (Bundle 2 Phase A) — Skoda lightweight widget endpoint.

        Endpoint: ``GET /api/v2/widgets/vehicle-status/{vin}``
        Source: skodaconnect/myskoda PR #557 (merged 2026-04-15) —
        models/widget.py + rest_api.py:get_widget(). MIT-licensed
        upstream, fixtures + tests adopted (see NOTICE.md).

        Response shape (verified myskoda WidgetResponse model):

            {
              "vehicle": {
                "name": "Octavia iV",
                "licensePlate": "BE-XXX-1234",
                "renderUrl": "https://..."  // image URL
              },
              "vehicleStatus": {
                "doorsLocked": true,
                "drivingRangeInKm": 380
              },
              "chargingStatus": {  // optional, EV/PHEV only
                "stateOfChargeInPercent": 80,
                "remainingTimeToFullyChargedInMinutes": 45
              },
              "parkingPosition": {
                "state": "PARKED",
                "maps": {"lightMapUrl": "https://...", "darkMapUrl": "..."},
                "gpsCoordinates": {"latitude": 52.5, "longitude": 13.4},
                "formattedAddress": "Hauptstraße 1, 12345 Berlin"
              }
            }

        Use case: lightweight per-tick polling complement to the full
        ``/v2/vehicle-status/{vin}`` endpoint. Returns curated subset
        for the in-app glance card. Smaller payload but myskoda's PR
        doesn't claim a quota benefit — treat parity as unverified.

        Subscription tier: base (same auth path, no premium gate).

        Best-effort: 404 / 403 / network error → ``{}`` (caller skips
        widget-derived enrichment, full vehicle-status still works).
        """
        try:
            data = await self._get(f"{_BASE}/api/v2/widgets/vehicle-status/{vin}")
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    async def get_vehicle_info(self, vin: str) -> dict[str, Any]:
        """v1.20.0 (Bundle 2 Phase A) — Skoda vehicle-information endpoint.

        Endpoint: ``GET /api/v1/vehicle-information/{vin}``
        Source: skodaconnect/myskoda rest_api.py:get_vehicle_info().

        Response shape (verified myskoda VehicleInfo model — keys
        observed across multiple Skoda fixtures):

            {
              "name": "Octavia iV",
              "licensePlate": "BE-XXX-1234",
              "model": "Octavia iV",
              "modelYear": "2024",
              "engine": {"power": 110, "type": "TSI iV"},
              "specification": {
                "title": "Octavia Combi iV Style",
                "trimLevel": "Style",
                "modelKey": "NX5DBY",
                "battery": {"capacityInKWH": 13},
                ...
              },
              "softwareVersion": "..."
            }

        Static data — coordinator caches 24h (analog to capabilities).
        Used to enrich HA DeviceInfo (model name, year, software
        version) without re-fetching every poll cycle.

        Best-effort: 404 / 403 → ``{}``.
        """
        try:
            data = await self._get(f"{_BASE}/api/v1/vehicle-information/{vin}")
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    async def get_vehicle_renders(self, vin: str) -> dict[str, Any]:
        """v1.22.x foundation (myskoda PR #571 confirmed live 2026-05-02) —
        Skoda multi-angle vehicle renders.

        Endpoint: ``GET /api/v1/vehicle-information/{vin}/renders``
        Source: skodaconnect/myskoda PR #571 — endpoint marked verified
        () in upstream ``docs/api_endpoints.md`` after the merge on
        2026-05-02T21:12:05Z.

        Response shape (verified from PR #571 example payload, Enyaq
        2021 fixture, identifying data redacted):

            {
              "renders": [],
              "compositeRenders": [
                {
                  "layers": [
                    {
                      "url": "https://iprenders.blob.core.windows.net/...png",
                      "viewPoint": "EXTERIOR_SIDE",
                      "type": "REAL",
                      "order": 0
                    }
                  ],
                  "viewType": "UNMODIFIED_EXTERIOR_SIDE"
                },
                ...
              ]
            }

        Six view points observed in the live Enyaq fixture: EXTERIOR_
        {SIDE,FRONT,REAR}, INTERIOR_{SIDE,FRONT,BOOT}. Older / less
        documented vehicles may return an empty ``compositeRenders[]``
        — that is normal and the parser must tolerate it.

        Static data — the coordinator caches the same 24h window as
        ``get_vehicle_info`` / ``get_vehicle_equipment``. Best-effort:
        404 / 403 → ``{}`` (older firmware before PR #571 was wired
        upstream, or accounts without the capability).
        """
        try:
            data = await self._get(
                f"{_BASE}/api/v1/vehicle-information/{vin}/renders",
            )
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    async def get_vehicle_equipment(self, vin: str) -> dict[str, Any]:
        """v1.20.0 (Bundle 2 Phase A) — Skoda equipment list endpoint.

        Endpoint: ``GET /api/v1/vehicle-information/{vin}/equipment``
        Source: skodaconnect/myskoda rest_api.py:get_vehicle_equipment().

        Response shape (verified myskoda VehicleEquipment model):

            {
              "equipment": [
                {"id": "1234", "name": "Heated steering wheel"},
                {"id": "5678", "name": "Towbar"},
                ...
              ]
            }

        Static data — coordinator caches 24h. Surfaced as
        ``equipment_count`` sensor + full list in extra_state_attributes
        on the maintenance sensor (analog v1.17.7 preferred_workshop
        pattern).

        Best-effort: 404 / 403 → ``{}``.
        """
        try:
            data = await self._get(
                f"{_BASE}/api/v1/vehicle-information/{vin}/equipment",
            )
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    async def get_status(self, vin: str) -> VehicleData:
        """Fetch full status from Škoda API."""
        # v2.12.6 — EU Data Act portal mode (read-only fallback). Route the
        # whole status read through the portal connector on ``self._eu_portal``
        # when the native backend is blocked (same pattern as VW EU).
        portal = getattr(self, "_eu_portal", None)
        if portal is not None:
            try:
                data: VehicleData = await portal.get_vehicle_data(vin)
            except AuthenticationError:
                if self._tokens and self._tokens.strategy == "device_grant_portal":
                    await self._refresh_tokens()
                else:
                    await portal.login(self._email, self._password)
                data = await portal.get_vehicle_data(vin)
            return data
        v = self._val
        d = VehicleData(vin=vin)

        # A Škoda diesel keeps 403ing /charging (no HV battery). Once a prior
        # poll's driving-range told us carType is pure-combustion, stop calling it.
        # POSITIVE-only: skip solely on a confirmed combustion carType, so an
        # EV/PHEV (electric/hybrid, or unknown) is always polled.
        skip_charging = self._powertrain.get(vin) in _COMBUSTION_ONLY_CAR_TYPES
        results = await asyncio.gather(
            self._get(f"{_BASE}/api/v2/vehicle-status/{vin}"),
            (_skipped_charging() if skip_charging
             else self._get(f"{_BASE}/api/v1/charging/{vin}")),
            self._get(f"{_BASE}/api/v2/air-conditioning/{vin}"),
            self._get(f"{_BASE}/api/v3/maps/positions/vehicles/{vin}/parking"),
            self._get(f"{_BASE}/api/v2/vehicle-status/{vin}/driving-range"),
            self._get(f"{_BASE}/api/v3/vehicle-maintenance/vehicles/{vin}"),
            self._get(f"{_BASE}/api/v2/connection-status/{vin}/readiness"),
            # v1.15.0 — software-version + update-status (myskoda PR #541,
            # requires Skoda app v8.10.0+). Best-effort: 404 on older
            # firmware, 403 on accounts without the cap — both turn into
            # exceptions in ``return_exceptions=True`` and we skip below.
            self._get(
                f"{_BASE}/api/v1/vehicle-information/{vin}/software-version/update-status"
            ),
            # v1.20.0 (Bundle 2 Phase A, myskoda PR #557) — lightweight
            # widget endpoint. Returns curated subset (license plate,
            # render image URL, formatted parking address) for HA
            # DeviceInfo enrichment + image platform.
            self._get(f"{_BASE}/api/v2/widgets/vehicle-status/{vin}"),
            # v2.0.0 — driving score (efficiency metric 0-100). Skoda-only,
            # not all MY expose it; 404 → None handled below.
            self._get(f"{_BASE}/api/v2/vehicle-status/{vin}/driving-score"),
            # v2.11.0 (myskoda source-verified) - canonical warning-lights
            # endpoint. Previously we relied on the embedded
            # vehicleHealthWarnings block inside other responses; this
            # is the dedicated source that ships per-category +
            # per-defect data with priorities.
            self._get(
                f"{_BASE}/api/v1/vehicle-health-report/warning-lights/{vin}"
            ),
            # v2.11.0 (myskoda source-verified) - trip statistics
            # endpoint. Lifetime + avg consumption + travel time per
            # myskoda TripStatistics model.
            self._get(
                f"{_BASE}/api/v1/trip-statistics/{vin}?offsetType=week&offset=0"
            ),
            # v2.11.0 (myskoda PR #586 source-verified) - charging
            # statistics replacement after the legacy /v1/charging/
            # {vin}/history returned HTTP 500 since the 2026-05-15
            # Skoda app update. POST body w/ VIN-filter on the
            # charging.cariad.digital host.
            self.get_charging_statistics(vin),
            return_exceptions=True,
        )
        (
            status, charging, ac, parking, driving_range,
            maintenance, readiness, sw_update, widget, driving_score,
            health_v1, trip_stats, charging_stats_v2,
        ) = results

        # v1.9.0 — Vehicle Data Scout opt-in. Stash raw responses keyed by
        # the same endpoint names used in ``EXPECTED_KEYS["skoda"]`` so the
        # coordinator can run drift detection without parsing twice.
        # Exceptions are skipped — only successful dict responses are stashed.
        self.last_raw_responses = {}
        for name, payload in (
            ("vehicle-status", status),
            ("charging", charging),
            ("air-conditioning", ac),
            ("parking", parking),
            ("driving-range", driving_range),
            ("maintenance", maintenance),
            ("readiness", readiness),
            # v1.15.0 — register the new endpoint so Vehicle Data Scout
            # detects new fields once a 2026+ Skoda surfaces them.
            ("software-version-update-status", sw_update),
            # v1.20.0 (Bundle 2 Phase A) — widget endpoint (myskoda PR
            # #557) for Vehicle Data Scout drift detection on the
            # lightweight per-tick payload.
            ("widget", widget),
            # v2.0.0 — driving-score (efficiency metric, Skoda-only).
            ("driving-score", driving_score),
        ):
            if isinstance(payload, dict):
                self.last_raw_responses[name] = payload

        # v2.8.0 quick win D — parser-health telemetry. Each Skoda
        # endpoint maps to one logical job. Records per-call success
        # (got a dict) or failure (got an Exception in gather). The
        # ``last_error`` field for failed jobs carries the exception
        # type so diagnostics shows which endpoint silently broke.
        def _note(job: str, payload: Any) -> None:
            if isinstance(payload, BaseException):
                stats = self.parser_stats.setdefault(
                    job, {"success": 0, "fail": 0, "last_error": ""},
                )
                stats["fail"] = int(stats.get("fail", 0)) + 1
                stats["last_error"] = (
                    f"{type(payload).__name__}: {str(payload)[:160]}"
                )
            else:
                self._note_parser_job(job, present=isinstance(payload, dict))

        _note("vehicle_status", status)
        if charging is not _CHARGING_SKIPPED:
            _note("charging", charging)
        _note("climatisation", ac)
        _note("parking_position", parking)
        _note("service_care", maintenance)
        # Skoda flattens door_lock, oil_level, tyre_pressure and
        # auxiliary_heating into the vehicle-status payload. Mirror the
        # door_lock counter from the ``overall`` sub-block so the
        # cross-brand diagnostics shape stays comparable; the other
        # three are Skoda-not-applicable and intentionally left out.
        if isinstance(status, BaseException):
            _note("door_lock", status)
        elif isinstance(status, dict):
            self._note_parser_job(
                "door_lock",
                present=isinstance(self._val(status, "overall"), dict),
            )

        # ── Access / doors / windows / detail ────────────────────────────────
        if isinstance(status, dict):
            access = v(status, "access") or {}
            # v1.20.2 (#131 Chr1sDub Skoda Octavia iV bug B) — drop the
            # buggy ``overallStatus != "OPEN"`` fallback. The
            # ``access.overallStatus`` field describes the access *state*
            # (e.g. "OPEN", "CLOSED", "UNAVAILABLE", "LOCKED") — it is
            # NOT a doors-locked indicator. Pre-v1.20.2 we treated any
            # value other than "OPEN" as locked, which incorrectly
            # marked closed-but-unlocked vehicles as locked AND
            # left ``UNAVAILABLE``-state vehicles falsely "locked".
            #
            # Newer Skoda firmware (Octavia iV 2024+, Kodiaq Mk2) ships
            # the proper ``overall.reliableLockStatus`` /
            # ``overall.doorsLocked`` / ``overall.locked`` flags that
            # the block below reads authoritatively. Leave
            # ``doors_locked`` as ``None`` if neither is present —
            # better "unknown" than "wrong".
            # v2.11.0 (myskoda source-verified): there is no `access`
            # subobject on Skoda mysmob vehicle-status — those
            # `doorsOpenedCount` / `windowsOpenedCount` reads have
            # been returning 0 (= False) for every Skoda since v1.0.
            # The canonical source is `overall.doors` / `overall.windows`
            # which is a literal "OPEN" / "CLOSED" string.
            overall_doors_status = v(status, "overall", "doors")
            overall_windows_status = v(status, "overall", "windows")
            if isinstance(overall_doors_status, str):
                d.doors_open = overall_doors_status.upper() == "OPEN"
            elif "access" in status:
                # Legacy fallback in case any firmware ever ships it.
                d.doors_open = v(access, "doorsOpenedCount", default=0) > 0
            if isinstance(overall_windows_status, str):
                d.windows_open = overall_windows_status.upper() == "OPEN"
            elif "access" in status:
                d.windows_open = v(access, "windowsOpenedCount", default=0) > 0

            # v1.8.11 (Session 3S) — `vehicle-status` real shape verified
            # against upstream/cc-skoda issue #50
            # (Kodiaq iV 2026 Live-Response, posted 2026-03-25):
            #
            #   {"overall":  {"doorsLocked": "YES", "locked": "YES",
            #                 "doors": "CLOSED", "windows": "CLOSED",
            #                 "lights": "OFF",
            #                 "reliableLockStatus": "LOCKED"},
            #    "detail":   {"sunroof": "CLOSED", "trunk": "CLOSED",
    #                          "bonnet": "CLOSED"},
            #    "carCapturedTimestamp": "..."}
            #
            # Pre-v1.8.11 the Skoda parser ignored both ``overall.*`` flags
            # AND the ``detail`` block entirely — sunroof, trunk and hood
            # entities never populated for any Skoda model. Fix: read the
            # detail block; treat "UNSUPPORTED" as "field doesn't apply"
            # (entity stays None / unavailable) so Karoq Diesel doesn't
    #     show a sunroof entity.
            overall = v(status, "overall") or {}
            detail = v(status, "detail") or {}

            # Prefer the new ``reliableLockStatus`` (Kodiaq 2026+) over
            # the older ``doorsLocked`` aggregate when available — the
            # name itself signals it's the trustworthy field.
            lock_raw = (
                v(overall, "reliableLockStatus")
                or v(overall, "doorsLocked")
                or v(overall, "locked")
            )
            if isinstance(lock_raw, str):
                # v1.20.2 (#131 Bug B hardening) — explicit unlocked-
                # value enumeration for safety. Pre-v1.20.2 only matched
                # locked-values and let everything else fall through to
                # whatever line 320 set (which was buggy). Now we're
                # explicit: if value clearly says locked → True, if
                # clearly says unlocked → False, otherwise log + None.
                up = lock_raw.upper()
                _locked_values = {"YES", "LOCKED", "TRUE", "RELIABLE_LOCKED"}
                _unlocked_values = {
                    "NO", "UNLOCKED", "FALSE", "OPEN", "RELIABLE_UNLOCKED",
                }
                if up in _locked_values:
                    d.doors_locked = True
                elif up in _unlocked_values:
                    d.doors_locked = False
                else:
                    # Forward-compat shield (myskoda #503 pattern) —
                    # log unknown enum value so we can extend the table
                    # without breaking the parser. Leave field None
                    # rather than guessing — the binary_sensor / lock
                    # entity stays "unknown" instead of showing wrong.
                    _LOGGER.info(
                        "Skoda lock status: unknown value %r — leaving "
                        "doors_locked as None. Please report on issue "
                        "#131 so we can extend the value table.",
                        lock_raw,
                    )

            def _detail_open(field: str) -> bool | None:
                """Map detail.{sunroof,trunk,bonnet} string to bool open.
                Returns None for "UNSUPPORTED" so the entity stays None."""
                raw = detail.get(field)
                if not isinstance(raw, str):
                    return None
                up = raw.upper()
                if up == "OPEN":
                    return True
                if up == "CLOSED":
                    return False
                # "UNSUPPORTED" or any other value → not applicable
                return None

            sunroof = _detail_open("sunroof")
            if sunroof is not None:
                d.sunroof_open = sunroof
            trunk = _detail_open("trunk")
            if trunk is not None:
                d.trunk_open = trunk
            bonnet = _detail_open("bonnet")  # mysmob calls it bonnet, our field is hood
            if bonnet is not None:
                d.hood_open = bonnet

            # v1.25.0 PR-A — Cross-brand parity: lights aggregate.
            # Skoda mysmob ships ``overall.lights`` ("OFF"/"ON") which
            # we previously ignored; VW EU/Audi already expose
            # ``lights_on``. This closes one gap without needing the
            # per-light dict (Skoda doesn't expose individual lights).
            lights_raw = v(overall, "lights")
            if isinstance(lights_raw, str):
                up = lights_raw.upper()
                if up == "ON":
                    d.lights_on = True
                elif up == "OFF":
                    d.lights_on = False

            # v1.25.0 PR-A — Cross-brand parity: 12V starter battery.
            # Skoda mysmob ``vehicle-status.detail`` ships 12V voltage
            # (myskoda PR ~#480 onwards). VW EU/Audi already had this
            # via the ``lvBattery`` job since v1.12.0 (#23). Same
            # threshold heuristic (< 11.5 V → low warning) handled by
            # the binary_sensor entity.
            v12_raw = v(detail, "battery12V", "voltage") or v(detail, "voltage12V")
            d.voltage_12v = safe_float(v12_raw)

        # ── Charging ─────────────────────────────────────────────────────────
        # v1.8.11 (Session 3S): `charging.status.fullyChargedAt` is an
        # absolute ISO timestamp returned by current Kodiaq iV 2026
        # firmware (verified in CC-skoda issue #50). Prefer it over
        # `remainingTimeToFullyChargedInMinutes + now()` because the
        # latter drifts: if the backend value is computed at car-side
        # and we receive it 5 minutes later via polling, our derived ETA
        # is 5 minutes off. The absolute timestamp doesn't drift.
        if isinstance(charging, dict):
            # v2.2.0 Phase 7 PR #4 — isVehicleInSavedLocation (top-level
            # boolean on the charging endpoint). Whether the car's
            # current GPS matches a user-saved home/work location.
            # Defensive: only flip when backend returns a real bool —
            # string "true" / int 1 silently rejected.
            saved_loc = v(charging, "isVehicleInSavedLocation")
            if isinstance(saved_loc, bool):
                d.vehicle_at_saved_location = saved_loc
            c = charging.get("status", {})
            d.battery_soc = v(c, "battery", "stateOfChargeInPercent")
            d.charging_state = v(c, "state")
            # v2.0.1 (#131 follow-up) — defensive parsing.
            if isinstance(d.charging_state, str):
                d.is_charging = d.charging_state.upper() == "CHARGING"
            d.charging_power_kw = v(c, "chargePowerInKw")
            d.charging_rate_kmh = v(c, "chargingRateInKilometersPerHour")
            # v3.0.2 (#1104) — screen the no-reading sentinel (see vw_eu).
            d.charging_type = drop_charge_sentinel(v(c, "chargeType"))
            fully_at = v(c, "fullyChargedAt")
            if isinstance(fully_at, str):
                try:
                    d.charge_complete_eta = datetime.fromisoformat(
                        fully_at.replace("Z", "+00:00"))
                except ValueError:
                    fully_at = None  # Fall through to remaining-minutes calc below
            if not d.charge_complete_eta:
                # v1.10.1 (#58) — safe_int instead of bare int(). New
                # firmwares occasionally ship the field as a stringified
                # decimal ("12.5") which crashed pre-1.10.1 with
                # ValueError and took the entire vehicle's poll down.
                remaining = safe_int(v(c, "remainingTimeToFullyChargedInMinutes"))
                if remaining:
                    d.charge_complete_eta = datetime.now(tz=timezone.utc) + timedelta(minutes=remaining)
            d.has_battery = d.battery_soc is not None
            # v2.31.0 (8.15.0 APK) — BatteryStatusDto.remainingCruisingRangeInMeters
            # (metres) as an electric-range FALLBACK. The driving-range endpoint
            # below is the primary source and overwrites this when it has a value
            # (see the guarded assignment there); this covers cars/polls where
            # driving-range is absent but the charging block still carries range.
            _crm = v(c, "battery", "remainingCruisingRangeInMeters")
            if isinstance(_crm, (int, float)) and not isinstance(_crm, bool):
                d.electric_range_km = int(_crm / 1000)

            settings = charging.get("settings", {})
            d.target_soc = v(settings, "targetStateOfChargeInPercent")
            # v2.31.0 (8.15.0 APK) — Škoda's ChargingSettingsDto spells this the
            # bare ``autoUnlockPlugWhenCharged`` (@Json name), value PERMANENT/OFF;
            # the ``…AC`` suffix (VW-EU/CUPRA spelling) is absent from all 8.15.0
            # DEX, so the old key read False forever on Škoda. Prefer the bare key
            # and accept the PERMANENT enum; keep the AC key as a cross-brand
            # fallback (this field is shared, settable cross-brand).
            _au = v(settings, "autoUnlockPlugWhenCharged") or v(
                settings, "autoUnlockPlugWhenChargedAC"
            )
            d.auto_unlock_charge = str(_au).upper() in ("ON", "PERMANENT")
            # v2.18.0 (Scout #781) — Skoda spells the AC current limit
            # ``maxChargeCurrentAcAmpere`` (integer amps): a third spelling
            # beside CUPRA/SEAT's ``maxChargeCurrentAcInAmperes`` and the
            # official dictionary's enum-only ``settings.max_charge_current_ac``.
            # sensor.max_charge_current is device_class=current (numeric A), so
            # only a number is accepted — an enum string here would break entity
            # rendering the way it did on CUPRA in #392.
            _mca = v(settings, "maxChargeCurrentAcAmpere")
            if isinstance(_mca, (int, float)) and not isinstance(_mca, bool):
                d.max_charge_current = float(_mca)
            # v1.26.0 Welle-6 (#173, scouts #143/#133) — cross-brand alias.
            # Skoda's autoUnlockPlugWhenCharged or AC-suffix variant.
            au_raw = v(settings, "autoUnlockPlugWhenCharged") or v(settings, "autoUnlockPlugWhenChargedAC")
            if isinstance(au_raw, str):
                up = au_raw.upper()
                if up in ("ON", "PERMANENT", "TRUE", "YES"):
                    d.auto_unlock_when_charged = True
                elif up in ("OFF", "FALSE", "NO"):
                    d.auto_unlock_when_charged = False
            # v1.26.0 — Battery-Care Skoda. From scout #143 batteryCareModeTargetValueInPercent
            # + chargingCareMode "ACTIVATED"/"DEACTIVATED".
            care_mode_raw = v(settings, "chargingCareMode")
            if isinstance(care_mode_raw, str):
                up = care_mode_raw.upper()
                if up in ("ACTIVATED", "ACTIVE", "ON", "TRUE"):
                    d.battery_care_enabled = True
                elif up in ("DEACTIVATED", "INACTIVE", "OFF", "FALSE"):
                    d.battery_care_enabled = False
            care_target_pct = v(settings, "batteryCareModeTargetValueInPercent")
            if d.battery_care_target_soc_pct is None:  # don't clobber CUPRA/SEAT path
                d.battery_care_target_soc_pct = safe_int(care_target_pct)
            # v2.31.0 (8.15.0 APK) — ChargingSettingsDto.preferredChargeMode
            # (String enum, e.g. MANUAL / TIMER / PREFERRED_CHARGING_TIMES) +
            # availableChargeModes (List). Diagnostic — which charge mode the car
            # is set to and which it offers.
            pcm = v(settings, "preferredChargeMode")
            if isinstance(pcm, str) and pcm:
                d.preferred_charge_mode = pcm
            acm = v(settings, "availableChargeModes")
            if isinstance(acm, list) and acm:
                d.available_charge_modes = [str(m) for m in acm if m is not None]

        # ── Air conditioning (also has plug state!) ──────────────────────────
        if isinstance(ac, dict):
            d.climatisation_state = v(ac, "state")
            d.climatisation_active = d.climatisation_state not in (None, "OFF", "INVALID")
            # v2.31.0 (8.15.0 APK) — the top-level AirConditioningStateDto enum
            # includes HEATING_AUXILIARY, so aux-heating's active state derives
            # from the state we already fetched (zero extra request). Fills the
            # flag the Škoda aux-heating switch reads — it spawns (Škoda has
            # command_start_aux_heating) but showed "unknown" because the Škoda
            # parser never set aux_heating_active (only vw_eu did). PREHEATING (the
            # warm-up sub-state) only shows on the .../auxiliary-heating sub-GET;
            # this coarse flag is enough to make the switch reflect reality.
            if isinstance(d.climatisation_state, str):
                d.aux_heating_active = d.climatisation_state == "HEATING_AUXILIARY"
            # "INVALID" is the AC endpoint's no-valid-state marker (e.g. a
            # combustion car whose remote-climate data is invalid, or the system
            # simply off): show the climate-state sensor as unavailable instead of
            # the raw "INVALID" noise. Done AFTER the active/aux derivation above,
            # both of which already treat INVALID as not-active. Reported by
            # Marco Schmidt via the Home Assistant Tipps und Tricks Facebook group.
            if d.climatisation_state == "INVALID":
                d.climatisation_state = None
            # v1.10.1 (#58) — safe_float. Skoda firmwares have shipped
            # ``"21,5"`` (locale-comma) on EU accounts at least once.
            d.target_temperature = safe_float(
                v(ac, "targetTemperature", "temperatureValue")
            )

            wh = v(ac, "windowHeatingState") or {}
            # v2.31.0 (8.15.0 APK) — AirConditioningWindowHeatingStateDto carries
            # front / rear / unspecified (all ON/OFF strings). Single-channel cars
            # report only ``unspecified``; fold it into both so their window
            # heating isn't stuck reading OFF when the channel is on.
            _wh_front = v(wh, "front")
            _wh_rear = v(wh, "rear")
            _wh_uns = v(wh, "unspecified")
            d.window_heating_front = (
                _wh_front == "ON" or (_wh_front is None and _wh_uns == "ON")
            )
            d.window_heating_back = (
                _wh_rear == "ON" or (_wh_rear is None and _wh_uns == "ON")
            )

            # v2.1.0 — climate-ready-at (closes scout #186 + #188).
            # Skoda mysmob air-conditioning endpoint shippt
            # ``estimatedDateTimeToReachTargetTemperature`` als ISO-8601
            # Zeitstempel wenn die Klimatisierung aktiv läuft. Sehr
            # nützlich für "Vorklimatisierung 5min vor Abfahrt"
            # Automatisierungen — User kann jetzt ``binary_sensor``
            # triggern wenn ``sensor.<vin>_climate_ready_at`` minus
            # 5min erreicht. Field ist nur während Climate-Run gesetzt;
            # bleibt None während OFF.
            climate_ready = v(ac, "estimatedDateTimeToReachTargetTemperature")
            if isinstance(climate_ready, str) and climate_ready:
                d.climate_ready_at = climate_ready
            # v1.26.0 Welle-6 (#173, scouts #143) — Skoda climate settings.
            # airConditioningAtUnlock as climate_at_unlock cross-brand alias.
            au_clim = v(ac, "airConditioningAtUnlock")
            if isinstance(au_clim, bool):
                d.climate_at_unlock = au_clim
            # windowHeatingEnabled (setting, not state — distinct from front/back ON state).
            wh_en = v(ac, "windowHeatingEnabled")
            if isinstance(wh_en, bool):
                d.window_heating_enabled = wh_en
            # v2.17.0 (#682 skoda Scout, ra666ack) — heaterSource on the
            # air-conditioning endpoint ("AUTOMATIC" in the wild). Cross-brand
            # alias to the existing heater_source sensor (VW/Audi/SEAT already
            # map it). Free enum string — defensive guard for null/older firmware.
            heater_src = v(ac, "heaterSource")
            if isinstance(heater_src, str) and heater_src:
                d.heater_source = heater_src
            # v2.2.0 (scout #220 — Daniel Walter 2026-05-16) — Skoda mysmob
            # exposes a new boolean ``airConditioningWithoutExternalPower``
            # on the air-conditioning endpoint indicating whether climate
            # can run from the HV battery alone (vs. requiring a charger
            # plugged in). Boolean — defensive isinstance guard so a
            # string/null variant on older firmware doesn't trip it.
            ac_no_ext = v(ac, "airConditioningWithoutExternalPower")
            if isinstance(ac_no_ext, bool):
                d.air_conditioning_without_external_power = ac_no_ext
            # v2.5.9 (#315/#316/#321/#327/#328/#329/#330/#333 — EIGHT
            # Skoda Scout-Reports converging 2026-05-28/29). New Enyaq/iV
            # "Camping Mode" feature exposed at
            # ``air-conditioning.campingMode``. Scout reported `{1 keys}`
            # so the API returns an object — we don't know the exact
            # sub-key yet (could be ``enabled``, ``active``, ``state``).
            # Defensive parse: accept BOOL (legacy), OBJECT-with-
            # ``enabled``/``active`` sub-key, OR plain string ("on"/"off").
            # When a real debug-log lands we can tighten this. Phantom-
            # protected via _DATA_PRESENT_REQUIRED in binary_sensor.py.
            camping = v(ac, "campingMode")
            if isinstance(camping, bool):
                d.camping_mode = camping
            elif isinstance(camping, dict):
                # Try common sub-key names in priority order.
                for key in ("enabled", "active", "isEnabled", "state"):
                    val = camping.get(key)
                    if isinstance(val, bool):
                        d.camping_mode = val
                        break
                    if isinstance(val, str):
                        d.camping_mode = val.lower() in ("on", "active", "enabled", "true")
                        break
            elif isinstance(camping, str):
                d.camping_mode = camping.lower() in ("on", "active", "enabled", "true")
            # v2.31.0 (8.15.0 APK) — CampingModeDto carries {enabled, endsAt}
            # (@Json names confirmed); expose the auto-stop time.
            if isinstance(camping, dict):
                ends = camping.get("endsAt")
                if isinstance(ends, str) and len(ends) >= 10:
                    try:
                        d.camping_ends_at = datetime.fromisoformat(
                            ends.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
            # v2.31.0 (8.15.0 APK) — air-conditioning.seatHeatingActivated is a
            # SeatHeatingSettingsDto {frontLeft, frontRight, rearLeft, rearRight}
            # of nullable Booleans (same shape as the set command). Fill the
            # single ``seat_heating`` binary-sensor flag = any seat currently
            # heating; this makes the previously-phantom sensor spawn.
            sh = v(ac, "seatHeatingActivated")
            if isinstance(sh, dict):
                _seats = [sh.get(k) for k in
                          ("frontLeft", "frontRight", "rearLeft", "rearRight")]
                if any(isinstance(s, bool) for s in _seats):
                    d.seat_heating = any(s is True for s in _seats)
            # v2.2.0 Phase 7 PR #1 — steeringWheelPosition (LEFT/RIGHT).
            # LHD/RHD-aware automations + diagnostic for markets where
            # the same car ships both (UK, AU, JP). Defensive: only
            # set when backend returns a non-empty string.
            swp = v(ac, "steeringWheelPosition")
            if isinstance(swp, str) and swp:
                d.steering_wheel_position = swp
            # v2.2.0 Phase 7 PR #4 — Skoda tier-B from scout-audit.
            # Climate timers list — count of currently-enabled entries.
            # Parity to VW EU/Audi `departure_timer_enabled_count`
            # (PR #2). Only set when timers block is actually present
            # (not just empty) so phantom-gate fires on non-Skoda.
            timers_list = v(ac, "timers")
            if isinstance(timers_list, list) and timers_list:
                d.climate_timer_enabled_count = sum(
                    1 for t in timers_list
                    if isinstance(t, dict) and t.get("enabled") is True
                )
            # v2.2.0 Phase 7 PR #4 — running climate requests count.
            # >0 means a command is still pending modem ack. Diagnostic
            # for "start_climatisation does nothing" mode. Only set
            # when list is present so other brands stay None.
            running = v(ac, "runningRequests")
            if isinstance(running, list):
                d.climate_running_requests_count = len(running)

            # v1.17.7 (#129 rocksandclouds + #130 Chr1sDub + #133
            # christianmhz — three converging Skoda Scout-Reports
            # 2026-05-03/04). Skoda mysmob now exposes the outside
            # temperature on the air-conditioning endpoint, mirroring
            # what VW EU + SEAT/CUPRA already provided. Native Celsius
            # value (no Kelvin conversion needed). Stale-detection via
            # carCapturedTimestamp is left to the existing connection-
            # state pipeline. ``safe_float`` handles locale-comma
            # variants (Skoda firmwares have shipped "21,5" once).
            outside_t = v(ac, "outsideTemperature", "temperatureValue")
            if outside_t is not None:
                # Backend always sends Celsius for Skoda (verified across
                # 3 user reports), but defensively check unit anyway.
                unit = v(ac, "outsideTemperature", "temperatureUnit")
                ot_val = safe_float(outside_t)
                if ot_val is not None:
                    if unit == "FAHRENHEIT":
                        ot_val = round((ot_val - 32) * 5 / 9, 1)
                    d.outside_temp = ot_val

            plug_conn = v(ac, "chargerConnectionState")
            if isinstance(plug_conn, str):
                d.plug_connected = plug_conn.upper() == "CONNECTED"
                d.plug_state = plug_conn
            # v2.0.1 (#131 follow-up) — defensive parsing.
            charger_lock = v(ac, "chargerLockState")
            if isinstance(charger_lock, str):
                d.connector_locked = charger_lock.upper() == "LOCKED"

        # ── Parking position (v3 with formatted address) ─────────────────────
        if isinstance(parking, dict):
            pos = v(parking, "parkingPosition", "gpsCoordinates") or {}
            d.latitude = pos.get("latitude")
            d.longitude = pos.get("longitude")
            addr = v(parking, "parkingPosition", "formattedAddress")
            if addr:
                d.parking_address = addr

        # ── Driving range ────────────────────────────────────────────────────
        if isinstance(driving_range, dict):
            # v1.10.0 (#94) — Skoda mysmob exposes the same per-engine
            # split as the CARIAD BFF, just under different keys:
            #   electricRange.distanceInKm
            #   combustionRange.distanceInKm  (was previously read as the
            #     scalar ``combustionRange`` only — wrong on Kodiaq iV)
            #   totalRangeInKm
            # Each is its own entity now; ``range_km`` keeps its old
            # "headline" semantics (electric for EV/PHEV, total for ICE).
            # v2.11.0 (#392 myskoda source-verified): the canonical key is
            # ``primaryEngineRange.remainingRangeInKm`` for the primary
            # propulsion (electric on BEV, combustion on ICE) and
            # ``secondaryEngineRange.remainingRangeInKm`` for the
            # secondary on PHEVs. ``electricRange.distanceInKm`` and
            # ``combustionRange.distanceInKm`` were our scout-derived
            # guesses that myskoda's DrivingRange model does NOT
            # include — for years they have returned None on every
            # Skoda. Keep the old paths as last-resort fallbacks for
            # any firmware that genuinely ships them.
            primary_remaining = v(
                driving_range, "primaryEngineRange", "remainingRangeInKm"
            )
            secondary_remaining = v(
                driving_range, "secondaryEngineRange", "remainingRangeInKm"
            )
            primary_eng_type = (
                v(driving_range, "primaryEngineRange", "engineType") or ""
            ).upper()
            # Derive electric / combustion from primary+secondary +
            # engineType. EV / PHEV electric: primary if primary is
            # ELECTRIC, else secondary. Combustion: primary if non-
            # electric, else secondary.
            if "ELECTRIC" in primary_eng_type or primary_eng_type in ("BEV",):
                electric = primary_remaining or v(
                    driving_range, "electricRange", "distanceInKm"
                )
                combustion = secondary_remaining or v(
                    driving_range, "combustionRange", "distanceInKm"
                )
            elif primary_eng_type:
                combustion = primary_remaining or v(
                    driving_range, "combustionRange", "distanceInKm"
                )
                electric = secondary_remaining or v(
                    driving_range, "electricRange", "distanceInKm"
                )
            else:
                # No engineType - try both, prefer remainingRangeInKm.
                electric = first_not_none(
                    v(driving_range, "primaryEngineRange", "remainingRangeInKm"),
                    v(driving_range, "electricRange", "distanceInKm"),
                )
                combustion = first_not_none(
                    v(driving_range, "secondaryEngineRange", "remainingRangeInKm"),
                    v(driving_range, "combustionRange", "distanceInKm"),
                )
            total = v(driving_range, "totalRangeInKm")
            if combustion is None:
                # Older firmwares published a flat scalar without the
                # ``distanceInKm`` wrapper — keep that path as a fallback.
                flat_combustion = v(driving_range, "combustionRange")
                if isinstance(flat_combustion, (int, float)):
                    combustion = flat_combustion
            # v1.24.2 (2026-05-08 audit): replaced 3 try/except wrappers
            # around int() with safe_int — same defensive shape, fewer
            # lines, and the NEVER-raise contract is property-tested.
            # v2.31.0 — don't clobber the charging-block fallback (set above)
            # with None when driving-range omits the electric figure.
            _er = safe_int(electric)
            if _er is not None:
                d.electric_range_km = _er
            d.combustion_range_km = safe_int(combustion)
            d.total_range_km = safe_int(total)
            d.has_combustion = combustion is not None
            # Headline number priority: electric for EV/PHEV, then total,
            # then combustion. Matches VW EU/Audi semantics from vw_eu.py.
            if d.has_battery and d.electric_range_km is not None:
                d.range_km = d.electric_range_km
            elif d.total_range_km is not None:
                d.range_km = d.total_range_km
            elif d.combustion_range_km is not None:
                d.range_km = d.combustion_range_km
            else:
                d.range_km = electric or total
            # v2.11.0 (myskoda source-verified): adBlueRange is a FLAT
            # int on the Skoda payload, NOT a dict with distanceInKm.
            # The pre-v2.11.0 dict lookup returned None on every car.
            adblue_flat = v(driving_range, "adBlueRange")
            if isinstance(adblue_flat, (int, float)):
                d.adblue_range_km = safe_int(adblue_flat)
            else:
                # Fallback if some firmware genuinely ships the dict.
                d.adblue_range_km = safe_int(
                    v(driving_range, "adBlueRange", "distanceInKm")
                )
            # v1.26.0 Welle-6 (#173, scout #165 christianmhz) — Skoda PHEV
            # secondary engine range (Kodiaq iV, Octavia iV, Superb iV).
            # v2.11.0: prefer remainingRangeInKm (myskoda canonical)
            # over the scout-derived distanceInKm.
            sec_eng = (
                v(driving_range, "secondaryEngineRange", "remainingRangeInKm")
                or v(driving_range, "secondaryEngineRange", "distanceInKm")
            )
            d.secondary_engine_range_km = safe_int(sec_eng)
            # v2.2.0 (Skoda Scout #220 — Daniel Walter 2026-05-16):
            # ``secondaryEngineRange`` expanded from 1-key (distanceInKm)
            # to 4-key shape mid-May 2026. The extra companion fields
            # surface as separate sensors so automations can branch on
            # engine-type / fuel-level. Defensive ``isinstance`` guards
            # because pre-expansion firmwares emit None / missing.
            sec_eng_type = v(driving_range, "secondaryEngineRange", "engineType")
            if isinstance(sec_eng_type, str) and sec_eng_type:
                d.secondary_engine_type = sec_eng_type
            sec_eng_fuel = v(
                driving_range, "secondaryEngineRange", "currentFuelLevelInPercent"
            )
            d.secondary_engine_fuel_level_pct = safe_int(sec_eng_fuel)
            # v2.2.0 Phase 7 PR #1 — primaryEngineRange.currentSoCInPercent.
            # On a gasoline car this is the 12V SoC (per #116 MavericklCS
            # 2026-05-01 scout) — early-warning sensor for "modem can't
            # keep itself awake". Defensive: missing key → field stays None.
            primary_soc = v(
                driving_range, "primaryEngineRange", "currentSoCInPercent"
            )
            d.primary_engine_soc_pct = safe_int(primary_soc)
            # v2.2.1 Phase 8 PR #1 — alles-parsen strategy:
            # primaryEngineRange.{engineType, currentFuelLevelInPercent}
            # cross-brand reuse. engineType maps into existing
            # `primary_engine_type` from PR #3 Phase 7 (CUPRA/SEAT) —
            # zero-new-entity expanded coverage. fuelLevelInPercent is
            # a new Skoda-only field (primary tank %), distinct vom
            # existing `fuel_level` (measurements path) und mit dem
            # bestehenden `secondary_engine_fuel_level_pct` als
            # cross-brand sibling.
            primary_eng_type = v(
                driving_range, "primaryEngineRange", "engineType"
            )
            if isinstance(primary_eng_type, str) and primary_eng_type:
                d.primary_engine_type = primary_eng_type
            primary_fuel = v(
                driving_range, "primaryEngineRange", "currentFuelLevelInPercent"
            )
            d.primary_engine_fuel_level_pct = safe_int(primary_fuel)
            # v2.2.1 Phase 8 PR #1 — carType (string enum diesel /
            # gasoline / electric / hybrid). Authoritative backend
            # classification der primary engine, distinct von den
            # derived booleans (is_electric / is_hybrid / has_combustion).
            car_type = v(driving_range, "carType")
            if isinstance(car_type, str) and car_type:
                d.car_type = car_type
                # Remember the authoritative powertrain so the NEXT poll can skip
                # /charging on a pure-combustion car (see get_status head).
                self._powertrain[vin] = car_type.strip().lower()

        d.is_electric = d.has_battery and not d.has_combustion
        d.is_hybrid = d.has_battery and d.has_combustion

        # ── Maintenance ──────────────────────────────────────────────────────
        if isinstance(maintenance, dict):
            report = v(maintenance, "maintenanceReport") or maintenance
            d.odometer_km = drop_odometer_sentinel(v(report, "mileageInKm"))
            d.service_km = v(report, "inspectionDueInKm")
            d.service_due_at = v(report, "inspectionDueInDays")
            d.oil_service_km = v(report, "oilServiceDueInKm")
            d.oil_service_at = v(report, "oilServiceDueInDays")
            # v1.11.0 (#91 closure) — explicit raw int day-counts
            # alongside the existing DATE-converted sensors.
            d.service_due_in_days = safe_int(d.service_due_at)
            d.oil_service_due_in_days = safe_int(d.oil_service_at)
            # v2.2.1 Phase 8 PR #1 — maintenanceReport.capturedAt
            # diagnostic timestamp. Useful für "ist mein service-due
            # data stale?" Fragen. ISO 8601 pass-through.
            mr_captured = v(report, "capturedAt")
            if isinstance(mr_captured, str) and mr_captured:
                d.maintenance_report_captured_at = mr_captured
            # v1.17.7 (#130 Chr1sDub + #133 christianmhz, 2026-05-04) —
            # Skoda mysmob now exposes the user's preferred-workshop
            # registration on the maintenance endpoint. Surfaced as
            # extra_state_attributes on the ``service_due_in_days``
            # sensor (sensor.py) so users see the workshop name +
            # contact data alongside the next-service countdown.
            #
            # We pass the raw dict through verbatim — backend ships
            # nested contact/address/location/openingHours blocks
            # whose exact keys vary (DE vs CH vs AT vehicles see
            # different address shapes). HA's recorder is fine with
            # nested attrs as long as the total serialised size fits;
            # for CIS-region accounts the openingHours array can be
            # large so we drop it (rarely actionable in HA UI).
            workshop = v(maintenance, "preferredServicePartner")
            if isinstance(workshop, dict) and workshop:
                # Shallow copy + drop openingHours to keep attrs lean
                # in the HA state machine. Users who need full hours
                # can read the diagnostics export.
                trimmed = {
                    k: val for k, val in workshop.items()
                    if k != "openingHours"
                }
                d.preferred_workshop = trimmed
                # v2.8.0 quick win C — also populate the normalised
                # singleton fields so the new sensors can read flat
                # values without templating into the composite dict.
                d.preferred_workshop_name = normalize_workshop_string(
                    workshop.get("name") or workshop.get("displayName")
                )
                d.preferred_workshop_address = compose_workshop_address(
                    workshop.get("address") or workshop.get("location")
                )
                d.preferred_workshop_phone = workshop_phone_from_contact(
                    workshop.get("contact") or workshop
                )

            # v2.8.0 quick win C — brake service due-dates. Skoda's
            # ``maintenanceReport`` exposes the brake fluid + pad
            # inspection due-counters when the dealer has scheduled
            # them. Field names differ between MOD3 (older) and MOD4+
            # (newer) so we accept either.
            brake_fluid_raw = (
                v(report, "brakeFluidServiceDueInDays")
                or v(report, "brakeFluidChangeDueInDays")
                or v(report, "brakeFluidChange_days")
            )
            d.brake_fluid_change_due_at = days_or_date_to_iso(brake_fluid_raw)
            front_pads_raw = (
                v(report, "brakePadsFrontInspectionDueInDays")
                or v(report, "brakePadFrontInspectionDueInDays")
            )
            d.brake_pads_front_inspection_due_at = days_or_date_to_iso(
                front_pads_raw
            )
            rear_pads_raw = (
                v(report, "brakePadsRearInspectionDueInDays")
                or v(report, "brakePadRearInspectionDueInDays")
            )
            d.brake_pads_rear_inspection_due_at = days_or_date_to_iso(
                rear_pads_raw
            )

        # ── Connection status ────────────────────────────────────────────────
        # is_driving (motion) — always a concrete bool for Škoda so the sensor is
        # never hidden by the "hide empty" option when the readiness block is
        # momentarily absent from a poll (#1310, indigomejor: readiness comes and
        # goes, so is_driving flapped to None and the entity disappeared). Not
        # driving is the safe default — a car with no motion signal is parked or
        # asleep far more often than it's mid-drive with the block dropped.
        d.is_driving = isinstance(readiness, dict) and v(readiness, "inMotion") is True
        if isinstance(readiness, dict):
            unreachable = v(readiness, "unreachable")
            # When unreachable is unknown (None), assume reachable (True)
            # to avoid setting is_online to a falsy default.
            d.is_online = unreachable is None or unreachable is False
            # v2.2.0 Phase 7 PR #1 — Skoda-only ignition boolean from
            # the scout-silenced-but-unwired audit. Useful for
            # "lock when ignition off" automations.
            ignition = v(readiness, "ignitionOn")
            if isinstance(ignition, bool):
                d.ignition_on = ignition
            # v2.2.1 Phase 8 PR #1 — Skoda-only 12V battery protection
            # threshold. Companion zu VW EU/Audi `daily_power_budget_
            # available` (Phase 7 PR #2). Skoda mysmob signaliert über
            # diesen boolean wenn der modem in low-power mode geht.
            bplim = v(readiness, "batteryProtectionLimitOn")
            if isinstance(bplim, bool):
                d.battery_protection_limit_on = bplim

        # ── carCapturedTimestamp → connection_state (v1.8.12 refactor) ────
        # v1.8.11 introduced this logic Skoda-only; v1.8.12 extracted the
        # algorithm into ``cariad/_util.compute_connection_state`` so VW EU,
        # Audi and CUPRA/SEAT can apply the same Pattern (Multi-Brand
        # Connection-State). The recursive timestamp walk in the helper
        # also handles VW EU CARIAD-BFF's deeper-nested structure
        # (``service.statusName.value.carCapturedTimestamp`` — verified
        # via upstream/volkswagencarnet issue #921 ID.4 2025
        # Live-Response).
        d.connection_state, d.last_seen_at = compute_connection_state(
            status, charging, ac, parking, driving_range, maintenance, readiness,
        )

        # ── v1.15.0 — Software-version + OTA update status (myskoda PR #541) ─
        # Endpoint shipped in Skoda app v8.10.0+ — older accounts return
        # 404 / 403 which surfaces as an exception in our gather(); we
        # leave the fields ``None`` in that case.
        if isinstance(sw_update, dict):
            sw_status = sw_update.get("status")
            if isinstance(sw_status, str):
                # Defensive enum tolerance for forward-compat with new
                # values (myskoda raises UnexpectedSoftwareUpdateStatusError
                # for unknown). We just pass through raw + derive a bool.
                d.software_update_status = sw_status
                d.ota_update_available = sw_status.upper() not in {
                    "NO_UPDATE_AVAILABLE", "UPDATE_SUCCESSFUL",
                }
            curr = sw_update.get("currentSoftwareVersion")
            if isinstance(curr, str):
                d.software_version = curr
            notes = sw_update.get("releaseNotesUrl")
            if isinstance(notes, str) and notes:
                d.ota_release_notes_url = notes

        # ── Widget endpoint (v1.20.0 Bundle 2 Phase A) ────────────────────────
        # Lightweight per-tick payload from /v2/widgets/vehicle-status/{vin}
        # (myskoda PR #557). Carries 4 fields useful in HA:
        #   - vehicle.licensePlate  → DeviceInfo enrichment
        #   - vehicle.renderUrl     → image platform integration
        #   - vehicle.name          → may be more accurate than garage nickname
        #   - parkingPosition.formattedAddress → reverse-geocoding-free address
        # Defensive: missing endpoint = 404 = exception in gather → skip.
        if isinstance(widget, dict):
            vehicle_meta = v(widget, "vehicle") or {}
            if isinstance(vehicle_meta, dict):
                lic = vehicle_meta.get("licensePlate")
                if isinstance(lic, str) and lic:
                    d.license_plate = lic
                render = vehicle_meta.get("renderUrl")
                if isinstance(render, str) and render.startswith("http"):
                    d.render_url = render
            # formattedAddress beats reverse-geocoding when present —
            # backend resolves locale-aware. Coordinator's _enrich
            # checks parking_address-already-set so we don't clobber.
            addr = v(widget, "parkingPosition", "formattedAddress")
            if isinstance(addr, str) and addr and not d.parking_address:
                d.parking_address = addr

        # ── Driving Score (v2.0.0, Skoda-only) ────────────────────────────────
        # /api/v2/vehicle-status/{vin}/driving-score — 0-100 efficiency metric.
        # Newer Skoda Connect MY24+ surface this; older 404. Defensive parse.
        # v2.11.0 (myskoda TripStatistics model source-verified): the
        # /v1/trip-statistics/{vin} endpoint returns an OverviewTrip
        # with overall_average_fuel_consumption / overall_average_mileage /
        # overall_travel_time_in_min / overall_mileage_in_km + a
        # detailedStatistics list of per-period TripStatistics entries.
        if isinstance(trip_stats, dict):
            overview = trip_stats.get("overview") or trip_stats
            if isinstance(overview, dict):
                lifetime_km = (
                    overview.get("overallMileageInKm")
                    or overview.get("mileageInKm")
                )
                if isinstance(lifetime_km, (int, float)):
                    d.lifetime_distance_km = int(lifetime_km)
                avg_fuel = overview.get("overallAverageFuelConsumption")
                if isinstance(avg_fuel, (int, float)):
                    d.lifetime_avg_fuel_consumption_l_100km = float(avg_fuel)
                avg_electric = (
                    overview.get("overallAverageElectricConsumption")
                    or overview.get("overallAverageElectricEngineConsumption")
                )
                if isinstance(avg_electric, (int, float)):
                    d.lifetime_avg_electric_consumption_kwh_100km = float(avg_electric)
            # last-trip from detailedStatistics[0]
            detailed = trip_stats.get("detailedStatistics")
            if isinstance(detailed, list) and detailed:
                last = detailed[0]
                if isinstance(last, dict):
                    last_km = last.get("mileageInKm") or last.get("mileage")
                    if isinstance(last_km, (int, float)):
                        d.last_trip_distance_km = int(last_km)
                    last_time = (
                        last.get("travelTimeInMin")
                        or last.get("travelTime")
                    )
                    if isinstance(last_time, (int, float)):
                        d.last_trip_duration_min = int(last_time)
                    last_fuel = last.get("averageFuelConsumption")
                    if isinstance(last_fuel, (int, float)):
                        d.last_trip_avg_fuel_consumption_l_100km = float(last_fuel)
                    last_speed = last.get("averageSpeedInKmph")
                    if isinstance(last_speed, (int, float)):
                        d.last_trip_avg_speed_kmh = int(last_speed)
                    last_ts = (
                        last.get("tripEndTimestamp")
                        or last.get("timestamp")
                    )
                    if isinstance(last_ts, str) and last_ts:
                        d.last_trip_timestamp = last_ts

            # v2.12.0 (myskoda PR #575 source-verified): overall_cost
            # breakdown on the OverviewTrip. Each sub-cost is an object
            # {cost, costCurrency, pricePerUnit}; we store the cost amounts +
            # a single currency code (they share one currency). v2.15.3 wires
            # these to four trip_*_cost diagnostic sensors (sensor.py), with the
            # currency exposed as a per-sensor attribute.
            overall_cost = trip_stats.get("overallCost") or (
                overview.get("overallCost") if isinstance(overview, dict) else None
            )
            if isinstance(overall_cost, dict):
                def _cost(node: Any) -> float | None:
                    if isinstance(node, dict):
                        c = node.get("cost")
                        return float(c) if isinstance(c, (int, float)) else None
                    return float(node) if isinstance(node, (int, float)) else None

                d.trip_total_cost = _cost(overall_cost.get("totalCost"))
                d.trip_fuel_cost = _cost(overall_cost.get("fuelCost"))
                d.trip_electricity_cost = _cost(overall_cost.get("electricityCost"))
                d.trip_cng_cost = _cost(overall_cost.get("cngCost"))
                # Currency lives on whichever sub-cost is present.
                for sub in (
                    overall_cost.get("totalCost"),
                    overall_cost.get("fuelCost"),
                    overall_cost.get("electricityCost"),
                ):
                    if isinstance(sub, dict) and sub.get("costCurrency"):
                        d.trip_cost_currency = str(sub["costCurrency"])
                        break

        # v2.11.0 (myskoda PR #586 source-verified): charging stats
        # from the replacement endpoint. monthSections[].entries[] each
        # carry an aggregated charging session with primaryValue (kWh)
        # + secondaryValue (duration) + sessionDetails.
        if isinstance(charging_stats_v2, dict):
            month_sections = charging_stats_v2.get("monthSections") or []
            all_entries: list[dict[str, Any]] = []
            for section in month_sections:
                if isinstance(section, dict):
                    entries = section.get("entries") or []
                    for entry in entries:
                        if isinstance(entry, dict):
                            all_entries.append(entry)
            # Lifetime aggregate: sum primaryValue.value (kWh) across
            # all entries when the value type is kWh.
            total_kwh = 0.0
            for entry in all_entries:
                pv = entry.get("primaryValue") or {}
                if isinstance(pv, dict):
                    unit = str(pv.get("unit", "")).lower()
                    val = pv.get("value")
                    if unit in ("kwh", "kw_h") and isinstance(val, (int, float)):
                        total_kwh += float(val)
            if total_kwh > 0:
                d.total_charged_energy_kwh = round(total_kwh, 2)
            # Last session = first entry (newest first per myskoda model).
            if all_entries:
                last = all_entries[0]
                pv_last = last.get("primaryValue") or {}
                sv_last = last.get("secondaryValue") or {}
                details = last.get("sessionDetails") or {}
                if isinstance(pv_last, dict):
                    last_kwh = pv_last.get("value")
                    if isinstance(last_kwh, (int, float)):
                        d.last_charging_session_kwh = float(last_kwh)
                if isinstance(sv_last, dict):
                    last_min = sv_last.get("value")
                    if isinstance(last_min, (int, float)):
                        d.last_charging_session_duration_min = int(last_min)
                started_at = details.get("startedAt") if isinstance(details, dict) else None
                if isinstance(started_at, str) and started_at:
                    d.last_charging_session_start = started_at
                current_type = details.get("currentType") if isinstance(details, dict) else None
                if isinstance(current_type, str) and current_type:
                    d.last_charging_session_current_type = current_type.upper()
                # recent_charging_sessions = compact list of last 10
                recent: list[dict[str, Any]] = []
                for e in all_entries[:10]:
                    e_pv = e.get("primaryValue") or {}
                    e_sv = e.get("secondaryValue") or {}
                    e_det = e.get("sessionDetails") or {}
                    recent.append({
                        "started_at": (
                            e_det.get("startedAt")
                            if isinstance(e_det, dict) else None
                        ),
                        "kwh": (
                            e_pv.get("value")
                            if isinstance(e_pv, dict) else None
                        ),
                        "duration_min": (
                            e_sv.get("value")
                            if isinstance(e_sv, dict) else None
                        ),
                    })
                d.recent_charging_sessions = recent

        # v2.11.0 (myskoda Health model source-verified): per-category
        # warning lights from the dedicated health endpoint. Shape:
        # {"capturedAt":"...","mileageInKm":12345,
        #  "warningLights":[{"category":"ENGINE","defects":[{"text":...,
        #    "priority":"HIGH","icon":"..."}]}, ...]}
        # #649: the list carries one entry per monitored category even
        # when the car is healthy (empty `defects`), so a warning counts
        # only where its own `defects` list is non-empty. See
        # parse_skoda_warning_lights.
        if isinstance(health_v1, dict):
            warn = parse_skoda_warning_lights(health_v1.get("warningLights"))
            if warn:
                d.warning_active = warn["warning_active"]
                d.warning_count = warn["warning_count"]
                d.warning_engine = warn["warning_engine"]
                d.warning_brakes = warn["warning_brakes"]
                d.warning_tyre = warn["warning_tyre"]
                d.warning_oil = warn["warning_oil"]
                if "warning_messages" in warn:
                    d.warning_messages = warn["warning_messages"]

        if isinstance(driving_score, dict):
            # v2.11.0 (myskoda source-verified): the top-level `score`
            # and `drivingScoreClass` keys were a scout-derived guess
            # that DrivingScore model does not include. The canonical
            # shape is per-period objects (daily/weekly/monthly/quarterly)
            # each with a `main` score and breakdown metrics. Prefer
            # weeklyScore.main as the "headline" value, then monthlyScore
            # as fallback. Class field doesn't exist upstream - drop.
            for period_key in ("weeklyScore", "monthlyScore",
                               "quarterlyScore", "dailyScore"):
                period = driving_score.get(period_key)
                if isinstance(period, dict):
                    main = period.get("main")
                    if isinstance(main, (int, float)):
                        d.driving_score = int(main)
                        break
            # Legacy fallback if any firmware actually ships top-level.
            if d.driving_score is None:
                score = driving_score.get("score")
                if isinstance(score, (int, float)):
                    d.driving_score = int(score)
            cls = driving_score.get("drivingScoreClass")
            if isinstance(cls, str) and cls:
                d.driving_score_class = cls

        # v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation fallback.
        # Skoda already reads `driving-range.carType` directly (Phase 8
        # PR #1), so this is a NO-OP for Skoda users with the standard
        # response shape. The helper only fires if the direct read
        # returned None (e.g. older firmware or rotated schema) — gives
        # those Skoda users a derived car_type from has_battery +
        # has_combustion + primary_engine_type.
        from .._util import derive_car_type_if_missing  # noqa: PLC0415

        derive_car_type_if_missing(d)

        return d

    # ── Static info enrichment (v1.20.0 Bundle 2 Phase A) ───────────────────
    # vehicle-information + equipment endpoints serve static data that
    # changes only on physical vehicle changes (firmware update, plate
    # swap, hardware retrofit). Coordinator caches 24h via the same
    # capability-cache pattern (see ``coordinator.refresh_capabilities``).

    async def get_vehicle_static_info(self, vin: str) -> dict[str, Any]:
        """v1.20.0 Bundle 2 Phase A — combined static-data fetch.

        Returns a single dict combining the static endpoints so the
        coordinator can cache + apply with one method call:

            {
              "info":      {... from /vehicle-information/{vin}},
              "equipment": [{...}, ...] from /vehicle-information/{vin}/equipment,
              "renders":   {... from /vehicle-information/{vin}/renders},
            }

        ``renders`` added v1.22.x foundation (myskoda PR #571 — multi-
        angle composite renders for the image platform). All three
        calls use the existing best-effort error handling — a 404 on
        any endpoint just leaves that key missing from ``out``.
        """
        # mypy strict can't infer the unpacked types from
        # ``asyncio.gather(..., return_exceptions=True)`` because each
        # slot may be ``T | BaseException``. Bind the result first
        # then index with explicit isinstance gates so the type
        # narrowing is unambiguous.
        results = await asyncio.gather(
            self.get_vehicle_info(vin),
            self.get_vehicle_equipment(vin),
            self.get_vehicle_renders(vin),
            return_exceptions=True,
        )
        info_result = results[0]
        equip_result = results[1]
        renders_result = results[2]
        out: dict[str, Any] = {}
        if isinstance(info_result, dict) and info_result:
            out["info"] = info_result
        if isinstance(equip_result, dict) and equip_result:
            equip_list = equip_result.get("equipment")
            if isinstance(equip_list, list):
                out["equipment"] = equip_list
        if isinstance(renders_result, dict) and renders_result:
            out["renders"] = renders_result
        return out

    # ── Commands ─────────────────────────────────────────────────────────────

    async def command_lock(self, vin: str, spin: str = "") -> None:
        # v2.31.0 — MyŠkoda 8.15.0 migrated vehicle-access to v2: the app wires
        # ONLY bff_vehicle_access/v2 (v1 VehicleAccessApi is compiled but has zero
        # references tree-wide; Koin DI resolves the v2 interface). v2 lock takes
        # AccessRequestDto{spin} (spin nullable → an empty body is structurally
        # valid, but an S-PIN-enforcing car needs it — v1 even required it).
        # Grounded: bff_vehicle_access/v2/VehicleAccessApi.smali (lockVehicle,
        # POST api/v2/vehicle-access/{vin}/lock, Body AccessRequestDto),
        # AccessRequestDto.smali @Json "spin".
        pin = spin or self._spin
        payload: dict[str, Any] = {"spin": pin} if pin else {}
        await self._post(f"{_BASE}/api/v2/vehicle-access/{vin}/lock", json=payload)

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        # v2.31.0 — v2 route (see command_lock) + the wire key was renamed
        # ``currentSpin`` (v1 SpinDto) → ``spin`` (v2 AccessRequestDto).
        pin = spin or self._spin
        payload: dict[str, Any] = {"spin": pin} if pin else {}
        await self._post(f"{_BASE}/api/v2/vehicle-access/{vin}/unlock", json=payload)

    async def command_start_climate(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v2/air-conditioning/{vin}/start", json={})

    async def command_stop_climate(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v2/air-conditioning/{vin}/stop", json={})

    async def command_start_charging(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v1/charging/{vin}/start", json={})

    async def command_stop_charging(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v1/charging/{vin}/stop", json={})

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,
        longitude: float | None = None,
        duration_s: int = 10,  # noqa: ARG002 - Skoda's DTO carries no duration
        honk: bool = False,
    ) -> None:
        # v2.20.0 (APK audit) — Skoda's HonkAndFlashRequestDto$Mode enum has only
        # HONK_AND_FLASH / FLASH; "FLASH_ONLY" is the VW-EU/Audi value that was
        # wrongly copied here and rejected. Flash-only = FLASH. No duration field.
        # v2.31.0 (8.15.0 APK) — two grounded fixes:
        #   (1) migrate to the v2 route (vehicle-access moved to v2 app-wide);
        #   (2) HonkAndFlashRequestDto carries a REQUIRED ``vehiclePosition``
        #       {latitude, longitude} (non-null on both v1 and v2) — we already
        #       receive lat/lng and previously discarded them, so a strict
        #       backend rejected the body. Grounded:
        #       bff_vehicle_access/v2/VehicleAccessApi.smali (honkAndFlash, POST
        #       api/v2/vehicle-access/{vin}/honk-and-flash, Body
        #       HonkAndFlashRequestDto), GpsCoordinatesDto.smali (latitude/
        #       longitude doubles).
        body: dict[str, Any] = {"mode": "HONK_AND_FLASH" if honk else "FLASH"}
        if latitude is None or longitude is None:
            # vehiclePosition is a REQUIRED non-null field (8.15.0
            # HonkAndFlashRequestDto) — a position-less body is 400-rejected.
            # Fail with an actionable message instead of emitting the doomed
            # request, so the user knows to refresh/wake the car first.
            raise ValueError(
                "Škoda honk-and-flash needs the vehicle's GPS position, which "
                "isn't cached yet — wake or refresh the car (so a location poll "
                "lands) and try again."
            )
        body["vehiclePosition"] = {"latitude": latitude, "longitude": longitude}
        await self._post(
            f"{_BASE}/api/v2/vehicle-access/{vin}/honk-and-flash",
            json=body,
        )

    async def command_wake(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v1/vehicle-wakeup/{vin}?applyRequestLimiter=true", json={})

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        # v2.20.0 (APK audit) — read-vs-write field trap: the set-charge-limit
        # request DTO (ChargeLimitDto, MyŠkoda 8.14.0) uses ``targetSOCInPercent``,
        # not the read-side ``targetStateOfChargeInPercent`` — the old key was
        # silently ignored so the target was never applied.
        # v2.20.1 (#866) — the mysmob charging-SETTINGS routes are PUT, not POST
        # (actions like start/stop stay POST). A POST here 500s server-side
        # (@tader, Elroq) even with the correct field. Confirmed against the
        # upstream myskoda rest_api (set_charge_limit → PUT).
        await self._put(
            f"{_BASE}/api/v1/charging/{vin}/set-charge-limit",
            json={"targetSOCInPercent": target},
        )

    async def command_update_charging_settings(
        self,
        vin: str,
        target_soc: int | None = None,
        max_charge_current: str | None = None,
        auto_unlock_charge: bool | None = None,  # noqa: ARG002
    ) -> None:
        """v2.15.10 — Skoda settable max charging current (MAXIMUM/REDUCED).

        Mirrors the brand-polymorphic ``command_update_charging_settings``
        contract that ``coordinator.async_update_charging_settings`` already
        dispatches (see SeatCupraClient for the OLA sibling). Only the
        ``max_charge_current`` field is wired for Skoda here; the endpoint
        and the ``MAXIMUM``/``REDUCED`` enum are grounded in the mysmob
        contract (PUT /api/v1/charging/{vin}/set-charging-current) and the
        read-side ``settings.maxChargingCurrent`` shape used by
        ``get_charging_profiles``. v2.20.1 (#866) — the write DTO field is
        ``chargingCurrent`` (not the read-side ``maxChargingCurrent``) and the
        verb is PUT, confirmed against upstream myskoda (set_reduced_current_limit).

        ``target_soc`` is intentionally routed through the dedicated
        ``set-charge-limit`` endpoint (``command_set_target_soc``) — the
        combined update-settings body is SEAT/CUPRA-only, so when a caller
        passes ``target_soc`` here we forward it to the grounded per-field
        endpoint rather than guessing a combined Skoda body.
        ``auto_unlock_charge`` has its own Skoda endpoint too and is not
        wired through this method.
        """
        if target_soc is not None:
            await self.command_set_target_soc(vin, int(target_soc))
        if max_charge_current is not None:
            await self._put(
                f"{_BASE}/api/v1/charging/{vin}/set-charging-current",
                json={"chargingCurrent": str(max_charge_current)},
            )

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/settings/target-temperature",
            json={"temperatureValue": temp_c, "unitInCar": "CELSIUS"},
        )

    async def command_start_window_heating(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v2/air-conditioning/{vin}/start-window-heating", json={})

    async def command_stop_window_heating(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v2/air-conditioning/{vin}/stop-window-heating", json={})

    # ── v2.0.0 Big-Bang: Aux Heating cross-brand parity (Issue from audit P2) ──
    # Skoda Webasto/Standheizung. Endpoint pattern from mysmob app traffic
    # (upstream iobroker.vw-connect Skoda + skodaconnect/myskoda v1.x reference).
    async def command_start_aux_heating(self, vin: str, spin: str = "") -> None:
        """Start Webasto auxiliary heater.

        v2.31.0 (8.15.0 APK) — the empty ``{}`` body was rejected: the
        ``StartAuxiliaryHeatingConfigurationDto`` requires ``spin`` (non-null,
        ``StartAuxiliaryHeatingConfigurationDto.smali`` @Json ``spin`` + the
        ``<init>`` null-check), so aux heating never actually started. Send the
        S-PIN. Optional DTO fields ``startMode`` / ``durationInSeconds`` /
        ``targetTemperature`` are left off (defaulted server-side).
        """
        pin = spin or self._spin
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/auxiliary-heating/start",
            json={"spin": pin} if pin else {},
        )

    async def command_stop_aux_heating(self, vin: str) -> None:
        """Stop Webasto auxiliary heater. No SPIN required (matches SEAT/CUPRA)."""
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/auxiliary-heating/stop", json={}
        )

    # ── 2.31.0 wave — camping + seat-heating (APK-GROUNDED gg LIVE 8.15.0) ─────
    # Every route + JSON field below is a LITERAL from the decoded MyŠkoda
    # 8.15.0 app (androguard/apktool, 2026-08): the AirConditioningApi Retrofit
    # methods ``startCamping`` (POST ``camping/start``, @Body
    # ``AirConditioningTargetTemperatureDto`` — same {temperatureValue, unitInCar}
    # shape as target-temperature), ``stopCamping`` (POST ``camping/stop``, no
    # body) and ``setAirConditioningSeatsHeating`` (POST
    # ``settings/seats-heating``, @Body ``SeatHeatingSettingsDto`` with the four
    # nullable Boolean seats frontLeft/frontRight/rearLeft/rearRight). LIVE-GATED:
    # no Skoda tester has confirmed these against a car yet, so the tests pin the
    # grounded wire shape and HA entity/service wiring is a follow-up once a
    # status dump lands — the same staged approach as the v2.20.0 routes above.
    async def command_start_camping(self, vin: str, temp_c: float = 20.0) -> None:
        """Start camping mode. The app's ``camping/start`` carries a target
        temperature (``AirConditioningTargetTemperatureDto``), identical to the
        climate ``target-temperature`` body."""
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/camping/start",
            json={"temperatureValue": temp_c, "unitInCar": "CELSIUS"},
        )

    async def command_stop_camping(self, vin: str) -> None:
        """Stop camping mode. ``camping/stop`` takes no body."""
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/camping/stop", json={}
        )

    async def command_set_seat_heating(
        self,
        vin: str,
        *,
        front_left: bool | None = None,
        front_right: bool | None = None,
        rear_left: bool | None = None,
        rear_right: bool | None = None,
    ) -> None:
        """Set seat-heating per seat. Only the seats passed (non-None) are sent,
        so an automation can toggle one seat without disturbing the others."""
        body: dict[str, bool] = {}
        if front_left is not None:
            body["frontLeft"] = front_left
        if front_right is not None:
            body["frontRight"] = front_right
        if rear_left is not None:
            body["rearLeft"] = rear_left
        if rear_right is not None:
            body["rearRight"] = rear_right
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/settings/seats-heating",
            json=body,
        )

    async def command_send_destination(
        self,
        vin: str,
        latitude: float,
        longitude: float,
        name: str,
        *,
        city: str = "",
        country: str = "",
        state: str = "",  # noqa: ARG002 - Škoda's MapPositionAddressDto has no state
        street: str = "",
        house_number: str = "",
        zip_code: str = "",
    ) -> None:
        """Send a navigation destination to the car (APK-GROUNDED, 8.15.0).

        Endpoint ``POST api/v3/maps/navigation/destination``, @Body
        ``SendDestinationRequestDto`` (Moshi, ``bff_maps/v3``). Required fields
        ``id`` / ``type`` / ``vin``; ``name`` / ``coordinates`` / ``address`` /
        ``savedLocationId`` optional. ``coordinates`` is ``GpsCoordinatesDto``
        ``{latitude, longitude}`` (NOT the SEAT/CUPRA ``geoCoordinate`` shape at
        their own ``/v1/users/vehicles/{vin}/destination`` — different endpoint,
        do not reuse). ``address`` is ``MapPositionAddressDto``.

        ``type`` is a Moshi String drawn from a closed place-kind vocabulary
        (``wt0/l.smali``); for a raw coordinate the generic-point member is
        ``"LOCATION"`` — never an off-vocabulary value (the app mapper rejects
        it). ``id`` is a required free String; a real place has a backend id, so
        for a HA-originated coordinate we mint a client UUID (accepted by the
        non-null String contract; a captured real request is the only way to
        fully confirm the backend tolerates an arbitrary id). LIVE-GATED.
        """
        body: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "type": "LOCATION",
            "vin": vin,
            "name": name,
            "coordinates": {"latitude": latitude, "longitude": longitude},
        }
        address = {
            k: val
            for k, val in {
                "city": city,
                "country": country,
                "houseNumber": house_number,
                "street": street,
                "zipCode": zip_code,
            }.items()
            if val
        }
        if address:
            body["address"] = address
        await self._post(
            f"{_BASE}/api/v3/maps/navigation/destination", json=body
        )

    async def command_set_profile_target_soc(
        self, vin: str, profile_id: int | str, target: int
    ) -> None:
        """Set the target SoC of ONE charging profile — per-location target (#25).

        The global ``set-charge-limit`` sets a single SoC for the car; a
        per-location target lives on a charging PROFILE. MyŠkoda updates a profile
        by echoing the WHOLE profile back — there is no partial-PATCH DTO — so we
        read the current profiles, find this one, mutate only
        ``settings.targetStateOfChargeInPercent`` (NOT the global
        ``targetSOCInPercent`` key), and PUT it. ``profile_id`` and the profile
        come from ``get_charging_profiles``; its ``currentVehiclePositionProfile``
        names the profile active at the car's GPS right now.

        Endpoint ``PUT api/v1/charging/{vin}/profiles/{id}``, Body the full
        ``ChargingProfileDto``. APK-grounded (8.15.0), LIVE-GATED.
        """
        data = await self.get_charging_profiles(vin)
        profiles = data.get("chargingProfiles") or []
        profile = next(
            (
                p for p in profiles
                if isinstance(p, dict) and str(p.get("id")) == str(profile_id)
            ),
            None,
        )
        if profile is None:
            raise ValueError(f"Skoda charging profile {profile_id!r} not found")
        settings = profile.get("settings")
        if not isinstance(settings, dict):
            settings = {}
            profile["settings"] = settings
        settings["targetStateOfChargeInPercent"] = int(target)
        await self._put(
            f"{_BASE}/api/v1/charging/{vin}/profiles/{profile_id}", json=profile
        )

    async def ask_assistant(
        self,
        vin: str,
        user_input: str,
        *,
        user_timezone: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Ask the MyŠkoda AI assistant ("Laura") — APK-GROUNDED (8.15.0).

        ``POST api/v2/ai-assistant/ask``, @Body ``AIAssistantRequestDto`` (all
        fields optional: userInput, userTimezone, vin, sessionId, routePlanner).
        Returns ``AIAssistantResponseDto{type, summary, sessionId, routeDetails}``
        — the ``summary`` is standalone human-readable free text.

        Read-only ADVISORY: EV trip/route planning + product Q&A. The
        AiAssistantApi package has ZERO command DTOs (no lock/climate/charge), so
        this never actuates the car. Uses the mysmob Bearer we already hold; no
        Play-Integrity/attestation (only ``v2/auth/HttpBearerAuth``). Pass
        ``session_id`` from a prior answer for multi-turn continuity. LIVE-GATED:
        answer quality/latency unverified by statics.
        """
        body: dict[str, Any] = {"userInput": user_input, "vin": vin}
        if user_timezone:
            body["userTimezone"] = user_timezone
        if session_id:
            body["sessionId"] = session_id
        data = await self._post(f"{_BASE}/api/v2/ai-assistant/ask", json=body)
        return data if isinstance(data, dict) else {}

    # ── v2.20.0 — additional mysmob command routes ────────────────────────
    # APK-GROUNDED. Each route + JSON DTO field below is a LITERAL string from
    # the decoded MyŠkoda 8.14.0 app: the route paths and the DTO wrappers
    # ``ChargingCareModeDto(chargingCareMode=…)``, ``AutoUnlockPlugDto(
    # autoUnlockPlug=…)`` and the ActiveVentilation ``durationInSeconds`` field.
    # v2.20.1 (#866) — the charging-SETTINGS routes are PUT (not POST) and their
    # value shapes were confirmed against upstream myskoda: care-mode is the
    # string enum ``ACTIVATED``/``DEACTIVATED`` (not a bool), auto-unlock is
    # ``PERMANENT``/``OFF``. Actions (start/stop/window-heating) stay POST.
    #
    # WIRING STATUS:
    # - ``command_set_battery_care`` OVERRIDES the base (which raises
    #   NotImplementedError): Skoda already parses ``battery_care_enabled`` so
    #   ``VagBatteryCareSwitch`` already spawns and dispatches this — until now
    #   it hit the base stub and crashed. This override makes the existing
    #   switch actually work. Still LIVE-GATED (no Skoda tester has confirmed
    #   the body), but it is a real fix for an already-visible control.
    # - active-ventilation + auto-unlock stay client-surface groundwork: we
    #   don't parse an active-ventilation state (no Skoda status sample to
    #   ground the JSON path), so a read-gated switch can't spawn honestly; the
    #   auto-unlock write enum is unconfirmed. HA entities are a follow-up once
    #   a Skoda owner provides a status dump.

    async def command_set_battery_care(self, vin: str, enabled: bool) -> None:
        """Toggle battery Care Mode (caps charge target to protect the pack).

        Overrides ``CariadBaseClient.command_set_battery_care`` (which raises
        NotImplementedError) so the existing ``VagBatteryCareSwitch`` works for
        Skoda. Route + DTO field ``chargingCareMode`` are grounded in MyŠkoda
        8.14.0 (``ChargingCareModeDto``). v2.20.1 (#866) — verb is PUT (a
        charging-SETTINGS route, not an action) and the value is the string
        enum ``ACTIVATED``/``DEACTIVATED``, NOT a JSON bool — confirmed against
        upstream myskoda (set_battery_care_mode). The old POST+bool 500'd.
        """
        await self._put(
            f"{_BASE}/api/v1/charging/{vin}/set-care-mode",
            json={"chargingCareMode": "ACTIVATED" if enabled else "DEACTIVATED"},
        )

    async def command_set_auto_unlock_plug(self, vin: str, mode: str) -> None:
        """Set auto-unlock-plug-when-charged behaviour.

        Route + DTO field ``autoUnlockPlug`` grounded in MyŠkoda 8.14.0
        (``AutoUnlockPlugDto``). v2.20.1 (#866) — verb is PUT (charging-SETTINGS
        route) and the enum is ``PERMANENT``/``OFF``, confirmed against upstream
        myskoda (set_auto_unlock_charging). ``mode`` is still passed through so
        the caller supplies the exact token; no HA entity is wired yet.
        """
        await self._put(
            f"{_BASE}/api/v1/charging/{vin}/set-auto-unlock-plug",
            json={"autoUnlockPlug": str(mode)},
        )

    async def command_start_active_ventilation(
        self, vin: str, duration_min: int = 30  # noqa: ARG002 - no writable duration
    ) -> None:
        """Start cabin active ventilation (airing without heating).

        v2.31.0 (8.15.0 APK) — ``startActiveVentilation`` takes NO request body
        (``AirConditioningApi.smali``: ``@Path`` vin + Continuation only), so the
        old ``{"durationInSeconds": …}`` body was fabricated. ``durationInSeconds``
        is a READ-only field of the active-ventilation status, writable nowhere;
        send an empty body like the other start/stop actions. ``duration_min`` is
        accepted for signature compatibility and ignored.
        """
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/active-ventilation/start",
            json={},
        )

    async def command_stop_active_ventilation(self, vin: str) -> None:
        """Stop cabin active ventilation. Route grounded in MyŠkoda 8.14.0."""
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/active-ventilation/stop", json={}
        )

    # ── v2.0.0 Big-Bang: Driving Score (Skoda-only metric) ────────────────
    async def get_driving_score(self, vin: str) -> dict[str, Any] | None:
        """Fetch Skoda driving score (efficiency metric, 0-100).

        Endpoint: /api/v2/vehicle-status/{vin}/driving-score
        Returns: {"score": int, "drivingScoreClass": str, "lastUpdate": str}
        Returns None on 404 (not all Skoda models expose this).
        """
        try:
            data = await self._get(f"{_BASE}/api/v2/vehicle-status/{vin}/driving-score")
            return data if isinstance(data, dict) else None
        except Exception:
            return None
