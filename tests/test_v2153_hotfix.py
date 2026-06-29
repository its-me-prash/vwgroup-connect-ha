# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.3 hotfix tests.

#513 follow-up: a float-typed charging_state_error_code ("0.0") must be treated
as "no error" (the v2.15.2 sentinel only dropped the string "0"/"#0").
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_charging_error_code_zero_variants_dropped() -> None:
    assert _map({"charging_state_error_code": "0"}).charging_error_code is None
    assert _map({"charging_state_error_code": "0.0"}).charging_error_code is None
    assert _map({"charging_state_error_code": "#0"}).charging_error_code is None


def test_charging_error_code_real_errors_kept() -> None:
    assert _map({"charging_state_error_code": "2"}).charging_error_code == "2"
    assert _map({"charging_state_error_code": "#1"}).charging_error_code == "#1"
