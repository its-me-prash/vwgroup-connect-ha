# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every Škoda capability-id is a real MySkoda ``CapabilityId`` enum member.

Source of truth: the MySkoda 8.15.0 APK (cz.skodaauto.myskoda), DEX class
``Lnj0/b;`` (the CapabilityId enum), dumped from its own <clinit> via androguard
— NOT grepped strings, and NOT guessed. This frozenset is that enum verbatim
(156 members). The guard test below fails the build if anyone re-introduces a
guessed id (like the old ``air-conditioning`` / ``DRIVING_SCORE`` / ``READINESS``
that never matched what the backend actually sends), because a wrong id makes
``vehicle_supports_capability`` report a real feature "absent" once the per-VIN
capability cache populates, silently hiding the control.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad._capabilities import CAPABILITY_MAP, cap_id_for

# MySkoda 8.15.0 CapabilityId enum (Lnj0/b;), androguard-verified.
MYSKODA_CAPABILITY_IDS = frozenset({
    "ACCESS", "ACCESS_WITHOUT_SPIN", "ACCIDENT_DAMAGE_MANAGEMENT", "ACTIVATED",
    "ACTIVE_VENTILATION", "AIR_CONDITIONING", "AIR_CONDITIONING_HEATING_SOURCE_AUXILIARY",
    "AIR_CONDITIONING_HEATING_SOURCE_ELECTRIC", "AIR_CONDITIONING_SAVE_AND_ACTIVATE",
    "AIR_CONDITIONING_TIMERS", "AUTOMATION", "AUXILIARY_HEATING", "AUXILIARY_HEATING_BASIC",
    "AUXILIARY_HEATING_TEMPERATURE_SETTING", "AUXILIARY_HEATING_TIMERS",
    "AUXILIARY_HEATING_TIMERS_IN_GMT", "BATTERY_CHARGING_CARE", "BATTERY_SUPPORT",
    "CAMPING_MODE", "CARE_AND_INSURANCE", "CAR_FEEDBACK", "CHARGING", "CHARGING_MEB",
    "CHARGING_PROFILES", "CHARGING_PROFILES_CREATE", "CHARGING_STATIONS", "CONSENT_MISSING",
    "CUBIC", "DATA_PLAN", "DCS", "DEACTIVATED", "DEACTIVATED_BY_ACTIVE_VEHICLE_USER",
    "DEALER_APPOINTMENT", "DEEP_SLEEP", "DEPARTURE_TIMERS", "DESTINATIONS",
    "DESTINATION_IMPORT", "DESTINATION_IMPORT_UPGRADABLE", "DESTINATION_SYNC", "DIGICERT",
    "DISABLED_BY_USER", "DOORS_2_MODULES", "DRIVING_SCORE_WITH_BONUS", "EMERGENCY_CALLING",
    "EV_ROUTE_PLANNING", "EV_SERVICE_BOOKING", "EXTENDED_CHARGING_SETTINGS", "E_PRIVACY",
    "FLEET_SUPPORTED", "FRONTEND_SWITCHED_OFF", "FUEL_STATUS", "GEOFENCE", "GOOGLE_EARTH",
    "GUEST_USER", "GUEST_USER_INVITATION", "GUEST_USER_MANAGEMENT",
    "GUEST_USER_UNKNOWN_TO_VEHICLE", "GUEST_USER_WAITING", "HEALTH_REPORT", "HONK_AND_FLASH",
    "HYBRID_RADIO", "ICE_VEHICLE_RTS", "INFORMATION_CALL", "INITIALLY_DISABLED",
    "INSUFFICIENT_BATTERY_LEVEL", "INSUFFICIENT_RIGHTS", "INSUFFICIENT_SECURITY_LEVEL",
    "INSUFFICIENT_SPIN", "LAURA_INITIAL_PROMPTS_BEV", "LAURA_INITIAL_PROMPTS_ICE",
    "LFP_BATTERY_CALIBRATION_DURING_CHARGING", "LICENSE_EXPIRED", "LICENSE_INACTIVE",
    "LICENSE_MISSING", "LOCATION_DATA_DISABLED", "LOYALTY_PROGRAM", "LOYALTY_PROGRAM_WORLDWIDE",
    "MAP_UPDATE", "MBB", "MBB_ODP", "MEASUREMENTS", "MISSING_OPERATION", "MISSING_SERVICE",
    "MISUSE_PROTECTION", "MOBILE_DEVICE_KEY", "NEWS", "NOT_ACTIVATED", "OBFCM_DATA_REPORTING",
    "OCU_3G_NOT_UPGRADABLE", "OCU_3G_NOT_UPGRADABLE_ALTERNATIVE_POSSIBLE",
    "OCU_3G_UPGRADABLE_VIA_OTA", "OCU_3G_UPGRADABLE_VIA_SERVICE",
    "OCU_4G_E_CALL_FIXABLE_VIA_OTA", "OCU_4G_E_CALL_FIXABLE_VIA_SERVICE", "OCU_UNKNOWN",
    "ONLINE_REMOTE_UPDATE", "ONLINE_SPEECH", "ONLINE_SPEECH_GPS", "OUTSIDE_TEMPERATURE",
    "PARKING_INFORMATION", "PARKING_POSITION", "PARK_ASSIST_PAIRING_VIA_CONNECTION_SETTINGS",
    "PAY_TO_FUEL", "PAY_TO_PARK", "PLUG_AND_CHARGE", "POISEARCH", "POWERPASS_TARIFFS",
    "POWER_BUDGET_REACHED", "PREDICTIVE_MAINTENANCE", "PREDICTIVE_WAKE_UP", "PREREGISTRATION",
    "PRIMARY_USER_UNKNOWN_TO_VEHICLE", "REMOTE_PARK_ASSIST", "RESET_SPIN", "ROADSIDE_ASSISTANT",
    "ROUTE_IMPORT", "ROUTE_PLANNING_10_CHARGERS", "ROUTE_PLANNING_15_CHARGERS",
    "ROUTE_PLANNING_5_CHARGERS", "ROUTING", "SERVICE_PARTNER",
    "SINGLE_SERVICE_DEACTIVATION_IN_VEHICLE", "SPEED_ALERT", "STATE", "SUBSCRIPTIONS",
    "TERMS_AND_CONDITIONS_NOT_ACCEPTED", "THEFT_WARNING", "TRAFFIC_INFORMATION",
    "TRIP_STATISTICS", "TRIP_STATISTICS_MEB", "UNAVAILABILITY_STATUSES",
    "UNAVAILABLE_CAPABILITY", "UNAVAILABLE_CAR_FEEDBACK", "UNAVAILABLE_DCS",
    "UNAVAILABLE_FLEET", "UNAVAILABLE_ONLINE_SPEECH_GPS",
    "UNAVAILABLE_SERVICE_PLATFORM_CAPABILITIES", "UNAVAILABLE_TRUNK_DELIVERY",
    "UNKNOWN_CAPABILITY_STATE", "USER_NOT_VERIFIED", "VEHICLE_DISABLED",
    "VEHICLE_HEALTH_INSPECTION", "VEHICLE_HEALTH_WARNINGS",
    "VEHICLE_HEALTH_WARNINGS_WITH_WAKE_UP", "VEHICLE_LIGHTS", "VEHICLE_NOT_REACHABLE",
    "VEHICLE_OFFLINE", "VEHICLE_SERVICES_BACKUPS", "VEHICLE_WAKE_UP",
    "VEHICLE_WAKE_UP_TRIGGER", "WARNING_LIGHTS", "WCAR", "WEATHER_INFORMATION", "WEB_RADIO",
    "WINDOW_HEATING", "WORKSHOP_MODE",
})


