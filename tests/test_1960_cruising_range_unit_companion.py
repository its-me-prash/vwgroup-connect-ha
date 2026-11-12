# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1960 — the per-point cruising-range ``.unit`` companion is a DISPLAY
preference, not the unit of the feed value.

The portal ships ``estimatedcruisingrangeprimary.unit`` (and …secondary) as a
per-point unit companion. 5.3.0 added it as a second, car-wide miles trigger —
but @cookp0's Audi Q4 e-tron (EU portal) demonstrated the companion reflects the
unit the car DISPLAYS (his myAudi app is set to miles) while the feed delivers
the odometer and range in kilometres. Using the companion as a miles trigger
therefore multiplied a correct, already-km odometer by 1.60934 (a ~1.6x error),
regressing every such car relative to 5.2.5.

So the companion is still CONSUMED here (the Scout stops re-filing it), but it no
longer drives conversion: only the global ``mileage.unit`` / ``range.unit`` /
``distance.unit`` companions do, as before 5.3.0.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


def test_cruising_range_companion_does_not_scale_the_odometer() -> None:
    # #1960 regression (@cookp0, Audi Q4 e-tron): the ONLY distance-unit signal
    # is the per-point cruising-range companion, which says MILES because the app
    # displays miles — but the feed value is kilometres. It must NOT be scaled.
    d = _map({"mileage.value": "100", "estimatedcruisingrangeprimary.unit": "MILES"})
    assert d.odometer_km == 100


def test_global_mileage_unit_still_drives_conversion() -> None:
    # The global companion remains trusted (pre-5.3.0 behaviour, unchanged).
    d = _map({"mileage.value": "100", "mileage.unit": "MILES"})
    assert d.odometer_km == 161  # 100 mi -> 160.934 -> 161


def test_km_companion_leaves_the_value_untouched() -> None:
    d = _map({"mileage.value": "100", "estimatedcruisingrangeprimary.unit": "KM"})
    assert d.odometer_km == 100


def test_cruising_range_companions_are_still_consumed_for_the_scout() -> None:
    # #1960's valid half: the companion must leave raw_unmapped_fields so the
    # Scout stops re-filing it on every poll — even though it no longer converts.
    d = _map(
        {
            "mileage.value": "100",
            "estimatedcruisingrangeprimary.unit": "MILES",
            "estimatedcruisingrangesecondary.unit": "MILES",
        }
    )
    assert "estimatedcruisingrangeprimary.unit" not in d.raw_unmapped_fields
    assert "estimatedcruisingrangesecondary.unit" not in d.raw_unmapped_fields
