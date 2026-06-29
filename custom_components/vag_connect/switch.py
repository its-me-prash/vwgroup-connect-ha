# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Switches for VAG Connect (lock/unlock, charging)."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.12.0 (#63) — Read-only Mode: switches send commands, skip all.
    if coordinator.is_read_only():
        return
    client = coordinator._cariad_client

    def _supported(vin: str, command_id: str) -> bool:
        cap_supported = coordinator.command_capability_supported(vin, command_id) is not False
        client_has_method = client is not None and hasattr(client, command_id)
        return cap_supported and client_has_method

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        entities: list = []
        if _supported(vin, "command_lock"):
            entities.append(VagLockSwitch(coordinator, vin))
        if _supported(vin, "command_start_climate"):
            entities.append(VagClimatisationSwitch(coordinator, vin))
        if _supported(vin, "command_start_window_heating"):
            entities.append(VagWindowHeatingSwitch(coordinator, vin))
        if _supported(vin, "command_start_ventilation"):
            entities.append(VagVentilationSwitch(coordinator, vin))
        if _supported(vin, "command_start_aux_heating"):
            entities.append(VagAuxHeatingSwitch(coordinator, vin))
        if vehicle.get("has_battery"):  # EV + PHEV
            if _supported(vin, "command_start_charging"):
                entities.append(VagChargingSwitch(coordinator, vin))
            if _supported(vin, "command_set_departure_timer"):
                for timer_id in (1, 2, 3):
                    entities.append(VagDepartureTimerSwitch(coordinator, vin, timer_id))
        return entities

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagLockSwitch(VagConnectEntity, SwitchEntity):
    """Door lock toggle."""

    _attr_translation_key = "lock_switch"
    _attr_icon = "mdi:car-door-lock"
    # v1.9.1 — Phase 2 gating mirrors VagDoorLock (same backend command).
    _command_id = "command_lock"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "lock_switch")

    @property
    def is_on(self) -> bool | None:
        return self._vehicle.get("doors_locked")

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_lock(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_unlock(self._vin)


class VagClimatisationSwitch(VagConnectEntity, SwitchEntity):
    """Pre-conditioning toggle."""

    _attr_translation_key = "climatisation_switch"
    _attr_icon = "mdi:thermometer"
    # v1.9.1 — Phase 2 gating.
    _command_id = "command_start_climate"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "climatisation_switch")

    @property
    def is_on(self) -> bool | None:
        state = self._vehicle.get("climatisation_state")
        if state is None:
            return None
        return str(state).lower() not in ("off", "stopped", "")

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_start_climatisation(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_stop_climatisation(self._vin)


class VagChargingSwitch(VagConnectEntity, SwitchEntity):
    """Charging toggle."""

    _attr_translation_key = "charging_switch"
    _attr_icon = "mdi:ev-plug-type2"
    # v1.9.1 — Phase 2 gating.
    _command_id = "command_start_charging"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "charging_switch")

    @property
    def is_on(self) -> bool | None:
        state = self._vehicle.get("charging_state")
        if state is None:
            return None
        return str(state).lower() in ("charging", "conservationcharging")

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_start_charging(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_stop_charging(self._vin)


class VagWindowHeatingSwitch(VagConnectEntity, SwitchEntity):
    """Window heating on/off."""

    _attr_translation_key = "window_heating_switch"
    _attr_icon = "mdi:car-windshield"
    # v1.9.1 — Phase 2 gating.
    _command_id = "command_start_window_heating"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "window_heating_switch")

    @property
    def is_on(self) -> bool | None:
        val = self._vehicle.get("window_heating_front")
        return bool(val) if val is not None else None

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_start_window_heating(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_stop_window_heating(self._vin)


class VagDepartureTimerSwitch(VagConnectEntity, SwitchEntity):
    """Enable or disable a departure timer (1–3)."""

    _attr_icon = "mdi:clock-time-eight-outline"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str, timer_id: int) -> None:
        super().__init__(coordinator, vin, f"departure_timer_{timer_id}_switch")
        self._timer_id = timer_id
        self._attr_translation_key = f"departure_timer_{timer_id}_switch"

    @property
    def is_on(self) -> bool | None:
        return self._vehicle.get(f"departure_timer_{self._timer_id}_enabled")

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_set_departure_timer(
            self._vin, self._timer_id, enabled=True, departure_time=None
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_set_departure_timer(
            self._vin, self._timer_id, enabled=False, departure_time=None
        )


class VagVentilationSwitch(VagConnectEntity, SwitchEntity):
    """v1.17.1 (Bruno seq 31/32) — SEAT/CUPRA cabin ventilation toggle.

    Optimistic-UI free (the OLA backend has no live ventilation_state
    sensor we could revert from), so we just dispatch and let the next
    poll surface the actual state.
    """

    _attr_translation_key = "ventilation_switch"
    _attr_icon = "mdi:fan"
    _command_id = "command_start_ventilation"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "ventilation_switch")

    @property
    def is_on(self) -> bool | None:
        # No reliable ventilation_state field in OLA mycar — return None
        # so HA shows "unknown" rather than a fake state.
        return self._vehicle.get("ventilation_active")

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_start_ventilation(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_stop_ventilation(self._vin)


class VagAuxHeatingSwitch(VagConnectEntity, SwitchEntity):
    """Engine pre-heater toggle (Standheizung).

    v1.17.1 (Bruno seq 29/30): SEAT/CUPRA Webasto aux heating toggle.
    Start requires SecToken (S-PIN-derived); stop does not. The
    coordinator helper raises ServiceValidationError("spin_required")
    at command time if S-PIN is missing on the SEAT/CUPRA path, same
    UX as VagDoorLock.

    v2.8.0: extended to Audi + VW EU. CARIAD-BFF endpoint takes a
    duration + target temperature payload, read at start time from the
    new ``auxheat_duration`` / ``auxheat_target_temp`` number sliders
    (stored under entry.options). No S-PIN required on the
    Audi + VW EU path.
    """

    _attr_translation_key = "aux_heating_switch"
    _attr_icon = "mdi:fire"
    _command_id = "command_start_aux_heating"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "aux_heating_switch")

    @property
    def is_on(self) -> bool | None:
        # v2.8.0 - prefer the derived ``aux_heating_active`` flag set by
        # the vw_eu parser. Fall back to ``auxiliary_heating_status``
        # so SEAT/CUPRA paths that haven't been wired yet still surface
        # a sensible state when their parser grows the field later.
        active = self._vehicle.get("aux_heating_active")
        if isinstance(active, bool):
            return active
        status = self._vehicle.get("auxiliary_heating_status")
        if isinstance(status, str) and status:
            return status.lower() in {"heating", "on", "heatingon", "active"}
        return None

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_start_aux_heating(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_stop_aux_heating(self._vin)
