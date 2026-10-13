# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion: a read-only sensor is not created next to the control showing it.

Switches, the charge target number and the departure timer time entities show
the same field a sensor reads, so where the control exists the sensor only
repeats it. An entry created by an earlier version is removed.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import EntityCategory

from custom_components.vag_connect import binary_sensor as bs
from custom_components.vag_connect import sensor as sn
from custom_components.vag_connect.companion.entity_twins import _TWINS, has_control_twin
from custom_components.vag_connect.const import vehicle_unique_id

VIN = "WVGZZZ1KZAW123456"
BINARY_TWINS = {key for platform, key in _TWINS if platform == "binary_sensor"}
SENSOR_TWINS = {key for platform, key in _TWINS if platform == "sensor"}


class _Client:
    pass


for _command, _battery in _TWINS.values():
    setattr(_Client, _command, None)


def _vehicle(**over):
    v = {"vin": VIN, "has_battery": True, "climatisation_state": "Off",
         "target_soc": 80, "target_temperature": 20.0, "climate_start_mode": "air_conditioning",
         "window_heating_back": False, "battery_soc": 70}
    for key in BINARY_TWINS:
        v[key] = False
    for slot in (1, 2, 3):
        v[f"departure_timer_{slot}_time"] = "07:25"
    v.update(over)
    return v


def _coordinator(*, companion=True, read_only=False, writes=True, vehicle=None):
    coord = MagicMock()
    coord.is_companion = MagicMock(return_value=companion)
    coord.is_read_only = MagicMock(return_value=read_only)
    coord.command_capability_supported = MagicMock(return_value=None)
    coord.command_method_available = MagicMock(return_value=writes)
    coord.read_capability_hidden = MagicMock(return_value=False)
    coord._cariad_client = _Client()
    coord.vehicles = coord.data = {VIN: vehicle or _vehicle()}
    return coord


def _added(platform, coord, registry=None):
    entry = MagicMock()
    entry.runtime_data = coord
    entry.data = {"brand": "volkswagen"}
    entry.options = {}
    added: list = []
    registry = registry or MagicMock(async_get_entity_id=MagicMock(return_value=None))
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
        asyncio.run(platform.async_setup_entry(
            MagicMock(), entry, lambda e, **_k: added.extend(e),
        ))
    return {
        getattr(getattr(e, "entity_description", None), "key", None): e for e in added
    }


def test_the_binary_twins_are_not_created_where_the_control_exists():
    keys = _added(bs, _coordinator())
    assert not keys.keys() & BINARY_TWINS
    assert "window_heating_back" in keys  # no switch for it: still a sensor


def test_the_sensor_twins_are_not_created_where_the_control_exists():
    keys = _added(sn, _coordinator())
    assert not keys.keys() & SENSOR_TWINS
    assert "battery_soc" in keys


@pytest.mark.parametrize("coord_kw", [
    {"companion": False}, {"read_only": True}, {"writes": False},
])
def test_without_the_control_the_sensor_stays(coord_kw):
    assert BINARY_TWINS <= _added(bs, _coordinator(**coord_kw)).keys()
    assert SENSOR_TWINS <= _added(sn, _coordinator(**coord_kw)).keys()


def test_battery_controls_need_a_battery():
    coord = _coordinator()
    plain = _vehicle(has_battery=False)
    assert not has_control_twin(coord, VIN, plain, "binary_sensor", "is_charging")
    assert not has_control_twin(coord, VIN, plain, "sensor", "departure_timer_1_time")
    assert has_control_twin(coord, VIN, plain, "binary_sensor", "climatisation_active")


def test_an_entry_from_an_earlier_version_is_removed():
    registry = MagicMock()
    registry.async_get_entity_id = MagicMock(
        side_effect=lambda domain, platform, uid: (
            "binary_sensor.tiguan_adb_climate_at_unlock"
            if uid == vehicle_unique_id(VIN, "climate_at_unlock", companion=True) else None
        )
    )
    _added(bs, _coordinator(), registry)
    registry.async_remove.assert_called_once_with("binary_sensor.tiguan_adb_climate_at_unlock")


def test_the_read_of_a_held_value_is_a_diagnostic():
    keys = _added(sn, _coordinator())
    assert keys["target_temperature"].entity_description.entity_category is EntityCategory.DIAGNOSTIC
    # The start mode is the climate entity's preset now: no sensor for it.
    assert "climate_start_mode" not in keys
    other = _added(sn, _coordinator(companion=False))
    assert other["target_temperature"].entity_description.entity_category is None
