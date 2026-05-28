# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Vehicle Data Scout — detects JSON fields the parser doesn't read.

Mirrors the `tillsteinbach/CarConnectivity-*` "Unexpected Keys found"
pattern that has been our richest source of API findings (CC-seatcupra
issue #109 with Rainer's CUPRA Born live dump, CC-skoda issue #50 with
the Kodiaq iV 2026 complete response).

Architecture:
- Pure data layer: ``EXPECTED_KEYS`` declares paths we already read; the
  ``detect_unexpected`` function walks an actual response and yields
  ``UnexpectedField`` entries for paths NOT in the expected set.
- Privacy: every yielded sample value is anonymised via ``mask_value``
  (VIN/userID/GPS/email/token redaction) before leaving this module.
- Brand-agnostic: the EXPECTED_KEYS table is keyed by ``(brand, endpoint)``
  so each brand client can register its known shape.

Usage from a brand client::

    from cariad._unexpected_keys import detect_unexpected
    findings = list(detect_unexpected("skoda", "vehicle-status", raw_status))
    if findings:
        coordinator.record_unexpected_keys(vin, findings)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from ._util import mask_vin

# Patterns we always mask in sample values, regardless of field name.
# VINs are 17 chars alphanumeric; rough match is fine for redaction.
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
# Email addresses
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
# JWT-shaped tokens (3 base64 segments)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
# UUIDs (used for userIDs)
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


@dataclass(frozen=True)
class UnexpectedField:
    """A JSON path observed in a live response that our parser doesn't read.

    Attributes:
        path: Dotted JSON path, e.g. ``"charging.batteryStatus.value.temp_C"``.
        sample_masked: Anonymised string snippet of the value seen
            (truncated to 80 chars). NEVER contains raw VIN, userID,
            GPS coordinate or token.
        endpoint: Logical endpoint name (e.g. ``"vehicle-status"``).
        first_seen_at: Timestamp of first observation (UTC ISO string).
    """

    path: str
    sample_masked: str
    endpoint: str
    first_seen_at: str


