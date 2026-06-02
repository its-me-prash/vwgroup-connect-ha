# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Device tracker (GPS) for VAG Connect.

v1.25.0 PR-C upgrades (per Audit Agent F findings):
- Dynamic listener so trackers spawn for vehicles that wake later
  (was: static setup-time filter — sleeping vehicles got no tracker
  until next full HA restart)
- Defensive (0, 0) lat/lon guard — some backends ship literal zeros
  instead of None for "no fix yet", which placed the car off the
  African coast
- Richer ``extra_state_attributes`` for Map-tooltip — parking_address,
  parking_city, last_seen_at, vehicle_state surface in Lovelace
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cariad._util import json_safe_dict, mask_vin
from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GPS device-tracker entities — one per vehicle that has GPS data.

    v1.25.0 PR-C: dynamic listener pattern (mirrors image.py since v1.24.0).
    Vehicles asleep at HA startup (no GPS in coordinator data yet) get
    their tracker spawned the moment GPS data appears in a subsequent
    coordinator update.
    """
    coordinator: VagConnectCoordinator = entry.runtime_data
    added: set[str] = set()

    def _has_gps(vehicle: dict) -> bool:
        lat = vehicle.get("latitude")
        lon = vehicle.get("longitude")
        # Defensive: explicit None check + (0, 0) guard. Some backends
        # ship literal zeros for "no fix yet" — without this guard, the
        # car appears off the African coast in HA's map.
        if lat is None or lon is None:
            return False
        if lat == 0 and lon == 0:
            return False
        return True

    def _spawn_for_new_vehicles() -> None:
        new_entities = []
        for vin, vehicle in coordinator.vehicles.items():
            if vin in added:
                continue
            if _has_gps(vehicle):
                new_entities.append(VagConnectTracker(coordinator, vin))
                added.add(vin)
        if new_entities:
            async_add_entities(new_entities)

    # Initial pass — vehicles already with GPS get trackers immediately
    _spawn_for_new_vehicles()

    # Listener pass — anything that wakes up later (was asleep at HA
    # startup, or activated mid-session via service call) gets its
    # tracker spawned on the next coordinator update.
    entry.async_on_unload(coordinator.async_add_listener(_spawn_for_new_vehicles))


class VagConnectTracker(VagConnectEntity, TrackerEntity):
    """GPS tracker entity — shows car on HA Lovelace map."""

    _attr_icon = "mdi:car"
    _attr_translation_key = "position"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "position")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Current latitude. (0, 0) treated as missing per PR-C guard."""
        lat = self._vehicle.get("latitude")
        lon = self._vehicle.get("longitude")
        if lat is None or lon is None or (lat == 0 and lon == 0):
            return None
        return float(lat) if isinstance(lat, (int, float)) else None

    @property
    def longitude(self) -> float | None:
        """Current longitude. (0, 0) treated as missing per PR-C guard."""
        lat = self._vehicle.get("latitude")
        lon = self._vehicle.get("longitude")
        if lat is None or lon is None or (lat == 0 and lon == 0):
            return None
        return float(lon) if isinstance(lon, (int, float)) else None

    @property
    def location_accuracy(self) -> int:
        return 10  # metres — typical car-GPS accuracy spec

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Surface address + state info for richer Map-tooltip.

        v1.25.0 PR-C: was empty pre-fix. Custom Lovelace cards
        (vehicle-info-card, mushroom-template-card) read these to
        display "Parked at <address>" labels next to the marker.
        """
        v = self._vehicle
        attrs: dict[str, Any] = {}
        for key in (
            "parking_address",
            "parking_city",
            "last_seen_at",
            "vehicle_state",
            "model",
            "model_year",
        ):
            val = v.get(key)
            if val is not None:
                attrs[key] = val
        # Mask VIN for privacy in any UI that displays attributes
        attrs["vin_masked"] = mask_vin(self._vin)
        # v2.2.0 PR #3 — ``last_seen_at`` is a ``datetime`` (set by
        # ``compute_connection_state``) which historically broke MQTT
        # statestream + REST API + recorder (Skoda PR #1090 bug-class).
        # ``json_safe`` recursively converts datetime → ISO 8601 string
        # so every consumer of the attribute gets a JSON-native value.
        return json_safe_dict(attrs)
