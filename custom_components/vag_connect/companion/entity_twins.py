# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion: read-only entities that repeat the control next to them.

A companion switch, number or time entity shows the very field a read-only
sensor of the same vehicle reads. Where that control exists the sensor only
repeats it, so it is not created, and an entry left by an earlier version is
removed. Without the control (Read-only Mode, a command the preset does not
map, other entries) the sensor stays.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# (entity platform, sensor key) → (command of the control, needs a battery):
# the control is created only on a car with a traction battery when set.
_TWINS: dict[tuple[str, str], tuple[str, bool]] = {
    # Air Conditioning Settings switches.
    ("binary_sensor", "climate_at_unlock"): ("command_set_climate_at_unlock", False),
    ("binary_sensor", "window_heating_enabled"): ("command_set_window_heating_auto", False),
    ("binary_sensor", "climate_zone_front_left"): ("command_set_climate_zone_front_left", False),
    ("binary_sensor", "climate_zone_front_right"): (
        "command_set_climate_zone_front_right", False,
    ),
    # Window heating and climate running state (the climate entity shows the same).
    ("binary_sensor", "window_heating_front"): ("command_start_window_heating", False),
    ("binary_sensor", "climatisation_active"): ("command_start_climate", False),
    ("sensor", "climatisation_state"): ("command_start_climate", False),
    # Charging switch and charge target number.
    ("binary_sensor", "is_charging"): ("command_start_charging", True),
    ("sensor", "target_soc"): ("command_set_target_soc", True),
    # Departure timer switches and time entities.
    **{
        ("binary_sensor", f"departure_timer_{slot}_enabled"): (
            "command_set_departure_timer", True,
        )
        for slot in (1, 2, 3)
    },
    **{
        ("sensor", f"departure_timer_{slot}_time"): ("command_set_departure_timer", True)
        for slot in (1, 2, 3)
    },
}


# Diagnostics of the cloud clients that a companion entry never fills: the
# push event stream, the cloud API field observer and the cloud wake counter.
_CLOUD_ONLY: frozenset[tuple[str, str]] = frozenset({
    ("event", "push_event"),
    ("sensor", "api_observer_findings"),
    ("sensor", "wake_count_today"),
})


# Climate entities the Companion's climate entity replaced: the climate and
# window heating switches, the start mode select and sensor, and the desired
# temperature number. Not created on a Companion entry, and an entry left by
# an earlier version is removed.
RETIRED_COMPANION_CLIMATE: frozenset[tuple[str, str]] = frozenset({
    ("switch", "climatisation_switch"),
    ("switch", "window_heating_switch"),
    ("select", "companion_climate_start_mode"),
    ("number", "target_temperature"),
    ("sensor", "climate_start_mode"),
})


def is_cloud_only(coordinator: Any, platform: str, key: str) -> bool:
    """True for a cloud-client diagnostic on a companion entry, which stays empty."""
    return (platform, key) in _CLOUD_ONLY and bool(coordinator.is_companion())


def has_control_twin(
    coordinator: Any, vin: str, vehicle: dict, platform: str, key: str,
) -> bool:
    """True when a companion control shows this sensor's field (same gates)."""
    twin = _TWINS.get((platform, key))
    if twin is None or not coordinator.is_companion() or coordinator.is_read_only():
        return False
    command, needs_battery = twin
    if needs_battery and not vehicle.get("has_battery"):
        return False
    client = coordinator._cariad_client
    return bool(
        coordinator.command_capability_supported(vin, command) is not False
        and client is not None
        and hasattr(client, command)
        and coordinator.command_method_available(command)
    )


def remove_twin(hass: HomeAssistant, platform: str, vin: str, key: str) -> None:
    """Drop the registry entry an earlier version created for this entity."""
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    from ..const import DOMAIN, vehicle_unique_id  # noqa: PLC0415

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        platform, DOMAIN, vehicle_unique_id(vin, key, companion=True),
    )
    if entity_id is not None:
        registry.async_remove(entity_id)


def drop_retired_climate(hass: HomeAssistant, coordinator: Any, platform: str, vin: str) -> None:
    """Companion: remove the registry entries of the entities the climate entity replaced."""
    if not coordinator.is_companion():
        return
    for plat, key in RETIRED_COMPANION_CLIMATE:
        if plat == platform:
            remove_twin(hass, plat, vin, key)
