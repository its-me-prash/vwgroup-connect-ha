# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.25.0 — a sentinel on a MAPPED field is consumed, not re-reported forever.

A field ``first()`` is asked for is, by definition, mapped (only mapped names
are ever passed to it). A sentinel value on such a field means "this mapped
field has no current reading", NOT "an undiscovered field". The pre-2.25.0
behaviour skipped the sentinel WITHOUT consuming it, so every mapped field
whose car was sending a sentinel re-filed a Scout report on every single poll —
that is what kept #958/#969/#970 (tyre pressure "1"=invalid) coming back.

This is the same class as the v2.24.2 value_type reclaim. The fix consumes the
sentinel so it stops re-surfacing; the sensor stays unavailable until a real
value arrives, at which point it maps normally.

The no-suppression policy is preserved for GENUINELY-NEW fields: an unmapped
field never reaches ``first()``, so a sentinel-shaped value on an unknown field
still surfaces in raw_unmapped_fields for discovery. That invariant is the last
test here and is the one that must never regress.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        map_dataset_to_vehicle_data,
    )
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_mapped_field_sentinel_is_consumed() -> None:
    # tyre pressure "1" = invalid: mapped target stays None, and the field is
    # gone from the Scout surface.
    d = _map({"tyre_pressure_actual_front_left": "1"})
    assert d.tyre_pressure_actual_fl is None
    assert "tyre_pressure_actual_front_left" not in d.raw_unmapped_fields


def test_mapped_field_real_value_still_maps() -> None:
    d = _map({"tyre_pressure_actual_front_left": "230"})
    assert d.tyre_pressure_actual_fl == 230
    assert "tyre_pressure_actual_front_left" not in d.raw_unmapped_fields


def test_all_wheels_sentinel_all_consumed() -> None:
    # the exact #958/#970 shape: every wheel reporting the invalid sentinel
    payload = {
        "tyre_pressure_actual_front_left": "1",
        "tyre_pressure_actual_front_right": "1",
        "tyre_pressure_actual_rear_left": "1",
        "tyre_pressure_actual_rear_right": "1",
        "tyre_pressure_actual_spare_tyre": "1",
    }
    d = _map(payload)
    for name in payload:
        assert name not in d.raw_unmapped_fields, f"{name} still re-reports"


def test_sentinel_synonyms_are_consumed_too() -> None:
    # both the bare and container-qualified spellings of a sentinel'd mapped
    # field must be consumed, or the twin keeps re-reporting.
    d = _map({
        "battery_state_report.remaining_charging_time_bulk": "-1",
        "remaining_charging_time_bulk": "-1",
    })
    assert d.remaining_charge_time_bulk_min is None
    raw = d.raw_unmapped_fields
    assert "battery_state_report.remaining_charging_time_bulk" not in raw
    assert "remaining_charging_time_bulk" not in raw


def test_UNMAPPED_field_sentinel_stays_scout_visible() -> None:
    # THE POLICY GUARD. A field the parser does not know (never passed to
    # first()) must keep surfacing for discovery, even with a sentinel-shaped
    # value — otherwise the fix would suppress genuinely-new fields.
    d = _map({"some_brand_new_unknown_field": "65535"})
    assert "some_brand_new_unknown_field" in d.raw_unmapped_fields
