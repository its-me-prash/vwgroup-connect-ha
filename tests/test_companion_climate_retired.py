# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion: the climate entity replaces the climate switches, the start mode
select and sensor and the desired temperature number. Cloud entries keep them."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from custom_components.vag_connect import number as number_mod
from custom_components.vag_connect import select as select_mod
from custom_components.vag_connect import sensor as sensor_mod
from custom_components.vag_connect import switch as switch_mod
from custom_components.vag_connect.companion.client import CompanionClient
from custom_components.vag_connect.companion.entity_twins import RETIRED_COMPANION_CLIMATE
from custom_components.vag_connect.const import DOMAIN, vehicle_unique_id

VIN = "WVWZZZTESTVIN0001"
VEHICLE = {
    "vin": VIN, "has_battery": True, "climatisation_active": False,
    "window_heating_front": False, "target_temperature": 21.0,
    "climate_start_mode": "air_conditioning", "battery_soc": 70,
}
RETIRED_CLASSES = {
    "VagClimatisationSwitch", "VagWindowHeatingSwitch",
    "VagCompanionClimateModeSelect", "VagCompanionClimateTemperatureNumber",
}


class _CloudClient:
    async def command_start_climate(self, *_a, **_k): ...
    async def command_stop_climate(self, *_a, **_k): ...
    async def command_start_window_heating(self, *_a, **_k): ...
    async def command_stop_window_heating(self, *_a, **_k): ...
    async def command_set_climate_temperature(self, *_a, **_k): ...


def _companion_client() -> CompanionClient:
    client = CompanionClient.__new__(CompanionClient)
    client._brand = "volkswagen"
    return client


def _coord(*, companion: bool):
    coord = MagicMock()
    coord.is_companion = MagicMock(return_value=companion)
    coord.is_read_only = MagicMock(return_value=False)
    coord.command_capability_supported = MagicMock(return_value=None)
    coord.command_method_available = MagicMock(return_value=True)
    coord.read_capability_hidden = MagicMock(return_value=False)
    coord._cariad_client = _companion_client() if companion else _CloudClient()
    coord.vehicles = coord.data = {VIN: dict(VEHICLE)}
    return coord


class _Registry:
    """Holds the five retired companion entries until they are removed."""

    def __init__(self) -> None:
        self.ids = {
            (platform, vehicle_unique_id(VIN, key, companion=True)): f"{platform}.{key}"
            for platform, key in RETIRED_COMPANION_CLIMATE
        }
        self.removed: set[str] = set()

    def async_get_entity_id(self, platform, domain, uid):
        assert domain == DOMAIN
        eid = self.ids.get((platform, uid))
        return None if eid in self.removed else eid

    def async_remove(self, entity_id):
        self.removed.add(entity_id)


def _build(companion: bool, registry: _Registry | None = None) -> list:
    coord = _coord(companion=companion)
    entry = MagicMock()
    entry.runtime_data = coord
    entry.data = {"brand": "volkswagen"}
    entry.options = {}
    built: list = []

    def spawner(_entry, _coord, _add, build):
        built.extend(build(VIN, dict(VEHICLE)))

    with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry or _Registry()):
        for mod in (switch_mod, select_mod, number_mod, sensor_mod):
            with patch.object(mod, "register_dynamic_spawner", spawner, create=True), \
                    patch.object(number_mod, "_companion_can_sync", return_value=False):
                asyncio.run(mod.async_setup_entry(
                    MagicMock(), entry, lambda e, **_k: built.extend(e),
                ))
    return built


def _keys(built: list) -> set:
    return {getattr(getattr(e, "entity_description", None), "key", None) for e in built}


def test_companion_entry_builds_none_of_the_retired():
    built = _build(True)
    assert not {type(e).__name__ for e in built} & RETIRED_CLASSES
    assert "climate_start_mode" not in _keys(
        [e for e in built if type(e).__module__.endswith(".sensor")]
    )


def test_cloud_entry_keeps_its_switches():
    names = {type(e).__name__ for e in _build(False)}
    assert {"VagClimatisationSwitch", "VagWindowHeatingSwitch"} <= names


def test_registry_entries_of_the_retired_are_removed():
    registry = _Registry()
    _build(True, registry)
    assert registry.removed == set(registry.ids.values())


def test_cloud_entry_removes_nothing():
    registry = _Registry()
    _build(False, registry)
    assert registry.removed == set()


@pytest.mark.parametrize("key", ["climate_zone_front_left_switch", "climate_zone_front_right_switch"])
def test_zone_switches_are_controls(key):
    assert key in switch_mod._COMPANION_CLIMATE_CONTROL_KEYS
