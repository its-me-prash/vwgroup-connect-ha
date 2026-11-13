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
import time
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

# The carport has no explicit body/chassis field, but the Audi sales-type code
# (``modelCode``, e.g. "8T30H9") encodes it in its 3rd character — the long-standing
# Audi Verkaufstyp convention. We only decode the distinctive bodies and leave sedans
# / anything unrecognised bodyless (never guess) so the model reads e.g. "A5 Coupé TDI"
# in the S6 style, rather than a possibly-wrong form. (acpp ``prCodes`` is empty and the
# myAudi vgql render/media resolvers reject the acpp client — live-verified — so this
# code is the only body source for a dongle car.)
_ACPP_BODY_FORM = {"3": "Coupé", "5": "Avant", "7": "Cabriolet", "A": "Sportback"}

# Paginated history resources (logbook / fuel log). acpp serves them in INSERTION
# order — oldest first, ``sort.unsorted`` — and a bare GET returns only the first 20,
# i.e. the OLDEST entries. Live 2026-11-13 (A5 B8): 42 trips; page 0 ended on 01.10
# while the real newest trip was 01.11, ~900 km later, so the reader showed a stale
# odometer and last trip. The OEM app pages through everything and sorts locally
# (3.6.5 ``RestoreWorker``: driverlogs ``limit=100``, fuellog ``limit=50``); the same
# limits are used here and were live-verified the same day.
_DRIVERLOG_PAGE_LIMIT = 100
_FUELLOG_PAGE_LIMIT = 50
# Per-poll page cap. Page 0 is always read (it carries ``totalPages``); beyond the
# cap the LAST pages are kept, because those hold the newest entries.
_MAX_HISTORY_PAGES = 5
# Per-trip time series (``…/driverlogs/{id}/polldata``). limit=300 was live-verified
# 2026-11-13 (237 samples in one page); ~5 s per sample, so 300 ≈ 25 min of driving.
# 10 pages ≈ 4 h, enough for any single trip's maxima.
_POLLDATA_PAGE_LIMIT = 300
_MAX_POLLDATA_PAGES = 10
# A trip without samples (backup off on the phone, upload still pending, or a
# request that failed) is asked again after this long, not on every poll.
_POLLDATA_RETRY_S = 3600.0


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


def _epoch_ms_to_datetime(val: Any) -> str | None:
    """acpp trip / refuel / parking timestamps are epoch-millisecond ints.

    Return a full ISO-8601 UTC datetime (time-of-day matters for a trip end or a
    position fix, unlike the carport dates), or None on anything unparseable.
    """
    try:
        ms = int(str(val))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _trip_order(trip: dict[str, Any]) -> tuple[Any, Any]:
    """Sort key: newest ``endTime`` first, then the highest server ``id``.

    Server-side duplicate copies of one trip share their ``endTime``; only the
    LAST uploaded copy (highest ``id``) carries the per-trip ``polldata`` — live
    2026-11-13: of 8 copies, 7 had 0 samples and the highest-id copy had 682. So
    whenever a copy has to stand for its trip, it must be that one.
    """
    end = trip.get("endTime")
    tid = trip.get("id")
    return (
        end if isinstance(end, (int, float)) and not isinstance(end, bool) else 0,
        tid if isinstance(tid, (int, float)) and not isinstance(tid, bool) else 0,
    )


def _newest_driverlog(snap: dict[str, Any]) -> dict[str, Any] | None:
    """The most-recent trip in the merged logbook (see ``_trip_order``).

    ``get_raw_snapshot`` reads every page (the server sends oldest first), so the
    newest trip is in here wherever the server put it. Defensive: any shape
    surprise → None, so a missing/odd logbook never breaks the status read.
    """
    dl = snap.get("driverlogs")
    content = dl.get("content") if isinstance(dl, dict) else None
    if not isinstance(content, list) or not content:
        return None
    trips = [t for t in content if isinstance(t, dict)]
    if not trips:
        return None
    return max(trips, key=_trip_order)


