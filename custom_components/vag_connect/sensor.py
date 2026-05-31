# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Sensor platform for VAG Connect.

The VagSensorDescription.condition field gates sensor creation:
  "electric"  — EV and PHEV only (has_battery=True)
  "combustion" — combustion and PHEV only (has_combustion=True)
  None        — all vehicles

charging_rate_kmh uses SensorDeviceClass.SPEED so HA auto-converts km/h ↔ mph
based on the user's unit system preference.
"""
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
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner


@dataclass(frozen=True)
class VagSensorDescription(SensorEntityDescription):
    """Sensor description with coordinator data key, condition, and optional default-disabled flag."""

    data_key: str = ""
    condition: str | None = None  # "electric" | "combustion" | None
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
    # Sensor stays "unknown" if backend never sends the header (gated
    # via ``_DATA_PRESENT_REQUIRED`` to avoid phantom 0 on first poll
    # before any header has been observed).
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
    # Two diagnostic sensors enriching DeviceInfo for Skoda vehicles:
    # license_plate (from widget per-tick) + equipment_count (from
    # equipment endpoint, 24h cache). Both data-present-gated so non-
    # Skoda brands don't get phantom entities.
    VagSensorDescription(
        key="license_plate",
        translation_key="license_plate",
        data_key="license_plate",
        icon="mdi:card-text-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
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
        device_class=SensorDeviceClass.ENERGY,
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
    VagSensorDescription(
        key="battery_care_target_soc_pct",
        translation_key="battery_care_target_soc_pct",
        data_key="battery_care_target_soc_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart",
        suggested_display_precision=0,
        condition="electric",
    ),
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
    VagSensorDescription(
        key="primary_engine_fuel_level_pct",
        translation_key="primary_engine_fuel_level_pct",
        data_key="primary_engine_fuel_level_pct",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
        condition="combustion",
        suggested_display_precision=0,
    ),
    VagSensorDescription(
        key="maintenance_report_captured_at",
        translation_key="maintenance_report_captured_at",
        data_key="maintenance_report_captured_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
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
})

# v1.14.0 (#24) — Trip Statistics is brand-restricted at the API level
# (CARIAD-BFF only — Audi + VW EU). Other brands' clients don't expose
# ``get_trip_statistics``. Gate at setup so SEAT/CUPRA/Skoda/Porsche/VW NA
# users don't get four "unknown" sensors per VIN. Capability gating
# (Phase 3, #56) further hides them when the subscription is absent.
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
_TRIP_STATS_BRANDS: frozenset[str] = frozenset({"audi", "volkswagen"})


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

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        entities: list = []
        has_battery    = vehicle.get("has_battery", False)
        has_combustion = vehicle.get("has_combustion", False)

        for desc in SENSOR_DESCRIPTIONS:
            if desc.condition == "electric" and not has_battery:
                continue
            if desc.condition == "combustion" and not has_combustion:
                continue
            if (
                desc.key in _DATA_PRESENT_REQUIRED
                and vehicle.get(desc.data_key) is None
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
            if desc.key in _REPORTER_KEYS:
                entities.append(ReporterSensor(coordinator, vin, desc))
            else:
                entities.append(VagConnectSensor(coordinator, vin, desc))
        return entities

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


# Keys that return 0 instead of None when not charging/driving
# This prevents the sensor showing "unavailable" while connected but idle
_ZERO_WHEN_IDLE: frozenset[str] = frozenset({
    "charging_power_kw",
    "charging_rate_kmh",
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
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
        return None

    @property
    def native_value(self) -> Any:
        val = self._vehicle.get(self.entity_description.data_key)
        # charging_power_kw + charging_rate_kmh: API omits these when not charging.
        # Return 0 so the entity shows "0 kW / 0 km/h" instead of "unavailable".
        if val is None and self.entity_description.key in _ZERO_WHEN_IDLE:
            # Only return 0 if plug is connected (makes sense to show 0 kW)
            if self._vehicle.get("plug_connected"):
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
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
