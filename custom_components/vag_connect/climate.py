# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Climate entity for VW Group Connect — remote pre-conditioning."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

DEFAULT_TEMP = 21.0
MIN_TEMP = 16.0
MAX_TEMP = 30.0
TEMP_STEP = 0.5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.12.0 (#63) — Read-only Mode: climate sends commands, skip.
    if coordinator.is_read_only():
        return

    def _build_for_vin(vin: str, vehicle: dict) -> list:  # noqa: ARG001
        # v1.13.0 (#56 Phase 3) — capability filter; only False (explicit
        # backend confirmation) hides; None (unknown) keeps the entity.
        if coordinator.command_capability_supported(vin, "command_start_climate") is False:
            return []
        return [VagClimate(coordinator, vin)]

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagClimate(VagConnectEntity, ClimateEntity):
    """Climate entity for vehicle pre-conditioning."""

    _attr_translation_key = "climate"
    _attr_icon = "mdi:thermometer"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    # v1.9.1 — Phase 2 gating. We use the "start" command as the gating
    # signal because the read side (current_temperature, hvac_mode) is
    # purely cosmetic — only the actuation matters for entitlement.
    _command_id = "command_start_climate"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "climate")
        # v3.0.0a1 — only advertise settable target temperature when the client
        # can actually set it. The companion (ADB) client does climate on/off
        # (command_start/stop_climate) but has no command_set_climate_temperature,
        # so offering the slider there would AttributeError on use. A full
        # network client keeps the feature (it has the method), so existing
        # setups are unchanged.
        if not coordinator.command_method_available("command_set_climate_temperature"):
            self._attr_supported_features = ClimateEntityFeature(0)

    @property
    def hvac_mode(self) -> HVACMode:
        # b7 (grounded audit P0-1) — the VW-EU/SEAT/CUPRA parsers store
        # b9 regression fix — derive from the parser-computed
        # ``climatisation_active`` boolean, the single source of truth every brand
        # sets alongside ``climatisation_state`` (with full knowledge of that
        # brand's state vocabulary). The b7 case-folded deny-list
        # (``state not in ("off","stopped","")``) read HEAT_COOL for TERMINAL /
        # no-data states — Škoda-official ``COMPLETED``/``UNKNOWN``, SEAT/CUPRA
        # ``unsupported`` — where the binary sensor + switch correctly read off,
        # re-introducing the exact climate↔switch contradiction b7 set out to
        # remove. Prefer the boolean; fall back to the state deny-list only if a
        # channel ever leaves ``climatisation_active`` unset.
        active = self._vehicle.get("climatisation_active")
        if active is not None:
            return HVACMode.HEAT_COOL if active else HVACMode.OFF
        state = self._vehicle.get("climatisation_state")
        if state and str(state).lower() not in ("off", "stopped", ""):
            return HVACMode.HEAT_COOL
        return HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        return self._vehicle.get("outside_temp")

    @property
    def target_temperature(self) -> float | None:
        t = self._vehicle.get("target_temperature")
        return float(t) if t is not None else DEFAULT_TEMP

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT_COOL:
            await self.coordinator.async_start_climatisation(self._vin)
        else:
            await self.coordinator.async_stop_climatisation(self._vin)

    async def async_set_temperature(self, **kwargs: object) -> None:
        raw = kwargs.get("temperature", DEFAULT_TEMP)
        temp = float(raw) if isinstance(raw, (int, float)) else DEFAULT_TEMP
        await self.coordinator.async_set_climatisation_temperature(
            self._vin, temp
        )
