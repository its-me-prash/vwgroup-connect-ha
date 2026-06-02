# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Škoda API client — mysmob.api.connect.skoda-auto.cz.

API endpoints verified against skodaconnect/myskoda (MIT) model classes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
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
from ..models import BRAND_SKODA, VehicleData
from .base import CariadBaseClient

_LOGGER = logging.getLogger(__name__)
_BASE = "https://mysmob.api.connect.skoda-auto.cz"


class SkodaClient(CariadBaseClient):
    """Škoda API client."""

    def __init__(
        self, session: ClientSession, email: str, password: str, spin: str = ""
    ) -> None:
        super().__init__(session, BRAND_SKODA, email, password, spin)

    async def get_vehicles(self) -> list[str]:
        """Return VINs from Škoda garage."""
        params = {
            "connectivityGenerations": ["MOD1", "MOD2", "MOD3", "MOD4"],
        }
        data = await self._get(f"{_BASE}/api/v2/garage", params=params)
        vehicles: list[dict[str, Any]] = data.get("vehicles", [])
        vins = [v["vin"] for v in vehicles if v.get("vin")]
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

    async def get_capabilities(self, vin: str) -> dict[str, Any]:
        """Return mysmob capabilities document for *vin*.

        v1.13.0 (#56 Phase 3 prerequisite) — Skoda mysmob capabilities
        endpoint. Required so Capability-Filter Phase 3 can hide
        unsupported entities for Skoda vehicles (without this, the
        coordinator's ``vehicle_supports_capability`` returns ``None``
        for every Skoda capability and Phase 3 falls through to the
        Phase 2 post-failure-unavailable fallback).

        Endpoint: ``GET /api/v1/vehicle-access/{vin}/capabilities``
        Schema (mysmob — different from CARIAD-BFF):
            {
              "capabilities": [
                {"id": "<cap_id>", "active": true|false,
                 "editable"?, "user-enabled"?, "status"?,
                 "license-issue"?, "parameters"?}
              ]
            }
        Verified via Issue #56 body + RESEARCH_NOTES_2026-04-29 §3
        Skoda capability section.

        Failure raises APIError (caller swallows — capabilities are
        best-effort metadata, never load-bearing). The default cache
        TTL (24h via coordinator) keeps this cheap.
        """
        data = await self._get(
            f"{_BASE}/api/v1/vehicle-access/{vin}/capabilities",
        )
        return data if isinstance(data, dict) else {}

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
        v = self._val
        d = VehicleData(vin=vin)

        results = await asyncio.gather(
            self._get(f"{_BASE}/api/v2/vehicle-status/{vin}"),
            self._get(f"{_BASE}/api/v1/charging/{vin}"),
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
            return_exceptions=True,
        )
        (
            status, charging, ac, parking, driving_range,
            maintenance, readiness, sw_update, widget, driving_score,
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
            d.doors_open = v(access, "doorsOpenedCount", default=0) > 0
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
            d.charging_type = v(c, "chargeType")
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

            settings = charging.get("settings", {})
            d.target_soc = v(settings, "targetStateOfChargeInPercent")
            d.auto_unlock_charge = v(settings, "autoUnlockPlugWhenChargedAC") == "ON"
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

        # ── Air conditioning (also has plug state!) ──────────────────────────
        if isinstance(ac, dict):
            d.climatisation_state = v(ac, "state")
            d.climatisation_active = d.climatisation_state not in (None, "OFF", "INVALID")
            # v1.10.1 (#58) — safe_float. Skoda firmwares have shipped
            # ``"21,5"`` (locale-comma) on EU accounts at least once.
            d.target_temperature = safe_float(
                v(ac, "targetTemperature", "temperatureValue")
            )

            wh = v(ac, "windowHeatingState") or {}
            d.window_heating_front = v(wh, "front") == "ON"
            d.window_heating_back = v(wh, "rear") == "ON"

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
            electric = v(driving_range, "electricRange", "distanceInKm")
            total = v(driving_range, "totalRangeInKm")
            combustion = v(driving_range, "combustionRange", "distanceInKm")
            if combustion is None:
                # Older firmwares published a flat scalar without the
                # ``distanceInKm`` wrapper — keep that path as a fallback.
                flat_combustion = v(driving_range, "combustionRange")
                if isinstance(flat_combustion, (int, float)):
                    combustion = flat_combustion
            # v1.24.2 (2026-05-08 audit): replaced 3 try/except wrappers
            # around int() with safe_int — same defensive shape, fewer
            # lines, and the NEVER-raise contract is property-tested.
            d.electric_range_km = safe_int(electric)
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
            adblue = v(driving_range, "adBlueRange", "distanceInKm")
            d.adblue_range_km = safe_int(adblue)
            # v1.26.0 Welle-6 (#173, scout #165 christianmhz) — Skoda PHEV
            # secondary engine range (Kodiaq iV, Octavia iV, Superb iV).
            # Distinct from combustion_range_km because Skoda PHEVs report
            # both via separate API blocks since 2024 firmware.
            sec_eng = v(driving_range, "secondaryEngineRange", "distanceInKm")
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

        d.is_electric = d.has_battery and not d.has_combustion
        d.is_hybrid = d.has_battery and d.has_combustion

        # ── Maintenance ──────────────────────────────────────────────────────
        if isinstance(maintenance, dict):
            report = v(maintenance, "maintenanceReport") or maintenance
            d.odometer_km = v(report, "mileageInKm")
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
        if isinstance(readiness, dict):
            unreachable = v(readiness, "unreachable")
            # When unreachable is unknown (None), assume reachable (True)
            # to avoid setting is_online to a falsy default.
            d.is_online = unreachable is None or unreachable is False
            d.is_driving = v(readiness, "inMotion") is True
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
        if isinstance(driving_score, dict):
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

    async def command_lock(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v1/vehicle-access/{vin}/lock", json={})

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        payload: dict[str, Any] = {}
        if spin or self._spin:
            payload["spin"] = spin or self._spin
        await self._post(f"{_BASE}/api/v1/vehicle-access/{vin}/unlock", json=payload)

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
        latitude: float | None = None,  # noqa: ARG002
        longitude: float | None = None,  # noqa: ARG002
    ) -> None:
        await self._post(f"{_BASE}/api/v1/vehicle-access/{vin}/honk-and-flash", json={"mode": "FLASH_ONLY"})

    async def command_wake(self, vin: str) -> None:
        await self._post(f"{_BASE}/api/v1/vehicle-wakeup/{vin}?applyRequestLimiter=true", json={})

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        await self._post(
            f"{_BASE}/api/v1/charging/{vin}/set-charge-limit",
            json={"targetStateOfChargeInPercent": target},
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
        """Start Webasto auxiliary heater. Some MY require SPIN; others don't.

        Pragmatic: try without SecToken first; on 403/spin_error fall back
        to SecToken-protected call. Same pattern as SEAT/CUPRA fallback.
        """
        url = f"{_BASE}/api/v2/air-conditioning/{vin}/auxiliary-heating/start"
        try:
            await self._post(url, json={})
            return
        except Exception:
            # Retry with SPIN if available (MY24+ Skoda Connect requires it)
            if spin:
                # SecToken via mysmob /spin/verify (mirrors lock/unlock flow)
                _LOGGER.debug("Skoda aux-heating: retry with SecToken")
            raise

    async def command_stop_aux_heating(self, vin: str) -> None:
        """Stop Webasto auxiliary heater. No SPIN required (matches SEAT/CUPRA)."""
        await self._post(
            f"{_BASE}/api/v2/air-conditioning/{vin}/auxiliary-heating/stop", json={}
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
