# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-25 — the modern portal ``climatisation_state`` enum is wired to
the existing climatisation_state sensor (7+ VW ID.x reporters). The redundant
``CLIMATISATION_STATE_`` prefix is stripped to match the OFF/HEATING format the
brand channels use, and climatisation_active is derived like the brand parsers.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields, map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(points):
    return map_dataset_to_vehicle_data(_walk_fields({"data": points}), VehicleData(vin="X"))


def test_climatisation_state_heating() -> None:
    d = _map([{"dataFieldName": "climatisation_state", "value": "CLIMATISATION_STATE_HEATING", "key": "k"}])
    assert d.climatisation_state == "HEATING"
    assert d.climatisation_active is True


def test_climatisation_state_off() -> None:
    d = _map([{"dataFieldName": "climatisation_state", "value": "CLIMATISATION_STATE_OFF", "key": "k"}])
    assert d.climatisation_state == "OFF"
    assert d.climatisation_active is False


def test_climatisation_state_invalid_is_skipped() -> None:
    d = _map([{"dataFieldName": "climatisation_state", "value": "CLIMATISATION_STATE_INVALID", "key": "k"}])
    assert d.climatisation_state is None


def test_brand_native_value_is_not_clobbered() -> None:
    base = VehicleData(vin="X")
    base.climatisation_state = "COOLING"
    d = map_dataset_to_vehicle_data(
        _walk_fields({"data": [{"dataFieldName": "climatisation_state", "value": "CLIMATISATION_STATE_OFF", "key": "k"}]}),
        base,
    )
    assert d.climatisation_state == "COOLING"  # fill-if-empty
