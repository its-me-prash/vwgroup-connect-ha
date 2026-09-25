# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-25 (#1492, VW Touareg eHybrid) — a car reported climate fields
outside the MEB dialect batch: climatisation_state="error" (+ an error code),
a climatise reason trigger, and an undocumented cycle mileage.

- climatisation_state="error" surfaces as ERROR but must NOT read as active.
- climatisation_state_error_code feeds the existing climate_error_code sensor.
- climatisation_reason_trigger feeds the new climatisation_reason field.
- cycle_data_mileage is HELD (undocumented unit) — stays Scout-visible.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(payload: dict) -> VehicleData:
    syn: dict = {}
    return map_dataset_to_vehicle_data(_walk_fields(payload, None, syn), VehicleData(vin="X"), field_syn=syn)


def test_climatisation_state_error_is_not_active() -> None:
    d = _map({"climatisation_state": "error"})
    assert d.climatisation_state == "ERROR"
    assert d.climatisation_active is False


def test_error_state_active_derivation_unchanged_for_normal_states() -> None:
    assert _map({"climatisation_state": "CLIMATISATION_STATE_HEATING"}).climatisation_active is True
    assert _map({"climatisation_state": "CLIMATISATION_STATE_OFF"}).climatisation_active is False


def test_climatisation_state_error_code_maps_to_climate_error_code() -> None:
    d = _map({"climatisation_state_error_code": "10"})
    assert d.climate_error_code == "10"


def test_error_code_zero_sentinel_is_dropped() -> None:
    # "0" is the no-error sentinel (same as the existing climate_error_code path).
    assert _map({"climatisation_state_error_code": "0"}).climate_error_code is None


def test_climatisation_reason_trigger_maps() -> None:
    d = _map({"climatisation_reason_trigger": "immediate"})
    assert d.climatisation_reason == "IMMEDIATE"


def test_cycle_data_mileage_is_held_visible() -> None:
    # Undocumented unit → intentionally not mapped; stays on the Scout surface.
    d = _map({"cycle_data_mileage": "784"})
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert "cycle_data_mileage" in leaves


def test_full_1492_payload() -> None:
    d = _map({
        "climatisation_state": "error",
        "climatisation_state_error_code": "10",
        "climatisation_reason_trigger": "immediate",
        "cycle_data_mileage": "784",
    })
    assert d.climatisation_state == "ERROR"
    assert d.climatisation_active is False
    assert d.climate_error_code == "10"
    assert d.climatisation_reason == "IMMEDIATE"