def _num(val: Any) -> float | None:
    """A real number, or None (bools and non-numbers excluded)."""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return None


# EcoScore breakdown: wire key → attribute name. ``*Result`` are 0-100 marks,
# and a mark is the share of positively rated intervals, rounded down (live
# 2026-11-13: brake 190 positive / 13 negative → 93; the formula holds for 145 of
# 161 marks in the logbook). So ``*NegativeCount`` counts intervals RATED
# negative — on a 52-minute trip about one in fifteen — not hard-braking events;
# the attribute names say exactly that.
_ECO_DETAIL_KEYS = (
    ("accelerationResult", "eco_acceleration"),
    ("brakeResult", "eco_braking"),
    ("engineSpeedResult", "eco_engine_speed"),
    ("speedResult", "eco_speed"),
    ("coolantTemperatureResult", "eco_coolant"),
    ("brakeNegativeCount", "eco_braking_negative_count"),
    ("accelerationNegativeCount", "eco_acceleration_negative_count"),
)


def _eco_detail(eco: Any) -> dict[str, int]:
    """The EcoScore breakdown of one trip as int attributes (missing keys skipped)."""
    if not isinstance(eco, dict):
        return {}
    out: dict[str, int] = {}
    for wire, attr in _ECO_DETAIL_KEYS:
        val = _num(eco.get(wire))
        if val is not None:
            out[attr] = int(round(val))
    return out


# Elevation from the per-sample GPS altitude is noisy: summing every step gave
# 107 m up / 155 m down on a live trip whose hysteresis-filtered figure was a
# stable 71 / 121 m at both 3 m and 5 m (net −48 m either way). Count a climb or
# descent only once it exceeds this much.
_ELEVATION_HYSTERESIS_M = 5.0
# "Engine warm" for the warm-up time: coolant at or above this.
_WARM_COOLANT_C = 80.0


def _elevation(altitudes: list[float]) -> tuple[float, float]:
    """(gain, loss) in metres over a hysteresis band, see _ELEVATION_HYSTERESIS_M."""
    gain = loss = 0.0
    ref = altitudes[0]
    for alt in altitudes[1:]:
        if alt - ref >= _ELEVATION_HYSTERESIS_M:
            gain += alt - ref
            ref = alt
        elif ref - alt >= _ELEVATION_HYSTERESIS_M:
            loss += ref - alt
            ref = alt
    return gain, loss


def _polldata_summary(samples: list[Any]) -> dict[str, Any] | None:
    """Per-trip figures from the ``polldata`` time series, or None without data.

    The first samples of a trip are placeholders (all zeros, then altitude only,
    live 2026-11-13), so only real readings count: positive speed / rpm / coolant
    / altitude, and for the smooth-driving share only samples where the car was
    running. A channel without a real reading yields no figure rather than a 0.
    Units follow the app's upload body: km/h, rpm, °C, m/s²; altitude in metres.
    """
    rows = sorted(
        (s for s in samples if isinstance(s, dict)),
        key=lambda s: _num(s.get("recordedAt")) or 0.0,
    )

    def real(key: str) -> list[float]:
        return [v for s in rows for v in (_num(s.get(key)),) if v is not None and v > 0]

    out: dict[str, Any] = {}
    speeds, rpms, coolants = real("speed"), real("engineSpeed"), real("coolant")
    if speeds:
        out["max_speed_kmh"] = round(max(speeds), 1)
    if rpms:
        out["max_engine_rpm"] = int(round(max(rpms)))
    if coolants:
        out["max_coolant_c"] = round(max(coolants), 1)

    # Strongest braking / acceleration (signed m/s² on the wire).
    accels = [v for s in rows for v in (_num(s.get("acceleration")),) if v is not None]
    if any(a < 0 for a in accels):
        out["max_braking_ms2"] = round(-min(accels), 2)
    if any(a > 0 for a in accels):
        out["max_acceleration_ms2"] = round(max(accels), 2)

    altitudes = real("altitude")
    if len(altitudes) >= 2:
        gain, loss = _elevation(altitudes)
        out["elevation_gain_m"] = int(round(gain))
        out["elevation_loss_m"] = int(round(loss))

    # Share of samples flagged smooth, among those where the car was running.
    running = [
        s for s in rows
        if (_num(s.get("speed")) or 0) > 0 or (_num(s.get("engineSpeed")) or 0) > 0
    ]
    flags = [f for s in running for f in (s.get("isSmooth"),) if isinstance(f, bool)]
    if flags:
        out["smooth_share_pct"] = int(round(100 * sum(flags) / len(flags)))

    # Warm-up: from the first coolant reading to the first at _WARM_COOLANT_C.
    # 0 when the engine was already warm; no figure when it never got there.
    timed = [
        (t, c) for s in rows
        for t, c in ((_num(s.get("recordedAt")), _num(s.get("coolant"))),)
        if t is not None and c is not None and c > 0
    ]
    if timed:
        warm_at = next((t for t, c in timed if c >= _WARM_COOLANT_C), None)
        if warm_at is not None:
            out["warmup_min"] = round((warm_at - timed[0][0]) / 60000, 1)
    return out or None


