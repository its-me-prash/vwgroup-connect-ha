# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Lock platform for VAG Connect — proper HA LockEntity for door lock/unlock."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
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
    """Set up lock entities. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.12.0 (#63) — Read-only Mode: lock entity sends commands, skip
    # entity creation entirely when the user enabled the option.
    if coordinator.is_read_only():
        return

    def _build_for_vin(vin: str, vehicle: dict) -> list:  # noqa: ARG001
        # v1.13.0 (#56 Phase 3) — capability-filter PRE entity creation.
        # ``False`` only when backend explicitly reports lock capability
        # missing/limited; ``None`` (unknown) keeps the entity (Phase 2
        # catches at runtime via classify_command_failure).
        if coordinator.command_capability_supported(vin, "command_lock") is False:
            return []
        return [VagDoorLock(coordinator, vin)]

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagDoorLock(VagConnectEntity, LockEntity):
    """Vehicle door lock — uses HA's native LockEntity."""

    _attr_translation_key = "door_lock"
    # v1.9.1 — Phase 2 gating. If a previous lock/unlock attempt was
    # rejected as missing-capability or not-entitled, the entity goes
    # unavailable instead of throwing 403/400 on every press.
    _command_id = "command_lock"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "door_lock")

    @property
    def is_locked(self) -> bool | None:
        return self._vehicle.get("doors_locked")

    async def async_lock(self, **kwargs: object) -> None:
        await self.coordinator.async_lock(self._vin)

    async def async_unlock(self, **kwargs: object) -> None:
        await self.coordinator.async_unlock(self._vin)