# `EXPECTED_KEYS[brand][endpoint]` is a set of dotted paths we know about.
# Paths use lowercase brand names (matching ``BrandConfig.name``).
# Add to these as new fields are integrated, so they stop appearing as
# "unexpected" findings.
#
# Convention:
#   - Top-level keys: just the key, e.g. ``"overall"``
#   - Nested: dot-separated, e.g. ``"charging.batteryStatus.value"``
#   - Wildcards: ``"*"`` matches any single segment
#     (e.g. ``"doors.*.locked"`` covers ``doors.frontLeft.locked`` etc.)
#   - Don't list scalar leaf values (we report parent paths)
#
# ─── Scout Policy (v2.4.1+) ────────────────────────────────────────────
# See ``docs/SCOUT_POLICY.md`` for the full rules. TL;DR: every leaf-
# value silenced here MUST also be parsed (parser → dataclass field →
# entity). Silencer-only is no longer acceptable.
#
# Exemption tiers documented inline below:
#   T2  — unit-variant duplicates (parse the canonical form, let
#         SensorDeviceClass handle display-time unit conversion)
#   T3  — *.carCapturedTimestamp leaves (consolidated into the
#         coordinator's ``last_updated_at`` field)
#   T4  — container declarations (endpoint roots, .status / .value /
#         .settings wrappers — no leaf value)
#   T5  — brand-specific paths from legacy fixtures (unclear if still
#         in production; defer to next scout-confirmation)
#
# When you ADD a new silencer entry, add the parser+entity at the same
# time OR add an inline ``# T2/T3/T4/T5 exempt`` comment.
#
# v2.4.1 audit (2026-05-25): classified 67 pre-existing silenced-only
# paths. 12 promoted to T1 (parsed + entity, see vw_eu.py + sensor.py).
# 55 documented as T2-T5 exempt with inline comments below.
EXPECTED_KEYS: dict[str, dict[str, set[str]]] = {
    "skoda": {
        "vehicle-status": {
            "overall", "overall.doors", "overall.doorsLocked",
            "overall.windows", "overall.lights", "overall.locked",
            "overall.reliableLockStatus",
            "detail", "detail.sunroof", "detail.trunk", "detail.bonnet",
            "carCapturedTimestamp",
            # v1.12.2 (#107 — tritanium73's Skoda live test 2026-05-01,
            # FIRST community Scout report from a non-maintainer!).
            # The wildcards ``renders.lightMode.*`` only match 3-segment
            # paths; the Scout reported ``renders.lightMode`` (2 segments)
            # so the parent itself needs explicit registration too.
            "renders", "renders.lightMode", "renders.lightMode.*",
            "renders.darkMode", "renders.darkMode.*",
            "compositeRenders", "compositeRenders.*",
            "engine",
        },
        "charging": {
            "status", "status.battery", "status.battery.stateOfChargeInPercent",
            "status.battery.remainingCruisingRangeInMeters",
            "status.battery.carCapturedTimestamp",
            "status.state", "status.chargingState",
            "status.chargePowerInKw", "status.chargingRateInKilometersPerHour",
            "status.chargeType", "status.fullyChargedAt",
            "status.remainingTimeToFullyChargedInMinutes",
            "status.carCapturedTimestamp",
            "settings", "settings.targetStateOfChargeInPercent",
            "settings.autoUnlockPlugWhenChargedAC",
            "settings.maxChargeCurrentAC",
            "settings.carCapturedTimestamp",
            # v1.19.3 (#143 whaak58 Skoda Scout-Report 2026-05-04) —
            # Skoda mysmob now ships full charging settings under
            # ``settings`` directly (lowercase Ac variants alongside
            # legacy AC) plus location-aware flag + transient-error
            # container + carCapturedTimestamp at top level. Wildcards
            # cover all current + future setting children.
            "isVehicleInSavedLocation",
            "carCapturedTimestamp",
            "errors",
            "errors.*",
            "settings.autoUnlockPlugWhenCharged",
            "settings.availableChargeModes",
            "settings.batteryCareModeTargetValueInPercent",
            "settings.chargingCareMode",
            "settings.maxChargeCurrentAc",
            "settings.preferredChargeMode",
        },
        "air-conditioning": {
            "state", "targetTemperature", "targetTemperature.temperatureValue",
            "windowHeatingState", "windowHeatingState.front", "windowHeatingState.rear",
            "chargerConnectionState", "chargerLockState",
            "carCapturedTimestamp",
            # v1.12.2 (#107 — tritanium73's Skoda 2026-05-01 Live-Test).
            # Newer mysmob air-conditioning response includes additional
            # status meta: list of in-flight requests, steering-wheel
            # position (LEFT/RIGHT), windowHeatingState.unspecified
            # (when state is INVALID), departure timer list, outside
            # temperature block, and an errors[] array.
            "runningRequests",
            "steeringWheelPosition",
            "windowHeatingState.unspecified",
            "timers",
            "outsideTemperature",
            "errors",
            # v1.17.5 (#129 rocksandclouds + #130 Chr1sDub + #133
            # christianmhz — three independent Skoda Scout-Reports
            # 2026-05-03/04 converging on the same outsideTemperature
            # leaf set). Backend now ships full block on air-conditioning
            # endpoint with value/unit/timestamp. Wildcard covers
            # potential future sub-fields without re-registering.
            "outsideTemperature.*",
            # v1.17.5 (#133 christianmhz) — targetTemperature now
            # includes the in-car display unit (CELSIUS|FAHRENHEIT)
            # alongside the value. Sibling of temperatureValue.
            "targetTemperature.unitInCar",
            # v1.19.3 (#143 whaak58 Skoda Scout-Report 2026-05-04) —
            # newer Skoda firmware exposes per-feature toggles on the
            # air-conditioning endpoint: airConditioningAtUnlock (auto-
            # AC when unlocking via app), seatHeatingActivated (dict
            # for front-left/front-right state), windowHeatingEnabled.
            # Wildcards on seatHeatingActivated because per-seat dict
            # may grow rear-seat keys on premium models.
            "airConditioningAtUnlock",
            "seatHeatingActivated",
            "seatHeatingActivated.*",
            "windowHeatingEnabled",
            # v2.2.0 (#220, Daniel Walter Scout-Report 2026-05-16) —
            # Skoda mysmob now exposes ``airConditioningWithoutExternalPower``
            # boolean on the air-conditioning endpoint. Indicates whether
            # climatisation can run from the HV battery alone (without
            # being plugged into a charger). Wired as binary_sensor.
            "airConditioningWithoutExternalPower",
            # v2.4.2 (#302, Scout-Report 2026-05-27) — RETRO-SILENCER ADD.
            # Field is ALREADY PARSED at skoda.py:586 since v2.1.0
            # (``estimatedDateTimeToReachTargetTemperature`` → ``d.climate_ready_at``
            # → ``sensor.climate_ready_at``). EXPECTED_KEYS was never
            # updated when the parser shipped — classic silencer-lag-
            # behind-parser gap, same class as v2.4.1 #284
            # (chargingSettings.requests). The sensor is shipping fine
            # for users; only the scout was noisy. T1 (parsed + entity
            # exists, just registering the silencer side now).
            "estimatedDateTimeToReachTargetTemperature",
        },
        "parking": {
            "parkingPosition", "parkingPosition.gpsCoordinates",
            "parkingPosition.gpsCoordinates.latitude",
            "parkingPosition.gpsCoordinates.longitude",
            "parkingPosition.formattedAddress",
            "carCapturedTimestamp",
            # v1.17.5 (#133 christianmhz) — Skoda mysmob now wraps
            # transient lookup failures (e.g. "no recent GPS fix") in
            # an ``errors`` array on the parking endpoint, mirroring
            # the same convention seen on air-conditioning + driving-
            # range. Defensive registration with wildcard.
            "errors",
            "errors.*",
        },
        "driving-range": {
            "totalRangeInKm", "electricRange", "electricRange.distanceInKm",
            "combustionRange", "adBlueRange", "adBlueRange.distanceInKm",
            "carCapturedTimestamp",
            # v1.12.2 (#107) — Skoda mysmob now also publishes the
            # high-level ``carType`` ("diesel"/"gasoline"/"electric"/
            # "hybrid") at the top level + a ``primaryEngineRange``
            # block (4 keys, similar to fuelStatus.primaryEngine on
            # CARIAD-BFF). Registering silences the Scout — actually
            # wiring these as fallback range sources is a v1.13.0+
            # feature once we have a verified live response.
            "carType",
            "primaryEngineRange",
            # v1.14.0 (#116, MavericklCS Scout-Report 2026-05-01) — four
            # ``primaryEngineRange.*`` children on a Skoda gasoline-engine
            # vehicle. Confirms the structure inferred in v1.12.2 from
            # tritanium73's #107 report. ``currentSoCInPercent`` on a
            # gasoline car is unusual — likely the 12V SoC; will be
            # cross-checked with future Scout-Reports before wiring as a
            # sensor.
            "primaryEngineRange.engineType",
            "primaryEngineRange.currentSoCInPercent",
            "primaryEngineRange.currentFuelLevelInPercent",
            "primaryEngineRange.remainingRangeInKm",
            # v2.2.0 (#220, Daniel Walter Scout-Report 2026-05-16) —
            # Skoda mysmob ``secondaryEngineRange`` expanded mid-May 2026
            # from 1-key (``distanceInKm`` only) to 4-key shape mirroring
            # the ``primaryEngineRange`` layout. New companion fields:
            # ``engineType`` (PETROL/DIESEL on PHEV), ``currentFuelLevelInPercent``
            # (secondary tank %), and an implicit container key.
            # Wildcard registration covers all current + future children
            # without per-field whack-a-mole — same pattern as primaryEngineRange.
            "secondaryEngineRange",
            "secondaryEngineRange.*",
        },
        "maintenance": {
            "maintenanceReport", "maintenanceReport.mileageInKm",
            "maintenanceReport.inspectionDueInKm",
            "maintenanceReport.inspectionDueInDays",
            "maintenanceReport.oilServiceDueInKm",
            "maintenanceReport.oilServiceDueInDays",
            "carCapturedTimestamp",
            # v1.12.2 (#107) — Skoda mysmob v3 maintenance endpoint
            # includes meta blocks alongside the report itself.
            "maintenanceReport.capturedAt",
            "preferredServicePartner",
            "predictiveMaintenance",
            "customerService",
            # v1.14.0 (#116, MavericklCS) — ``predictiveMaintenance``
            # has a ``setting`` sub-block (4 keys observed). Wildcard
            # registration covers all current + future setting children
            # without per-field whack-a-mole.
            "predictiveMaintenance.setting",
            "predictiveMaintenance.setting.*",
            # v1.17.5 (#130 Chr1sDub Octavia iV 2024 + #133 christianmhz —
            # both reported the same maintenance shape on 2026-05-04).
            # Skoda mysmob exposes preferred-workshop info (name, brand,
            # partner-id, contact, address, location, opening hours) and
            # service-booking history (active + past). Wildcards because
            # contact/address/location/openingHours are deeply nested
            # composite blocks; we don't read them yet but registering
            # silences the Scout. Future feature work can wire a
            # ``preferred_workshop_name`` sensor + booking attrs.
            #
            # Both 2-segment + 3-segment wildcards needed because the
            # Scout walker (``_walk`` in this module) DESCENDS through
            # known parents. ``preferredServicePartner.*`` matches the
            # 2-segment children (``contact``, ``address``, ``location``,
            # ``openingHours``) — those ARE dicts so the walker recurses
            # into them and 3-segment leaves (``contact.phone``,
            # ``address.street``, ``location.lat/lon``) need their own
            # wildcard. ``customerService`` is shallower (2 keys both
            # arrays) so 2-segment alone suffices but 3-segment is safe
            # future-proofing.
            "preferredServicePartner.*",
            "preferredServicePartner.*.*",
            "customerService.*",
            "customerService.*.*",
        },
        "readiness": {
            "unreachable", "inMotion", "carCapturedTimestamp",
            # v1.19.3 (#143 whaak58 Skoda Scout-Report 2026-05-04) —
            # newer Skoda firmware exposes additional readiness flags:
            # ignitionOn (boolean) + batteryProtectionLimitOn (12V
            # protection threshold reached). Useful future signals
            # for "car is being driven" / "12V critical" automations.
            "ignitionOn",
            "batteryProtectionLimitOn",
        },
        # v1.20.0 (Bundle 2 Phase A) — myskoda PR #557 widget endpoint
        # for lightweight per-tick polling. Schema verified against
        # myskoda WidgetResponse model + 2 fixtures (parked + inmotion).
        # Wildcards on per-section subtree because parking + maps blocks
        # carry varying optional children depending on vehicle state
        # (in-motion vs parked, with/without GPS).
        "widget": {
            "vehicle", "vehicle.name", "vehicle.licensePlate",
            "vehicle.renderUrl",
            "vehicleStatus", "vehicleStatus.doorsLocked",
            "vehicleStatus.drivingRangeInKm",
            "chargingStatus",
            "chargingStatus.stateOfChargeInPercent",
            "chargingStatus.remainingTimeToFullyChargedInMinutes",
            "parkingPosition", "parkingPosition.state",
            "parkingPosition.formattedAddress",
            "parkingPosition.gpsCoordinates",
            "parkingPosition.gpsCoordinates.latitude",
            "parkingPosition.gpsCoordinates.longitude",
            "parkingPosition.maps",
            "parkingPosition.maps.lightMapUrl",
            "parkingPosition.maps.darkMapUrl",
            # Wildcards for forward-compat children we haven't seen yet
            "vehicle.*",
            "vehicleStatus.*",
            "chargingStatus.*",
            "parkingPosition.*",
            "parkingPosition.maps.*",
            "parkingPosition.gpsCoordinates.*",
        },
    },
    "cupra": {
        "status": {
            "doors", "doors.*", "doors.*.locked", "doors.*.open",
            "windows", "windows.*", "windows.sunroof",
            "trunk", "trunk.open", "trunk.locked",
            "hood", "hood.open",
            # v1.10.2 (#53 Gerhard's Born Live-Dump 2026-04-30) — newer
            # OLA firmware ships flat top-level overall fields alongside
            # the structured tree.
            "hood.locked",
            "locked",        # overall door-locked bool
            "lights",        # vehicle lights state ("off"/"on")
            "updatedAt",     # alternate to carCapturedTimestamp
            "sunroof", "sunRoof",
            "engine",
            "access", "access.doorClosedLeftFront", "access.doorClosedRightFront",
            "access.doorClosedLeftBack", "access.doorClosedRightBack",
            "access.doorsOpenedCount", "access.windowsOpenedCount",
            "access.trunk", "access.trunkLocked", "access.trunkStatus",
            "access.hood", "access.hoodOpen", "access.sunroof",
            "access.sunroofOpen",
            "carCapturedTimestamp",
        },
        "mycar": {
            "measurements", "measurements.mileage", "measurements.mileage.value",
            "measurements.fuelLevelStatus",
            "measurements.fuelLevelStatus.value",
            "measurements.fuelLevelStatus.value.currentFuelLevel_pct",
            "measurements.batteryStatus",
            "measurements.batteryStatus.value",
            "measurements.batteryStatus.value.currentSOC_pct",
            "access", "access.accessStatus", "access.accessStatus.value",
            "access.accessStatus.value.doorLockStatus",
            # v1.10.2 (#53 Gerhard's Born Live-Dump) — top-level meta blocks.
            # We don't drill into them yet but registering silences the Scout.
            "engines",       # vehicle engine info block
            "services",      # subscribed services info block
            "carCapturedTimestamp",
            # v1.16.1 (#122 r1150gs SEAT Scout-Report 2026-05-02) —
            # ``engines`` block has a ``primary`` sub-block (3 keys
            # observed). Wildcard registration covers all current +
            # future primary children without per-field whack-a-mole.
            "engines.primary",
            "engines.primary.*",
            # v2.2.0 PR #18/20 (#232 matthias0304 CUPRA Scout-Report
            # 2026-05-16) — ``engines.secondary`` 3-key block shipped on
            # CUPRA PHEV variants (Formentor PHEV, Leon e-Hybrid). Mirrors
            # the Skoda Scout #220 ``driving-range.secondaryEngineRange``
            # pattern. Wired in seat_cupra.py parser to populate the
            # existing cross-brand ``secondary_engine_{range_km,type,
            # fuel_level_pct}`` fields. Wildcard registration covers
            # all current + future secondary children without per-field
            # whack-a-mole — same pattern as engines.primary.
            "engines.secondary",
            "engines.secondary.*",
            # v1.17.5 (#53 Gerhard Born v1.17.4 test 2026-05-04) —
            # ``services`` block on mycar has been registered as parent
            # since v1.10.2; Born now exposes the per-service entitlement
            # children (charging/climatisation/windowHeating). Each is a
            # multi-key dict (subscription state + caps + limits) that we
            # don't drill into yet — wildcard silences Scout for any
            # future per-service shape changes. 3-segment wildcard for
            # the per-service leaves (sub state, expiry, etc.).
            "services.*",
            "services.*.*",
        },
        "charging": {
            "battery", "battery.stateOfChargeInPercent", "battery.currentSOC_pct",
            # v1.10.2 (#53 Gerhard's Born Live-Dump) — Born 2026 firmware
            # uses camelCase field names.
            "battery.currentSocPercentage",
            "battery.estimatedRangeInKm",
            "currentPct",
            "charging", "state", "status", "chargingState",
            "chargePowerInKw", "chargePower_kW", "chargedPowerInKw",
            "chargeRateInKmPerHour", "chargeRate_kmph",
            # v2.4.2 (#299, Scout-Report 2026-05-27) — RETRO-SILENCER ADD.
            # Field is ALREADY PARSED at seat_cupra.py:747 since v2.0.1
            # (Scout #192 — Cupra Born MY26 ships ``rateInKmph`` on the
            # OLA charging endpoint as a 3rd-position fallback in the
            # ``charging_rate_kmh`` chain after ``chargeRateInKmPerHour``
            # and ``chargeRate_kmph``). Wired into ``sensor.charging_speed``.
            # EXPECTED_KEYS just never got the silencer-side entry —
            # silencer-lag-behind-parser gap. T1 (parsed + entity exists).
            "rateInKmph",
            # v2.4.3 (pre-emptive, 2026-05-27 cross-project sweep) — pycupra
            # v0.2.31 (WulfgarW, 2026-05-26) added Compressed Natural Gas
            # (CNG) instruments for CUPRA Leon TGI / Ibiza TGI variants.
            # We don't have a CUPRA TGI tester live yet but ship the
            # silencer pre-emptively to avoid scout spam when one shows up.
            # T5 (community-discovered field, not yet parser-wired — when
            # a tester reports we'll promote to T1 with sensor.cng_range_km
            # + sensor.cng_level_pct entities, mirroring the existing
            # diesel_range pattern from v1.9.1 #91).
            "cngLevel", "cngLevelInPct", "cng_level_pct",
            "cngRange", "cngRangeInKm", "cng_range_km",
            "remainingTimeInMinutes", "remainingTime",
            "remainingTimeToFullyChargedInMinutes", "remainingChargingTime",
            "chargeType", "chargingType", "type",
            "chargeMode", "preferredChargeMode", "mode",
            "settings", "active", "batteryCardStatus", "progressBarPct",
            "plug", "plug.connectionState", "plug.plugConnectionState",
            "plug.lockState", "plug.externalPower",
            # v1.10.2 (#53 Gerhard) — short field name variants on Born 2026.
            "plug.connection",
            "plug.lock",
            # v1.10.2 (#53 Gerhard) — nested ``charging.*`` paths (the
            # backend wraps the flat fields above into a nested object on
            # newer firmware as well).
            "charging.state",
            "charging.remainingTimeInMinutes",
            "charging.chargedPowerInKw",
            "charging.type",
            "charging.mode",
            "charging.settings",
        },
        "charging-info": {
            "targetSOC_pct", "targetSoc_pct", "targetStateOfChargeInPercent",
            "maxChargeCurrentAC", "maxChargeCurrent",
            "autoUnlockPlugWhenCharged", "autoUnlockPlugWhenChargedAC",
            # v1.10.2 (#53 Gerhard's Born Live-Dump) — wrapper blocks
            # for the new charge-care subsystem.
            "settings",
            "chargingCareSettings",
            "chargingCareStatus",
            "carCapturedTimestamp",
            # v1.17.5 (#53 Gerhard Born v1.17.4 test 2026-05-04) — Born
            # now publishes the per-setting children directly under
            # ``settings`` (lowercase ``Ac`` suffix variant alongside the
            # uppercase ``AC`` we already had above) and the charge-care
            # status leaves. Wildcards because the dict shape is settled
            # for now but Born firmware migrations have shown to add
            # fields each release. 3-segment for any nested settings dicts.
            "settings.*",
            "settings.*.*",
            "chargingCareSettings.*",
            "chargingCareSettings.*.*",
            "chargingCareStatus.*",
            "chargingCareStatus.*.*",
        },
        "climatisation": {
            "status", "status.climatisationState", "status.state",
            "settings", "settings.targetTemperature_K",
            "settings.targetTemperatureInCelsius", "targetTemperatureCelsius",
            "outsideTemperature",
            "windowHeatingStateFront", "windowHeatingStateRear",
            "carCapturedTimestamp",
        },
        # v2.5.3 (#306) — OLA /v1/vehicles/{vin}/mileage. Endpoint shipped
        # by the OLA backend with server-side cached odometer values that
        # remain available even when /v5/mycar reports the vehicle as
        # offline. Field-name variants observed across firmware: snake +
        # camel + ``*InKm`` (myskoda-style) + plain ``value``.
        "mileage": {
            "mileageInKm", "mileage", "odometer", "currentMileage", "value",
            "carCapturedTimestamp", "updatedAt",
            # Wildcard for any forward-compat OLA additions we haven't
            # explicitly observed yet. Belt-and-braces against this
            # endpoint being a future scout-issue magnet.
            "*",
        },
    },
    # SEAT shares OLA endpoints with CUPRA — same expected-keys table.
    "seat": {},  # populated at module load below
    "volkswagen": {
        "selectivestatus": {
            "access", "access.accessStatus", "access.accessStatus.value",
            "access.accessStatus.value.overallStatus",
            "access.accessStatus.value.carCapturedTimestamp",
            "access.accessStatus.value.doors", "access.accessStatus.value.windows",
            "access.accessStatus.value.doorLockStatus",
            "charging", "charging.batteryStatus", "charging.batteryStatus.value",
            "charging.batteryStatus.value.currentSOC_pct",
            "charging.batteryStatus.value.cruisingRangeElectric_km",
            "charging.batteryStatus.value.carCapturedTimestamp",
            "charging.chargingStatus", "charging.chargingStatus.value",
            "charging.chargingStatus.value.chargingState",
            "charging.chargingStatus.value.chargePower_kW",
            # v2.2.2 (Scout #260, j4x5mgq94b-commits, Audi 2026-05-17) —
            # ``chargeRate_kmph`` was parsed since v1.10.0
            # (``vw_eu.py`` → ``d.charging_rate_kmh`` → ``sensor.charging_speed``)
            # but never registered in EXPECTED_KEYS, so the Scout fired
            # on it as "unexpected". Classic silencer-lagging-behind-parser
            # gap. Audi inherits via ``EXPECTED_KEYS["audi"] = ...``.
            "charging.chargingStatus.value.chargeRate_kmph",
            "charging.chargingStatus.value.chargeMode",
            "charging.chargingStatus.value.chargeType",
            "charging.chargingStatus.value.remainingChargingTimeToComplete_min",
            # v2.3.0 — scout #264 (Audi moltke69 2026-05-19): route-aware
            # smart-charging fields. Backend computes a navigation-target
            # SoC + ETA based on the user's planned nav route.
            # Both wired in vw_eu.py → d.nav_target_soc_pct +
            # d.remaining_charge_time_nav_min → new sensors.
            "charging.batteryStatus.value.navigationTargetSOC_pct",
            "charging.chargingStatus.value.remainingChargingTimeNavigation_min",
            "charging.chargingStatus.value.chargingSettings",
            "charging.chargingStatus.value.chargingScenario",
            "charging.chargingStatus.value.carCapturedTimestamp",
            # v2.2.3 — scout #268 (VW EU arvcer 2026-05-21): pending
            # ``start_charging``/``stop_charging`` commands queue. Mirror
            # of the existing ``chargingSettings.requests`` parser, now
            # parsed into ``d.charging_status_pending`` (count diagnostic).
            "charging.chargingStatus.requests",
            # v2.4.1 — scout #284 (Audi KimmoT727 2026-05-24): retroactive
            # silencer-add for the long-parsed ``chargingSettings.requests``
            # field (parser shipped v1.27.2 #181 but EXPECTED_KEYS was
            # never updated — classic Scout Policy gap, see
            # docs/SCOUT_POLICY.md). Reporter on latest v2.4.0, scout
            # legitimately re-fired because of this gap. Audi inherits.
            "charging.chargingSettings.requests",
            "charging.chargingSettings", "charging.chargingSettings.value",
            "charging.chargingSettings.value.targetSOC_pct",
            "charging.chargingSettings.value.maxChargeCurrentAC",
            # v1.9.1 (#90, Golf 7 GTE Live-Dump) — VW EU added the
            # explicit ampere variant alongside the legacy enum string.
            "charging.chargingSettings.value.maxChargeCurrentAC_A",
            "charging.chargingSettings.value.autoUnlockPlugWhenChargedAC",
            "charging.chargingSettings.value.carCapturedTimestamp",
            # v1.9.1 (#90) — top-level chargeMode block on selectivestatus.
            # Same content as chargingStatus.value.chargeMode, just exposed
            # at the brand level too. Don't recurse — already covered above.
            "charging.chargeMode",
            "charging.plugStatus", "charging.plugStatus.value",
            "charging.plugStatus.value.plugConnectionState",
            "charging.plugStatus.value.plugLockState",
            "charging.plugStatus.value.externalPower",
            "charging.plugStatus.value.ledColor",
            "charging.plugStatus.value.carCapturedTimestamp",
            "climatisation", "climatisation.climatisationStatus",
            "climatisation.climatisationStatus.value",
            "climatisation.climatisationStatus.value.climatisationState",
            "climatisation.climatisationStatus.value.remainingClimatisationTime_min",
            "climatisation.climatisationStatus.value.carCapturedTimestamp",
            # v2.2.3 — scout #272 (VW EU arvcer 2026-05-23): pending
            # start/stop climatisation commands queue. Mirror of the
            # ``charging.chargingStatus.requests`` pattern added at
            # the same time. Parsed into ``d.climatisation_status_pending``.
            "climatisation.climatisationStatus.requests",
            # v2.4.1 — scout #283 (VW EU Brinki99 2026-05-24): fourth
            # and final ``*.requests`` queue-counter family member,
            # on the climatisationSettings side. Parsed into
            # ``d.climatisation_settings_pending``. Audi inherits.
            "climatisation.climatisationSettings.requests",
            # v2.4.2 — scout #301 (VW EU 2026-05-27): new ID-family
            # ACTIVE VENTILATION subsystem (front-seat active ventilation
            # while charging — replaces older "ventilation" climatisation
            # mode on MEB ID.7 + facelift ID.3/.4). Backend ships:
            #   - climatisation.activeVentilationStatus.value.* (state + ETA)
            #   - climatisation.climatisationSettings.value.activeVentilationSettings.* (config)
            #   - climatisationTimers.activeVentilationTimersStatus.value.* (schedule)
            #
            # INTERIM SILENCER (this PR): wildcards .* absorb the unknown
            # sub-shape so Scouts don't spam users while a follow-up PR
            # builds the full parser + entities. The shape inferred from
            # key-counts in the scout report aligns with the sibling
            # ``climatisationStatus.value.{climatisationState,
            # remainingClimatisationTime_min, carCapturedTimestamp}`` pattern
            # but needs real-payload confirmation before shipping entities
            # with possibly-wrong field names.
            #
            # FOLLOW-UP PR: parser → ``d.active_ventilation_state``,
            # ``d.active_ventilation_remaining_min``,
            # ``d.active_ventilation_duration_min``,
            # ``d.active_ventilation_timer_count`` + 4 default-disabled
            # entities (1 binary_sensor + 3 sensors). Tracked as the
            # "make scouts useful, not just silenced" follow-up per
            # 2026-05-27 maintainer-correction. Audi inherits via line 851.
            "climatisation.activeVentilationStatus",
            "climatisation.activeVentilationStatus.*",
            "climatisation.climatisationSettings.value.activeVentilationSettings",
            "climatisation.climatisationSettings.value.activeVentilationSettings.*",
            "climatisationTimers.activeVentilationTimersStatus",
            "climatisationTimers.activeVentilationTimersStatus.value",
            "climatisationTimers.activeVentilationTimersStatus.value.*",
            "climatisation.climatisationSettings",
            "climatisation.climatisationSettings.value",
            "climatisation.climatisationSettings.value.targetTemperature_C",
            # v1.9.1 (#90) — Fahrenheit pair to celsius (US-region exposure).
            "climatisation.climatisationSettings.value.targetTemperature_F",
            # v1.9.1 (#90) — flag indicating climate without external power.
            "climatisation.climatisationSettings.value.climatisationWithoutExternalPower",
            "climatisation.climatisationSettings.value.carCapturedTimestamp",
            "climatisation.windowHeatingStatus",
            "climatisation.windowHeatingStatus.value",
            "climatisation.windowHeatingStatus.value.windowHeatingStatus",
            "climatisation.windowHeatingStatus.value.carCapturedTimestamp",
            "measurements", "measurements.rangeStatus",
            "measurements.rangeStatus.value",
            "measurements.rangeStatus.value.electricRange",
            # v1.9.1 (#91, Audi S6 TDI) — diesel range alongside electric
            # for ICE / plug-in vehicles. Same pattern as Skoda's
            # adblue_range exposure.
            "measurements.rangeStatus.value.dieselRange",
            "measurements.rangeStatus.value.gasolineRange",
            # v2.4.2 — scout #301 (VW EU 2026-05-27): retro-silencer-add
            # for AdBlue tank remaining-range on TDI vehicles. Parser
            # already lifts ``adBlueRange`` to brand level since v1.9.1
            # (vw_eu.py → d.adblue_range_km → sensor.adblue_range),
            # but EXPECTED_KEYS was never updated for the
            # ``measurements.rangeStatus.value.adBlueRange`` source path.
            # Classic silencer-lagging-behind-parser gap, same class as
            # #284 (chargingSettings.requests). Audi inherits via line 851.
            "measurements.rangeStatus.value.adBlueRange",
            "measurements.rangeStatus.value.totalRange_km",
            "measurements.rangeStatus.value.carCapturedTimestamp",
            "measurements.odometerStatus",
            "measurements.odometerStatus.value",
            "measurements.odometerStatus.value.odometer",
            "measurements.odometerStatus.value.carCapturedTimestamp",
            "measurements.fuelLevelStatus",
            "measurements.fuelLevelStatus.value",
            "measurements.fuelLevelStatus.value.currentSOC_pct",
            # v1.9.1 (#91) — combustion fuel level percentage. Same key
            # pattern as currentSOC_pct but for the petrol/diesel tank.
            "measurements.fuelLevelStatus.value.currentFuelLevel_pct",
            "measurements.fuelLevelStatus.value.primaryEngineType",
            "measurements.fuelLevelStatus.value.carType",
            "measurements.fuelLevelStatus.value.carCapturedTimestamp",
            "measurements.temperatureBatteryStatus",
            "measurements.temperatureBatteryStatus.value",
            "measurements.temperatureBatteryStatus.value.carCapturedTimestamp",
            "measurements.temperatureOutsideStatus",
            "measurements.temperatureOutsideStatus.value",
            "measurements.temperatureOutsideStatus.value.temperatureOutside_K",
            "measurements.temperatureOutsideStatus.value.carCapturedTimestamp",
            "readiness", "readiness.readinessStatus",
            "readiness.readinessStatus.value",
            "readiness.readinessStatus.value.connectionState",
            "readiness.readinessStatus.value.connectionWarning",
            "vehicleLights", "vehicleLights.lightsStatus",
            "vehicleLights.lightsStatus.value",
            # v1.9.1 (#90 + #91) — explicit nested fields on lightsStatus.
            "vehicleLights.lightsStatus.value.carCapturedTimestamp",
            "vehicleLights.lightsStatus.value.lights",
            # v1.9.1 (#90 + #91) — top-level diagnostic blocks added
            # in newer firmware. We don't read them yet, but registering
            # them silences the Vehicle Data Scout for these well-known
            # branches. Future feature work can drill into the children.
            "userCapabilities",
            "fuelStatus",
            "vehicleHealthInspection",
            "vehicleHealthWarnings",
            # v1.9.1 (#90, Golf 7 GTE) — automation block (timers, smart
            # charging schedules) and departureProfiles (replacement for
            # the older departureTimers — see ROADMAP "PPE Climate Body").
            "automation",
            "departureProfiles",
            # v1.12.0 (#103 Audi + #104 VW EU, 2026-04-30) — intermediate
            # ``.{xxxStatus}`` / ``.warningLights`` / ``.chargeMode.error``
            # wrappers below the top-level meta blocks. The detector
            # correctly descended past the registered parents and saw
            # these wrappers as unknown — registering silences the Scout
            # for them. We don't need to drill deeper because v1.9.1
            # already registered the leaf paths under each (e.g.
            # ``vehicleHealthInspection.maintenanceStatus.value...``).
            "userCapabilities.capabilitiesStatus",
            "fuelStatus.rangeStatus",
            "vehicleHealthInspection.maintenanceStatus",
            "vehicleHealthWarnings.warningLights",
            "automation.climatisationTimer",
            "automation.chargingProfiles",
            "departureProfiles.departureProfilesStatus",
            # ``charging.chargeMode.error`` — same Bad-Gateway-style
            # error wrapper as ``fuelStatus.rangeStatus.error`` from #96.
            # Older firmwares wrap fields in error objects when the
            # backend can't compute them. Defensive registration.
            "charging.chargeMode.error",
            # v1.12.1 (#105 + #106, 2026-04-30) — Scout descended one
            # more level past the v1.12.0 wrapper registrations and
            # found the ``.value`` containers below them. Same
            # whack-a-mole as #103/#104 → register explicitly.
            "userCapabilities.capabilitiesStatus.value",
            "fuelStatus.rangeStatus.value",
            "vehicleHealthInspection.maintenanceStatus.value",
            "vehicleHealthWarnings.warningLights.value",
            "departureProfiles.departureProfilesStatus.value",
            # v1.12.1 (#105) — newer firmwares wrap automation timers
            # in the same Bad-Gateway error envelope as charging.chargeMode.
            "automation.climatisationTimer.error",
            "automation.chargingProfiles.error",
            # v1.12.1 (#105) — standardized HTTP-error-wrapper sub-fields.
            # Six children always co-exist (CARIAD BFF error contract):
            # message / errorTimeStamp / info / code / group / retry.
            # Wildcard match keeps the registry compact + future-proofs
            # against new error sub-fields the backend might add.
            "charging.chargeMode.error.*",
            "automation.climatisationTimer.error.*",
            "automation.chargingProfiles.error.*",
            "fuelStatus.rangeStatus.error.*",  # proactive — already saw fuelStatus.rangeStatus.error in #96
            # v1.12.3 (#111 — DnnsJp74's Audi Live-Test 2026-05-01,
            # ZWEITER community Scout report from a non-maintainer).
            # 23 fields reported. Pattern: .value containers next to
            # the .error wrappers we already registered in v1.12.0.
            # Plus .value.* wildcards because timer/profile blocks
            # contain user-configurable nested objects (per-timer
            # schedules, charge profiles per location) — children are
            # inherently variable + we don't read them in the parser.
            "automation.climatisationTimer.value",
            "automation.climatisationTimer.value.*",
            "automation.chargingProfiles.value",
            "automation.chargingProfiles.value.*",
            # v2.2.0 Phase 7 PR #5 (#245 Scout 2026-05-11/12/13) —
            # Systemic Cariad-BFF rollout: jeder ``<block>.{xxxStatus}``
            # bekommt jetzt einen ``.error`` container (6 keys —
            # message/errorTimeStamp/info/code/group/retry) wenn das
            # sub-status fails. Dieselbe Bad-Gateway-error-wrapper-
            # convention wie ``charging.chargeMode.error`` (#96 +
            # v1.12.0) plus ``automation.*.error`` (v1.12.1 #105) —
            # nur jetzt auf 17 statt 3 sub-blocks ausgerollt. Defensive
            # blanket-silencing inkl. ``.error.*`` wildcards für die
            # 6-key standard children — keep silencer compact +
            # future-proof.
            "access.accessStatus.error",
            "access.accessStatus.error.*",
            "fuelStatus.rangeStatus.error",  # parent already silenced above
            # fuelStatus.rangeStatus.error.* schon silenced (line ~585)
            "measurements.rangeStatus.error",
            "measurements.rangeStatus.error.*",
            "measurements.odometerStatus.error",
            "measurements.odometerStatus.error.*",
            "measurements.temperatureBatteryStatus.error",
            "measurements.temperatureBatteryStatus.error.*",
            "measurements.fuelLevelStatus.error",
            "measurements.fuelLevelStatus.error.*",
            "measurements.temperatureOutsideStatus.error",
            "measurements.temperatureOutsideStatus.error.*",
            "vehicleLights.lightsStatus.error",
            "vehicleLights.lightsStatus.error.*",
            "charging.batteryStatus.error",
            "charging.batteryStatus.error.*",
            "charging.chargingStatus.error",
            "charging.chargingStatus.error.*",
            "charging.chargingSettings.error",
            "charging.chargingSettings.error.*",
            "charging.plugStatus.error",
            "charging.plugStatus.error.*",
            "climatisation.climatisationSettings.error",
            "climatisation.climatisationSettings.error.*",
            "climatisation.climatisationStatus.error",
            "climatisation.climatisationStatus.error.*",
            "climatisation.windowHeatingStatus.error",
            "climatisation.windowHeatingStatus.error.*",
            "vehicleHealthInspection.maintenanceStatus.error",
            "vehicleHealthInspection.maintenanceStatus.error.*",
            "departureProfiles.departureProfilesStatus.error",
            "departureProfiles.departureProfilesStatus.error.*",
            # v2.2.3 — scout #273 (VW EU gudden 2026-05-23): readiness
            # endpoint's defensive ``.error`` envelope (Cariad-BFF
            # "endpoint hat einen Fehler"-wrapper pattern, same shape
            # as the other ``*.error`` siblings above). Backend hiccup,
            # parser ignores it cleanly. No code change beyond the
            # silencer-add.
            "readiness.readinessStatus.error",
            "readiness.readinessStatus.error.*",
            # v2.2.0 Phase 7 PR #5 (#245 Scout) — `measurements.
            # tirePressureStatus` 1-key container shipped alongside
            # the error rollout. Wildcard covers current + future
            # children (likely `.value.tires[*]` per Cariad convention).
            "measurements.tirePressureStatus",
            "measurements.tirePressureStatus.*",
            "measurements.tirePressureStatus.value",
            "measurements.tirePressureStatus.value.*",
            # Top-level batteryChargingCare + climatisationTimers job
            # names — present in our selectivestatus query since v1.9.x
            # but never registered in EXPECTED_KEYS catalog.
            "batteryChargingCare",
            "batteryChargingCare.*",  # children unknown, future-proof
            "climatisationTimers",
            "climatisationTimers.*",
            # Charging chargeMode .value (mode dict) + chargingCareSettings
            "charging.chargeMode.value",
            "charging.chargeMode.value.*",  # mode children variable
            "charging.chargingCareSettings",
            "charging.chargingCareSettings.*",
            # vehicleHealthWarnings.warningLights.value children — the
            # actual warning lights dict (per-light status). Variable
            # set per vehicle, parser already iterates them in v1.0+.
            "vehicleHealthWarnings.warningLights.value.*",
            # v1.12.3 (#113 Golf GTE + #114 Audi S6 C8 — Prash testing
            # 2026-05-01 evening): the parent .value containers
            # (registered in v1.12.1) descend into business+meta
            # children which were unregistered. Use wildcards instead
            # of enumerating because every brand/firmware mix yields
            # different sub-fields. Parser already reads the relevant
            # ones (inspectionDue_*, oilServiceDue_*, mileage_km,
            # totalRange_km, carType) — registry is just for Scout silence.
            "fuelStatus.rangeStatus.value.*",
            "fuelStatus.rangeStatus.value.primaryEngine.*",
            "fuelStatus.rangeStatus.value.secondaryEngine.*",
            "vehicleHealthInspection.maintenanceStatus.value.*",
            "departureProfiles.departureProfilesStatus.value.*",
            "userCapabilities.capabilitiesStatus.value.*",
            # batteryChargingCare + climatisationTimers .value children
            # (proactive — these top-level wrappers may have own .value
            # blocks on newer firmwares per #103/#104 pattern).
            "batteryChargingCare.value.*",
            "climatisationTimers.value.*",
            # Older auto-unlock-plug variant without AC suffix (#111 saw "off")
            "charging.chargingSettings.value.autoUnlockPlugWhenCharged",
            # 5x climatisationSettings.value.* zone + unit fields
            "climatisation.climatisationSettings.value.unitInCar",
            "climatisation.climatisationSettings.value.climatizationAtUnlock",
            "climatisation.climatisationSettings.value.windowHeatingEnabled",
            "climatisation.climatisationSettings.value.zoneFrontLeftEnabled",
            "climatisation.climatisationSettings.value.zoneFrontRightEnabled",
            # temperatureBatteryStatus Min + Max fields (parser already
            # reads temperatureHvBatteryMin_K for battery_temp sensor;
            # Max variant is new from #111)
            "measurements.temperatureBatteryStatus.value.temperatureHvBatteryMin_K",
            "measurements.temperatureBatteryStatus.value.temperatureHvBatteryMax_K",
            # 4x connectionState meta + 2x connectionWarning meta on
            # readiness.readinessStatus.value (we only had the parents
            # connectionState/connectionWarning registered — Scout
            # descended and found the leaves as unknown)
            "readiness.readinessStatus.value.connectionState.isOnline",
            "readiness.readinessStatus.value.connectionState.isActive",
            "readiness.readinessStatus.value.connectionState.batteryPowerLevel",
            "readiness.readinessStatus.value.connectionState.dailyPowerBudgetAvailable",
            "readiness.readinessStatus.value.connectionWarning.insufficientBatteryLevelWarning",
            "readiness.readinessStatus.value.connectionWarning.dailyPowerBudgetWarning",
            # v1.17.5 (#132 rborkenhagen Scout-Report 2026-05-04 on a
            # VW PHEV/EV) — three new leaves on selectivestatus:
            #   - climatisation.climatisationSettings.value.heaterSource
            #     ("electric" — used by Born/ID family to choose between
            #     PTC and HV-loop pre-conditioning)
            #   - measurements.fuelLevelStatus.value.secondaryEngineType
            #     ("electric" — companion to primaryEngineType, hardens
            #     the PHEV detection from v1.11.1 #96)
            #   - departureTimers (top-level job from selectivestatus
            #     query already in v1.13.0+ but never explicitly in
            #     EXPECTED_KEYS catalog — wildcard for future shape)
            "climatisation.climatisationSettings.value.heaterSource",
            "measurements.fuelLevelStatus.value.secondaryEngineType",
            "departureTimers",
            "departureTimers.*",
            # 3-segment wildcard for per-timer leaves (enabled, time,
            # repetition pattern, etc.). Walker descends into known
            # `departureTimers.{id}` containers.
            "departureTimers.*.*",
            # v2.3.0 — scout #264 (Audi moltke69 2026-05-19): newer
            # Cariad-BFF firmware restructured departureTimers into a
            # unified parent with charging + climatisation sub-status
            # blocks (each with its own value/timers/carCapturedTimestamp
            # shape — see the 5 reported paths). 4-segment wildcards
            # cover the leaves; the parser fallback in vw_eu.py reads
            # ``departureTimers.climatisationTimersStatus.value.timers``
            # if the legacy ``climatisationTimers.*`` path is empty.
            "departureTimers.chargingTimersStatus",
            "departureTimers.chargingTimersStatus.value",
            "departureTimers.chargingTimersStatus.value.*",
            "departureTimers.climatisationTimersStatus",
            "departureTimers.climatisationTimersStatus.value",
            "departureTimers.climatisationTimersStatus.value.*",
            "departureTimers.*.*.*",
            # v1.19.3 (#145 manentw + #146 ammelch + #147 gudden —
            # three convergent VW Scout-Reports 2026-05-05/06).
            # Newer CARIAD-BFF firmware ships:
            # - 5-segment leaves under automation.chargingProfiles.value
            #   (nextChargingTimer.id + .targetSOCreachable). Existing
            #   `automation.chargingProfiles.value.*` only matches
            #   4-segment paths; 5-segment needs explicit wildcard.
            # - Top-level batteryChargingCare.chargingCareSettings.value
            #   container (3 segments). Sibling of existing
            #   batteryChargingCare wildcard but the latter only matched
            #   2-segment children.
            # - charging.chargingCareSettings.value.batteryCareMode (4
            #   segments). Existing charging.chargingCareSettings.* only
            #   matched 2-segment children.
            # - climatisationTimers.climatisationTimersStatus.value (3
            #   segments). Status wrapper analogous to other CARIAD
            #   .{xxxStatus}.value pattern from v1.12.0.
            "automation.chargingProfiles.value.*.*",
            "batteryChargingCare.chargingCareSettings",
            "batteryChargingCare.chargingCareSettings.value",
            # Proactive 4-segment for batteryChargingCare leaves
            # (#145 reported `{1 keys}` shape but didn't surface the
            # leaf name — register wildcard so future Scout doesn't
            # re-fire on the inner key).
            "batteryChargingCare.chargingCareSettings.value.*",
            "charging.chargingCareSettings.value",
            "charging.chargingCareSettings.value.*",
            "climatisationTimers.climatisationTimersStatus",
            "climatisationTimers.climatisationTimersStatus.value",
            "climatisationTimers.climatisationTimersStatus.value.*",
        },
        "parkingposition": {
            "data", "data.lon", "data.lat", "data.carCapturedTimestamp",
        },
    },
    # Audi inherits VW EU's selectivestatus shape (same backend, same endpoint).
    "audi": {},  # populated at module load below
}

