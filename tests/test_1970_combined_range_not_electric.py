# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1970 (@martinbos, Audi Q3 PHEV) — the portal ships only a COMBINED cruising
range (UUID 153e8c40, catalogue "cruising_range_combined"). On a PHEV that also
reports a fuel level and a real HV SoC, that combined figure (150 km = ~34
electric + ~116 petrol) landed on electric_range_km. The #1316 final screen
cannot clean it: a real SoC is electric evidence, so that screen stays inert on
any plug-in.

The fix keys off the SOURCE, not engine_type: when electric_range_km came from
the combined-range leaf AND the car has fuel (a PHEV, so combined != electric),
it is not the EV range; clear the phantom (range_km already carries the figure).

Soll-values from the issue (34 electric / ~116 petrol / ~150 combined) and the
dictionary (153e8c40 = combined). The regression guards below encode two
adversarial review findings (gpt-oss + Gemini via agy): a legit-electric PHEV
must survive, and a combustion-only car must keep the #1316 screen's handoff to
combustion_range_km.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


_COMBINED = "153e8c40-4c6c-3c17-a11b-0ecc35d55b81"   # "cruising_range_combined"
_PRIMARY = "0ca40e18-0564-3eda-bcc0-7aee9ef44f04"    # "Value of the primary range"


def test_q3_phev_combined_on_electric_is_cleared() -> None:
    """martinbos's case. FAILS BEFORE THE FIX: electric_range_km == 150."""
    d = _map({_COMBINED: "150", "fuel_level": "40", "battery_level_HV.value": "50"})
    assert d.battery_soc == 50          # the PHEV shape that keeps #1316 inert
    assert d.electric_range_km is None  # phantom cleared
    assert d.range_km == 150            # the combined figure stays honest here


def test_combined_source_cleared_even_with_an_electric_engine_type() -> None:
    """Gemini finding #2: the discriminator must be the SOURCE, not engine_type.
    A PHEV that names an ELECTRIC engine_type but ships only the combined UUID
    still had the bug. FAILS BEFORE THE FIX: electric_range_km == 150."""
    d = _map({
        _COMBINED: "150",
        "engine_type": "ENGINE_TYPE_HYBRID_ELECTRIC",
        "fuel_level": "40",
        "battery_level_HV.value": "50",
    })
    assert d.electric_range_km is None


def test_a_legit_electric_phev_range_survives() -> None:
    """gpt-oss finding: a PHEV whose PRIMARY range IS the electric range (source
    0ca40e18 / a named leaf, not the combined UUID) must NOT be zeroed."""
    d = _map({_PRIMARY: "48", "fuel_level": "55", "battery_level_HV.value": "50"})
    assert d.electric_range_km == 48


def test_a_combustion_only_car_keeps_its_combustion_range() -> None:
    """Gemini finding #1: a pure-combustion car (no engine_type, no SoC) relies on
    the #1316 screen to move the range to combustion_range_km. The fix must run
    AFTER that screen so the handoff is not starved."""
    d = _map({_PRIMARY: "500", "fuel_level": "40"})
    assert d.combustion_range_km == 500
    assert d.electric_range_km is None


def test_a_pure_bev_still_gets_its_electric_range() -> None:
    """No fuel => pure BEV => combined == electric => keep it (unchanged)."""
    d = _map({_COMBINED: "211"})
    assert d.electric_range_km == 211


def test_combustion_primary_phev_with_secondary_is_unchanged() -> None:
    """#555/#565 GTE: a separate secondary range => combustion primary, electric
    secondary. Source is the secondary leaf, not the combined UUID => untouched."""
    d = _map({
        "cruising_range_primary_engine": "380",
        "cruising_range_secondary_engine": "20",
        "fuel_level": "60",
    })
    assert d.combustion_range_km == 380
    assert d.electric_range_km == 20
