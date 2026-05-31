# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Number entities for VAG Connect (target SOC, climatisation temperature)."""

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner


@dataclass(frozen=True)
class VagNumberDescription(NumberEntityDescription):
    data_key: str = ""
    condition: str | None = None  # "electric" | None


NUMBER_DESCRIPTIONS: tuple[VagNumberDescription, ...] = (
    VagNumberDescription(
        key="target_soc",
        translation_key="target_soc",
        data_key="target_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        native_min_value=10,
        native_max_value=100,
        native_step=5,
        mode=NumberMode.SLIDER,
        icon="mdi:battery-charging-high",
        entity_category=EntityCategory.CONFIG,
        condition="electric",
    ),
    VagNumberDescription(
        key="target_temperature",
        translation_key="target_temperature",
        data_key="target_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=16,
        native_max_value=30,
        native_step=0.5,
        mode=NumberMode.SLIDER,
        icon="mdi:thermometer",
        entity_category=EntityCategory.CONFIG,
    ),
    VagNumberDescription(
        key="min_soc",
        translation_key="min_soc",
        data_key="min_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        native_min_value=0,
        native_max_value=100,
        native_step=5,
        mode=NumberMode.SLIDER,
        icon="mdi:battery-charging-low",
        entity_category=EntityCategory.CONFIG,
        condition="electric",
    ),
    # v1.12.0 (#91 follow-up) — writeable max AC charge current.
    # The CARIAD command was wired in v1.12.0 (vw_eu.py:
    # command_set_max_charge_current), so the Number entity returns.
    # Range 6-32 A covers all common chargers; step=2 matches the values
    # most VW EU vehicles accept (6, 8, 10, 12, 14, 16, 32). Values
    # outside the vehicle's capability list will be rejected by the
    # backend with a 4xx — surfaced via ServiceValidationError through
    # the standard _cariad_cmd → classify_command_failure pipeline.
    VagNumberDescription(
        key="max_charge_current",
        translation_key="max_charge_current",
        data_key="max_charge_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        native_min_value=6,
        native_max_value=32,
        native_step=2,
        mode=NumberMode.SLIDER,
        icon="mdi:current-ac",
        entity_category=EntityCategory.CONFIG,
        condition="electric",
    ),
    # v2.8.0 - Auxiliary heating runtime preset (Audi + VW EU only).
    # Stored in entry.options under "auxheat_duration"; the aux heating
    # switch reads it at start-time so the user can set "always preheat
    # for 25 min" once and never touch it again. Not a live data value,
    # purely a setting, so condition="auxheat" restricts the entity to
    # the two brands that ship the Cariad-BFF aux-heating endpoint.
    VagNumberDescription(
        key="auxheat_duration",
        translation_key="auxheat_duration",
        data_key="auxheat_duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=5,
        native_max_value=60,
        native_step=5,
        mode=NumberMode.SLIDER,
        icon="mdi:timer-sand",
        entity_category=EntityCategory.CONFIG,
        condition="auxheat",
    ),
    # v2.8.0 - Auxiliary heating cabin target temperature preset
    # (Audi + VW EU only). Stored in entry.options under
    # "auxheat_target_temp"; the aux heating switch passes it through
    # to the Cariad-BFF endpoint (converted to Kelvin).
    VagNumberDescription(
        key="auxheat_target_temp",
        translation_key="auxheat_target_temp",
        data_key="auxheat_target_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=16,
        native_max_value=30,
        native_step=0.5,
        mode=NumberMode.SLIDER,
        icon="mdi:thermometer-lines",
        entity_category=EntityCategory.CONFIG,
        condition="auxheat",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.12.0 (#63) — Read-only Mode: number sliders send commands, skip.
    if coordinator.is_read_only():
        return

    _CMD_ID = {
        "target_soc": "command_set_target_soc",
        "target_temperature": "command_set_climate_temperature",
        "min_soc": "command_set_min_soc",
        "max_charge_current": "command_set_max_charge_current",
        # v2.8.0 - aux heating sliders are settings (no live command),
        # so gate via the start command's capability so the slider only
        # appears for VINs whose backend can actually consume the value.
        "auxheat_duration": "command_start_aux_heating",
        "auxheat_target_temp": "command_start_aux_heating",
    }

    # v2.8.0 - brand check for the aux heating sliders. Audi + VW EU
    # only; other brands (SEAT/CUPRA OLA, Skoda, Porsche, VW NA) ignore
    # duration + target on the wire, so creating the slider for them
    # would be misleading.
    from .const import CONF_BRAND  # noqa: PLC0415
    brand = str(entry.data.get(CONF_BRAND, "")).lower()
    auxheat_supported_brand = brand in {"volkswagen", "audi"}

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        entities: list = []
        has_battery = vehicle.get("has_battery", False)
        for desc in NUMBER_DESCRIPTIONS:
            if desc.condition == "electric" and not has_battery:
                continue
            if desc.condition == "auxheat" and not auxheat_supported_brand:
                continue
            cmd_id = _CMD_ID.get(desc.key)
            if cmd_id and coordinator.command_capability_supported(vin, cmd_id) is False:
                continue
            entities.append(VagConnectNumber(coordinator, vin, desc))
        return entities

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagConnectNumber(VagConnectEntity, NumberEntity):
    entity_description: VagNumberDescription

    def __init__(self, coordinator: VagConnectCoordinator, vin: str, description: VagNumberDescription) -> None:
        super().__init__(coordinator, vin, description.key)
        self.entity_description = description

    # v2.8.0 - default values for the aux heating sliders when the user
    # has not picked one yet. Mirrors the coordinator-side fallbacks in
    # ``async_start_aux_heating`` so the UI and the wire payload agree.
    _AUXHEAT_DEFAULTS: dict[str, float] = {
        "auxheat_duration": 30.0,
        "auxheat_target_temp": 21.0,
    }

    @property
    def native_value(self) -> float | None:
        key = self.entity_description.key
        # v2.8.0 - aux heating sliders are settings, not telemetry. Read
        # them from entry.options so the value persists across HA
        # restarts. Fall back to the spec defaults when the user has
        # not changed the slider yet.
        if key in self._AUXHEAT_DEFAULTS:
            options = getattr(self.coordinator.entry, "options", None) or {}
            val = options.get(self.entity_description.data_key) if isinstance(options, dict) else None
            try:
                return float(val) if val is not None else self._AUXHEAT_DEFAULTS[key]
            except (TypeError, ValueError):
                return self._AUXHEAT_DEFAULTS[key]
        val = self._vehicle.get(self.entity_description.data_key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set slider value — dispatches to the appropriate coordinator action."""
        key = self.entity_description.key
        if key == "target_soc":
            await self.coordinator.async_set_target_soc(self._vin, int(value))
        elif key == "target_temperature":
            await self.coordinator.async_set_climatisation_temperature(self._vin, value)
        elif key == "min_soc":
            await self.coordinator.async_set_min_soc(self._vin, int(value))
        elif key == "max_charge_current":
            # v1.12.0 (#91 follow-up) — wired to the new
            # vw_eu:command_set_max_charge_current command.
            await self.coordinator.async_set_max_charge_current(self._vin, int(value))
        elif key in self._AUXHEAT_DEFAULTS:
            # v2.8.0 - persist aux heating preset into entry.options.
            # The number is a *setting*, not a backend command, so we
            # write to the config entry instead of calling a coordinator
            # method. The aux heating switch reads these on start.
            entry = self.coordinator.entry
            current = dict(entry.options or {})
            stored: float | int = (
                int(value) if key == "auxheat_duration" else float(value)
            )
            current[self.entity_description.data_key] = stored
            self.coordinator.hass.config_entries.async_update_entry(
                entry, options=current,
            )
            # Trigger an entity state update so the slider reflects the
            # new value immediately without waiting for the next poll.
            self.async_write_ha_state()
