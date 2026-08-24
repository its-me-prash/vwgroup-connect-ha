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
# A value may be a single cap-id or a tuple of platform-variant ids (Škoda
# charging = CHARGING/CHARGING_MEB, lock = ACCESS/ACCESS_WITHOUT_SPIN, …);
# ``cap_id_for`` returns it as-is and ``command_capability_supported`` matches
# a tuple with "supported if the car advertises ANY".
CAPABILITY_MAP: Final[dict[str, dict[str, "str | tuple[str, ...]"]]] = {
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
        # ── 4.0.0 full-grounding wave (androguard We Connect 4.3.2) ──────
        # Every cap-id below is a verbatim member of the app's 87-strong
        # ``Lcom/volkswagen/common/capabilitiesfinder/Capability;`` enum.
        # New two-way command bindings (client methods + entities land in
        # the P1 command wave; the cap rows are registered now so the
        # gate answers cleanly the moment those entities appear):
        "command_battery_support_toggle": "batterySupport",
        # battery-care write (the switch/number use these exact command-ids)
        "command_set_battery_care": "batteryChargingCare",
        "command_set_battery_care_target": "batteryChargingCare",
        "command_start_active_ventilation": "activeVentilation",
        "command_stop_active_ventilation": "activeVentilation",
        "command_unlock_trunk": "access",
        # Read-only / metadata cap-ids pre-registered (Škoda-block pattern):
        # no command binding, but registered so a future capability-gated
        # read entity resolves cleanly instead of guessing. A tuple accepts
        # any advertised variant so a platform variant never wrongly hides.
        "command_battery_health": "batteryHealthState",
        "command_parking_position": "parkingPosition",
        "command_warning_lights": "warningLights",
        "command_theft_warning": "theftWarning",
        "command_plug_and_charge": "plugAndCharge",
        "command_charging_profiles": "chargingProfiles",
        "command_vehicle_health": (
            "vehicleHealth",
            "vehicleHealthInspection",
            "vehicleHealthWarnings",
        ),
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
    # ─────────────────────────────────────────────────────────────────
    # v3.2.1 — the ENTIRE Škoda table is now androguard-verified against the
    # real MySkoda 8.15.0 ``CapabilityId`` enum (DEX class ``Lnj0/b;``, 156
    # members, dumped from its own <clinit>). The old kebab/camel guesses
    # (``access`` / ``honk-and-flash`` / ``charging`` / ``departure-timers``)
    # never match what the garage-doc capability list actually sends, so once
    # the per-VIN cache populates ``vehicle_supports_capability`` reported them
    # "absent" (False) and hid the control. Every value below is a verbatim
    # enum member. Where a feature has genuine platform variants, the value is
    # a tuple → supported if the car advertises ANY (see ``cap_id_for``), so a
    # variant never wrongly hides a control. Empty cache → None → shown.
    # ─────────────────────────────────────────────────────────────────
    "skoda": {
        "command_lock": ("ACCESS", "ACCESS_WITHOUT_SPIN"),
        "command_unlock": ("ACCESS", "ACCESS_WITHOUT_SPIN"),
        "command_flash": "HONK_AND_FLASH",
        "command_wake": ("VEHICLE_WAKE_UP", "VEHICLE_WAKE_UP_TRIGGER"),
        "command_start_climate": "AIR_CONDITIONING",
        "command_stop_climate": "AIR_CONDITIONING",
        "command_start_charging": ("CHARGING", "CHARGING_MEB"),
        "command_stop_charging": ("CHARGING", "CHARGING_MEB"),
        "command_set_target_soc": ("CHARGING", "CHARGING_MEB"),
        "command_set_charge_mode": ("CHARGING", "CHARGING_MEB"),
        "command_set_min_soc": ("CHARGING", "CHARGING_MEB"),
        "command_start_window_heating": "WINDOW_HEATING",
        "command_stop_window_heating": "WINDOW_HEATING",
        "command_set_climate_temperature": "AIR_CONDITIONING",
        # Fuel-fired Standheizung + airing-without-heat (Škoda-only commands).
        "command_start_aux_heating": "AUXILIARY_HEATING",
        "command_stop_aux_heating": "AUXILIARY_HEATING",
        "command_start_active_ventilation": "ACTIVE_VENTILATION",
        "command_set_departure_timer": "DEPARTURE_TIMERS",
        # Read-only / metadata capabilities (no command binding yet — registered
        # so vehicle_supports_capability answers cleanly for future entities).
        # Every id verified present in the 8.15.0 enum. ``command_readiness``
        # was dropped: no ``READINESS`` member exists — it was a pure guess, and
        # leaving it would hide a future readiness entity the moment a cache
        # lands. Re-add it only when the real id is grounded.
        "command_charging_history": ("CHARGING", "CHARGING_MEB"),
        "command_charging_profiles": ("CHARGING_PROFILES", "EXTENDED_CHARGING_SETTINGS"),
        "command_driving_score": "DRIVING_SCORE_WITH_BONUS",
        "command_plug_and_charge": "PLUG_AND_CHARGE",
        "command_route_planning": "EV_ROUTE_PLANNING",
        "command_battery_charging_care": "BATTERY_CHARGING_CARE",
        # OTA software update: the enum carries both ONLINE_REMOTE_UPDATE (the
        # OTA channel) and VEHICLE_HEALTH_INSPECTION (a service check). Which one
        # gates the OTA entity isn't grounded from a live sample yet, so accept
        # either rather than guess one and risk hiding it.
        "command_software_update": ("ONLINE_REMOTE_UPDATE", "VEHICLE_HEALTH_INSPECTION"),
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


def cap_id_for(brand: str, command_id: str) -> str | tuple[str, ...] | None:
    """Return the brand-specific capability-id for a command, or None.

    A **tuple** means the feature is advertised under any of several
    platform-variant ids (e.g. Škoda charging = ``CHARGING`` on classic cars,
    ``CHARGING_MEB`` on MEB EVs; lock = ``ACCESS`` / ``ACCESS_WITHOUT_SPIN``).
    ``command_capability_supported`` treats a tuple as "supported if the car
    advertises ANY of them", so a real platform variant never wrongly hides a
    control.

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
    "audi_acpp": {
        # plug&play OBD-dongle cloud reader — a read-only snapshot silo (its
        # token is not BFF/DAG-whitelisted, there is no command backend and no
        # push). It declares nothing: every capability is False so diagnostics
        # never imply a command it can't do.
        "auxiliary_heating": False,
        "charging": False,
        "climatisation": False,
        "trip_statistics": False,
        "brake_service": False,
        "ola_push": False,
        "fcm_push": False,
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
        # v3.0.1 — VW revoked Škoda's device_code grant (403 unauthorized_client),
        # so the QR/browser login no longer works for Škoda. It signs in via
        # email + password (IDK authorization-code) instead.
        "dag_login": False,
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
    # v2.19.0 — Audi US/CA login foundation (CARIAD-BFF NA). Declared
    # CONSERVATIVELY: the data plane is attestation-gated / live-unconfirmed, so
    # we don't claim charging/climatisation reads until a US tester confirms them
    # (avoids a false drift signal). dag_login IS wired (Prash's clean auth).
    "audi_na": {
        "charging": False,
        "climatisation": False,
        "trip_statistics": False,
        "brake_service": False,
        "ola_push": False,
        "fcm_push": False,
        "dag_login": True,
    },
}
