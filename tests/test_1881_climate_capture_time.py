# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1881 — the portal's climate state had no capture time of its own.

``climatisation_state`` was read without ``record_as``, so ``field_captured_ts``
never held an entry for it, even when the dataset leaf carried its own
timestamp. Recording it changes no value and no gating; it only lets a
diagnostics dump show how old the climate reading is.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _point(name: str, value: str, ts: str | None = None) -> dict:
    p: dict = {"dataFieldName": name, "value": value}
    if ts:
        p["timestampUtc"] = ts
    return p


def _map(payload: dict) -> VehicleData:
    ts: dict = {}
    syn: dict = {}
    flat = _walk_fields(payload, ts, syn)
    return map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), ts, syn)


def test_the_state_carries_its_own_capture_time() -> None:
    d = _map({"data": [
        _point("climatisation_state", "CLIMATISATION_STATE_HEATING", "2026-11-19T15:00:00Z"),
        _point("mileage", "19002", "2026-11-19T18:19:00Z"),
    ]})
    assert d.climatisation_state == "HEATING"
    assert d.field_captured_ts["climatisation_state"].startswith("2026-11-19T15:00:00")
    assert d.field_source_leaf["climatisation_state"] == "climatisation_state"


def test_the_reason_carries_its_own_capture_time() -> None:
    d = _map({"data": [
        _point("climatisation_reason_trigger", "immediate", "2026-11-19T15:01:00Z"),
    ]})
    assert d.climatisation_reason == "IMMEDIATE"
    assert d.field_captured_ts["climatisation_reason"].startswith("2026-11-19T15:01:00")


def test_a_leaf_without_a_time_gives_no_invented_one() -> None:
    d = _map({"data": [
        _point("climatisation_state", "CLIMATISATION_STATE_OFF"),
        _point("mileage", "19002", "2026-11-19T18:19:00Z"),
    ]})
    assert d.climatisation_state == "OFF"
    assert "climatisation_state" not in d.field_captured_ts


def test_an_invalid_state_records_nothing() -> None:
    d = _map({"data": [
        _point("climatisation_state", "CLIMATISATION_STATE_INVALID", "2026-11-19T15:00:00Z"),
    ]})
    assert d.climatisation_state is None
    assert "climatisation_state" not in d.field_captured_ts
    assert "climatisation_state" not in d.field_source_leaf


def test_values_are_unchanged() -> None:
    d = _map({"data": [
        _point("climatisation_state", "CLIMATISATION_STATE_HEATING", "2026-11-19T15:00:00Z"),
    ]})
    assert d.climatisation_state == "HEATING"
    assert d.climatisation_active is True
