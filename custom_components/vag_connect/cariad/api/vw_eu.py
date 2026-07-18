# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Volkswagen EU API client — emea.bff.cariad.digital."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._mbb import MbbOperationList

from .._util import compute_connection_state, safe_float, safe_int
from ..exceptions import (
    APIError,
    AuthenticationError,
    SpinError,
    VehicleCommandError,
)
from ..models import BRAND_VW_EU, VehicleData
from .base import CariadBaseClient

_LOGGER = logging.getLogger(__name__)

_BASE = "https://emea.bff.cariad.digital"

_SELECTIVE_STATUS_JOBS = ",".join([
    "access",
    # v2.11.0 (cross-brand upstream audit): activeVentilation job was
    # not requested but the parser at _parse_status reads from this
    # block - pre-v2.11.0 the field would have been None for any car
    # whose firmware doesn't ship ventilation data inside another sibling
    # block. audi_services.JOBS2QUERY lists it explicitly.
    "activeVentilation",
    "automation",
    "auxiliaryHeating",
    "batteryChargingCare",
    # v2.11.0: also missing - batterySupport, chargingProfiles,
    # chargingTimers per audi_services.JOBS2QUERY + CC-VW connector jobs.
    "batterySupport",
    "charging",
    "chargingProfiles",
    "chargingTimers",
    "climatisation",
    "climatisationTimers",
    "departureProfiles",
    "departureTimers",
    "fuelStatus",
    # v1.12.0 (#23) — 12V starter battery status. Critical for older
    # vehicles with degrading 12V batteries that cause silent
    # API-no-response weeks before total failure. The CARIAD BFF
    # publishes voltage + warning state here.
    "lvBattery",
    "measurements",
    # v2.7.0b10 — Audi parity fix. Promoted from _v3_probes.py after
    # gap audit vs upstream confirmed both endpoints ship real
    # data on the standard /selectivestatus surface, we just never
    # asked for the job.
    "oilLevel",
    "tyrePressure",
    "readiness",
    "userCapabilities",
    "vehicleLights",
    "vehicleHealthInspection",
    "vehicleHealthWarnings",
])