def _trip_key(trip: dict[str, Any], idx: int) -> Any:
    """Identity of a logical trip across server-side duplicates.

    The app can upload the same local trip more than once; the server then stores
    copies that differ only in ``id`` (live 2026-11-13: one trip 8x, 42 entries =
    35 trips). ``driverLogId`` is the app's local trip id and stays the same across
    those copies. Entries without it are treated as distinct.
    """
    local_id = trip.get("driverLogId")
    if isinstance(local_id, str) and local_id:
        return local_id
    return ("idx", idx)


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
        # Newest trip's polldata summary: trip server id → (monotonic fetch time,
        # summary or None). A finished trip's series does not change, so a summary
        # is fetched once; one entry only (the newest trip), replaced when it changes.
        self._polldata_cache: dict[Any, tuple[float, dict[str, Any] | None]] = {}

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """Log in (authorization_code+PKCE) and cache the durable token set."""
        self._tokens = await self._auth.authenticate(
            self._email, self._password, mfa_code=mfa_code
        )

    @property
    def tokens(self) -> TokenSet | None:
        return self._tokens

    async def _get(self, path: str, _retry: bool = True) -> tuple[int, Any]:
        if not self._tokens or not self._tokens.access_token:
            raise AuthenticationError("plug&play client is not authenticated")
        headers = {
            "Authorization": f"Bearer {self._tokens.access_token}",
            "Accept": "application/json",
            # The carport (master-data) endpoint reads the language from
            # Accept-Language and needs a SINGLE tag: it 500s when the header is
            # absent and — verified live 2026-08-24 — 400s on a multi-value /
            # q-weighted value (e.g. "de-DE, en-US;q=0.9"). A bare "de-DE" (or
            # "de"/"en-US") returns 200. Other endpoints ignore it, so a single
            # tag on every request is safe.
            "Accept-Language": "de-DE",
            "User-Agent": self._brand.user_agent,
        }
        async with self._session.get(
            f"{self.API_BASE}/{path}", headers=headers, timeout=_TIMEOUT
        ) as resp:
            status = resp.status
            try:
                body = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001 — error bodies may be text
                body = await resp.text()
        # acpp is a STANDALONE client (not a BaseClient), so it does NOT inherit
        # the base 401→refresh path. The access token is short-lived (~1h) and the
        # refresh token rotates — on a 401, refresh once and retry (mirroring
        # BaseClient._request), and keep the rotated token so the next poll doesn't
        # replay a dead one. A persistent 401 falls through unchanged.
        if (
            status == 401 and _retry
            and self._tokens is not None and self._tokens.refresh_token
        ):
            try:
                self._tokens = await self._auth.refresh(self._tokens.refresh_token)
            except Exception:  # noqa: BLE001 — refresh failed → surface the 401
                return status, body
            return await self._get(path, _retry=False)
        return status, body

    async def _get_all_pages(
        self, path: str, limit: int, extra: str = "",
        max_pages: int = _MAX_HISTORY_PAGES,
    ) -> tuple[int, Any]:
        """Read a paginated acpp list resource completely (see ``_DRIVERLOG_PAGE_LIMIT``).

        Returns ``(status, body)`` where ``body`` is page 0 with ``content`` replaced
        by the concatenation of every page read. A failing later page stops the walk
        and keeps what was read; a failing page 0 returns its status and body as is.
        """
        status, first = await self._get(f"{path}?page=0&limit={limit}{extra}")
        if status != 200 or not isinstance(first, dict):
            return status, first
        content = first.get("content")
        if not isinstance(content, list):
            return status, first
        merged = list(content)
        total_pages = first.get("totalPages")
        if (
            isinstance(total_pages, int)
            and not isinstance(total_pages, bool)
            and total_pages > 1
        ):
            for page in range(max(1, total_pages - (max_pages - 1)), total_pages):
                s, b = await self._get(f"{path}?page={page}&limit={limit}{extra}")
                page_content = b.get("content") if isinstance(b, dict) else None
                if s != 200 or not isinstance(page_content, list):
                    # page number only — `path` carries the VIN.
                    _LOGGER.debug("plug&play history page %s → HTTP %s (stopped)", page, s)
                    break
                merged.extend(page_content)
        body = dict(first)
        body["content"] = merged
        return status, body

    async def _newest_trip_polldata(
        self, vin: str, trip: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Summary of the newest trip's ``polldata`` series, cached per trip id.

        Costs requests only when the newest trip changes (or, for a trip without
        samples, once per ``_POLLDATA_RETRY_S``); a quiet poll costs none.
        """
        trip_id = trip.get("id")
        if not isinstance(trip_id, int) or isinstance(trip_id, bool):
            return None
        now = time.monotonic()
        cached = self._polldata_cache.get(trip_id)
        if cached is not None:
            fetched_at, summary = cached
            if summary is not None or now - fetched_at < _POLLDATA_RETRY_S:
                return summary
        summary = None
        try:
            s, b = await self._get_all_pages(
                f"vehicle/{vin}/driverlogs/{trip_id}/polldata",
                _POLLDATA_PAGE_LIMIT, max_pages=_MAX_POLLDATA_PAGES,
            )
            samples = b.get("content") if isinstance(b, dict) else None
            if s == 200 and isinstance(samples, list):
                summary = _polldata_summary(samples)
            else:
                _LOGGER.debug("plug&play sub-resource polldata → HTTP %s (skipped)", s)
        except Exception as exc:  # noqa: BLE001 — defence-in-depth
            _LOGGER.debug("plug&play sub-resource polldata failed: %s", type(exc).__name__)
        self._polldata_cache = {trip_id: (now, summary)}
        return summary

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
        if status == 401:
            # After _get's refresh+retry, a persistent 401 means the stored token
            # is truly dead. Raise AuthenticationError (not APIError) so the
            # coordinator suppresses the per-poll Error-Reporter flood and fires a
            # single re-auth Repair instead of ~20 buffered 401s (acpp, Prash).
            raise AuthenticationError(
                # mask the VIN — this message is logged/surfaced on the poll path.
                f"plug&play token rejected (401) for vehicle …{vin[-6:]}"
            )
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
            # achievements = the account driver-score ledger. Only fills after the
            # dongle syncs a drive; empty otherwise.
            ("achievements", "user/achievements/v2"),
        ):
            try:
                s, b = await self._get(sub)
                if s == 200:
                    snap[key] = b
                else:
                    # A non-200 here is NOT swallowed silently: _get returns a
                    # status (it doesn't raise), so without this the sub-resource
                    # would just be absent and every derived field come back None
                    # on a live read while mocked tests stay green — exactly how the
                    # multi-value Accept-Language carport 400 hid itself. Log it so a
                    # future live-only regression is visible in debug.
                    # log the friendly resource key, not `sub` (it carries the VIN).
                    _LOGGER.debug(
                        "plug&play sub-resource %s → HTTP %s (skipped)", key, s)
            except Exception as exc:  # noqa: BLE001 — defence-in-depth
                # key (no VIN) + class name (a raw exc's str carries the VIN-URL).
                _LOGGER.debug(
                    "plug&play sub-resource %s failed: %s", key, type(exc).__name__)
        # Paginated history, read across all pages (oldest-first on the wire, see
        # _DRIVERLOG_PAGE_LIMIT): driverlogs = the trip logbook (precise odometer +
        # last-trip stats + EcoScore + start/end GPS); fuellog = refuel history
        # ("von→auf" litres). ``returnPollData=false`` keeps the per-trip time series
        # out of the logbook payload (the app's restore path asks for it embedded).
        for key, path, limit, extra in (
            ("driverlogs", f"vehicle/{vin}/driverlogs", _DRIVERLOG_PAGE_LIMIT,
             "&returnPollData=false"),
            ("fuellog", f"user/fuellog/{vin}", _FUELLOG_PAGE_LIMIT, ""),
        ):
            try:
                s, b = await self._get_all_pages(path, limit, extra)
                if s == 200:
                    snap[key] = b
                else:
                    _LOGGER.debug(
                        "plug&play sub-resource %s → HTTP %s (skipped)", key, s)
            except Exception as exc:  # noqa: BLE001 — defence-in-depth
                _LOGGER.debug(
                    "plug&play sub-resource %s failed: %s", key, type(exc).__name__)
        # Per-trip time series of the newest trip → maxima for the last-trip row.
        newest = _newest_driverlog(snap)
        if newest is not None:
            summary = await self._newest_trip_polldata(vin, newest)
            if summary is not None:
                snap["polldata_summary"] = {"trip_id": newest.get("id"), **summary}
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

        # Licence plate + nickname: user-entered in the app's vehicle details
        # (empty strings until the owner fills them in — live 2026-11-13).
        for src, attr in (("licencePlate", "license_plate"),
                          ("vehicleNickName", "vehicle_nickname")):
            val = veh.get(src)
            if isinstance(val, str) and val.strip() and val.strip().lower() != "null":
                setattr(data, attr, val.strip())

        # Data-as-of timestamp ("Datenstand"): a KWP2000 dongle only refreshes its
        # snapshot when the car is driven, so a reading can be days old. NOT from
        # ``registrationDate`` / ``mainCheck``: the app sends those with the licence
        # plate and nickname in its vehicle-details payload — user-entered first
        # registration and main-inspection dates that merely default to the
        # enrollment time (live 2026-11-13: registrationDate had become a 2008 date,
        # and the sensor showed it). The real stamps are the newest trip's end and
        # the parking fix; set further down, after the logbook is mapped.

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

        # ── Trip logbook (driverlogs) — precise odometer + last-trip stats ──
        # The dongle's driverlog carries a fresher, sub-metre odometer than the
        # coarse/lagging root value, plus the last trip's distance, duration, start
        # odometer and end time. Only present after a synced drive. Reuse the
        # existing BFF trip columns so the same sensors light up — brand clients
        # are mutually exclusive per vehicle, so there's no clobber (#1310).
        trip = _newest_driverlog(snap)
        if trip is not None:
            end_odo = (trip.get("endData") or {}).get("odometer")
            if isinstance(end_odo, (int, float)) and not isinstance(end_odo, bool):
                data.odometer_km = int(round(end_odo))  # precise → overrides root
            start_odo = (trip.get("startData") or {}).get("odometer")
            if isinstance(start_odo, (int, float)) and not isinstance(start_odo, bool):
                data.last_trip_start_odometer_km = int(round(start_odo))
            dist = trip.get("totalTripMileage")
            if isinstance(dist, (int, float)) and not isinstance(dist, bool):
                data.last_trip_distance_km = round(float(dist), 2)
            dur_ms = trip.get("totalTripTime")
            if (
                isinstance(dur_ms, (int, float))
                and not isinstance(dur_ms, bool)
                and dur_ms > 0
            ):
                data.last_trip_duration_min = int(round(dur_ms / 60000))
            end_ts = _epoch_ms_to_datetime(trip.get("endTime"))
            if end_ts is not None:
                data.last_trip_timestamp = end_ts
            # Average speed from the logbook alone (distance over driving time);
            # no polldata needed. Fills the existing BFF column.
            dist_km, drive_ms = _num(dist), _num(dur_ms)
            if dist_km is not None and drive_ms is not None and dist_km > 0 and drive_ms > 0:
                data.last_trip_avg_speed_kmh = round(dist_km / (drive_ms / 3_600_000), 1)
            # avgFuelConsumption is the car's own average-consumption reading at the
            # trip end (app column ``end_average_consumption``, dongle element
            # FuelConsumption.AverageValuePerMileage, l/100 km) — the trip-computer
            # memory, like the BFF short-term figure. The app uploads 0 when it had
            # no reading, so only a positive value counts.
            fuel = _num(trip.get("avgFuelConsumption"))
            if fuel is not None and fuel > 0:
                data.last_trip_avg_fuel_consumption_l_100km = round(fuel, 1)

        # ── Parked-position freshness ──
        # last-parking-position.recordedAt is the TRUE age of the GPS fix. Feed the
        # existing position-age column (has carry-forward TTL machinery).
        parking_raw = (snap.get("last_parking_position") or {}).get("recordedAt")
        parking_ms = _num(parking_raw)
        # raw value into the parser: it reads int(str(val)), which a float rejects
        pos_at = _epoch_ms_to_datetime(parking_raw)
        if pos_at is not None:
            data.position_captured_at = pos_at

        # "Datenstand" = the freshest real stamp: newest trip end or parking fix
        # (see the note above on why not registrationDate / mainCheck). With
        # neither, the age is unknown and the sensor stays empty.
        trip_end_ms = _num(trip.get("endTime")) if trip is not None else None
        stamps = [ms for ms in (trip_end_ms, parking_ms) if ms is not None and ms > 0]
        if stamps:
            captured = _epoch_ms_to_datetime(int(max(stamps)))
            if captured is not None:
                data.data_captured_at = captured

        # ── EcoScore + intake-air + trip count + compact logbook (Priority B/C) ──
        dl = snap.get("driverlogs")
        dl_content = dl.get("content") if isinstance(dl, dict) else None
        # Distinct trips: the server keeps re-uploaded copies of one trip (see
        # _trip_key). Deduplicate whenever every entry was read; past the page cap
        # only the server's own total is known.
        dl_trips = (
            [t for t in dl_content if isinstance(t, dict)]
            if isinstance(dl_content, list) else []
        )
        distinct = len({_trip_key(t, i) for i, t in enumerate(dl_trips)})
        if isinstance(dl, dict):
            total = dl.get("totalElements")
            if isinstance(total, int) and not isinstance(total, bool):
                data.trip_count = distinct if len(dl_trips) >= total else total
            elif isinstance(dl_content, list):
                data.trip_count = distinct
        if trip is not None:
            eco = (trip.get("ecoScore") or {}).get("ecoScore")
            if isinstance(eco, (int, float)) and not isinstance(eco, bool):
                data.last_trip_eco_score = int(round(eco))
            iat = trip.get("averageInductionAirTemperature")
            if isinstance(iat, (int, float)) and not isinstance(iat, bool):
                data.last_trip_intake_air_temp_c = int(round(iat))
        # Priority C — the last few trips (newest first) for the last-trip sensor's
        # attributes: date / distance / duration / EcoScore / end time. One row per
        # logical trip (server-side duplicates collapsed, see _trip_key; the copy
        # kept is the highest-id one, see _trip_order). The newest trip's row also
        # carries the polldata maxima (speed / rpm / coolant) when there are any.
        poll = snap.get("polldata_summary")
        poll = poll if isinstance(poll, dict) else {}
        if dl_trips:
            recent: list[dict[str, Any]] = []
            seen_trips: set[Any] = set()
            newest_first = sorted(
                enumerate(dl_trips),
                key=lambda it: _trip_order(it[1]),
                reverse=True,
            )
            for idx, t in newest_first:
                key = _trip_key(t, idx)
                if key in seen_trips:
                    continue
                seen_trips.add(key)
                if len(recent) >= 10:
                    break
                dur = t.get("totalTripTime")
                row: dict[str, Any] = {
                    "date": t.get("remark"),
                    "distance_km": t.get("totalTripMileage"),
                    "duration_min": (
                        int(round(dur / 60000))
                        if isinstance(dur, (int, float)) and not isinstance(dur, bool)
                        else None
                    ),
                    "eco_score": (t.get("ecoScore") or {}).get("ecoScore"),
                    "ended_at": _epoch_ms_to_datetime(t.get("endTime")),
                }
                if not recent:
                    # newest trip only: the EcoScore breakdown (0-100 per area)
                    # and the negatively rated intervals behind the brake/accel marks.
                    row.update(_eco_detail(t.get("ecoScore")))
                if poll and t.get("id") == poll.get("trip_id"):
                    row.update({k: v for k, v in poll.items() if k != "trip_id"})
                recent.append(row)
            if recent:
                data.recent_trips = recent

        # ── Fuel log — "von→auf" litres + odometer at the fill-up ──
        fl = snap.get("fuellog")
        fl_content = fl.get("content") if isinstance(fl, dict) else None
        if isinstance(fl_content, list) and fl_content:
            newest = max(
                (r for r in fl_content if isinstance(r, dict)),
                key=lambda r: r.get("createdTimestamp") or 0,
                default=None,
            )
            if newest is not None:
                amount = newest.get("amount")
                after = newest.get("postFuelAmount")
                amount_num = (
                    float(amount)
                    if isinstance(amount, (int, float)) and not isinstance(amount, bool)
                    else None
                )
                if amount_num is not None:
                    data.last_refuel_liters_added = round(amount_num, 1)
                if isinstance(after, (int, float)) and not isinstance(after, bool):
                    data.last_refuel_tank_after_l = round(float(after), 1)
                    if amount_num is not None:
                        data.last_refuel_tank_before_l = round(float(after) - amount_num, 1)
                fodo = newest.get("odometer")
                if isinstance(fodo, (int, float)) and not isinstance(fodo, bool):
                    data.last_refuel_odometer_km = int(round(fodo))
                refuel_at = _epoch_ms_to_datetime(newest.get("createdTimestamp"))
                if refuel_at is not None:
                    data.last_refuel_at = refuel_at
                # Price and station only exist when the owner typed them into the
                # app: price 0.0 / empty station otherwise (live 2026-11-13: two of
                # four fill-ups had a price). The currency alone says nothing, so it
                # is set only together with a real price.
                price = _num(newest.get("price"))
                if price is not None and price > 0:
                    data.last_refuel_cost = round(price, 2)
                    cur = newest.get("currency")
                    if isinstance(cur, str) and cur.strip():
                        data.last_refuel_currency = cur.strip().upper()
                station = newest.get("stationName")
                if isinstance(station, str) and station.strip():
                    data.last_refuel_station = station.strip()

        # ── Driver-score points (account-level achievements ledger) ──
        ach = snap.get("achievements")
        ach_content = ach.get("content") if isinstance(ach, dict) else None
        if isinstance(ach_content, list) and ach_content:
            now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000
            total_pts = 0
            seen = False
            for a in ach_content:
                if not isinstance(a, dict):
                    continue
                pts = a.get("points")
                if not isinstance(pts, (int, float)) or isinstance(pts, bool):
                    continue
                exp = a.get("expirationDate") or 0  # 0 = never expires
                if not exp or exp > now_ms:
                    total_pts += int(pts)
                    seen = True
            if seen:
                data.score_points_total = total_pts

        # Factory ("ab Haus") model designation from the carport master-data
        # record — e.g. brandCode "A" + modelDesc "A5" + engType "TDI CR".
        cp = snap.get("carport") or {}
        if isinstance(cp, dict):
            brand_name = _ACPP_BRAND_CODES.get(str(cp.get("brandCode") or "").upper())
            if brand_name:
                data.manufacturer = brand_name
            desc = str(cp.get("modelDesc") or "").strip()
            eng = str(cp.get("engType") or "").strip()
            # body/chassis form from the sales-type code (3rd char), S6 style.
            model_code = str(cp.get("modelCode") or "")
            body = _ACPP_BODY_FORM.get(model_code[2].upper(), "") if len(model_code) >= 3 else ""
            kw: int | None = None
            hp: int | None = None
            for p in (cp.get("power") or []):
                if not (isinstance(p, dict)
                        and isinstance(p.get("value"), (int, float))
                        and not isinstance(p.get("value"), bool)):
                    continue
                unit = str(p.get("unit") or "").lower()
                if unit in ("hp", "ps"):
                    hp = int(round(p["value"]))
                elif unit == "kw":
                    kw = int(round(p["value"]))
            # Model designation in the S6 style — manufacturer + full model text with
            # the body form, NOT the power (that lives in its own sensor): "A5 Coupé TDI".
            model = " ".join(x for x in (desc, body, eng) if x)
            if model:
                data.model = model
            # One consolidated power figure carrying both units, e.g. "176 kW / 239 PS".
            if kw and hp:
                data.engine_power = f"{kw} kW / {hp} PS"
            elif kw:
                data.engine_power = f"{kw} kW"
            elif hp:
                data.engine_power = f"{hp} PS"
            # deliveryDate = the real first-delivery date (epoch-ms string, e.g.
            # 2008 for this A5) — reliable, unlike the /vehicles registrationDate
            # which is just the dongle-enrollment time. Feeds the service calendar.
            reg = _epoch_ms_to_date(cp.get("deliveryDate"))
            if reg:
                data.registration_date = reg
            # bonus master-data
            col = str(cp.get("exteriorColor") or "").strip()
            if col:
                data.exterior_color = col
            icol = str(cp.get("interiorColor") or "").strip()
            if icol:
                data.interior_color = icol
            tq = cp.get("torque")
            if isinstance(tq, (int, float)) and not isinstance(tq, bool):
                data.engine_torque_nm = int(round(tq))
            cyl = cp.get("cylinderCount")
            if isinstance(cyl, int) and not isinstance(cyl, bool):
                data.engine_cylinders = cyl
            # engine displacement — carport "capacity" lists ccm + ccs; take ccm.
            for cap in (cp.get("capacity") or []):
                if (isinstance(cap, dict)
                        and str(cap.get("unit") or "").lower() == "ccm"
                        and isinstance(cap.get("value"), (int, float))
                        and not isinstance(cap.get("value"), bool)):
                    data.engine_displacement_ccm = int(round(cap["value"]))
                    break
            ecode = str(cp.get("engCode") or "").strip()
            if ecode:
                data.engine_code = ecode
            ftype = str(cp.get("fuelType") or "").strip()
            if ftype:
                data.fuel_type = ftype
            trans = str(cp.get("transmissionType") or "").strip()
            tcode = str(cp.get("transmissionCode") or "").strip()
            if trans and tcode:
                data.transmission = f"{trans} (Code: {tcode})"
            elif trans:
                data.transmission = trans
            war = _epoch_ms_to_date(cp.get("warranty"))
            if war:
                data.warranty_until = war
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
