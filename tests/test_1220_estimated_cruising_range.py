# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1220 (CUPRA Raval, new platform) — the primary/secondary cruising range under
the OFFICIAL EU Data Act dict leaf ``estimatedcruisingrange{primary,secondary}
(.value)`` is now consumed. Before, the chain never read it, so on the Raval the
range value dropped silently and only ``.is_set`` reached the Vehicle Data Scout.
Added as a LAST-RESORT named source, so cars shipping the canonical spellings are
unchanged.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_estimated_primary_range_surfaces_when_canonical_absent() -> None:
    d = _map({"estimatedcruisingrangeprimary.value": "312", "engine_type": "ELECTRIC"})
    assert d.range_km == 312
    assert d.electric_range_km == 312


def test_canonical_range_still_wins_over_estimated() -> None:
    """The estimated leaf is last-resort: a car shipping both keeps the canonical."""
    d = _map({
        "cruising_range_primary_engine": "300",
        "estimatedcruisingrangeprimary.value": "999",
        "engine_type": "ELECTRIC",
    })
    assert d.electric_range_km == 300


def test_estimated_secondary_range_on_a_phev() -> None:
    d = _map({
        "estimatedcruisingrangeprimary.value": "40",
        "estimatedcruisingrangesecondary.value": "500",
        "engine_type": "PETROL",
        "fuel_level": "60",
    })
    assert d.combustion_range_km == 40   # primary == combustion on a PHEV
    assert d.electric_range_km == 500    # secondary == electric


def test_no_estimated_leaf_is_inert() -> None:
    d = _map({"cruising_range_primary_engine": "250", "engine_type": "ELECTRIC"})
    assert d.electric_range_km == 250
