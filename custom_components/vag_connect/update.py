# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update platform for VAG Connect — read-only vehicle-firmware status.

The car reports its installed software version and whether an over-the-air update
is available (Škoda's software-version endpoint today). This surfaces that as a
native HA ``UpdateEntity`` — the "update available / release notes" card — but
WITHOUT an Install button (``UpdateEntityFeature(0)``): VAG firmware is flashed by
the vehicle itself, not by Home Assistant.

The backend gives us a boolean "update available", not a target version string, so
``latest_version`` is synthesised: a sentinel (guaranteed to differ from installed)
when an update is available, the installed version when confirmed up to date, and
``None`` when we only know the installed version (info-only, no false "up to date").
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

# No target-version field exists in the source payload; a sentinel that differs
# from any real installed version makes HA render state ON = "update available".
# The human meaning lives in the release-notes link + the card title.
_UPDATE_AVAILABLE_SENTINEL = "update_available"

# software_update_status tokens that mean an install is running on the car
# (best-effort — reflects the vehicle's own OTA, not an HA install).
_IN_PROGRESS_STATES = frozenset({
    "installing", "in_progress", "processing", "downloading", "readytoinstall",
})


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one firmware-update entity per vehicle that reports OTA data."""
    coordinator: VagConnectCoordinator = entry.runtime_data

    def _build_for_vin(vin: str, vehicle: dict) -> list[Any]:
        # Only spawn when the car actually reports firmware/OTA data (Škoda
        # today) — otherwise the entity would sit permanently unknown.
        if (
            vehicle.get("software_version") is not None
            or vehicle.get("ota_update_available") is not None
        ):
            return [VagUpdateEntity(coordinator, vin)]
        return []

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagUpdateEntity(VagConnectEntity, UpdateEntity):
    """Read-only firmware-update status for a single vehicle."""

    _attr_translation_key = "software_update"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature(0)  # info-only, no Install

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "software_update")

    @property
    def installed_version(self) -> str | None:
        return self._vehicle.get("software_version")

    @property
    def latest_version(self) -> str | None:
        avail = self._vehicle.get("ota_update_available")
        installed = self._vehicle.get("software_version")
        if avail is True:
            return _UPDATE_AVAILABLE_SENTINEL   # differs from installed → ON
        if avail is False:
            return installed                    # confirmed up to date → OFF
        return None                             # unknown → info-only

    @property
    def release_url(self) -> str | None:
        return self._vehicle.get("ota_release_notes_url")

    @property
    def in_progress(self) -> bool:
        status = self._vehicle.get("software_update_status")
        if not isinstance(status, str):
            return False
        return status.strip().lower().replace("_", "") in {
            s.replace("_", "") for s in _IN_PROGRESS_STATES
        }
