# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1164 (@morpheusbdf) — remaining mappable Scout fields.

`state_ext_cond_available_*` (static per-zone climate availability) map to named
model fields so they leave the Scout and show in diagnostics — deliberately no
dedicated entities (four static flags = clutter). `tank_accuracy` folds into the
existing `fuel_level_estimated` diagnostic (0=measured / 1=calculated), reusing an
entity rather than adding one.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_ext_cond_available_zones_map_to_fields() -> None:
    d = _map({
        "state_ext_cond_available_front_left": "true",
        "state_ext_cond_available_front_right": "false",
        "state_ext_cond_available_rear_left": "true",
        "state_ext_cond_available_rear_right": "false",
    })
    assert d.climate_zone_available_front_left is True
    assert d.climate_zone_available_front_right is False
    assert d.climate_zone_available_rear_left is True
    assert d.climate_zone_available_rear_right is False


def test_tank_accuracy_folds_into_fuel_level_estimated() -> None:
    assert _map({"tank_accuracy": "1"}).fuel_level_estimated is True
    assert _map({"tank_accuracy": "0"}).fuel_level_estimated is False


def test_native_fuel_level_accuracy_still_wins_over_the_tank_alias() -> None:
    d = _map({"fuel_level__accuracy": "0", "tank_accuracy": "1"})
    assert d.fuel_level_estimated is False  # the primary key resolves first
