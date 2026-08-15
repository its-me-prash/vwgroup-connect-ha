# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1088 (ggfbrkt6mc-max, ID.Buzz) — VALID-gated HV level beats a contested SoC.

The reporter's raw EU Data Act export shipped ``battery_state_report.soc`` TWICE
(36 first/correct, 18 second/stale) — and VW stamped the STALE 18 with the NEWER
capture time, so the freshness resolver picked 18 and ``contested_fields`` never
flagged it (the two timestamps genuinely differ, so it is not a tie the reconcile
hook can catch). ``battery_level_HV`` is single-occurrence and VW marks it
VALID/INVALID; on this car it read ``value 36 / state VALID`` — the true pack SoC.
So when ``battery_level_HV.state == VALID`` we trust its value over the contested
leaf. Inert for cars that don't ship the HV pair or mark it non-VALID.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_valid_hv_level_wins_over_the_stale_contested_soc() -> None:
    """The reporter's exact case: soc leaf resolved to the stale 18, HV says 36/VALID."""
    d = _map({
        "battery_state_report.soc": "18",       # the stale value that won freshness
        "battery_level_HV.value": "36.0",
        "battery_level_HV.state": "VALID",
    })
    assert d.battery_soc == 36
    assert d.has_battery is True


def test_hv_level_recovers_soc_when_the_leaf_is_absent() -> None:
    d = _map({"battery_level_HV.value": "36.0", "battery_level_HV.state": "VALID"})
    assert d.battery_soc == 36


def test_non_valid_hv_state_falls_through_to_the_soc_leaf() -> None:
    """VW marks the HV level INVALID → do NOT trust it; the soc leaf stands."""
    d = _map({
        "battery_state_report.soc": "50",
        "battery_level_HV.value": "36.0",
        "battery_level_HV.state": "INVALID",
    })
    assert d.battery_soc == 50


def test_missing_hv_state_falls_through() -> None:
    """No explicit VALID marker → don't promote the HV value (safety)."""
    d = _map({
        "battery_state_report.soc": "50",
        "battery_level_HV.value": "36.0",
    })
    assert d.battery_soc == 50


def test_canonical_soc_without_hv_pair_is_unchanged() -> None:
    d = _map({"battery_state_report.soc": "80"})
    assert d.battery_soc == 80


def test_out_of_range_hv_value_is_ignored() -> None:
    d = _map({
        "battery_state_report.soc": "44",
        "battery_level_HV.value": "255",   # implausible → not trusted
        "battery_level_HV.state": "VALID",
    })
    assert d.battery_soc == 44


def test_valid_hv_does_not_leak_the_soc_leaf_to_the_scout() -> None:
    """#1179-1183 — a VALID HV pair used to SHORT-CIRCUIT first_freshest, so the
    co-present ``battery_state_report.soc`` leaf was never consumed and leaked to
    the Vehicle Data Scout as a "new field" every poll (six duplicate issues in a
    day). first_freshest now runs unconditionally for its consumption side effect;
    the HV value still wins the VALUE."""
    d = _map({
        "battery_state_report.soc": "18",
        "battery_level_HV.value": "36.0",
        "battery_level_HV.state": "VALID",
    })
    assert d.battery_soc == 36  # HV value still wins (#1088 unchanged)
    assert "battery_state_report.soc" not in d.raw_unmapped_fields
    assert "soc" not in d.raw_unmapped_fields


def test_valid_hv_equal_leaf_also_reclaimed() -> None:
    """Amredage's shape: HV and the leaf agree (both 79) — still must not leak."""
    d = _map({
        "battery_state_report.soc": "79",
        "battery_level_HV.value": "79",
        "battery_level_HV.state": "VALID",
    })
    assert d.battery_soc == 79
    assert "battery_state_report.soc" not in d.raw_unmapped_fields


def test_valid_hv_does_not_over_suppress_a_genuinely_new_field() -> None:
    """The reclaim must not hide unrelated unmapped fields — only the SoC aliases
    are consumed; anything else still surfaces to the Scout."""
    d = _map({
        "battery_state_report.soc": "79",
        "battery_level_HV.value": "79",
        "battery_level_HV.state": "VALID",
        "some_brand_new_leaf": "42",
    })
    assert d.raw_unmapped_fields.get("some_brand_new_leaf") == "42"
