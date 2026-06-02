# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Button entities for VAG Connect (flash lights, force refresh, wake)."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

# v1.13.0 (#56 Phase 3) — capability filtering moved to coordinator's
# ``command_capability_supported(vin, command_id)`` helper, which uses
# the per-brand mapping in ``cariad/_capabilities.py``. This replaces
# the brand-allowlist + cap-id-string approach below.
#
# Phase 2 (v1.9.1) brand-allowlist (now superseded but kept for reference):
#   Pre-1.13.0 only SEAT/CUPRA were gated because we had verified their
#   OLA capability vocabulary. v1.13.0 ships verified vocabularies for
#   VW EU + Audi + Skoda (via the new Skoda capabilities endpoint) so
#   the allowlist becomes the implicit "any brand with a registered
#   command-id mapping in CAPABILITY_MAP".


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.12.0 (#63) — Read-only Mode: skip vehicle-command buttons
    # (Flash, Wake) but ALWAYS keep VagRefreshButton — refresh is a
    # coordinator-level cloud poll, doesn't send any vehicle command.
    read_only = coordinator.is_read_only()

    def _build_for_vin(vin: str, vehicle: dict) -> list:  # noqa: ARG001
        entities: list = []
        # Refresh button never gates — coordinator-level operation.
        entities.append(VagRefreshButton(coordinator, vin))
        if read_only:
            return entities
        if coordinator.command_capability_supported(vin, "command_flash") is not False:
            entities.append(VagFlashButton(coordinator, vin))
        if coordinator.command_capability_supported(vin, "command_wake") is not False:
            entities.append(VagWakeButton(coordinator, vin))
        return entities

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagFlashButton(VagConnectEntity, ButtonEntity):
    """Trigger a honk-and-flash sequence."""

    _attr_translation_key = "flash_button"
    _attr_icon = "mdi:car-light-high"
    # v1.9.1 — Phase 2 gating: hide once a 403/missing-capability is seen.
    _command_id = "command_flash"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "flash_button")

    async def async_press(self) -> None:
        await self.coordinator.async_flash_lights(self._vin)


class VagRefreshButton(VagConnectEntity, ButtonEntity):
    """Force an immediate data refresh from the cloud."""

    _attr_translation_key = "refresh_button"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "refresh_button")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class VagWakeButton(VagConnectEntity, ButtonEntity):
    """Wake the vehicle from sleep."""

    _attr_translation_key = "wake_button"
    _attr_icon = "mdi:car-connected"
    # v1.9.1 — Phase 2 gating.
    _command_id = "command_wake"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "wake_button")

    async def async_press(self) -> None:
        await self.coordinator.async_wake_vehicle(self._vin)
