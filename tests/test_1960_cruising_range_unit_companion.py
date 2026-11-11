# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1960 — the per-point cruising-range ``.unit`` companion was unmapped.

The portal ships ``estimatedcruisingrangeprimary.unit`` (and …secondary) as a
per-point unit companion. The miles post-process only read the global
``mileage.unit`` / ``distance.unit``, so on a car that ships ONLY the
cruising-range companion the value went unconverted and the ``.unit`` leaf kept
re-surfacing to the Scout. The companion is now a second miles signal: reading it
consumes it and drives the conversion.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


def test_cruising_range_unit_companion_alone_drives_miles_conversion() -> None:
    # No global mileage.unit — only the per-point cruising-range companion says
    # MILES. Before #1960 the odometer stayed in raw (miles) numbers.
    d = _map({"mileage.value": "100", "estimatedcruisingrangeprimary.unit": "MILES"})
    assert d.odometer_km == 161  # 100 mi -> 160.934 -> 161


def test_km_companion_leaves_the_value_untouched() -> None:
    d = _map({"mileage.value": "100", "estimatedcruisingrangeprimary.unit": "KM"})
    assert d.odometer_km == 100
