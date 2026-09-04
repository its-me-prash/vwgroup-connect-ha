# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Switches for VW Group Connect (lock/unlock, charging)."""

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
        # Aux heating (fuel-fired Standheizung). Gated like every other switch:
        # shown unless the per-VIN capability list explicitly lacks
        # AUXILIARY_HEATING. The old "positive-evidence" heuristic wrongly hid
        # it on aux-equipped Škodas whose AC subsystem reports INVALID during a
        # transient degraded/403 auth state (both the diesel reporter and a
        # gasoline Octavia owner presented byte-identical telemetry — there is
        # no groundable "no aux heater" signal in that state, so we never hide).
        if _supported(vin, "command_start_aux_heating"):
            entities.append(VagAuxHeatingSwitch(coordinator, vin))
        # v2.31.0 — Škoda camping mode. Gate on the READ having produced a value
        # (a car that reports camping state has the feature), not just the client
        # method — mirrors battery-care below.
        if (
            _supported(vin, "command_start_camping")
            and vehicle.get("camping_mode") is not None
        ):
            entities.append(VagCampingSwitch(coordinator, vin))
        # Škoda active ventilation (airing without heating). The backend command
        # command_start_active_ventilation lives ONLY on SkodaClient, so
        # _supported()'s hasattr() confines this to Škoda and it can never double
        # up with VagVentilationSwitch (command_start_ventilation is a SEAT/CUPRA
        # command). Top-level, not gated on has_battery: airing is a climate
        # feature on ICE/PHEV/EV. Optimistic state (Škoda never parses one).
        if _supported(vin, "command_start_active_ventilation"):
            entities.append(VagActiveVentilationSwitch(coordinator, vin))
        if vehicle.get("has_battery"):  # EV + PHEV
            if _supported(vin, "command_start_charging"):
                entities.append(VagChargingSwitch(coordinator, vin))
            if _supported(vin, "command_set_departure_timer"):
                for timer_id in (1, 2, 3):
                    entities.append(VagDepartureTimerSwitch(coordinator, vin, timer_id))
            # v2.18.0 — gate on the READ actually having produced a value, not
            # on the client having the method: every brand inherits the command
            # stub from the base client, so hasattr() is true even where it
            # raises NotImplementedError. A car that reports battery-care state
            # is a car whose backend has the feature.
            if vehicle.get("battery_care_enabled") is not None:
                entities.append(VagBatteryCareSwitch(coordinator, vin))
            # v2.31.0 — Škoda auto-unlock the charging plug when charged. Read
            # (auto_unlock_when_charged) gates it; the command maps the boolean
            # to the PERMANENT/OFF enum.
            if (
                _supported(vin, "command_set_auto_unlock_plug")
                and vehicle.get("auto_unlock_when_charged") is not None
            ):
                entities.append(VagAutoUnlockPlugSwitch(coordinator, vin))
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
        # b9 regression fix — prefer the parser-computed ``climatisation_active``
        # boolean (correct for terminal/no-data states like COMPLETED / UNKNOWN /
        # unsupported, where a raw state deny-list wrongly read "on"); fall back to
        # the state deny-list only when a channel leaves the boolean unset. Keeps
        # the switch, the climate entity and the binary sensor in agreement.
        active = self._vehicle.get("climatisation_active")
        if active is not None:
            return bool(active)
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


class VagBatteryCareSwitch(VagConnectEntity, SwitchEntity):
    """Battery-care (preservation) mode on/off.

    v2.18.0 — caps the top of the charge to spare the HV battery. The state
    has been readable since v2.10.0; this makes it settable.
    """

    _attr_translation_key = "battery_care_switch"
    _attr_icon = "mdi:battery-heart-variant"
    _command_id = "command_set_battery_care"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "battery_care_switch")

    @property
    def is_on(self) -> bool | None:
        val = self._vehicle.get("battery_care_enabled")
        return bool(val) if val is not None else None

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_set_battery_care(self._vin, True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_set_battery_care(self._vin, False)


class VagCampingSwitch(VagConnectEntity, SwitchEntity):
    """Škoda camping mode — cabin climate comfort while parked.

    v2.31.0 — the read (``camping_mode``) has shipped; this makes it settable.
    Start carries the car's default target temperature.
    """

    _attr_translation_key = "camping_switch"
    _attr_icon = "mdi:tent"
    _command_id = "command_start_camping"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "camping_switch")

    @property
    def is_on(self) -> bool | None:
        val = self._vehicle.get("camping_mode")
        return bool(val) if val is not None else None

    def _platform_attributes(self) -> dict[str, object] | None:
        # v2.31.0 — when camping mode will auto-stop (CampingModeDto.endsAt).
        # Use the _platform_attributes hook, NOT extra_state_attributes: the
        # base owns that property (merges image_url/source) and a subclass
        # override would shadow the shared attributes.
        ends = self._vehicle.get("camping_ends_at")
        return {"ends_at": ends} if ends is not None else None

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_start_camping(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_stop_camping(self._vin)


class VagAutoUnlockPlugSwitch(VagConnectEntity, SwitchEntity):
    """Auto-unlock the charging plug once the car is fully charged (Škoda).

    v2.31.0 — the read (``auto_unlock_when_charged``) has shipped; the command
    maps the boolean to the mysmob ``PERMANENT``/``OFF`` enum.
    """

    _attr_translation_key = "auto_unlock_plug_switch"
    _attr_icon = "mdi:ev-plug-type2"
    _command_id = "command_set_auto_unlock_plug"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "auto_unlock_plug_switch")

    @property
    def is_on(self) -> bool | None:
        val = self._vehicle.get("auto_unlock_when_charged")
        return bool(val) if val is not None else None

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_set_auto_unlock_plug(self._vin, True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_set_auto_unlock_plug(self._vin, False)


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


class VagActiveVentilationSwitch(VagConnectEntity, SwitchEntity):
    """Cabin active ventilation — airing without heating (Škoda + VW/Audi).

    Distinct from the SEAT/CUPRA VagVentilationSwitch: the command is
    ``command_start_active_ventilation``. On Škoda (mysmob v2 air-conditioning
    route) the read path never parses ``active_ventilation_state`` so the state
    is optimistic; on VW/Audi (v4.0.0 grounding — CARIAD-BFF
    ``activeventilation/start|stop``) the selectivestatus parser DOES surface
    ``active_ventilation_state``, so ``is_on`` reflects the real reading there.
    Both are gated by cap ``activeVentilation`` / ``ACTIVE_VENTILATION`` + the
    client owning the method (hasattr), so they never double up.
    """

    _attr_translation_key = "active_ventilation_switch"
    _attr_icon = "mdi:fan"
    _command_id = "command_start_active_ventilation"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "active_ventilation_switch")

    @property
    def is_on(self) -> bool | None:
        state = self._vehicle.get("active_ventilation_state")
        if state is None:
            return None
        return str(state).lower() not in ("off", "stopped", "invalid", "")

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_start_active_ventilation(self._vin)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_stop_active_ventilation(self._vin)


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
