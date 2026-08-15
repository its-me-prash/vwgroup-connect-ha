# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1202 (CUPRA Raval) — map the SEAT/CUPRA `remaining_time_finished` value+unit
pair to the remaining-charge-time sensor.

The Raval ships the time-until-charging-finishes as a number plus a separate
`TIME_UNIT_*` enum (dict UUIDs 0901e6d5… / 6f7f6a6d…), unlike the `"2400s"` form
other cars use. It's wired as a LAST fallback (never out-competes a canonical
`remaining_charging_time`), and BOTH leaves are consumed so they stop surfacing
to the Vehicle Data Scout.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_VAL = "remaining_time_finished.remaining_time_finished_value"
_UNIT = "remaining_time_finished.remaining_time_finished_unit"


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_minutes_pass_through() -> None:
    assert _map({_VAL: "45", _UNIT: "TIME_UNIT_MINUTES"}).remaining_charge_time_min == 45


def test_seconds_convert_to_minutes() -> None:
    assert _map({_VAL: "2400", _UNIT: "TIME_UNIT_SECONDS"}).remaining_charge_time_min == 40


def test_hours_convert_to_minutes() -> None:
    assert _map({_VAL: "2", _UNIT: "TIME_UNIT_HOURS"}).remaining_charge_time_min == 120


def test_undefined_unit_treated_as_minutes() -> None:
    assert _map({_VAL: "30", _UNIT: "TIME_UNIT_UNDEFINED"}).remaining_charge_time_min == 30
    assert _map({_VAL: "20"}).remaining_charge_time_min == 20  # unit absent → minutes


def test_zero_means_done() -> None:
    assert _map({_VAL: "0", _UNIT: "TIME_UNIT_MINUTES"}).remaining_charge_time_min == 0


def test_canonical_source_still_wins() -> None:
    d = _map({"remaining_charging_time": "30", _VAL: "99", _UNIT: "TIME_UNIT_MINUTES"})
    assert d.remaining_charge_time_min == 30  # canonical wins, not the 99 fallback


def test_both_leaves_leave_the_scout() -> None:
    """Consumed unconditionally — even when a canonical source set the value —
    so neither leaf re-surfaces to the Scout (the first()-consume trap)."""
    d = _map({"remaining_charging_time": "30", _VAL: "99", _UNIT: "TIME_UNIT_MINUTES"})
    assert not any("remaining_time_finished" in k for k in d.raw_unmapped_fields)
    d2 = _map({_VAL: "45", _UNIT: "TIME_UNIT_MINUTES"})
    assert not any("remaining_time_finished" in k for k in d2.raw_unmapped_fields)
