# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capability-ID Mapping per Brand — Single Source of Truth.

v1.13.0 (#56 Phase 3) — when an HA platform's ``async_setup_entry``
decides whether to register a command-bound entity, it asks
``coordinator.command_capability_supported(vin, command_id)``. That
helper translates the integration-level command name (e.g.
``"command_flash"``) into the brand-specific capability ID (e.g.
``"honkAndFlash"`` for VW EU CARIAD-BFF, ``"honk-and-flash"`` for
SEAT/CUPRA OLA, ``"honk-and-flash"`` for Skoda mysmob) before
querying the capability cache.

Why this lives in its own module:
- Pre-v1.13.0 the brand→cap-id mapping was implicit — Phase 2 only
  recorded post-failure outcomes (`MISSING_CAPABILITY`) and the
  brand-string never mattered.
- Phase 3 needs to PRE-decide; that requires a stable lookup table.
- Putting it in const.py would mix infra constants with business
  vocabulary; here it's a focused single-source-of-truth that the
  research notes (`docs/RESEARCH_NOTES_2026-05-02.md`) reference
  directly.

Design rules:
- Keep the table CONSERVATIVE — when in doubt, do NOT add a
  capability mapping. Phase 3 falls through to Phase 2 (which
  catches at runtime) if no cap-id is registered.
- Annotate confidence with comments per row:  verified in production
  vs ️ [Inference] vs  unknown.
- New brands (vw_na, porsche) start empty — capabilities discovered
  via Vehicle Data Scout reports get added here once verified.
"""

from __future__ import annotations

from typing import Final

# Per-brand: command-id → capability-id string.
#
# ``command_id`` is the same string used by ``coordinator.record_command_*``
# (e.g. "command_lock", "command_flash"). ``cap_id`` is the brand-specific
# string the backend's capabilities endpoint publishes.
#
# When a row is missing from a brand's table, ``command_capability_supported``
# returns ``None`` (= unknown, don't filter). That's the safe default —
# Phase 2's runtime filter catches missing capabilities post-failure.
CAPABILITY_MAP: Final[dict[str, dict[str, str]]] = {
    # ─────────────────────────────────────────────────────────────────
    # VW EU CARIAD-BFF — capabilities endpoint:
    #   GET /vehicle/v1/vehicles/{vin}/capabilities
    # Schema: {capabilities: [{id, status: [...]}]}
    # status=[] → fully usable; non-empty → limitation present
    # ─────────────────────────────────────────────────────────────────
    "volkswagen": {
        "command_lock": "access",                #  verified — used by lock platform
        "command_unlock": "access",              #  same capability gates both
        "command_flash": "honkAndFlash",         #  verified — vw_eu.py:120 reference
        "command_start_climate": "climatisation",   #  standard CARIAD vocabulary
        "command_stop_climate": "climatisation",
        "command_start_charging": "charging",       # 
        "command_stop_charging": "charging",
        "command_set_target_soc": "charging",       #  same parent capability
        "command_set_charge_mode": "charging",
        "command_set_min_soc": "charging",
        "command_set_max_charge_current": "charging",
        # ️ [Inference] — pattern from CARIAD vocabulary, not yet seen
        # in a Scout-Whitelist-confirmed capabilities response.
        "command_wake": "vehicleWakeUpTrigger",
        "command_start_window_heating": "windowHeating",
        "command_stop_window_heating": "windowHeating",
        "command_set_climate_temperature": "climatisation",
        "command_set_departure_timer": "departureTimers",
        # v2.8.0 - Audi + VW EU engine pre-heater (Standheizung). Cap-id
        # ``auxiliaryHeating`` matches the SELECTIVE_STATUS_JOBS naming
        # in vw_eu.py and the CARIAD camelCase pattern. [Inference]:
        # the cap-id has not been observed in a Scout-confirmed
        # capabilities response, so Phase 3 falls through to Phase 2
        # runtime detection on vehicles whose capabilities response
        # uses a different label.
        "command_start_aux_heating": "auxiliaryHeating",
        "command_stop_aux_heating": "auxiliaryHeating",
        # v1.14.0 (#24) — Trip Statistics (subscription-required: Audi
        # connect Plus / WeConnect Plus). ️ [Inference] cap-id matches
        # CARIAD camelCase pattern; not yet seen in a Scout-confirmed
        # capabilities response. Phase 3 returns ``None`` → don't filter
        # if the cap row is absent, so vehicles without a published
        # capability still get the entities.
        "command_trip_stats": "tripStatistics",
    },
    # ─────────────────────────────────────────────────────────────────
    # Audi inherits VW EU's CARIAD-BFF capabilities (AudiClient(VWEUClient)).
    # Identical endpoint, identical schema, mostly identical cap-ids.
    # See cariad/api/audi.py for the inheritance.
    #
    # v1.14.0 (#28) — Audi-only ICE Remote Engine Start has no
    # corresponding entry in CAPABILITY_MAP["volkswagen"] — VW EU's
    # CARIAD-BFF doesn't expose the /engine/ subtree. The Audi-only
    # cap-id is patched in below the inheritance assignment.
    # ─────────────────────────────────────────────────────────────────
    "audi": {},  # populated at module load below from "volkswagen"
    # ─────────────────────────────────────────────────────────────────
    # SEAT/CUPRA OLA — capabilities endpoint:
    #   GET /v1/vehicles/{vin}/capabilities  (or /v5/users/{userId}/...)
    # Schema same dict-shape but cap-ids are kebab-case.
    # ─────────────────────────────────────────────────────────────────
    "cupra": {
        "command_lock": "access",                #  verified
        "command_unlock": "access",
        # v1.17.1 (Bruno-Collection seq 31/32) — cabin ventilation
        "command_start_ventilation": "ventilation",
        "command_stop_ventilation": "ventilation",
        # v1.17.1 (Bruno seq 29/30 + pycupra) — Webasto aux heating
        "command_start_aux_heating": "auxiliary-heating",
        "command_stop_aux_heating": "auxiliary-heating",
        # v1.17.1 (#36, Bruno seq 34) — nav destination push
        "command_send_destination": "destination",
        # v1.17.1 (Bruno seq 10/11) — battery-care read endpoints
        "command_battery_care_read": "charging",
        "command_flash": "honk-and-flash",       #  verified — seat_cupra.py:87 reference
        # ️ [Inference] — kebab-case pattern from OLA, plus missing-capability
        # responses observed for these on Gerhard's Born (#53 — CUPRA Born
        # 2023 Active subscription, capabilities did NOT include these).
        "command_wake": "vehicle-wakeup",
        "command_start_climate": "climatisation",
        "command_stop_climate": "climatisation",
        "command_start_charging": "charging",
        "command_stop_charging": "charging",
        "command_set_target_soc": "charging",
        "command_set_charge_mode": "charging",
        "command_set_min_soc": "charging",
        "command_set_max_charge_current": "charging",
        "command_start_window_heating": "window-heating",
        "command_stop_window_heating": "window-heating",
        "command_set_climate_temperature": "climatisation",
        "command_set_departure_timer": "departure-timers",
    },
    # SEAT shares OLA backend with CUPRA — same capability vocabulary.
    "seat": {},  # populated at module load below from "cupra"
    # ─────────────────────────────────────────────────────────────────
    # Skoda mysmob — capabilities endpoint:
    #   GET /api/v1/vehicle-access/{vin}/capabilities  (NEW in v1.13.0)
    # Schema: {capabilities: [{id, active, editable?, user-enabled?,
    #          status?, license-issue?, parameters?}]}
    # Different shape — uses "active" + "user-enabled" booleans plus
    # optional "status" array. See vehicle_supports_capability for the
    # schema-compatibility logic.
    # ─────────────────────────────────────────────────────────────────
    "skoda": {
        "command_lock": "access",
        "command_unlock": "access",
        # ️ [Inference] — kebab-case Skoda pattern matches OLA convention.
        # Real Skoda capabilities response not yet captured in a Scout
        # report; treat as inferred and let Phase 2 catch failures.
        "command_flash": "honk-and-flash",
        "command_wake": "vehicleWakeUpTrigger",
        "command_start_climate": "air-conditioning",   # mysmob endpoint name
        "command_stop_climate": "air-conditioning",
        "command_start_charging": "charging",
        "command_stop_charging": "charging",
        "command_set_target_soc": "charging",
        "command_set_charge_mode": "charging",
        "command_set_min_soc": "charging",
        "command_start_window_heating": "air-conditioning",
        "command_stop_window_heating": "air-conditioning",
        "command_set_climate_temperature": "air-conditioning",
        "command_set_departure_timer": "departure-timers",
        # v1.15.0 — Skoda Modernization. New cap-ids observed in
        # ``skodaconnect/myskoda`` PRs #533/#540/#541/#543/#557/#560
        # (merged 2026-03 → 2026-04). These are READ-only / metadata
        # capabilities — no command bindings yet, just registered so
        # Phase 3's ``vehicle_supports_capability`` can answer cleanly
        # for whichever entities we add later (driving-score sensors,
        # OTA binary-sensor, charging-history sensor, etc.).
        "command_software_update": "VEHICLE_HEALTH_INSPECTION",  # OTA via vhi
        "command_charging_history": "CHARGING",                  # umbrella cap
        "command_charging_profiles": "EXTENDED_CHARGING_SETTINGS",
        "command_driving_score": "DRIVING_SCORE",
        "command_readiness": "READINESS",
        "command_plug_and_charge": "PLUG_AND_CHARGE",
        "command_route_planning": "EV_ROUTE_PLANNING",
        "command_battery_charging_care": "BATTERY_CHARGING_CARE",
    },
    # ─────────────────────────────────────────────────────────────────
    # VW NA + Porsche — different backends, capabilities not yet
    # reverse-engineered. Empty table = Phase 3 falls through to Phase 2
    # (runtime-detect after failure). Safe fallback.
    # ─────────────────────────────────────────────────────────────────
    "volkswagen_na": {},  #  unknown — VW NA Auth/API distinct from CARIAD
    "porsche": {},        #  unknown — Auth0 + PPA backend, separate vocabulary
}

# Audi inherits the VW EU mapping at module load time. SEAT inherits CUPRA's.
# Same alias-trick used for EXPECTED_KEYS in cariad/_unexpected_keys.py.
CAPABILITY_MAP["audi"] = CAPABILITY_MAP["volkswagen"]
CAPABILITY_MAP["seat"] = CAPABILITY_MAP["cupra"]

# v1.14.0 (#28) — Audi-only ICE Engine Start. Replace the alias with a
# COPY so we can add Audi-specific entries without polluting VW EU's
# table (the alias trick above shares the same dict by reference).
# ️ [Inference] cap-id ``engineRemoteStart`` is the camelCase guess
# that matches CARIAD vocabulary patterns (``honkAndFlash``,
# ``vehicleWakeUpTrigger``). NOT confirmed in a live capabilities
# response yet — when a Scout report surfaces the real id we update.
CAPABILITY_MAP["audi"] = dict(CAPABILITY_MAP["audi"])
CAPABILITY_MAP["audi"]["command_engine_start"] = "engineRemoteStart"
CAPABILITY_MAP["audi"]["command_engine_stop"] = "engineRemoteStart"


def cap_id_for(brand: str, command_id: str) -> str | None:
    """Return the brand-specific capability-id for a command, or None.

    None means the command-id has no registered capability mapping for
    this brand. Phase 3 in the platform setup interprets this as "don't
    filter" (Phase 2 catches it at runtime if it really doesn't work).

    Pure function — safe to call from any thread, no I/O.
    """
    return CAPABILITY_MAP.get(brand, {}).get(command_id)


# v2.8.0 quick win E — declared per-brand capability table.
# Used by diagnostics + Repairs flow to know what the integration
# expects each brand to support. The actual support is determined
# at runtime by whether the brand's get_status() populates the
# corresponding VehicleData fields. This table is the "expected"
# baseline; the runtime check sits in coordinator.capabilities_snapshot.
#
# When a user reports "my Audi doesn't have a charging sensor" we now
# get a three-way signal from the diagnostics dump:
#   - declared=True, observed=True  → working as designed
#   - declared=True, observed=False → drift (parser broke / backend changed)
#   - declared=False, observed=*    → brand never supported it
#
# Capability keys are integration-level concepts (not brand-specific
# cap-ids); the mapping from "expected to parse" to the actual
# VehicleData field lives in coordinator.capabilities_snapshot so this
# module stays a pure data table.
DECLARED_CAPABILITIES: dict[str, dict[str, bool]] = {
    "audi": {
        "auxiliary_heating": True,
        "charging": True,
        "climatisation": True,
        "trip_statistics": True,
        "brake_service": True,
        "ola_push": False,
        "fcm_push": True,
        "dag_login": True,
    },
    "bentley": {
        # v2.14.11 — Bentley runs on the Audi CARIAD-BFF (shared IDK client +
        # tenant), so its backend capability surface mirrors Audi. Wired
        # read-only for now (two-way is live-test gated); the BACKEND supports
        # these. dag_login False — Bentley is not in DAG_ENABLED_BRANDS.
        "auxiliary_heating": True,
        "charging": True,
        "climatisation": True,
        "trip_statistics": True,
        "brake_service": True,
        "ola_push": False,
        "fcm_push": True,
        "dag_login": False,
    },
    "volkswagen": {
        "auxiliary_heating": True,
        "charging": True,
        "climatisation": True,
        "trip_statistics": True,
        "brake_service": True,
        "ola_push": False,
        "fcm_push": True,
        "dag_login": False,
    },
    "skoda": {
        "auxiliary_heating": False,
        "charging": True,
        "climatisation": True,
        "trip_statistics": True,
        "brake_service": True,
        "ola_push": False,
        "fcm_push": False,
        "dag_login": True,
        "mqtt_push": True,
    },
    "seat": {
        "charging": True,
        "climatisation": True,
        "trip_statistics": True,
        "brake_service": False,
        "ola_push": True,
        "fcm_push": True,
        "dag_login": True,
    },
    "cupra": {
        "charging": True,
        "climatisation": True,
        "trip_statistics": True,
        "brake_service": False,
        "ola_push": True,
        "fcm_push": True,
        "dag_login": True,
    },
    "porsche": {
        "charging": True,
        "climatisation": True,
        "trip_statistics": False,
        "brake_service": False,
        "ola_push": False,
        "fcm_push": False,
        "dag_login": False,
    },
    "volkswagen_na": {
        "charging": True,
        "climatisation": True,
        "trip_statistics": False,
        "brake_service": False,
        "ola_push": False,
        "fcm_push": False,
        "dag_login": False,
    },
}
