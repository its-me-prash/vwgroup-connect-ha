# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.1 (#465 RaAdNe) — flat-log snapshot dedup by car_captured_time.

The EU Data Act portal ships an ordered flat event-log; each snapshot's capture
time arrives as its OWN ``car_captured_time`` data-point (not a sibling key). A
field repeated across snapshots — RaAdNe's ``settings.target_soc`` = 100 at
15:35, then 80 at 18:27 after battery-care lowered it — must resolve to the
LATEST snapshot's value (80), which the car and the app actually show. Before the
fix the values tied on the dataset floor and first-seen (the stale 100) won.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# RaAdNe's reported portal payload (trimmed to the relevant data-points).
_PAYLOAD = [
    {"key": "k1", "dataFieldName": "car_captured_time", "value": "2026-06-24T15:35:53Z"},
    {"key": "k2", "dataFieldName": "settings.target_soc", "value": "100"},
    {"key": "k3", "dataFieldName": "timestamp", "value": "2026-06-24T18:59:58.903Z"},
    {"key": "k4", "dataFieldName": "car_captured_time", "value": "2026-06-24T18:27:26Z"},
    {"key": "k5", "dataFieldName": "settings.target_soc", "value": "80"},
]


def test_flat_log_target_soc_picks_latest_snapshot() -> None:
    assert _walk_fields(_PAYLOAD)["settings.target_soc"] == "80"


def test_flat_log_target_soc_maps_to_vehicle_data() -> None:
    d = map_dataset_to_vehicle_data(_walk_fields(_PAYLOAD), VehicleData(vin="X"))
    assert d.target_soc == 80


def test_latest_capture_time_wins_regardless_of_list_order() -> None:
    # The 80% block is FIRST in the list but carries the LATER capture time;
    # the 100% block is later in the list with an EARLIER capture time. The
    # value must be chosen by car_captured_time, not list position.
    payload = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:27:26Z"},
        {"dataFieldName": "settings.target_soc", "value": "80"},
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T15:35:53Z"},
        {"dataFieldName": "settings.target_soc", "value": "100"},
    ]
    assert _walk_fields(payload)["settings.target_soc"] == "80"