def test_vocabulary_has_expected_size():
    assert len(MYSKODA_CAPABILITY_IDS) == 156


def _flatten(value):
    return list(value) if isinstance(value, tuple) else [value]


def test_every_skoda_capability_id_is_a_real_enum_member():
    offenders = {}
    for command_id, value in CAPABILITY_MAP["skoda"].items():
        for cid in _flatten(value):
            if cid not in MYSKODA_CAPABILITY_IDS:
                offenders.setdefault(command_id, []).append(cid)
    assert not offenders, f"non-enum (guessed) Škoda capability ids: {offenders}"


@pytest.mark.parametrize("command_id,expected", [
    ("command_start_aux_heating", "AUXILIARY_HEATING"),
    ("command_start_active_ventilation", "ACTIVE_VENTILATION"),
    ("command_start_window_heating", "WINDOW_HEATING"),
    ("command_start_climate", "AIR_CONDITIONING"),
    ("command_flash", "HONK_AND_FLASH"),
    ("command_set_departure_timer", "DEPARTURE_TIMERS"),
])
def test_single_id_mappings(command_id, expected):
    assert cap_id_for("skoda", command_id) == expected


@pytest.mark.parametrize("command_id,expected", [
    ("command_lock", ("ACCESS", "ACCESS_WITHOUT_SPIN")),
    ("command_start_charging", ("CHARGING", "CHARGING_MEB")),
    ("command_wake", ("VEHICLE_WAKE_UP", "VEHICLE_WAKE_UP_TRIGGER")),
])
def test_variant_tuple_mappings(command_id, expected):
    assert cap_id_for("skoda", command_id) == expected


# ── set-match resolution in command_capability_supported ─────────────────────


def _coord(capabilities):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "skoda"}
    coord.vehicle_capabilities = (
        {"VINX": {"capabilities": capabilities}} if capabilities is not None else {}
    )
    return coord


def test_charging_supported_via_primary_variant():
    coord = _coord([{"id": "CHARGING", "status": []}])
    assert coord.command_capability_supported("VINX", "command_start_charging") is True


def test_charging_supported_via_meb_variant_only():
    # An MEB car advertises CHARGING_MEB but not the classic CHARGING — must
    # still resolve supported, not hide the charging switch.
    coord = _coord([{"id": "CHARGING_MEB", "status": []}])
    assert coord.command_capability_supported("VINX", "command_start_charging") is True


def test_charging_absent_when_neither_variant_present():
    coord = _coord([{"id": "AIR_CONDITIONING", "status": []}])
    assert coord.command_capability_supported("VINX", "command_start_charging") is False


def test_charging_unknown_when_cache_empty():
    coord = _coord(None)  # no cache → don't hide
    assert coord.command_capability_supported("VINX", "command_start_charging") is None


def test_lock_supported_via_without_spin_variant():
    coord = _coord([{"id": "ACCESS_WITHOUT_SPIN", "status": []}])
    assert coord.command_capability_supported("VINX", "command_lock") is True
