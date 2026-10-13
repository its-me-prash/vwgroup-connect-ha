# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Climate entity for VW Group Connect — remote pre-conditioning."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import DOMAIN
from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

if TYPE_CHECKING:
    from .companion.client import ClimateTargets

DEFAULT_TEMP = 21.0
MIN_TEMP = 16.0
MAX_TEMP = 30.0
TEMP_STEP = 0.5


# b13 — platinum parallel-updates rule: the coordinator's background poll
# loop owns every API request, so entity updates need no throttling. HA reads
# this MODULE-level constant (an entity attr is a no-op).
PARALLEL_UPDATES = 0


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
        if coordinator.is_companion():
            return [VagCompanionClimate(coordinator, vin)]
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
        # Companion: the temperature held in HA for the next Start (the poll
        # reads what the app's dial shows, which Start overwrites).
        if self.coordinator.is_companion():
            from .companion.client import climate_targets_of  # noqa: PLC0415

            targets = climate_targets_of(self.coordinator)
            if targets is not None and targets.temp_c is not None:
                return targets.temp_c
        t = self._vehicle.get("target_temperature")
        return float(t) if t is not None else DEFAULT_TEMP

    def _check_hvac_mode(self, hvac_mode: str) -> HVACMode:
        # Only the listed modes: anything else must never be read as Stop.
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="hvac_mode_not_supported",
                translation_placeholders={
                    "hvac_mode": str(hvac_mode), "modes": ", ".join(self.hvac_modes),
                },
            )
        return HVACMode(hvac_mode)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        hvac_mode = self._check_hvac_mode(hvac_mode)
        if hvac_mode == HVACMode.HEAT_COOL:
            await self.coordinator.async_start_climatisation(self._vin)
        else:
            await self.coordinator.async_stop_climatisation(self._vin)

    async def async_set_temperature(self, **kwargs: object) -> None:
        hvac_mode = kwargs.get("hvac_mode") if self.coordinator.is_companion() else None
        if hvac_mode is not None:
            # Checked before anything is stored or sent.
            hvac_mode = self._check_hvac_mode(str(hvac_mode))
        raw = kwargs.get("temperature", DEFAULT_TEMP)
        temp = float(raw) if isinstance(raw, (int, float)) else DEFAULT_TEMP
        await self.coordinator.async_set_climatisation_temperature(
            self._vin, temp
        )
        # Companion: the store comes first, so a Start asked for alongside
        # applies the new temperature.
        if hvac_mode is not None:
            await self.async_set_hvac_mode(hvac_mode)


PRESET_AIR_CONDITIONING = "air_conditioning"
PRESET_WINDOW_HEATING = "window_heating"


@dataclass
class _HeldClimate(ExtraStoredData):
    """What HA holds for the next Start, with the dial it was held against."""

    held_temp_c: float | None
    app_dial_c: float | None
    window_heating_only: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "held_temp_c": self.held_temp_c,
            "app_dial_c": self.app_dial_c,
            "window_heating_only": self.window_heating_only,
        }


class VagCompanionClimate(VagClimate, RestoreEntity):
    """Companion: the one place to run climate.

    The app's *Select mode* picker only chooses what Start starts, and one
    Stop ends either mode. So the mode is a preset: chosen while off it is
    held in HA for the next start (nothing is sent), while running it shows
    what runs and cannot be changed. Same unique id as the shared entity.
    """

    _attr_preset_modes: list[str] = [PRESET_AIR_CONDITIONING, PRESET_WINDOW_HEATING]
    # The app's dial: 15.5 is LO, 30 is HI.
    _attr_min_temp = 15.5

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin)
        self._attr_supported_features |= (
            ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    @property
    def extra_restore_state_data(self) -> _HeldClimate:
        # Only held values: a dial reading shown in their place must never come
        # back as a target, or the next Start would move the dial.
        t = self._targets()
        return _HeldClimate(
            t.temp_c if t is not None else None,
            t.app_dial_c if t is not None else None,
            bool(t.window_heating_only) if t is not None else False,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        extra = await self.async_get_last_extra_data()
        if extra is None:
            return
        saved = extra.as_dict()
        client = self.coordinator._cariad_client
        if saved.get("window_heating_only") is True:
            client.store_climate_start_mode(True)
        held = saved.get("held_temp_c")
        dial = saved.get("app_dial_c")
        if isinstance(held, (int, float)) and not isinstance(held, bool):
            client.restore_climate_target_temperature(
                float(held), float(dial) if isinstance(dial, (int, float)) else None,
            )

    _window_heating_seen = False

    def _handle_coordinator_update(self) -> None:
        # Mirror the app: a window-heating Start is one-shot. Once a run was
        # seen and has ended (Stop, the car's timer, or the app), the next
        # Start is air conditioning again. A choice never started is kept.
        t = self._targets()
        if t is not None and t.window_heating_only:
            # Only a read shows window heating running: a Start's optimistic
            # climatisation_active (reverted when the Start is refused) is not
            # a run, and a real window-heating read never sets it.
            if self._vehicle.get("window_heating_front"):
                self._window_heating_seen = True
            elif self._window_heating_seen:
                self._window_heating_seen = False
                self.coordinator._cariad_client.store_climate_start_mode(False)
        super()._handle_coordinator_update()

    def _targets(self) -> ClimateTargets | None:
        from .companion.client import climate_targets_of  # noqa: PLC0415

        return climate_targets_of(self.coordinator)

    def _running(self) -> bool:
        v = self._vehicle
        return bool(v.get("climatisation_active")) or bool(v.get("window_heating_front"))

    @property
    def hvac_mode(self) -> HVACMode:
        # Window heating alone is climate running too: the app's Stop ends it.
        return HVACMode.HEAT_COOL if self._running() else HVACMode.OFF

    @property
    def preset_mode(self) -> str:
        if self._running():
            if self._vehicle.get("climatisation_active"):
                shown = self._vehicle.get("climate_start_mode")
                return PRESET_WINDOW_HEATING if shown == PRESET_WINDOW_HEATING else PRESET_AIR_CONDITIONING
            return PRESET_WINDOW_HEATING
        targets = self._targets()
        if targets is not None and targets.window_heating_only:
            return PRESET_WINDOW_HEATING
        return PRESET_AIR_CONDITIONING

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in self._attr_preset_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="climate_preset_not_supported",
                translation_placeholders={
                    "preset": str(preset_mode), "presets": ", ".join(self._attr_preset_modes),
                },
            )
        if self._running():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="climate_preset_while_running",
            )
        store = getattr(self.coordinator._cariad_client, "store_climate_start_mode", None)
        if callable(store):
            store(preset_mode == PRESET_WINDOW_HEATING)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT_COOL)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
