# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
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
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner


@dataclass(frozen=True)
class VagNumberDescription(NumberEntityDescription):
    data_key: str = ""
    condition: str | None = None  # "electric" | "auxheat" | "battery_care" | None
    # v4.0.0 grounding wave — optional capability-id (or tuple of variants);
    # None = ungated. See coordinator.read_capability_hidden.
    capability: "str | tuple[str, ...] | None" = None


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
    # v2.18.0 — battery-care top-charge target. Backend accepts 50-100 and
    # rejects the rest; the slider mirrors that rather than letting the user
    # pick a value the car will refuse.
    VagNumberDescription(
        key="battery_care_target",
        translation_key="battery_care_target",
        data_key="battery_care_target_soc_pct",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        native_min_value=50,
        native_max_value=100,
        native_step=5,
        mode=NumberMode.SLIDER,
        icon="mdi:battery-heart-variant",
        entity_category=EntityCategory.CONFIG,
        condition="battery_care",
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
    # v2.23.0 (#847) — the poll-interval slider is account-scoped (not per-VIN)
    # and useful to EVERY user, so create it BEFORE the read-only short-circuit
    # below: read-only / portal users are exactly the ones who want to tune how
    # often the integration polls the manufacturer backend.
    async_add_entities([VagConnectScanIntervalNumber(coordinator, entry)])
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
            # v4.0.0 grounding wave — soft capability gate (opt-in via
            # desc.capability; hidden only on an explicitly-absent cap).
            if desc.capability is not None and coordinator.read_capability_hidden(
                vin, desc.capability
            ):
                continue
            # v2.18.0 — gate on the READ having produced a value rather than on
            # the brand: every client inherits the command stub from the base
            # class, so a capability/hasattr check can't tell us who really has
            # the feature. A car that reports a care target has it.
            if (
                desc.condition == "battery_care"
                and vehicle.get("battery_care_target_soc_pct") is None
            ):
                continue
            cmd_id = _CMD_ID.get(desc.key)
            if cmd_id and coordinator.command_capability_supported(vin, cmd_id) is False:
                continue
            # v3.0.0a1 — the client must implement the command, else the number
            # raises AttributeError on set (companion/ADB has no target-SoC etc.).
            if cmd_id and not coordinator.command_method_available(cmd_id):
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
            # v2.18.0 — options THEN data. The setter below writes to
            # entry.options, but the update-listener folds options into
            # entry.data and blanks entry.options (__init__.py), so an
            # options-only read never saw the stored value and the slider
            # snapped straight back to the spec default.
            entry = self.coordinator.entry
            # v2.18.0 (#806, lucson) — entry.data/.options are MappingProxyType,
            # not dict, so the isinstance(..., dict) checks below silently failed
            # on every real HA instance and this always returned the default.
            # Normalise to a real dict once; keep the isinstance guards as a
            # belt against a None/odd entry.
            options = dict(getattr(entry, "options", None) or {})
            data = dict(getattr(entry, "data", None) or {})
            dkey = self.entity_description.data_key
            val = options.get(dkey) if isinstance(options, dict) else None
            if val is None and isinstance(data, dict):
                val = data.get(dkey)
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
        elif key == "battery_care_target":
            await self.coordinator.async_set_battery_care_target(self._vin, int(value))
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


class VagConnectScanIntervalNumber(NumberEntity):
    """Config-entry-scoped poll-interval slider, in minutes.

    v2.23.0 (#847) — exposes the account poll interval as a Number so it can be
    driven from an HA automation (e.g. shorter by day, longer at night) to cut
    load on the manufacturer backend. It writes ``CONF_SCAN_INTERVAL`` into
    ``entry.options``; the update-listener folds that into ``entry.data`` and
    ``_poll_loop`` re-reads it live every iteration — no reload, no service.

    Unlike the per-VIN command sliders it is NOT tied to a vehicle: it lives on
    its own account-level service device and is created for EVERY entry,
    including read-only (portal) ones.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "scan_interval"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = MIN_SCAN_INTERVAL
    _attr_native_max_value = 240
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(
        self, coordinator: VagConnectCoordinator, entry: ConfigEntry
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_scan_interval"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_settings")},
            name="VW Group Connect",
            manufacturer="VW Group",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | None:
        # Options THEN data: the setter writes entry.options, but the
        # update-listener folds options into entry.data and blanks options, so
        # an options-only read would miss the stored value. Both are
        # MappingProxyType on a live HA (#806), so normalise to a real dict.
        options = dict(getattr(self._entry, "options", None) or {})
        data = dict(getattr(self._entry, "data", None) or {})
        val = options.get(CONF_SCAN_INTERVAL)
        if val is None:
            val = data.get(CONF_SCAN_INTERVAL)
        try:
            return float(val) if val is not None else float(DEFAULT_SCAN_INTERVAL)
        except (TypeError, ValueError):
            return float(DEFAULT_SCAN_INTERVAL)

    async def async_set_native_value(self, value: float) -> None:
        # Clamp to [MIN_SCAN_INTERVAL, native_max] as a belt against a raw
        # number.set_value service call bypassing the slider bounds — a too-low
        # interval would hammer the backend's request quota.
        clamped = max(MIN_SCAN_INTERVAL, min(int(value), int(self._attr_native_max_value)))
        current = dict(self._entry.options or {})
        current[CONF_SCAN_INTERVAL] = clamped
        self._coordinator.hass.config_entries.async_update_entry(
            self._entry, options=current,
        )
        self.async_write_ha_state()
