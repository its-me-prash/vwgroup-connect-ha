# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Binary sensors for VAG Connect — correct data keys from coordinator."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner


@dataclass(frozen=True)
class VagBinarySensorDescription(BinarySensorEntityDescription):
    data_key: str = ""
    condition: str | None = None


BINARY_DESCRIPTIONS: tuple[VagBinarySensorDescription, ...] = (
    VagBinarySensorDescription(
        key="doors_locked",
        translation_key="doors_locked",
        data_key="doors_locked",
        device_class=BinarySensorDeviceClass.LOCK,
        icon="mdi:car-door-lock",
    ),
    VagBinarySensorDescription(
        key="doors_open",
        translation_key="doors_open",
        data_key="doors_open",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
    ),
    VagBinarySensorDescription(
        key="windows_open",
        translation_key="windows_open",
        data_key="windows_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        icon="mdi:car-windshield-outline",
    ),
    # v2.4.1 — Scout Policy Compliance Audit T1 binary entities.
    # All disabled-by-default per the policy doc (opt-in for users
    # who actually need them). Climatisation zone-control, climate-
    # without-external-power flag, readiness deep-diagnostics.
    VagBinarySensorDescription(
        key="climate_without_external_power",
        translation_key="climate_without_external_power",
        data_key="climate_without_external_power",
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagBinarySensorDescription(
        key="climate_zone_front_left",
        translation_key="climate_zone_front_left",
        data_key="climate_zone_front_left",
        icon="mdi:car-seat",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagBinarySensorDescription(
        key="climate_zone_front_right",
        translation_key="climate_zone_front_right",
        data_key="climate_zone_front_right",
        icon="mdi:car-seat",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagBinarySensorDescription(
        key="connection_active",
        translation_key="connection_active",
        data_key="connection_active",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:wifi-check",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagBinarySensorDescription(
        key="daily_power_budget_warning",
        translation_key="daily_power_budget_warning",
        data_key="daily_power_budget_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:battery-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagBinarySensorDescription(
        key="insufficient_battery_level_warning",
        translation_key="insufficient_battery_level_warning",
        data_key="insufficient_battery_level_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    VagBinarySensorDescription(
        key="plug_connected",
        translation_key="plug_connected",
        data_key="plug_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:power-plug",
        condition="electric",
    ),
    VagBinarySensorDescription(
        key="is_charging",
        translation_key="is_charging",
        data_key="is_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:battery-charging",
        condition="electric",
    ),
    # v1.27.2 — External power availability from plugStatus.externalPower.
    # True when the wallbox/EVSE is actively delivering power to the
    # connector. False = plug connected but power source unavailable
    # (RCD trip / phase loss / smart-charging pause). Diagnostic-only.
    VagBinarySensorDescription(
        key="external_power_available",
        translation_key="external_power_available",
        data_key="external_power_available",
        device_class=BinarySensorDeviceClass.POWER,
        icon="mdi:transmission-tower-export",
        condition="electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="climatisation_active",
        translation_key="climatisation_active",
        data_key="climatisation_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:thermometer",
    ),
    VagBinarySensorDescription(
        key="warning_active",
        translation_key="warning_active",
        data_key="warning_active",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="warning_engine",
        translation_key="warning_engine",
        data_key="warning_engine",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:engine",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="warning_oil",
        translation_key="warning_oil",
        data_key="warning_oil",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:oil",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="warning_tyre",
        translation_key="warning_tyre",
        data_key="warning_tyre",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:tire",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="warning_brakes",
        translation_key="warning_brakes",
        data_key="warning_brakes",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:car-brake-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.7.0b10 — oilLevel job, parity with upstream.
    # State is inverted vs. the warning_* family above: oil_level_ok
    # True means everything's fine, False means oil needs attention.
    # Use device_class PROBLEM with the value flipped so HA renders it
    # consistently (red = problem) without a separate template.
    VagBinarySensorDescription(
        key="oil_level_warning",
        translation_key="oil_level_warning",
        data_key="oil_level_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:oil-level",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

_NEW_BINARY: tuple[VagBinarySensorDescription, ...] = (
    VagBinarySensorDescription(
        key="is_driving",
        translation_key="is_driving",
        data_key="is_driving",
        device_class=BinarySensorDeviceClass.MOTION,
        icon="mdi:car-speed-limiter",
    ),
    VagBinarySensorDescription(
        key="is_online",
        translation_key="is_online",
        data_key="is_online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:car-wireless",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="connector_locked",
        translation_key="connector_locked",
        data_key="connector_locked",
        device_class=BinarySensorDeviceClass.LOCK,
        icon="mdi:ev-plug-ccs2",
        entity_category=EntityCategory.DIAGNOSTIC,
        condition="electric",
    ),
    VagBinarySensorDescription(
        key="window_heating_front",
        translation_key="window_heating_front",
        data_key="window_heating_front",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:car-windshield",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="window_heating_back",
        translation_key="window_heating_back",
        data_key="window_heating_back",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:car-windshield",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.8.1 #306 — 6 P1 boolean OLA-field gaps surfaced via pycupra
    # side-by-side. All brand-restricted at parser level (mostly OLA
    # SEAT/CUPRA today); brands without the underlying field leave
    # the entry None so the _DATA_PRESENT_REQUIRED gate hides it.
    VagBinarySensorDescription(
        key="seat_heating",
        translation_key="seat_heating",
        data_key="seat_heating",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:car-seat-heater",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="parking_light",
        translation_key="parking_light",
        data_key="parking_light",
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:car-parking-lights",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="external_power",
        translation_key="external_power",
        data_key="external_power",
        device_class=BinarySensorDeviceClass.POWER,
        icon="mdi:power-plug",
    ),
    VagBinarySensorDescription(
        key="battery_care",
        translation_key="battery_care",
        data_key="battery_care",
        icon="mdi:battery-heart-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="energy_flow",
        translation_key="energy_flow",
        data_key="energy_flow",
        device_class=BinarySensorDeviceClass.POWER,
        icon="mdi:flash",
    ),
    VagBinarySensorDescription(
        key="area_alarm",
        translation_key="area_alarm",
        data_key="area_alarm",
        device_class=BinarySensorDeviceClass.SAFETY,
        icon="mdi:map-marker-alert",
    ),
    # v1.11.0 (#91 closure) — vehicle lights aggregate "any light on?".
    VagBinarySensorDescription(
        key="lights_on",
        translation_key="lights_on",
        data_key="lights_on",
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:lightbulb-on-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v1.12.0 (#23) — 12V starter battery low-voltage warning. Threshold
    # 11.5 V applied in vw_eu parser. Surface as PROBLEM device class
    # so HA's binary_sensor card shows a red alert when triggered.
    VagBinarySensorDescription(
        key="warning_12v_low",
        translation_key="warning_12v_low",
        data_key="warning_12v_low",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:car-battery",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v1.15.0 — Skoda OTA update available (mysmob, app v8.10.0+,
    # endpoint ``/v1/vehicle-information/{vin}/software-version/update-status``).
    # ``releaseNotesUrl`` exposed via ``extra_state_attributes`` so users
    # can click through to read what changed.
    VagBinarySensorDescription(
        key="ota_update_available",
        translation_key="ota_update_available",
        data_key="ota_update_available",
        device_class=BinarySensorDeviceClass.UPDATE,
        icon="mdi:cellphone-arrow-down",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v1.17.1 (Bruno seq 10) — SEAT/CUPRA Battery Care mode active.
    # Battery care = OEM mode that limits charging to preserve
    # battery longevity (typically caps at the target_soc_pct from
    # /charging/battery-care/target). Read-only via two thin OLA GETs.
    VagBinarySensorDescription(
        key="battery_care_enabled",
        translation_key="battery_care_enabled",
        data_key="battery_care_enabled",
        icon="mdi:battery-heart-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v1.26.0 Welle-6 Feature Backlog (#173) — new binary sensors.
    VagBinarySensorDescription(
        key="auto_unlock_when_charged",
        translation_key="auto_unlock_when_charged",
        data_key="auto_unlock_when_charged",
        icon="mdi:lock-open-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="climate_at_unlock",
        translation_key="climate_at_unlock",
        data_key="climate_at_unlock",
        icon="mdi:car-electric",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="window_heating_enabled",
        translation_key="window_heating_enabled",
        data_key="window_heating_enabled",
        icon="mdi:car-defrost-front",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 (Skoda Scout #220 — Daniel Walter 2026-05-16) — Skoda mysmob
    # `airConditioningWithoutExternalPower` on the air-conditioning endpoint.
    # Tells you whether climatisation can run from the HV battery alone
    # (without being plugged in). Skoda-only today; gated below for phantom
    # protection so other brands don't see a meaningless OFF entity.
    VagBinarySensorDescription(
        key="air_conditioning_without_external_power",
        translation_key="air_conditioning_without_external_power",
        data_key="air_conditioning_without_external_power",
        icon="mdi:battery-charging",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.5.9 (#315/#316/#321/#327/#328/#329/#330/#333 — EIGHT Skoda
    # Scout-Reports converging 2026-05-28/29). Skoda's new Enyaq/iV
    # "Camping Mode" — climatisation runs continuously when parked.
    # Skoda-only today; phantom-protected below. When CUPRA/SEAT
    # firmware ships an equivalent (which the OLA backend is likely to
    # mirror given shared codebase), they'll auto-light up.
    VagBinarySensorDescription(
        key="camping_mode",
        translation_key="camping_mode",
        data_key="camping_mode",
        icon="mdi:tent",
    ),
    # v2.2.0 Phase 2 PR #9/20 — Companion to subscription_expiry_at
    # (PR #8/20). Simple True/False "is your Connect subscription
    # currently valid?" — perfect for HA automations like
    # ``if binary_sensor.subscription_active == off → notify``.
    # SEAT/CUPRA-only today; tri-state semantics (None preserved for
    # perpetual entitlements) prevent false-alarms.
    VagBinarySensorDescription(
        key="subscription_active",
        translation_key="subscription_active",
        data_key="subscription_active",
        icon="mdi:check-decagram",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 Phase 7 PR #1 — Skoda-only ignition state (`readiness.
    # ignitionOn`). Useful for "lock when ignition off" automations.
    VagBinarySensorDescription(
        key="ignition_on",
        translation_key="ignition_on",
        data_key="ignition_on",
        icon="mdi:key-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 Phase 7 PR #2 — VW EU + Audi telematics modem daily
    # power budget. When OFF the modem is rationing wake-ups to
    # preserve 12V → user sees long poll intervals. Diagnostic
    # category — power-users monitor this to plan a 12V check.
    VagBinarySensorDescription(
        key="daily_power_budget_available",
        translation_key="daily_power_budget_available",
        data_key="daily_power_budget_available",
        icon="mdi:battery-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.0 Phase 7 PR #4 — Skoda mysmob isVehicleInSavedLocation.
    # Whether the car's GPS matches a user-saved home/work location.
    # Enables "auto-charge only at home" automations without a zone
    # helper. Skoda-only today; other brands stay None.
    VagBinarySensorDescription(
        key="vehicle_at_saved_location",
        translation_key="vehicle_at_saved_location",
        data_key="vehicle_at_saved_location",
        icon="mdi:home-map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.2.1 Phase 8 PR #1 — Skoda 12V battery protection threshold.
    # Companion to VW EU/Audi `daily_power_budget_available`
    # (Phase 7 PR #2) — both signal modem rationing wake-ups.
    VagBinarySensorDescription(
        key="battery_protection_limit_on",
        translation_key="battery_protection_limit_on",
        data_key="battery_protection_limit_on",
        icon="mdi:battery-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.0.0 (Big-Bang) — Porsche TPMS warning aggregate (any corner
    # raising ``warning: true`` in the TIRE_PRESSURE measurement).
    # Brand-restricted via _DATA_PRESENT_REQUIRED below — non-Porsche
    # vehicles leave the field None → no phantom entity is created.
    VagBinarySensorDescription(
        key="tire_pressure_warning",
        translation_key="tire_pressure_warning",
        data_key="tire_pressure_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:car-tire-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.0.0 (Big-Bang) — Vehicle alarm (issue #33).
    # Two PROBLEM-class binary_sensors:
    # - ``alarm_active``: car-level alarm state (ALARM vs NO_ALARM)
    # - ``siren_active``: siren currently sounding
    # Brand-restricted via _DATA_PRESENT_REQUIRED — only populated when
    # the Cariad-BFF actually publishes the fields.
    VagBinarySensorDescription(
        key="alarm_active",
        translation_key="alarm_active",
        data_key="alarm_active",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:shield-alert",
    ),
    VagBinarySensorDescription(
        key="siren_active",
        translation_key="siren_active",
        data_key="siren_active",
        device_class=BinarySensorDeviceClass.SOUND,
        icon="mdi:bullhorn-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.0.0 (Big-Bang) — read-only ``enabled`` binary_sensors for the
    # 3 departure timers. The existing ``departure_timer_X_switch``
    # entities are write-able and conflate read+write, which makes them
    # awkward as conditions in template automations. These pure-read
    # binary_sensors expose the same field with PRESENCE semantics so
    # automations can ``binary_sensor.<vin>_departure_timer_1_enabled``
    # without accidentally toggling the timer in a template loop.
    VagBinarySensorDescription(
        key="departure_timer_1_enabled",
        translation_key="departure_timer_1_enabled",
        data_key="departure_timer_1_enabled",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="departure_timer_2_enabled",
        translation_key="departure_timer_2_enabled",
        data_key="departure_timer_2_enabled",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    VagBinarySensorDescription(
        key="departure_timer_3_enabled",
        translation_key="departure_timer_3_enabled",
        data_key="departure_timer_3_enabled",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.5.0 (#306 goncal Mii electric, parity with PyCupra) — three
    # boolean fields that were parsed into VehicleData since v1.x but
    # never surfaced as HA entities. PyCupra ships them as binary_sensors
    # for the same VIN; we already had the data, just no entity wrapper.
    # All three are top-level booleans (no nested-dict-lookup needed).
    VagBinarySensorDescription(
        key="hood_open",
        translation_key="hood_open",
        data_key="hood_open",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-cog",
    ),
    VagBinarySensorDescription(
        key="trunk_open",
        translation_key="trunk_open",
        data_key="trunk_open",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-back",
    ),
    VagBinarySensorDescription(
        key="trunk_locked",
        translation_key="trunk_locked",
        data_key="trunk_locked",
        device_class=BinarySensorDeviceClass.LOCK,
        icon="mdi:lock",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # v2.5.0 — sunroof state for vehicles that have one. Phantom-protected
    # below (None data → no entity), so most cars without sunroof don't
    # show a meaningless OFF entity. Mirrors PyCupra parity for #306.
    VagBinarySensorDescription(
        key="sunroof_open",
        translation_key="sunroof_open",
        data_key="sunroof_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        icon="mdi:car-select",
    ),
)
BINARY_DESCRIPTIONS = BINARY_DESCRIPTIONS + _NEW_BINARY

# v1.11.0 — same phantom-entity-prevention pattern as sensor.py.
_DATA_PRESENT_REQUIRED: frozenset[str] = frozenset({
    # v2.8.1 #306 — 6 P1 boolean OLA-field gap entries. SEAT/CUPRA OLA
    # primarily; vehicles without the underlying field stay None so
    # no phantom binary sensor surfaces.
    "seat_heating",
    "parking_light",
    "external_power",
    "battery_care",
    "energy_flow",
    "area_alarm",
    "lights_on",
    # v2.5.0 (#306 goncal Mii) — sunroof is option-dependent. Many cars
    # don't have a sunroof; parser leaves field None → no phantom entity.
    "sunroof_open",
    # v1.12.0 (#23) — vehicles without lvBattery job don't get the warning.
    "warning_12v_low",
    # v1.15.0 — Skoda-only OTA. Cross-brand support deferred (Research
    # 2026-05-02) — CARIAD-BFF + OLA don't yet expose a software-version
    # update-status endpoint.
    "ota_update_available",
    # v1.17.1 — SEAT/CUPRA-only battery care endpoint. Stays None on
    # other brands and on accounts where the feature isn't available.
    "battery_care_enabled",
    # v1.26.0 Welle-6 Feature Backlog (#173) — phantom protection.
    # Brand-restricted at parser level (only populated when backend
    # ships the field). Other vehicles → field stays None → no phantom.
    "auto_unlock_when_charged",
    "climate_at_unlock",
    "window_heating_enabled",
    # v2.2.0 (scout #220) — Skoda-only AC-without-external-power.
    # Other brands leave field None → no phantom entity.
    "air_conditioning_without_external_power",
    # v2.5.9 (8 converging Skoda scouts) — Skoda-only Camping Mode today.
    # Cross-brand auto-light-up when other OLA brands ship the feature.
    "camping_mode",
    # v2.2.0 PR #9/20 + PR #10/20 — subscription_active companion to
    # subscription_expiry_at. SEAT/CUPRA from ``mycar.services``;
    # VW EU + Audi (PR #10) from CARIAD-BFF ``userCapabilities``.
    # Field stays None on Skoda/Porsche/VW NA AND on perpetual
    # entitlements → tri-state semantics prevent false-positives.
    "subscription_active",
    # v2.2.0 Phase 7 PR #1 — Skoda-only `readiness.ignitionOn`.
    # Other brands leave field None → no phantom entity.
    "ignition_on",
    # v2.2.0 Phase 7 PR #2 — VW EU + Audi only telematics power-
    # budget. Other brands' readiness blocks don't ship this leaf →
    # field stays None → no phantom entity.
    "daily_power_budget_available",
    # v2.2.0 Phase 7 PR #4 — Skoda-only isVehicleInSavedLocation.
    # Other brands' charging endpoints don't ship this leaf →
    # field stays None → no phantom entity.
    "vehicle_at_saved_location",
    # v2.2.1 Phase 8 PR #1 — Skoda-only 12V protection threshold.
    # Other brands' readiness blocks don't ship this leaf →
    # field stays None → no phantom entity.
    "battery_protection_limit_on",
    # v2.0.0 (Big-Bang) — Porsche-only TPMS warning (PPA TIRE_PRESSURE
    # measurement). Non-Porsche vehicles leave the field None → no phantom.
    "tire_pressure_warning",
    # v2.0.0 (Big-Bang) — Vehicle alarm (issue #33). Cariad-BFF only
    # publishes alarm fields on enrolled vehicles with anti-theft
    # configured. Cars without it leave both fields None → no phantom.
    "alarm_active",
    "siren_active",
})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors. v1.25.0 PR-C: dynamic listener spawn —
    all 4 sub-loops (descriptions / doors / windows / lights) run
    per-VIN once, idempotently re-run when new vehicles wake up."""
    coordinator: VagConnectCoordinator = entry.runtime_data

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        entities: list = []
        has_battery = vehicle.get("has_battery", False)
        # 1) Description-driven binary sensors
        for desc in BINARY_DESCRIPTIONS:
            if desc.condition == "electric" and not has_battery:
                continue
            # v1.11.0 (#91) — phantom-entity prevention.
            if (
                desc.key in _DATA_PRESENT_REQUIRED
                and vehicle.get(desc.data_key) is None
            ):
                continue
            entities.append(VagConnectBinarySensor(coordinator, vin, desc))

        # 2) Per-door sensors
        for door_id in vehicle.get("doors_individual", {}):
            entities.append(VagDoorSensor(coordinator, vin, door_id))
        # 3) Per-window sensors (SEAT/CUPRA OLA today)
        for window_id in vehicle.get("windows_individual", {}):
            entities.append(VagWindowSensor(coordinator, vin, window_id))
        # 4) Per-light sensors (v1.12.0 #91 leftover)
        for light_id in vehicle.get("lights_individual", {}):
            entities.append(VagLightSensor(coordinator, vin, light_id))
        return entities

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagConnectBinarySensor(VagConnectEntity, BinarySensorEntity):
    entity_description: VagBinarySensorDescription

    def __init__(self, coordinator: VagConnectCoordinator, vin: str, description: VagBinarySensorDescription) -> None:
        super().__init__(coordinator, vin, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        val = self._vehicle.get(self.entity_description.data_key)
        if val is None:
            return None
        # v1.20.1 (#131 Chr1sDub Skoda Octavia iV bug-report) — fix
        # inverted UI for HA's LOCK device class. HA convention:
        # ``BinarySensorDeviceClass.LOCK`` → ``is_on=True`` means
        # "open" / "unsafe" / "unlocked"; ``is_on=False`` means
        # "locked" / "safe". Our internal model field convention
        # (``data["doors_locked"] = True`` when locked) matches the
        # natural-language reading but is the opposite of the LOCK
        # class semantic. Without this invert, HA showed "Unlocked"
        # in the UI for actually-locked vehicles — confusing for
        # every Skoda user since the binary_sensor was added.
        # The lock entity (lock.py:is_locked) reads the same field
        # but uses the LockEntity convention which is non-inverted,
        # so it was always correct.
        if (
            self.entity_description.device_class
            == BinarySensorDeviceClass.LOCK
        ):
            return not bool(val)
        return bool(val)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """v1.15.0 — surface OTA release-notes URL on the update sensor.

        Pattern from the Trip-Stats `recent_trips` attrs in v1.14.0:
        list-shaped or freely-formed metadata lives here, not in the
        state string (which has a 255 char limit and is recorder-noisy).
        """
        if self.entity_description.key == "ota_update_available":
            url = self._vehicle.get("ota_release_notes_url")
            status = self._vehicle.get("software_update_status")
            attrs: dict[str, Any] = {}
            if isinstance(url, str) and url:
                attrs["release_notes_url"] = url
            if isinstance(status, str) and status:
                attrs["raw_status"] = status
            return attrs or None
        return None


# Per-door binary sensors.

_DOOR_NAMES = {
    "frontLeft":  "Door Front Left",
    "frontRight": "Door Front Right",
    "rearLeft":   "Door Rear Left",
    "rearRight":  "Door Rear Right",
    "trunk":      "Trunk",
    "bonnet":     "Motorhaube",
}


class VagDoorSensor(VagConnectEntity, BinarySensorEntity):
    """Binary Sensor für eine einzelne Tür/Kofferraum/Motorhaube."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(
        self,
        coordinator: VagConnectCoordinator,
        vin: str,
        door_id: str,
    ) -> None:
        super().__init__(coordinator, vin, f"door_{door_id}")
        self._door_id = door_id
        self._attr_name = _DOOR_NAMES.get(door_id, door_id)
        self._attr_icon = "mdi:car-door" if "door" in door_id.lower() or "rear" in door_id.lower() or "front" in door_id.lower() else "mdi:car-door-lock"

    @property
    def is_on(self) -> bool | None:
        doors = self._vehicle.get("doors_individual", {})
        val = doors.get(self._door_id)
        return bool(val) if val is not None else None


async def _async_setup_door_sensors(
    coordinator: VagConnectCoordinator,
    vin: str,
    vehicle: dict,
    entities: list,
) -> None:
    """Legt individuelle Tür-Sensoren an basierend auf Fahrzeug-Doors-Dict."""
    doors = vehicle.get("doors_individual", {})
    for door_id in doors:
        entities.append(VagDoorSensor(coordinator, vin, door_id))


# v1.8.9 (Session 3C) — per-window binary sensors.
# Layout mirrors ``_DOOR_NAMES``; populated by SEAT/CUPRA OLA paths
# (``status.windows.{position}``). State convention: ``True`` means
# *open* (BinarySensorDeviceClass.WINDOW reports True for "the
# detected event", i.e. open). Internally we store ``True`` for
# *closed* in ``windows_individual`` (consistent with
# ``doors_individual``), so ``is_on`` inverts that.

_WINDOW_NAMES = {
    "frontLeft":  "Window Front Left",
    "frontRight": "Window Front Right",
    "rearLeft":   "Window Rear Left",
    "rearRight":  "Window Rear Right",
}


class VagWindowSensor(VagConnectEntity, BinarySensorEntity):
    """Binary Sensor für ein einzelnes Fenster (CUPRA/SEAT initial)."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW

    def __init__(
        self,
        coordinator: VagConnectCoordinator,
        vin: str,
        window_id: str,
    ) -> None:
        super().__init__(coordinator, vin, f"window_{window_id}")
        self._window_id = window_id
        self._attr_name = _WINDOW_NAMES.get(window_id, window_id)
        self._attr_icon = "mdi:car-door"

    @property
    def is_on(self) -> bool | None:
        windows = self._vehicle.get("windows_individual", {})
        val = windows.get(self._window_id)
        # Stored value: True == closed. is_on for WINDOW device_class
        # means "open detected" — invert.
        return (not val) if val is not None else None


async def _async_setup_window_sensors(
    coordinator: VagConnectCoordinator,
    vin: str,
    vehicle: dict,
    entities: list,
) -> None:
    """Legt individuelle Fenster-Sensoren an, wenn die Fahrzeug-Antwort
    sie liefert. Heute: SEAT/CUPRA OLA. Andere Marken: leer → keine Entities."""
    windows = vehicle.get("windows_individual", {})
    for window_id in windows:
        entities.append(VagWindowSensor(coordinator, vin, window_id))


# v1.12.0 (#91 leftover) — per-light binary sensors. Mirror the
# door/window pattern: dynamically created at setup time based on
# whatever names the v1.11.0 vw_eu light parser put into
# ``lights_individual``. Vehicles whose firmware ships an unknown
# light element shape leave that dict empty → no per-light entities,
# only the aggregate ``lights_on`` + ``lights_count`` from v1.11.0.
class VagLightSensor(VagConnectEntity, BinarySensorEntity):
    """Binary Sensor für ein einzelnes Fahrzeuglicht (frontLeft etc.).

    state: True == "this light is on" (BinarySensorDeviceClass.LIGHT
    convention matches the parser's bool semantics directly).
    """

    _attr_device_class = BinarySensorDeviceClass.LIGHT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:lightbulb-on-outline"

    def __init__(
        self,
        coordinator: VagConnectCoordinator,
        vin: str,
        light_id: str,
    ) -> None:
        super().__init__(coordinator, vin, f"light_{light_id}")
        self._light_id = light_id
        # Friendly fallback name; HA will use translation_key if available.
        self._attr_name = f"Light {light_id}"

    @property
    def is_on(self) -> bool | None:
        lights = self._vehicle.get("lights_individual", {})
        val = lights.get(self._light_id)
        return bool(val) if val is not None else None


async def _async_setup_light_sensors(
    coordinator: VagConnectCoordinator,
    vin: str,
    vehicle: dict,
    entities: list,
) -> None:
    """Create per-light binary sensors based on ``lights_individual`` dict.

    Empty dict → no entities. Same phantom-protection pattern as
    ``_async_setup_door_sensors`` / ``_async_setup_window_sensors``.
    """
    lights = vehicle.get("lights_individual", {})
    for light_id in lights:
        entities.append(VagLightSensor(coordinator, vin, light_id))
