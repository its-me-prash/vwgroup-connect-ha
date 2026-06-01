# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""SEAT/CUPRA API client — ola.prod.code.seat.cloud.vwgroup.com.

API endpoints based on upstream/pycupra (Apache-2.0) — clean-room reimplementation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientSession

from .._util import (
    compose_workshop_address,
    compute_connection_state,
    days_or_date_to_iso,
    normalize_workshop_string,
    safe_float,
    safe_int,
    workshop_phone_from_contact,
)
from .._ola_headers import get_fallback_count, get_ola_headers
from ..exceptions import APIError, SpinError
from ..models import BRAND_CUPRA, BRAND_SEAT, BrandConfig, VehicleData
from .base import CariadBaseClient

_LOGGER = logging.getLogger(__name__)
_BASE = "https://ola.prod.code.seat.cloud.vwgroup.com"

# v2.4.1 (#281+#282) — number of consecutive 403s on OLA endpoints
# before we raise an HA Repair issue prompting the user to check for
# integration updates. Set conservatively to avoid false positives on
# transient backend errors (Cariad has occasional 5xx flutter on the
# OLA path too, which 403s on stale tokens).
_OLA_REPAIR_THRESHOLD = 5


class SeatCupraClient(CariadBaseClient):
    """SEAT/CUPRA API client.

    v2.4.1 (#281+#282) — Defense-in-depth against the 2026-05-20 OLA
    header-enforcement change (see ``cariad/_ola_headers.py`` module
    docstring for the full architecture):

    1. Inject brand-specific app-identifying headers on every request
       via ``_request()`` override (Layer 1: centralized constants).
    2. Honor OptionsFlow overrides for app_version + user_agent
       (Layer 2: see ``const.py`` CONF_OLA_APP_VERSION_OVERRIDE +
       CONF_OLA_USER_AGENT_OVERRIDE — read at construction time).
    3. On 403, retry with the next fallback header-set from
       ``_ola_headers.py`` (Layer 3: multi-version fallback chain).
    4. After N consecutive unrecoverable 403s, raise an HA Repair
       issue (Layer 4: actionable user signal).
    """

    def __init__(
        self,
        session: ClientSession,
        brand: str,
        email: str,
        password: str,
        spin: str = "",
        ola_app_version_override: str | None = None,
        ola_user_agent_override: str | None = None,
    ) -> None:
        brand_cfg: BrandConfig = BRAND_CUPRA if brand.lower() == "cupra" else BRAND_SEAT
        super().__init__(session, brand_cfg, email, password, spin)
        self._user_id: str | None = None
        # v2.4.1 (#281+#282) — OLA defense-in-depth state.
        self._ola_app_version_override = ola_app_version_override or None
        self._ola_user_agent_override = ola_user_agent_override or None
        # Counter for consecutive 403s after all fallbacks exhausted.
        # Reset to 0 on any successful response.
        self._ola_consecutive_403 = 0
        # Public flag readable by the coordinator to surface a Repair
        # issue when threshold is exceeded. Coordinator wires this to
        # ``repairs.raise_issue_ola_headers_outdated`` (added v2.4.1).
        self.ola_headers_repair_needed = False
        # v2.4.1 — Scout Policy Compliance Audit T1: per-VIN caches
        # for license plate + nickname (from /v2/users/.../garage)
        # and parking-position map URLs (from /v1/vehicles/{vin}/
        # parkingposition). Surfaced as sensors in get_status().
        self._vin_to_license_plate: dict[str, str] = {}
        self._vin_to_nickname: dict[str, str] = {}

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """IDK auth + capture user_id from redirect chain."""
        await super().authenticate()
        if self._auth.user_id:
            self._user_id = self._auth.user_id
            _LOGGER.debug("SEAT/CUPRA user_id from auth redirect: %s", self._user_id[:8])
        else:
            await self._fetch_user_id()

    # ── v2.4.1 OLA defense-in-depth ────────────────────────────────────────
    async def _request(
        self, method: str, url: str, retry: bool = True, _attempt: int = 0, **kwargs: Any
    ) -> Any:
        """Override to inject OLA app-identifying headers + 403 fallback chain.

        v2.4.1 (#281+#282) — VW Group's OLA backend started enforcing
        app-identifying headers on 2026-05-20. Every request against
        ``ola.prod.code.seat.cloud.vwgroup.com`` MUST carry the brand-
        appropriate ``app-market`` + ``app-brand`` + ``app-version`` +
        ``origin`` headers (and ideally the matching ``User-Agent``).
        Otherwise the backend returns HTTP 403 Forbidden regardless
        of token validity — blocking ALL setup + operation entirely.

        Layer 1: inject the headers from ``_ola_headers.py``.
        Layer 2: honor user OptionsFlow overrides (``_ola_app_version_
                 override`` + ``_ola_user_agent_override``).
        Layer 3: on 403, retry once with the next fallback header-set.
        Layer 4: track consecutive 403s — when threshold exceeded, set
                 ``ola_headers_repair_needed`` flag so the coordinator
                 raises an HA Repair issue.
        """
        # Build OLA headers for this brand + apply user overrides.
        headers = kwargs.pop("headers", None) or {}
        # Fallback index is encoded in _attempt: 0 = primary, 1+ = fallback chain.
        fb_idx = -1 if _attempt == 0 else _attempt - 1
        ola_headers = get_ola_headers(
            self._brand.name,
            fallback_index=fb_idx,
            app_version_override=self._ola_app_version_override,
            user_agent_override=self._ola_user_agent_override,
        )
        # Caller-supplied headers win (allows per-request override for SecToken etc).
        for k, v in ola_headers.items():
            headers.setdefault(k, v)

        try:
            response = await super()._request(method, url, retry=retry, _attempt=_attempt, headers=headers, **kwargs)
            # Layer 4: reset 403 counter on any successful response.
            self._ola_consecutive_403 = 0
            self.ola_headers_repair_needed = False
            return response
        except APIError as exc:
            # Only intercept 403s from OLA — let other errors propagate.
            if "403" not in str(exc) or "ola.prod" not in url:
                raise
            # Layer 3: try the next fallback header-set if available.
            fb_count = get_fallback_count(self._brand.name)
            if _attempt < fb_count:
                _LOGGER.warning(
                    "OLA 403 on %s — retrying with fallback header-set "
                    "#%d/%d (defense-in-depth Layer 3)",
                    url[-60:], _attempt + 1, fb_count,
                )
                return await self._request(method, url, retry=False, _attempt=_attempt + 1, **kwargs)
            # Layer 4: all fallbacks exhausted — count toward threshold.
            self._ola_consecutive_403 += 1
            if self._ola_consecutive_403 >= _OLA_REPAIR_THRESHOLD:
                _LOGGER.error(
                    "OLA 403 persistent (%d consecutive) — flagging for HA "
                    "Repair issue. Likely cause: OLA backend updated app-"
                    "header requirements again. Check for integration update.",
                    self._ola_consecutive_403,
                )
                self.ola_headers_repair_needed = True
            raise

    async def _fetch_user_id(self) -> None:
        """Fallback: extract user_id from JWT or API call."""
        if self._tokens and self._tokens.id_token:
            try:
                import base64  # noqa: PLC0415
                import json as _json  # noqa: PLC0415
                payload_b64 = self._tokens.id_token.split(".")[1]
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
                sub = payload.get("sub")
                if sub:
                    self._user_id = sub
                    _LOGGER.debug("SEAT/CUPRA user_id from JWT: %s", sub[:8])
                    return
            except Exception:  # noqa: BLE001
                pass

        try:
            data = await self._get(f"{_BASE}/v1/users")
            self._user_id = data.get("userId") or data.get("sub")
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not fetch SEAT/CUPRA user ID")

    async def get_vehicles(self) -> list[str]:
        """Return VINs from garage.

        v2.4.1 — Scout Policy Compliance Audit T1: cache the
        ``licensePlate`` + ``name`` (nickname) fields from each
        vehicle dict so the per-vehicle parser can surface them as
        sensors. The garage response already includes these; we just
        weren't reading them.
        """
        if not self._user_id:
            await self._fetch_user_id()
        data = await self._get(f"{_BASE}/v2/users/{self._user_id}/garage/vehicles")
        vehicles: list[dict[str, Any]] = data.get("vehicles", [])
        vins = []
        for vehicle in vehicles:
            vin = vehicle.get("vin")
            if not vin:
                continue
            vins.append(vin)
            # v2.4.1 T1: cache license plate + nickname per VIN.
            plate = vehicle.get("licensePlate")
            if isinstance(plate, str) and plate:
                self._vin_to_license_plate[vin] = plate
            nick = vehicle.get("name") or vehicle.get("vehicleNickname")
            if isinstance(nick, str) and nick:
                self._vin_to_nickname[vin] = nick
        await self._fetch_renders(vins)
        await self.fetch_images()
        return vins

    async def get_capabilities(self, vin: str) -> dict[str, Any]:
        """Return the OLA capabilities document for *vin*.

        The response shape is roughly:
            {"capabilities": [{"id": "honk-and-flash", "status": [...]}, ...]}

        Caller is responsible for caching (handled by the coordinator with a
        24h TTL). Failure raises ``APIError`` — caller should swallow it
        because capabilities are best-effort metadata, never load-bearing.

        v1.17.1 — A/B fallback after Bruno-Collection research:
        - Bruno (seq 4): GET /v1/user/{userId}/vehicle/{vin}/capabilities (singular)
        - Our pre-v1.17.1: GET /v1/vehicles/{vin}/capabilities (plural)

        Both observed in upstream sources. Try our pre-v1.17.1 plural
        path first (status quo, no migration risk), fall back to
        Bruno's singular path on 404. If our path was actually the
        wrong one all along, this preserves capability fetching for
        accounts that need the singular variant.
        """
        try:
            data = await self._get(f"{_BASE}/v1/vehicles/{vin}/capabilities")
            return data if isinstance(data, dict) else {}
        except APIError as err:
            if err.status != 404:
                raise
            _LOGGER.debug(
                "OLA capabilities 404 on /v1/vehicles/{vin}/capabilities — "
                "trying Bruno-singular path /v1/user/{userId}/vehicle/{vin}/capabilities"
            )
        # Fallback to Bruno-Collection singular path (requires user_id).
        if not self._user_id:
            await self._fetch_user_id()
        if not self._user_id:
            return {}  # Can't build the singular URL without user_id
        try:
            data = await self._get(
                f"{_BASE}/v1/user/{self._user_id}/vehicle/{vin}/capabilities"
            )
            return data if isinstance(data, dict) else {}
        except APIError as err:
            if err.status == 404:
                return {}  # Both paths 404 — give up, return empty
            raise

    async def _fetch_renders(self, vins: list[str]) -> None:
        """Fetch vehicle render images from OLA renders endpoint."""
        for vin in vins:
            try:
                data = await self._get(f"{_BASE}/v2/vehicles/{vin}/renders")
                urls: dict[str, str] = {}
                for render in data if isinstance(data, list) else data.get("renders", []):
                    view = render.get("viewPoint") or render.get("type", "")
                    url = render.get("url", "")
                    if view and url:
                        urls[view] = url
                if urls:
                    from .graphql import VehicleImageData  # noqa: PLC0415
                    self._image_data[vin] = VehicleImageData(
                        vin=vin, image_urls=urls, short_name=None, long_name=None, exterior_color=None
                    )
                    _LOGGER.debug("SEAT/CUPRA renders for %s: %d views", vin[-6:], len(urls))
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Could not fetch renders for %s", vin[-6:])

    async def get_status(self, vin: str) -> VehicleData:
        """Fetch full status from OLA server."""
        v = self._val
        d = VehicleData(vin=vin)

        # v2.4.1 — Scout Policy Compliance Audit T1: surface the
        # garage-cached license plate + nickname per VIN. No extra
        # HTTP call needed — populated during get_vehicles().
        d.license_plate = self._vin_to_license_plate.get(vin)
        d.vehicle_nickname = self._vin_to_nickname.get(vin)

        # v2.5.3 — OLA v1↔v5 fallback chain (#306 Mii/Tavascan/Leon FR-KL
        # null-cascade). PyCupra's pattern: when the modern ``/v5/mycar``
        # response is offline-state, fall back to the v1 endpoints which
        # the OLA backend caches server-side and returns even for offline
        # vehicles. We now ALWAYS fetch ``/v1/mileage`` in parallel so the
        # odometer + range cache is available as a fallback when v5 returns
        # null measurements. Other v1 endpoints (ranges, maintenance,
        # charging/info) were already in the gather; v2.5.3 widens their
        # field-variant coverage for older vehicle generations.
        results = await asyncio.gather(
            self._get(f"{_BASE}/v5/users/{self._user_id}/vehicles/{vin}/mycar"),
            self._get(f"{_BASE}/v1/vehicles/{vin}/parkingposition"),
            self._get(f"{_BASE}/v1/vehicles/{vin}/ranges"),
            self._get(f"{_BASE}/v2/vehicles/{vin}/status"),
            self._get(f"{_BASE}/v1/vehicles/{vin}/charging/status"),
            self._get(f"{_BASE}/v1/vehicles/{vin}/charging/info"),
            self._get(f"{_BASE}/v2/vehicles/{vin}/climatisation"),
            self._get(f"{_BASE}/v1/vehicles/{vin}/maintenance"),
            self._get(f"{_BASE}/v1/vehicles/{vin}/remote-availability"),
            self._get(f"{_BASE}/v1/vehicles/{vin}/mileage"),  # v2.5.3 (#306)
            return_exceptions=True,
        )
        (
            mycar, parking, ranges, status, charge_status, charge_info,
            climate, maintenance, availability,
            mileage_v1,  # v2.5.3 (#306)
        ) = results

        # v1.9.0 — Vehicle Data Scout opt-in. Endpoint names match
        # ``EXPECTED_KEYS["cupra"]`` (SEAT inherits the same table).
        # v2.5.3 — added ``mileage`` so the v1 cached-odometer block is
        # walked by the scout same as the other endpoints.
        self.last_raw_responses = {}
        for name, payload in (
            ("mycar", mycar),
            ("status", status),
            ("charging", charge_status),
            ("charging-info", charge_info),
            ("climatisation", climate),
            ("mileage", mileage_v1),  # v2.5.3 (#306)
        ):
            if isinstance(payload, dict):
                self.last_raw_responses[name] = payload

        # v2.8.0 quick win D — parser-health telemetry. Each OLA
        # endpoint maps to one logical job. Records per-call success
        # (got a dict) or failure (Exception in gather). Tracks the
        # same canonical job names as the other brands so cross-brand
        # diagnostics aggregation reads consistently.
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

        _note("vehicle_status", mycar)
        _note("charging", charge_status)
        _note("climatisation", climate)
        _note("parking_position", parking)
        _note("service_care", maintenance)
        # OLA flattens oil_level / tyre_pressure / auxiliary_heating
        # into the mycar payload; door_lock lives under
        # ``access.accessStatus.value``. Mirror the door_lock counter
        # from there so cross-brand diagnostics line up.
        if isinstance(mycar, BaseException):
            _note("door_lock", mycar)
        elif isinstance(mycar, dict):
            self._note_parser_job(
                "door_lock",
                present=isinstance(
                    self._val(mycar, "access", "accessStatus", "value"), dict,
                ),
            )

        # ── Main vehicle data (mycar) ────────────────────────────────────────
        if isinstance(mycar, dict):
            measurements = v(mycar, "measurements") or {}
            d.odometer_km = v(measurements, "mileage", "value")
            d.fuel_level = v(measurements, "fuelLevelStatus", "value", "currentFuelLevel_pct")
            d.battery_soc = v(measurements, "batteryStatus", "value", "currentSOC_pct")
            d.has_battery = d.battery_soc is not None

            # v2.8.1 #306 — user-selected preferred charging mode. The
            # OLA backend mirrors the brand-app setting under
            # ``mycar.services.charging.preferredChargeMode``. Known
            # enum values: "manual", "preferredChargingTimes",
            # "automaticUnlocked". Empty string means unset.
            pref_mode = v(mycar, "services", "charging", "preferredChargeMode")
            if isinstance(pref_mode, str) and pref_mode.strip():
                d.charging_preferred_mode = pref_mode

            # v2.8.1 #306 — area alarm event flag. Top-level
            # ``mycar.areaAlarm`` carries an event payload when the
            # vehicle has left a configured geofence. We expose the
            # boolean presence here; coordinator-side timestamp decay
            # to clear stale alarms after 15 minutes is in scope for
            # v2.8.2 (the harness for event-decay is not yet wired).
            area_alarm_block = v(mycar, "areaAlarm")
            if isinstance(area_alarm_block, dict) and area_alarm_block:
                d.area_alarm = True
            elif area_alarm_block is not None:
                d.area_alarm = False

            access = v(mycar, "access") or {}
            # v2.0.1 (#131 follow-up) — defensive parsing, see vw_eu.py
            # for the full rationale. Per-door + top-level fallbacks
            # below (lines ~265 + ~331) further refine the value.
            access_lock = v(access, "accessStatus", "value", "doorLockStatus")
            if isinstance(access_lock, str):
                d.doors_locked = access_lock.upper() == "LOCKED"

            # v2.2.0 Phase 2 PR #8/20 — Connect-subscription expiry.
            # ``mycar.services`` is a per-entitlement map (charging,
            # climatisation, windowHeating, etc.). Each entry MAY carry
            # an expiry timestamp under one of several key-name variants
            # (the OLA team has shipped 3 different spellings in 18 months
            # — pycupra commit 0f3b1c7 documents the rotation). We pick
            # the EARLIEST present expiry across all services so the user
            # sees "first to expire" (most-restrictive cap).
            #
            # Defensive: any malformed timestamp (non-ISO string, int,
            # None) is skipped silently. If no service has an expiry,
            # field stays None → phantom-protected sensor never created.
            services = v(mycar, "services")
            if isinstance(services, dict):
                earliest: str | None = None
                for svc_name, svc_data in services.items():
                    if not isinstance(svc_data, dict):
                        continue
                    # Try the 3 known key-name variants in priority order
                    raw_expiry = (
                        svc_data.get("expirationDate")
                        or svc_data.get("validUntil")
                        or svc_data.get("expiresAt")
                    )
                    if not isinstance(raw_expiry, str) or not raw_expiry:
                        continue
                    # ISO 8601 strings sort lexicographically when
                    # they share the same format width (e.g. all
                    # "YYYY-MM-DDTHH:MM:SSZ" or all with offsets).
                    # earliest = min, so first iteration sets baseline.
                    if earliest is None or raw_expiry < earliest:
                        earliest = raw_expiry
                        _LOGGER.debug(
                            "subscription expiry candidate: service=%s "
                            "raw=%s (current earliest=%s)",
                            svc_name, raw_expiry, earliest,
                        )
                if earliest is not None:
                    d.subscription_expiry_at = earliest
                    # v2.2.0 Phase 2 PR #9/20 — companion boolean.
                    # Tri-state-preserving: only flip to True/False
                    # when we successfully parse a timestamp; on parse
                    # failure leave at None (don't false-alarm a user
                    # with perpetual entitlements just because our
                    # datetime parse choked on an unusual format).
                    #
                    # NB: uses the module-level ``datetime`` / ``timezone``
                    # imports (line 11). Inline ``from datetime import``
                    # shadows the module-level name as a function-local
                    # for the WHOLE ``get_status`` scope (Python lexer
                    # rule), causing UnboundLocalError on any prior
                    # reference inside the function.
                    try:
                        # Normalise trailing ``Z`` to ``+00:00`` for
                        # ``fromisoformat`` (Python 3.11+ accepts ``Z``
                        # natively but we keep this for older HA users).
                        exp_dt = datetime.fromisoformat(
                            earliest.replace("Z", "+00:00")
                        )
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        now_utc = datetime.now(tz=timezone.utc)
                        d.subscription_active = exp_dt > now_utc
                        # v2.2.0 Phase 2 PR #11/20 — derived integer days
                        # remaining. Negative when expired (e.g. -3 means
                        # "expired 3 days ago"). Floor-divide so partial
                        # days don't inflate the count.
                        d.subscription_days_remaining = (
                            exp_dt - now_utc
                        ).days
                    except (ValueError, TypeError) as exc:
                        _LOGGER.debug(
                            "subscription_active: could not parse expiry "
                            "%s — leaving as None (raw_exc=%s)",
                            earliest, exc,
                        )

            # v2.2.0 PR #18/20 (Scout #232 — matthias0304 2026-05-16) —
            # CUPRA PHEV companion to Skoda Scout #220. OLA mycar
            # ``engines.secondary`` is a 3-key block on PHEV variants
            # (Formentor PHEV, Leon e-Hybrid) mirroring the Skoda
            # ``driving-range.secondaryEngineRange`` shape. We reuse the
            # existing cross-brand ``secondary_engine_*`` fields from
            # PR #6 so phantom-protection gates + sensor descriptions
            # carry over automatically — zero new entities, zero new
            # translations needed.
            #
            # Observed shape (per matthias0304 scout + pycupra precedent):
            #   engines.secondary.{range, fuelLevel_pct, fuelType}
            #
            # Field-name variants tried defensively because OLA has
            # historically shipped multiple spellings before settling.
            engines = v(mycar, "engines")
            if isinstance(engines, dict):
                secondary = v(engines, "secondary")
                if isinstance(secondary, dict):
                    # Range — Skoda uses ``distanceInKm``, OLA observed
                    # variants: ``range``, ``rangeInKm``, ``distanceInKm``.
                    sec_range = (
                        secondary.get("range")
                        or secondary.get("rangeInKm")
                        or secondary.get("distanceInKm")
                    )
                    if isinstance(sec_range, (int, float)):
                        d.secondary_engine_range_km = int(sec_range)
                    # Engine type — Skoda uses ``engineType``, OLA observed
                    # ``fuelType`` (per pycupra Formentor PHEV dump).
                    sec_type = (
                        secondary.get("fuelType")
                        or secondary.get("engineType")
                    )
                    if isinstance(sec_type, str) and sec_type:
                        d.secondary_engine_type = sec_type
                    # Fuel level % — Skoda uses ``currentFuelLevelInPercent``,
                    # OLA observed ``fuelLevel_pct``.
                    sec_fuel = (
                        secondary.get("fuelLevel_pct")
                        or secondary.get("currentFuelLevelInPercent")
                    )
                    if isinstance(sec_fuel, (int, float)):
                        d.secondary_engine_fuel_level_pct = int(sec_fuel)

                # v2.2.0 Phase 7 PR #3 — parse the engines.primary block.
                # Silenced via wildcard since v1.16.1 but never read.
                # 3 known keys per r1150gs scout #122 + pycupra references:
                # `fuelType`, `tankCapacity`, `range` (last one redundant
                # with the separate `ranges` block — skip).
                #
                # Same defensive multi-variant lookup as the secondary
                # block (Scout #232 / PR #18) — OLA has historically
                # shipped alternative spellings for the same semantic.
                primary = v(engines, "primary")
                if isinstance(primary, dict):
                    primary_type = (
                        primary.get("fuelType")
                        or primary.get("engineType")
                    )
                    if isinstance(primary_type, str) and primary_type:
                        d.primary_engine_type = primary_type
                    tank_cap = (
                        primary.get("tankCapacity")
                        or primary.get("tankCapacityInLiters")
                        or primary.get("tankSize")
                    )
                    if isinstance(tank_cap, (int, float)) and tank_cap > 0:
                        d.fuel_tank_capacity_liters = int(tank_cap)
                    # v2.8.1 #306 — primary engine residual range. Mirror
                    # of the secondary_engine_range_km field that has
                    # existed since v1.26.0 / Scout #232. Same field-name
                    # variants tried defensively.
                    prim_range = (
                        primary.get("range")
                        or primary.get("rangeInKm")
                        or primary.get("distanceInKm")
                    )
                    if isinstance(prim_range, (int, float)):
                        d.primary_engine_range_km = int(prim_range)
                    # v2.8.1 #306 — CNG tank level. Primary engine entry
                    # carries levelPct for CNG vehicles (Mii Ecofuel,
                    # Leon TGI). For PHEV-CNG dual-fuel the secondary
                    # block carries it instead; the secondary branch
                    # above already populated fuel_level_pct from the
                    # same field if applicable.
                    if (primary_type or "").lower() == "cng":
                        level = primary.get("levelPct") or primary.get("level_pct")
                        if isinstance(level, (int, float)):
                            d.cng_level_pct = int(level)
                        if isinstance(prim_range, (int, float)):
                            d.cng_range_km = int(prim_range)
                # v2.8.1 #306 — same CNG check on secondary block (some
                # PHEV-CNG dual-fuel SEAT vehicles ship CNG on secondary).
                secondary_check = v(engines, "secondary")
                if isinstance(secondary_check, dict):
                    sec_type_check = (
                        secondary_check.get("fuelType")
                        or secondary_check.get("engineType") or ""
                    )
                    if sec_type_check.lower() == "cng":
                        sec_level = (
                            secondary_check.get("levelPct")
                            or secondary_check.get("level_pct")
                            or secondary_check.get("fuelLevel_pct")
                        )
                        if isinstance(sec_level, (int, float)):
                            d.cng_level_pct = int(sec_level)
                        sec_range_check = (
                            secondary_check.get("range")
                            or secondary_check.get("rangeInKm")
                            or secondary_check.get("distanceInKm")
                        )
                        if isinstance(sec_range_check, (int, float)):
                            d.cng_range_km = int(sec_range_check)

        # ── Ranges ───────────────────────────────────────────────────────────
        # v2.5.3 (#306) — widened field-name coverage. PyCupra-style
        # alternatives observed across firmware generations: ``electricRange``
        # vs ``electricRangeInKm`` vs ``primaryEngineRange.remainingRangeInKm``;
        # ``gasolineRange``/``dieselRange`` vs ``combustionRangeInKm``;
        # ``totalRange`` vs ``totalRangeInKm``. First non-None wins.
        if isinstance(ranges, dict):
            electric = (
                v(ranges, "electricRange")
                or v(ranges, "electricRangeInKm")                           # v2.5.3
                or v(ranges, "primaryEngineRange", "remainingRangeInKm")    # v2.5.3
            )
            combustion = (
                v(ranges, "gasolineRange")
                or v(ranges, "dieselRange")
                or v(ranges, "combustionRangeInKm")                         # v2.5.3
                or v(ranges, "secondaryEngineRange", "remainingRangeInKm")  # v2.5.3
            )
            d.range_km = (
                electric
                or combustion
                or v(ranges, "totalRange")
                or v(ranges, "totalRangeInKm")                              # v2.5.3
            )
            d.has_combustion = combustion is not None
            d.adblue_range_km = (
                v(ranges, "adBlueRange")
                or v(ranges, "adBlueRangeInKm")                             # v2.5.3
            )

        # ── Detailed vehicle status (doors, windows, trunk) ──────────────────
        # OLA `/v2/vehicles/{vin}/status` for SEAT/CUPRA returns a structured
        # tree, NOT the flat ``doorsOpenedCount`` shape that CARIAD BFF uses.
        # The real shape (verified against `upstream/pycupra/vehicle.py` lines
        # ~3100–3325, the pycupra dashboard reads identical paths):
        #
        #   status:
        #     doors:
        #       frontLeft:  { locked: bool, open: bool }
        #       frontRight: { locked: bool, open: bool }
        #       rearLeft:   { locked: bool, open: bool }
        #       rearRight:  { locked: bool, open: bool }
        #     windows:
        #       frontLeft:  "closed" | "open"      # string state
        #       frontRight: "closed" | "open"
        #       rearLeft:   "closed" | "open"
        #       rearRight:  "closed" | "open"
        #       sunroof:    "closed" | "open"      # sometimes here, sometimes top-level
        #     trunk:   { open: bool, locked?: bool }
        #     hood:    { open: bool }              # newer firmware
        #     sunroof: "closed" | "open"           # legacy/alternative position
        #
        # Pre-v1.8.9 used CARIAD-BFF flat keys (``doorsOpenedCount``,
        # ``doorClosedLeftFront`` etc.) which do not exist on OLA — so for
        # CUPRA Born / Formentor / Tavascan the door, window, trunk, hood
        # and sunroof entities silently never populated. Fix verified via
        # pycupra source — the legacy-flat fallback below stays in place
        # for the rare model that sends the older shape.
        if isinstance(status, dict):
            access_s = v(status, "access") or status
            doors_obj = v(status, "doors") or {}
            windows_obj = v(status, "windows") or {}
            trunk_obj = v(status, "trunk") or {}
            hood_obj = v(status, "hood") or {}

            # v2.8.1 #306 — parking light flag. OLA exposes the top-level
            # ``status.lights`` enum ("on" / "off") on Born + Mii firmware.
            # Some newer firmware ships it under
            # ``status.lights.parkingLightState`` instead.
            lights_raw = v(status, "lights")
            if isinstance(lights_raw, str):
                d.parking_light = lights_raw.lower() == "on"
            elif isinstance(lights_raw, dict):
                pl_state = lights_raw.get("parkingLightState")
                if isinstance(pl_state, str):
                    d.parking_light = pl_state.lower() == "on"

            # Per-door (locked + open). Aggregate ``doors_open`` and
            # ``doors_locked`` are derived once we have the dict.
            door_individual: dict[str, bool] = {}
            for pos in ("frontLeft", "frontRight", "rearLeft", "rearRight"):
                door = v(doors_obj, pos) or {}
                if not door:
                    continue
                # ``open`` may be bool or "open"/"closed" string — normalise
                open_raw = door.get("open")
                if isinstance(open_raw, bool):
                    is_closed = not open_raw
                elif isinstance(open_raw, str):
                    is_closed = open_raw.lower() == "closed"
                else:
                    is_closed = None
                if is_closed is not None:
                    door_individual[pos] = is_closed
            if door_individual:
                d.doors_individual = door_individual
                d.doors_open = any(not closed for closed in door_individual.values())
                # ``doors_locked`` is True only when every position reports
                # locked=True. If any position doesn't report (None),
                # fall back to the access endpoint or stay False.
                locked_states = []
                for pos in ("frontLeft", "frontRight", "rearLeft", "rearRight"):
                    door = v(doors_obj, pos) or {}
                    locked = door.get("locked")
                    if locked is not None:
                        locked_states.append(bool(locked))
                if locked_states:
                    d.doors_locked = all(locked_states)

            # Per-window (string-state). New ``windows_individual`` dict
            # mirrors ``doors_individual`` so binary sensors can expose
            # one entity per window.
            window_individual: dict[str, bool] = {}
            for pos in ("frontLeft", "frontRight", "rearLeft", "rearRight"):
                wstate = v(windows_obj, pos)
                if isinstance(wstate, str):
                    window_individual[pos] = wstate.lower() == "closed"
                elif isinstance(wstate, bool):
                    # Some firmware returns bool. Convention: True == closed.
                    window_individual[pos] = wstate
            if window_individual:
                d.windows_individual = window_individual
                d.windows_open = any(not closed for closed in window_individual.values())

            # Trunk + hood — both as nested {open, locked}. Sunroof can be
            # at status.sunroof OR status.windows.sunroof (pycupra checks
            # both due to firmware variance).
            if trunk_obj:
                trunk_open = trunk_obj.get("open")
                if trunk_open is not None:
                    d.trunk_open = bool(trunk_open) if isinstance(trunk_open, bool) else trunk_open == "open"
                trunk_locked = trunk_obj.get("locked")
                if trunk_locked is not None:
                    d.trunk_locked = bool(trunk_locked)
            if hood_obj:
                hood_open = hood_obj.get("open")
                if hood_open is not None:
                    d.hood_open = bool(hood_open) if isinstance(hood_open, bool) else hood_open == "open"
            # Sunroof can be at three different positions depending on
            # firmware/model. Issue #5 (CC-seatcupra) confirms ``sunRoof``
            # (camelCase with capital R) as a top-level field on Seat Leon
            # KL — verified live. pycupra checks both ``sunroof`` and
            # ``windows.sunroof`` due to firmware variance. Accept all three.
            sunroof_state = (
                v(status, "sunRoof")                # CC-seatcupra #5 — verified
                or v(status, "sunroof")              # pycupra path
                or v(windows_obj, "sunroof")         # pycupra alternative
            )
            if isinstance(sunroof_state, str):
                d.sunroof_open = sunroof_state.lower() == "open"
            elif isinstance(sunroof_state, bool):
                d.sunroof_open = sunroof_state

            # Engine state — top-level field on OLA `/v2/vehicles/{vin}/status`.
            # CC-seatcupra issue #50 reports ``engine: 'on' | 'off'`` from
            # multiple users (Seat Leon KL, Cupra Born). When 'on' the car
            # is being driven; this is the only reliable signal for driving
            # state because the official ``vehicle.state`` field stays at
            # ``parked`` for many users (CC-seatcupra issue #18).
            engine_state = v(status, "engine")
            if isinstance(engine_state, str):
                d.is_driving = engine_state.lower() == "on"
                if d.is_driving:
                    d.vehicle_state = "DRIVING"

            # v1.10.2 (#53 Gerhard's Born Live-Dump 2026-04-30) — newer
            # OLA firmware ships flat top-level overall fields ALONGSIDE
            # the structured `doors`/`windows`/etc. tree. Use them as a
            # backstop when the structured tree didn't yield a value:
            #   status.locked        : true/false (overall door-locked)
            #   status.lights        : "off" / "on" (vehicle lights state)
            #   status.hood.locked   : "false"/"true" string
            top_locked = v(status, "locked")
            if isinstance(top_locked, bool):
                # v2.0.1 (#131 follow-up): always honour an explicit
                # top-level boolean. Pre-v2.0.1 used ``and not
                # d.doors_locked`` which shadowed the top-level signal
                # whenever the access-block already set False — but
                # access-block-False during a parser miss meant we'd
                # incorrectly skip the more authoritative top-level
                # signal. Now: explicit bool always wins.
                d.doors_locked = top_locked
            top_hood_locked = v(status, "hood", "locked")
            if isinstance(top_hood_locked, str) and d.hood_open is None:
                # hood.locked is the inverse of hood.open — only set if
                # we don't already have an explicit hood.open value.
                d.hood_open = top_hood_locked.lower() == "false"

            # ── Legacy CARIAD-BFF-style flat fallback ────────────────────
            # If the new structured paths produced nothing (older firmware,
            # corrupted response, or a future OLA API change) fall back to
            # the pre-v1.8.9 flat shape. Defensive only — should not fire
            # for any current SEAT/CUPRA model verified against pycupra.
            if not door_individual and not window_individual:
                d.doors_open = v(access_s, "doorsOpenedCount", default=0) > 0
                d.windows_open = v(access_s, "windowsOpenedCount", default=0) > 0
                if d.trunk_open is None:
                    d.trunk_open = v(access_s, "trunk") == "OPEN" or v(access_s, "trunkOpen") is True
                if d.trunk_locked is None:
                    d.trunk_locked = v(access_s, "trunkLocked") is True or v(access_s, "trunkStatus") == "LOCKED"
                if d.hood_open is None:
                    d.hood_open = v(access_s, "hood") == "OPEN" or v(access_s, "hoodOpen") is True
                if d.sunroof_open is None:
                    d.sunroof_open = v(access_s, "sunroof") == "OPEN" or v(access_s, "sunroofOpen") is True

                doors_legacy: dict[str, bool] = {}
                for key in ("doorClosedLeftFront", "doorClosedRightFront",
                            "doorClosedLeftBack", "doorClosedRightBack"):
                    val = v(access_s, key)
                    if val is not None:
                        door_id = (key.replace("doorClosed", "")
                                   .replace("LeftFront", "frontLeft")
                                   .replace("RightFront", "frontRight")
                                   .replace("LeftBack", "rearLeft")
                                   .replace("RightBack", "rearRight"))
                        # v1.8.10 hotfix: pre-v1.8.9 legacy code had
                        # ``doors_legacy[door_id] = not val`` which inverted
                        # the semantics — the field is named "doorClosed*"
                        # so ``True`` means the door IS closed, matching our
                        # ``doors_individual`` convention (True == closed).
                        # The accidental ``not val`` was caught by the v1.8.9
                        # regression test ``test_v189_status_legacy_flat_fallback_still_works``
                        # which failed in CI on the v1.8.9 PR (#82) but the
                        # PR was merged anyway because branch protection on
                        # required-checks isn't enabled.
                        doors_legacy[door_id] = bool(val)
                if doors_legacy:
                    d.doors_individual = doors_legacy

        # ── Charging status ──────────────────────────────────────────────────
        # OLA charging endpoint field-name variance. Path order is now
        # **real-world response first, legacy guesses last** (v1.8.9
        # methodology fix): the older paths in this file were inferred
        # from CARIAD-BFF / pycupra back when we had no live OLA dump.
        # Now that we have a verified live CUPRA Born response from
        # `upstream/cc-seatcupra` issue #109
        # (user "Rainer", 2026-03-27 — same OLA host, same brand),
        # those field names are known good and must be tried first so a
        # vehicle that returns BOTH shapes doesn't accidentally pick a
        # zero from a legacy field.
        #
        # /v1/vehicles/{vin}/charging — observed shapes:
        #   Real-world (Rainer #109 shape B):
        #     {"state": "notReadyForCharging", "chargedPowerInKw": 0.0,
        #      "remainingTimeInMinutes": 0, "type": "invalid", "mode": "manual"}
        #   Real-world (Rainer #109 shape A — same endpoint, alt firmware):
        #     {"status": "NotReadyForCharging", "currentPct": 43,
        #      "remainingTime": 0, "chargeMode": "manual",
        #      "preferredChargeMode": "manual", "active": false}
        #   Legacy (pre-v1.8.9 inferred, kept as defensive fallback):
        #     {"chargingState": ..., "chargePowerInKw": ...,
        #      "remainingTimeToFullyChargedInMinutes": ..., "chargeType": ...}
        if isinstance(charge_status, dict):
            bat = v(charge_status, "battery") or charge_status
            if d.battery_soc is None:
                # v1.10.2 (#53 — Gerhard's Born Live-Dump 2026-04-30):
                # newer OLA firmware ships ``battery.currentSocPercentage``
                # (camelCase, no underscores). Ranks first because Born
                # users on 2026+ firmware would otherwise see no SoC at
                # all — Rainer's #109 dump (used as v1.8.9 reference)
                # was already on a firmware that's been superseded.
                d.battery_soc = (
                    v(bat, "currentSocPercentage")        # Born 2026 firmware (#53)
                    or v(charge_status, "currentPct")  # Rainer #109 shape A — verified
                    or v(bat, "stateOfChargeInPercent")
                    or v(bat, "currentSOC_pct")
                )
                d.has_battery = d.battery_soc is not None

            # v2.5.9 (#331 matthias0304 + #332 ColinSainsbury — TWO CUPRA
            # Scout-Reports converging 2026-05-29). OLA backend now ships
            # ``battery.chargeEnergyInKwh`` — lifetime cumulative charge
            # energy delivered (kWh). Mirrors Skoda's
            # ``total_charged_energy_kwh`` (per #35 / v1.15.0) so the
            # cross-brand `sensor.total_charged_energy_kwh` Just Works.
            # Phantom-protected: only sets the field when the API returns
            # a non-None numeric value, so vehicles without this field
            # show no entity at all (HACS / SoC-pessimist owners stay
            # clean).
            charge_energy = v(bat, "chargeEnergyInKwh")
            if isinstance(charge_energy, (int, float)) and charge_energy >= 0:
                d.total_charged_energy_kwh = float(charge_energy)

            # v1.10.2 (#53 Gerhard) — ``battery.estimatedRangeInKm`` is the
            # new short field. Only sets ``range_km`` if not already set
            # by the dedicated ranges endpoint (which we prefer when
            # available since it splits electric vs. combustion).
            if d.range_km is None:
                est_range = v(bat, "estimatedRangeInKm")
                est_int = safe_int(est_range)
                if est_int is not None:
                    d.range_km = est_int
                    if d.electric_range_km is None:
                        d.electric_range_km = est_int

            chg = v(charge_status, "charging") or charge_status
            d.charging_state = (
                v(chg, "state")             # Rainer #109 shape B — verified
                or v(chg, "status")         # Rainer #109 shape A — verified
                or v(chg, "chargingState")  # Legacy — inferred pre-v1.8.9
            )
            # Charging-state values are camelCase or PascalCase depending on
            # firmware; treat case-insensitively. v1.10.2 (#53 Gerhard):
            # newer Born firmware ships purely lowercase camelCase like
            # ``"notReadyForCharging"``, ``"readyForCharging"``,
            # ``"charging"`` — the case-insensitive comparison already
            # covers it but we explicitly document the lowercase pattern.
            d.is_charging = (
                isinstance(d.charging_state, str)
                and d.charging_state.lower() == "charging"
            )
            d.charging_power_kw = (
                v(chg, "chargedPowerInKw")  # Rainer #109 shape B — verified
                or v(chg, "chargePowerInKw")  # Legacy
                or v(chg, "chargePower_kW")   # Legacy
            )
            d.charging_rate_kmh = (
                v(chg, "chargeRateInKmPerHour")  # Rainer #109 shape A
                or v(chg, "chargeRate_kmph")     # Legacy CARIAD path
                or v(chg, "rateInKmph")          # v2.0.1 Scout #192 — Cupra Born MY26 ships this on the OLA charging endpoint
            )
            remaining = (
                v(chg, "remainingTimeInMinutes")  # Rainer #109 shape B — verified
                or v(chg, "remainingTime")        # Rainer #109 shape A — verified
                or v(chg, "remainingTimeToFullyChargedInMinutes")  # Legacy
                or v(chg, "remainingChargingTime")                  # Legacy
            )
            # v1.10.1 (#58) — safe_int. Multiple OLA firmwares ship the
            # remaining-time field as a stringified decimal occasionally;
            # bare int() crashed the entire status parse pre-1.10.1.
            remaining_int = safe_int(remaining)
            if remaining_int:
                d.charge_complete_eta = datetime.now(tz=timezone.utc) + timedelta(minutes=remaining_int)
            d.charging_type = (
                v(chg, "type")          # Rainer #109 shape B — verified
                or v(chg, "chargeType")  # Legacy
                or v(chg, "chargingType")  # Legacy
            )

            plug = v(charge_status, "plug") or {}
            # v1.10.2 (#53 Gerhard's Born Live-Dump) — newer OLA firmware
            # uses short field names ``plug.connection`` and ``plug.lock``
            # plus lowercase enum values ("connected"/"disconnected",
            # "locked"/"unlocked"). The previous parser only knew
            # ``plug.connectionState=="CONNECTED"`` shape — Born owners
            # on 2026 firmware saw plug_connected=False even with cable
            # plugged in. Read all three field-name variants and compare
            # case-insensitively against both casings.
            plug_state_raw = (
                v(plug, "connection")          # Born 2026 firmware (#53)
                or v(plug, "connectionState")     # Rainer #109 shape
                or v(plug, "plugConnectionState")  # Legacy CARIAD
            )
            d.plug_state = plug_state_raw
            d.plug_connected = (
                isinstance(plug_state_raw, str)
                and plug_state_raw.lower() == "connected"
            )
            plug_lock_raw = (
                v(plug, "lock")                # Born 2026 firmware (#53)
                or v(plug, "lockState")           # Rainer #109 shape
                or v(plug, "plugLockState")        # Legacy CARIAD
            )
            ext_power = v(plug, "externalPower")
            # v2.0.1 (#131 follow-up) — only assign when at least one of
            # the two source fields is present. Pre-v2.0.1 always
            # assigned False when both were missing, masking a real
            # "still locked, can't unplug yet" state during parser miss.
            if isinstance(plug_lock_raw, str) or isinstance(ext_power, str):
                d.connector_locked = (
                    isinstance(plug_lock_raw, str)
                    and plug_lock_raw.lower() == "locked"
                ) or (
                    isinstance(ext_power, str) and ext_power.upper() == "READY"
                )

            # v2.8.1 #306 — external power availability bool. Distinct
            # from ``plug_connected`` (cable present): this signals
            # whether the wallbox / charger is actually feeding power
            # through the cable. "available" = station is energising.
            if isinstance(ext_power, str):
                d.external_power = ext_power.lower() in (
                    "available", "ready", "stationokay",
                )

            # v2.8.1 #306 — energy-flow direction. OLA exposes a
            # composite ``charging.status.state`` enum (idle / charging /
            # discharging / V2L_active / ...). Aggregate to a bool that
            # answers "is the battery currently exchanging energy".
            flow_state = v(chg, "state") or v(charge_status, "state")
            if isinstance(flow_state, str):
                d.energy_flow = flow_state.lower() in (
                    "charging", "discharging", "v2l_active",
                    "preconditioning",
                )

        # v2.8.1 #306 — battery-care mode flag. OLA ships this under
        # /v1/charging/info under chargingCareSettings on Born MY24+
        # firmware. Absent on older firmware where the value is always
        # False, so default to None when the key is missing so the
        # sensor's phantom gate hides it.
        if isinstance(charge_info, dict):
            care_block = (
                v(charge_info, "chargingCareSettings")
                or v(charge_info, "settings", "chargingCareSettings")
            )
            if isinstance(care_block, dict):
                care_mode = care_block.get("batteryCareMode")
                if isinstance(care_mode, bool):
                    d.battery_care = care_mode

        # ── Charging info (settings) ─────────────────────────────────────────
        # OLA `/v2/vehicles/{vin}/charging/settings` field variance.
        # Real-world (Rainer #109): {"targetSoc_pct": 80, "maxChargeCurrentAC":
        # "maximum", "autoUnlockPlugWhenCharged": "off" | "on" | "permanent"}.
        # The "permanent" value is documented in issue #51 and means the
        # connector unlocks at any SoC, not just at full charge — so
        # ``auto_unlock_charge`` is True for both "on" and "permanent".
        if isinstance(charge_info, dict):
            d.target_soc = (
                v(charge_info, "targetSoc_pct")  # Rainer #109 — verified
                or v(charge_info, "targetSOC_pct")          # Legacy uppercase
                or v(charge_info, "targetStateOfChargeInPercent")  # Legacy verbose
            )
            d.max_charge_current = v(charge_info, "maxChargeCurrentAC") or v(charge_info, "maxChargeCurrent")
            auto_raw = v(charge_info, "autoUnlockPlugWhenCharged")
            auto_str = auto_raw.lower() if isinstance(auto_raw, str) else None
            d.auto_unlock_charge = (
                # #51: "permanent" is also "yes, unlock". Only "off"/None means no.
                auto_str in ("on", "permanent")
                or v(charge_info, "autoUnlockPlugWhenChargedAC") is True
            )

        # ── Climate ──────────────────────────────────────────────────────────
        # CC-seatcupra issue #21 + #8 documented that ``climatisationTrigger``
        # can return ``"unsupported"`` on older Born firmware; pre-v1.8.9
        # treated this state as if the climate was off (since it didn't
        # match "off"/"on" exactly), which still happened to be correct,
        # but a bool ``is_climate_supported`` would let entity platforms
        # hide controls cleanly. For v1.8.9 we keep ``climatisation_active``
        # behaviour stable and just ensure ``"off"``, ``"OFF"``,
        # ``"unsupported"``, and any ``None`` all evaluate to False.
        if isinstance(climate, dict):
            cs = v(climate, "status") or climate
            d.climatisation_state = v(cs, "climatisationState") or v(cs, "state")
            _inactive_states = (None, "OFF", "off", "Off", "unsupported")
            d.climatisation_active = d.climatisation_state not in _inactive_states
            d.target_temperature = v(climate, "settings", "targetTemperature_K")
            # v1.24.2 (audit): safe_float for Kelvin → Celsius
            target_k = safe_float(d.target_temperature)
            if target_k is not None:
                d.target_temperature = round(target_k - 273.15, 1)
            if not d.target_temperature:
                # `targetTemperatureCelsius` (no "In") is the Rainer #109
                # Live-response variant; `targetTemperatureInCelsius` is the
                # newer settings-endpoint variant. Try both.
                d.target_temperature = (
                    v(climate, "settings", "targetTemperatureInCelsius")
                    or v(cs, "targetTemperatureCelsius")  # Rainer #109
                )
            d.outside_temp = v(cs, "outsideTemperature")
            # v1.24.2 (audit): safe_float defensive coerce for Kelvin → Celsius.
            # > 100 heuristic distinguishes Kelvin (Skoda/CUPRA returns ~280-310 K)
            # from already-converted Celsius values.
            outside = safe_float(d.outside_temp)
            if outside is not None and outside > 100:
                d.outside_temp = round(outside - 273.15, 1)
            d.window_heating_front = v(cs, "windowHeatingStateFront") == "ON"
            d.window_heating_back = v(cs, "windowHeatingStateRear") == "ON"
            # v2.8.1 #306 — seat heating overall aggregate. OLA ships
            # ``airConditioning.seatHeatingSupport`` as a dict keyed by
            # seat position (frontLeft, frontRight, ...). Any seat in
            # ``"on"`` state flips the aggregate True.
            seat_block = v(climate, "seatHeatingSupport") or v(cs, "seatHeatingStatus")
            if isinstance(seat_block, dict):
                for entry in seat_block.values():
                    state = entry if isinstance(entry, str) else (
                        entry.get("state") if isinstance(entry, dict) else None
                    )
                    if isinstance(state, str) and state.lower() == "on":
                        d.seat_heating = True
                        break
                else:
                    d.seat_heating = False
            elif isinstance(seat_block, list):
                d.seat_heating = any(
                    isinstance(e, dict) and str(e.get("state", "")).lower() == "on"
                    for e in seat_block
                )

        # ── Parking ──────────────────────────────────────────────────────────
        # v2.0.0 (#53 follow-up to v1.27.1): defensive `data` envelope unwrap.
        # Cariad-BFF returns `{"data": {"lat": ..., "lon": ...}}`; OLA backend
        # may follow the same convention (some OLA versions wrap, some don't).
        # Without unwrap, `parking.get("lat")` returned None silently → no GPS
        # → command_flash always failed our pre-validation. Now unwraps `data`
        # transparently with fallback to top-level for backwards compat.
        if isinstance(parking, dict):
            _maybe_data = parking.get("data")
            parking_data: dict[str, Any] = _maybe_data if isinstance(_maybe_data, dict) else parking
            d.latitude = v(parking_data, "lat")
            d.longitude = v(parking_data, "lon")
            # v1.25.0 PR-A — Cross-brand parity: parking_address from
            # OLA backend if present (Skoda has it via mysmob since
            # v1.20.0). Tries common field names defensively. Saves
            # an HA reverse-geocoding round-trip when the backend
            # already supplied it.
            addr = (
                v(parking_data, "address", "formattedAddress")
                or v(parking_data, "formattedAddress")
                or v(parking_data, "address")
            )
            if isinstance(addr, str) and addr:
                d.parking_address = addr

            # v2.4.1 — Scout Policy Compliance Audit T1: parking map
            # renders. OLA's parkingposition endpoint includes Google-
            # Maps-style URLs (dark + light theme) of the parking
            # location. Useful for Lovelace cards that want to show a
            # static map without hitting Google Maps API directly.
            maps_data = v(parking_data, "maps") or {}
            if isinstance(maps_data, dict):
                dark = maps_data.get("darkMapUrl")
                light = maps_data.get("lightMapUrl")
                if isinstance(dark, str) and dark:
                    d.parking_map_url_dark = dark
                if isinstance(light, str) and light:
                    d.parking_map_url_light = light

        # ── Maintenance ──────────────────────────────────────────────────────
        # v2.5.3 (#306) — widened field-name coverage. PyCupra ports show
        # the OLA backend has shipped at least 3 naming conventions for
        # the same field across firmware generations. Order: snake_case →
        # camelCase → ``*InKm``/``*InDays`` (myskoda-style). First non-None
        # wins, so newer responses fall through cleanly.
        if isinstance(maintenance, dict):
            d.service_km = (
                v(maintenance, "inspectionDue_km")
                or v(maintenance, "distanceToInspection")
                or v(maintenance, "inspectionDueInKm")              # v2.5.3
                or v(maintenance, "mileageRemainingForInspection")  # v2.5.3 (Leon FR-KL variant)
            )
            d.service_due_at = (
                v(maintenance, "inspectionDue_days")
                or v(maintenance, "daysToInspection")
                or v(maintenance, "inspectionDueInDays")            # v2.5.3
                or v(maintenance, "timeRemainingForInspection")     # v2.5.3
            )
            d.oil_service_km = (
                v(maintenance, "oilServiceDue_km")
                or v(maintenance, "distanceToOilChange")
                or v(maintenance, "oilServiceDueInKm")              # v2.5.3
                or v(maintenance, "mileageRemainingForOilService")  # v2.5.3
            )
            d.oil_service_at = (
                v(maintenance, "oilServiceDue_days")
                or v(maintenance, "daysToOilChange")
                or v(maintenance, "oilServiceDueInDays")            # v2.5.3
                or v(maintenance, "timeRemainingForOilService")     # v2.5.3
            )
            # v2.8.1 #306 — AdBlue tank level (%). OLA ships this under
            # an opaque code key on diesel vehicles with SCR. Field-name
            # variants tried defensively since OLA has shipped both the
            # human-readable ``adblueLevel`` and the legacy CARIAD-style
            # ``0x02040C0001`` code key (per pycupra reference).
            adblue_lvl = (
                v(maintenance, "adblueLevel")
                or v(maintenance, "adBlueLevel")
                or v(maintenance, "0x02040C0001", "value")
            )
            if isinstance(adblue_lvl, (int, float)):
                d.adblue_level_pct = int(adblue_lvl)
            # v2.8.0 quick win C — brake-service + preferred-workshop.
            # OLA exposes both on the same /maintenance response when
            # the dealer has wired up the vehicle's service plan.
            # Field names mirror the Skoda mysmob shape so we accept
            # either variant; OLA-specific keys take precedence when
            # both are present.
            brake_fluid_raw = (
                v(maintenance, "brakeFluidChangeDueInDays")
                or v(maintenance, "brakeFluidServiceDueInDays")
                or v(maintenance, "brakeFluidChange_days")
            )
            d.brake_fluid_change_due_at = days_or_date_to_iso(brake_fluid_raw)
            front_pads_raw = (
                v(maintenance, "brakePadsFrontInspectionDueInDays")
                or v(maintenance, "brakePadFrontInspectionDueInDays")
            )
            d.brake_pads_front_inspection_due_at = days_or_date_to_iso(
                front_pads_raw
            )
            rear_pads_raw = (
                v(maintenance, "brakePadsRearInspectionDueInDays")
                or v(maintenance, "brakePadRearInspectionDueInDays")
            )
            d.brake_pads_rear_inspection_due_at = days_or_date_to_iso(
                rear_pads_raw
            )
            workshop = (
                v(maintenance, "preferredServicePartner")
                or v(maintenance, "preferredDealer")
            )
            if isinstance(workshop, dict) and workshop:
                d.preferred_workshop_name = normalize_workshop_string(
                    workshop.get("name") or workshop.get("displayName")
                )
                d.preferred_workshop_address = compose_workshop_address(
                    workshop.get("address") or workshop.get("location")
                )
                d.preferred_workshop_phone = workshop_phone_from_contact(
                    workshop.get("contact") or workshop
                )

        # ── v2.5.3 — /v1/mileage fallback (#306 Mii/Tavascan/Leon FR-KL) ────
        # PyCupra dedicates an entire endpoint to the cached odometer
        # because the OLA backend serves this value even when ``/v5/mycar``
        # returns null measurements (offline vehicle). We only consume the
        # value as a FALLBACK — when ``mycar.measurements.mileage.value``
        # successfully populated ``d.odometer_km`` above, we keep that
        # (it's the freshest signal). When mycar was offline / empty, the
        # /v1/mileage response carries the last server-cached value.
        if isinstance(mileage_v1, dict) and d.odometer_km is None:
            # Field-name variants observed across firmware generations.
            odo = (
                v(mileage_v1, "mileageInKm")
                or v(mileage_v1, "mileage")
                or v(mileage_v1, "odometer")
                or v(mileage_v1, "currentMileage")
                or v(mileage_v1, "value")
            )
            if isinstance(odo, (int, float)) and odo > 0:
                d.odometer_km = int(odo)
                _LOGGER.debug(
                    "OLA v1 mileage fallback (%s): odometer_km=%d (mycar was null)",
                    vin[-6:], d.odometer_km,
                )

        # ── v2.5.3 — doors_locked consistency safeguard (#306 follow-on) ────
        # When the OLA backend serves stale-cached data (typical when the
        # vehicle is offline), the per-door ``open`` flags may report
        # ``true`` while the door-lock state is ``LOCKED`` — physically
        # impossible since you can't open a locked door. The lock state
        # is more reliable than per-door position because the lock is a
        # binary discrete signal while position uses analog sensors that
        # can stick at the last-seen value. When the two contradict, trust
        # the lock and force per-door + rollup to "closed".
        if d.doors_locked is True and d.doors_open is True:
            _LOGGER.debug(
                "OLA stale-data safeguard (%s): doors_locked=True but "
                "doors_open=True — forcing doors closed (lock implies closed)",
                vin[-6:],
            )
            d.doors_open = False
            if d.doors_individual:
                # True == closed per the upstream parser convention.
                d.doors_individual = {
                    pos: True for pos in d.doors_individual
                }

        # ── Availability ─────────────────────────────────────────────────────
        if isinstance(availability, dict):
            d.is_online = v(availability, "isOnline") is True or v(availability, "status") == "ONLINE"

        # ── Image data ───────────────────────────────────────────────────────
        img = self._image_data.get(vin)
        if img:
            d.image_urls = img.image_urls
            d.media_short_name = img.short_name
            d.media_long_name = img.long_name
            d.media_exterior_color = img.exterior_color

        # ── Drivetrain ───────────────────────────────────────────────────────
        d.is_electric = d.has_battery and not d.has_combustion
        d.is_hybrid = d.has_battery and d.has_combustion

        # v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation.
        # CUPRA/SEAT OLA doesn't ship a direct `carType` field —
        # derive from has_battery + has_combustion + primary_engine_type.
        # Never overwrites a directly-read value (would be no-op if
        # OLA ever ships the field — defensive forward-compat).
        from .._util import derive_car_type_if_missing  # noqa: PLC0415

        derive_car_type_if_missing(d)

        # ── carCapturedTimestamp → connection_state (v1.8.12 Multi-Brand) ────
        # OLA backend returns ``carCapturedTimestamp`` on multiple
        # sub-responses (verified live in
        # `upstream/cc-seatcupra` issue #109,
        # Rainer's CUPRA Born 2026-03-27 dump shows it on
        # ``climatisationStatus`` and ``chargingSettings``).
        # Same Pattern as Škoda + VW EU; helper handles nested paths and
        # both string + datetime values.
        # v2.5.3 (#306) — include mileage_v1 because OLA stamps its
        # cached responses with ``carCapturedTimestamp`` and the v1
        # mileage block is often newer than the v5/mycar block on
        # offline vehicles (server keeps refreshing the cached value
        # opportunistically when the car briefly checks in).
        d.connection_state, d.last_seen_at = compute_connection_state(
            mycar, parking, ranges, status, charge_status, charge_info,
            climate, maintenance, availability, mileage_v1,
        )

        return d

    # ── Commands ─────────────────────────────────────────────────────────────

    async def _get_sec_token(self, spin: str) -> str:
        """Verify the S-PIN against OLA and return a SecToken.

        SEAT/CUPRA lock/unlock both require a per-call SecToken obtained
        from a separate `spin/verify` POST. Pycupra does this verbatim:
        POST `/v2/users/{userId}/spin/verify` with ``{"spin": "<pin>"}``,
        read ``securityToken`` from the response, then send that as the
        ``SecToken`` header on the actual lock/unlock POST.

        The S-PIN is passed plain — there's no client-side hashing,
        challenge/response or RSA. The OLA backend handles verification.
        """
        if not spin:
            raise SpinError("S-PIN required for SEAT/CUPRA lock/unlock.")
        if not self._user_id:
            await self._fetch_user_id()
        url = f"{_BASE}/v2/users/{self._user_id}/spin/verify"
        try:
            resp = await self._post(url, json={"spin": spin})
        except APIError as err:
            # 400/401 from /spin/verify means the PIN is wrong or the
            # account is locked. Surface a SpinError so HA can show the
            # right reauth/correct-pin prompt instead of a raw API error.
            raise SpinError(
                f"S-PIN verification failed (HTTP {getattr(err, 'status', '?')}). "
                "Update the S-PIN in the integration options."
            ) from err
        token = (resp or {}).get("securityToken") if isinstance(resp, dict) else None
        if not token:
            raise SpinError("S-PIN verify returned no securityToken.")
        return str(token)

    async def command_lock(self, vin: str) -> None:
        """Lock the vehicle. Requires a verified S-PIN SecToken."""
        token = await self._get_sec_token(self._spin)
        # Empty body is intentional — pycupra/OLA expect no payload here,
        # only the SecToken header. _request adds the Authorization +
        # Content-Type headers automatically.
        await self._post(
            f"{_BASE}/v1/vehicles/{vin}/access/lock",
            headers={"SecToken": token},
        )

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        """Unlock the vehicle. Requires a verified S-PIN SecToken."""
        token = await self._get_sec_token(spin or self._spin)
        await self._post(
            f"{_BASE}/v1/vehicles/{vin}/access/unlock",
            headers={"SecToken": token},
        )

    async def command_start_climate(self, vin: str) -> None:
        """v1.16.1 (#53 Gerhard CUPRA Born) — Fix 404 climatisation.

        OLA returns ``404 No static resource v2/vehicles/{vin}/climati``
        when posting ``{"action": "start"}`` to the bare endpoint. The
        action lives in the URL path, not the body — verified against
        ``upstream/pycupra/connection.py`` (``API_CLIMATER + '/start'``).

        Defensive: try the verified ``/start`` path first; on 404 fall
        back to the legacy bare endpoint with body action so any account
        that the legacy URL DID work for is not broken.
        """
        await self._post_climatisation_action(vin, "start")

    async def command_stop_climate(self, vin: str) -> None:
        """v1.16.1 (#53) — same fix as start."""
        await self._post_climatisation_action(vin, "stop")

    async def _post_climatisation_action(self, vin: str, action: str) -> None:
        """v1.16.1 (#53) — climatisation start/stop with v1/v2 fallback.

        Now uses generic ``_post_with_ab_fallback`` (v1.17.1).
        """
        await self._post_with_ab_fallback(
            primary_url=f"{_BASE}/v2/vehicles/{vin}/climatisation/{action}",
            primary_json={},
            fallback_url=f"{_BASE}/v2/vehicles/{vin}/climatisation",
            fallback_json={"action": action},
            label=f"climatisation {action}",
            vin=vin,
        )

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
        """v1.17.1 — generic A/B fallback POST.

        Try ``primary_url`` first. On 404 (only), fall back to
        ``fallback_url``. Non-404 errors propagate so Phase 2's
        ``classify_command_failure`` records subscription/spin/etc.
        properly.

        Pattern proven in v1.16.1 climatisation fix; extracted in
        v1.17.1 for reuse across the Bruno-Collection-discovered
        endpoints (window heating, ventilation, aux-heating,
        charging-requests/start, capabilities path, etc.) where
        Bruno + pycupra disagree on the exact path or where Cariad
        is in the middle of migrating away from ``/v1`` prefixes.
        """
        from ..exceptions import APIError  # noqa: PLC0415

        # base.py::_request does ``headers = kwargs.pop("headers", {})``
        # which returns None (not {}) if ``headers=None`` is explicitly
        # passed — that breaks downstream `headers["Authorization"] = ...`.
        # So only forward the headers kwarg when we actually have headers.
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
                "OLA %s: 404 on primary %s — falling back to legacy %s "
                "(vin ***%s)",
                label, primary_url, fallback_url, vin[-6:],
            )
        fallback_kwargs: dict[str, Any] = {"json": fallback_json}
        if fallback_headers:
            fallback_kwargs["headers"] = fallback_headers
        await self._post(fallback_url, **fallback_kwargs)

    async def command_start_charging(self, vin: str) -> None:
        """v1.17.1 — A/B fallback after Bruno-Collection research.

        Bruno (seq 47): POST /vehicles/{vin}/charging/requests/start (no /v1, no body)
        Pre-v1.17.1: POST /v1/vehicles/{vin}/charging/actions body {"action":"start"}

        Bruno suggests Cariad migrated some endpoints away from /v1.
        Try Bruno path first; fall back to legacy /v1/.../actions on 404.
        """
        await self._post_with_ab_fallback(
            primary_url=f"{_BASE}/vehicles/{vin}/charging/requests/start",
            primary_json=None,
            fallback_url=f"{_BASE}/v1/vehicles/{vin}/charging/actions",
            fallback_json={"action": "start"},
            label="charging start",
            vin=vin,
        )

    async def command_stop_charging(self, vin: str) -> None:
        """v1.17.1 — A/B fallback. See command_start_charging doc."""
        await self._post_with_ab_fallback(
            primary_url=f"{_BASE}/vehicles/{vin}/charging/requests/stop",
            primary_json=None,
            fallback_url=f"{_BASE}/v1/vehicles/{vin}/charging/actions",
            fallback_json={"action": "stop"},
            label="charging stop",
            vin=vin,
        )

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        """SEAT/CUPRA honk-and-flash.

        The OLA endpoint requires a `userPosition` field; without it the API
        returns HTTP 400 "internal-error". Mode must be lowercase "flash"
        (not "FLASH_ONLY"). Coordinates are truncated to 4 decimals (~11 m).

        ️ **[Inference] — semantic interpretation NOT verified against
        official My SEAT / My CUPRA app traffic.**

        We send the **vehicle's** last-known position rather than the
        user's phone GPS, because:

        - **Verified**: pycupra `vehicle.set_honkandflash` reads
          `findCarResponse.lat/lon` (vehicle position).
        - **Verified**: myskoda equivalent sends `PositionType.VEHICLE`.
        - **NOT verified**: whether the official My SEAT/CUPRA mobile
          apps populate the field from phone GPS or from the cached
          last-known vehicle position. We have NOT captured app traffic
          to confirm.

        Pragmatically the OLA endpoint accepts vehicle coordinates
        (verified live across multiple users on #53). The field name
        ``userPosition`` is likely a misnomer in the OLA contract — it
        appears to act as a server-side sanity token bound to *some*
        recent location. If a future capture of My SEAT/CUPRA app
        traffic shows it actually wants phone GPS, this needs revisiting.

        Status: **WORKING** for OLA endpoint, **INFERENCE** for
        semantic mapping to the official apps.
        """
        # v2.0.0 (#53 Gerhard CUPRA Born): try the call WITHOUT userPosition
        # first. Some firmware variants accept the bare body with just
        # ``mode``; only fall back to enforcing position if backend returns 400.
        # This unblocks users whose vehicle has never reported a recent GPS
        # position (first-install before first status poll, privacy-mode
        # suppressed GPS, etc.).
        url = f"{_BASE}/v1/vehicles/{vin}/honk-and-flash"
        try:
            await self._post(url, json={"mode": "flash"})
            return
        except APIError as exc:
            if exc.status != 400:
                raise
            # 400 from backend → likely the userPosition validation.
            # Retry with position if cached; otherwise raise an actionable
            # error explaining what to check.
            if latitude is None or longitude is None:
                raise APIError(
                    400,
                    url,
                    "honk-and-flash failed: backend rejected the bare body "
                    "(needs userPosition) AND no GPS position is cached for "
                    "this vehicle. Press the wake button first to force a "
                    "status poll, wait ~30s, then retry. If GPS stays empty, "
                    "check whether privacy-mode is enabled in the car's "
                    "head-unit settings.",
                ) from exc
            body = {
                "mode": "flash",
                "userPosition": {
                    "latitude": int(latitude * 10000) / 10000,
                    "longitude": int(longitude * 10000) / 10000,
                },
            }
            await self._post(url, json=body)

    async def command_wake(self, vin: str) -> None:
        await self._post(f"{_BASE}/v1/vehicles/{vin}/vehicle-wakeup/request", json={})

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        await self._post(
            f"{_BASE}/v1/vehicles/{vin}/charging/actions",
            json={"action": "settings", "targetSOC_pct": target},
        )

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        await self._post(
            f"{_BASE}/v2/vehicles/{vin}/climatisation",
            json={"action": "settings", "targetTemperature_K": temp_c + 273.15},
        )

    async def command_start_window_heating(self, vin: str) -> None:
        """v1.17.1 — A/B fallback after Bruno-Collection research.

        Bruno (Timwun/Cupra-WeConnect-Bruno-Collection seq 50):
            POST /vehicles/{vin}/windowheating/requests/start (no /v1)
        Legacy (our pre-v1.17.1 path):
            POST /v2/vehicles/{vin}/climatisation
                 body={"action":"startWindowHeating"}

        We don't know which Cariad-firmware-cohort uses which — try the
        Bruno-verified path first, fall back to legacy on 404.
        """
        await self._post_with_ab_fallback(
            primary_url=f"{_BASE}/vehicles/{vin}/windowheating/requests/start",
            primary_json=None,
            fallback_url=f"{_BASE}/v2/vehicles/{vin}/climatisation",
            fallback_json={"action": "startWindowHeating"},
            label="window heating start",
            vin=vin,
        )

    async def command_stop_window_heating(self, vin: str) -> None:
        """v1.17.1 — A/B fallback. See command_start_window_heating doc."""
        await self._post_with_ab_fallback(
            primary_url=f"{_BASE}/vehicles/{vin}/windowheating/requests/stop",
            primary_json=None,
            fallback_url=f"{_BASE}/v2/vehicles/{vin}/climatisation",
            fallback_json={"action": "stopWindowHeating"},
            label="window heating stop",
            vin=vin,
        )

    # ── v1.17.1 — Bruno-Collection new commands ────────────────────────

    async def command_start_ventilation(self, vin: str) -> None:
        """v1.17.1 (Bruno seq 31) — Cabin ventilation (without heating).

        Endpoint: ``POST /v1/vehicles/{vin}/ventilation/start`` — no body.
        New OLA feature; NEVER existed in our integration before. No
        legacy fallback path possible. On 404 the per-VIN capability
        gate (Phase 3) catches it next reload.
        """
        await self._post(
            f"{_BASE}/v1/vehicles/{vin}/ventilation/start", json={}
        )

    async def command_stop_ventilation(self, vin: str) -> None:
        """v1.17.1 (Bruno seq 32) — Stop ventilation."""
        await self._post(
            f"{_BASE}/v1/vehicles/{vin}/ventilation/stop", json={}
        )

    async def command_start_aux_heating(
        self,
        vin: str,
        spin: str = "",
        **_ignored: Any,
    ) -> None:
        """v1.17.1 (Bruno seq 29 + pycupra) — Webasto auxiliary heating.

        SEAT/CUPRA PHEV/ICE Standheizung remote-start. Requires SecToken
        derived from S-PIN — same flow as ``command_lock`` /
        ``command_unlock`` (verified against pycupra).

        URL conflict between sources:
        - Bruno (seq 29):
            POST /v1/vehicles/{vin}/auxiliary-heating/start  + SecToken
        - Pycupra (`API_AUXILIARYHEATING`):
            POST /api/auxiliary-heating/v1/{vin}/start  + SecToken

        We try Bruno's path first (Bruno specs are typically newer), fall
        back to pycupra's on 404. Both verified to require SecToken on
        START (stop does not — see ``command_stop_aux_heating``).

        v2.8.0: ``**_ignored`` accepts ``duration_min`` / ``target_c``
        kwargs that the v2.8.0 Audi + VW EU client uses. OLA's
        ``auxiliary-heating/start`` endpoint takes no body, so we
        silently drop those kwargs on this brand path.
        """
        if not (spin or self._spin):
            raise SpinError(
                "S-PIN required for SEAT/CUPRA auxiliary heating start"
            )
        sec_token = await self._get_sec_token(spin or self._spin)
        await self._post_with_ab_fallback(
            primary_url=f"{_BASE}/v1/vehicles/{vin}/auxiliary-heating/start",
            primary_json={},
            fallback_url=(
                f"{_BASE}/api/auxiliary-heating/v1/{vin}/start"
            ),
            fallback_json={},
            label="aux-heating start",
            vin=vin,
            primary_headers={"SecToken": sec_token},
            fallback_headers={"SecToken": sec_token},
        )

    async def command_stop_aux_heating(self, vin: str) -> None:
        """v1.17.1 — Webasto stop. No SecToken (Bruno seq 30 confirmed)."""
        await self._post_with_ab_fallback(
            primary_url=f"{_BASE}/v1/vehicles/{vin}/auxiliary-heating/stop",
            primary_json={},
            fallback_url=(
                f"{_BASE}/api/auxiliary-heating/v1/{vin}/stop"
            ),
            fallback_json={},
            label="aux-heating stop",
            vin=vin,
        )

    async def get_battery_care(self, vin: str) -> dict[str, Any]:
        """v1.17.1 (Bruno seq 10) — Battery-care current status.

        ``GET /v1/vehicles/{vin}/charging/battery-care``
        Response: ``{"enabled": bool}``

        Best-effort: 404 → ``{}`` so coordinator's ``_DATA_PRESENT_REQUIRED``
        gate skips the entity rather than showing "unknown".
        """
        from ..exceptions import APIError  # noqa: PLC0415
        try:
            data = await self._get(
                f"{_BASE}/v1/vehicles/{vin}/charging/battery-care"
            )
            return data if isinstance(data, dict) else {}
        except APIError as err:
            if err.status == 404:
                return {}
            raise

    async def get_battery_care_target(self, vin: str) -> dict[str, Any]:
        """v1.17.1 (Bruno seq 11) — Battery-care target SoC.

        ``GET /v1/vehicles/{vin}/charging/battery-care/target``
        Response: ``{"targetSocPercentage": int}``
        """
        from ..exceptions import APIError  # noqa: PLC0415
        try:
            data = await self._get(
                f"{_BASE}/v1/vehicles/{vin}/charging/battery-care/target"
            )
            return data if isinstance(data, dict) else {}
        except APIError as err:
            if err.status == 404:
                return {}
            raise

    async def command_send_destination(
        self,
        vin: str,
        latitude: float,
        longitude: float,
        name: str,
        *,
        city: str = "",
        country: str = "",
        state: str = "",
        street: str = "",
        house_number: str = "",
        zip_code: str = "",
        poi_provider: str = "vagOlaIntegration",
    ) -> None:
        """v1.17.1 (#36, Bruno seq 34) — Send destination to vehicle nav.

        Endpoint: ``PUT /v1/users/vehicles/{vin}/destination``
        Note the URL pattern omits ``{userId}`` — Bruno-verified literal.
        Body is a JSON ARRAY (not object) of destination dicts.

        We send a single destination per call; the API supports a list
        but most automations send one address at a time.

        ️ [Inference] — only Bruno cites this URL; pycupra source
        doesn't have a destination endpoint we could cross-validate
        against. Ship behind a capability gate (``command_send_destination``
        cap-id) plus per-call exception handling so a single 404 doesn't
        wreck other commands.
        """
        body = [{
            "address": {
                "city": city,
                "country": country,
                "state": state,
                "street": street,
                "houseNumber": house_number,
                "zipCode": zip_code,
            },
            "poiProvider": poi_provider,
            "geoCoordinate": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "destinationName": name,
        }]
        url = f"{_BASE}/v1/users/vehicles/{vin}/destination"
        await self._request("PUT", url, json=body)