# SEAT and CUPRA share the OLA backend — same expected-keys table
EXPECTED_KEYS["seat"] = EXPECTED_KEYS["cupra"]
# Audi inherits VW EU's CARIAD-BFF expected keys (same selectivestatus endpoint)
EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]


def _path_matches(path: str, expected_paths: set[str]) -> bool:
    """Check whether ``path`` is covered by ``expected_paths`` (with wildcards).

    Wildcards: a path component ``"*"`` in expected matches any single
    actual component. So ``"doors.*.locked"`` matches
    ``"doors.frontLeft.locked"``.
    """
    if path in expected_paths:
        return True
    actual_parts = path.split(".")
    for expected in expected_paths:
        if "*" not in expected:
            continue
        expected_parts = expected.split(".")
        if len(expected_parts) != len(actual_parts):
            continue
        if all(e == "*" or e == a for e, a in zip(expected_parts, actual_parts)):
            return True
    return False


def mask_value(value: Any, *, max_len: int = 80) -> str:
    """Anonymise a sample value for logging / external sharing.

    - VINs (17-char alphanumeric blocks) → ``***{last 6 chars}``
    - Email addresses → ``***@***``
    - JWT-shaped tokens → ``[token]``
    - UUIDs → ``[uuid]``
    - Latitude/longitude pairs in numeric values → kept (rounded to 1
      decimal place ≈ 11 km precision) — useful for "is this a EU vehicle"
      kind of context without exposing precise location
    - Strings: redacted then truncated to ``max_len``
    - Numbers / bools / None: stringified (no leak risk)
    - Dicts / lists: shape only (e.g. ``{4 keys}`` or ``[3 items]``)
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        # Round to 1 decimal — kills GPS precision (1.0° ≈ 111km)
        return f"{value:.1f}"
    if isinstance(value, str):
        s = value
        s = _VIN_RE.sub(lambda m: mask_vin(m.group(0)), s)
        s = _EMAIL_RE.sub("***@***", s)
        s = _JWT_RE.sub("[token]", s)
        s = _UUID_RE.sub("[uuid]", s)
        if len(s) > max_len:
            s = s[: max_len - 3] + "..."
        return f'"{s}"'
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    # Fallback: type only
    return f"<{type(value).__name__}>"


def detect_unexpected(
    brand: str,
    endpoint: str,
    response: Any,
    *,
    parent_path: str = "",
    max_depth: int = 6,
) -> Iterable[UnexpectedField]:
    """Walk ``response`` and yield ``UnexpectedField`` for paths NOT in
    ``EXPECTED_KEYS[brand][endpoint]``.

    Behaviour:
    - Returns nothing if the brand or endpoint is not registered (keeps
      old brand clients quiet until they opt in).
    - Walks dicts only — list contents are not recursed (the list
      itself is reported if its parent path is unexpected).
    - Stops at ``max_depth`` to avoid pathological responses tying up
      the event loop.
    - Always yields ``parent_path`` is reported once even if it has many
      unknown children (we don't spam — finer detail comes via individual
      child paths up to ``max_depth``).
    """
    from datetime import datetime, timezone  # local to avoid module-load cost

    expected = EXPECTED_KEYS.get(brand, {}).get(endpoint)
    if expected is None:
        return  # brand/endpoint not registered for detection
    if not isinstance(response, dict):
        return
    now = datetime.now(tz=timezone.utc).isoformat()

    def _walk(node: Any, path: str, depth: int) -> Iterable[UnexpectedField]:
        if depth > max_depth:
            return
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            child_path = f"{path}.{key}" if path else key
            if not _path_matches(child_path, expected):
                yield UnexpectedField(
                    path=child_path,
                    sample_masked=mask_value(val),
                    endpoint=endpoint,
                    first_seen_at=now,
                )
                # Don't recurse into unknown subtree — single report per branch
                continue
            if isinstance(val, dict):
                yield from _walk(val, child_path, depth + 1)

    yield from _walk(response, parent_path, depth=0)
