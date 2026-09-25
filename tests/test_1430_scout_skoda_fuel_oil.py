# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1430 (Vehicle Data Scout, Škoda Octavia) — two new EU Data Act portal leaves.

``fuelLevel`` is the Škoda EU-portal tank-percent leaf and ``inspectionOilDistance``
the distance until the next oil service. Both map onto the existing fuel_level /
oil_service_km sensors (fill-if-empty; no new entities), so the Scout stops
re-reporting them as undiscovered.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(points: list[dict]) -> VehicleData:
    fields = _walk_fields({"data": points})
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_skoda_fuel_level_leaf_is_parsed() -> None:
    d = _map([{"dataFieldName": "fuelLevel", "value": "16", "key": "k"}])
    assert d.fuel_level == 16


def test_skoda_inspection_oil_distance_leaf_is_parsed() -> None:
    d = _map([{"dataFieldName": "inspectionOilDistance", "value": "19000", "key": "k"}])
    assert d.oil_service_km == 19000


def test_oil_service_km_is_fill_if_empty() -> None:
    # oil_service_km only fills when empty, so a brand-native value is preserved
    base = VehicleData(vin="X")
    base.oil_service_km = 5000
    fields = _walk_fields({"data": [{"dataFieldName": "inspectionOilDistance", "value": "19000", "key": "k"}]})
    d = map_dataset_to_vehicle_data(fields, base)
    assert d.oil_service_km == 5000  # native value preserved
