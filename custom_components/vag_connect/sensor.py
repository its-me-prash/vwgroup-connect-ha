# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sensor platform for VW Group Connect.

The VagSensorDescription.condition field gates sensor creation:
  "electric"  — EV and PHEV only (has_battery=True)
  "combustion" — combustion and PHEV only (has_combustion=True)
  None        — all vehicles

charging_rate_kmh uses SensorDeviceClass.SPEED so HA auto-converts km/h ↔ mph
based on the user's unit system preference.
"""
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

_LOGGER = logging.getLogger(__name__)

# Device classes whose state Home Assistant parses as a number. DATE and
# TIMESTAMP are deliberately absent: they are datetimes and have their own
# handling in native_value above. Used by the schema-drift guard there.
_NUMERIC_DEVICE_CLASSES = frozenset({
    SensorDeviceClass.BATTERY,
    SensorDeviceClass.CURRENT,
    SensorDeviceClass.DISTANCE,
    SensorDeviceClass.DURATION,
    SensorDeviceClass.ENERGY,
    SensorDeviceClass.ENERGY_STORAGE,
    SensorDeviceClass.POWER,
    SensorDeviceClass.PRESSURE,
    SensorDeviceClass.SPEED,
    SensorDeviceClass.TEMPERATURE,
    SensorDeviceClass.VOLTAGE,
    SensorDeviceClass.VOLUME,
    SensorDeviceClass.VOLUME_STORAGE,
})


@dataclass(frozen=True)
class VagSensorDescription(SensorEntityDescription):
    """Sensor description with coordinator data key, condition, and optional default-disabled flag."""

    data_key: str = ""
    condition: str | None = None  # "electric" | "combustion" | None
    # v4.0.0 grounding wave — optional capability-id (or tuple of platform
    # variants) that must not be explicitly absent for this sensor to appear.
    # None = ungated (data-presence only, unchanged). See
    # coordinator.read_capability_hidden for the soft-gate semantics.
    capability: "str | tuple[str, ...] | None" = None
    suggested_display_precision: int | None = None


SENSOR_DESCRIPTIONS: tuple[VagSensorDescription, ...] = (

    VagSensorDescription(
        key="fuel_level",
        translation_key="fuel_level",
        data_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
        condition="combustion",
    ),
    VagSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        data_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging",
        condition="electric",
    ),
    VagSensorDescription(
        key="range_km",
        translation_key="range_km",
        data_key="range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
    ),

    # v1.10.0 (#94, #91) — explicit per-energy-source range sensors.
    # Conditional creation in ``async_setup_entry`` is data-present-gated
    # in addition to the ``condition`` flag: even an EV that *has*
    # has_battery=True won't get a phantom ``electric_range_km`` entity
    # if the API didn't actually publish ``electric_range_km`` for it.
    # That solves the "unknown" clutter complaint in #94.
    VagSensorDescription(
        key="electric_range_km",
        translation_key="electric_range_km",
        data_key="electric_range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging-outline",
        condition="electric",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="combustion_range_km",
        translation_key="combustion_range_km",
        data_key="combustion_range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
        condition="combustion",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="total_range_km",
        translation_key="total_range_km",
        data_key="total_range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
        # No ``condition`` — total is meaningful for any drivetrain that
        # publishes the field. Pure EVs typically don't (so the gating
        # below filters it out anyway), but plug-in hybrids and ICE
        # vehicles with a combined trip-meter range get it.
    ),

    VagSensorDescription(
        key="odometer_km",
        translation_key="odometer_km",
        data_key="odometer_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        suggested_display_precision=0,
    ),

    VagSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        data_key="charging_state",
        icon="mdi:ev-plug-type2",
        condition="electric",
    ),
    VagSensorDescription(
        key="plug_state",
        translation_key="plug_state",
        data_key="plug_state",
        icon="mdi:power-plug",
        condition="electric",
        # #1055 — enum sensor so HA localizes the state label. Values are
        # normalized to this set in coordinator._enrich (anything else → None).
        device_class=SensorDeviceClass.ENUM,
        options=["connected", "disconnected"],
    ),
    # Stage-0 EU Data Act observability. portal_health tells a user whether the
    # PORTAL is delivering, apart from whether the integration is working — the
    # single most visible signal for the field's #1 problem (a fresh delivery
    # wrapping a stale payload). Enum so HA localizes the state; enabled by
    # default; computed in coordinator._enrich and only set for a portal read.
    VagSensorDescription(
        key="portal_health",
        translation_key="portal_health",
        data_key="portal_health",
        icon="mdi:cloud-check-variant",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "ok",
            "waiting_for_portal_data",
            "empty_snapshots",
            "delivery_not_ready",
            "stale",
        ],
    ),
    # The car's own data-capture age in minutes — how old the newest portal
    # snapshot is. Diagnostic + disabled by default (portal_health is the at-a-
    # glance version); enable it to automate on a staleness threshold.
    VagSensorDescription(
        key="minutes_since_last_snapshot",
        translation_key="minutes_since_last_snapshot",
        data_key="minutes_since_last_snapshot",
        icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # Stage-1 — the one-time historical-export lifecycle state. Only present
    # (visible) while an export is in flight or just finished; hidden otherwise.
    VagSensorDescription(
        key="historical_export_state",
        translation_key="historical_export_state",
        data_key="historical_export_state",
        icon="mdi:history",
        device_class=SensorDeviceClass.ENUM,
        options=["pending", "done", "timed_out"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.22.0 (evcc) — normalized IEC-61851 charge status (A=unplugged /
    # B=plugged-idle / C=charging) for the evcc connector's custom-vehicle
    # `status` field (our raw charging_state strings don't map to A/B/C).
    # Diagnostic + opt-in (enable it under the device if you use evcc);
    # electric-only. Always A/B/C — computed in coordinator._enrich. See
    # docs/EVCC.md.
    VagSensorDescription(
        key="evcc_charge_status",
        translation_key="evcc_charge_status",
        data_key="evcc_charge_status",
        icon="mdi:ev-station",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="target_soc",
        translation_key="target_soc",
        data_key="target_soc",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging-high",
        condition="electric",
    ),
    # v2.3.0 — Cariad scout #264 (Audi moltke69 2026-05-19): route-aware
    # smart-charging SoC target. Distinct from the static ``target_soc``
    # — backend computes how much battery you need for the next planned
    # navigation route. Power-users on EU/Audi PHEV/BEV with active
    # nav-routing see this populate as soon as a route is planned in
    # the car's nav system. Disabled by default until users opt-in.
    VagSensorDescription(
        key="nav_target_soc_pct",
        translation_key="nav_target_soc_pct",
        data_key="nav_target_soc_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-arrow-up",
        condition="electric",
        entity_registry_enabled_default=False,
    ),
    # v2.3.0 — companion to nav_target_soc_pct: ETA until the route-
    # aware target SoC is reached at the current charge rate. Minutes.
    VagSensorDescription(
        key="remaining_charge_time_nav_min",
        translation_key="remaining_charge_time_nav_min",
        data_key="remaining_charge_time_nav_min",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:clock-fast",
        condition="electric",
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_power_kw",
        translation_key="charging_power_kw",
        data_key="charging_power_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        condition="electric",
    ),
    VagSensorDescription(
        key="charging_rate_kmh",
        translation_key="charging_rate_kmh",
        data_key="charging_rate_kmh",
        # km/h = km Reichweite pro Stunde → device_class=SPEED → HA rechnet km/h ↔ mph
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging-outline",
        condition="electric",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="charge_complete_eta",
        translation_key="charge_complete_eta",
        data_key="charge_complete_eta",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-end",
        condition="electric",
    ),
    # v1.27.2 — Cariad scout #181 (Audi): pending charging-settings change
    # requests count. Diagnostic — typically 0 (idle), >0 means a
    # putChargingSettings POST is queued at the gateway.
    VagSensorDescription(
        key="charging_settings_pending",
        translation_key="charging_settings_pending",
        data_key="charging_settings_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:tray-arrow-up",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.2.3 — Cariad scout #268 (VW EU arvcer): mirror of the above
    # for the chargingStatus side — counts queued ``start_charging`` /
    # ``stop_charging`` commands. Same diagnostic semantics: 0 = idle,
    # >0 = command queued at the gateway. Disabled by default — power
    # users opt in. Phantom-protected (None when leaf absent).
    VagSensorDescription(
        key="charging_status_pending",
        translation_key="charging_status_pending",
        data_key="charging_status_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-alert",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.15.8 — Cariad scout #583 (Audi): third charging-side *_pending
    # sibling — counts queued chargeMode change requests
    # (``charging.chargeMode.requests``). 0 = idle, >0 = a chargeMode
    # change (manual <-> timer) is queued at the gateway. Disabled by
    # default — power-user opt-in. Phantom-protected (None when leaf absent).
    VagSensorDescription(
        key="charging_mode_pending",
        translation_key="charging_mode_pending",
        data_key="charging_mode_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:tune-variant",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.17.5 — fourth charging-side *_pending sibling — counts queued
    # battery-care setting changes (``batteryChargingCare
    # .chargingCareSettings.requests``). 0 = idle, >0 = queued at the gateway.
    # Disabled by default — power-user opt-in. None when leaf absent.
    VagSensorDescription(
        key="charging_care_pending",
        translation_key="charging_care_pending",
        data_key="charging_care_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.21.0 — MEB/PPE 12V-battery-support state (enabled/disabled), mapped
    # from the ``batterySupport`` selectivestatus job that ~27 reporters filed
    # (#832 et al.). Interim-silenced since v2.12.0; now surfaced as a
    # diagnostic, opt-in sensor. None when the leaf is absent.
    VagSensorDescription(
        key="battery_support_state",
        translation_key="battery_support_state",
        data_key="battery_support_state",
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # #1020 — HV-battery calibration notifications. All diagnostic and
    # disabled by default: most owners never see anything but NONE, and the
    # ones who do want to know without hunting through the app.
    VagSensorDescription(
        key="calibration_need_detected",
        translation_key="calibration_need_detected",
        data_key="calibration_need_detected",
        icon="mdi:battery-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="calibration_request_initial",
        translation_key="calibration_request_initial",
        data_key="calibration_request_initial",
        icon="mdi:battery-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="calibration_request_escalation_1",
        translation_key="calibration_request_escalation_1",
        data_key="calibration_request_escalation_1",
        icon="mdi:battery-alert-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="calibration_request_escalation_2",
        translation_key="calibration_request_escalation_2",
        data_key="calibration_request_escalation_2",
        icon="mdi:battery-alert-variant-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="calibration_request_method",
        translation_key="calibration_request_method",
        data_key="calibration_request_method",
        icon="mdi:battery-charging-medium",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="calibration_failure",
        translation_key="calibration_failure",
        data_key="calibration_failure",
        icon="mdi:battery-remove",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="calibration_failure_reason",
        translation_key="calibration_failure_reason",
        data_key="calibration_failure_reason",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.18.0 — Scout #799: queued charge-PROFILE changes
    # (``automation.chargingProfiles.requests``). Same *_pending diagnostic.
    VagSensorDescription(
        key="charging_profiles_pending",
        translation_key="charging_profiles_pending",
        data_key="charging_profiles_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:playlist-edit",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.18.0 — Scout #801: queued climate-TIMER schedule changes
    # (``climatisationTimers.climatisationTimersStatus.requests``).
    VagSensorDescription(
        key="climatisation_timers_pending",
        translation_key="climatisation_timers_pending",
        data_key="climatisation_timers_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-cog-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.2.3 — Cariad scout #272 (VW EU arvcer 2026-05-23): third
    # *_pending sibling — counts queued start/stop_climatisation
    # commands. No ``condition`` filter (every brand with climatisation
    # support — electric AND combustion alike). Disabled by default.
    VagSensorDescription(
        key="climatisation_status_pending",
        translation_key="climatisation_status_pending",
        data_key="climatisation_status_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-conditioner",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.4.1 — Cariad scout #283 (VW EU Brinki99 2026-05-24): fourth
    # and final ``*_pending`` family member — counts queued climate-
    # settings commands (set_climatisation_temperature, set_window_heating,
    # etc.) at the gateway. Same opt-in pattern as the siblings.
    VagSensorDescription(
        key="climatisation_settings_pending",
        translation_key="climatisation_settings_pending",
        data_key="climatisation_settings_pending",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermostat-cog",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.4.1 — Scout Policy Compliance Audit T1 sensors. All disabled-
    # by-default (opt-in) per docs/SCOUT_POLICY.md Rule 5.
    # HV battery cell temperature (Celsius). Critical for users with
    # home wallbox curtail automations based on battery thermal limits.
    VagSensorDescription(
        key="battery_temp_c",
        translation_key="battery_temp_c",
        data_key="battery_temp_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ETA in minutes until the climate target temperature is reached.
    VagSensorDescription(
        key="climate_remaining_time_min",
        translation_key="climate_remaining_time_min",
        data_key="climate_remaining_time_min",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.8.0 - Auxiliary heating (Standheizung) status. CARIAD-BFF ships
    # the raw enum string under
    # ``auxiliaryHeating.auxiliaryHeatingStatus.value.{operationMode,
    # climatisationState}``. Common values: "off", "heating", "ventilation",
    # "stopped". Brand-restricted via _DATA_PRESENT_REQUIRED below so
    # non-supporting brands never see a phantom "unknown" entity.
    VagSensorDescription(
        key="auxiliary_heating_status",
        translation_key="auxiliary_heating_status",
        data_key="auxiliary_heating_status",
        icon="mdi:fire",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.8.0 - Auxiliary heating remaining-time. Populated while the
    # pre-heater is running; clears on stop. Same diagnostic semantics
    # as ``climate_remaining_time_min`` next door.
    VagSensorDescription(
        key="auxiliary_heating_remaining_min",
        translation_key="auxiliary_heating_remaining_min",
        data_key="auxiliary_heating_remaining_min",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-sand",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # Readiness deep-diagnostics: connection sub-status string.
    VagSensorDescription(
        key="connection_battery_power_level",
        translation_key="connection_battery_power_level",
        data_key="connection_battery_power_level",
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # OLA-only (SEAT/CUPRA): license plate text from garage payload.
    VagSensorDescription(
        key="license_plate",
        translation_key="license_plate",
        data_key="license_plate",
        icon="mdi:card-text",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # OLA-only: user-chosen vehicle nickname.
    VagSensorDescription(
        key="vehicle_nickname",
        translation_key="vehicle_nickname",
        data_key="vehicle_nickname",
        icon="mdi:car-info",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # OLA-only: parking position map renders (dark + light theme URLs).
    # Useful for Lovelace cards that want to embed a static map.
    VagSensorDescription(
        key="parking_map_url_dark",
        translation_key="parking_map_url_dark",
        data_key="parking_map_url_dark",
        icon="mdi:map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="parking_map_url_light",
        translation_key="parking_map_url_light",
        data_key="parking_map_url_light",
        icon="mdi:map-marker-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v1.27.2 — Visual feedback color of the charge-port LED.
    # none / red (error) / green (idle/done) / blue (charging) — drivable by
    # automations like "notify me when LED turns red".
    VagSensorDescription(
        key="plug_led_color",
        translation_key="plug_led_color",
        data_key="plug_led_color",
        icon="mdi:led-on",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="charging_type",
        translation_key="charging_type",
        data_key="charging_type",
        icon="mdi:ev-plug-type2",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="electric",
    ),
    # v2.31.0 (8.15.0 APK) — Škoda ChargingSettingsDto.preferredChargeMode.
    VagSensorDescription(
        key="preferred_charge_mode",
        translation_key="preferred_charge_mode",
        data_key="preferred_charge_mode",
        icon="mdi:ev-station",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="electric",
    ),
    # v2.31.0 (8.15.0 APK) — Škoda pay-at-pump LAST fill-up (read-only
    # consumption; phantom-gated → only spawns for pay-at-pump users).
    VagSensorDescription(
        key="last_refuel_quantity",
        translation_key="last_refuel_quantity",
        data_key="last_refuel_quantity",
        native_unit_of_measurement="L",
        icon="mdi:fuel",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_refuel_cost",
        translation_key="last_refuel_cost",
        data_key="last_refuel_cost",
        icon="mdi:cash-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_refuel_currency",
        translation_key="last_refuel_currency",
        data_key="last_refuel_currency",
        icon="mdi:currency-eur",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_refuel_fuel_type",
        translation_key="last_refuel_fuel_type",
        data_key="last_refuel_fuel_type",
        icon="mdi:gas-station",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_refuel_station",
        translation_key="last_refuel_station",
        data_key="last_refuel_station",
        icon="mdi:gas-station",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_refuel_at",
        translation_key="last_refuel_at",
        data_key="last_refuel_at",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.31.0 (8.15.0 APK) — Škoda pay-to-park current/last session (read-only;
    # phantom-gated → only spawns for pay-to-park users).
    VagSensorDescription(
        key="parking_location",
        translation_key="parking_location",
        data_key="parking_location",
        icon="mdi:parking",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="parking_cost",
        translation_key="parking_cost",
        data_key="parking_cost",
        icon="mdi:cash-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="parking_currency",
        translation_key="parking_currency",
        data_key="parking_currency",
        icon="mdi:currency-eur",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="parking_started_at",
        translation_key="parking_started_at",
        data_key="parking_started_at",
        icon="mdi:clock-start",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="parking_ended_at",
        translation_key="parking_ended_at",
        data_key="parking_ended_at",
        icon="mdi:clock-end",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.31.0 (8.15.0 APK) — Škoda predictive-maintenance service reminders
    # (read-only; state = due date if present else status). Phantom-gated.
    VagSensorDescription(
        key="reminder_technical_inspection",
        translation_key="reminder_technical_inspection",
        data_key="reminder_technical_inspection",
        icon="mdi:car-wrench",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="reminder_seasonal_tyre_change",
        translation_key="reminder_seasonal_tyre_change",
        data_key="reminder_seasonal_tyre_change",
        icon="mdi:tire",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="reminder_first_aid_kit",
        translation_key="reminder_first_aid_kit",
        data_key="reminder_first_aid_kit",
        icon="mdi:medical-bag",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="reminder_tyre_repair_kit",
        translation_key="reminder_tyre_repair_kit",
        data_key="reminder_tyre_repair_kit",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.31.0 (8.15.0 APK) — Škoda departure-timer times (read-only).
    VagSensorDescription(
        key="departure_timer_1_time",
        translation_key="departure_timer_1_time",
        data_key="departure_timer_1_time",
        icon="mdi:clock-time-four-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="departure_timer_2_time",
        translation_key="departure_timer_2_time",
        data_key="departure_timer_2_time",
        icon="mdi:clock-time-four-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="departure_timer_3_time",
        translation_key="departure_timer_3_time",
        data_key="departure_timer_3_time",
        icon="mdi:clock-time-four-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),


    VagSensorDescription(
        key="climatisation_state",
        translation_key="climatisation_state",
        data_key="climatisation_state",
        icon="mdi:thermometer",
    ),
    VagSensorDescription(
        key="target_temperature",
        translation_key="target_temperature",
        data_key="target_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-auto",
    ),

    VagSensorDescription(
        key="outside_temp",
        translation_key="outside_temp",
        data_key="outside_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
    ),
    # v2.17.1 (Scout #701, VW ID.7) — EU-portal interior temperature.
    # Brand-restricted via _DATA_PRESENT_REQUIRED (portal-only field).
    VagSensorDescription(
        key="cabin_temp",
        translation_key="cabin_temp",
        data_key="cabin_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-thermometer",
    ),

    VagSensorDescription(
        key="service_km",
        translation_key="service_km",
        data_key="service_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wrench-clock",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="service_due_at",
        translation_key="service_due_at",
        data_key="service_due_at",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v1.11.0 (#91 closure) — explicit "days remaining" int sensor
    # alongside the DATE sensor above. The DATE conversion loses the
    # exact day count; this one keeps it for users who want "5 Tage"
    # rather than "May 5". Unit "d" makes HA render "5 d" automatically.
    VagSensorDescription(
        key="service_due_in_days",
        translation_key="service_due_in_days",
        data_key="service_due_in_days",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="oil_service_km",
        translation_key="oil_service_km",
        data_key="oil_service_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil",
        condition="combustion",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="oil_service_at",
        translation_key="oil_service_at",
        data_key="oil_service_at",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:oil",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="combustion",
    ),
    # v1.11.0 (#91 closure) — explicit oil-service days int sensor.
    VagSensorDescription(
        key="oil_service_due_in_days",
        translation_key="oil_service_due_in_days",
        data_key="oil_service_due_in_days",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="combustion",
        suggested_display_precision=0,
    ),

    VagSensorDescription(
        key="vehicle_state",
        translation_key="vehicle_state",
        data_key="vehicle_state",
        icon="mdi:car-info",
    ),
    # v1.8.11 (Session 3S) — Connection-State Sensor.
    # Closes #54 (GitHobi). Three-state derived from carCapturedTimestamp:
    # online (<30 min), standby (<24 h, wakeable), offline (>=24 h, 12V flat
    # / underground / service mode). Currently only populated for Škoda;
    # other brands keep it None so HA shows "unknown" instead of false data.
    # Pattern verified against `homeassistant-myskoda` issues #751, #731.
    VagSensorDescription(
        key="connection_state",
        translation_key="connection_state",
        data_key="connection_state",
        icon="mdi:car-connected",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),

    VagSensorDescription(
        key="parking_address",
        translation_key="parking_address",
        data_key="parking_address",
        icon="mdi:map-marker",
    ),
    VagSensorDescription(
        key="parking_city",
        translation_key="parking_city",
        data_key="parking_city",
        icon="mdi:city",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),

    VagSensorDescription(
        key="battery_temp",
        translation_key="battery_temp",
        data_key="battery_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="electric",
    ),

    VagSensorDescription(
        key="last_updated_at",
        translation_key="last_updated_at",
        data_key="last_updated_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # #465 (@TomJonesGreggs) — the car's own data-capture time, distinct from the
    # poll time above. On a frozen-but-non-empty EU-DA feed the poll keeps
    # succeeding (last_updated_at stays fresh) while the car's data is days old;
    # HA renders this TIMESTAMP as a relative age, so "last reported 2 days ago"
    # next to "last updated 1 minute ago" makes a silent freeze obvious. The value
    # is already captured (last_seen_at) on every channel — this just surfaces it.
    VagSensorDescription(
        key="last_seen_at",
        translation_key="last_seen_at",
        data_key="last_seen_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:car-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),

    # vgql coverage (2026-08-28) — the authoritative drivetrain classification
    # (electric/hybrid/gasoline/diesel) from the vgql we already run for the
    # model name. Diagnostic string, distinct from the is_electric/is_hybrid
    # booleans; phantom-guarded (hidden until the vgql actually supplies it).
    VagSensorDescription(
        key="drive_train",
        translation_key="drive_train",
        data_key="drive_train",
        icon="mdi:car-cog",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # The stable per-vehicle Customer Service ID (vgql `csid`). A durable
    # secondary identifier; disabled by default — power-user / support handle.
    VagSensorDescription(
        key="csid",
        translation_key="csid",
        data_key="csid",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # "Parked since" — the capture time of the current parking position. No new
    # network read: reuses position_captured_at we already fetch. HA renders it
    # as a relative age ("parked 3 h ago").
    VagSensorDescription(
        key="parked_since",
        translation_key="parked_since",
        data_key="position_captured_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:car-clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),

    VagSensorDescription(
        key="departure_timer_1_time",
        translation_key="departure_timer_1_time",
        data_key="departure_timer_1_time",
        icon="mdi:clock-time-eight-outline",
        condition="electric",
    ),
    VagSensorDescription(
        key="departure_timer_2_time",
        translation_key="departure_timer_2_time",
        data_key="departure_timer_2_time",
        icon="mdi:clock-time-eight-outline",
        condition="electric",
    ),
    VagSensorDescription(
        key="departure_timer_3_time",
        translation_key="departure_timer_3_time",
        data_key="departure_timer_3_time",
        icon="mdi:clock-time-eight-outline",
        condition="electric",
    ),

    # ── AdBlue (Diesel) ──────────────────────────────────────────────────────
    VagSensorDescription(
        key="adblue_range_km",
        translation_key="adblue_range_km",
        data_key="adblue_range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-check",
        condition="combustion",
        suggested_display_precision=0,
    ),

    # v1.11.0 (#91 closure) — vehicle lights count.
    # ``lights_count`` is the on-light count from
    # ``vehicleLights.lightsStatus.value.lights[]``. Created only when
    # the field is non-None (data-present-gated, like the v1.10.0
    # range entities) so vehicles whose API doesn't expose lights
    # don't get a phantom "0" entity.
    VagSensorDescription(
        key="lights_count",
        translation_key="lights_count",
        data_key="lights_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightbulb-on-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),

    # v1.11.0 (#91 closure, #90 verified) — max charge current (Ampere)
    # as a read-only Sensor. The v1.9.1 Vehicle Data Scout findings
    # showed this as ``charging.chargingSettings.value.maxChargeCurrentAC_A
    # = 16`` on the Golf 7 GTE — clean integer, suitable for direct
    # display. v1.12.0 also exposes a writeable Number entity for the
    # same field (see number.py); the read-only Sensor stays as a
    # quick at-a-glance diagnostic.
    VagSensorDescription(
        key="max_charge_current_a",
        translation_key="max_charge_current_a",
        data_key="max_charge_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),

    # v1.12.0 (#23) — 12V starter battery voltage. Older vehicles see
    # silent API outages when 12V drops below ~10.8 V because the
    # cellular modem can't keep itself awake. This sensor surfaces the
    # voltage so users see "go to garage" warnings before the integration
    # appears to "stop working".
    VagSensorDescription(
        key="voltage_12v",
        translation_key="voltage_12v",
        data_key="voltage_12v",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),

    # v1.12.0 (#55) — daily wake-up counter. Vehicles cap remote wake-up
    # commands per day (typically 3-5 depending on backend). Once
    # exceeded the car silently ignores wake requests until midnight.
    # This sensor surfaces the count so users + automations can budget.
    VagSensorDescription(
        key="wake_count_today",
        translation_key="wake_count_today",
        data_key="wake_count_today",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alarm-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    # v1.19.1 — Pycupra-style API quota visibility. Populated from
    # X-RateLimit-Remaining response header when the backend sends it
    # (most VAG endpoints do; older firmwares omit). Community research:
    # MyCupra/MySeat ~1500 calls/day, OLA + mysmob behave similarly.
    #
    # No phantom 0 on a header-less backend: the value stays None and the
    # ``hide_empty`` gate (default on) skips the sensor at spawn time — see
    # the spawn loop below. This trio is deliberately NOT in
    # ``_DATA_PRESENT_REQUIRED``, despite an earlier comment here claiming so.
    # That set is for fields a given car's API will never publish (brand or
    # capability); a rate-limit header is transport metadata that can show up
    # on the first response that carries it, which is precisely the "starts as
    # None and populates later" case the set's own docstring says not to gate.
    # With hide_empty off the user has asked to see everything, unknowns
    # included, so there is nothing to protect them from here.
    VagSensorDescription(
        key="requests_remaining_today",
        translation_key="requests_remaining_today",
        data_key="requests_remaining_today",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge-low",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    # v1.20.0 Bundle 2 Phase A (myskoda PR #557 widget + vehicle-info).
    # equipment_count (from equipment endpoint, 24h cache) enriches DeviceInfo
    # for Skoda vehicles; data-present-gated so non-Skoda brands don't get a
    # phantom entity. (The license_plate description that was here duplicated the
    # authoritative OLA def above on the same `key=` — HA's last-wins dict
    # silently dropped one — so the duplicate is removed.)
    VagSensorDescription(
        key="equipment_count",
        translation_key="equipment_count",
        data_key="equipment_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:format-list-bulleted",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    # v1.15.0 — Skoda software-version (mysmob, app v8.10.0+).
    # Population depends on Skoda backend; entity is gated via
    # ``_DATA_PRESENT_REQUIRED`` so non-Skoda vehicles + older Skoda
    # firmwares don't get a phantom "unknown" entity.
    VagSensorDescription(
        key="software_version",
        translation_key="software_version",
        data_key="software_version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v1.15.0 (#35) — Skoda Charging History → HA Energy Dashboard.
    # ``total_charged_energy_kwh`` with TOTAL_INCREASING is THE long-
    # term-statistics signal users want for kWh-tracking dashboards.
    # Last-session sensors complement with at-a-glance recent context.
    # ``recent_charging_sessions`` (last 5) lives in the
    # ``total_charged_energy_kwh.extra_state_attributes`` (same audi
    # #113 pattern we used for Trip Stats in v1.14.0).
    VagSensorDescription(
        key="total_charged_energy_kwh",
        translation_key="total_charged_energy_kwh",
        data_key="total_charged_energy_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt-circle",
        suggested_display_precision=2,
        condition="electric",
    ),
    VagSensorDescription(
        key="last_charging_session_kwh",
        translation_key="last_charging_session_kwh",
        data_key="last_charging_session_kwh",
        native_unit_of_measurement="kWh",
        # b1 — HA 2026.6 rejects device_class=energy + state_class=measurement
        # (energy needs total/total_increasing). These are per-session/trip delta
        # measurements, not cumulative counters → drop device_class, keep kWh.
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging",
        suggested_display_precision=2,
        condition="electric",
    ),
    VagSensorDescription(
        key="last_charging_session_duration_min",
        translation_key="last_charging_session_duration_min",
        data_key="last_charging_session_duration_min",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        suggested_display_precision=0,
        condition="electric",
    ),
    # v2.10.0 (charging_statistics) - SEAT/CUPRA per-session detail from
    # the charging.cariad.digital host. Skoda already populates the same
    # last_charging_session_* fields from mysmob (v1.15.0 #35); SEAT/CUPRA
    # gained these in v2.10.0 via the new charging-stats host. Both fields
    # below are gated by _DATA_PRESENT_REQUIRED so non-EV cars and brands
    # without the host stay clean.
    VagSensorDescription(
        key="last_charging_session_start",
        translation_key="last_charging_session_start",
        data_key="last_charging_session_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        condition="electric",
    ),
    VagSensorDescription(
        key="last_charging_session_current_type",
        translation_key="last_charging_session_current_type",
        data_key="last_charging_session_current_type",
        icon="mdi:ev-plug-type2",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.10.0 (charging_statistics) - per-session power-curve samples.
    # State is the COUNT of points to keep HA recorder usage low; the
    # full sample list lives in extra_state_attributes (see
    # VagConnectSensor.extra_state_attributes below). Useful for
    # Lovelace cards that graph kW over time for the last DC fast-charge.
    VagSensorDescription(
        key="last_charging_power_curve_points",
        translation_key="last_charging_power_curve_points",
        data_key="last_charging_power_curve_points",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        condition="electric",
    ),
    # v1.16.0 (#25, #31) — Skoda Charging Profiles read-only sensors.
    # The killer field: ``active_charging_profile_name`` from the
    # backend's ``currentVehiclePositionProfile`` (the backend already
    # decided which profile is active based on the car's current GPS
    # position — solves #25 location-based target SoC without any
    # client-side GPS-zone matching).
    VagSensorDescription(
        key="active_charging_profile_name",
        translation_key="active_charging_profile_name",
        data_key="active_charging_profile_name",
        icon="mdi:map-marker-radius",
        condition="electric",
    ),
    VagSensorDescription(
        key="active_charging_profile_target_soc_pct",
        translation_key="active_charging_profile_target_soc_pct",
        data_key="active_charging_profile_target_soc_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging-90",
        suggested_display_precision=0,
        condition="electric",
    ),
    VagSensorDescription(
        key="next_charging_time",
        translation_key="next_charging_time",
        data_key="next_charging_time",
        icon="mdi:clock-time-eight-outline",
        condition="electric",
    ),
    VagSensorDescription(
        key="charging_profiles_count",
        translation_key="charging_profiles_count",
        data_key="charging_profiles_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:format-list-numbered",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        condition="electric",
    ),
    # v1.17.1 (Bruno seq 10/11) — SEAT/CUPRA Battery Care read-only.
    # Two thin OLA endpoints surface battery-care mode + target SoC.
    # Skoda has equivalent under different paths (covered v1.15.0 cap-id
    # work). Brand-restricted via _DATA_PRESENT_REQUIRED gating below.
    # NOTE: the battery_care_target_soc_pct description lives further down as
    # the DIAGNOSTIC mirror (v2.10.0); the duplicate that was here collided on
    # the same `key=` and was silently dropped by HA's last-wins dict, so it is
    # removed (one authoritative def, no behaviour change).
    # v2.0.0 (Big-Bang) — Skoda driving-score (efficiency metric 0-100).
    # mysmob ``GET /api/v2/vehicle-status/{vin}/driving-score`` (MY24+).
    # Brand-restricted via _DATA_PRESENT_REQUIRED — non-Skoda vehicles
    # leave both fields None, so no phantom entity is created.
    VagSensorDescription(
        key="driving_score",
        translation_key="driving_score",
        data_key="driving_score",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:medal-outline",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="driving_score_class",
        translation_key="driving_score_class",
        data_key="driving_score_class",
        icon="mdi:gauge",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.0.0 (Big-Bang) — Porsche TPMS (4 corners). PPA only — Cariad/OLA/
    # mysmob status endpoints don't expose per-tire pressure today.
    # Brand-restricted via _DATA_PRESENT_REQUIRED — non-Porsche vehicles
    # (and pre-TPMS Porsche models) leave fields None → no phantom entity.
    VagSensorDescription(
        key="tire_pressure_front_left_bar",
        translation_key="tire_pressure_front_left_bar",
        data_key="tire_pressure_front_left_bar",
        native_unit_of_measurement="bar",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:tire",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="tire_pressure_front_right_bar",
        translation_key="tire_pressure_front_right_bar",
        data_key="tire_pressure_front_right_bar",
        native_unit_of_measurement="bar",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:tire",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="tire_pressure_rear_left_bar",
        translation_key="tire_pressure_rear_left_bar",
        data_key="tire_pressure_rear_left_bar",
        native_unit_of_measurement="bar",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:tire",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="tire_pressure_rear_right_bar",
        translation_key="tire_pressure_rear_right_bar",
        data_key="tire_pressure_rear_right_bar",
        native_unit_of_measurement="bar",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:tire",
        suggested_display_precision=2,
    ),
    # v2.0.0 (Big-Bang) — Vehicle alarm timestamp (issue #33).
    # Records when the alarm last triggered. Brand-restricted via
    # _DATA_PRESENT_REQUIRED — only populated when Cariad-BFF actually
    # publishes the field (cars without alarm telemetry stay None).
    VagSensorDescription(
        key="last_alarm_at",
        translation_key="last_alarm_at",
        data_key="last_alarm_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:shield-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.0.0 (Big-Bang) — heaterSource read-only sensor (issue #163).
    # ID.x heat-pump cars publish "electric"/"fuel" in
    # climatisationSettings.value.heaterSource. Brand-restricted via
    # _DATA_PRESENT_REQUIRED — non-heat-pump cars leave the field None
    # → no phantom entity is spawned. Diagnostic category since the
    # value is a niche enum used mostly for power-user automations.
    VagSensorDescription(
        key="heater_source",
        translation_key="heater_source",
        data_key="heater_source",
        icon="mdi:radiator",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="electric",
    ),
    # v2.1.0 — Skoda climate-ready-at (closes Scout #186 + #188).
    # ISO-8601 timestamp when the cabin is expected to reach the
    # target temperature. Only populated during active climate run.
    # Brand-restricted via _DATA_PRESENT_REQUIRED — Skoda-only today.
    # Device class TIMESTAMP renders as relative time in HA UI
    # ("in 8 minutes") and is automation-friendly with template
    # ``{{ as_datetime(states('sensor.x')) - 5|minutes }}`` for
    # "5min before climate ready" triggers.
    VagSensorDescription(
        key="climate_ready_at",
        translation_key="climate_ready_at",
        data_key="climate_ready_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-end",
    ),

    # ── v1.9.0 Vehicle Data Scout + Error Reporter ────────────────────────────
    # Two diagnostic sensors that surface drift / runtime errors detected
    # by the integration so users can 1-click report them via the HA Repair
    # dashboard. data_key="" — value comes from coordinator helpers, not
    # the vehicle dict — see ``ReporterSensor.native_value``.
    # ── v1.14.0 (#24) — Trip Statistics (Audi + VW EU) ────────────────
    # Subscription-required (Audi connect Plus / WeConnect Plus).
    # Phase 3 capability gate (#56) hides these entities for accounts
    # without the subscription. Data populated by 1h cache cycle in
    # ``coordinator.refresh_trip_statistics`` from the CARIAD-BFF
    # ``GET /vehicle/v1/vehicles/{vin}/tripstatistics`` endpoint.
    # ``recent_trips`` (list of last 5) lives in
    # ``last_trip_distance_km.extra_state_attributes`` to avoid the
    # 255-char state limit for list-shaped data.
    VagSensorDescription(
        key="last_trip_distance_km",
        translation_key="last_trip_distance_km",
        data_key="last_trip_distance_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:road-variant",
        suggested_display_precision=1,
    ),
    # v2.10.0 - last-trip reset timestamp (audi_connect_ha parity).
    VagSensorDescription(
        key="last_trip_reset_at",
        translation_key="last_trip_reset_at",
        data_key="last_trip_reset_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_trip_avg_speed_kmh",
        translation_key="last_trip_avg_speed_kmh",
        data_key="last_trip_avg_speed_kmh",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        suggested_display_precision=0,
    ),
    # b10 — EU Data Act portal long-tail trip/maintenance sensors.
    VagSensorDescription(
        key="lifetime_avg_speed_kmh",
        translation_key="lifetime_avg_speed_kmh",
        data_key="lifetime_avg_speed_kmh",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer-medium",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="lifetime_travel_time_min",
        translation_key="lifetime_travel_time_min",
        data_key="lifetime_travel_time_min",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        # HA audit — a lifetime cumulative counter (like its lifetime_distance_km /
        # lifetime_zero_emission_km siblings) had no state_class, so it got zero
        # long-term statistics. TOTAL_INCREASING enables them (HA handles resets).
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:timer-outline",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="monthly_mileage_km",
        translation_key="monthly_mileage_km",
        data_key="monthly_mileage_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:road-variant",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="remaining_charge_time_min",
        translation_key="remaining_charge_time_min",
        data_key="remaining_charge_time_min",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-clock",
    ),
    VagSensorDescription(
        key="last_trip_avg_fuel_consumption_l_100km",
        translation_key="last_trip_avg_fuel_consumption_l_100km",
        data_key="last_trip_avg_fuel_consumption_l_100km",
        native_unit_of_measurement="L/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
        suggested_display_precision=1,
        condition="combustion",
    ),
    VagSensorDescription(
        key="last_trip_avg_electric_consumption_kwh_100km",
        translation_key="last_trip_avg_electric_consumption_kwh_100km",
        data_key="last_trip_avg_electric_consumption_kwh_100km",
        native_unit_of_measurement="kWh/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        suggested_display_precision=1,
        condition="electric",
    ),

    VagSensorDescription(
        key="api_observer_findings",
        translation_key="api_observer_findings",
        data_key="",
        icon="mdi:radar",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # b1/A6 — raw field discovery. ONE diagnostic sensor (disabled by default)
    # whose state is the count of portal fields the curated parser did not map;
    # the full {field: value} set lives in attributes. Same detection as the
    # Scout report — the user gets every value the backend sent without waiting
    # for a curated mapping, and without an entity per field. Gated on data
    # present so only vehicles that actually have unmapped fields get it.
    VagSensorDescription(
        key="raw_api_fields",
        translation_key="raw_api_fields",
        data_key="raw_unmapped_fields",
        icon="mdi:code-json",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # b1/C1 — data provenance. Shows which channel(s) produced the snapshot,
    # e.g. "eu_data_act+mbb" when several contributed, or the single channel's
    # name when one did.
    # v2.18.0 (B2) — this used to appear only on multi-channel entries, because
    # a car with no supplementary channel skipped the merge and so had no
    # provenance at all. Every snapshot is attributed now, so the sensor answers
    # "where is this car's data from" for everyone. Still gated on data-present,
    # so a car that produced nothing yet doesn't get a phantom.
    VagSensorDescription(
        key="data_source_channel",
        translation_key="data_source_channel",
        data_key="source_channel",
        icon="mdi:transit-connection-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="error_reporter_count",
        translation_key="error_reporter_count",
        data_key="",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # v2.7.0b11 — comma-joined string of every backend warning.
    # Surfaces brand-specific warning types (Audi STO/towing-bracket,
    # etc) that the warning_oil/engine/brake/tyre family of binary
    # sensors misses. Text-only diagnostic sensor.
    VagSensorDescription(
        key="warning_messages",
        translation_key="warning_messages",
        data_key="warning_messages",
        icon="mdi:alert-decagram-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Service / recall campaigns the manufacturer app shows (dealer actions +
    # software-update campaigns), from the CARIAD-BFF warnings block. Text-only
    # diagnostic sensor, disabled by default (most cars have none).
    VagSensorDescription(
        key="service_campaigns",
        translation_key="service_campaigns",
        data_key="service_campaigns",
        icon="mdi:bullhorn-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v1.26.0 Welle-6 Feature Backlog (#173) — new sensors from scout reports.
    VagSensorDescription(
        key="secondary_engine_range_km",
        translation_key="secondary_engine_range_km",
        data_key="secondary_engine_range_km",
        native_unit_of_measurement="km",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station-outline",
        condition="combustion",
        suggested_display_precision=0,
    ),
    # v2.2.0 (Skoda Scout #220 — Daniel Walter 2026-05-16) — companion
    # fields that shipped when ``secondaryEngineRange`` expanded from
    # 1-key (distanceInKm) to 4-key shape.
    VagSensorDescription(
        key="secondary_engine_type",
        translation_key="secondary_engine_type",
        data_key="secondary_engine_type",
        icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="combustion",
    ),
    VagSensorDescription(
        key="secondary_engine_fuel_level_pct",
        translation_key="secondary_engine_fuel_level_pct",
        data_key="secondary_engine_fuel_level_pct",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
        condition="combustion",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="next_charging_timer_id",
        translation_key="next_charging_timer_id",
        data_key="next_charging_timer_id",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="electric",
    ),
    # v2.2.0 Phase 2 PR #8/20 — SEAT/CUPRA Connect-subscription expiry.
    # Surfaces "first to expire" date across all entitled services so
    # users can plan renewal. ISO 8601 → device_class=TIMESTAMP renders
    # as "in 47 days" / calendar date in HA UI. Brand-restricted via
    # _DATA_PRESENT_REQUIRED — other brands stay None → no phantom.
    VagSensorDescription(
        key="subscription_expiry_at",
        translation_key="subscription_expiry_at",
        data_key="subscription_expiry_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 Phase 7 PR #1 — quick-wins batch from scout-audit.
    # Three sensor entities for fields silenced in `_unexpected_keys.py`
    # but never exposed: 12V SoC, steering-wheel position, HV battery
    # max temp. All phantom-protected via `_DATA_PRESENT_REQUIRED`.
    VagSensorDescription(
        key="primary_engine_soc_pct",
        translation_key="primary_engine_soc_pct",
        data_key="primary_engine_soc_pct",
        native_unit_of_measurement="%",
        # HA audit — a battery state-of-charge %, so tag it BATTERY like its
        # aux_battery_energy_pct sibling (icon/UX; MEASUREMENT already gives history).
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="steering_wheel_position",
        translation_key="steering_wheel_position",
        data_key="steering_wheel_position",
        icon="mdi:steering",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="battery_temp_max",
        translation_key="battery_temp_max",
        data_key="battery_temp_max",
        native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    # v2.17.1 (Scout #701, VW ID.7) — EU-portal charge-target time
    # (ISO ts) + vehicle-profile user capacity. Both portal-only,
    # brand-restricted via _DATA_PRESENT_REQUIRED. Diagnostic category.
    VagSensorDescription(
        key="charge_target_time",
        translation_key="charge_target_time",
        data_key="charge_target_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:battery-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="max_number_users",
        translation_key="max_number_users",
        data_key="max_number_users",
        icon="mdi:account-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 Phase 7 PR #2 — VW EU + Audi aggregate count of enabled
    # departure timers (0-3). Saves users the templating effort of
    # summing 3 separate binary states. Diagnostic category.
    VagSensorDescription(
        key="departure_timer_enabled_count",
        translation_key="departure_timer_enabled_count",
        data_key="departure_timer_enabled_count",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 Phase 7 PR #3 — SEAT/CUPRA `engines.primary` block.
    # Companion to PR #6/#18 secondary_engine_* fields.
    VagSensorDescription(
        key="primary_engine_type",
        translation_key="primary_engine_type",
        data_key="primary_engine_type",
        icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="fuel_tank_capacity_liters",
        translation_key="fuel_tank_capacity_liters",
        data_key="fuel_tank_capacity_liters",
        native_unit_of_measurement="L",
        icon="mdi:gas-station",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        condition="combustion",
    ),
    # acpp plug&play — absolute fuel in the tank (litres) from the OBD dongle.
    VagSensorDescription(
        key="fuel_level_liters",
        translation_key="fuel_level_liters",
        data_key="fuel_level_liters",
        native_unit_of_measurement="L",
        icon="mdi:gas-station",
        suggested_display_precision=1,
        condition="combustion",
    ),
    # acpp plug&play — factory master-data (carport) bonus sensors.
    VagSensorDescription(
        key="exterior_color", translation_key="exterior_color",
        data_key="exterior_color", icon="mdi:palette",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="engine_power", translation_key="engine_power",
        data_key="engine_power", icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="engine_torque_nm", translation_key="engine_torque_nm",
        data_key="engine_torque_nm", native_unit_of_measurement="Nm",
        icon="mdi:engine", entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="engine_cylinders", translation_key="engine_cylinders",
        data_key="engine_cylinders", icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="engine_displacement_ccm", translation_key="engine_displacement_ccm",
        data_key="engine_displacement_ccm", native_unit_of_measurement="cm³",
        icon="mdi:engine", entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="engine_code", translation_key="engine_code",
        data_key="engine_code", icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="fuel_type", translation_key="fuel_type",
        data_key="fuel_type", icon="mdi:fuel",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # "Datenstand" — when the dongle last synced its snapshot. Renders as a
    # relative age in HA, so users see how fresh the reading is.
    VagSensorDescription(
        key="data_captured_at", translation_key="data_captured_at",
        data_key="data_captured_at", device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="transmission", translation_key="transmission",
        data_key="transmission", icon="mdi:car-shift-pattern",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="interior_color", translation_key="interior_color",
        data_key="interior_color", icon="mdi:palette",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 Phase 7 PR #4 — Skoda tier-B from scout-audit.
    # Climate-timer count (parity to VW EU/Audi PR #2 departure
    # timer count) + running-requests count (diagnostic for
    # "start_climatisation does nothing" failure mode).
    VagSensorDescription(
        key="climate_timer_enabled_count",
        translation_key="climate_timer_enabled_count",
        data_key="climate_timer_enabled_count",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="climate_running_requests_count",
        translation_key="climate_running_requests_count",
        data_key="climate_running_requests_count",
        icon="mdi:progress-clock",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.1 Phase 8 PR #1 — "alles parsen" strategy. 3 new Skoda
    # sensors aus dem reverse-audit. All defensive + phantom-protected.
    VagSensorDescription(
        key="car_type",
        translation_key="car_type",
        data_key="car_type",
        icon="mdi:car-info",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.23.1 — this is the same combustion-tank percentage as the primary
    # "fuel_level" sensor (fuel_level even falls back to this very field), so
    # showing both was a duplicate ("Tankstand" + "Tankfüllstand (primär)").
    # Demote it to a diagnostic, disabled-by-default comparison value instead of
    # deleting it (entity_id + registry entry preserved); fuel_level stays the
    # primary user-facing tank sensor.
    VagSensorDescription(
        key="primary_engine_fuel_level_pct",
        translation_key="primary_engine_fuel_level_pct",
        data_key="primary_engine_fuel_level_pct",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
        condition="combustion",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="maintenance_report_captured_at",
        translation_key="maintenance_report_captured_at",
        data_key="maintenance_report_captured_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ── v2.16.0 — volkswagen.de authproxy live-status read-path (BETA) ────────
    # All three disabled-by-default: the underlying live endpoints
    # (warninglights/last + transactionhistory) are unvalidated, so the user
    # opts in to test. Only the authproxy channel populates these fields, so
    # every other brand/entry leaves them None (phantom-protected below).
    VagSensorDescription(
        key="active_warning_lights_count",
        translation_key="active_warning_lights_count",
        data_key="active_warning_lights_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-light-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="last_lock_action",
        translation_key="last_lock_action",
        data_key="last_lock_action",
        icon="mdi:car-key",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="last_lock_action_at",
        translation_key="last_lock_action_at",
        data_key="last_lock_action_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.8.0 quick win C — brake-service due timestamps + preferred-
    # workshop. The parser populates these only when the brand backend
    # actually ships them. Listed in _DATA_PRESENT_REQUIRED below so
    # non-applicable vehicles do not get phantom "Unbekannt" sensors.
    VagSensorDescription(
        key="brake_fluid_change_due_at",
        translation_key="brake_fluid_change_due_at",
        data_key="brake_fluid_change_due_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:car-brake-fluid-level",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="brake_pads_front_inspection_due_at",
        translation_key="brake_pads_front_inspection_due_at",
        data_key="brake_pads_front_inspection_due_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:car-brake-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="brake_pads_rear_inspection_due_at",
        translation_key="brake_pads_rear_inspection_due_at",
        data_key="brake_pads_rear_inspection_due_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:car-brake-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="preferred_workshop_name",
        translation_key="preferred_workshop_name",
        data_key="preferred_workshop_name",
        icon="mdi:store",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="preferred_workshop_address",
        translation_key="preferred_workshop_address",
        data_key="preferred_workshop_address",
        icon="mdi:map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="preferred_workshop_phone",
        translation_key="preferred_workshop_phone",
        data_key="preferred_workshop_phone",
        icon="mdi:phone",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.8.1 #306 — 5 P1 numeric/string OLA-field gaps surfaced via
    # pycupra side-by-side. The 6 boolean fields in this set
    # (parking_light, seat_heating, external_power, battery_care,
    # energy_flow, area_alarm) are wired in binary_sensor.py.
    VagSensorDescription(
        key="adblue_level_pct",
        translation_key="adblue_level_pct",
        data_key="adblue_level_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="cng_level_pct",
        translation_key="cng_level_pct",
        data_key="cng_level_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="cng_range_km",
        translation_key="cng_range_km",
        data_key="cng_range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="primary_engine_range_km",
        translation_key="primary_engine_range_km",
        data_key="primary_engine_range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:road-variant",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="charging_preferred_mode",
        translation_key="charging_preferred_mode",
        data_key="charging_preferred_mode",
        icon="mdi:cog-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.10.0 (#389 scout) — pending-action surface. CARIAD BFF ships
    # access.accessStatus.requests when a lock/unlock/climate command
    # was dispatched and the vehicle has not yet confirmed. Three
    # sensors expose the most-recent entry so HA scripts can wait for
    # action acknowledgement instead of fixed sleeps.
    VagSensorDescription(
        key="pending_action_id",
        translation_key="pending_action_id",
        data_key="pending_action_id",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="pending_action_type",
        translation_key="pending_action_type",
        data_key="pending_action_type",
        icon="mdi:gesture-tap",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="pending_action_status",
        translation_key="pending_action_status",
        data_key="pending_action_status",
        icon="mdi:progress-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.10.0 - refuel-trip aggregator (since last tank fill / charge).
    # CARIAD BFF tripstatistics?type=cyclic. Energy-Dashboard friendly.
    VagSensorDescription(
        key="refuel_trip_distance_km",
        translation_key="refuel_trip_distance_km",
        data_key="refuel_trip_distance_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-path",
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="refuel_trip_duration_min",
        translation_key="refuel_trip_duration_min",
        data_key="refuel_trip_duration_min",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    VagSensorDescription(
        key="refuel_trip_avg_speed_kmh",
        translation_key="refuel_trip_avg_speed_kmh",
        data_key="refuel_trip_avg_speed_kmh",
        native_unit_of_measurement="km/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer-medium",
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="refuel_trip_avg_fuel_consumption_l_100km",
        translation_key="refuel_trip_avg_fuel_consumption_l_100km",
        data_key="refuel_trip_avg_fuel_consumption_l_100km",
        native_unit_of_measurement="L/100km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="refuel_trip_avg_electric_consumption_kwh_100km",
        translation_key="refuel_trip_avg_electric_consumption_kwh_100km",
        data_key="refuel_trip_avg_electric_consumption_kwh_100km",
        native_unit_of_measurement="kWh/100km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="refuel_trip_total_fuel_consumption_l",
        translation_key="refuel_trip_total_fuel_consumption_l",
        data_key="refuel_trip_total_fuel_consumption_l",
        native_unit_of_measurement="L",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:fuel",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="refuel_trip_total_electric_consumption_kwh",
        translation_key="refuel_trip_total_electric_consumption_kwh",
        data_key="refuel_trip_total_electric_consumption_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="refuel_trip_recuperation_kwh",
        translation_key="refuel_trip_recuperation_kwh",
        data_key="refuel_trip_recuperation_kwh",
        native_unit_of_measurement="kWh",
        # b1 — HA 2026.6: energy device_class needs total/total_increasing, not
        # measurement. Per-trip delta → drop device_class, keep kWh.
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-arrow-up-outline",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="refuel_trip_timestamp",
        translation_key="refuel_trip_timestamp",
        data_key="refuel_trip_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.10.0 - battery-care target SOC (read-only diag mirror; the
    # number entity for setting it is wired separately in number.py).
    VagSensorDescription(
        key="battery_care_target_soc_pct",
        translation_key="battery_care_target_soc_pct",
        data_key="battery_care_target_soc_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.10.0 - real-time charge rate, distinct from averaged
    # charging_rate_kmh. Only some CARIAD BFF firmware exposes this.
    VagSensorDescription(
        key="actual_charge_rate_kw",
        translation_key="actual_charge_rate_kw",
        data_key="actual_charge_rate_kw",
        native_unit_of_measurement="kW",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        suggested_display_precision=2,
    ),
    # v2.2.0 Phase 2 PR #11/20 — derived integer days until expiry.
    # Closes the subscription-feature triangle (timestamp + active +
    # days). Negative when expired. Automation-friendly: threshold
    # triggers like ``if state(...) < 30 → notify`` are trivial against
    # an int sensor (much easier than templating against a TIMESTAMP).
    VagSensorDescription(
        key="subscription_days_remaining",
        translation_key="subscription_days_remaining",
        data_key="subscription_days_remaining",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-end",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="next_charging_timer_target_soc_reachable",
        translation_key="next_charging_timer_target_soc_reachable",
        data_key="next_charging_timer_target_soc_reachable",
        icon="mdi:battery-charging-high",
        condition="electric",
    ),
    VagSensorDescription(
        key="capabilities_count",
        translation_key="capabilities_count",
        data_key="capabilities_count",
        icon="mdi:format-list-numbered",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # v2.0.0 (Big-Bang) — Long-Term Trip Aggregates [NEW v2.0].
    # Coordinator already merges ``longTerm`` (since-last-reset) data
    # into ``lifetime_*`` fields on VehicleData; v2.0.0 finally promotes
    # them to first-class entities. Brand-restricted via the existing
    # _TRIP_STATS_BRANDS / _TRIP_STATS_KEYS gating below (Audi + VW EU
    # only — CARIAD-BFF /tripstatistics endpoint).
    VagSensorDescription(
        key="lifetime_distance_km",
        translation_key="lifetime_distance_km",
        data_key="lifetime_distance_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="lifetime_avg_fuel_consumption_l_100km",
        translation_key="lifetime_avg_fuel_consumption_l_100km",
        data_key="lifetime_avg_fuel_consumption_l_100km",
        native_unit_of_measurement="L/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
        suggested_display_precision=1,
        condition="combustion",
    ),
    VagSensorDescription(
        key="lifetime_avg_electric_consumption_kwh_100km",
        translation_key="lifetime_avg_electric_consumption_kwh_100km",
        data_key="lifetime_avg_electric_consumption_kwh_100km",
        native_unit_of_measurement="kWh/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        suggested_display_precision=1,
        condition="electric",
    ),
    # v2.10.0 Group A - VW EU field parity additions. Phantom-protected
    # via ``_DATA_PRESENT_REQUIRED`` below: cars without the underlying
    # field stay clean.
    VagSensorDescription(
        key="hv_battery_min_temperature_c",
        translation_key="hv_battery_min_temperature_c",
        data_key="hv_battery_min_temperature_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-low",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="hv_battery_max_temperature_c",
        translation_key="hv_battery_max_temperature_c",
        data_key="hv_battery_max_temperature_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-high",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="charge_max_ac_setting",
        translation_key="charge_max_ac_setting",
        data_key="charge_max_ac_setting",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charge_max_ac_ampere",
        translation_key="charge_max_ac_ampere",
        data_key="charge_max_ac_ampere",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="auto_release_ac_connector_state",
        translation_key="auto_release_ac_connector_state",
        data_key="auto_release_ac_connector_state",
        icon="mdi:ev-plug-ccs2",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="active_ventilation_state",
        translation_key="active_ventilation_state",
        data_key="active_ventilation_state",
        icon="mdi:fan",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="active_ventilation_remaining_time_min",
        translation_key="active_ventilation_remaining_time_min",
        data_key="active_ventilation_remaining_time_min",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="connection_state_battery_power_level",
        translation_key="connection_state_battery_power_level",
        data_key="connection_state_battery_power_level",
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_trip_total_fuel_consumption_l",
        translation_key="last_trip_total_fuel_consumption_l",
        data_key="last_trip_total_fuel_consumption_l",
        native_unit_of_measurement="L",
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-station",
        suggested_display_precision=2,
        condition="combustion",
    ),
    VagSensorDescription(
        key="last_trip_total_electric_consumption_kwh",
        translation_key="last_trip_total_electric_consumption_kwh",
        data_key="last_trip_total_electric_consumption_kwh",
        native_unit_of_measurement="kWh",
        # b1 — HA 2026.6: energy device_class needs total/total_increasing, not
        # measurement. Per-trip delta → drop device_class, keep kWh.
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        suggested_display_precision=2,
        condition="electric",
    ),
    # v2.10.0 Group B — SEAT/CUPRA OLA endpoint parity.
    # Notifications endpoint surface (3 entries) plus 2 engine
    # measurement temperatures. ``charging_profiles_*`` reuses the
    # Skoda surface so no new descriptions are needed; the charging
    # modes list lives as an attribute on ``charging_preferred_mode``.
    # All phantom-protected via _DATA_PRESENT_REQUIRED below.
    VagSensorDescription(
        key="notifications_count",
        translation_key="notifications_count",
        data_key="notifications_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bell-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_notification_subject",
        translation_key="last_notification_subject",
        data_key="last_notification_subject",
        icon="mdi:bell-ring-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="last_notification_severity",
        translation_key="last_notification_severity",
        data_key="last_notification_severity",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="engine_oil_temperature_c",
        translation_key="engine_oil_temperature_c",
        data_key="engine_oil_temperature_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil-temperature",
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="engine_coolant_temperature_c",
        translation_key="engine_coolant_temperature_c",
        data_key="engine_coolant_temperature_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-water",
        suggested_display_precision=1,
    ),

    # ── v2.15.1 — EU Data Act + BFF wire-key mapping (2.15.0 plan) ──────────
    # EU Data Act dialect sensors.
    VagSensorDescription(
        key="charging_scenario",
        translation_key="charging_scenario",
        data_key="charging_scenario",
        icon="mdi:ev-station",
        condition="electric",
    ),
    VagSensorDescription(
        key="immediate_charge_action_state",
        translation_key="immediate_charge_action_state",
        data_key="immediate_charge_action_state",
        icon="mdi:flash-alert",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="profile_charge_reason",
        translation_key="profile_charge_reason",
        data_key="profile_charge_reason",
        icon="mdi:help-rhombus-outline",
        condition="electric",
    ),
    VagSensorDescription(
        key="charge_session_energy_kwh",
        translation_key="charge_session_energy_kwh",
        data_key="charge_session_energy_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-charging",
        suggested_display_precision=2,
        condition="electric",
    ),
    VagSensorDescription(
        key="remaining_charge_time_bulk_min",
        translation_key="remaining_charge_time_bulk_min",
        data_key="remaining_charge_time_bulk_min",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:clock-fast",
        condition="electric",
    ),
    VagSensorDescription(
        key="odometer_state",
        translation_key="odometer_state",
        data_key="odometer_state",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="instrument_cluster_time",
        translation_key="instrument_cluster_time",
        data_key="instrument_cluster_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # #604 Scout — HV-battery status flag (battery_level_HV.state enum). Dict
    # lists no value tokens → LOW confidence, disabled-by-default.
    VagSensorDescription(
        key="hv_battery_state",
        translation_key="hv_battery_state",
        data_key="hv_battery_state",
        icon="mdi:battery-heart-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="data_error_detail",
        translation_key="data_error_detail",
        data_key="data_error_detail",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.15.2 — EU Data Act portal "charger detail" fields (#513 Scout).
    VagSensorDescription(
        key="external_power_supply_state",
        translation_key="external_power_supply_state",
        data_key="external_power_supply_state",
        icon="mdi:power-plug-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="charging_reason",
        translation_key="charging_reason",
        data_key="charging_reason",
        icon="mdi:help-rhombus-outline",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="charging_error_code",
        translation_key="charging_error_code",
        data_key="charging_error_code",
        icon="mdi:alert-circle-outline",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="remaining_time_target_soc",
        translation_key="remaining_time_target_soc",
        data_key="remaining_time_target_soc",
        icon="mdi:battery-clock",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Charge-port LED colour/pattern — disabled-by-default (niche diagnostic).
    VagSensorDescription(
        key="charge_led_color",
        translation_key="charge_led_color",
        data_key="charge_led_color",
        icon="mdi:led-on",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charge_led_pattern",
        translation_key="charge_led_pattern",
        data_key="charge_led_pattern",
        icon="mdi:led-variant-on",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="last_report_id",
        translation_key="last_report_id",
        data_key="last_report_id",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="climate_energy_consumption_kwh",
        translation_key="climate_energy_consumption_kwh",
        data_key="climate_energy_consumption_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:air-conditioner",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="residual_energy_consumption_kwh",
        translation_key="residual_energy_consumption_kwh",
        data_key="residual_energy_consumption_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:car-electric",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="battery_climatization_energy_kwh",
        translation_key="battery_climatization_energy_kwh",
        data_key="battery_climatization_energy_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-heart-variant",
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="last_trip_avg_recuperation_kwh_100km",
        translation_key="last_trip_avg_recuperation_kwh_100km",
        data_key="last_trip_avg_recuperation_kwh_100km",
        native_unit_of_measurement="kWh/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-plus-variant",
        suggested_display_precision=1,
        condition="electric",
    ),
    VagSensorDescription(
        key="lifetime_avg_recuperation_kwh_100km",
        translation_key="lifetime_avg_recuperation_kwh_100km",
        data_key="lifetime_avg_recuperation_kwh_100km",
        native_unit_of_measurement="kWh/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-plus-variant",
        suggested_display_precision=1,
        condition="electric",
    ),
    # LOW confidence — disabled-by-default, Scout/diagnostic only.
    VagSensorDescription(
        key="dataset_key",
        translation_key="dataset_key",
        data_key="dataset_key",
        icon="mdi:key",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # ── v2.15.3 — EU Data Act portal new fields (#465/#514/#515/#516) ────────
    # A. Charging settings.
    VagSensorDescription(
        key="charge_mode_selection",
        translation_key="charge_mode_selection",
        data_key="charge_mode_selection",
        icon="mdi:ev-station",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="max_charge_current_ac",
        translation_key="max_charge_current_ac",
        data_key="max_charge_current_ac",
        icon="mdi:current-ac",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="auto_unlock_charge_port",
        translation_key="auto_unlock_charge_port",
        data_key="auto_unlock_charge_port",
        icon="mdi:lock-open-variant-outline",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="charge_bulk_threshold_pct",
        translation_key="charge_bulk_threshold_pct",
        data_key="charge_bulk_threshold_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-70",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # LOW — companion unit for the charge rate. Disabled-by-default.
    VagSensorDescription(
        key="charge_rate_unit",
        translation_key="charge_rate_unit",
        data_key="charge_rate_unit",
        icon="mdi:speedometer",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # C. Trip odometer endpoints.
    VagSensorDescription(
        key="lifetime_trip_distance_km",
        translation_key="lifetime_trip_distance_km",
        data_key="lifetime_trip_distance_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:map-marker-distance",
        suggested_display_precision=0,
    ),
    # LOW — odometer at window start. Disabled-by-default.
    VagSensorDescription(
        key="lifetime_trip_start_odometer_km",
        translation_key="lifetime_trip_start_odometer_km",
        data_key="lifetime_trip_start_odometer_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="last_trip_start_odometer_km",
        translation_key="last_trip_start_odometer_km",
        data_key="last_trip_start_odometer_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
    ),
    # D. Fuel / fluids.
    VagSensorDescription(
        key="oil_level_liters",
        translation_key="oil_level_liters",
        data_key="oil_level_liters",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil",
        condition="combustion",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    # LOW — failure-overwrite oil level. Disabled-by-default.
    VagSensorDescription(
        key="oil_level_additional_pct",
        translation_key="oil_level_additional_pct",
        data_key="oil_level_additional_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil",
        condition="combustion",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
    ),
    # E. Tyre pressure DELTA vs target — LOW, unit-ambiguous, disabled-by-default.
    VagSensorDescription(
        key="tyre_pressure_diff_fl",
        translation_key="tyre_pressure_diff_fl",
        data_key="tyre_pressure_diff_fl",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_diff_fr",
        translation_key="tyre_pressure_diff_fr",
        data_key="tyre_pressure_diff_fr",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_diff_rl",
        translation_key="tyre_pressure_diff_rl",
        data_key="tyre_pressure_diff_rl",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_diff_rr",
        translation_key="tyre_pressure_diff_rr",
        data_key="tyre_pressure_diff_rr",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_diff_spare",
        translation_key="tyre_pressure_diff_spare",
        data_key="tyre_pressure_diff_spare",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # E'. Tyre ACTUAL per-wheel pressure (#528) — dict unit ambiguous
    # ("10kPA / Bar / PSI/ kPA") → unitless diagnostic. LOW — disabled-by-default.
    VagSensorDescription(
        key="tyre_pressure_actual_fl",
        translation_key="tyre_pressure_actual_fl",
        data_key="tyre_pressure_actual_fl",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_actual_fr",
        translation_key="tyre_pressure_actual_fr",
        data_key="tyre_pressure_actual_fr",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # E'' (#538) — rear + spare ACTUAL, and the REQUIRED/target family. Same
    # ambiguous unit → unitless diagnostic, disabled-by-default.
    VagSensorDescription(
        key="tyre_pressure_actual_rl",
        translation_key="tyre_pressure_actual_rl",
        data_key="tyre_pressure_actual_rl",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_actual_rr",
        translation_key="tyre_pressure_actual_rr",
        data_key="tyre_pressure_actual_rr",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_actual_spare",
        translation_key="tyre_pressure_actual_spare",
        data_key="tyre_pressure_actual_spare",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_required_fl",
        translation_key="tyre_pressure_required_fl",
        data_key="tyre_pressure_required_fl",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_required_fr",
        translation_key="tyre_pressure_required_fr",
        data_key="tyre_pressure_required_fr",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_required_rl",
        translation_key="tyre_pressure_required_rl",
        data_key="tyre_pressure_required_rl",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_required_rr",
        translation_key="tyre_pressure_required_rr",
        data_key="tyre_pressure_required_rr",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tyre_pressure_required_spare",
        translation_key="tyre_pressure_required_spare",
        data_key="tyre_pressure_required_spare",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # F. Lights / energy / misc.
    VagSensorDescription(
        key="parking_lights_state",
        translation_key="parking_lights_state",
        data_key="parking_lights_state",
        icon="mdi:car-parking-lights",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagSensorDescription(
        key="aux_battery_energy_pct",
        translation_key="aux_battery_energy_pct",
        data_key="aux_battery_energy_pct",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # 12V battery BEM level-2 pre-warning alert time (#897). EU-Data-Act dialect
    # only; observed value is an absolute ISO timestamp. LOW value, disabled-by-
    # default.
    VagSensorDescription(
        key="aux_battery_bem_alert_at",
        translation_key="aux_battery_bem_alert_at",
        data_key="aux_battery_bem_alert_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # LOW — raw warning bitmask, no verified decode. Disabled-by-default.
    VagSensorDescription(
        key="dashboard_warnings_raw",
        translation_key="dashboard_warnings_raw",
        data_key="dashboard_warnings_raw",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # #901 (Mezzo1973, volkswagen) — best-effort LOW-confidence EU-Data-Act
    # driving-telemetry. All disabled-by-default. Speed carries km/h (grounded
    # in the parser dictionary) + SPEED device class (HA auto-converts to mph);
    # the other two stay unit-less / class-less (enum/unit unconfirmed).
    VagSensorDescription(
        key="current_speed_kmh",
        translation_key="current_speed_kmh",
        data_key="current_speed_kmh",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="ignition_state",
        translation_key="ignition_state",
        data_key="ignition_state",
        icon="mdi:key-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="brake_pressure_indication",
        translation_key="brake_pressure_indication",
        data_key="brake_pressure_indication",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-brake-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="climate_error_code",
        translation_key="climate_error_code",
        data_key="climate_error_code",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="window_heating_error_code",
        translation_key="window_heating_error_code",
        data_key="window_heating_error_code",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # G. v2.15.3 (#517) — consumption / range aggregates (EU-Data-Act dialect).
    VagSensorDescription(
        key="last_trip_avg_aux_consumption_kwh_100km",
        translation_key="last_trip_avg_aux_consumption_kwh_100km",
        data_key="last_trip_avg_aux_consumption_kwh_100km",
        native_unit_of_measurement="kWh/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="lifetime_avg_aux_consumption_kwh_100km",
        translation_key="lifetime_avg_aux_consumption_kwh_100km",
        data_key="lifetime_avg_aux_consumption_kwh_100km",
        native_unit_of_measurement="kWh/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="lifetime_avg_gas_consumption_kg_100km",
        translation_key="lifetime_avg_gas_consumption_kg_100km",
        data_key="lifetime_avg_gas_consumption_kg_100km",
        native_unit_of_measurement="kg/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
        condition="combustion",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="lifetime_range_gain_km",
        translation_key="lifetime_range_gain_km",
        data_key="lifetime_range_gain_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:map-marker-distance",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="lifetime_zero_emission_km",
        translation_key="lifetime_zero_emission_km",
        data_key="lifetime_zero_emission_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:leaf",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    # Short-term (last-trip) counterparts of the gas/range-gain/zero-emission
    # lifetime aggregates above. Same units; per-trip values reset each drive so
    # MEASUREMENT (not TOTAL_INCREASING). Diagnostic, disabled-by-default.
    VagSensorDescription(
        key="last_trip_avg_gas_consumption_kg_100km",
        translation_key="last_trip_avg_gas_consumption_kg_100km",
        data_key="last_trip_avg_gas_consumption_kg_100km",
        native_unit_of_measurement="kg/100 km",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
        condition="combustion",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="last_trip_range_gain_km",
        translation_key="last_trip_range_gain_km",
        data_key="last_trip_range_gain_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="last_trip_zero_emission_km",
        translation_key="last_trip_zero_emission_km",
        data_key="last_trip_zero_emission_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:leaf",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    # LOW — last battery-charger update trigger. Disabled-by-default.
    VagSensorDescription(
        key="charger_update_trigger",
        translation_key="charger_update_trigger",
        data_key="charger_update_trigger",
        icon="mdi:update",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.16.2 (#636) — report-delivery trigger enum (ROA/ICL/USM/…). LOW,
    # disabled-by-default. NOT electric-only (applies to all EU-Data-Act cars).
    VagSensorDescription(
        key="report_trigger",
        translation_key="report_trigger",
        data_key="report_trigger",
        icon="mdi:motion-sensor",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.16.2 (#671 audi Q6 Scout) — climatisationSettings.value.climatisationMode
    # readback (e.g. "comfort"). Diagnostic, disabled-by-default. Data-present
    # gated so cars that don't ship it never get a phantom "unknown" entity.
    VagSensorDescription(
        key="climate_mode",
        translation_key="climate_mode",
        data_key="climate_mode",
        icon="mdi:air-conditioner",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # v2.15.3 (#518) — EU-Data-Act charging-detail string family. All LOW,
    # diagnostic, disabled-by-default. Data-present gated (see
    # _DATA_PRESENT_REQUIRED) so single-port cars never get a plug2 entity and
    # cars on other channels never get a phantom "unknown" entity.
    VagSensorDescription(
        key="active_target_soc",
        translation_key="active_target_soc",
        data_key="active_target_soc",
        icon="mdi:battery-charging-90",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charge_time_display",
        translation_key="charge_time_display",
        data_key="charge_time_display",
        icon="mdi:timer-sand",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug1_flap_lock_state",
        translation_key="charging_plug1_flap_lock_state",
        data_key="charging_plug1_flap_lock_state",
        icon="mdi:lock",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug1_flap_state",
        translation_key="charging_plug1_flap_state",
        data_key="charging_plug1_flap_state",
        icon="mdi:ev-plug-type2",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug1_infrastructure_state",
        translation_key="charging_plug1_infrastructure_state",
        data_key="charging_plug1_infrastructure_state",
        icon="mdi:ev-station",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug1_lock_state",
        translation_key="charging_plug1_lock_state",
        data_key="charging_plug1_lock_state",
        icon="mdi:lock",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug2_connectionstate",
        translation_key="charging_plug2_connectionstate",
        data_key="charging_plug2_connectionstate",
        icon="mdi:power-plug",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug2_flap_lock_state",
        translation_key="charging_plug2_flap_lock_state",
        data_key="charging_plug2_flap_lock_state",
        icon="mdi:lock",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug2_flap_state",
        translation_key="charging_plug2_flap_state",
        data_key="charging_plug2_flap_state",
        icon="mdi:ev-plug-type2",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug2_infrastructure_state",
        translation_key="charging_plug2_infrastructure_state",
        data_key="charging_plug2_infrastructure_state",
        icon="mdi:ev-station",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="charging_plug2_lock_state",
        translation_key="charging_plug2_lock_state",
        data_key="charging_plug2_lock_state",
        icon="mdi:lock",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # v2.15.3 — deferred parsed-but-unsurfaced energy-content fields. Both are
    # parsed from energy_contents.{current,maximal}_energy_content (EU Data Act)
    # and batteryCapacityNetto (BFF) but had no entity until now. Diagnostic.
    VagSensorDescription(
        key="battery_available_kwh",
        translation_key="battery_available_kwh",
        data_key="battery_available_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging-medium",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    VagSensorDescription(
        key="battery_cap_kwh",
        translation_key="battery_cap_kwh",
        data_key="battery_cap_kwh",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-high",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    # Battery State of Health (%). Two sources: Audi device-grant cars carry a REAL
    # SoH from the batteryHealthState BFF read; everyone else can opt in by setting
    # the car's nameplate net capacity (CONF_BATTERY_NOMINAL_KWH), from which we
    # derive current-max / nominal. The measured value always wins over the estimate.
    # Disabled by default so it only appears when one of those sources exists.
    VagSensorDescription(
        key="battery_soh_pct",
        translation_key="battery_soh_pct",
        data_key="battery_soh_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # v2.15.3 — Skoda trip-cost breakdown (parsed in skoda.py, previously
    # unsurfaced). Currency is dynamic (per account) so it lives in
    # extra_state_attributes ("currency"), not a fixed native unit. Diagnostic.
    # device_class is intentionally NOT MONETARY: that class mandates a fixed
    # currency native unit, but the currency is per-account-dynamic. We keep the
    # value unitless and expose the ISO currency code via extra_state_attributes.
    VagSensorDescription(
        key="trip_total_cost",
        translation_key="trip_total_cost",
        data_key="trip_total_cost",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash-multiple",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="trip_fuel_cost",
        translation_key="trip_fuel_cost",
        data_key="trip_fuel_cost",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:gas-station",
        condition="combustion",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="trip_electricity_cost",
        translation_key="trip_electricity_cost",
        data_key="trip_electricity_cost",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:transmission-tower",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="trip_cng_cost",
        translation_key="trip_cng_cost",
        data_key="trip_cng_cost",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:gas-cylinder",
        condition="combustion",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
    ),

    # v2.15.3 — engine oil level percentage gauge (BFF oilLevel + EU Data Act
    # oil_level_actual_level both write oil_level_pct). Combustion-gated.
    VagSensorDescription(
        key="oil_level_pct",
        translation_key="oil_level_pct",
        data_key="oil_level_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:oil-level",
        condition="combustion",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),

    # BFF / selectivestatus dialect sensors.
    # Per-corner tire STATE — diagnostic, disabled-by-default.
    VagSensorDescription(
        key="tire_pressure_fl_state",
        translation_key="tire_pressure_fl_state",
        data_key="tire_pressure_fl_state",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tire_pressure_fr_state",
        translation_key="tire_pressure_fr_state",
        data_key="tire_pressure_fr_state",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tire_pressure_rl_state",
        translation_key="tire_pressure_rl_state",
        data_key="tire_pressure_rl_state",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tire_pressure_rr_state",
        translation_key="tire_pressure_rr_state",
        data_key="tire_pressure_rr_state",
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # Per-corner tire ERROR CODE — diagnostic, disabled-by-default.
    VagSensorDescription(
        key="tire_pressure_fl_errorcode",
        translation_key="tire_pressure_fl_errorcode",
        data_key="tire_pressure_fl_errorcode",
        icon="mdi:alert-rhombus-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tire_pressure_fr_errorcode",
        translation_key="tire_pressure_fr_errorcode",
        data_key="tire_pressure_fr_errorcode",
        icon="mdi:alert-rhombus-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tire_pressure_rl_errorcode",
        translation_key="tire_pressure_rl_errorcode",
        data_key="tire_pressure_rl_errorcode",
        icon="mdi:alert-rhombus-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="tire_pressure_rr_errorcode",
        translation_key="tire_pressure_rr_errorcode",
        data_key="tire_pressure_rr_errorcode",
        icon="mdi:alert-rhombus-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="lpg_range_km",
        translation_key="lpg_range_km",
        data_key="lpg_range_km",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gas-cylinder",
        condition="combustion",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="engine_status",
        translation_key="engine_status",
        data_key="engine_status",
        icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # LOW confidence — unit ambiguous, disabled-by-default.
    VagSensorDescription(
        key="trip_avg_aux_consumption_kwh",
        translation_key="trip_avg_aux_consumption_kwh",
        data_key="trip_avg_aux_consumption_kwh",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    # LOW confidence — disabled-by-default. ENERGY device_class is invalid
    # with state_class=measurement on HA 2026.6+, so device_class is dropped
    # (same pattern as last_charging_session_kwh) while keeping the kWh unit.
    VagSensorDescription(
        key="departure_charge_kwh",
        translation_key="departure_charge_kwh",
        data_key="departure_charge_kwh",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),

    # v2.15.4 — EU Data Act portal new fields (#521/#522 Scout). EU-Data-Act
    # dialect only; brand/firmware-restricted at the parser level so vehicles/
    # channels without the field stay None → no phantom diagnostic entity.
    VagSensorDescription(
        key="next_charge_timer_start_at",
        translation_key="next_charge_timer_start_at",
        data_key="next_charge_timer_start_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="next_charge_timer_finish_at",
        translation_key="next_charge_timer_finish_at",
        data_key="next_charge_timer_finish_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-end",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="next_charge_target_reachability",
        translation_key="next_charge_target_reachability",
        data_key="next_charge_target_reachability",
        icon="mdi:target",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.15.4 (#537 Scout) — which timer slot (1-15) is the next charging timer.
    # Bare slot index, low user value → diagnostic NUMBER, disabled-by-default.
    VagSensorDescription(
        key="next_charge_timer_number",
        translation_key="next_charge_timer_number",
        data_key="next_charge_timer_number",
        icon="mdi:counter",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # Slope consumption — LOW, unit unconfirmed (dict null), disabled-by-default.
    VagSensorDescription(
        key="ascent_slope_consumption",
        translation_key="ascent_slope_consumption",
        data_key="ascent_slope_consumption",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:slope-uphill",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    VagSensorDescription(
        key="descent_slope_consumption",
        translation_key="descent_slope_consumption",
        data_key="descent_slope_consumption",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:slope-downhill",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    # report_type — metadata, not telemetry. LOW — disabled-by-default.
    VagSensorDescription(
        key="report_type",
        translation_key="report_type",
        data_key="report_type",
        icon="mdi:file-document-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # result_app / result_master — delivery/sync result status enums.
    # Metadata, not telemetry. LOW — disabled-by-default.
    VagSensorDescription(
        key="result_app",
        translation_key="result_app",
        data_key="result_app",
        icon="mdi:check-network-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="result_master",
        translation_key="result_master",
        data_key="result_master",
        icon="mdi:check-network-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # v2.15.5 — update_reason: report-trigger reason enum. Metadata, not
    # telemetry. LOW — disabled-by-default.
    VagSensorDescription(
        key="update_reason",
        translation_key="update_reason",
        data_key="update_reason",
        icon="mdi:message-alert-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ── v2.15.4 (#523) — EU Data Act portal new fields ──────────────────────
    # start_stop_action — charging-related action string. LOW —
    # disabled-by-default.
    VagSensorDescription(
        key="start_stop_action",
        translation_key="start_stop_action",
        data_key="start_stop_action",
        icon="mdi:play-pause",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # start_stop_modification — start/stop modification detail string. LOW —
    # disabled-by-default.
    VagSensorDescription(
        key="start_stop_modification",
        translation_key="start_stop_modification",
        data_key="start_stop_modification",
        icon="mdi:play-pause",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ── v2.15.5 (#541) — V2G / bidirectional-charging charge-level limits ────
    # Upper / lower charge-level limit (percent) the car may bidi-charge within.
    # LOW — diagnostic, disabled-by-default. NO 'SoC' token in the NAME.
    VagSensorDescription(
        key="bidi_max_charge_level_pct",
        translation_key="bidi_max_charge_level_pct",
        data_key="bidi_max_charge_level_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging-high",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="bidi_min_charge_level_pct",
        translation_key="bidi_min_charge_level_pct",
        data_key="bidi_min_charge_level_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging-low",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ── v2.26.0 (#981) — the rest of the bidirectional_charging_mode.* V2G usage
    # accounting + its limits. All UNITLESS (dict unit=null) — no device_class,
    # no invented unit. LOW — diagnostic, disabled-by-default.
    *(
        VagSensorDescription(
            key=_k,
            translation_key=_k,
            data_key=_k,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:home-battery-outline",
            condition="electric",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        )
        for _k in (
            "bidi_energy_used",
            "bidi_energy_used_threshold",
            "bidi_cycles",
            "bidi_cycles_threshold",
            "bidi_operating_hours",
            "bidi_operating_hours_threshold",
            "bidi_quota",
            "bidi_quota_threshold",
        )
    ),
    # ── v2.15.5 (#544) — sunroof motor hood 1 POSITION (%; 0=closed). Distinct
    # from the sunroof_open STATE. LOW — diagnostic, disabled-by-default.
    VagSensorDescription(
        key="sunroof_position_pct",
        translation_key="sunroof_position_pct",
        data_key="sunroof_position_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:window-shutter-open",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ── v2.15.11 (#614) — spoiler POSITION (%; 0=closed). Distinct from the
    # spoiler_open STATE. LOW — diagnostic, disabled-by-default.
    VagSensorDescription(
        key="spoiler_position_pct",
        translation_key="spoiler_position_pct",
        data_key="spoiler_position_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:airplane-landing",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # ── Unreleased (Scout #938/#947) — battery charging care mode (BCAM) score
    # and its threshold. dict-confirmed type=number, unit=null → UNITLESS, no
    # device_class. LOW — diagnostic, disabled-by-default.
    VagSensorDescription(
        key="battery_care_score",
        translation_key="battery_care_score",
        data_key="battery_care_score",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagSensorDescription(
        key="battery_care_score_threshold",
        translation_key="battery_care_score_threshold",
        data_key="battery_care_score_threshold",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-outline",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

# Sensor keys that read from coordinator helpers instead of the per-vehicle
# data dict. Kept in a frozenset so ``async_setup_entry`` can dispatch to
# the right entity class without scattering branch logic.
_REPORTER_KEYS: frozenset[str] = frozenset({
    "api_observer_findings",
    "error_reporter_count",
})

# v1.10.0 (#94) — keys that require the field to be non-None at setup
# time before the entity is created. Prevents phantom "unknown" entities
# on vehicles whose API simply doesn't publish a particular range source.
# Adding to this set is a deliberate per-key opt-in: most existing sensors
# legitimately start as None and populate later, so they should NOT be
# gated this way.
_DATA_PRESENT_REQUIRED: frozenset[str] = frozenset({
    # b1/A6 — raw-discovery sensor only spawns when the portal actually
    # delivered unmapped fields (empty dict on every other brand/channel).
    "raw_api_fields",
    # v2.17.1 (Scout #701, VW ID.7) — EU-portal-only interior temp,
    # HV-battery-derived charge-target time + profile user capacity.
    # Non-portal cars leave these None → no phantom entity.
    "cabin_temp",
    "charge_target_time",
    "max_number_users",
    # b1/C1 — provenance sensor only spawns when a multi-channel merge set
    # source_channel (None on single-channel entries).
    "data_source_channel",
    "electric_range_km",
    "combustion_range_km",
    "total_range_km",
    # v1.11.0 (#91) — same phantom-entity-prevention reasoning. Vehicles
    # whose API doesn't expose ``vehicleLights.lightsStatus.value.lights[]``
    # shouldn't get a "0" sensor or default-False binary sensor.
    "lights_count",
    # v1.12.0 (#23) — older vehicles + non-CARIAD backends don't expose
    # ``lvBattery``; don't create a phantom 0 V sensor for them.
    "voltage_12v",
    # v1.15.0 — Skoda-only software-version (mysmob app v8.10.0+).
    # Cross-brand support deferred — CARIAD-BFF + OLA don't expose an
    # equivalent endpoint yet (Research 2026-05-02).
    "software_version",
    # v1.15.0 (#35) — Skoda-only charging history. Cross-brand deferred
    # (CARIAD-BFF/OLA equivalent endpoints unverified).
    "total_charged_energy_kwh",
    "last_charging_session_kwh",
    "last_charging_session_duration_min",
    # v2.10.0 (charging_statistics) - SEAT/CUPRA host-specific. Other
    # brands and SEAT/CUPRA vehicles without subscription leave these
    # at None so no phantom entity appears.
    "last_charging_session_start",
    "last_charging_session_current_type",
    "last_charging_power_curve_points",
    # v1.16.0 (#25, #31) — Skoda-only charging profiles. Same cross-
    # brand deferral. Even on Skoda these stay None for accounts
    # without configured profiles → don't create phantom entities.
    "active_charging_profile_name",
    "active_charging_profile_target_soc_pct",
    "next_charging_time",
    "charging_profiles_count",
    # v1.17.1 (Bruno seq 11) — SEAT/CUPRA battery-care target SoC.
    # Field stays None for non-OLA brands and for accounts where
    # battery-care isn't supported / configured.
    "battery_care_target_soc_pct",
    # v1.20.2 (post-v1.20.0 phantom-entity fix) — Bundle 2 Phase A
    # introduced two Skoda-only sensors but forgot to gate them.
    # Without this set membership, all non-Skoda VINs (Audi/VW EU/
    # CUPRA/SEAT/Porsche/VW NA) showed a phantom "License Plate:
    # unknown" + "Equipment Count: unknown" diagnostic entity since
    # v1.20.0 was released. Field stays None for those brands so the
    # data-present gate keeps the entity from ever being created.
    "license_plate",
    "equipment_count",
    # v1.26.0 Welle-6 Feature Backlog (#173) — phantom protection for
    # the new sensors. Brand-restricted at the parser level (Skoda has
    # secondary_engine_range_km only for PHEV; VW EU/Audi have the
    # next_charging_timer_* + capabilities_count). Other vehicles leave
    # the field None → no phantom entity created.
    "secondary_engine_range_km",
    # v2.2.0 (scout #220) — Skoda PHEV-only secondaryEngineRange
    # companion fields (engineType / fuel-level %). Stay None on
    # ICE-only and EV-only vehicles → no phantom entity.
    "secondary_engine_type",
    "secondary_engine_fuel_level_pct",
    # v2.2.0 Phase 2 PR #8/20 + PR #10/20 — subscription expiry timestamp.
    # SEAT/CUPRA parses from ``mycar.services.*.expirationDate``; VW EU
    # + Audi (PR #10) parse from CARIAD-BFF ``userCapabilities.
    # capabilitiesStatus.value[*].expirationDate``. Skoda + Porsche +
    # VW NA leave field None → no phantom entity.
    "subscription_expiry_at",
    # v2.2.0 Phase 2 PR #11/20 — derived days-remaining int sensor.
    # Computed from the same expiry-aggregation as PR #8/#10, so same
    # brand-coverage matrix (None on Skoda/Porsche/VW NA).
    "subscription_days_remaining",
    # v2.2.0 Phase 7 PR #1 — scout-audit quick-wins. Each is brand-
    # restricted at the parser level; other brands stay None.
    "primary_engine_soc_pct",       # Skoda-only (driving-range)
    "steering_wheel_position",      # Skoda-only (air-conditioning)
    "preferred_charge_mode",        # Skoda-only (charging settings) — v2.31.0
    # v2.31.0 — Škoda pay-at-pump last fill-up; only present for enrolled users.
    "last_refuel_quantity",
    "last_refuel_cost",
    "last_refuel_currency",
    "last_refuel_fuel_type",
    "last_refuel_station",
    "last_refuel_at",
    # v2.31.0 — Škoda pay-to-park; only present for enrolled users.
    "parking_location",
    "parking_cost",
    "parking_currency",
    "parking_started_at",
    "parking_ended_at",
    # v2.31.0 — Škoda service reminders + departure-timer times (Skoda-only).
    "reminder_technical_inspection",
    "reminder_seasonal_tyre_change",
    "reminder_first_aid_kit",
    "reminder_tyre_repair_kit",
    "departure_timer_1_time",
    "departure_timer_2_time",
    "departure_timer_3_time",
    "battery_temp_max",             # VW EU + Audi only (CARIAD-BFF)
    # v2.2.0 Phase 7 PR #2 — VW EU + Audi only (CARIAD-BFF
    # departureTimers block). Other brands' parsers don't populate
    # this aggregate → field stays None → no phantom entity.
    "departure_timer_enabled_count",
    # v2.2.0 Phase 7 PR #3 — SEAT/CUPRA only (OLA mycar.engines.primary).
    # Other brands don't ship this block → fields stay None → no phantom.
    "primary_engine_type",
    "fuel_tank_capacity_liters",
    # v2.2.0 Phase 7 PR #4 — Skoda-only AC tier-B aggregates.
    # Other brands' AC blocks don't ship timers/runningRequests →
    # fields stay None → no phantom entity.
    "climate_timer_enabled_count",
    "climate_running_requests_count",
    # v2.2.1 Phase 8 PR #1 — Skoda-only "alles parsen" batch.
    "car_type",
    "primary_engine_fuel_level_pct",
    "maintenance_report_captured_at",
    # v2.8.0 quick win C — brake-service + preferred-workshop singletons.
    # Brand-restricted at the parser level (VW EU, Audi via subclass,
    # Skoda mysmob and SEAT/CUPRA OLA when the dealer wired up the
    # service plan). Stay None for brands or vehicles where the upstream
    # endpoint never ships the keys → no phantom "Unbekannt" entity.
    "brake_fluid_change_due_at",
    "brake_pads_front_inspection_due_at",
    "brake_pads_rear_inspection_due_at",
    "preferred_workshop_name",
    "preferred_workshop_address",
    "preferred_workshop_phone",
    # v2.8.1 #306 — 5 P1 numeric/string OLA-field gap sensors.
    # Brand-restricted at parser level (SEAT/CUPRA OLA primarily; some
    # also populated for VW EU/Audi/Skoda where the equivalent shape
    # exists on the brand backend). Vehicles without the underlying
    # field leave the entry None so no phantom "Unbekannt" entity
    # surfaces.
    "adblue_level_pct",
    "cng_level_pct",
    "cng_range_km",
    "primary_engine_range_km",
    "charging_preferred_mode",
    # v2.10.0 (#389) — pending-action surface, only populated when the
    # CARIAD BFF reports an in-flight request. Most polls these will
    # be None and the sensors stay hidden.
    "pending_action_id",
    "pending_action_type",
    "pending_action_status",
    # v2.10.0 — refuel-trip aggregator. Cars without ?type=cyclic
    # capability or that have never had a refuel/charge tracked yet
    # leave the fields None.
    "refuel_trip_distance_km",
    "refuel_trip_duration_min",
    "refuel_trip_avg_speed_kmh",
    "refuel_trip_avg_fuel_consumption_l_100km",
    "refuel_trip_avg_electric_consumption_kwh_100km",
    "refuel_trip_total_fuel_consumption_l",
    "refuel_trip_total_electric_consumption_kwh",
    "refuel_trip_recuperation_kwh",
    "refuel_trip_timestamp",
    # v2.10.0 - battery-care target (OLA /charging/battery-care GET).
    "battery_care_target_soc_pct",
    # v2.10.0 - structured warning lights from /v3/warninglights. Phantom-
    # protected because non-CUPRA brands won't poll the v3 endpoint and
    # leave warning_count/warning_messages at None.
    "warning_count",
    "warning_messages",
    # v2.16.0 — volkswagen.de authproxy live-status read-path (BETA, opt-in).
    # Only the website-authproxy channel populates these; every other brand/
    # entry leaves them None so no phantom entity surfaces. (license_plate +
    # vehicle_nickname are already covered by this set above.)
    "active_warning_lights_count",
    "last_lock_action",
    "last_lock_action_at",
    # v2.10.0 - real-time charge rate, Audi-only firmware exposes it.
    "actual_charge_rate_kw",
    "next_charging_timer_id",
    "next_charging_timer_target_soc_reachable",
    "capabilities_count",
    # v2.0.0 (Big-Bang) — Skoda-only driving-score (mysmob, MY24+).
    # Other brands leave both fields None; gate prevents phantom entities.
    "driving_score",
    "driving_score_class",
    # v2.0.0 (Big-Bang) — Porsche-only TPMS (PPA TIRE_PRESSURE measurement).
    # Non-Porsche vehicles leave the fields None → no phantom entity.
    "tire_pressure_front_left_bar",
    "tire_pressure_front_right_bar",
    "tire_pressure_rear_left_bar",
    "tire_pressure_rear_right_bar",
    # v2.0.0 (Big-Bang) — Vehicle alarm timestamp (issue #33).
    "last_alarm_at",
    # v2.0.0 (Big-Bang) — heaterSource (issue #163, ID.x heat-pump only).
    "heater_source",
    # v2.16.2 (#671) — climatisationMode readback (data-present gated so
    # cars that don't ship the field never get a phantom "unknown" entity).
    "climate_mode",
    # v2.1.0 — Skoda climate-ready-at (Scout #186/#188). Field is
    # only populated during active climate run; gating prevents a
    # phantom "unknown" entity for non-Skoda + idle climates.
    "climate_ready_at",
    # v2.8.0 - aux heating (Standheizung) status + remaining minutes.
    # Audi + VW EU only via the CARIAD-BFF auxiliaryHeating job;
    # other brands leave the fields None so no phantom diagnostic
    # entity appears for SEAT/CUPRA/Skoda/Porsche/VW NA.
    "auxiliary_heating_status",
    "auxiliary_heating_remaining_min",
    # v2.10.0 Group A — VW EU field parity additions. All brand-
    # restricted at the parser level (CARIAD-BFF VW EU + Audi via
    # subclass). Vehicles without the underlying field stay None
    # so no phantom diagnostic entity appears.
    "hv_battery_min_temperature_c",
    "hv_battery_max_temperature_c",
    "charge_max_ac_setting",
    "charge_max_ac_ampere",
    "auto_release_ac_connector_state",
    "active_ventilation_state",
    "active_ventilation_remaining_time_min",
    "battery_support_state",  # v2.21.0 — MEB-only; no phantom on other cars
    "evcc_charge_status",  # v2.22.0 — only set for EVs with charging data
    "connection_state_battery_power_level",
    "last_trip_total_fuel_consumption_l",
    "last_trip_total_electric_consumption_kwh",
    # v2.10.0 Group B - SEAT/CUPRA OLA endpoint parity. Brand-restricted
    # at parser level (OLA-only); other brands leave the fields None
    # so no phantom diagnostic entity surfaces.
    "notifications_count",
    "last_notification_subject",
    "last_notification_severity",
    "engine_oil_temperature_c",
    "engine_coolant_temperature_c",
    # v2.15.1 — EU Data Act + BFF wire-key mapping (2.15.0 plan). Every new
    # sensor is brand/firmware-restricted at the parser level (EU Data Act
    # portal and/or CARIAD-BFF selectivestatus). Vehicles/channels without the
    # underlying field stay None so no phantom diagnostic entity surfaces.
    "charging_scenario",
    "immediate_charge_action_state",
    "profile_charge_reason",
    "charge_session_energy_kwh",
    "remaining_charge_time_bulk_min",
    "odometer_state",
    "instrument_cluster_time",
    "hv_battery_state",
    "data_error_detail",
    # v2.15.2 — EU Data Act portal "charger detail" fields (#513 Scout).
    "external_power_supply_state",
    "charging_reason",
    "charging_error_code",
    "remaining_time_target_soc",
    "charge_led_color",
    "charge_led_pattern",
    "last_report_id",
    "climate_energy_consumption_kwh",
    "residual_energy_consumption_kwh",
    # v2.15.7 (#547-#581 Scout) — battery-climatization energy. EU-Data-Act
    # dialect only; vehicles/channels without the field stay None → no phantom.
    "battery_climatization_energy_kwh",
    "last_trip_avg_recuperation_kwh_100km",
    "lifetime_avg_recuperation_kwh_100km",
    "dataset_key",
    "tire_pressure_fl_state",
    "tire_pressure_fr_state",
    "tire_pressure_rl_state",
    "tire_pressure_rr_state",
    "tire_pressure_fl_errorcode",
    "tire_pressure_fr_errorcode",
    "tire_pressure_rl_errorcode",
    "tire_pressure_rr_errorcode",
    "lpg_range_km",
    "engine_status",
    "trip_avg_aux_consumption_kwh",
    "departure_charge_kwh",
    # v2.15.3 — EU Data Act portal new fields (#465/#514/#515/#516). EU-Data-Act
    # dialect only; vehicles/channels without the field stay None → no phantom.
    "charge_mode_selection",
    "max_charge_current_ac",
    "auto_unlock_charge_port",
    "charge_bulk_threshold_pct",
    "charge_rate_unit",
    "lifetime_trip_distance_km",
    "lifetime_trip_start_odometer_km",
    "last_trip_start_odometer_km",
    "oil_level_liters",
    "oil_level_additional_pct",
    "tyre_pressure_diff_fl",
    "tyre_pressure_diff_fr",
    "tyre_pressure_diff_rl",
    "tyre_pressure_diff_rr",
    "tyre_pressure_diff_spare",
    "parking_lights_state",
    "aux_battery_energy_pct",
    "dashboard_warnings_raw",
    "climate_error_code",
    "window_heating_error_code",
    # #901 — best-effort EU-Data-Act driving telemetry. VW-only / firmware-
    # restricted at the parser; vehicles/channels without the field stay None
    # → no phantom diagnostic entity.
    "current_speed_kmh",
    "ignition_state",
    "brake_pressure_indication",
    # v2.15.3 (#517) — consumption / range aggregates (EU-Data-Act dialect) +
    # deferred energy-content + Skoda trip-cost + oil-level-pct. All
    # brand/firmware-restricted at the parser level → None on cars/channels
    # without the field, so no phantom diagnostic entity surfaces.
    "last_trip_avg_aux_consumption_kwh_100km",
    "lifetime_avg_aux_consumption_kwh_100km",
    "lifetime_avg_gas_consumption_kg_100km",
    "last_trip_avg_gas_consumption_kg_100km",
    "lifetime_range_gain_km",
    "last_trip_range_gain_km",
    "lifetime_zero_emission_km",
    "last_trip_zero_emission_km",
    "charger_update_trigger",
    # v2.16.2 (#636) — report-delivery trigger. EU-Data-Act dialect only;
    # non-EU-Data-Act channels never ship trigger_type → stays None → no phantom.
    "report_trigger",
    # v2.15.3 (#518) — EU-Data-Act charging-detail string family. Junk
    # sentinels dropped to None at the parser → single-port cars never get a
    # plug2 entity; non-EU-Data-Act channels never ship the keys → no phantom.
    "active_target_soc",
    "charge_time_display",
    "charging_plug1_flap_lock_state",
    "charging_plug1_flap_state",
    "charging_plug1_infrastructure_state",
    "charging_plug1_lock_state",
    "charging_plug2_connectionstate",
    "charging_plug2_flap_lock_state",
    "charging_plug2_flap_state",
    "charging_plug2_infrastructure_state",
    "charging_plug2_lock_state",
    "battery_available_kwh",
    "battery_cap_kwh",
    "trip_total_cost",
    "trip_fuel_cost",
    "trip_electricity_cost",
    "trip_cng_cost",
    "oil_level_pct",
    # v2.15.4 — EU Data Act portal new fields (#521/#522). EU-Data-Act dialect
    # only; vehicles/channels without the field stay None → no phantom.
    "next_charge_timer_start_at",
    "next_charge_timer_finish_at",
    "next_charge_target_reachability",
    # v2.15.4 (#537) — next-charging-timer slot index. EU-Data-Act dialect only;
    # vehicles/channels without the field stay None → no phantom.
    "next_charge_timer_number",
    # #897 — 12V battery BEM level-2 pre-warning alert time. EU-Data-Act dialect
    # only; vehicles/channels without the field stay None → no phantom.
    "aux_battery_bem_alert_at",
    "ascent_slope_consumption",
    "descent_slope_consumption",
    "report_type",
    "result_app",
    "result_master",
    # v2.15.5 — report-trigger reason. EU-Data-Act dialect only; vehicles/
    # channels without the field stay None → no phantom.
    "update_reason",
    # v2.15.4 (#523) — EU Data Act portal new field. EU-Data-Act dialect only;
    # vehicles/channels without the field stay None → no phantom.
    "start_stop_action",
    # v2.15.4 (#528) — EU Data Act portal new fields. EU-Data-Act dialect only;
    # vehicles/channels without the field stay None → no phantom.
    "start_stop_modification",
    "tyre_pressure_actual_fl",
    "tyre_pressure_actual_fr",
    # v2.15.4 (#538) — rear + spare ACTUAL and the REQUIRED/target family.
    # EU-Data-Act dialect only; vehicles/channels without the field stay None.
    "tyre_pressure_actual_rl",
    "tyre_pressure_actual_rr",
    "tyre_pressure_actual_spare",
    "tyre_pressure_required_fl",
    "tyre_pressure_required_fr",
    "tyre_pressure_required_rl",
    "tyre_pressure_required_rr",
    "tyre_pressure_required_spare",
    # v2.15.5 (#541) — V2G / bidirectional-charging charge-level limits.
    # EU-Data-Act dialect only; vehicles/channels without the field stay None.
    "bidi_max_charge_level_pct",
    "bidi_min_charge_level_pct",
    # v2.15.5 (#544) — sunroof motor hood 1 position. EU-Data-Act dialect only;
    # vehicles/channels without the field stay None → no phantom.
    "sunroof_position_pct",
    # v2.15.11 (#614) — spoiler position. EU-Data-Act dialect only; vehicles/
    # channels without the field stay None → no phantom.
    "spoiler_position_pct",
    # Unreleased (Scout #938/#947) — battery charging care mode score + its
    # threshold. EU-Data-Act dialect only; vehicles/channels without the field
    # stay None → no phantom.
    "battery_care_score",
    "battery_care_score_threshold",
    # v4.4.0 (vgql coverage, 2026-08-28) — drivetrain classification + the
    # stable customer-service id come from the Audi/VW-EU vgql only. Every
    # other brand/channel leaves them None → no phantom entity. "parked_since"
    # reads position_captured_at (its data_key), which stays None for cars/
    # channels that never report a parking position → no phantom there either.
    "drive_train",
    "csid",
    "parked_since",
})

# v1.14.0 (#24) — Trip Statistics is brand-restricted. The long-term aggregates
# come from the CARIAD-BFF (Audi + VW EU); Škoda additionally fills the per-trip
# keys from its own mysmob /trip-statistics parse (#1310). Gate at setup so
# SEAT/CUPRA/Porsche/VW NA users — whose clients don't expose trip data — don't
# get "unknown" sensors per VIN. Capability gating (Phase 3, #56) further hides
# them when the subscription is absent.
_TRIP_STATS_KEYS: frozenset[str] = frozenset({
    "last_trip_distance_km",
    "last_trip_avg_speed_kmh",
    "last_trip_avg_fuel_consumption_l_100km",
    "last_trip_avg_electric_consumption_kwh_100km",
    # v2.0.0 (Big-Bang) — long-term aggregates from /tripstatistics?type=longTerm
    # (CARIAD-BFF only). Same brand gate as the per-trip keys above.
    "lifetime_distance_km",
    "lifetime_avg_fuel_consumption_l_100km",
    "lifetime_avg_electric_consumption_kwh_100km",
})
# audi + volkswagen fill these from the CARIAD-BFF /tripstatistics endpoint.
# #1310 (indigomejor): Škoda fills the per-trip keys (last_trip_*) from its own
# mysmob /trip-statistics parse (skoda.py), so it belongs here too — the
# last_trip_* entities then spawn and populate. The CARIAD-BFF FETCH gate stays
# audi/volkswagen only (coordinator._TRIP_STATS_BRANDS), so no wrong call fires
# for Škoda; the lifetime_* keys stay empty on Škoda and are hidden by the
# default "hide empty entities" option rather than showing as unknown.
_TRIP_STATS_BRANDS: frozenset[str] = frozenset({"audi", "volkswagen", "skoda"})

# Per-window opening position (% open), from the EU-DA window-lifter positions
# (``position_*_door_window_lifter``). Parsed into ``windows_position`` — a slot
# only lands there when the car actually reports a value, so cars without window
# telemetry spawn no entities (self-gating, no "unknown" clutter). Mirrors the
# per-window binary sensor's slot names.
_WINDOW_POSITION_TKEYS = {
    "frontLeft":  "window_position_front_left",
    "frontRight": "window_position_front_right",
    "rearLeft":   "window_position_rear_left",
    "rearRight":  "window_position_rear_right",
}


class VagWindowPositionSensor(VagConnectEntity, SensorEntity):
    """Opening position of a single window, in percent (0 = closed)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:window-open-variant"
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: VagConnectCoordinator,
        vin: str,
        window_id: str,
    ) -> None:
        super().__init__(coordinator, vin, f"window_position_{window_id}")
        self._window_id = window_id
        _tkey = _WINDOW_POSITION_TKEYS.get(window_id)
        if _tkey:
            self._attr_translation_key = _tkey
        else:
            self._attr_name = window_id

    @property
    def native_value(self) -> int | float | None:
        pos = self._vehicle.get("windows_position", {})
        val = pos.get(self._window_id)
        return val if isinstance(val, (int, float)) and not isinstance(val, bool) else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensor-Entities einrichten.

    v1.25.0 PR-C: dynamic listener spawn — vehicles asleep at HA startup
    get their sensors spawned the moment data arrives in a subsequent
    poll, instead of users having to restart HA.
    """
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.14.0 (#24) — read brand once for trip-stats brand-restriction.
    brand = str(entry.data.get("brand", "")).lower()
    trip_stats_supported = brand in _TRIP_STATS_BRANDS
    # b3 — "hide entities without data" (default on): don't flood the device
    # with "unknown" sensors; only spawn data sensors once their value arrives
    # (the per-id spawner re-evaluates each poll, so late data still appears).
    from .const import CONF_HIDE_EMPTY_ENTITIES  # noqa: PLC0415
    hide_empty = bool(entry.options.get(
        CONF_HIDE_EMPTY_ENTITIES,
        entry.data.get(CONF_HIDE_EMPTY_ENTITIES, True),
    ))

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        entities: list = []
        has_battery    = vehicle.get("has_battery", False)
        has_combustion = vehicle.get("has_combustion", False)

        for desc in SENSOR_DESCRIPTIONS:
            if desc.condition == "electric" and not has_battery:
                continue
            if desc.condition == "combustion" and not has_combustion:
                continue
            # v4.0.0 grounding wave — soft capability gate. Only descriptions
            # that opt in via ``desc.capability`` are affected; a sensor is
            # hidden ONLY when the capabilities document is loaded and the cap
            # is explicitly absent (unknown/supported keep it). Existing
            # descriptions leave ``capability`` None → unchanged behaviour.
            if desc.capability is not None and coordinator.read_capability_hidden(
                vin, desc.capability
            ):
                continue
            # v2.23.1 — de-duplicate the range family on single-energy cars. The
            # parser collapses range_km to the total on any non-hybrid, so on a
            # pure-combustion car range_km == combustion_range_km == total_range_km
            # (three identical "Reichweite" sensors). Keep the single range_km
            # headline and hide the redundant two. A real hybrid (battery AND
            # combustion) keeps all three because they genuinely differ, and
            # combustion_range_km is hidden ONLY when it actually equals range_km,
            # so a bi-fuel car reporting a distinct combustion range still keeps it.
            if desc.key == "total_range_km" and not (has_battery and has_combustion):
                continue
            if (
                desc.key == "combustion_range_km"
                and not has_battery
                and vehicle.get("combustion_range_km") == vehicle.get("range_km")
            ):
                continue
            if desc.key in _DATA_PRESENT_REQUIRED:
                _present = vehicle.get(desc.data_key)
                # v2.10.0 (charging_statistics) - some gated fields are list-
                # shaped with a ``default_factory=list`` default that yields
                # ``[]`` on absent data rather than ``None``. Treat both as
                # "not present" so the entity is skipped at spawn time.
                if (
                    _present is None
                    or (isinstance(_present, list) and not _present)
                    or (isinstance(_present, dict) and not _present)
                ):
                    continue
            if desc.key in _TRIP_STATS_KEYS:
                if not trip_stats_supported:
                    continue
                if (
                    coordinator.command_capability_supported(vin, "command_trip_stats")
                    is False
                ):
                    continue
            # b3 — hide empty: skip data sensors with no value yet (reporters,
            # which read coordinator state with data_key="", are exempt). The
            # per-id spawner re-spawns the sensor when its value first arrives.
            if hide_empty and desc.key not in _REPORTER_KEYS and desc.data_key:
                _v = vehicle.get(desc.data_key)
                if _v is None or (isinstance(_v, (list, dict)) and not _v):
                    continue
            if desc.key in _REPORTER_KEYS:
                entities.append(ReporterSensor(coordinator, vin, desc))
            else:
                entities.append(VagConnectSensor(coordinator, vin, desc))

        # Per-window opening position (%), self-gating on populated slots.
        for window_id in vehicle.get("windows_position", {}):
            entities.append(VagWindowPositionSensor(coordinator, vin, window_id))
        return entities

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


# Keys that return 0 instead of None when not charging/driving
# This prevents the sensor showing "unavailable" while connected but idle
_ZERO_WHEN_IDLE: frozenset[str] = frozenset({
    "charging_power_kw",
    "charging_rate_kmh",
    # #1090 — some backends (e.g. Audi e-tron GT) keep reporting the last
    # non-zero rate for minutes after a charge stops; this is the CARIAD-BFF
    # actual charge rate, zeroed on the same "charging definitively stopped" rule.
    "actual_charge_rate_kw",
})


# Charge-session "minutes remaining" ETAs that must not keep a stale reading once
# the charge is over. Same freeze as _ZERO_WHEN_IDLE (backend keeps sending the
# last value, or the field stops arriving and last-known-value persistence holds
# it), but observed on EU-Data-Act portal cars too — a real capture on gr6803's
# VW ID.7 (#632) showed remaining_charge_time_min = 70 while the car sat at
# NOT_READY_FOR_CHARGING (also seen at 5 and 115 min on other portal VWs). Those
# cars never report plug_connected, so unlike _ZERO_WHEN_IDLE this rule can't gate
# on the plug; it keys on is_charging being *explicitly* False (never None /
# unknown, where the car might actually be charging). A charge ETA with no charge
# in progress is 0 by definition.
_ZERO_REMAINING_WHEN_NOT_CHARGING: frozenset[str] = frozenset({
    "remaining_charge_time_min",
    "remaining_charge_time_nav_min",
    "remaining_charge_time_bulk_min",
})


class VagConnectSensor(VagConnectEntity, SensorEntity):
    entity_description: VagSensorDescription

    def __init__(
        self,
        coordinator: VagConnectCoordinator,
        vin: str,
        description: VagSensorDescription,
    ) -> None:
        super().__init__(coordinator, vin, description.key)
        self.entity_description = description
        if description.suggested_display_precision is not None:
            self._attr_suggested_display_precision = description.suggested_display_precision

    def _platform_attributes(self) -> dict[str, Any] | None:
        """v1.14.0 (#24) — Surface ``recent_trips`` (last 5 short-term
        trips) on the ``last_trip_distance_km`` sensor.

        Pattern from audi #113 — list-shaped data goes into attributes
        because HA caps state strings at 255 chars and per-trip metadata
        easily exceeds that. Other sensors return ``None`` so we don't
        accidentally inflate recorder rows.

        v2.2.0 PR #3 — all return values wrapped in ``json_safe`` so
        Phase-2 additions (which may introduce datetime fields, e.g.
        ``fullyChargedAt``) can't accidentally break MQTT statestream /
        recorder. Defensive against future regression.
        """
        from .cariad._util import json_safe_dict  # noqa: PLC0415

        if self.entity_description.key == "last_trip_distance_km":
            recent = self._vehicle.get("recent_trips")
            if isinstance(recent, list) and recent:
                return json_safe_dict({"recent_trips": recent[: 5]})
        # v1.15.0 (#35) — Skoda charging-history recent sessions go on
        # the cumulative total sensor. Same audi #113 pattern: list-
        # shaped data lives in attributes to dodge the 255-char state
        # limit + recorder bloat.
        if self.entity_description.key == "total_charged_energy_kwh":
            recent = self._vehicle.get("recent_charging_sessions")
            ct = self._vehicle.get("last_charging_session_current_type")
            attrs: dict[str, Any] = {}
            if isinstance(recent, list) and recent:
                attrs["recent_sessions"] = recent[:5]
            if isinstance(ct, str) and ct:
                attrs["last_session_current_type"] = ct
            return json_safe_dict(attrs) if attrs else None
        # v1.16.0 (#25, #31) — Full registered profiles list lives in
        # attributes on the active-profile sensor so users can see all
        # configured locations + their per-location target SoCs at a
        # glance without needing 4× sensors per profile.
        if self.entity_description.key == "active_charging_profile_name":
            profiles = self._vehicle.get("charging_profiles")
            if isinstance(profiles, list) and profiles:
                return json_safe_dict({"profiles": profiles})
        # v1.17.7 (#130 Chr1sDub + #133 christianmhz, 2026-05-04) —
        # Skoda preferred-workshop block surfaced on the
        # ``service_due_in_days`` sensor. Same audi #113 pattern:
        # composite metadata lives in attributes (workshop name,
        # contact, address, location, partner-id) so the sensor's
        # native_value (the int day-count) stays clean for templates.
        # Other brands keep returning None until they grow analogous
        # parsing.
        if self.entity_description.key == "service_due_in_days":
            workshop = self._vehicle.get("preferred_workshop")
            if isinstance(workshop, dict) and workshop:
                return json_safe_dict({"preferred_workshop": workshop})
        # v1.20.0 Bundle 2 Phase A — full equipment list as attrs on
        # the equipment_count sensor (analog v1.14.0 #24 recent_trips
        # pattern). Native_value stays the int count for clean
        # templates; full list ([{id, name}, ...]) lives in attrs.
        if self.entity_description.key == "equipment_count":
            equip = self._vehicle.get("equipment")
            if isinstance(equip, list) and equip:
                return json_safe_dict({"equipment": equip})
        # v2.10.0 (charging_statistics) - full power-curve sample list on
        # the per-sample sensor. Same audi #113 pattern as recent_trips
        # and recent_charging_sessions: list-shaped data lives in attrs
        # to dodge the 255-char HA state limit; native_value stays the
        # int sample count.
        if self.entity_description.key == "last_charging_power_curve_points":
            points = self._vehicle.get("last_charging_power_curve_points")
            if isinstance(points, list) and points:
                return json_safe_dict({"points": points})
        # v2.10.0 Group B - surface the SEAT/CUPRA OLA allowed-charge-
        # modes list as an attribute on the existing
        # ``charging_preferred_mode`` sensor instead of growing a new
        # entity. Picks up automatically when the brand client populates
        # ``available_charge_modes`` from the /charging/modes endpoint.
        if self.entity_description.key == "charging_preferred_mode":
            modes = self._vehicle.get("available_charge_modes")
            if isinstance(modes, list) and modes:
                return json_safe_dict({"available_modes": modes})
        # b1/A6 — raw field discovery: the full {field: value} set as attributes
        # on the one raw_api_fields diagnostic sensor (state stays the count).
        if self.entity_description.key == "raw_api_fields":
            raw = self._vehicle.get("raw_unmapped_fields")
            if isinstance(raw, dict) and raw:
                return json_safe_dict({"fields": raw})
        # Move 1 / data-quality — surface the ambiguous-reading signal we already
        # compute (two portal samples with the SAME car_captured_time but
        # different values, recorded by _walk_fields as contested_fields) on the
        # data-provenance diagnostic sensor. Portal rivals (TommiG1) expose a bare
        # ``ambiguous_reading: true``; ours names each field and the values that
        # tied, so a user can see exactly which reading was uncertain this cycle.
        # Only present when a genuine tie occurred, so it never bloats the
        # recorder on a clean poll.
        if self.entity_description.key == "data_source_channel":
            from ._channel_labels import channels_overview  # noqa: PLC0415
            src_attrs: dict[str, Any] = {}
            raw = self._vehicle.get("source_channel")
            _display, labels = channels_overview(
                raw if isinstance(raw, str) else None)
            if labels:
                # friendly per-channel list + the raw token join for support
                src_attrs["channels"] = labels
                src_attrs["raw"] = raw
            contested = self._vehicle.get("contested_fields")
            if isinstance(contested, dict) and contested:
                src_attrs["contested_fields"] = contested
            return json_safe_dict(src_attrs) if src_attrs else None
        # v2.15.3 — Skoda trip-cost sensors carry the (dynamic) ISO currency
        # code as an attribute, since device_class=MONETARY would force a fixed
        # native currency unit we don't know ahead of time.
        if self.entity_description.key in (
            "trip_total_cost", "trip_fuel_cost",
            "trip_electricity_cost", "trip_cng_cost",
        ):
            currency = self._vehicle.get("trip_cost_currency")
            if isinstance(currency, str) and currency:
                return json_safe_dict({"currency": currency})
        # v2.16.0 — surface the lock/unlock command timestamp as an attribute on
        # the last_lock_action sensor (state stays the "lock"/"unlock" string,
        # same pattern as service_due_in_days above). The dedicated
        # last_lock_action_at TIMESTAMP sensor still exists for graphing.
        if self.entity_description.key == "last_lock_action":
            ts = self._vehicle.get("last_lock_action_at")
            if isinstance(ts, str) and ts:
                return json_safe_dict({"last_lock_action_at": ts})
        return None

    @property
    def native_value(self) -> Any:
        val = self._vehicle.get(self.entity_description.data_key)
        # data_source_channel — show the friendly, de-duplicated channel list
        # ("Car-Net + EU Data Act portal") instead of the raw token join
        # ("eu_data_act+mbb"). The raw value stays in the ``raw`` attribute and
        # in ``source_channel`` itself, so nothing that keys on tokens changes.
        if self.entity_description.key == "data_source_channel":
            from ._channel_labels import channels_overview  # noqa: PLC0415
            display, _labels = channels_overview(
                val if isinstance(val, str) else None)
            return display
        # v2.10.0 (charging_statistics) - power-curve sample list. Native
        # value is the COUNT to keep state HA-recorder friendly; the full
        # list lives in extra_state_attributes (see above). Returns None
        # when the list is missing or empty so the entity reports
        # "unknown" rather than "0" before the first poll has data.
        if self.entity_description.key == "last_charging_power_curve_points":
            if isinstance(val, list) and val:
                return len(val)
            return None
        # b1/A6 — raw_api_fields state is the COUNT of unmapped portal fields;
        # the {field: value} map lives in extra_state_attributes.
        if self.entity_description.key == "raw_api_fields":
            return len(val) if isinstance(val, dict) and val else None
        # charging power / rate: the API either omits these when idle (None) OR,
        # on some backends, keeps reporting the last non-zero value for minutes
        # after a charge stops (#1090 — Audi e-tron GT). Force 0 in both cases,
        # but only while the plug is connected (so a detached car reads
        # "unavailable", not a fake 0) and only once charging is DEFINITIVELY
        # over — is_charging explicitly False and not conservation charging,
        # which legitimately draws a small amount of power to hold the SoC.
        if self.entity_description.key in _ZERO_WHEN_IDLE and self._vehicle.get(
            "plug_connected"
        ):
            state = str(self._vehicle.get("charging_state") or "").lower()
            charging_stopped = (
                self._vehicle.get("is_charging") is False
                and "conservation" not in state
            )
            if val is None or charging_stopped:
                return 0

        # EU-Data-Act portal cars never report plug_connected, so the plug-gated
        # block above can't zero a charge power/rate the feed keeps sending after
        # a session ends (#632 gr6803 ID.7: charging_rate_kmh stuck at 29 while
        # idle at READY_FOR_CHARGING). Mirror the remaining-time rule below:
        # override an actual stale reading once charging is explicitly off, but
        # never fabricate a 0 on a car that simply never reported one (val None
        # stays unavailable) or while charging state is unknown (is_charging None).
        if (
            self.entity_description.key in _ZERO_WHEN_IDLE
            and val is not None
            and self._vehicle.get("is_charging") is False
            and "conservation" not in str(
                self._vehicle.get("charging_state") or ""
            ).lower()
        ):
            return 0

        # Charge-session "minutes remaining" ETA that froze on its last value
        # after the charge ended (#632 gr6803: 70 min while NOT_READY_FOR_CHARGING).
        # Only override an actual stale reading (val present) once charging is
        # explicitly False — never when is_charging is None/unknown, where the car
        # may still be charging and the ETA is real.
        if (
            self.entity_description.key in _ZERO_REMAINING_WHEN_NOT_CHARGING
            and val is not None
            and self._vehicle.get("is_charging") is False
        ):
            return 0

        # DATE sensors: API may return int (days until event) or a date string.
        # HA SensorDeviceClass.DATE requires datetime.date — convert if needed.
        if (
            self.entity_description.device_class == SensorDeviceClass.DATE
            and val is not None
        ):
            if isinstance(val, int):
                from datetime import date, timedelta  # noqa: PLC0415
                return date.today() + timedelta(days=val)
            if isinstance(val, str):
                try:
                    from datetime import date as _date  # noqa: PLC0415
                    return _date.fromisoformat(val[:10])
                except ValueError:
                    return None

        # v2.7.0b5 — TIMESTAMP sensors: API ships ISO-8601 strings (e.g.
        # subscription_expiry_at returns "2026-06-16T22:34:00Z"). HA's
        # SensorDeviceClass.TIMESTAMP requires a timezone-aware datetime
        # object — feeding a str raises 'str has no attribute tzinfo'
        # and rejects the entity at add-time. Convert here so brand
        # parsers can stay loose (just hand through whatever the backend
        # gives us). Trailing 'Z' is handled by replacing it with +00:00
        # since datetime.fromisoformat predates RFC 3339 'Z' support on
        # older Python (3.10 and below).
        if (
            self.entity_description.device_class == SensorDeviceClass.TIMESTAMP
            and val is not None
        ):
            if isinstance(val, str):
                from datetime import datetime, timezone  # noqa: PLC0415
                try:
                    parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
                except ValueError:
                    return None
                # Defensive: ensure tz-aware. ISO strings without
                # timezone are assumed UTC (the backend convention).
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed

        # Schema-drift safety net. A backend field that turns from a number
        # into an enum string raises inside Home Assistant's state write, which
        # is outside the coordinator's parse guard, so it cannot be caught
        # there. It has happened for real: CUPRA firmware turned the max charge
        # current into "maximum"/"reduced" and the amp sensor blew up with
        # "could not convert string to float" (#392). That was patched per
        # field, in whichever parser had already been burned; this catches the
        # whole class once, at the boundary. Reports unknown instead of raising.
        # No-op for every field that is already numeric today, and untouched
        # for text sensors (no state class, no numeric device class).
        if (
            val is not None
            and not isinstance(val, (int, float))
            and (
                self.entity_description.state_class is not None
                or self.entity_description.device_class in _NUMERIC_DEVICE_CLASSES
            )
        ):
            from .cariad._util import safe_float  # noqa: PLC0415

            coerced = safe_float(val)
            if coerced is None:
                _LOGGER.warning(
                    "VW Group Connect: %s received the non-numeric value %r, so it "
                    "reports unknown. This usually means the backend changed "
                    "the field's type.",
                    self.entity_description.key, val,
                )
            return coerced

        return val


class ReporterSensor(VagConnectSensor):
    """v1.9.0 — Vehicle Data Scout / Error Reporter sensor.

    Reads from coordinator-level state (``unexpected_findings`` /
    ``error_buffer``) rather than the per-vehicle data dict. Surfaces
    counts so users can see drift / failures at a glance, and points at
    the HA Repair issue (raised by the reporter pipeline) for the 1-click
    GitHub-or-Copy workflow.

    Per-VIN even though Error Reporter is account-wide — keeps the entity
    layout consistent with every other diagnostic sensor and means the
    sensor still appears even when a single vehicle in a multi-VIN setup
    becomes unavailable.
    """

    @property
    def native_value(self) -> Any:
        key = self.entity_description.key
        coord = self.coordinator
        if key == "api_observer_findings":
            # Per-VIN count (not aggregate) so each vehicle's sensor reflects
            # only its own drift. Aggregate goes into the repair issue.
            findings: dict[str, dict[str, Any]] = (
                getattr(coord, "unexpected_findings", {}) or {}
            )
            return len(findings.get(self._vin, {}))
        if key == "error_reporter_count":
            # Account-wide count — auth/rate-limit errors aren't per-VIN
            # and the buffer is shared across all vehicles in the account.
            return coord.reporter_error_count() if hasattr(
                coord, "reporter_error_count"
            ) else 0
        return None

    def _platform_attributes(self) -> dict[str, Any] | None:
        """Surface a tiny preview so the entity card is informative.

        Privacy: every value here has already passed through
        ``mask_value`` / ``_redact`` upstream. Don't add raw fields.
        """
        key = self.entity_description.key
        coord = self.coordinator
        if key == "api_observer_findings":
            findings = (getattr(coord, "unexpected_findings", {}) or {}).get(
                self._vin, {}
            )
            # Up to 5 most recent paths — keeps the attributes panel tidy
            # and avoids hammering the recorder with huge state dicts.
            preview = list(findings.keys())[-5:]
            return {
                "paths": preview,
                "report_url": "https://github.com/its-me-prash/vag-connect-ha/issues/new",
            }
        if key == "error_reporter_count":
            buffer = getattr(coord, "error_buffer", None)
            records = (buffer.records if buffer is not None else [])[-3:]
            return {
                "recent_types": [r.exception_type for r in records],
                "report_url": "https://github.com/its-me-prash/vag-connect-ha/issues/new",
            }
        return None
