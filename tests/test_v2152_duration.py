# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.2 (#511 Ra72xx) — EU portal sends charging/climate durations as
seconds with a trailing ``s`` (``"2400s"`` = 40 min). v2.15.1 read them as a
plain number and left the sensors empty; they now convert ``Ns`` → minutes,
while a bare number is still treated as already-minutes (older firmwares).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _dur_to_min,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def test_seconds_suffix_to_minutes() -> None:
    assert _dur_to_min("2400s") == 40
    assert _dur_to_min("300s") == 5
    assert _dur_to_min("0s") == 0


def test_bare_number_stays_minutes() -> None:
    assert _dur_to_min("40") == 40
    assert _dur_to_min(None) is None
    assert _dur_to_min("") is None


def test_portal_remaining_times_parse_from_seconds() -> None:
    payload = [
        {"dataFieldName": "battery_state_report.remaining_charging_time_complete",
         "value": "2400s"},
        {"dataFieldName": "battery_state_report.remaining_charging_time_bulk",
         "value": "300s"},
        {"dataFieldName": "remaining_climate_time", "value": "0s"},
    ]
    d = map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))
    assert d.remaining_charge_time_min == 40
    assert d.remaining_charge_time_bulk_min == 5
    assert d.climate_remaining_time_min == 0