def _find_flat(node: Any, key: str) -> Any:
    """Return the first value for *key* anywhere in the nested *node*.

    v2.15.1 — several flat BFF wire-keys (``petrolRange``, ``gasRange``,
    ``currentCngLevel_pct``, ``batteryCapacityNetto``, ``oilLevelResult``,
    ``engineStatus``, ``parkingBrakeStatus``, the per-corner ``*TireState`` /
    ``*TireErrorCode``…) are documented on the selectivestatus envelope, but
    the exact container under which a given firmware nests them is live-test
    gated (MED confidence per the 2.15.0 plan). A targeted depth-first scan
    for the exact key name is robust to placement without guessing the path,
    and returns the first non-container value found (matching the leaf-value
    semantics the rest of the parser relies on). Returns None if absent.
    """
    if isinstance(node, dict):
        if key in node and not isinstance(node[key], (dict, list)):
            return node[key]
        for val in node.values():
            found = _find_flat(val, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_flat(item, key)
            if found is not None:
                return found
    return None


class VWEUClient(CariadBaseClient):
    """VW EU / WeConnect client — emea.bff.cariad.digital.

    Also serves as base for AudiClient (same endpoints, extra auth).
    Data paths documented in docs/research/VAG_GROUP_ECOSYSTEM.md.
    """

    def __init__(self, session: Any, email: str, password: str, spin: str = "") -> None:
        super().__init__(session, BRAND_VW_EU, email, password, spin)
        # v2.1.0 (HomeRegion full wire-in) — per-VIN base URL cache.
        # Hydrated by ``get_vehicles`` after garage discovery; consumed
        # by ``_base_for_vin``. Empty dict → ``_base_for_vin`` falls
        # back to the default ``_BASE`` (EU/standard accounts, 99% of
        # users). Non-empty entries override per-VIN for non-EU /
        # imported / region-routed vehicles (closes the long-standing
        # plumbing gap for issue #75 + EXTERNAL_BLOCKED Track 3).
        self._vehicle_bases: dict[str, str] = {}
        # v2.1.0 — eager-init the HomeRegion cache so mypy strict
        # doesn't complain about ``hasattr``/redefine patterns. The
        # cache is shared across ``_resolve_home_regions`` (called by
        # ``get_vehicles``) and ``command_wake``'s MBB fallback.
        from .._home_region import HomeRegionCache  # noqa: PLC0415
        self._home_region_cache: HomeRegionCache = HomeRegionCache()

    def _base_for_vin(self, vin: str) -> str:
        """v2.1.0 — return per-VIN base URL or default ``_BASE``.

        Sync helper because the cache is pre-populated by ``get_vehicles``.
        Pre-v2.1.0 the integration hardcoded ``_BASE`` for every URL,
        which 403'd vehicles imported from non-EU regions or US-spec
        VW EU models. Now: any VIN whose ``mal-1a`` discovery returned
        a non-default ``baseUri.content`` routes through that base
        instead. Cache TTL is 7 days (set in ``HomeRegionCache``).

        Defensive ``getattr`` access — tests that bypass ``__init__``
        via ``VWEUClient.__new__`` won't have ``_vehicle_bases`` set,
        and the fallback to ``_BASE`` is exactly what we want anyway.
        """
        bases: dict[str, str] = getattr(self, "_vehicle_bases", {})
        return bases.get(vin, _BASE)

    async def get_vehicles(self) -> list[str]:
        """Return list of VINs from the CARIAD garage."""
        # v2.14.0 — OPT-IN website-authproxy mode (read-only beta). When the
        # user explicitly chose it, VINs come from the authproxy relations
        # endpoint, not the BFF. Routed first + identically to the EU Data Act
        # portal below; dormant (proxy is None) for every other entry.
        web = getattr(self, "_website_proxy", None)
        if web is not None:
            # v2.15.13 — proactively roll the SSO before it silently lapses
            # (debounced; never raises). Keeps our #1 read-path hedge alive.
            await web.maybe_roll()
            try:
                web_vins: list[str] = await web.list_vehicle_vins()
            except AuthenticationError:
                await web.refresh()
                web_vins = await web.list_vehicle_vins()
            return web_vins

        # v2.12.0 — EU Data Act portal mode: the token-based CARIAD garage
        # is dead for VW EU, so VIN enumeration also has to come from the
        # portal (not just get_status). Without this the coordinator's
        # get_vehicles hits the dead BFF, gets nothing, and the entry ends
        # in setup_retry with "No vehicles found" even though the portal
        # login succeeded (surfaced by swebachus on #388).
        portal = getattr(self, "_eu_portal", None)
        if portal is not None:
            vins: list[str]
            try:
                vins = await portal.list_vehicle_vins()
            except AuthenticationError:
                # v2.13.0 — device-code/QR entries store no password; a 401
                # means the bearer expired → refresh it (re-injects a fresh
                # token into the connector). Legacy cookie entries re-scrape.
                if self._tokens and self._tokens.strategy == "device_grant_portal":
                    await self._refresh_tokens()
                else:
                    await portal.login(self._email, self._password)
                vins = await portal.list_vehicle_vins()
            # Best-effort nickname enrichment from the relation endpoint.
            self._vehicle_metadata: dict[str, dict[str, Any]] = {}
            for pvin in vins:
                nick = await portal.get_relation_nickname(pvin)
                if nick:
                    self._vehicle_metadata[pvin] = {
                        "model": nick, "model_year": None,
                    }
            if not vins:
                _LOGGER.warning(
                    "EU Data Act portal: login OK but the portal returned "
                    "no vehicle. Enable the data-sharing / continuous data "
                    "request for this car on the VW data portal — it can "
                    "take a while to propagate before the car appears."
                )
            return vins

        # v2.15.0 — durable MBB strategy: the token-based CARIAD garage is
        # dead/attestation-gated for VW EU, so enumerate VINs via the legacy
        # MBB usermanagement endpoint with the durable MBB bearer (NOT the BFF,
        # and NOT self._get — that would send the bearer to the dead BFF host).
        if self._tokens and self._tokens.strategy == "mbb":
            return await self._get_vehicles_via_mbb()

        data = await self._get(f"{_BASE}/vehicle/v1/vehicles")
        vehicles: list[dict[str, Any]] = data.get("data", [])

        # Cache nickname/model per VIN — used in _parse_status to set device name
        # CARIAD returns: nickname (user-set in app), model, modelYear
        #
        # Privacy guard: myAudi/CARIAD defaults the vehicle "nickname" to the
        # raw VIN when the owner never renamed the car, so a naive
        # ``nickname or model`` lands the full VIN in ``d.model`` — which then
        # leaks into the public Vehicle Data Scout / Error Reporter issue
        # titles. Drop any candidate that *is* the VIN before it becomes the
        # model. (_reporter_pipeline._safe_model is the hard backstop, but
        # filtering here keeps device names + diagnostics clean too.)
        def _pick_model(v: dict[str, Any], vin: str) -> str | None:
            vin_u = vin.strip().upper()
            for candidate in (
                v.get("nickname"),      # user-set name (e.g. "Golf GTE")
                v.get("vehicleNick"),
                v.get("model"),
                v.get("carModel"),
            ):
                if not isinstance(candidate, str):
                    continue
                trimmed = candidate.strip()
                if trimmed and trimmed.upper() != vin_u:
                    return trimmed
            return None

        self._vehicle_metadata = {
            v["vin"]: {
                "model": _pick_model(v, v["vin"]),
                "model_year": v.get("modelYear") or v.get("model_year"),
            }
            for v in vehicles if v.get("vin")
        }
        # Filter unsupported platforms — prevents repeated 400 errors for legacy/PPC vehicles
        # enrollmentStatus: GDC_MISSING = vehicle not enrolled in digital services
        # devicePlatform: UNKNOWN = platform not supported by CARIAD BFF
        _UNSUPPORTED_ENROLLMENT = {"GDC_MISSING", "UNKNOWN", "NOT_ENROLLED"}
        _UNSUPPORTED_PLATFORM   = {"UNKNOWN"}

        supported: list[dict] = []
        skipped:   list[str]  = []
        for v in vehicles:
            vin = v.get("vin")
            if not vin:
                continue
            enrollment = v.get("enrollmentStatus", "")
            platform   = v.get("devicePlatform", "")
            if enrollment in _UNSUPPORTED_ENROLLMENT or platform in _UNSUPPORTED_PLATFORM:
                skipped.append(f"{vin[-6:]} [{enrollment}/{platform}]")
            else:
                supported.append(v)

        if skipped:
            _LOGGER.info(
                "VAG: skipping %d vehicle(s) with unsupported platform: %s",
                len(skipped), ", ".join(skipped),
            )

        vins = [v["vin"] for v in supported if v.get("vin")]
        if vehicles:
            _LOGGER.debug(
                "VAG vehicles raw fields (first car): %s",
                {k: str(v)[:40] for k, v in vehicles[0].items()
                 if k not in ("vin",)},
            )
        _LOGGER.debug(
            "Found %d vehicle(s): %s",
            len(vins),
            {k: m["model"] for k, m in self._vehicle_metadata.items()},
        )

        # v2.1.0 — HomeRegion full wire-in. Resolve per-VIN base URLs
        # in parallel, populate the cache that ``_base_for_vin`` reads.
        # Each call is best-effort — ``resolve_home_region`` returns
        # ``DEFAULT_BASE`` on any failure so the integration never
        # blocks on an optional discovery hop. Closes EXTERNAL_BLOCKED
        # Track 3 + Issue #75 plumbing.
        await self._resolve_home_regions(vins)

        # Fetch render images via shared base method (best-effort)
        await self.fetch_images()

        return vins

    async def _resolve_home_regions(self, vins: list[str]) -> None:
        """v2.1.0 — populate ``self._vehicle_bases`` from discovery.

        Reuses the existing ``HomeRegionCache`` instance lazily created
        by ``command_wake`` if it ran first; otherwise creates one. The
        7-day cache TTL means subsequent ``get_vehicles`` calls during
        the same HA session are essentially free (one dict lookup per
        VIN). Best-effort everywhere — failure is logged at DEBUG and
        the affected VIN falls through to ``_BASE``.
        """
        from .._home_region import resolve_home_region  # noqa: PLC0415
        import asyncio  # noqa: PLC0415

        async def _one(vin: str) -> tuple[str, str]:
            try:
                base = await resolve_home_region(
                    self, vin, cache=self._home_region_cache,
                )
            except Exception:  # noqa: BLE001
                base = _BASE
            return vin, base

        results = await asyncio.gather(
            *[_one(v) for v in vins],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, BaseException):
                continue
            vin, base = r
            if base != _BASE:
                self._vehicle_bases[vin] = base

    async def get_capabilities(self, vin: str) -> dict[str, Any]:
        """Return CARIAD BFF capabilities document for *vin*.

        Endpoint identical for VW EU + Audi (same backend, different brand
        token). The JSON shape is roughly:
            {"capabilities": [{"id": "honkAndFlash", "status": [...]}, ...]}

        Failure raises ``APIError`` — caller should swallow it because
        capabilities are best-effort metadata, never load-bearing.
        """
        data = await self._get(f"{self._base_for_vin(vin)}/vehicle/v1/vehicles/{vin}/capabilities")
        return data if isinstance(data, dict) else {}

    async def get_trip_statistics(
        self, vin: str, kind: str = "shortTerm"
    ) -> dict[str, Any]:
        """v1.14.0 (#24) — Trip Stats from CARIAD-BFF.

        ``kind`` is ``"shortTerm"`` (per-ignition-cycle trips, "Seit Start")
        or ``"longTerm"`` (since-last-reset aggregates, "Seit Tanken /
        Gesamt"). Both return a list under ``tripDataList.tripData[]`` —
        callers sort by ``overallMileage`` descending and take ``[0]`` as
        the most recent trip (the audi #113 "aggregate-in-state"
        convention).

        Per-trip fields (verified across upstream, upstream,
        davidgiga1993/AudiAPI, ioBroker/vw-connect):
        - ``timestamp`` (ISO 8601 UTC) — trip end time
        - ``mileage`` (km) — distance of this trip
        - ``startMileage`` / ``overallMileage`` (km) — odometer at start/end
        - ``traveltime`` (minutes)
        - ``averageSpeed`` (km/h)
        - ``averageFuelConsumption`` (l/100 km × 10 — divide by 10)
        - ``averageElectricEngineConsumption`` (kWh/100 km × 10)
        - ``averageAuxConsumerConsumption`` (kWh/100 km × 10, often missing)

        Returns the raw response dict so the coordinator can parse + cache.
        Returns an empty dict if the response is not a JSON object (defensive
        against backend edge-cases — best-effort, never raises into the
        polling loop).

        Subscription-required (Audi connect Plus / WeConnect Plus) — if
        the user lacks the entitlement the backend returns 403; the
        capability-filter Phase 3 (#56, v1.13.0) gates this from the
        platform side via ``cap_id_for(brand, "command_trip_stats")``.
        """
        url = f"{self._base_for_vin(vin)}/vehicle/v1/vehicles/{vin}/tripstatistics"
        data = await self._get(url, params={"type": kind})
        return data if isinstance(data, dict) else {}

    async def find_charging_stations(
        self,
        latitude: float,
        longitude: float,
        radius_m: int = 5000,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """v2.0.0 (Big-Bang) — POI lookup for nearby charging stations.

        Returns up to ``max_results`` station dicts within ``radius_m``
        metres of (``latitude``, ``longitude``). Each dict carries the
        raw backend fields (typically: ``id``, ``name``, ``address``,
        ``location``, ``operator``, ``maxPowerInKW``, ``connectorTypes``,
        ``availability``).

        Backed by the Cariad-BFF POI service:
        ``GET /charging-stations/v1/locations``
        (verified live against EU CARIAD-BFF as of 2026-05). The exact
        path varies by client version; we use the POI v1 schema
        documented by upstream/cc-vw
        v0.10.3 (April 2026).

        Defensive: if the backend returns 404 or a non-dict body the
        method returns an empty list so the calling service never
        raises into the polling loop.
        """
        # v2.15.0 — durable MBB tenants have no CARIAD-BFF POI access; never
        # send the MBB bearer to the BFF host. POI lookup is unsupported on
        # MBB, so return an empty list (the documented no-result shape).
        if self._tokens and self._tokens.strategy == "mbb":
            return []
        url = f"{_BASE}/charging-stations/v1/locations"
        params: dict[str, Any] = {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "radiusInMeters": str(int(radius_m)),
            "maxResults": str(int(max_results)),
        }
        try:
            data = await self._get(url, params=params)
        except APIError as exc:
            _LOGGER.debug("find_charging_stations: backend returned %s", exc)
            return []
        if not isinstance(data, dict):
            return []
        # Try the two known list keys (BFF uses ``stations`` in some
        # tenants and ``locations`` in others — both observed live).
        for key in ("stations", "locations", "data"):
            v = data.get(key)
            if isinstance(v, list):
                return v[: int(max_results)]
        return []

    async def get_status(self, vin: str) -> VehicleData:
        """Fetch full vehicle status via selectivestatus."""
        # v2.14.0 — OPT-IN website-authproxy mode (read-only beta). Routed
        # first + identically to the EU Data Act portal below; on a stale
        # cookie session the connector re-establishes it via refresh().
        # Dormant (proxy is None) for every other entry.
        web = getattr(self, "_website_proxy", None)
        if web is not None:
            # v2.15.13 — proactively roll the SSO before it silently lapses
            # (debounced to once per ~10 min; best-effort, never raises).
            await web.maybe_roll()
            try:
                web_data: VehicleData = await web.get_vehicle_data(vin)
            except AuthenticationError:
                await web.refresh()
                web_data = await web.get_vehicle_data(vin)
            return web_data

        # v2.12.0 — EU Data Act portal mode (read-only fallback). When the
        # token-based BFF strategies are exhausted, the auth resolver
        # retains a cookie-based portal connector on ``self._eu_portal``.
        # Route the whole status fetch through it; on a stale cookie
        # session (401/403 surfaced as AuthenticationError) re-login once.
        portal = getattr(self, "_eu_portal", None)
        if portal is not None:
            try:
                data: VehicleData = await portal.get_vehicle_data(vin)
            except AuthenticationError:
                # v2.13.0 — device-code/QR: refresh bearer (no stored password);
                # legacy cookie entries re-scrape via login().
                if self._tokens and self._tokens.strategy == "device_grant_portal":
                    await self._refresh_tokens()
                else:
                    await portal.login(self._email, self._password)
                data = await portal.get_vehicle_data(vin)
            return data

        # v2.15.0 — durable MBB strategy: route the whole status read through
        # the legacy VSR endpoint with the MBB bearer + registered X-Client-Id.
        # Never falls through to the dead BFF for MBB entries.
        if self._tokens and self._tokens.strategy == "mbb":
            return await self._get_status_via_mbb_vsr(vin)

        # v2.1.0 — per-VIN base URL via HomeRegion lookup.
        base = self._base_for_vin(vin)
        url = f"{base}/vehicle/v1/vehicles/{vin}/selectivestatus"
        # v2.8.0 quick win D — vehicle_status job covers the full
        # selectivestatus fetch (parser-health telemetry).
        with self._parser_job("vehicle_status"):
            raw: dict[str, Any] = await self._get(
                url, params={"jobs": _SELECTIVE_STATUS_JOBS},
            )

        # Parking position (separate endpoint)
        parking: dict[str, Any] = {}
        try:
            with self._parser_job("parking_position"):
                parking = await self._get(
                    f"{base}/vehicle/v1/vehicles/{vin}/parkingposition"
                )
        except Exception:  # noqa: BLE001
            pass

        # v2.7.0b11 — Trip statistics (separate endpoint, two query
        # types). Lifetime and last-trip stats live here, NOT in
        # selectivestatus. Best-effort: any failure leaves the trip
        # fields at their dataclass defaults so older firmwares /
        # capability-gated vehicles don't crash the whole poll.
        trip_short: dict[str, Any] = {}
        trip_long: dict[str, Any] = {}
        trip_refuel: dict[str, Any] = {}
        try:
            with self._parser_job("trip_statistics"):
                trip_short = await self._get(
                    f"{base}/vehicle/v1/vehicles/{vin}/tripstatistics",
                    params={"type": "shortTerm"},
                )
                trip_long = await self._get(
                    f"{base}/vehicle/v1/vehicles/{vin}/tripstatistics",
                    params={"type": "longTerm"},
                )
                # v2.10.0 - "cyclic" category = since-refuel / since-recharge
                # aggregator. CARIAD BFF exposes this alongside shortTerm
                # and longTerm at the same endpoint. Pattern observed in
                # volkswagencarnet's TRIP_REFUEL service constant and
                # mirrored here with our own parser. Energy-Dashboard-
                # friendly: total-consumption-per-tank/charge is a missing
                # building block in the HA VAG ecosystem today.
                try:
                    trip_refuel = await self._get(
                        f"{base}/vehicle/v1/vehicles/{vin}/tripstatistics",
                        params={"type": "cyclic"},
                    )
                except Exception:  # noqa: BLE001
                    # cyclic is a newer firmware capability; some pre-2024
                    # vehicles 404 it. Treat as soft-fail to keep the rest
                    # of the parse working unchanged.
                    pass
        except Exception:  # noqa: BLE001
            pass

        d = self._parse_status(vin, raw, parking)
        self._parse_trip_statistics(d, trip_short, trip_long)
        # v2.10.0 - refuel-trip parse. Separate method to keep the
        # shortTerm + longTerm parser untouched and ship a focused diff.
        self._parse_refuel_trip(d, trip_refuel)

        # v1.25.0 PR-G — MBB VSR Phase 2 read-side fallback (Golf 7 GTE
        # Tank-Level use case). Triggers when:
        #   1. Cariad-BFF returned no fuel_level (older PHEV firmware
        #      ships ``fuelStatus.rangeStatus = {error}`` with no
        #      ``currentFuelLevel_pct``)
        #   2. AND the VIN is known-MBB-backed via MBBBackendCache
        #      (was set by a previous wrapper-404 wake fallback in
        #      v1.21.0 Phase 1)
        # Then we GET the legacy MBB ``/fs-car/bs/vsr/v1/.../status``
        # endpoint and parse field IDs ``0x030103000A`` (tank %) +
        # ``0x0301030005`` (total range km). Defensive: any failure
        # leaves ``d.fuel_level`` at None — entity stays unknown.
        if d.fuel_level is None:
            try:
                await self._maybe_fill_from_mbb_vsr(vin, d)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "MBB VSR fallback failed for %s — leaving fuel_level None: %s",
                    vin[-6:], type(err).__name__,
                )

        # v1.9.0 — Vehicle Data Scout opt-in. Endpoint names match
        # ``EXPECTED_KEYS["volkswagen"]`` (Audi inherits the table via
        # AudiClient(VWEUClient) — same backend, same shape).
        self.last_raw_responses = {}
        if isinstance(raw, dict):
            self.last_raw_responses["selectivestatus"] = raw
        if isinstance(parking, dict):
            self.last_raw_responses["parkingposition"] = parking

        # ── carCapturedTimestamp → connection_state (v1.8.12 Multi-Brand) ────
        # CARIAD-BFF returns ``carCapturedTimestamp`` on the .value of every
        # status sub-object — confirmed live in
        # `upstream/volkswagencarnet` issue #921 (ID.4 2025 dump):
        #   access.accessStatus.value.carCapturedTimestamp
        #   charging.chargingStatus.value.carCapturedTimestamp
        #   charging.batteryStatus.value.carCapturedTimestamp
        #   climatisation.climatisationStatus.value.carCapturedTimestamp
        #   measurements.{range,odometer,fuelLevel}Status.value.carCapturedTimestamp
        #   parkingposition.carCapturedTimestamp (separate endpoint)
        # The recursive walk in compute_connection_state() handles the
        # nested .value.carCapturedTimestamp paths without per-brand
        # configuration. AudiClient inherits this since it uses the same
        # selectivestatus endpoint via VWEUClient.
        d.connection_state, d.last_seen_at = compute_connection_state(raw, parking)

        return d

    def _mbb_command_target(self) -> "VWEUClient | None":
        """b12 — which connector runs MBB commands. On an MBB-PRIMARY entry
        that's ``self`` (behaviour unchanged). On a read-only primary (EU Data
        Act portal) with an armed MBB command channel it's that second
        connector. None → no MBB path (falls through to the BFF, as before)."""
        if self._tokens and self._tokens.strategy == "mbb":
            return self
        return getattr(self, "_mbb_command", None)

    async def arm_mbb_command_channel(
        self, tokens: Any, client_id: str, vins: list[str], spin: str = "",
    ) -> bool:
        """b12 — arm a durable-MBB command connector ALONGSIDE this (read-only
        primary) client: commands route through MBB while reads stay on the
        primary. Builds a second VWEUClient on the shared session (MBB = bearer,
        no IDP-cookie clobber). Fail-soft → False leaves the slot None and the
        primary unaffected. Skipped if THIS client is already MBB-primary."""
        if not tokens or not getattr(tokens, "access_token", ""):
            return False
        if self._tokens and self._tokens.strategy == "mbb":
            return False
        try:
            cmd = VWEUClient(
                self._session, self._email, self._password, spin or self._spin,
            )
            # v2.17.1 (#666) — inherit the PRIMARY's brand so the MBB URL
            # {Brand}/{country} segment is correct for Audi Car-Net as well as
            # VW (the legacy fs-car bs/* catalog was extracted from the Audi
            # DEX; both share the mbboauth/mal-1a hosts). VW→VW is a no-op.
            cmd._brand = self._brand
            cmd.set_persisted_tokens(tokens)
            cmd._mbb_client_id = client_id or ""
            cmd._mbb_manual_vins = list(vins or [])
            self._mbb_command = cmd
            _LOGGER.info(
                "VAG Connect: MBB command channel armed alongside the"
                " read-only primary (commands → MBB, reads → primary)."
            )
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "VAG Connect: could not arm MBB command channel (%s) —"
                " primary unaffected.", type(err).__name__,
            )
            self._mbb_command = None
            return False

    async def command_lock(self, vin: str, spin: str = "") -> None:
        """Lock vehicle — combined endpoint with separate-endpoint fallback,
        each tried on both /vehicle/v1/ and /vehicle/v2/ paths.

        v1.8.8 (Session 3B): HTTP-404-only fallback via
        ``_post_command_with_fallback_paths``. Auth failures, rate limits
        and 5xx errors propagate so ``classify_command_failure`` handles them.

        v1.9.1 (#92, Audi S6 C8 2021): the CARIAD BFF returns
        ``403 spin_error`` for **lock too** on premium Audi models when no
        S-PIN is sent (same behaviour the unlock path had). The S-PIN, when
        configured, is now included in the lock-unlock payload exactly the
        same way as ``command_unlock``. When the user has no S-PIN
        configured the call still proceeds and may legitimately succeed
        on older / non-premium models that don't enforce the S-PIN
        requirement on lock.
        """
        # v2.15.0 — durable MBB strategy uses the classic Car-Net RLU flow
        # (3-leg S-PIN secure-token handshake + lock action), NOT the BFF.
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_rlu_mbb(vin, spin=spin, lock=True)
            return
        primary_payload: dict[str, Any] = {"action": "lock"}
        fallback_payload: dict[str, Any] = {}
        if spin or self._spin:
            primary_payload["spin"] = spin or self._spin
            fallback_payload["spin"] = spin or self._spin
        await self._post_command_with_fallback_paths(
            vin,
            primary_suffix="access/lock-unlock",
            primary_payload=primary_payload,
            fallback_suffix="access/lock",
            fallback_payload=fallback_payload,
        )

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        """Unlock vehicle — S-PIN required if set.

        Same v1/v2 + combined/separate dispatch as ``command_lock``.
        S-PIN, when present, is included in *both* the combined-endpoint
        payload and the separate-endpoint fallback payload (the legacy
        unlock endpoint accepts the PIN in the body, the same way the
        SecToken-using SEAT/CUPRA flow does in v1.8.4).
        """
        # v2.15.0 — durable MBB strategy uses the classic Car-Net RLU flow.
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_rlu_mbb(vin, spin=spin, lock=False)
            return
        primary_payload: dict[str, Any] = {"action": "unlock"}
        fallback_payload: dict[str, Any] = {}
        if spin or self._spin:
            primary_payload["spin"] = spin or self._spin
            fallback_payload["spin"] = spin or self._spin
        await self._post_command_with_fallback_paths(
            vin,
            primary_suffix="access/lock-unlock",
            primary_payload=primary_payload,
            fallback_suffix="access/unlock",
            fallback_payload=fallback_payload,
        )

    async def command_start_climate(
        self, vin: str, ppe_mode: bool = False
    ) -> None:
        """Start pre-conditioning — combined endpoint with separate fallback,
        each on v1/v2.

        Default target temperature 21°C and window heating enabled match
        the previous separate-endpoint payload — kept so behaviour does
        not regress when the combined endpoint isn't available.

        v1.14.0 (#29, audi #644 + #677) — when ``ppe_mode=True`` the
        fallback body uses the PPE/PPC shape:
        - ``climatisationMode: "comfort"`` (mandatory, NOT null)
        - ``targetTemperature`` + ``targetTemperatureUnit`` OMITTED
        Required for Q6 e-tron, A6 e-tron, RS e-tron GT Facelift, A3 2024+
        PHEV — all of which return ``400 Bad Request`` for the legacy
        body shape. Coordinator gates this via ``CONF_FORCE_PPE_CLIMATE``
        option (Audi-only, user-overridable since auto-detection is
        unreliable). ️ [Inference] — body shape verified from upstream
        PRs but Audi never published a definitive PPE compatibility list.
        """
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_mbb_op(vin, "climate_start")
            return
        if ppe_mode:
            fallback_payload = {
                "climatisationMode": "comfort",
                "climatisationWithoutExternalPower": True,
                "windowHeatingEnabled": True,
                # NOTE: targetTemperature* OMITTED for PPE — body validator
                # rejects it on Q6/A6 e-tron / PPC vehicles.
            }
        else:
            fallback_payload = {
                "targetTemperature": 21.0,
                "targetTemperatureUnit": "celsius",
                "climatisationWithoutExternalPower": True,
                "windowHeatingEnabled": True,
            }
        await self._post_command_with_fallback_paths(
            vin,
            primary_suffix="climatisation/start-stop",
            primary_payload={"action": "start"},
            fallback_suffix="climatisation/start",
            fallback_payload=fallback_payload,
        )

    async def command_start_climate_control(
        self,
        vin: str,
        *,
        temp_c: float | None = None,
        glass_heating: bool | None = None,
        seat_fl: bool | None = None,
        seat_fr: bool | None = None,
        seat_rl: bool | None = None,
        seat_rr: bool | None = None,
        climatisation_at_unlock: bool | None = None,
        climatisation_mode: str | None = None,
    ) -> None:
        """v2.10.0 - rich climate-start payload for CARIAD BFF.

        Body keys + types match the cariad-bff /climatisation/start
        endpoint contract: each is optional, the backend keeps the
        existing setting for any omitted field. Posts directly to the
        separate-endpoint path (not the combined start-stop endpoint)
        because the combined endpoint only accepts ``{"action": "start"}``
        without per-seat / mode extensions.

        For seat heating: if any of the four seat flags is supplied,
        all four zone flags are emitted (defaulting unspecified seats
        to ``False``). Mixed per-seat + None inputs are treated as
        ``False`` for the unspecified seats so the user always sends
        a coherent zone configuration to the backend.
        """
        body: dict[str, Any] = {}
        if temp_c is not None:
            body["targetTemperatureInCelsius"] = float(temp_c)
        if glass_heating is not None:
            body["windowHeatingEnabled"] = bool(glass_heating)
        if any(s is not None for s in (seat_fl, seat_fr, seat_rl, seat_rr)):
            body["zoneFrontLeftEnabled"] = (
                bool(seat_fl) if seat_fl is not None else False
            )
            body["zoneFrontRightEnabled"] = (
                bool(seat_fr) if seat_fr is not None else False
            )
            body["zoneRearLeftEnabled"] = (
                bool(seat_rl) if seat_rl is not None else False
            )
            body["zoneRearRightEnabled"] = (
                bool(seat_rr) if seat_rr is not None else False
            )
        if climatisation_at_unlock is not None:
            body["climatisationAtUnlock"] = bool(climatisation_at_unlock)
        if climatisation_mode is not None:
            body["climatisationMode"] = str(climatisation_mode)
        url = f"{self._base_for_vin(vin)}/vehicle/v1/vehicles/{vin}/climatisation/start"
        await self._post(url, json=body)

    async def command_stop_climate(self, vin: str) -> None:
        """Stop pre-conditioning — combined endpoint with separate fallback."""
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_mbb_op(vin, "climate_stop")
            return
        await self._post_command_with_fallback_paths(
            vin,
            primary_suffix="climatisation/start-stop",
            primary_payload={"action": "stop"},
            fallback_suffix="climatisation/stop",
            fallback_payload={},
        )

    async def command_start_charging(self, vin: str) -> None:
        """Start charging — combined endpoint with separate fallback."""
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_mbb_op(vin, "charge_start")
            return
        await self._post_command_with_fallback_paths(
            vin,
            primary_suffix="charging/start-stop",
            primary_payload={"action": "start"},
            fallback_suffix="charging/start",
            fallback_payload={},
        )

    async def command_stop_charging(self, vin: str) -> None:
        """Stop charging — combined endpoint with separate fallback."""
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_mbb_op(vin, "charge_stop")
            return
        await self._post_command_with_fallback_paths(
            vin,
            primary_suffix="charging/start-stop",
            primary_payload={"action": "stop"},
            fallback_suffix="charging/stop",
            fallback_payload={},
        )

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        """Flash the lights — CARIAD-BFF ``honkandflash`` endpoint.

        v2.15.5 — corrected from the invented ``vehicleLights/flash`` +
        ``{"action":"flash"}`` shape (which the BFF rejected with a flat
        ``400 Bad Request``) to the real We Connect EU contract, grounded
        in the decompiled We Connect EU app:

        - **Path**: ``/vehicle/v1/vehicles/{vin}/honkandflash`` (literal in
          classes3.dex; routed via ``_post_command`` so it inherits the
          v1→v2 404 fallback every other command uses).
        - **Body**: a ``HonkAndFlashRequest`` whose ctor signature in the
          DEX is ``(int duration, String mode, UserPosition userPosition)``
          → JSON keys ``duration`` / ``mode`` / ``userPosition`` (the last
          nesting ``latitude`` / ``longitude``).
        - **Mode**: the CARIAD ``HonkAndFlashParameters$Mode`` enum has
          exactly two members — ``HONK_AND_FLASH`` and ``FLASH_ONLY``.
          We flash only, so ``mode = "FLASH_ONLY"``.
        - **duration**: integer seconds; the app exposes a
          ``HonkAndFlashDuration`` config — 10 s is a safe default.

        The app's ``HonkAndFlashViewModel`` gates the command on a known
        position (it shows ``location_disabled_alert`` and blocks the call
        without a fix), so the BFF very likely requires ``userPosition``.

        Resilient strategy (mirrors SEAT/CUPRA ``command_flash``): send the
        bare ``mode``/``duration`` body first — some firmwares accept it and
        this unblocks users whose vehicle has never reported GPS — and only
        if the backend answers ``400`` do we retry with ``userPosition``
        built from the caller-supplied coordinates. If the bare body 400s
        and no coordinates are available, raise an actionable ``APIError``.

        ️ Live-test gate: ``userPosition``/``latitude``/``longitude`` keys
        and the location-gating UI behaviour are confirmed statically, but
        whether the BFF *hard-rejects* a flash with ``userPosition`` omitted
        (vs. only the honk variant) is the one detail not provable from the
        static strings. The bare-body-then-position retry covers both cases.
        """
        # v2.17.3 — MBB gate (the footgun this fixes): command_flash was the
        # ONE write command missing the ``_mbb_command_target()`` guard that
        # command_lock/unlock/wake/start_climate all have. On a legacy Car-Net
        # (MBB) car the read-only primary bearer was POSTed to the CARIAD BFF
        # honkandflash endpoint, which answered ``400 {"info":"missing or
        # invalid auth header"}`` — and the retry branch below then masked it
        # as a bogus "requires userPosition / no GPS" message. There is no MBB
        # remote-honk-flash service wired, so surface an honest, actionable
        # error instead of leaking the bearer to the dead BFF host.
        if self._mbb_command_target() is not None:
            raise VehicleCommandError(
                "flash",
                "Honk & Flash isn't available on the MBB command channel — it "
                "needs the CARIAD BFF, which legacy Car-Net (MBB) cars don't "
                "have. Lock, unlock, climate and charge commands still work "
                "over MBB.",
            )
        body: dict[str, Any] = {"mode": "FLASH_ONLY", "duration": 10}
        try:
            await self._post_command(vin, "honkandflash", json=body)
            return
        except APIError as exc:
            if exc.status != 400:
                raise
            # 400 → most likely the BFF wants a bounding ``userPosition``.
            # Retry with coordinates if we have them; otherwise surface an
            # actionable hint instead of an opaque "API error 400".
            if latitude is None or longitude is None:
                raise APIError(
                    400,
                    f"{self._base_for_vin(vin)}"
                    f"/vehicle/v1/vehicles/{vin}/honkandflash",
                    "honk-and-flash rejected the bare body (the BFF likely "
                    "requires userPosition) AND no GPS position is available "
                    "for this vehicle. Wake the car / wait for a status poll "
                    "so a parking position is reported, then retry. If GPS "
                    "stays empty, check whether privacy-mode is enabled in "
                    "the head-unit settings.",
                ) from exc
            body["userPosition"] = {
                # Truncate to ~11 m precision, matching the SEAT path.
                "latitude": int(latitude * 10000) / 10000,
                "longitude": int(longitude * 10000) / 10000,
            }
            await self._post_command(vin, "honkandflash", json=body)

    async def command_wake(self, vin: str) -> None:
        """Wake vehicle — Cariad-BFF first, MBB legacy fallback.

        v1.9.1 (#92, Audi S6 C8 2021): premium Audi models return ``404``
        on the legacy ``/vehicle/v1/vehicles/{vin}/vehicleWakeup`` path.
        Same v1 → v2 dispatch we use for every other command — the
        ``_post_command`` helper auto-falls-back to ``/vehicle/v2/...``
        on a 404 and remembers the result per VIN so subsequent calls
        skip the dead path.

        v1.21.0 (Audi A4 B9 / Q5 2021 / VW Golf 7 user-report
        2026-05-07): older MIB3 cars (pre-PPE/MEB) reject Cariad-BFF
        completely — both v1 and v2 return Cariad-wrapper-404 with
        body marker ``"Upstream service responded"`` + ``retry:true``.
        These vehicles speak the **legacy MBB stack** instead.

        New strategy:
        1. Check ``MBBBackendCache`` — if VIN previously detected as
           MBB-backed, skip Cariad-BFF entirely + go straight to MBB
        2. Otherwise: try Cariad-BFF (v1+v2 fallback as before)
        3. If Cariad returns wrapper-404 → mark VIN as MBB-backed,
           resolve homeRegion, retry on MBB
        4. Cache the backend choice for 7 days

        See ``cariad/_mbb.py`` for backend-detection logic and
        ``cariad/_home_region.py`` for per-VIN read-base resolution.
        """
        from .._mbb import (  # noqa: PLC0415
            MBBBackendCache,
            is_cariad_wrapper_404,
        )

        # v2.15.0 — durable MBB strategy: never touch the CARIAD BFF. Go
        # straight to the MBB wake (which uses the MBB-headered poster), so
        # the bearer never leaks to the dead BFF host. Mirrors the gates on
        # get_status / command_lock / command_unlock.
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_wake_mbb(vin)
            return

        # v2.1.0 — ``_home_region_cache`` is now eager-init in __init__
        # (mypy strict). MBBBackendCache stays lazy because it's only
        # touched after the first wrapper-404 detection.
        if not hasattr(self, "_mbb_backend_cache"):
            self._mbb_backend_cache: MBBBackendCache = MBBBackendCache()

        # Step 1: cached backend?
        cached_backend = self._mbb_backend_cache.get(vin)

        if cached_backend == "mbb":
            # Skip Cariad entirely — go straight to MBB
            await self._command_wake_mbb(vin)
            return

        # Step 2: try Cariad-BFF (existing v1→v2 fallback)
        try:
            await self._post_command(vin, "vehicleWakeup", json={})
            # Success — mark VIN as Cariad-backed if not already
            if cached_backend != "cariad":
                self._mbb_backend_cache.set(vin, "cariad")
            return
        except APIError as err:
            # APIError's message includes body[:200] — use str(err)
            # for marker detection (no separate .body attribute).
            body = str(err)
            if not is_cariad_wrapper_404(body):
                # Real failure — propagate (could be auth, real
                # missing endpoint, etc.)
                raise
            _LOGGER.info(
                "VAG wake: Cariad-wrapper-404 for vin ***%s — "
                "marking as MBB-backed and retrying via legacy path",
                vin[-6:],
            )

        # Step 3: detected MBB — cache the flag and retry
        self._mbb_backend_cache.set(vin, "mbb")
        await self._command_wake_mbb(vin)

    async def _command_wake_mbb(self, vin: str) -> None:
        """v1.21.0 — Wake via MBB legacy stack.

        Resolves per-VIN homeRegion (cached 7d), then POSTs to
        ``{readBase}/fs-car/bs/vsr/v1/{Brand}/{country}/vehicles/{vin}/requests``.
        """
        from .._mbb import build_mbb_wake_url, MBB_DEFAULT_READ_BASE  # noqa: PLC0415
        from .._home_region import resolve_home_region  # noqa: PLC0415

        # Resolve home region — defaults to MBB read-base if discovery fails
        try:
            read_base = await resolve_home_region(
                self, vin, cache=self._home_region_cache,
            )
        except Exception:  # noqa: BLE001
            read_base = MBB_DEFAULT_READ_BASE
        # If discovery returned the Cariad default, MBB needs the actual
        # read base — fall back to msg.volkswagen.de (most common).
        if "cariad.digital" in read_base or "bff.cariad" in read_base:
            read_base = MBB_DEFAULT_READ_BASE

        # Brand segment: Audi/VW. Country: for the durable MBB strategy use
        # the account's own country from the id_token (CH/DE/AT…); the legacy
        # IDK wrapper-404 path keeps the DE default.
        brand_name = self._brand.name  # 'volkswagen' or 'audi'
        if self._tokens and self._tokens.strategy == "mbb":
            country = self._mbb_country_from_id_token() or "DE"
        else:
            country = "DE"
        url = build_mbb_wake_url(read_base, brand_name, country, vin)
        _LOGGER.debug(
            "MBB wake POST → %s (vin ***%s)",
            url.replace(vin, f"***{vin[-6:]}"),
            vin[-6:],
        )
        # v2.15.0 — for the durable MBB strategy the wake must carry the
        # registered X-Client-Id / X-MbbUserId headers (the MBB backend 403s
        # without them), so use the dedicated MBB poster. The legacy IDK-token
        # wrapper-404 fallback path (non-mbb entries on older MIB3 cars) keeps
        # its original ``self._post`` behaviour.
        if self._tokens and self._tokens.strategy == "mbb":
            try:
                await self._mbb_post_json(url, {})
            except APIError as exc:
                # v2.17.3 — the durable-MBB grant carries commands (RLU /
                # climate / charge via SecToken) but NOT the VSR data-refresh
                # plane: the VSR ``requests`` POST 403s with
                # ``VSR.security.9007 / systemId 'XID_APP_VW'``. That's a
                # structural scope gap for this token, not a transient error and
                # not a subscription lapse — surface it honestly instead of a
                # raw 403 traceback that reads as "unexpected exception".
                b = (exc.body or "").lower()
                if exc.status == 403 and (
                    "xid_app_vw" in b or "security.9007" in b
                ):
                    raise VehicleCommandError(
                        "wake",
                        "Remote wake isn't permitted for this car's MBB grant — "
                        "VW's status-refresh plane (VSR) is closed to this "
                        "token. The car still updates on its normal poll / push "
                        "cycle.",
                    ) from exc
                raise
        else:
            await self._post(url, json={})

    async def _maybe_fill_from_mbb_vsr(self, vin: str, d: VehicleData) -> None:
        """v1.25.0 PR-G — MBB VSR Phase 2 read-side fallback.

        When Cariad-BFF returns no ``fuel_level`` (Golf 7 GTE / older
        PHEV firmware ships ``fuelStatus.rangeStatus = {error}``), the
        underlying MBB OCU still publishes the field via the legacy
        VSR ``/fs-car/bs/vsr/v1/.../status`` endpoint. This is the
        read-side complement to v1.21.0's wake-side MBB fallback.

        Only fires when:
          1. ``d.fuel_level is None`` (Cariad gave us nothing)
          2. AND VIN is known-MBB-backed (set by previous wrapper-404
             event in MBBBackendCache; new VINs must hit a wake first
             to be classified)

        Defensive: any HTTP failure / empty response leaves
        ``d.fuel_level`` at None — entity stays "unknown".

        References:
          - upstream audi_models.py legacy IDS table for the
            field-IDs ``0x030103000A`` (tank %) + ``0x0301030005``
            (total range km)
          - upstream/weconnect-python — same field-IDs
            confirmed for VW EU MBB stack
        """
        from .._mbb import (  # noqa: PLC0415
            MBBBackendCache,
            MBB_DEFAULT_READ_BASE,
            MBB_VSR_FIELD_TANK_PCT,
            MBB_VSR_FIELD_TOTAL_RANGE_KM,
            build_mbb_vsr_status_url,
            parse_mbb_vsr_field,
        )
        from .._home_region import resolve_home_region  # noqa: PLC0415
        from .._util import safe_int  # noqa: PLC0415

        # v2.1.0 — ``_home_region_cache`` is now eager-init in __init__
        # (mypy strict). MBBBackendCache stays lazy.
        if not hasattr(self, "_mbb_backend_cache"):
            self._mbb_backend_cache = MBBBackendCache()

        # Only proceed if we KNOW the VIN is MBB-backed. Don't speculatively
        # probe MBB on every Cariad-BFF poll — too noisy for non-Golf 7
        # vehicles. The first wrapper-404 wake will set the flag.
        if self._mbb_backend_cache.get(vin) != "mbb":
            return

        # Resolve homeRegion-derived read base
        try:
            read_base = await resolve_home_region(
                self, vin, cache=self._home_region_cache,
            )
        except Exception:  # noqa: BLE001
            read_base = MBB_DEFAULT_READ_BASE
        if "cariad.digital" in read_base or "bff.cariad" in read_base:
            read_base = MBB_DEFAULT_READ_BASE

        url = build_mbb_vsr_status_url(read_base, self._brand.name, "DE", vin)
        _LOGGER.debug(
            "MBB VSR GET → %s (vin ***%s) — Phase 2 fallback for fuel_level",
            url.replace(vin, f"***{vin[-6:]}"), vin[-6:],
        )

        try:
            response = await self._get(url)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "MBB VSR fetch failed for ***%s: %s — leaving fuel_level None",
                vin[-6:], type(err).__name__,
            )
            return

        # Tank %
        tank_raw = parse_mbb_vsr_field(response, MBB_VSR_FIELD_TANK_PCT)
        tank_pct = safe_int(tank_raw)
        if tank_pct is not None:
            d.fuel_level = tank_pct
            _LOGGER.info(
                "MBB VSR Phase 2: filled fuel_level=%d%% for ***%s "
                "(Cariad-BFF was empty)", tank_pct, vin[-6:],
            )
        # Total range km — only fill if Cariad didn't already give us one
        if d.combustion_range_km is None:
            range_raw = parse_mbb_vsr_field(response, MBB_VSR_FIELD_TOTAL_RANGE_KM)
            range_km = safe_int(range_raw)
            if range_km is not None:
                d.combustion_range_km = range_km
                _LOGGER.info(
                    "MBB VSR Phase 2: filled combustion_range_km=%d for ***%s",
                    range_km, vin[-6:],
                )

    # ── v2.15.0 — durable MBB strategy: auth-isolated HTTP + read + RLU ─────
    #
    # All MBB requests carry the MBB bearer (``self._access_token`` for an
    # ``mbb`` entry) + the registered ``X-Client-Id`` (``self._mbb_client_id``)
    # via these DEDICATED getters/posters — never ``self._get``/``self._post``,
    # which would send the MBB bearer to the dead CARIAD BFF host. This keeps
    # the blast radius of the MBB strategy to exactly these methods.

    def _mbb_user_id(self) -> str:
        """Return the ``sub`` claim of the id_token (X-MbbUserId), or ''.

        Decodes only the public JWT payload — never the signature, never
        logged. Some MBB endpoints 403 without this header even when the
        security token is valid.
        """
        tok = self._tokens.id_token if self._tokens else ""
        if not tok:
            return ""
        try:
            payload = tok.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except (ValueError, IndexError, json.JSONDecodeError):
            return ""
        sub = claims.get("sub")
        return sub if isinstance(sub, str) else ""

    def _mbb_country_from_id_token(self) -> str | None:
        """Best-effort ISO-2 country for the MBB market segment.

        The fs-car path carries a ``{country}`` market segment (DE/CH/AT…).
        Most VW id_tokens carry a ``locale`` (e.g. ``de-CH``) or an explicit
        ``country`` claim; we read the region from there. Returns None when
        nothing usable is present (caller falls back to a candidate list).
        """
        tok = self._tokens.id_token if self._tokens else ""
        if not tok:
            return None
        try:
            payload = tok.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except (ValueError, IndexError, json.JSONDecodeError):
            return None
        for key in ("country", "countryCode", "market"):
            val = claims.get(key)
            if isinstance(val, str) and len(val) == 2:
                return val.upper()
        locale = claims.get("locale")
        if isinstance(locale, str) and "-" in locale:
            region = locale.split("-")[-1]
            if len(region) == 2:
                return region.upper()
        return None

    def _mbb_app_identity(self) -> tuple[str, str]:
        """``(X-App-Name, X-App-Version)`` for the active brand.

        The fs-car / usermanagement endpoints gate on the app-identification
        headers (grounded in the We Connect / myAudi app + the Bruno legacy
        fixtures). Audi uses ``myAudi``; everything else the VW We Connect id.
        """
        if self._brand.name == "audi":
            return "myAudi", "5.5.1"  # b13 (RE) — live myAudi build (was 4.24.0)
        # b13 (#503 dismantle / H5) — bumped to the live We Connect version.
        # Verified against the dismantled com.volkswagen.weconnect APK
        # (versionName 3.63.2, androguard 2026-06). A fidelity check on the
        # fs-car endpoints rejects stale versions, so tracking the current
        # build hardens the command path; this is the value the App-Atlas
        # refresh unblocked.
        return "Volkswagen", "3.63.2"

    def _mbb_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        app_name, app_version = self._mbb_app_identity()
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "X-Client-Id": self._mbb_client_id,
            "Accept": "application/json",
            # The MBB fs-car endpoints reject calls without the app-identity
            # headers (usermanagement / rolesrights are picky); send them on
            # every MBB request so reads, enumeration and commands all carry
            # them. Grounded in the We Connect app + the mbb_legacy fixtures.
            "X-App-Name": app_name,
            "X-App-Version": app_version,
            "User-Agent": "okhttp/3.14.9",
        }
        uid = self._mbb_user_id()
        if uid:
            headers["X-MbbUserId"] = uid
        if extra:
            headers.update(extra)
        return headers

    async def _mbb_ensure_fresh(self, *, for_command: bool = False) -> None:
        """b11 — PROACTIVELY refresh the durable MBB bearer before it expires.

        The key MBB reads (operationList, VSR) run with ``_retry=False`` so a
        data-plane ACL 401 can't trigger a refresh storm — which means the
        reactive 401→refresh path is disabled for them. So the ONLY thing that
        keeps the bearer alive is this pre-flight check: when the token is within
        the 60s expiry skew, refresh it now via the durable MBB branch. (The
        operationList comment used to assume a "scheduled refresh" that never
        existed — this is it.) No-op for non-MBB strategies and fresh tokens.

        v2.15.12 (#584): ``for_command`` bills the refresh against the command
        storm budget so a command can't drain the data-plane's.
        """
        tok = self._tokens
        if tok and tok.strategy == "mbb" and tok.needs_refresh():
            await self._refresh_tokens(for_command=for_command)

    async def _mbb_get(
        self, url: str, *, _retry: bool = True, for_command: bool = False
    ) -> dict[str, Any]:
        """GET an MBB endpoint with the MBB bearer + registered X-Client-Id.

        Pre-flight refreshes the bearer if it's expiring (``_mbb_ensure_fresh``).
        On a 401 (expired MBB bearer) refresh ONCE via the durable MBB refresh
        branch and retry. These requests bypass ``base._request`` (the usual
        401→refresh trigger). The storm guard in ``_refresh_tokens`` bounds
        retries; ``_retry=False`` on the second attempt prevents recursion.

        v2.15.12 (#584): ``for_command`` routes any triggered refresh to the
        command storm budget (used by the command legs that GET via MBB).
        """
        await self._mbb_ensure_fresh(for_command=for_command)
        async with self._session.get(url, headers=self._mbb_headers()) as resp:
            text = await resp.text()
            if resp.status == 401 and _retry:
                await self._refresh_tokens(for_command=for_command)
                return await self._mbb_get(
                    url, _retry=False, for_command=for_command
                )
            if resp.status >= 400:
                raise APIError(resp.status, url, body=text)
            if not text:
                return {}
            try:
                loaded = json.loads(text)
            except ValueError:
                return {}
            return loaded if isinstance(loaded, dict) else {}

    async def _mbb_post_json(
        self, url: str, body: dict[str, Any], *, _retry: bool = True,
        for_command: bool = False,
    ) -> dict[str, Any]:
        """POST a JSON body to an MBB endpoint (leg-2 SPIN completion).

        Refreshes once on a 401 and retries (see ``_mbb_get``). v2.15.12 (#584):
        ``for_command`` bills any triggered refresh to the command storm budget.
        """
        await self._mbb_ensure_fresh(for_command=for_command)
        headers = self._mbb_headers({"Content-Type": "application/json"})
        async with self._session.post(url, json=body, headers=headers) as resp:
            text = await resp.text()
            if resp.status == 401 and _retry:
                await self._refresh_tokens(for_command=for_command)
                return await self._mbb_post_json(
                    url, body, _retry=False, for_command=for_command
                )
            if resp.status >= 400:
                raise APIError(resp.status, url, body=text)
            if not text:
                return {}
            try:
                loaded = json.loads(text)
            except ValueError:
                return {}
            return loaded if isinstance(loaded, dict) else {}

    async def _mbb_post_rlu(
        self, url: str, sec_token: str, *, _retry: bool = True,
        for_command: bool = False,
    ) -> dict[str, Any]:
        """POST the RLU lock/unlock action — EMPTY body, x-securityToken header.

        The lock/unlock verb is encoded in the URL path tail, NOT a body
        (the ``<rluAction>`` XML body is the deprecated pre-2019 variant).
        The Content-Type must still be the RemoteLockUnlock vendor type or
        the backend 415s. Refreshes once on a 401 and retries (see
        ``_mbb_get``) — but note the ``sec_token`` is action-bound, so a 401
        here is the bearer expiring, not the sec-token (which would 403).
        """
        from .._mbb import MBB_RLU_CONTENT_TYPE  # noqa: PLC0415

        await self._mbb_ensure_fresh(for_command=for_command)
        headers = self._mbb_headers({
            "Content-Type": MBB_RLU_CONTENT_TYPE,
            "x-securityToken": sec_token,
        })
        async with self._session.post(url, data=None, headers=headers) as resp:
            text = await resp.text()
            if resp.status == 401 and _retry:
                await self._refresh_tokens(for_command=for_command)
                return await self._mbb_post_rlu(
                    url, sec_token, _retry=False, for_command=for_command
                )
            if resp.status >= 400:
                raise APIError(resp.status, url, body=text)
            if not text:
                return {}
            try:
                loaded = json.loads(text)
            except ValueError:
                return {}
            return loaded if isinstance(loaded, dict) else {}

    async def _mbb_resolve_read_base(self, vin: str) -> str:
        """Resolve the per-VIN MBB read base via homeRegion (≠ setter host)."""
        from .._home_region import resolve_home_region  # noqa: PLC0415
        from .._mbb import MBB_DEFAULT_READ_BASE  # noqa: PLC0415

        try:
            read_base = await resolve_home_region(
                self, vin, cache=self._home_region_cache,
            )
        except Exception:  # noqa: BLE001
            read_base = MBB_DEFAULT_READ_BASE
        if "cariad.digital" in read_base or "bff.cariad" in read_base:
            read_base = MBB_DEFAULT_READ_BASE
        return read_base

    async def _get_vehicles_via_mbb(self) -> list[str]:
        """Enumerate paired VINs via the legacy MBB usermanagement endpoint.

        The account-level pairing call has no per-VIN homeRegion yet, and the
        ``{country}`` market segment varies by account (CH/DE/AT…). We try the
        id_token's country first, then common fallbacks, across the two known
        hosts, and return on the first candidate that yields VINs. Every
        candidate's HTTP status is logged so a persistent failure pinpoints the
        endpoint instead of a vague "APIError". On total failure we return []
        (never falling through to the dead BFF).
        """
        from .._mbb import (  # noqa: PLC0415
            MBB_DEFAULT_READ_BASE,
            build_mbb_vehicles_url,
            parse_mbb_vehicle_vins,
        )

        self._vehicle_metadata = {}

        # Primary path: user-supplied VIN(s). The durable MBB bearer is
        # ``sc2:fal``-scoped (vehicle function/status layer) and is REJECTED by
        # the account-level usermanagement garage endpoint (live-confirmed
        # 2026-06-21: HTTP 403 ``RS.security.9007`` "no permission for systemId
        # XID_APP_VW"). Vehicle-level reads/commands work with this token, so
        # the user enters the VIN directly in the MBB login and we use it.
        manual = [v for v in getattr(self, "_mbb_manual_vins", []) if v]
        if manual:
            _LOGGER.info(
                "MBB: using %d user-supplied VIN(s) (garage enumeration is "
                "not available to the fal-scoped MBB token).", len(manual),
            )
            return manual

        # Fallback (best-effort): try the usermanagement endpoint anyway, in
        # case some accounts/markets DO grant it. Single host — ``mal-1a`` is
        # /api-only and 404s for /fs-car (live-confirmed). Log each status.
        countries: list[str] = []
        tok_country = self._mbb_country_from_id_token()
        if tok_country:
            countries.append(tok_country)
        for c in ("CH", "DE", "AT"):
            if c not in countries:
                countries.append(c)

        host = MBB_DEFAULT_READ_BASE
        host_label = host.split("//")[-1].split("/")[0]
        last_status: int | str = "?"
        for country in countries:
            url = build_mbb_vehicles_url(host, self._brand.name, country)
            try:
                resp = await self._mbb_get(url)
            except APIError as err:
                last_status = err.status
                _LOGGER.warning(
                    "MBB enum %s /%s → HTTP %s: %s",
                    host_label, country, err.status, str(err.body)[:160],
                )
                continue
            except Exception as err:  # noqa: BLE001
                last_status = type(err).__name__
                _LOGGER.warning(
                    "MBB enum %s /%s → %s", host_label, country,
                    type(err).__name__,
                )
                continue
            vins = parse_mbb_vehicle_vins(resp)
            if vins:
                _LOGGER.info(
                    "MBB enumeration OK via %s /%s → %d vehicle(s)",
                    host_label, country, len(vins),
                )
                return vins
            _LOGGER.warning(
                "MBB enum %s /%s → HTTP 200 but no paired vehicles",
                host_label, country,
            )

        _LOGGER.warning(
            "MBB: no VIN available (enumeration last status %s, and no VIN was "
            "entered). Reconfigure the MBB login and enter your VIN — the "
            "durable token can't list the garage but works per-VIN.",
            last_status,
        )
        return []

    async def _get_mbb_operationlist(
        self, vin: str, *, for_command: bool = False,
    ) -> "MbbOperationList | None":
        """Fetch + cache the per-VIN MBB operationList (service directory).

        Cached 12h — the licence/enrolment state changes rarely, and the call
        is on the setter host (mal-1a, ``/api`` prefix). Returns a parsed
        ``MbbOperationList`` or None on failure (caller treats None as
        "unknown" — it does NOT block the read).

        v2.15.12 (#584): ``for_command`` bills any proactive refresh triggered
        here to the command budget when this is fetched as a command pre-flight.
        """
        from .._mbb import (  # noqa: PLC0415
            MBB_SETTER_BASE,
            build_mbb_operationlist_url,
            parse_mbb_operationlist,
        )

        if not hasattr(self, "_mbb_oplist_cache"):
            self._mbb_oplist_cache: dict[
                str, tuple[MbbOperationList, datetime]
            ] = {}
        now = datetime.now(tz=timezone.utc)
        cached = self._mbb_oplist_cache.get(vin)
        if cached and cached[1] > now:
            return cached[0]

        url = build_mbb_operationlist_url(MBB_SETTER_BASE, vin)
        try:
            # v2.15.0a10 — _retry=False: a 401 here is the data-plane ACL
            # rejecting the MBB read, NOT an expired bearer. The default
            # 401→refresh would hammer the refresh endpoint every poll and trip
            # the refresh-storm guard (IP-ban risk, seen live). b11 — the bearer
            # is instead kept fresh PROACTIVELY by _mbb_ensure_fresh() inside
            # _mbb_get (refresh within the 60s expiry skew), so a genuine expiry
            # no longer leaves every read 401-ing until restart.
            resp = await self._mbb_get(
                url, _retry=False, for_command=for_command
            )
        except APIError as err:
            _LOGGER.warning(
                "MBB operationList ***%s → HTTP %s: %s",
                vin[-6:], err.status, str(err.body)[:160],
            )
            return None
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "MBB operationList ***%s failed: %s", vin[-6:], type(err).__name__,
            )
            return None

        oplist = parse_mbb_operationlist(resp, vin)
        if oplist is not None:
            self._mbb_oplist_cache[vin] = (oplist, now + timedelta(hours=12))
            enabled = [s for s in oplist.services.values() if s.enabled]
            _LOGGER.info(
                "MBB operationList ***%s: role=%s status=%s, %d/%d services "
                "enabled", vin[-6:], oplist.role, oplist.status,
                len(enabled), len(oplist.services),
            )
        return oplist

    def _apply_mbb_subscription(
        self, d: VehicleData, oplist: "MbbOperationList | None",
    ) -> None:
        """Populate the subscription_* fields from the operationList status
        service licence (surfaces as the subscription sensors in HA)."""
        from .._mbb import mbb_operation_granted, mbb_subscription_active  # noqa: PLC0415

        d.subscription_active = mbb_subscription_active(oplist)
        # b1/B2 — "two-way available" symbol: at least one remote command
        # (climate or charge) granted on a currently-licensed service. None when
        # we have no operationList this poll (unknown), not False.
        d.mbb_two_way_available = None if oplist is None else (
            mbb_operation_granted(oplist, "rclima_v1", "P_START_CLIMA_NOSET")
            or mbb_operation_granted(oplist, "rbatterycharge_v1", "P_START")
        )
        if oplist is None:
            return
        svc = oplist.status_service
        if svc is None or not svc.license_expiry:
            return
        d.subscription_expiry_at = svc.license_expiry
        try:
            exp = datetime.fromisoformat(svc.license_expiry.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            delta = exp - datetime.now(tz=timezone.utc)
            d.subscription_days_remaining = delta.days
        except (ValueError, TypeError):
            pass

    async def _get_status_via_mbb_vsr(self, vin: str) -> VehicleData:
        """Read vehicle status via the durable MBB VSR endpoint.

        Strongest for combustion/PHEV (tank %, total range, AdBlue); EV
        SoC/charging field IDs are not yet catalogued so those stay at the
        ``VehicleData`` defaults until a live VSR dump confirms them.
        """
        from .._mbb import (  # noqa: PLC0415
            MBB_VSR_FIELD_ADBLUE_RANGE_KM,
            MBB_VSR_FIELD_TANK_PCT,
            MBB_VSR_FIELD_TOTAL_RANGE_KM,
            build_mbb_vsr_status_url,
            mbb_subscription_active,
            mbb_vsr_field_ids as _mbb_vsr_field_ids,
            parse_mbb_vsr_field,
        )

        d = VehicleData(vin=vin)

        # ── operationList: the service directory. It tells us, authoritatively,
        # whether the vehicle-status service is LICENSED. The classic "no data"
        # case is an EXPIRED We Connect subscription — every paid service is
        # Disabled/noActiveLicense and the VSR read just 403s. Read it first so
        # we (a) surface the subscription state on the entity and (b) skip the
        # doomed VSR call (and its scary 403 log) when it's not licensed. ──
        oplist = await self._get_mbb_operationlist(vin)
        self._apply_mbb_subscription(d, oplist)
        if mbb_subscription_active(oplist) is False:
            _LOGGER.warning(
                "MBB ***%s: the vehicle-status service is not licensed — your "
                "We Connect subscription looks expired/inactive (renew it in "
                "the We Connect app). Skipping the status read; the "
                "subscription sensors still update.", vin[-6:],
            )
            return d

        read_base = await self._mbb_resolve_read_base(vin)
        country = self._mbb_country_from_id_token() or "DE"
        host_label = read_base.split("//")[-1].split("/")[0]
        url = build_mbb_vsr_status_url(read_base, self._brand.name, country, vin)
        _LOGGER.info(
            "MBB VSR status GET → host=%s country=%s (vin ***%s)",
            host_label, country, vin[-6:],
        )
        try:
            # v2.15.0a10 — _retry=False, see _get_mbb_operationlist: avoid the
            # per-poll token-refresh storm when the data-plane ACL 401s the read.
            resp = await self._mbb_get(url, _retry=False)
        except APIError as err:
            _LOGGER.warning(
                "MBB VSR read ***%s via %s/%s → HTTP %s: %s",
                vin[-6:], host_label, country, err.status, str(err.body)[:200],
            )
            return d
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "MBB VSR read failed for ***%s (%s/%s): %s",
                vin[-6:], host_label, country, type(err).__name__,
            )
            return d

        tank = safe_int(parse_mbb_vsr_field(resp, MBB_VSR_FIELD_TANK_PCT))
        if tank is not None:
            d.fuel_level = tank
        rng = safe_int(parse_mbb_vsr_field(resp, MBB_VSR_FIELD_TOTAL_RANGE_KM))
        if rng is not None:
            d.combustion_range_km = rng
        adblue = safe_int(parse_mbb_vsr_field(resp, MBB_VSR_FIELD_ADBLUE_RANGE_KM))
        if adblue is not None:
            d.adblue_range_km = adblue

        # Diagnostics: a 200 with an unexpected shape (or a car that hasn't
        # reported) leaves every field None. Surface the actual envelope so the
        # next round can map the real field IDs instead of guessing — list the
        # field IDs the car DID return (capped), or the top-level keys if the
        # StoredVehicleDataResponse envelope is missing entirely.
        mapped = [v for v in (tank, rng, adblue) if v is not None]
        if not mapped:
            field_ids = _mbb_vsr_field_ids(resp)
            if field_ids:
                _LOGGER.warning(
                    "MBB VSR ***%s via %s/%s → HTTP 200 but none of the mapped "
                    "fields were present. Field IDs the car returned: %s",
                    vin[-6:], host_label, country, ", ".join(field_ids[:40]),
                )
            else:
                _LOGGER.warning(
                    "MBB VSR ***%s via %s/%s → HTTP 200 but no StoredVehicleData "
                    "fields. Envelope top-level keys: %s",
                    vin[-6:], host_label, country,
                    list(resp.keys())[:10] if isinstance(resp, dict) else type(resp).__name__,
                )
        else:
            _LOGGER.info(
                "MBB VSR ***%s → mapped %d field(s): fuel=%s range=%s adblue=%s",
                vin[-6:], len(mapped), tank, rng, adblue,
            )
        return d

    async def _command_rlu_mbb(
        self, vin: str, *, spin: str = "", lock: bool = True,
    ) -> None:
        """Lock/unlock via the classic Car-Net 3-leg S-PIN SecToken + RLU flow.

        Leg 1: GET the SPIN challenge.  Leg 2: POST the hashed SPIN → level-2
        security token.  Leg 3: POST the empty-body lock/unlock action with
        ``x-securityToken`` → poll the request status. The S-PIN is validated
        locally first (a wrong hash burns one of the three allowed tries).
        """
        from .._mbb import (  # noqa: PLC0415
            MBB_SETTER_BASE,
            build_mbb_completed_body,
            build_mbb_rlu_action_url,
            build_mbb_spin_challenge_url,
            build_mbb_spin_completed_url,
            compute_spin_hash,
            parse_mbb_completed_token,
            parse_mbb_rlu_request_id,
            parse_mbb_spin_challenge,
            validate_spin_format,
        )

        verb = "lock" if lock else "unlock"
        pin = spin or self._spin
        if not pin:
            raise SpinError("S-PIN required for MBB lock/unlock")
        validate_spin_format(pin)  # raises locally BEFORE burning a try

        setter = MBB_SETTER_BASE

        # v2.17.1 (#666) — leg 3 (the RLU action + its status poll) uses the
        # homeRegion READ base under /fs-car/bs/rlu/v1/{Brand}/{country}/…,
        # NOT the setter host. Resolve it up-front, mirroring the VSR path.
        # Legs 1-2 (the S-PIN rolesrights handshake) stay on the setter /api.
        from .._mbb import MBB_DEFAULT_READ_BASE  # noqa: PLC0415
        from .._home_region import resolve_home_region  # noqa: PLC0415
        try:
            read_base = await resolve_home_region(
                self, vin, cache=self._home_region_cache,
            )
        except Exception:  # noqa: BLE001
            read_base = MBB_DEFAULT_READ_BASE
        if "cariad.digital" in read_base or "bff.cariad" in read_base:
            read_base = MBB_DEFAULT_READ_BASE
        brand_name = self._brand.name
        if self._tokens and self._tokens.strategy == "mbb":
            country = self._mbb_country_from_id_token() or "DE"
        else:
            country = "DE"

        # Leg 1 — challenge
        ch_resp = await self._mbb_get(
            build_mbb_spin_challenge_url(setter, vin, lock=lock),
            for_command=True,
        )
        level1, challenge, remaining = parse_mbb_spin_challenge(ch_resp)
        if not level1 or not challenge:
            raise VehicleCommandError(verb, "MBB SPIN challenge missing token/challenge")
        if remaining is not None and remaining < 2:
            raise SpinError(
                f"S-PIN has only {remaining} attempt(s) left — refusing to "
                "risk a lockout. Verify your S-PIN in the brand app first."
            )

        # Leg 2 — submit hashed SPIN, get the level-2 security token
        spin_hash = compute_spin_hash(pin, challenge)
        try:
            comp_resp = await self._mbb_post_json(
                build_mbb_spin_completed_url(setter),
                build_mbb_completed_body(level1, challenge, spin_hash),
                for_command=True,
            )
        except APIError as exc:
            # v2.17.3 — the backend rejected the S-PIN hash. Legs 1-2 of the
            # rolesrights handshake DID run (so the MBB grant permits the
            # operation), the PIN VALUE is simply wrong. Surface an actionable
            # SpinError instead of a raw 403 traceback — and note the lockout so
            # the user doesn't keep burning their remaining tries.
            if exc.status == 403 and "invalidsecuritypin" in (exc.body or "").lower():
                raise SpinError(
                    "The Security PIN was rejected by VW — double-check your "
                    "S-PIN in the We Connect / Car-Net app. After 3 wrong "
                    "attempts the PIN locks for a while."
                ) from exc
            raise
        sec_token = parse_mbb_completed_token(comp_resp)
        if not sec_token:
            raise VehicleCommandError(verb, "MBB SPIN completion returned no token")

        # Leg 3 — the action (empty body) + poll
        action_resp = await self._mbb_post_rlu(
            build_mbb_rlu_action_url(
                read_base, brand_name, country, vin, lock=lock,
            ),
            sec_token,
            for_command=True,
        )
        request_id = parse_mbb_rlu_request_id(action_resp)
        _LOGGER.info(
            "MBB %s sent for ***%s (request_id=%s)",
            verb, vin[-6:], request_id or "(none)",
        )
        if request_id:
            await self._poll_mbb_rlu(
                read_base, brand_name, country, vin, request_id, verb,
            )

    async def _poll_mbb_rlu(
        self, read_base: str, brand: str, country: str, vin: str,
        request_id: str, verb: str,
    ) -> None:
        """Poll the RLU request status until success/fail or timeout (~45s)."""
        from .._mbb import (  # noqa: PLC0415
            build_mbb_rlu_status_url,
            parse_mbb_rlu_status,
        )

        url = build_mbb_rlu_status_url(read_base, brand, country, vin, request_id)
        for _ in range(15):
            await asyncio.sleep(3)
            try:
                resp = await self._mbb_get(url, for_command=True)
            except Exception:  # noqa: BLE001
                continue
            status = parse_mbb_rlu_status(resp)
            if status in ("request_successful", "succeeded"):
                _LOGGER.info("MBB %s confirmed for ***%s", verb, vin[-6:])
                return
            if status in ("request_fail", "failed"):
                raise VehicleCommandError(
                    verb, f"MBB backend reported {status} (door open / key inside?)"
                )
        _LOGGER.warning(
            "MBB %s status poll timed out for ***%s — command may still complete",
            verb, vin[-6:],
        )

    async def _mbb_post_action(
        self, url: str, sec_token: str, body: str | None, content_type: str,
        *, _retry: bool = True, for_command: bool = False,
    ) -> dict[str, Any]:
        """POST an MBB write-command action (XML body) with the level-2
        x-securityToken + the vendor content-type. Refresh-once on 401.
        v2.15.12 (#584): ``for_command`` bills refreshes to the command budget."""
        await self._mbb_ensure_fresh(for_command=for_command)
        headers = self._mbb_headers({
            "Content-Type": content_type,
            "x-securityToken": sec_token,
        })
        data = body.encode("utf-8") if isinstance(body, str) else None
        async with self._session.post(url, data=data, headers=headers) as resp:
            text = await resp.text()
            if resp.status == 401 and _retry:
                await self._refresh_tokens(for_command=for_command)
                return await self._mbb_post_action(
                    url, sec_token, body, content_type, _retry=False,
                    for_command=for_command)
            if resp.status >= 400:
                raise APIError(resp.status, url, body=text)
            if not text:
                return {}
            try:
                loaded = json.loads(text)
            except ValueError:
                return {}
            return loaded if isinstance(loaded, dict) else {}

    async def _command_mbb_op(
        self, vin: str, command_name: str, *, spin: str = "",
        body_override: str | None = None,
    ) -> None:
        """Durable MBB write-command via the 3-leg SecToken flow, routed
        GENERICALLY through the operationList (per-service host = correct for
        any country/brand) and gated on the operation actually being granted.

        Live-confirmed that leg-1 (security-pin-auth-requested) = HTTP 200 for
        climate/charge — so this drives DURABLE two-way where data reads can't.
        """
        from .._mbb import (  # noqa: PLC0415
            MBB_COMMANDS,
            MBB_SETTER_BASE,
            build_mbb_action_url,
            build_mbb_completed_body,
            build_mbb_op_auth_url,
            build_mbb_spin_completed_url,
            compute_spin_hash,
            mbb_operation_granted,
            mbb_service_base,
            parse_mbb_action_request_id,
            parse_mbb_completed_token,
            parse_mbb_spin_challenge,
            validate_spin_format,
        )

        spec = MBB_COMMANDS.get(command_name)
        if spec is None:
            raise VehicleCommandError(command_name, "unknown MBB command")
        pin = spin or self._spin
        if not pin:
            raise SpinError(f"S-PIN required for MBB {command_name}")
        validate_spin_format(pin)

        # operationList → per-service host (generic) + granted gate
        oplist = await self._get_mbb_operationlist(vin, for_command=True)
        country = self._mbb_country_from_id_token() or "DE"
        base = mbb_service_base(
            oplist, spec.service_id, brand=self._brand.name,
            country=country, vin=vin)
        if base is None:
            raise VehicleCommandError(
                command_name,
                f"{spec.service_id} not available on this vehicle "
                "(not in the operationList)")
        if not mbb_operation_granted(oplist, spec.service_id, spec.operation_id):
            raise VehicleCommandError(
                command_name,
                f"{spec.operation_id} not granted — check the We Connect "
                "subscription / that you're the primary user")

        setter = MBB_SETTER_BASE
        # Leg 1 — operation-specific SecToken challenge
        ch = await self._mbb_get(
            build_mbb_op_auth_url(setter, vin, spec.service_id, spec.operation_id),
            for_command=True)
        level1, challenge, remaining = parse_mbb_spin_challenge(ch)
        if not level1 or not challenge:
            raise VehicleCommandError(command_name, "SecToken challenge missing")
        if remaining is not None and remaining < 2:
            raise SpinError(
                f"S-PIN has only {remaining} attempt(s) left — refusing to risk "
                "a lockout. Verify your S-PIN in the brand app first.")
        # Leg 2 — submit hashed S-PIN
        comp = await self._mbb_post_json(
            build_mbb_spin_completed_url(setter),
            build_mbb_completed_body(level1, challenge, compute_spin_hash(pin, challenge)),
            for_command=True)
        sec = parse_mbb_completed_token(comp)
        if not sec:
            raise VehicleCommandError(command_name, "SecToken completion returned no token")
        # Leg 3 — the action on the service's own host
        url = build_mbb_action_url(base, spec.action_subpath)
        resp = await self._mbb_post_action(
            url, sec, body_override if body_override is not None else spec.body,
            spec.content_type, for_command=True)
        request_id = parse_mbb_action_request_id(resp)
        # NOTE: we deliberately do NOT poll for confirmation on the climater/
        # charger/timer actions. The action fires correctly above, but their
        # per-service status URL + response envelope differ from the RLU one
        # and aren't live-captured yet — reusing the RLU poll (different host +
        # path) would just 404 for ~45s and block the coordinator. HA reflects
        # the new state on the next poll cycle. (RLU keeps its own poll in
        # _command_rlu_mbb.) Wire a per-service _poll_mbb_action once the
        # climater/charger status shape is captured live.
        _LOGGER.info(
            "MBB command %s sent for ***%s (request_id=%s) — state updates "
            "on the next poll", command_name, vin[-6:], request_id or "(none)")

    # ── v1/v2 endpoint dispatch (Session 3A — #51, #74) ─────────────────────
    #
    # Newer premium Audi models (RS e-tron GT, Q6 e-tron, A3 2024+ on PPC/PPE)
    # and recent VW EU models (Passat 2025 B9) reject the /vehicle/v1/...
    # command paths with HTTP 404. The same logical commands exist under
    # /vehicle/v2/...  We learn the right prefix per VIN on the first 404
    # and remember it for subsequent commands. Cache is per-client-instance
    # so a coordinator restart re-learns (one extra 404 per cold start, OK).

    def _supports_v2_paths(self, vin: str) -> bool:
        """Return True if the v2 command prefix is known to work for *vin*."""
        flags: dict[str, bool] = getattr(self, "_v2_command_paths", {}) or {}
        return bool(flags.get(vin, False))

    def _mark_v2_active(self, vin: str) -> None:
        """Remember that v2 worked for *vin* — skip v1 on subsequent calls."""
        if not hasattr(self, "_v2_command_paths"):
            self._v2_command_paths: dict[str, bool] = {}
        if not self._v2_command_paths.get(vin, False):
            _LOGGER.info(
                "CARIAD command profile: %s now using /vehicle/v2/ paths",
                vin[-6:] if vin else "***",
            )
            self._v2_command_paths[vin] = True

    async def _post_command(
        self, vin: str, path_suffix: str, **kwargs: Any
    ) -> Any:
        """POST to /vehicle/v1/vehicles/{vin}/{suffix} with v2 fallback on 404.

        First call per VIN: try v1, on 404 retry v2 and remember.
        Subsequent calls: skip v1 if v2 is known to work for this VIN.
        Other 4xx/5xx errors propagate as-is — this only handles the
        version-mismatch case.
        """
        # v2.1.0 — per-VIN base URL via HomeRegion lookup.
        base = self._base_for_vin(vin)
        if self._supports_v2_paths(vin):
            return await self._post(
                f"{base}/vehicle/v2/vehicles/{vin}/{path_suffix}", **kwargs,
            )
        try:
            return await self._post(
                f"{base}/vehicle/v1/vehicles/{vin}/{path_suffix}", **kwargs,
            )
        except APIError as err:
            if getattr(err, "status", 0) != 404:
                raise
            # v1 said the resource doesn't exist — try v2 once
            result = await self._post(
                f"{base}/vehicle/v2/vehicles/{vin}/{path_suffix}", **kwargs,
            )
            self._mark_v2_active(vin)
            return result

    async def _post_command_with_fallback_paths(
        self,
        vin: str,
        primary_suffix: str,
        primary_payload: dict[str, Any],
        fallback_suffix: str,
        fallback_payload: dict[str, Any],
    ) -> Any:
        """POST a vehicle command with full v1/v2 + primary/fallback dispatch.

        Used by lock/unlock and climate/charging start/stop where the
        CARIAD BFF historically exposes both a combined endpoint
        (e.g. ``/access/lock-unlock`` with ``{"action": "lock"}``) and
        separate endpoints (e.g. ``/access/lock`` + ``/access/unlock``).

        Order of attempts (each via ``_post_command``, so each carries its
        own v1 → v2 fallback on 404):

        1. ``primary_suffix`` (combined endpoint, the historically
           preferred form on the older CARIAD BFF)
        2. ``fallback_suffix`` (separate endpoint, what older firmware
           and some current PPE/PPC vehicles still expect)

        The previous implementation caught a bare ``except Exception`` and
        always fell back, which masked auth failures, rate limits and
        backend 500s as if they were endpoint mismatches. v1.8.8 narrows
        the fallback trigger to HTTP 404 only — every other error
        propagates so the coordinator's
        ``classify_command_failure`` can see it.
        """
        try:
            return await self._post_command(
                vin, primary_suffix, json=primary_payload,
            )
        except APIError as err:
            if getattr(err, "status", 0) != 404:
                raise
            return await self._post_command(
                vin, fallback_suffix, json=fallback_payload,
            )

    async def _settings_put_with_fallback(
        self,
        vin: str,
        path_suffix: str,
        put_body: dict[str, Any],
        post_body: dict[str, Any],
        command_name: str,
    ) -> None:
        """PUT a ``.../settings`` write (v1) with a legacy-POST fallback.

        v2.16.3/v2.17.0 (#666) — the CARIAD BFF exposes climatisation/settings
        and charging/settings as **PUT** (verified across four BFF-native
        clients: CarConnectivity audi/vw, volkswagencarnet, WeConnect-python).
        We historically POSTed them, which the gateway answers with **404**
        (not a clean 405) on the stricter PPE/MEB platform — that broke both
        climate temp-set and charge-target on Q4/Q6 e-tron (torstentosh, #666).

        Primary = PUT the v1 path directly (bypasses the shared v2-path flag,
        since every source uses v1 for these writes). Fallback = the legacy
        POST body via ``_post_command`` so any car that accepted the old form
        can't regress. If both return 404 the write isn't provisioned for this
        vehicle → a clean VehicleCommandError, not a raw 404 traceback.
        """
        base = self._base_for_vin(vin)
        put_url = f"{base}/vehicle/v1/vehicles/{vin}/{path_suffix}"
        try:
            await self._put(put_url, json=put_body)
            return
        except APIError as err:
            if getattr(err, "status", 0) not in (404, 405):
                raise
        try:
            await self._post_command(vin, path_suffix, json=post_body)
        except APIError as err:
            if getattr(err, "status", 0) != 404:
                raise
            raise VehicleCommandError(
                command_name,
                f"the '{path_suffix}' write isn't available on this vehicle "
                "via the current API (both PUT and the legacy POST returned "
                "404). On PPE/MEB vehicles (e.g. Q4/Q6 e-tron) some settings "
                "writes aren't exposed — use the official app instead.",
            ) from err

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        """Set charge target SoC.

        v2.17.0 (#666) — charging/settings is a PUT (was POST → 404 on the
        PPE Q4; torstentosh's charge-target 404). MBB legacy path unchanged.
        """
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            from .._mbb import build_mbb_charger_settings_body  # noqa: PLC0415
            await _tgt._command_mbb_op(
                vin, "charge_target_soc",
                body_override=build_mbb_charger_settings_body(target))
            return
        await self._settings_put_with_fallback(
            vin, "charging/settings",
            put_body={"targetSOC_pct": target},
            post_body={"targetSOC_pct": target},
            command_name="set_target_soc",
        )

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        """Set pre-conditioning temperature on the CARIAD BFF.

        v2.16.3 (#666) — the climatisation/settings write is a **PUT** with
        body ``{targetTemperature, targetTemperatureUnit:"celsius"}``, verified
        across four independent BFF-native clients (CarConnectivity audi/vw,
        volkswagencarnet, WeConnect-python). ``targetTemperature_C`` is the
        *read*-side field name — reusing it as the write field, plus POSTing a
        PUT-only route, made the gateway answer **404** (not a clean 405),
        which broke temperature-set — most visibly on the stricter PPE/MEB
        Audis (Q4/Q6 e-tron), where torstentosh's Q4 404'd on every attempt.

        Primary = the grounded PUT + correct body on the v1 path (competitors
        only ever use v1 for climate; the shared v2-path flag is deliberately
        bypassed so a VIN marked v2 by some *other* endpoint doesn't skip the
        working v1 climate route). Fallback = the legacy POST+``_C`` shape, so
        any car that somehow accepted the old form can't regress. If both
        return 404 the write genuinely isn't provisioned for this vehicle →
        a clean VehicleCommandError instead of a raw 404 traceback.
        """
        await self._settings_put_with_fallback(
            vin, "climatisation/settings",
            put_body={
                "targetTemperature": temp_c,
                "targetTemperatureUnit": "celsius",
            },
            post_body={"targetTemperature_C": temp_c},
            command_name="set_climate_temperature",
        )

    async def command_set_charge_mode(self, vin: str, mode: str) -> None:
        """Set charging mode — MANUAL, TIMER, PREFERRED_CHARGING_TIMES.

        v2.17.0 (#666) — charging/settings is a PUT (was POST → 404 on PPE).
        """
        await self._settings_put_with_fallback(
            vin, "charging/settings",
            put_body={"chargeMode": mode.upper()},
            post_body={"chargeMode": mode.upper()},
            command_name="set_charge_mode",
        )

    async def command_set_min_soc(self, vin: str, min_soc: int) -> None:
        """Set minimum SoC for PHEV (0–100%).

        v2.17.0 (#666) — charging/settings is a PUT (was POST → 404 on PPE).
        """
        await self._settings_put_with_fallback(
            vin, "charging/settings",
            put_body={"minChargeLimit_pct": min_soc},
            post_body={"minChargeLimit_pct": min_soc},
            command_name="set_min_soc",
        )

    async def command_set_max_charge_current(self, vin: str, ampere: int) -> None:
        """Set max AC charge current in Amperes.

        v1.12.0 (#91 follow-up + #90 verified) — body shape verified
        live in #90 (Golf 7 GTE returns ``maxChargeCurrentAC_A = 16``
        from chargingSettings GET, the symmetrical PUT body uses the
        same field name). Same chargingSettings endpoint as
        ``command_set_target_soc`` / ``command_set_charge_mode`` / etc.,
        so v1 → v2 fallback comes for free via ``_post_command``.

        Typical range: 6, 10, 13, 16, 32 A. The CARIAD BFF doesn't
        clamp invalid values server-side reliably — entity layer
        (``number.py``) enforces 6-32 A range.

        ️ [Inference] — verified on Golf 7 GTE READ side (#90 live
        scout dump = 16 A); WRITE side semantics not yet captured
        from official VW EU app traffic. If the backend rejects the
        write, the response goes through the standard
        ``classify_command_failure`` pipeline and surfaces as
        ``ServiceValidationError`` with the actual reason.

        v2.17.0 (#666) — charging/settings is a PUT (was POST → 404 on PPE).
        """
        await self._settings_put_with_fallback(
            vin, "charging/settings",
            put_body={"maxChargeCurrentAC_A": int(ampere)},
            post_body={"maxChargeCurrentAC_A": int(ampere)},
            command_name="set_max_charge_current",
        )

    async def command_start_window_heating(self, vin: str) -> None:
        """Start window heating (front windscreen + rear window)."""
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_mbb_op(vin, "window_heat_start")
            return
        await self._post(
            f"{self._base_for_vin(vin)}/vehicle/v1/vehicles/{vin}/climatisation/windowheating/start-stop",
            json={"action": "start"},
        )

    async def command_stop_window_heating(self, vin: str) -> None:
        """Stop window heating."""
        _tgt = self._mbb_command_target()
        if _tgt is not None:
            await _tgt._command_mbb_op(vin, "window_heat_stop")
            return
        await self._post(
            f"{self._base_for_vin(vin)}/vehicle/v1/vehicles/{vin}/climatisation/windowheating/start-stop",
            json={"action": "stop"},
        )

    # v2.8.0 - Auxiliary heating (Standheizung).
    async def command_start_aux_heating(
        self,
        vin: str,
        spin: str = "",
        duration_min: int = 30,
        target_c: float = 21.0,  # noqa: ARG002 - pre-heater takes no target temp
    ) -> None:
        """Start engine pre-heater (Audi + VW EU CARIAD-BFF).

        Endpoint: ``POST /vehicle/v1/vehicles/{vin}/auxiliaryheating/start``
        — one word, matching the CARIAD read field ``auxiliaryHeating``. The
        earlier hyphenated ``auxiliary-heating`` (tried on v1 AND v2) 404'd for
        every Audi (#752). Body is the minimal
        ``{"duration_min": <int>, "spin": <S-PIN>}`` the myAudi backend accepts
        (community-verified against a working client) — the old
        ``{command, duration_in_min, target_temperature_in_kelvin}`` was an
        unverified APK-research guess, and the pre-heater request carries no
        target temperature (``target_c`` kept for signature parity, unused). The
        S-PIN is sent when configured.
        """
        # v2.15.12 (#584 follow-up) — on a legacy MBB-primary entry
        # ``self._access_token`` is the MBB bearer, which the CARIAD BFF
        # below rejects with "400 missing or invalid auth header". There is
        # no verified MBB aux-heating (rheating) route yet, so rather than
        # leak the wrong bearer to the wrong backend, fail cleanly with a
        # clear message. (Non-MBB entries fall through to the BFF as before.)
        if self._mbb_command_target() is not None:
            raise VehicleCommandError(
                "command_start_aux_heating",
                "remote auxiliary heating is not available on the legacy "
                "Car-Net two-way path yet — this vehicle uses MBB, which has "
                "no verified aux-heating command",
            )
        _pin = spin or self._spin
        body: dict[str, Any] = {"duration_min": int(duration_min)}
        if _pin:
            body["spin"] = _pin
        await self._post_command(vin, "auxiliaryheating/start", json=body)

    async def command_stop_aux_heating(self, vin: str) -> None:
        """Stop engine pre-heater (Audi + VW EU CARIAD-BFF).

        ``POST /vehicle/v1/vehicles/{vin}/auxiliaryheating/stop`` (one word,
        #752) with an empty body — matching a working myAudi client's stop.
        v2 fallback on 404 via ``_post_command``.
        """
        # v2.15.12 (#584 follow-up) — same MBB-primary guard as start: don't
        # leak the MBB bearer to the CARIAD BFF; fail cleanly instead.
        if self._mbb_command_target() is not None:
            raise VehicleCommandError(
                "command_stop_aux_heating",
                "remote auxiliary heating is not available on the legacy "
                "Car-Net two-way path yet — this vehicle uses MBB, which has "
                "no verified aux-heating command",
            )
        await self._post_command(vin, "auxiliaryheating/stop", json={})

    async def command_set_departure_timer(
        self,
        vin: str,
        timer_id: int,
        enabled: bool,
        departure_time: str | None,
        recurring_on: list[str] | None = None,
    ) -> None:
        """Set a departure timer (1–3).

        Args:
            vin:            Vehicle VIN
            timer_id:       1, 2 or 3
            enabled:        True to enable, False to disable
            departure_time: "HH:MM" format, e.g. "07:30" (None = keep existing)
            recurring_on:   v2.0.0 (Big-Bang) — optional list of weekday
                            strings (``MONDAY``, ``TUESDAY``, …, ``SUNDAY``)
                            for weekly preheat. When provided, the timer
                            switches to ``recurring`` mode and fires on
                            each listed day; when None the existing
                            recurrence pattern (or one-off) is preserved.
                            Backed by CARIAD-BFF
                            ``/climatisation/timers`` ``recurringOn`` field.
        """
        payload: dict[str, Any] = {"id": timer_id, "enabled": enabled}
        if departure_time:
            payload["departureTime"] = {"time": departure_time}
        if recurring_on:
            # Validate + uppercase: API only accepts the canonical list.
            valid = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                     "FRIDAY", "SATURDAY", "SUNDAY"}
            cleaned = [d.upper() for d in recurring_on if d.upper() in valid]
            if cleaned:
                payload["recurringOn"] = cleaned
                payload["type"] = "RECURRING"
        await self._post(
            f"{self._base_for_vin(vin)}/vehicle/v1/vehicles/{vin}/climatisation/timers",
            json=payload,
        )

    # ── data parsing ───────────────────────────────────────────────────────────

    def _parse_trip_statistics(
        self,
        d: VehicleData,
        short_term: dict[str, Any],
        long_term: dict[str, Any],
    ) -> None:
        """v2.7.0b11 — populate trip + lifetime fields from tripstatistics.

        Cariad-BFF response shape (both shortTerm and longTerm):
            {"tripData": [
                {"tripEndTimestamp": "...", "mileage_km": 142,
                 "travelTime": 113, "averageSpeed_kmph": 75,
                 "averageFuelConsumption": 68,  # int x10 (=> 6.8 l/100km)
                 "averageElectricEngineConsumption": 0,  # int x10 (kWh/100km)
                 "averageRecuperation": 12,
                 "overallMileage_km": 143229,
                 ...},
                ...
            ]}

        shortTerm trips: last ~15 individual drives, ordered most-recent first.
        longTerm trips: cumulative aggregate per cycle (since last reset).

        We populate:
          - last_trip_* fields from shortTerm[0]
          - recent_trips list (5 entries) from shortTerm[:5] for the
            extra_state_attributes on the last_trip_distance_km sensor
          - lifetime_* fields from longTerm[0] (the active aggregate)
        """
        # ---- shortTerm: most recent trip + recent trips list ----
        short = short_term.get("tripData") if isinstance(short_term, dict) else None
        if isinstance(short, list) and short:
            last = short[0]
            if isinstance(last, dict):
                # mileage_km may be int or float
                mileage = last.get("mileage_km")
                if isinstance(mileage, (int, float)):
                    d.last_trip_distance_km = float(mileage)
                travel = last.get("travelTime")
                if isinstance(travel, (int, float)):
                    d.last_trip_duration_min = int(travel)
                avg_speed = last.get("averageSpeed_kmph")
                if isinstance(avg_speed, (int, float)):
                    d.last_trip_avg_speed_kmh = float(avg_speed)
                avg_fuel = last.get("averageFuelConsumption")
                if isinstance(avg_fuel, (int, float)):
                    # Stored as int x10
                    d.last_trip_avg_fuel_consumption_l_100km = (
                        float(avg_fuel) / 10.0
                    )
                avg_elec = last.get("averageElectricEngineConsumption")
                if isinstance(avg_elec, (int, float)):
                    d.last_trip_avg_electric_consumption_kwh_100km = (
                        float(avg_elec) / 10.0
                    )
                # v2.10.0 Group A - per-trip totals. CARIAD BFF firmware
                # ships these directly under several key names; we try
                # the canonical name first and derive from
                # avg * distance / 100 ONLY when no direct field is
                # present, so a backend-supplied total is never
                # overwritten by a derived one. field-name variants
                # tried defensively.
                total_fuel = (
                    last.get("totalFuelConsumption_l")
                    or last.get("totalFuelConsumption")
                    or last.get("fuelConsumption_l")
                )
                if isinstance(total_fuel, (int, float)):
                    d.last_trip_total_fuel_consumption_l = float(total_fuel)
                elif (
                    d.last_trip_avg_fuel_consumption_l_100km is not None
                    and d.last_trip_distance_km is not None
                ):
                    d.last_trip_total_fuel_consumption_l = round(
                        d.last_trip_avg_fuel_consumption_l_100km
                        * d.last_trip_distance_km / 100.0, 2,
                    )
                total_elec = (
                    last.get("totalElectricConsumption_kwh")
                    or last.get("totalElectricEngineConsumption_kwh")
                    or last.get("totalElectricConsumption")
                )
                if isinstance(total_elec, (int, float)):
                    d.last_trip_total_electric_consumption_kwh = float(total_elec)
                elif (
                    d.last_trip_avg_electric_consumption_kwh_100km is not None
                    and d.last_trip_distance_km is not None
                ):
                    d.last_trip_total_electric_consumption_kwh = round(
                        d.last_trip_avg_electric_consumption_kwh_100km
                        * d.last_trip_distance_km / 100.0, 2,
                    )
                ts = last.get("tripEndTimestamp")
                if isinstance(ts, str):
                    d.last_trip_timestamp = ts
                # v2.10.0 - trip-reset timestamp (audi_connect_ha
                # `shortterm_reset` parity). Field-name variants
                # observed across firmware: tripStartTimestamp,
                # resetTimestamp, dataResetAt.
                reset_ts = (
                    last.get("tripStartTimestamp")
                    or last.get("resetTimestamp")
                    or last.get("dataResetAt")
                )
                if isinstance(reset_ts, str):
                    d.last_trip_reset_at = reset_ts
            # Recent trips for extra_state_attributes: keep small.
            recent: list[dict[str, Any]] = []
            for trip in short[:5]:
                if not isinstance(trip, dict):
                    continue
                recent.append({
                    "timestamp": trip.get("tripEndTimestamp"),
                    "distance_km": trip.get("mileage_km"),
                    "duration_min": trip.get("travelTime"),
                    "avg_speed_kmh": trip.get("averageSpeed_kmph"),
                })
            d.recent_trips = recent

        # ---- longTerm: lifetime cumulative ----
        long_trips = long_term.get("tripData") if isinstance(long_term, dict) else None
        if isinstance(long_trips, list) and long_trips:
            first = long_trips[0]
            if isinstance(first, dict):
                lifetime_km = (
                    first.get("overallMileage_km")
                    or first.get("mileage_km")
                )
                if isinstance(lifetime_km, (int, float)):
                    d.lifetime_distance_km = float(lifetime_km)
                lt_fuel = first.get("averageFuelConsumption")
                if isinstance(lt_fuel, (int, float)):
                    d.lifetime_avg_fuel_consumption_l_100km = (
                        float(lt_fuel) / 10.0
                    )
                lt_elec = first.get("averageElectricEngineConsumption")
                if isinstance(lt_elec, (int, float)):
                    d.lifetime_avg_electric_consumption_kwh_100km = (
                        float(lt_elec) / 10.0
                    )

    def _parse_refuel_trip(
        self,
        d: VehicleData,
        cyclic: dict[str, Any],
    ) -> None:
        """v2.10.0 - parse the cyclic / refuel trip aggregator.

        CARIAD BFF tripstatistics?type=cyclic ships the same field
        shape as shortTerm / longTerm but the data window is reset by
        the vehicle on every tank-fill or charge-completion event.
        Useful as the "kWh per charge" / "L per tank" Energy-Dashboard
        building block that today is missing in the HA-VAG ecosystem.

        Shape (per CARIAD BFF, mirrored from the shortTerm parser):
            {"tripData": [
                {"tripEndTimestamp": "...", "mileage_km": 412,
                 "travelTime": 387, "averageSpeed_kmph": 64,
                 "averageFuelConsumption": 58,  # int x10
                 "averageElectricEngineConsumption": 0,
                 "averageRecuperation": 18,
                 "totalElectricConsumption_kwh": 0,
                 "totalFuelConsumption_l": 23.4,
                 ...}
            ]}

        ``tripData[0]`` is the current cycle. Older cycles (one per
        previous refuel) tail behind in tripData[1:] but we expose
        only the current cycle as sensors; older cycles stay in the
        raw diagnostics dump for users that want history.
        """
        if not isinstance(cyclic, dict):
            return
        trips = cyclic.get("tripData")
        if not isinstance(trips, list) or not trips:
            return
        first = trips[0]
        if not isinstance(first, dict):
            return

        mileage = first.get("mileage_km")
        if isinstance(mileage, (int, float)):
            d.refuel_trip_distance_km = float(mileage)
        travel = first.get("travelTime")
        if isinstance(travel, (int, float)):
            d.refuel_trip_duration_min = int(travel)
        avg_speed = first.get("averageSpeed_kmph")
        if isinstance(avg_speed, (int, float)):
            d.refuel_trip_avg_speed_kmh = float(avg_speed)
        avg_fuel = first.get("averageFuelConsumption")
        if isinstance(avg_fuel, (int, float)):
            d.refuel_trip_avg_fuel_consumption_l_100km = float(avg_fuel) / 10.0
        avg_elec = first.get("averageElectricEngineConsumption")
        if isinstance(avg_elec, (int, float)):
            d.refuel_trip_avg_electric_consumption_kwh_100km = (
                float(avg_elec) / 10.0
            )
        # Totals - some firmware ships these directly; others require
        # derivation from avg * distance. Try direct first, fall through
        # to the derived form when avg + distance are both present.
        total_fuel = first.get("totalFuelConsumption_l")
        if isinstance(total_fuel, (int, float)):
            d.refuel_trip_total_fuel_consumption_l = float(total_fuel)
        elif (
            d.refuel_trip_avg_fuel_consumption_l_100km is not None
            and d.refuel_trip_distance_km is not None
        ):
            d.refuel_trip_total_fuel_consumption_l = round(
                d.refuel_trip_avg_fuel_consumption_l_100km
                * d.refuel_trip_distance_km / 100.0, 2,
            )
        total_elec = first.get("totalElectricConsumption_kwh")
        if isinstance(total_elec, (int, float)):
            d.refuel_trip_total_electric_consumption_kwh = float(total_elec)
        elif (
            d.refuel_trip_avg_electric_consumption_kwh_100km is not None
            and d.refuel_trip_distance_km is not None
        ):
            d.refuel_trip_total_electric_consumption_kwh = round(
                d.refuel_trip_avg_electric_consumption_kwh_100km
                * d.refuel_trip_distance_km / 100.0, 2,
            )
        recup = first.get("averageRecuperation")
        if isinstance(recup, (int, float)):
            # Stored as int x10 in the same encoding as fuel/elec
            d.refuel_trip_recuperation_kwh = float(recup) / 10.0
        ts = first.get("tripEndTimestamp")
        if isinstance(ts, str):
            d.refuel_trip_timestamp = ts

    def _parse_status(
        self,
        vin: str,
        raw: dict[str, Any],
        parking: dict[str, Any],
    ) -> VehicleData:
        """Map raw selectivestatus JSON → VehicleData.

        Path documentation: docs/research/VAG_GROUP_ECOSYSTEM.md
        """
        v = self._val
        d = VehicleData(vin=vin)

        # v2.8.0 quick win D — per-sub-job presence telemetry. The
        # selectivestatus response packs many logical jobs into one call;
        # this records which sub-blocks shipped so diagnostics can show
        # "tyre_pressure stopped flowing on 2026-06-01" without us having
        # to wrap every parser branch in a context manager.
        if isinstance(raw, dict):
            self._note_parser_job(
                "charging", present=isinstance(raw.get("charging"), dict),
            )
            self._note_parser_job(
                "climatisation",
                present=isinstance(raw.get("climatisation"), dict),
            )
            self._note_parser_job(
                "oil_level", present=isinstance(raw.get("oilLevel"), dict),
            )
            self._note_parser_job(
                "tyre_pressure",
                present=isinstance(raw.get("tyrePressure"), dict),
            )
            self._note_parser_job(
                "auxiliary_heating",
                present=isinstance(raw.get("auxiliaryHeating"), dict),
            )
            self._note_parser_job(
                "service_care",
                present=isinstance(raw.get("vehicleHealthInspection"), dict),
            )
            self._note_parser_job(
                "door_lock",
                present=isinstance(
                    self._val(raw, "access", "accessStatus", "value"),
                    dict,
                ),
            )

        # ── Model name from vehicles list (nickname set in app) ────────────────
        meta = getattr(self, "_vehicle_metadata", {}).get(vin, {})
        if meta.get("model"):
            d.model = meta["model"]
        # v1.10.1 (#58) — safe_int. The model_year metadata sometimes
        # arrives as a 4-digit string and sometimes as int depending on
        # how the auth flow normalised the user profile JSON.
        d.model_year = safe_int(meta.get("model_year"), default=d.model_year)

        # ── Charging ──────────────────────────────────────────────────────────
        d.charging_state = v(raw, "charging", "chargingStatus", "value", "chargingState")
        # v2.0.1 (#131 follow-up) — defensive: keep is_charging None
        # when charging_state is missing (preserves "unknown" semantics).
        if isinstance(d.charging_state, str):
            d.is_charging = d.charging_state.upper() == "CHARGING"
        d.charging_power_kw = v(raw, "charging", "chargingStatus", "value", "chargePower_kW")
        d.charging_rate_kmh = v(raw, "charging", "chargingStatus", "value", "chargeRate_kmph")

        # v2.10.0 - real-time (instant) charge rate, distinct from the
        # averaged chargeRate_kmph above. The CARIAD BFF ships this
        # under different keys across firmware generations; field-name
        # variants tried defensively. None when the firmware does not
        # expose a separate instant rate, in which case the existing
        # charging_rate_kmh remains the only signal.
        actual_rate = (
            v(raw, "charging", "actualChargeRate", "value")
            or v(raw, "charging", "chargingStatus", "value", "actualChargeRate")
            or v(raw, "charging", "chargingStatus", "value", "instantChargeRate_kW")
        )
        if isinstance(actual_rate, (int, float)):
            d.actual_charge_rate_kw = float(actual_rate)

        # v2.10.0 - Audi-only charging port LED color. Audi vehicles
        # ship a coloured LED ring around the charge port that signals
        # charging state to bystanders. The CARIAD BFF surfaces the
        # current colour string under several paths; defensive lookup
        # since not all Audi models report it (PPE Q6/A6 e-tron yes,
        # older B9 A4 no).
        # v2.11.0 (audi audit): consolidated with the post-block
        # ``ledColor`` write below into a single defensive chain so
        # the second assignment doesn't clobber a valid value with
        # None on PPE firmware. ``ledColor`` is the canonical upstream
        # key (audi_connect_ha); the three plugLedColor variants are
        # our scout-derived fallbacks for older / PPE shape variance.
        led_color = (
            v(raw, "charging", "plugStatus", "value", "ledColor")
            or v(raw, "access", "accessStatus", "value", "plugLedColor")
            or v(raw, "charging", "plugStatus", "value", "plugLedColor")
            or v(raw, "charging", "chargingStatus", "value", "plugLedColor")
        )
        if isinstance(led_color, str) and led_color:
            d.plug_led_color = led_color

        # v1.27.2 — scout #181 (Audi): pending charging-settings change requests.
        # Surfaced as a count diagnostic so users can verify their
        # putChargingSettings POSTs actually queued. Empty list = idle.
        pending = v(raw, "charging", "chargingSettings", "requests")
        if isinstance(pending, list):
            d.charging_settings_pending = len(pending)

        # v2.2.3 — scout #268 (VW EU arvcer, 2026-05-21): mirror of the
        # above pattern for ``charging.chargingStatus.requests`` (start/
        # stop charging commands queued on the chargingStatus side, vs.
        # putChargingSettings on the chargingSettings side). Same shape
        # ``[1 items]`` observed in the scout-report. Surfaced as
        # ``charging_status_pending`` so users can verify their
        # ``vag_connect.start_charging`` / ``stop_charging`` requests
        # actually queued at the backend. Defensive list-check keeps
        # the field None when the leaf is absent (phantom-gate honest).
        status_pending = v(raw, "charging", "chargingStatus", "requests")
        if isinstance(status_pending, list):
            d.charging_status_pending = len(status_pending)

        # v2.15.8 — scout #583 (Audi): third charging-side ``.requests``
        # sibling — ``charging.chargeMode.requests``. The chargeMode sub-job
        # gained its own pending-requests queue (mirror of chargingSettings /
        # chargingStatus): queued chargeMode-change POSTs (manual <-> timer).
        # Same ``[1 items]`` list shape — surfaced as a count so users can
        # verify a chargeMode change actually queued. None when leaf absent.
        mode_pending = v(raw, "charging", "chargeMode", "requests")
        if isinstance(mode_pending, list):
            d.charging_mode_pending = len(mode_pending)

        # v2.17.5 — fourth *.requests sibling: batteryChargingCare.
        # chargingCareSettings.requests counts queued battery-care changes
        # (we already parse batteryCareMode/batteryCareTargetSoc from this
        # container). Same [N items] count diagnostic; None when leaf absent.
        care_pending = v(
            raw, "batteryChargingCare", "chargingCareSettings", "requests"
        )
        if isinstance(care_pending, list):
            d.charging_care_pending = len(care_pending)

        # v2.18.0 — Scout #799: queued charge-PROFILE changes. Same [N items]
        # count diagnostic as the *_pending family; None when the leaf is absent.
        profiles_pending = v(raw, "automation", "chargingProfiles", "requests")
        if isinstance(profiles_pending, list):
            d.charging_profiles_pending = len(profiles_pending)

        # v2.18.0 — Scout #801: queued climate-TIMER schedule changes (distinct
        # from climatisation start/stop, which is climatisationStatus.requests).
        timers_pending = v(
            raw, "climatisationTimers", "climatisationTimersStatus", "requests"
        )
        if isinstance(timers_pending, list):
            d.climatisation_timers_pending = len(timers_pending)

        # v2.3.0 — scout #264 (Audi moltke69 2026-05-19) — route-aware
        # smart charging fields. The Cariad-BFF backend ships a
        # navigation-aware SoC target (e.g. "charge until you have
        # enough for the next planned destination") and the companion
        # ETA. Distinct semantic from the static ``target_soc_pct`` /
        # ``remaining_charge_time_min`` siblings — kept as separate
        # entities so dashboards can show both ("static target: 90%
        # vs. nav target: 65%"). Defensive int-cast: backend ships
        # raw ints in Audi tests, but Skoda firmware has previously
        # surfaced floats on similar fields → safe-int handles both.
        nav_target = v(raw, "charging", "batteryStatus", "value", "navigationTargetSOC_pct")
        if isinstance(nav_target, (int, float)):
            d.nav_target_soc_pct = int(nav_target)
        nav_eta = v(raw, "charging", "chargingStatus", "value", "remainingChargingTimeNavigation_min")
        if isinstance(nav_eta, (int, float)):
            d.remaining_charge_time_nav_min = int(nav_eta)

        # v2.11.0: ``ledColor`` extraction consolidated into the
        # defensive chain at the top of this section so a second
        # unconditional write doesn't clobber a valid PPE plugLedColor.
        ext_power = v(raw, "charging", "plugStatus", "value", "externalPower")
        if isinstance(ext_power, str):
            d.external_power_available = ext_power.lower() == "available"

        # v1.26.0 Welle-6 Feature Backlog (#173) — Battery-Care for VW EU/Audi.
        # Skoda + CUPRA/SEAT have these via own paths since v1.17.5; VW EU/Audi
        # finally exposed via Cariad-BFF (paths from scout reports
        # #144/#145/#146/#147 — were silenced in v1.19.3, now wired as features).
        # v2.11.0 (volkswagencarnet vw_const source-verified): the
        # canonical parent block is `batteryChargingCare`, not
        # `charging`. Pre-v2.11.0 we read `charging.chargingCareSettings`
        # FIRST and the dedicated batteryChargingCare job (already in
        # _SELECTIVE_STATUS_JOBS) was a fallback - flipped the order
        # so the canonical source wins.
        care_mode = (
            v(raw, "batteryChargingCare", "chargingCareSettings", "value", "batteryCareMode")
            or v(raw, "charging", "chargingCareSettings", "value", "batteryCareMode")
        )
        if isinstance(care_mode, str):
            up = care_mode.upper()
            if up in ("ACTIVATED", "ACTIVE", "ON", "TRUE"):
                d.battery_care_enabled = True
            elif up in ("DEACTIVATED", "INACTIVE", "OFF", "FALSE"):
                d.battery_care_enabled = False
        care_target = (
            v(raw, "batteryChargingCare", "chargingCareSettings", "value", "batteryCareTargetSoc")
            or v(raw, "charging", "chargingCareSettings", "value", "batteryCareTargetSoc")
        )
        d.battery_care_target_soc_pct = safe_int(care_target)
        # v2.15.1 — flat `batteryCareTargetSOC_pct` is a FALLBACK ONLY behind the
        # canonical batteryChargingCare path above. Only fill it when that path
        # left the field None — do NOT double-map / clobber a real value.
        if d.battery_care_target_soc_pct is None:
            _bcare_flat = _find_flat(raw, "batteryCareTargetSOC_pct")
            d.battery_care_target_soc_pct = safe_int(_bcare_flat)

        # v1.26.0 — Auto-Unlock plug when charged. From scout #144 VW ID.4 Pro.
        auto_unlock_raw = v(raw, "charging", "chargingSettings", "value", "autoUnlockPlugWhenCharged")
        if isinstance(auto_unlock_raw, str):
            up = auto_unlock_raw.upper()
            if up in ("PERMANENT", "ON", "ACTIVATED", "TRUE", "YES"):
                d.auto_unlock_when_charged = True
            elif up in ("OFF", "DEACTIVATED", "FALSE", "NO"):
                d.auto_unlock_when_charged = False

        # v1.26.0 — Next-Charging-Timer info (read-side complement to v1.16.0
        # write-side). From scout #144/#145/#146/#147 (3-user convergence).
        # v2.15.4 (#530 audi) — some Audi firmware ships the same two fields
        # under a DIFFERENT container: ``chargingProfiles.chargingProfilesStatus
        # .value.nextChargingTimer.{id,targetSOCreachable}`` instead of the
        # ``automation.chargingProfiles.value.nextChargingTimer.*`` path. Keep
        # the automation path PRIMARY; the chargingProfilesStatus container is a
        # FALLBACK (first-non-null wins). Same model fields/entities/i18n.
        nct_id = v(raw, "automation", "chargingProfiles", "value", "nextChargingTimer", "id")
        if nct_id is None:
            nct_id = v(
                raw, "chargingProfiles", "chargingProfilesStatus", "value",
                "nextChargingTimer", "id",
            )
        d.next_charging_timer_id = safe_int(nct_id)
        nct_target = v(
            raw, "automation", "chargingProfiles", "value",
            "nextChargingTimer", "targetSOCreachable",
        )
        if nct_target is None:
            nct_target = v(
                raw, "chargingProfiles", "chargingProfilesStatus", "value",
                "nextChargingTimer", "targetSOCreachable",
            )
        if isinstance(nct_target, str) and nct_target:
            d.next_charging_timer_target_soc_reachable = nct_target

        # v1.10.1 (#58) — safe_int. New CARIAD firmware shipped this as
        # a stringified decimal at least once — see myskoda #503.
        remaining_min = safe_int(
            v(raw, "charging", "chargingStatus", "value", "remainingChargingTimeToComplete_min")
        )
        if remaining_min is not None:
            d.charge_complete_eta = datetime.now(tz=timezone.utc) + timedelta(minutes=remaining_min)

        d.battery_soc = v(raw, "charging", "batteryStatus", "value", "currentSOC_pct")
        # v1.10.0 (#94) — ``range_km`` headline assignment moved to the
        # consolidated PHEV-range block further down. Reading the battery
        # range here would clobber the per-engine logic for hybrids where
        # the battery range and the engine block disagree.

        # v2.8.0 — Pydantic dual-write scaffold removed (task #44 dead-
        # weight cleanup). The v2.2.0 Phase 5b foundation had a single
        # call site here whose return value was discarded, and its
        # import-time site-packages walk triggered "Detected blocking
        # call to listdir" warnings on every fresh HA startup. The
        # scaffold never grew past one model so it was removed rather
        # than expanded.

        plug_state = v(raw, "charging", "plugStatus", "value", "plugConnectionState")
        # v2.0.1 (#131 follow-up) — defensive parsing.
        if isinstance(plug_state, str):
            d.plug_connected = plug_state.upper() == "CONNECTED"
            # v2.17.5 (#770) — don't surface the CARIAD 'invalid'/'unsupported'
            # sentinel as a raw plug-state text sensor (the boolean above is
            # already safe via the positive == CONNECTED test). Mirror the
            # climatisation 'invalid' handling and keep the text state unknown.
            d.plug_state = (
                None
                if plug_state.upper() in ("INVALID", "UNSUPPORTED")
                else plug_state
            )
        else:
            d.plug_state = plug_state
        # v2.0.1 (#131 follow-up) — defensive parsing.
        plug_lock = v(raw, "charging", "plugStatus", "value", "plugLockState")
        if isinstance(plug_lock, str):
            d.connector_locked = plug_lock.upper() == "LOCKED"

        d.target_soc = v(raw, "charging", "chargingSettings", "value", "targetSOC_pct")
        # v2.11.0 (volkswagencarnet PR #328, merged 2026-06-01) - CARIAD-BFF
        # now exposes a dedicated chargeMode sub-job under selectivestatus
        # charging block. preferredChargeMode + availableChargeModes are
        # real backend additions (independent of the auth crisis). Values
        # observed: "manual", "timer", "preferredChargingTimes",
        # "timerChargingWithClimatisation".
        preferred = v(raw, "charging", "chargeMode", "value", "preferredChargeMode")
        if isinstance(preferred, str) and preferred:
            d.charging_preferred_mode = preferred
        available = v(raw, "charging", "chargeMode", "value", "availableChargeModes")
        if isinstance(available, list):
            d.available_charge_modes = [
                m for m in available if isinstance(m, str) and m
            ]
        d.charge_mode = (
            v(raw, "charging", "chargingStatus", "value", "chargeMode")
            or v(raw, "charging", "chargeMode", "value")
        )
        d.min_soc = v(raw, "charging", "chargingSettings", "value", "minChargeLimit_pct")
        # v1.10.1 (#58) — safe_float for max charge current too. The
        # ``_A`` field is a clean integer in #90's Live-Dump (16) but the
        # legacy enum form was a string ("MAXIMUM"); this normalises.
        max_ac = safe_float(
            v(raw, "charging", "chargingSettings", "value", "maxChargeCurrentAC_A")
        )
        if max_ac is not None:
            d.max_charge_current = max_ac
        d.auto_unlock_charge = (
            v(raw, "charging", "chargingSettings", "value", "autoUnlockPlugWhenChargedAC") == "ON"
        )

        charging_type = v(raw, "charging", "chargingStatus", "value", "chargeType")
        d.charging_type = charging_type

        # ── Drivetrain detection ───────────────────────────────────────────────
        # v1.11.1 (#96 root-cause fix) — VW Golf 7 GTE 2015 + Passat
        # B7/B8 GTE return ``fuelStatus.rangeStatus = {"error": ...}``
        # instead of the ``.value.primaryEngine/.secondaryEngine`` block.
        # Without these fallback paths, ``has_combustion`` stayed False
        # even though ``measurements.fuelLevelStatus.value.primaryEngineType
        # = "gasoline"`` was published — and the data-present gate then
        # blocked both the ``fuel_level`` and ``combustion_range_km``
        # entities. Issue #96 acceptance criteria documented this exactly
        # (evcc-io/evcc#19045 trace shows the same pattern on Passat GTE).
        #
        # Fix: collect engine types from FOUR sources (was 2):
        #   1. fuelStatus.rangeStatus.value.primaryEngine.type
        #   2. fuelStatus.rangeStatus.value.secondaryEngine.type
        #   3. measurements.fuelLevelStatus.value.primaryEngineType  ← NEW
        #   4. measurements.fuelLevelStatus.value.secondaryEngineType  ← NEW
        # AND treat ``carType="hybrid"`` as both battery+combustion (was
        # only matching substring "electric"/"gasoline"/"diesel"/"gas",
        # which missed pure "hybrid" — verified live on Passat GTE).
        primary_engine = v(raw, "fuelStatus", "rangeStatus", "value", "primaryEngine", "type")
        secondary_engine = v(raw, "fuelStatus", "rangeStatus", "value", "secondaryEngine", "type")
        # New: also read measurements engine-type fields. Same backend
        # value, different path — populated even when fuelStatus errors.
        ms_primary = v(raw, "measurements", "fuelLevelStatus", "value", "primaryEngineType")
        ms_secondary = v(raw, "measurements", "fuelLevelStatus", "value", "secondaryEngineType")
        # carType can live under either fuelStatus or measurements.
        car_type = (
            v(raw, "fuelStatus", "rangeStatus", "value", "carType")
            or v(raw, "measurements", "fuelLevelStatus", "value", "carType")
        )

        electric_types = {"electric", "ev"}
        combustion_types = {"gasoline", "petrol", "diesel", "gas", "cng", "lpg"}

        # Iterate ALL four engine-type fields; whichever the API publishes
        # is enough to set the drivetrain flag.
        for engine_type_raw in (primary_engine, secondary_engine, ms_primary, ms_secondary):
            if not engine_type_raw:
                continue
            lower = str(engine_type_raw).lower()
            if lower in electric_types:
                d.has_battery = True
            if lower in combustion_types:
                d.has_combustion = True

        if car_type:
            lower = str(car_type).lower()
            if "electric" in lower:
                d.has_battery = True
            if any(x in lower for x in ("gasoline", "petrol", "diesel", "gas")):
                d.has_combustion = True
            # v1.11.1 (#96) — pure ``hybrid`` / ``phev`` / ``plug-in
            # hybrid`` carType means BOTH drivetrains. Pre-1.11.1 missed
            # this and Passat GTE with carType="hybrid" but no engine
            # detail blocks ended up has_combustion=False.
            if lower in {"hybrid", "phev", "plug-in hybrid", "pluginhybrid", "plug_in_hybrid"}:
                d.has_battery = True
                d.has_combustion = True

        # v2.2.1 Phase 8 PR #2 — cross-brand engine-metadata expansion.
        # The variables ``ms_primary`` / ``ms_secondary`` / ``car_type``
        # are already read above for drivetrain-flag derivation. Now ALSO
        # populate the explicit fields that Skoda (PR #6/#220, PR #1
        # today) and CUPRA/SEAT (PR #3/#18) already use — same dataclass
        # fields, just expanded brand coverage. Audi inherits via
        # ``AudiClient(VWEUClient)`` automatically.
        #
        # Priority order for the type fields: fuelStatus block (richer
        # backend metadata) → measurements fallback (always populated).
        primary_eng = primary_engine or ms_primary
        if isinstance(primary_eng, str) and primary_eng:
            d.primary_engine_type = primary_eng
        secondary_eng = secondary_engine or ms_secondary
        if isinstance(secondary_eng, str) and secondary_eng:
            d.secondary_engine_type = secondary_eng
        if isinstance(car_type, str) and car_type:
            d.car_type = car_type

        # v2.2.1 Phase 8 PR #2/#4 — per-engine-block fuel level walk.
        # Walks both engine blocks and assigns:
        # - `secondary_engine_fuel_level_pct` from the combustion side
        #   of a PHEV (PR #2 original — Skoda parity).
        # - `primary_engine_fuel_level_pct` from the combustion side
        #   when it's the primary engine position (PR #4 cross-brand —
        #   Skoda already has this from driving-range path; this gives
        #   ICE-only VW/Audi the same field).
        #
        # The primary/secondary assignment is by POSITION in the
        # engine block, not by drivetrain. Modern PHEVs put electric
        # as primary + combustion as secondary; older Golf GTE 2015
        # firmware flipped it; ICE-only cars only have primary.
        for engine_path in (
            ("fuelStatus", "rangeStatus", "value", "primaryEngine"),
            ("fuelStatus", "rangeStatus", "value", "secondaryEngine"),
        ):
            engine_block = v(raw, *engine_path)
            if not isinstance(engine_block, dict):
                continue
            etype = (engine_block.get("type") or "").lower()
            if etype not in combustion_types:
                continue
            fuel_pct = safe_int(engine_block.get("currentFuelLevel_pct"))
            if fuel_pct is None:
                continue
            position = engine_path[-1]
            if position == "primaryEngine":
                d.primary_engine_fuel_level_pct = fuel_pct
            elif position == "secondaryEngine":
                d.secondary_engine_fuel_level_pct = fuel_pct

        d.is_electric = d.has_battery and not d.has_combustion
        d.is_hybrid = d.has_battery and d.has_combustion

        # ── Fuel / range ──────────────────────────────────────────────────────
        # v1.11.1 (#96 Track D) — fuel_level fallback from the engine
        # block. Older GTE firmware ships ``currentFuelLevel_pct``
        # INSIDE ``primaryEngine`` (when type=gasoline) — confirmed by
        # CarConnectivity log in #96. Try the well-known measurements
        # path first, fall back to whichever engine block is combustion.
        d.fuel_level = v(raw, "measurements", "fuelLevelStatus", "value", "currentFuelLevel_pct")
        if d.fuel_level is None:
            for engine_path in (
                ("fuelStatus", "rangeStatus", "value", "primaryEngine"),
                ("fuelStatus", "rangeStatus", "value", "secondaryEngine"),
            ):
                engine = v(raw, *engine_path)
                if not isinstance(engine, dict):
                    continue
                engine_type = (engine.get("type") or "").lower()
                if engine_type not in combustion_types:
                    continue
                fuel_pct = safe_int(engine.get("currentFuelLevel_pct"))
                if fuel_pct is not None:
                    d.fuel_level = fuel_pct
                    break

        # v1.10.0 (#94) — explicit per-energy-source range fields, plus
        # backward-compatible ``range_km``. Logic order matters:
        #
        # 1. Read the two CARIAD BFF engine blocks. Each carries its own
        #    ``type`` (electric/gasoline/diesel/...) plus its own
        #    ``remainingRange_km``. Older Audi diesels expose
        #    ``measurements.rangeStatus.value.dieselRange`` instead, so
        #    we fall through to that path when the engine blocks are empty.
        # 2. Map by *engine type* not by *position* — primary != electric
        #    forever. A Golf 7 GTE 2015 has primary=gasoline, secondary=
        #    electric in early firmware; modern PHEVs flip them around.
        # 3. ``total_range_km`` is its own field — only set when the API
        #    explicitly publishes it (PHEVs do, pure EVs don't).
        # 4. ``range_km`` (back-compat headline number) prefers electric
        #    for EV/PHEV, otherwise total, otherwise combustion.
        electric_types = {"electric", "ev"}
        combustion_types = {"gasoline", "petrol", "diesel", "gas", "cng", "lpg"}

        for engine_path in (
            ("fuelStatus", "rangeStatus", "value", "primaryEngine"),
            ("fuelStatus", "rangeStatus", "value", "secondaryEngine"),
        ):
            engine = v(raw, *engine_path)
            if not isinstance(engine, dict):
                continue
            engine_type = (engine.get("type") or "").lower()
            engine_range = engine.get("remainingRange_km")
            if engine_range is None:
                continue
            # v1.24.2 (audit): safe_int instead of bare int() try/except
            value = safe_int(engine_range)
            if value is None:
                continue
            if engine_type in electric_types:
                d.electric_range_km = value
            elif engine_type in combustion_types:
                d.combustion_range_km = value

        # Older Audi models (S6 TDI 2021, A6 e-tron, etc.) expose only the
        # combustion range under ``measurements.rangeStatus.value.dieselRange``
        # / ``gasolineRange`` — no ``fuelStatus.rangeStatus.value`` block.
        # Verified live on Audi S6 C8 2021 (#91).
        if d.combustion_range_km is None:
            for ms_field in ("dieselRange", "gasolineRange"):
                ms_val = v(raw, "measurements", "rangeStatus", "value", ms_field)
                if ms_val is None:
                    continue
                # CARIAD-BFF returns either a scalar km value OR a wrapped
                # ``{"distanceInKm": int}`` shape (the same dual-form shape
                # Skoda uses for its electricRange/combustionRange blocks).
                if isinstance(ms_val, dict):
                    ms_val = ms_val.get("distanceInKm")
                # v1.24.2 (audit): safe_int handles None + non-numeric
                parsed = safe_int(ms_val)
                if parsed is not None:
                    d.combustion_range_km = parsed

        # Total range — from explicit field if present.
        # v1.11.1 (#96 Track C) — older GTE firmware fails fuelStatus
        # with a ``Bad Gateway`` error object but still publishes total
        # range under ``measurements.rangeStatus.value.totalRange_km``
        # (verified via evcc-io/evcc#19045 Passat GTE trace). Both paths
        # tried in order — fuelStatus preferred when it works, falls
        # through to measurements when it doesn't.
        total_range = (
            v(raw, "fuelStatus", "rangeStatus", "value", "totalRange_km")
            or v(raw, "measurements", "rangeStatus", "value", "totalRange_km")
        )
        if total_range is not None:
            d.total_range_km = safe_int(total_range)

        # Back-compat ``range_km`` headline. Preference order matches
        # users' intuitive expectation — EVs/PHEVs see battery range as
        # primary, ICE see combustion or total.
        # v2.11.0 (volkswagencarnet source-verified): also try
        # `measurements.rangeStatus.value.electricRange` - some pure-EV
        # ID.x firmware ships only this leaf and our pre-v2.11.0 code
        # missed it.
        battery_range = (
            v(raw, "charging", "batteryStatus", "value", "cruisingRangeElectric_km")
            or v(raw, "measurements", "rangeStatus", "value", "electricRange")
        )
        if d.electric_range_km is None and battery_range is not None:
            # v1.24.2 (audit): safe_int — handles None/string/float defensively
            d.electric_range_km = safe_int(battery_range)
        if d.has_battery and d.electric_range_km is not None:
            d.range_km = d.electric_range_km
        elif d.total_range_km is not None:
            d.range_km = d.total_range_km
        elif d.combustion_range_km is not None:
            d.range_km = d.combustion_range_km

        adblue = v(raw, "measurements", "rangeStatus", "value", "adBlueRange")
        d.adblue_range_km = safe_int(adblue)

        # ── Measurements ──────────────────────────────────────────────────────
        d.odometer_km = v(raw, "measurements", "odometerStatus", "value", "odometer")
        # v2.7.0b11 — outside temp ships under different key variants
        # depending on model year and brand. Try the canonical Cariad
        # name first, then Audi MY24+ variants observed in user logs.
        # All values are Kelvin; convert to Celsius after we find one.
        outside_raw = (
            v(raw, "measurements", "outsideTemperatureStatus", "value", "outsideTemperature_K")
            or v(raw, "measurements", "outsideTemperatureStatus", "value", "temperatureOutside_K")
            or v(raw, "measurements", "temperatureOutsideStatus", "value", "outsideTemperature_K")
            or v(raw, "measurements", "temperatureOutsideStatus", "value", "temperatureOutside_K")
        )
        outside_k = safe_float(outside_raw)
        d.outside_temp = round(outside_k - 273.15, 1) if outside_k is not None else None

        bat_min = v(raw, "measurements", "temperatureBatteryStatus", "value", "temperatureHvBatteryMin_K")
        bat_min_k = safe_float(bat_min)
        d.battery_temp = round(bat_min_k - 273.15, 1) if bat_min_k is not None else None

        # v2.2.0 Phase 7 PR #1 — HV battery max-temperature companion
        # to existing min (above). Both Celsius after K→C conversion.
        # Power-users monitoring thermal balance during DC fast-charging
        # want BOTH extremes, not just the min — the spread is the
        # diagnostic signal. Defensive: same safe_float + None guard.
        bat_max = v(raw, "measurements", "temperatureBatteryStatus", "value", "temperatureHvBatteryMax_K")
        bat_max_k = safe_float(bat_max)
        d.battery_temp_max = round(bat_max_k - 273.15, 1) if bat_max_k is not None else None

        # v2.10.0 Group A - HV battery min/max temperature from the
        # ``charging.batteryStatus.value`` block. Newer Born / Q4 e-tron
        # firmware ships ``minTemperature_K`` and ``maxTemperature_K``
        # under the charging block in addition to (or instead of) the
        # ``measurements.temperatureBatteryStatus`` block used above.
        # field-name variants tried defensively. Kelvin-to-Celsius
        # only when the raw value is > 200 (heuristic to distinguish
        # Kelvin from already-Celsius readings).
        hv_min_raw = (
            v(raw, "charging", "batteryStatus", "value", "minTemperature_K")
            or v(raw, "charging", "batteryStatus", "value", "minimumTemperature_K")
            or v(raw, "charging", "batteryStatus", "value", "temperatureMin_K")
        )
        hv_min_k = safe_float(hv_min_raw)
        if hv_min_k is not None:
            d.hv_battery_min_temperature_c = round(
                hv_min_k - 273.15 if hv_min_k > 200 else hv_min_k, 1,
            )
        hv_max_raw = (
            v(raw, "charging", "batteryStatus", "value", "maxTemperature_K")
            or v(raw, "charging", "batteryStatus", "value", "maximumTemperature_K")
            or v(raw, "charging", "batteryStatus", "value", "temperatureMax_K")
        )
        hv_max_k = safe_float(hv_max_raw)
        if hv_max_k is not None:
            d.hv_battery_max_temperature_c = round(
                hv_max_k - 273.15 if hv_max_k > 200 else hv_max_k, 1,
            )

        # v2.10.0 Group A - distinguish user-requested AC charge current
        # setting from the actual deliverable amperage the wallbox +
        # cable can support. Existing ``max_charge_current`` stays
        # populated from ``maxChargeCurrentAC_A`` for backward compat;
        # the two new fields below sit alongside as explicit setting /
        # actual pair. field-name variants tried defensively.
        ac_setting = (
            v(raw, "charging", "chargingSettings", "value", "maxChargeCurrentAC_setting")
            or v(raw, "charging", "chargingSettings", "value", "maxChargeCurrentACSetting")
            or v(raw, "charging", "chargingSettings", "value", "maxChargeCurrentAC_set")
        )
        ac_setting_int = safe_int(ac_setting)
        if ac_setting_int is not None:
            d.charge_max_ac_setting = ac_setting_int
        ac_ampere = (
            v(raw, "charging", "chargingSettings", "value", "maxChargeCurrentAC")
            or v(raw, "charging", "chargingStatus", "value", "maxChargeCurrentAC")
            or v(raw, "charging", "chargingSettings", "value", "maxChargeCurrentAC_actual")
        )
        ac_ampere_int = safe_int(ac_ampere)
        if ac_ampere_int is not None:
            d.charge_max_ac_ampere = ac_ampere_int

        # v2.10.0 Group A - Born MY24+ AC connector auto-release.
        # Field-name variants tried defensively. The boolean flag
        # surfaces under several names across firmware generations;
        # the enum ``autoReleaseState`` lives only on plugStatus.
        auto_release_raw = (
            v(raw, "charging", "chargingSettings", "value", "autoReleaseAcConnector")
            or v(raw, "charging", "plugStatus", "value", "autoUnlockPlugWhenCharged")
            or v(raw, "charging", "chargingSettings", "value", "autoReleaseAcConnectorEnabled")
        )
        if isinstance(auto_release_raw, bool):
            d.auto_release_ac_connector = auto_release_raw
        elif isinstance(auto_release_raw, str):
            up = auto_release_raw.upper()
            if up in ("PERMANENT", "ON", "ACTIVATED", "TRUE", "YES", "ENABLED"):
                d.auto_release_ac_connector = True
            elif up in ("OFF", "DEACTIVATED", "FALSE", "NO", "DISABLED"):
                d.auto_release_ac_connector = False
        auto_release_state = (
            v(raw, "charging", "plugStatus", "value", "autoReleaseState")
            or v(raw, "charging", "chargingStatus", "value", "autoReleaseState")
        )
        if isinstance(auto_release_state, str) and auto_release_state:
            d.auto_release_ac_connector_state = auto_release_state

        # v2.10.0 Group A - battery-preservation flag distinct from
        # battery_care. Born / ID.x setting that limits charging
        # dynamics (current ramp + thermal pre-conditioning) to
        # preserve cell longevity. field-name variants tried
        # defensively.
        opt_bat_raw = (
            v(raw, "charging", "chargingSettings", "value", "optimisedBatteryUse")
            or v(raw, "charging", "chargingSettings", "value", "optimizedBatteryUse")
            or v(raw, "charging", "chargingCareSettings", "value", "optimisedBatteryUse")
        )
        if isinstance(opt_bat_raw, bool):
            d.optimised_battery_use = opt_bat_raw
        elif isinstance(opt_bat_raw, str):
            up = opt_bat_raw.upper()
            if up in ("ACTIVATED", "ACTIVE", "ON", "TRUE", "ENABLED"):
                d.optimised_battery_use = True
            elif up in ("DEACTIVATED", "INACTIVE", "OFF", "FALSE", "DISABLED"):
                d.optimised_battery_use = False

        # v2.10.0 Group A - active ventilation (cabin air-circulation
        # without heating / cooling). Surfaces under the climatisation
        # block as a sibling status enum + remaining time. field-name
        # variants tried defensively. State is one of ``off`` /
        # ``running`` / ``finished``.
        vent_state = (
            v(raw, "climatisation", "climatisationStatus", "value", "ventilationState")
            or v(raw, "climatisation", "ventilationStatus", "value", "ventilationState")
            or v(raw, "climatisation", "climatisationStatus", "value", "activeVentilationState")
        )
        if isinstance(vent_state, str) and vent_state:
            d.active_ventilation_state = vent_state
        vent_remaining = (
            v(raw, "climatisation", "climatisationStatus", "value", "ventilationRemainingTimeInMinutes")
            or v(raw, "climatisation", "climatisationStatus", "value", "ventilationRemainingTime_min")
            or v(raw, "climatisation", "ventilationStatus", "value", "remainingTime_min")
        )
        vent_remaining_int = safe_int(vent_remaining)
        if vent_remaining_int is not None:
            d.active_ventilation_remaining_time_min = vent_remaining_int

        # v2.10.0 Group A - rear sunroof + Cabrio roof cover. Both are
        # window-array entries on the access.accessStatus.value.windows
        # block. ``sunRoofRear`` covers panoramic rear glass roofs;
        # ``roofCover`` covers convertible tops. Two paths checked:
        # (1) the existing ``windows_individual`` dict populated by the
        # access block walker above, (2) direct lookup against the
        # raw windows list as a fallback for firmware shapes the
        # walker did not capture.
        windows_dict = d.windows_individual or {}
        for key, target in (
            ("sunRoofRear", "sunroof_rear_closed"),
            ("sun_roof_rear", "sunroof_rear_closed"),
            ("roofCover", "roof_cover_closed"),
            ("roof_cover", "roof_cover_closed"),
        ):
            if key in windows_dict:
                # windows_individual maps id -> "open" boolean (True = open).
                # Closed = NOT open.
                setattr(d, target, not windows_dict[key])
        # Direct fallback: read the raw windows list, look for the
        # named entries, normalise status string against "closed".
        raw_windows = v(raw, "access", "accessStatus", "value", "windows") or []
        if isinstance(raw_windows, list):
            for w in raw_windows:
                if not isinstance(w, dict):
                    continue
                name = w.get("name") or w.get("location") or ""
                if not isinstance(name, str):
                    continue
                name_l = name.lower()
                status_raw = w.get("status")
                if isinstance(status_raw, list) and status_raw:
                    status_raw = status_raw[0]
                if isinstance(status_raw, dict):
                    status_raw = status_raw.get("value") or status_raw.get("status")
                if not isinstance(status_raw, str):
                    continue
                # v2.18.1 (#810, @lucson) — only a real open/closed status is
                # meaningful. Option-dependent roof parts on a car without one
                # report a non-open/closed sentinel ("unsupported"/"invalid");
                # treating that as "not closed" wrote False and rendered the
                # entity as 'open'. Skip so the descriptor stays None and the
                # phantom-entity guard (_DATA_PRESENT_REQUIRED) suppresses it.
                status_l = status_raw.lower()
                if status_l not in ("open", "closed"):
                    continue
                is_closed = status_l == "closed"
                if "sunroofrear" in name_l.replace("_", "") or name_l == "sun_roof_rear":
                    if d.sunroof_rear_closed is None:
                        d.sunroof_rear_closed = is_closed
                elif "roofcover" in name_l.replace("_", "") or name_l == "roof_cover":
                    if d.roof_cover_closed is None:
                        d.roof_cover_closed = is_closed

        # v2.10.0 Group A - 12V health bucket from connectionStatus or
        # the vehicleHealthInspection block. Companion to the v2.4.1
        # T1 ``connection_battery_power_level`` field that reads the
        # same logical signal from a different parent block on
        # other firmware shapes. field-name variants tried defensively.
        bpl = (
            v(raw, "connectionStatus", "batteryPowerLevel")
            or v(raw, "vehicleHealthInspection", "value", "battery12VLevel")
            or v(raw, "vehicleHealthInspection", "maintenanceStatus", "value", "battery12VLevel")
        )
        if isinstance(bpl, str) and bpl:
            d.connection_state_battery_power_level = bpl

        # v1.12.0 (#23) — 12V starter battery voltage. The CARIAD BFF
        # ``lvBattery`` job publishes voltage in volts (decimal, e.g.
        # 12.6 = healthy). Threshold for warning is 11.5 V (matches
        # volkswagencarnet PR #940 + ELM327 readings widely cited as
        # the "go to garage soon" line). Below 10.5 V the modem can't
        # keep itself awake and the integration will silently fail to
        # poll — that's the symptom users keep blaming on us.
        voltage_raw = v(raw, "lvBattery", "lvBatteryStatus", "value", "batteryVoltage_V")
        d.voltage_12v = safe_float(voltage_raw)
        if d.voltage_12v is not None:
            d.warning_12v_low = d.voltage_12v < 11.5

        # ── v2.0.0 (Big-Bang) — Vehicle alarm (issue #33) ─────────────────────
        # Cariad-BFF surfaces alarm telemetry under access.accessStatus.value.
        # Defensive: only populate when the field is explicitly present so
        # _DATA_PRESENT_REQUIRED in binary_sensor.py / sensor.py keeps
        # phantom entities away from cars that never publish these fields.
        alarm_raw = v(raw, "access", "accessStatus", "value", "vehicleAlarm")
        if isinstance(alarm_raw, str):
            d.alarm_active = alarm_raw.upper() == "ALARM"
        siren_raw = v(raw, "access", "accessStatus", "value", "siren")
        if isinstance(siren_raw, str):
            d.siren_active = siren_raw.upper() == "ACTIVE"
        last_alarm = (
            v(raw, "access", "accessStatus", "value", "lastAlarmAt")
            or v(raw, "access", "accessStatus", "value", "lastAlarmTimestamp")
        )
        if last_alarm:
            d.last_alarm_at = last_alarm

        # v2.10.0 (#389 scout 2026-06-02) — pending-action request list.
        # CARIAD BFF ships ``access.accessStatus.requests`` (and
        # sometimes ``access.accessStatus.value.requests``) when a
        # lock/unlock/climate command was dispatched and the vehicle
        # has not yet confirmed completion. Expose the most-recent
        # entry as 3 sensors so HA automations can wait for action
        # acknowledgement instead of guessing with a fixed sleep.
        requests_list = (
            v(raw, "access", "accessStatus", "requests")
            or v(raw, "access", "accessStatus", "value", "requests")
        )
        if isinstance(requests_list, list) and requests_list:
            # Field names observed: ``requestId``/``id``, ``operation``/
            # ``operationCode``/``type``, ``status``/``state``. Defensive
            # multi-key lookup mirrors the rest of vw_eu.py.
            latest = requests_list[-1] if isinstance(requests_list[-1], dict) else {}
            rid = (
                latest.get("requestId")
                or latest.get("id")
                or latest.get("requestID")
            )
            rop = (
                latest.get("operation")
                or latest.get("operationCode")
                or latest.get("type")
            )
            rst = (
                latest.get("status")
                or latest.get("state")
            )
            if isinstance(rid, str):
                d.pending_action_id = rid
            if isinstance(rop, str):
                d.pending_action_type = rop
            if isinstance(rst, str):
                d.pending_action_status = rst

        # ── Access / doors / windows ──────────────────────────────────────────
        # v2.0.1 (#131 user-reported follow-up) — defensive parsing.
        # Previously: ``d.doors_locked = X == "LOCKED"`` always assigned
        # True or False, even when X was None (missing field, .error
        # envelope, backend hiccup). Combined with the old
        # ``doors_locked: bool = False`` dataclass default that made HA
        # falsely show "Unlocked" for actually-locked cars during any
        # parser-miss scenario. New shape: only assign when the source
        # field is an actual string; otherwise leave the dataclass
        # default ``None`` so the entity stays "unknown" instead of
        # showing wrong state. Same fix applied to ``doors_open`` and
        # ``windows_open`` below.
        lock_raw = v(raw, "access", "accessStatus", "value", "doorLockStatus")
        if isinstance(lock_raw, str):
            d.doors_locked = lock_raw.upper() == "LOCKED"

        # v2.7.0b10 — Audi parity fix. The old code only built the
        # per-door / per-window breakdown when overallStatus was
        # "UNSAFE". On a locked car (overallStatus == "SAFE", which is
        # the common case) the parser bailed out without populating
        # ``doors_individual`` / ``windows_individual`` / trunk lock,
        # so all the per-position entities (left front door, sun roof,
        # trunk lock, etc) stayed at None and rendered as "Unbekannt"
        # in HA. Audi-connect-ha iterates the arrays unconditionally;
        # that's the right shape. Always walk the doors + windows
        # arrays when they are present; rely on each entry's own
        # status field for the open/closed answer.
        from .._util import safe_get  # noqa: PLC0415
        doors: list[dict[str, Any]] = (
            v(raw, "access", "accessStatus", "value", "doors") or []
        )
        windows: list[dict[str, Any]] = (
            v(raw, "access", "accessStatus", "value", "windows") or []
        )
        overall = v(raw, "access", "accessStatus", "value", "overallStatus")
        if doors:
            d.doors_open = any(
                safe_get(door, "status[0].value") == "open" for door in doors
            )
            d.doors_individual = {
                str(name): safe_get(door, "status[0].value") == "open"
                for door in doors
                if (name := door.get("name")) is not None
            }
            # Trunk lock state lives in the doors array under the
            # entry whose name is "trunk". Backends ship either a
            # top-level ``locked`` boolean or a status entry with
            # value=="locked" — accept both.
            trunk = next(
                (door for door in doors if door.get("name") == "trunk"),
                None,
            )
            if trunk is not None:
                trunk_locked_raw = (
                    trunk.get("locked")
                    if "locked" in trunk
                    else safe_get(trunk, "lockState[0].value")
                )
                if isinstance(trunk_locked_raw, bool):
                    d.trunk_locked = trunk_locked_raw
                elif isinstance(trunk_locked_raw, str):
                    d.trunk_locked = trunk_locked_raw.lower() == "locked"
        elif overall == "SAFE":
            # Backend reported SAFE but didn't enumerate the doors
            # array. Honour the aggregate signal so the entity shows
            # False (closed) instead of Unknown.
            d.doors_open = False

        if windows:
            d.windows_open = any(
                safe_get(w, "status[0].value") == "open" for w in windows
            )
            # v2.18.1 (#810, @lucson) — windows_individual follows the documented
            # ``True == closed`` convention: the same one VagWindowSensor (which
            # inverts for the HA WINDOW device_class) and the EU-Data-Act portal
            # parser already use. Storing ``== "open"`` here (True == open) was the
            # lone outlier and rendered every *closed* window as *open* on Audi /
            # VW-EU cars. Only entries with a real open/closed status are stored; a
            # non-open/closed sentinel (an option-dependent roof on a car without
            # one) is skipped so it can't surface as a phantom window.
            windows_individual: dict[str, bool] = {}
            for w in windows:
                name = w.get("name")
                if name is None:
                    continue
                st = safe_get(w, "status[0].value")
                if not isinstance(st, str) or st.lower() not in ("open", "closed"):
                    continue
                windows_individual[str(name)] = st.lower() == "closed"
            d.windows_individual = windows_individual
        elif overall == "SAFE":
            d.windows_open = False

        # ── Climatisation ─────────────────────────────────────────────────────
        d.climatisation_state = v(raw, "climatisation", "climatisationStatus", "value", "climatisationState")
        # v2.15.0a9 — #442 (nekas123, Audi e-tron): the car can report
        # ``climatisationState = "invalid"`` (a degraded/no-data sentinel — seen
        # when climatisation can't start, e.g. at a low battery level). The old
        # check only treated OFF / CLIMATISATION_STATUS_UNAVAILABLE as inactive,
        # so "invalid" (and any case variant) fell through to active=True — a
        # false positive. Normalise case and treat the no-data sentinels as off.
        _clima = d.climatisation_state
        d.climatisation_active = (
            _clima is not None
            and str(_clima).strip().upper()
            not in ("OFF", "INVALID", "CLIMATISATION_STATUS_UNAVAILABLE", "UNSUPPORTED")
        )
        d.target_temperature = v(raw, "climatisation", "climatisationSettings", "value", "targetTemperature_C")

        # v2.2.3 — scout #272 (VW EU arvcer 2026-05-23): third member
        # of the ``*.requests`` queue-counter family (alongside
        # ``chargingStatus.requests`` and ``chargingSettings.requests``
        # parsed elsewhere in this file). Counts queued
        # ``start_climatisation`` / ``stop_climatisation`` commands at
        # the gateway. Same diagnostic semantic, same defensive
        # list-check, same phantom-honest None when leaf is absent.
        clim_pending = v(raw, "climatisation", "climatisationStatus", "requests")
        if isinstance(clim_pending, list):
            d.climatisation_status_pending = len(clim_pending)

        # v2.4.1 — scout #283 (VW EU Brinki99 2026-05-24): fourth and
        # final member of the ``*.requests`` queue-counter family on
        # the climatisationSettings side. Counts queued
        # ``set_climatisation_temperature`` / ``set_window_heating`` /
        # related settings-update commands at the gateway. Mirrors the
        # ``chargingSettings.requests`` parser from v1.27.2 #181 but
        # on the climate side. Audi inherits via brand-vererbung.
        clim_settings_pending = v(raw, "climatisation", "climatisationSettings", "requests")
        if isinstance(clim_settings_pending, list):
            d.climatisation_settings_pending = len(clim_settings_pending)

        # v2.4.1 — Scout Policy Compliance Audit T1: parse the
        # silenced-but-not-parsed leaves discovered in the v2.4.1 sweep
        # (see docs/SCOUT_POLICY.md). Each was already in EXPECTED_KEYS;
        # we're adding parsers + entities per the new "always parse"
        # policy. All disabled-by-default in sensor.py.
        #
        # HV battery cell temperature.
        bat_temp = v(raw, "charging", "batteryStatus", "value", "temp_C")
        if isinstance(bat_temp, (int, float)):
            d.battery_temp_c = float(bat_temp)
        # Climatisation: per-zone front + battery-only mode.
        cwep = v(raw, "climatisation", "climatisationSettings", "value", "climatisationWithoutExternalPower")
        if isinstance(cwep, bool):
            d.climate_without_external_power = cwep
        zfl = v(raw, "climatisation", "climatisationSettings", "value", "zoneFrontLeftEnabled")
        if isinstance(zfl, bool):
            d.climate_zone_front_left = zfl
        zfr = v(raw, "climatisation", "climatisationSettings", "value", "zoneFrontRightEnabled")
        if isinstance(zfr, bool):
            d.climate_zone_front_right = zfr
        # v2.15.9 (#597 audi Scout) — rear-zone enable siblings. Same
        # selectivestatus climatisationSettings.value.* namespace as the
        # front zones. Rear-zone-capable cars only → field stays None on
        # others (phantom-protected in binary_sensor.py).
        zrl = v(raw, "climatisation", "climatisationSettings", "value", "zoneRearLeftEnabled")
        if isinstance(zrl, bool):
            d.climate_zone_rear_left = zrl
        zrr = v(raw, "climatisation", "climatisationSettings", "value", "zoneRearRightEnabled")
        if isinstance(zrr, bool):
            d.climate_zone_rear_right = zrr
        # v2.16.2 (#671 audi Q6 Scout) — climatisation MODE readback
        # ("comfort" in the wild). Same climatisationSettings.value.*
        # namespace. Read-only diagnostic; data-present gated so cars that
        # omit it never get a phantom "unknown" entity.
        cmode = v(raw, "climatisation", "climatisationSettings", "value", "climatisationMode")
        if isinstance(cmode, str) and cmode:
            d.climate_mode = cmode
        # Climatisation: ETA in minutes from current to target temperature.
        crt = v(raw, "climatisation", "climatisationStatus", "value", "remainingClimatisationTime_min")
        if isinstance(crt, (int, float)):
            d.climate_remaining_time_min = int(crt)
        # Readiness: deeper connection-state diagnostics. These augment
        # the existing aggregate ``connection_state`` field with the
        # per-sub-key values for power-user automations.
        cbpl = v(raw, "readiness", "readinessStatus", "value", "connectionState", "batteryPowerLevel")
        if isinstance(cbpl, str):
            d.connection_battery_power_level = cbpl
        cact = v(raw, "readiness", "readinessStatus", "value", "connectionState", "isActive")
        if isinstance(cact, bool):
            d.connection_active = cact
        dpbw = v(raw, "readiness", "readinessStatus", "value", "connectionWarning", "dailyPowerBudgetWarning")
        if isinstance(dpbw, bool):
            d.daily_power_budget_warning = dpbw
        iblw = v(raw, "readiness", "readinessStatus", "value", "connectionWarning", "insufficientBatteryLevelWarning")
        if isinstance(iblw, bool):
            d.insufficient_battery_level_warning = iblw

        # v1.26.0 Welle-6 (#173) — climate-at-unlock + window-heating-enabled
        # SETTINGS (distinct from front/back STATES). Scout #144 VW ID.4 Pro.
        clim_at_unlock = v(raw, "climatisation", "climatisationSettings", "value", "climatizationAtUnlock")
        if isinstance(clim_at_unlock, bool):
            d.climate_at_unlock = clim_at_unlock
        wh_enabled = v(raw, "climatisation", "climatisationSettings", "value", "windowHeatingEnabled")
        if isinstance(wh_enabled, bool):
            d.window_heating_enabled = wh_enabled

        # v2.0.0 (Big-Bang) — heaterSource (issue #163, best-effort).
        # ID.x heat-pump cars publish ``heaterSource`` ("electric"/"fuel"
        # in the wild). Read-only sensor exposure since #163 has no
        # confirmed tester for write semantics yet. Field stays None for
        # vehicles that don't ship it → _DATA_PRESENT_REQUIRED skips the
        # sensor for them.
        heater_src = v(raw, "climatisation", "climatisationSettings", "value", "heaterSource")
        if isinstance(heater_src, str) and heater_src:
            d.heater_source = heater_src

        # v1.26.0 (#173) — capabilities_count diagnostic. From scout #144
        # (54 items observed). Useful for power-users debugging "why is
        # entity X missing for me?". Read from selectivestatus envelope.
        caps = v(raw, "userCapabilities", "capabilitiesStatus", "value")
        if isinstance(caps, list):
            d.capabilities_count = len(caps)

            # v2.2.0 Phase 2 PR #10/20 — VW EU/Audi parity to SEAT/CUPRA
            # PR #8+#9. The CARIAD-BFF capabilities array carries an
            # ``expirationDate`` per capability for subscription-gated
            # services (e.g. ``honkAndFlash``, ``parkingPosition``,
            # ``access``). We mirror the SEAT/CUPRA earliest-wins
            # aggregation: scan all capabilities, pick the EARLIEST
            # expiry, surface as both ``subscription_expiry_at``
            # (timestamp sensor) and ``subscription_active`` (tri-state
            # binary_sensor). Tri-state semantics preserved — perpetual
            # capabilities (no expiry leaf) stay None instead of False.
            #
            # Defensive: non-dict cap entries, non-string expiry, and
            # malformed ISO 8601 are silently skipped. If the whole
            # capabilities array has no expiry leaves anywhere → field
            # stays None → phantom-protected sensors never created.
            cap_earliest: str | None = None
            for cap in caps:
                if not isinstance(cap, dict):
                    continue
                cap_exp = (
                    cap.get("expirationDate")
                    or cap.get("validUntil")
                    or cap.get("expiresAt")
                )
                if not isinstance(cap_exp, str) or not cap_exp:
                    continue
                if cap_earliest is None or cap_exp < cap_earliest:
                    cap_earliest = cap_exp
            if cap_earliest is not None:
                d.subscription_expiry_at = cap_earliest
                try:
                    # Same Z-suffix normalisation as seat_cupra.py to
                    # support ``fromisoformat`` on older HA / Python.
                    # NB: variable name ``cap_expiry_dt`` (not ``parsed``)
                    # because ``parsed`` is reused elsewhere in this
                    # function as ``int | None`` from ``safe_int`` — mypy
                    # would infer the wider union otherwise.
                    cap_expiry_dt = datetime.fromisoformat(
                        cap_earliest.replace("Z", "+00:00")
                    )
                    if cap_expiry_dt.tzinfo is None:
                        cap_expiry_dt = cap_expiry_dt.replace(
                            tzinfo=timezone.utc
                        )
                    now_utc = datetime.now(tz=timezone.utc)
                    d.subscription_active = cap_expiry_dt > now_utc
                    # v2.2.0 Phase 2 PR #11/20 — derived integer days
                    # remaining. Negative when expired (e.g. -3 means
                    # "expired 3 days ago"). Floor-divide via
                    # ``timedelta.days`` so partial days don't inflate.
                    d.subscription_days_remaining = (
                        cap_expiry_dt - now_utc
                    ).days
                except (ValueError, TypeError):
                    # Leave subscription_active at None — don't false-
                    # alarm perpetual users on a parse blip.
                    pass

        # v2.7.0b11 — windowHeatingStatus ships under different shapes
        # depending on brand / firmware. Try canonical nested name,
        # plus statusList variant, plus direct-array variant. First
        # non-empty list wins.
        wh_status = (
            v(raw, "climatisation", "windowHeatingStatus", "value", "windowHeatingStatus")
            or v(raw, "climatisation", "windowHeatingStatus", "value", "statusList")
            or v(raw, "climatisation", "windowHeatingStatus", "value", "windowHeatingStatusList")
            or v(raw, "climatisation", "windowHeatingStatus", "value")
            or []
        )
        if isinstance(wh_status, list):
            for wh in wh_status:
                if not isinstance(wh, dict):
                    continue
                location = (
                    wh.get("windowLocation")
                    or wh.get("location")
                    or wh.get("window")
                    or ""
                )
                state_raw = (
                    wh.get("windowHeatingState")
                    or wh.get("state")
                    or wh.get("status")
                )
                if not isinstance(state_raw, str) or not isinstance(location, str):
                    continue
                state = state_raw.upper() == "ON"
                loc_low = location.lower()
                if "front" in loc_low:
                    d.window_heating_front = state
                elif "rear" in loc_low or "back" in loc_low:
                    d.window_heating_back = state

        # Auxiliary heating (Standheizung, v2.8.0).
        # Cariad-BFF emits the ``auxiliaryHeating`` job since v2.7.0b10 (it
        # was the SELECTIVE_STATUS_JOBS promote that closed scout #366/#367).
        # Until now we only requested the job but never parsed the leaves.
        # Shape per Cariad vocabulary mirrors the climatisation block:
        #   auxiliaryHeating.auxiliaryHeatingStatus.value.{
        #       operationMode | climatisationState,
        #       remainingTime_min,
        #   }
        # Different firmwares ship one key or the other (some both); take
        # whichever is a non-empty string so older Audi MIB3 and newer
        # PPE/PPC both light up.
        # v2.11.0 (audi_connect_ha source-verified): older Audi A4 B9 /
        # MIB3 cars ship aux heating under `climatisation.auxiliary
        # HeatingStatus.value.climatisationState` (parent = climatisation,
        # NOT auxiliaryHeating). audi_connect_ha references this legacy
        # path; we missed it pre-v2.11.0.
        aux_state = (
            v(raw, "auxiliaryHeating", "auxiliaryHeatingStatus", "value", "operationMode")
            or v(raw, "auxiliaryHeating", "auxiliaryHeatingStatus", "value", "climatisationState")
            or v(raw, "climatisation", "auxiliaryHeatingStatus", "value", "climatisationState")
            or v(raw, "climatisation", "auxiliaryHeatingStatus", "value", "operationMode")
        )
        if isinstance(aux_state, str) and aux_state:
            d.auxiliary_heating_status = aux_state
            d.aux_heating_active = aux_state.lower() in {
                "heating", "on", "heatingon", "active",
            }
        aux_rem = (
            v(raw, "auxiliaryHeating", "auxiliaryHeatingStatus", "value",
              "remainingTime_min")
            or v(raw, "climatisation", "auxiliaryHeatingStatus", "value",
                 "remainingTime_min")
        )
        if isinstance(aux_rem, (int, float)):
            d.auxiliary_heating_remaining_min = int(aux_rem)

        # ── Readiness / online ─────────────────────────────────────────────────
        d.is_online = v(raw, "readiness", "readinessStatus", "value", "connectionState", "isOnline") is True
        # v2.2.0 Phase 7 PR #2 — telematics modem daily power budget.
        # When False the modem is rationing wake-ups to preserve 12V —
        # long poll intervals are the user-visible symptom. Surfaced
        # as binary_sensor so users can build "if power-budget
        # exhausted → warn" automations. Defensive: only assign when
        # backend returns a real bool (not None / missing).
        power_budget = v(
            raw, "readiness", "readinessStatus", "value",
            "connectionState", "dailyPowerBudgetAvailable",
        )
        if isinstance(power_budget, bool):
            d.daily_power_budget_available = power_budget

        # ── Vehicle health / service ──────────────────────────────────────────
        # ── Warning lights ────────────────────────────────────────────────────
        # v2.7.0b10 — distinguish "field missing" from "field present and
        # empty". Backend ships an empty list [] for a healthy car (no
        # active warnings) and a populated list when warnings fire. The
        # old code used ``or []`` which collapsed both into the same
        # branch but only ASSIGNED warning_* when the list was non-empty.
        # Result: a healthy car's warning sensors stayed at the dataclass
        # default None and rendered as "Unbekannt" in HA forever. Now
        # explicitly set False on empty list (true negative) and only
        # leave None when the field itself is genuinely absent from the
        # response (backend hiccup / capability-gated).
        warnings_raw = v(raw, "vehicleHealthWarnings", "warningLights", "value")
        if isinstance(warnings_raw, list):
            # Each warning: {warningType, iconId, text}
            warning_types = {
                w.get("warningType", "").upper()
                for w in warnings_raw
                if w.get("warningType")
            }
            d.warning_oil     = "OIL" in warning_types or "OIL_LEVEL" in warning_types
            d.warning_engine  = "ENGINE" in warning_types or "CHECK_ENGINE" in warning_types
            d.warning_tyre    = any("TYR" in t or "TIRE" in t for t in warning_types)
            d.warning_brakes  = "BRAKE" in warning_types
            d.warning_count   = len(warnings_raw)
            d.warning_active  = len(warnings_raw) > 0
            # v2.7.0b11 — generic warning surfacer. The hardcoded set
            # above misses real warnings users care about (the myAudi
            # email body shows things like "STO-Warning, Please check
            # towing bracket" which doesn't match any of OIL/ENGINE/
            # BRAKE/TYR). Pack everything backend reports into a
            # comma-joined string sensor so the user always sees what
            # the manufacturer app would show. Each item is
            # "type: text" when text is present, else "type".
            messages = []
            for w in warnings_raw:
                if not isinstance(w, dict):
                    continue
                wtype = (w.get("warningType") or "").strip()
                wtext = (w.get("text") or w.get("message") or "").strip()
                if wtype and wtext:
                    messages.append(f"{wtype}: {wtext}")
                elif wtype:
                    messages.append(wtype)
                elif wtext:
                    messages.append(wtext)
            d.warning_messages = ", ".join(messages) if messages else ""

        # v2.7.0b10 — oilLevel job, parity with upstream.
        # CARIAD-BFF ships either a discrete status string (most
        # common) or a numeric percentage, depending on the model.
        # Surface both fields; the entity layer renders whichever
        # the user's car actually provides.
        oil_value = v(raw, "oilLevel", "oilLevelStatus", "value")
        if isinstance(oil_value, dict):
            oil_status = oil_value.get("value")
            if isinstance(oil_status, str):
                d.oil_level_status = oil_status
                # PROBLEM device class convention: True = warning,
                # False = OK. Unknown strings leave the bool None so
                # we don't render a fake OK on a car with a backend
                # path we haven't catalogued yet.
                lowered = oil_status.lower()
                if lowered in ("normal", "ok", "sufficient"):
                    d.oil_level_warning = False
                elif "warning" in lowered or "service" in lowered or "low" in lowered:
                    d.oil_level_warning = True
            oil_pct = oil_value.get("oilLevelPercentage")
            if isinstance(oil_pct, (int, float)):
                d.oil_level_pct = int(oil_pct)

        # v2.15.1 — flat `oilLevelResult` wire-key (BFF dialect). Maps into the
        # same oil_level_status field + derives oil_level_warning with the same
        # logic as the structured oilLevel block above. Guard is None so the
        # structured path (when present) stays authoritative.
        if d.oil_level_status is None:
            oil_result = _find_flat(raw, "oilLevelResult")
            if isinstance(oil_result, str) and oil_result:
                d.oil_level_status = oil_result
                lowered = oil_result.lower()
                if lowered in ("normal", "ok", "sufficient"):
                    d.oil_level_warning = False
                elif "warning" in lowered or "service" in lowered or "low" in lowered:
                    d.oil_level_warning = True

        # v2.7.0b10 — tyrePressure job, parity with upstream.
        # Backend ships per-corner status + numeric pressure (kPa or bar
        # depending on firmware). Convert kPa->bar when needed (divide by
        # 100) so the sensor unit stays consistent. The warning bool is
        # already extracted from vehicleHealthWarnings above but the
        # tyrePressure job carries it explicitly too, so prefer this.
        # v2.10.0 (Scout audit 2026-06-02) — newer CARIAD-BFF firmware also
        # surfaces tire pressure on the ``measurements.tirePressureStatus.value``
        # branch (US naming) alongside the long-standing ``tyrePressure.*``
        # branch (EU naming). Read both, the second branch wins so the more
        # specific dedicated tyrePressure job stays authoritative.
        measurements_tyre = v(
            raw, "measurements", "tirePressureStatus", "value"
        )
        tyre_value = v(raw, "tyrePressure", "tyrePressureStatus", "value")
        if isinstance(measurements_tyre, dict) and not isinstance(tyre_value, dict):
            tyre_value = measurements_tyre
        if isinstance(tyre_value, dict):
            # Backend keys observed: currentTirePressure_FrontLeft_bar,
            # currentTirePressure_FrontLeft_kPa, currentValue_FL, etc.
            # Walk every key and route by suffix-pattern match.
            for key, value in tyre_value.items():
                if not isinstance(value, (int, float)):
                    continue
                klow = key.lower()
                bar_value: float | None = None
                if "_kpa" in klow or klow.endswith("kpa"):
                    bar_value = float(value) / 100.0
                elif "_bar" in klow or klow.endswith("bar"):
                    bar_value = float(value)
                if bar_value is None:
                    continue
                if "frontleft" in klow or "_fl" in klow:
                    d.tire_pressure_front_left_bar = round(bar_value, 2)
                elif "frontright" in klow or "_fr" in klow:
                    d.tire_pressure_front_right_bar = round(bar_value, 2)
                elif "rearleft" in klow or "_rl" in klow:
                    d.tire_pressure_rear_left_bar = round(bar_value, 2)
                elif "rearright" in klow or "_rr" in klow:
                    d.tire_pressure_rear_right_bar = round(bar_value, 2)
            warning_raw = tyre_value.get("overallStatus") or tyre_value.get("warningLight")
            if isinstance(warning_raw, str):
                d.tire_pressure_warning = warning_raw.lower() not in (
                    "ok", "normal", "off", "false",
                )
            elif isinstance(warning_raw, bool):
                d.tire_pressure_warning = warning_raw

            # v2.15.1 — per-corner tire STATE + ERROR CODE (BFF dialect NEW
            # fields). Walk the same value block: route by corner substring,
            # then by `state` vs `errorcode`/`errcode` in the key. State is a
            # lowercased passthrough string; errorcode is int with the 0/1
            # sentinels (unsupported / invalid) dropped to None.
            for key, value in tyre_value.items():
                klow = key.lower()
                corner: str | None = None
                if "frontleft" in klow or "_fl" in klow or klow.startswith("fl"):
                    corner = "fl"
                elif "frontright" in klow or "_fr" in klow or klow.startswith("fr"):
                    corner = "fr"
                elif "rearleft" in klow or "_rl" in klow or klow.startswith("rl"):
                    corner = "rl"
                elif "rearright" in klow or "_rr" in klow or klow.startswith("rr"):
                    corner = "rr"
                if corner is None:
                    continue
                if "errorcode" in klow or "errcode" in klow or "error_code" in klow:
                    ec = safe_int(value)
                    if ec is not None and ec not in (0, 1):
                        setattr(d, f"tire_pressure_{corner}_errorcode", ec)
                elif "state" in klow and "status" not in klow:
                    if isinstance(value, str) and value:
                        setattr(
                            d, f"tire_pressure_{corner}_state", value.lower()
                        )

        d.service_km = v(raw, "vehicleHealthInspection", "maintenanceStatus", "value", "inspectionDue_km")
        d.service_due_at = v(raw, "vehicleHealthInspection", "maintenanceStatus", "value", "inspectionDue_days")
        d.oil_service_km = v(raw, "vehicleHealthInspection", "maintenanceStatus", "value", "oilServiceDue_km")
        d.oil_service_at = v(raw, "vehicleHealthInspection", "maintenanceStatus", "value", "oilServiceDue_days")
        # v1.11.0 (#91 closure) — explicit raw int day-counts. Same backend
        # source as ``service_due_at``/``oil_service_at`` (which are
        # int-typed but exposed as DATE sensors via in-sensor.py
        # conversion). The new int sensors complement the date sensors
        # for users who want "5 days remaining" instead of "May 5, 2026".
        d.service_due_in_days = safe_int(d.service_due_at)
        d.oil_service_due_in_days = safe_int(d.oil_service_at)

        # v2.8.0 — brake service due-dates + preferred workshop (Quick Win C).
        # Same parent block as the legacy ``inspectionDue_days``/
        # ``oilServiceDue_days`` pair. Field-name probes follow the
        # observed CARIAD-BFF + competitor-integration shapes:
        #   - ``brakeFluidChange_days`` (CARIAD-BFF VW EU MEB)
        #   - ``brakeFluidChangeDue_days`` (Audi MLB Evo variant)
        #   - ``brakePadWearFrontInspection_days`` (CARIAD-BFF)
        #   - ``frontBrakePadWearInspection_days`` (Audi variant)
        # First non-None wins. Values are int "days from now"; the
        # ``days_or_date_to_iso`` helper anchors them to midnight UTC
        # so the TIMESTAMP-class sensor renders relative ("in 142 days").
        from .._util import (  # noqa: PLC0415
            compose_workshop_address,
            days_or_date_to_iso,
            normalize_workshop_string,
            workshop_phone_from_contact,
        )
        ms_value = v(raw, "vehicleHealthInspection", "maintenanceStatus", "value")
        if isinstance(ms_value, dict):
            brake_fluid_raw = (
                ms_value.get("brakeFluidChange_days")
                or ms_value.get("brakeFluidChangeDue_days")
                or ms_value.get("brakeFluidChangeDue_at")
                or ms_value.get("brakeFluidChange_at")
            )
            d.brake_fluid_change_due_at = days_or_date_to_iso(brake_fluid_raw)
            front_pads_raw = (
                ms_value.get("brakePadWearFrontInspection_days")
                or ms_value.get("frontBrakePadWearInspection_days")
                or ms_value.get("brakePadFrontInspectionDue_days")
                or ms_value.get("brakePadWearFrontInspection_at")
            )
            d.brake_pads_front_inspection_due_at = days_or_date_to_iso(front_pads_raw)
            rear_pads_raw = (
                ms_value.get("brakePadWearRearInspection_days")
                or ms_value.get("rearBrakePadWearInspection_days")
                or ms_value.get("brakePadRearInspectionDue_days")
                or ms_value.get("brakePadWearRearInspection_at")
            )
            d.brake_pads_rear_inspection_due_at = days_or_date_to_iso(rear_pads_raw)

            # Preferred workshop — CARIAD-BFF surfaces it alongside the
            # maintenance numbers on the same ``maintenanceStatus.value``
            # block. Defensive: shape varies (sometimes flat keys, often
            # a nested ``preferredServicePartner`` / ``servicePartner``
            # dict — same convention as Skoda's mysmob endpoint).
            workshop = (
                ms_value.get("preferredServicePartner")
                or ms_value.get("servicePartner")
                or ms_value.get("preferredWorkshop")
            )
            if isinstance(workshop, dict) and workshop:
                d.preferred_workshop_name = normalize_workshop_string(
                    workshop.get("name") or workshop.get("displayName"),
                )
                d.preferred_workshop_address = compose_workshop_address(
                    workshop.get("address") or workshop,
                )
                d.preferred_workshop_phone = workshop_phone_from_contact(
                    workshop.get("contact") or workshop,
                )

        # v1.11.0 (#91 closure) — vehicle lights aggregate.
        # Backend shape (from #90 + #91 Scout reports — ``[2 items]``,
        # exact element shape varies):
        #   vehicleLights.lightsStatus.value.lights = [
        #     {"name": "frontLeft", "status": "off"},   # common shape A
        #     {"id": "rearRight", "status": "on"},      # common shape B
        #     ...
        #   ]
        # We extract three things:
        #   1. ``lights_count`` — number of lights reporting "on"
        #      (always set when the array is present)
        #   2. ``lights_on`` — bool aggregate (count > 0)
        #   3. ``lights_individual`` — dict {name -> bool} when shape is
        #      recognised. Per-light entities (binary sensors per light)
        #      only register when this dict is populated, so unknown
        #      firmwares never get phantom entities.
        lights_arr = v(raw, "vehicleLights", "lightsStatus", "value", "lights")
        if isinstance(lights_arr, list):
            on_count = 0
            individual: dict[str, bool] = {}
            for light in lights_arr:
                if not isinstance(light, dict):
                    continue
                # Status: try "status" (most common), then "state".
                # May be a plain string ("on"/"off"), a dict
                # ({"value": "on"}), or a list of dicts (CARIAD-BFF
                # pattern — see doors/windows). All three normalise to
                # a single string we then compare case-insensitively.
                raw_status = light.get("status") or light.get("state")
                if isinstance(raw_status, list) and raw_status:
                    raw_status = raw_status[0]
                if isinstance(raw_status, dict):
                    raw_status = raw_status.get("value") or raw_status.get("status")
                is_on = (
                    isinstance(raw_status, str)
                    and raw_status.lower() == "on"
                )
                if is_on:
                    on_count += 1
                # Try to extract a stable name for the per-light dict.
                # Skip if no recognised name field — keeps unknown
                # shapes from polluting the per-light entity list.
                name = (
                    light.get("name")
                    or light.get("id")
                    or (light.get("location") or {}).get("position")
                )
                if isinstance(name, str) and name:
                    individual[name] = is_on
            d.lights_count = on_count
            d.lights_on = on_count > 0
            if individual:
                d.lights_individual = individual

        # ── Departure timers ──────────────────────────────────────────────────
        timers: list[dict[str, Any]] = v(raw, "departureTimers", "departureTimersStatus", "value", "timers") or []
        for i, timer in enumerate(timers[:3], 1):
            enabled = timer.get("enabled", False)
            time_str = timer.get("departureTime", {}).get("time") if timer.get("departureTime") else None
            setattr(d, f"departure_timer_{i}_enabled", enabled)
            setattr(d, f"departure_timer_{i}_time", time_str)
        # v2.2.0 Phase 7 PR #2 — aggregate count of enabled timers.
        # Saves users the templating effort of summing 3 separate
        # binary states. Defensive: only set when the timers list
        # is actually present (not just empty) — keeps the
        # phantom-protection gate honest.
        if timers:
            d.departure_timer_enabled_count = sum(
                1 for t in timers if t.get("enabled") is True
            )

        # v2.2.2 cross-brand expansion (#248 arvcer scout — climatisation
        # Timers reported as silenced-but-unwired). Mirror of departure
        # timers shape: `climatisationTimers.climatisationTimersStatus.
        # value.timers[*]`. Populates `d.climate_timer_enabled_count`
        # which Skoda already has from Phase 7 PR #4. VW EU/Audi parity.
        # Defensive: shape unverified per scout reporting `{2 keys}`
        # — assumption is mirror of departureTimers (timers + carCaptured
        # Timestamp). If the actual leaves differ on production, the
        # list-check guard keeps the field None (no false-positive
        # zero count) — phantom-gate stays honest.
        clim_timers: list[dict[str, Any]] = v(
            raw, "climatisationTimers", "climatisationTimersStatus",
            "value", "timers",
        ) or []
        # v2.3.0 — scout #264 (Audi moltke69 2026-05-19): newer
        # Cariad-BFF firmware restructured the timers under a unified
        # ``departureTimers`` parent block with separate ``charging``
        # and ``climatisation`` sub-statuses. moltke69's scout shows
        # ``departureTimers.climatisationTimersStatus.value.timers``
        # with ``[1 items]`` — same shape as the older
        # ``climatisationTimers.*`` path, just relocated. Try the new
        # location as fallback when the legacy path is empty so users
        # on newer firmware still get a populated count.
        if not clim_timers:
            clim_timers = v(
                raw, "departureTimers", "climatisationTimersStatus",
                "value", "timers",
            ) or []
        if clim_timers:
            d.climate_timer_enabled_count = sum(
                1 for t in clim_timers
                if isinstance(t, dict) and t.get("enabled") is True
            )

        # ── Parking position ──────────────────────────────────────────────────
        # v1.27.1 hotfix: Cariad-BFF ``/vehicle/v1/vehicles/{vin}/parkingposition``
        # returns ``{"data": {"lat": ..., "lon": ..., "carCapturedTimestamp": ...}}``.
        # Pre-v1.27.1 parser read ``parking.get("lat")`` directly (no ``data``
        # unwrap) → always None → device_tracker never spawned because
        # ``device_tracker._has_gps()`` filter rejects None values silently.
        # Verified live response shape via ``scripts/verify_cariad_for_gte.py``
        # against Golf 7 GTE on 2026-05-11.
        if parking:
            parking_data = parking.get("data") if isinstance(parking, dict) else None
            if not isinstance(parking_data, dict):
                # Some legacy/historic responses or alternate firmwares may
                # ship lat/lon at top level — keep that as a fallback.
                parking_data = parking
            d.latitude = parking_data.get("lat")
            d.longitude = parking_data.get("lon")
            # v1.25.0 PR-A — Cross-brand parity: parking_address from
            # Cariad-BFF if present (Skoda mysmob ships
            # ``formattedAddress`` since v1.20.0). Cariad-BFF
            # ``parkingposition`` returns
            # ``{"address": {"city": "...", "country": "...", ...}}``
            # on most accounts; some firmwares also surface a
            # composed ``formattedAddress``. Saves the HA
            # reverse-geocoding round-trip when supplied.
            addr_block = parking_data.get("address") if isinstance(parking_data, dict) else None
            if isinstance(addr_block, dict):
                fa = addr_block.get("formattedAddress")
                if isinstance(fa, str) and fa:
                    d.parking_address = fa
                else:
                    # Compose from parts: street, city, country
                    parts = [
                        addr_block.get("street"),
                        addr_block.get("city"),
                        addr_block.get("country"),
                    ]
                    composed = ", ".join(p for p in parts if isinstance(p, str) and p)
                    if composed:
                        d.parking_address = composed
                if isinstance(addr_block.get("city"), str):
                    d.parking_city = addr_block["city"]

        # v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation
        # fallback. VW EU already reads `carType` directly from
        # `fuelStatus` or `measurements` (Phase 8 PR #2), so this is
        # a NO-OP when the backend ships the field. Fires only on
        # rotated/missing-field firmware to give those users a
        # derived value. Audi inherits this automatically.
        from .._util import derive_car_type_if_missing  # noqa: PLC0415

        derive_car_type_if_missing(d)

        # ── v2.15.1 — flat BFF wire-key mapping (2.15.0 plan) ───────────────
        # Runs LAST so the structured engine/range blocks above stay
        # authoritative. Each flat key is scanned defensively via _find_flat
        # since its exact container on selectivestatus is live-test gated.

        # petrolRange → combustion_range_km, only if the structured block
        # left it None (guard is None so the engine block wins).
        if d.combustion_range_km is None:
            d.combustion_range_km = safe_int(_find_flat(raw, "petrolRange"))

        # gasRange (CNG) → cng_range_km preferred, else combustion_range_km.
        _gas = safe_int(_find_flat(raw, "gasRange"))
        if _gas is not None:
            if d.cng_range_km is None:
                d.cng_range_km = _gas
            elif d.combustion_range_km is None:
                d.combustion_range_km = _gas

        # currentCngLevel_pct → cng_level_pct (0–100).
        if d.cng_level_pct is None:
            d.cng_level_pct = safe_int(_find_flat(raw, "currentCngLevel_pct"))

        # batteryCapacityNetto → battery_cap_kwh. kWh vs Wh: a value > 500 is
        # treated as Wh and divided by 1000 (live-test heuristic).
        if d.battery_cap_kwh is None:
            _cap = safe_float(_find_flat(raw, "batteryCapacityNetto"))
            if _cap is not None:
                d.battery_cap_kwh = _cap / 1000.0 if _cap > 500 else _cap

        # parkingBrakeStatus → parking_brake_engaged (shared field). enum→bool.
        _pbrk = _find_flat(raw, "parkingBrakeStatus")
        if _pbrk is not None:
            if isinstance(_pbrk, bool):
                d.parking_brake_engaged = _pbrk
            elif isinstance(_pbrk, str):
                d.parking_brake_engaged = _pbrk.lower() in (
                    "engaged", "applied", "set", "on", "true", "active",
                )

        # — BFF NEW fields —
        # lpgRange → lpg_range_km.
        d.lpg_range_km = safe_int(_find_flat(raw, "lpgRange"))

        # engineStatus → engine_status (lowercased; bool→on/off).
        _eng = _find_flat(raw, "engineStatus")
        if isinstance(_eng, bool):
            d.engine_status = "on" if _eng else "off"
        elif isinstance(_eng, str) and _eng:
            d.engine_status = _eng.lower()

        # trip_avg_aux_consumption_kwh — LOW, unit ambiguous → NOT rescaled.
        _aux = safe_float(
            _find_flat(raw, "tripAverageAuxConsumption")
            or _find_flat(raw, "averageAuxiliaryConsumption")
        )
        if _aux is not None:
            d.trip_avg_aux_consumption_kwh = _aux

        # departure_charge_kwh — LOW.
        _dep = safe_float(
            _find_flat(raw, "departureCharge")
            or _find_flat(raw, "departureChargeEnergy_kwh")
        )
        if _dep is not None:
            d.departure_charge_kwh = _dep

        return d
