# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1195 (hangout6690, ID.3) — the EU Data Act portal ships
``battery_state_report.soc`` under TWO content-UUIDs: the live SoC and a
"SoC at charge start" snapshot (per the official EU Data Act data dictionary).
The charge-start leaf is re-stamped with a fresh capture time whenever a charge
begins, so the freshness resolver let its stale value win the live SoC right
after a charge started (his car: charge-start 37% beating the live 24%).

The walker now remaps the known charge-start-SoC UUID onto a distinct leaf
(``battery_state_report.soc_at_charge_start``) so it never competes for the live
``battery_state_report.soc``. The value is kept (never suppressed), just no
longer mistaken for the live reading.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _CHARGE_START_SOC_UUIDS,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_LIVE_UUID = "506cb83e-f99f-3af3-bbeb-0429b69a78d9"
_CHARGE_START_UUID = "93b55324-6628-36df-8f76-8eba797fc59c"


def _soc_point(value: str, key: str) -> dict:
    return {"dataFieldName": "battery_state_report.soc", "value": value, "key": key}


def test_charge_start_soc_does_not_win_the_live_soc() -> None:
    # live 24% + charge-start 37% (the stale one) in one export.
    fields = _walk_fields({"data": [
        _soc_point("24", _LIVE_UUID),
        _soc_point("37", _CHARGE_START_UUID),
    ]})
    assert fields["battery_state_report.soc"] == "24"
    # kept under its own name — not suppressed
    assert fields["battery_state_report.soc_at_charge_start"] == "37"


def test_charge_start_remapped_even_when_it_is_the_last_append() -> None:
    # last-append would otherwise win inside the ZIP (#529) — the remap must fire
    # regardless of order, so the live SoC still wins.
    fields = _walk_fields({"data": [
        _soc_point("37", _CHARGE_START_UUID),
        _soc_point("24", _LIVE_UUID),
    ]})
    assert fields["battery_state_report.soc"] == "24"


def test_normal_single_soc_is_unaffected() -> None:
    # a car that ships one soc point (any/no charge-start UUID) is untouched.
    fields = _walk_fields({"data": [
        {"dataFieldName": "battery_state_report.soc", "value": "55",
         "key": "some-other-uuid"},
    ]})
    assert fields["battery_state_report.soc"] == "55"
    assert "battery_state_report.soc_at_charge_start" not in fields


def test_known_charge_start_uuid_is_registered() -> None:
    assert _CHARGE_START_UUID in _CHARGE_START_SOC_UUIDS


def test_end_to_end_battery_soc_is_the_live_value() -> None:
    # end to end: the mapper must set battery_soc to the live 24, not 37.
    fields = _walk_fields({"data": [
        _soc_point("24", _LIVE_UUID),
        _soc_point("37", _CHARGE_START_UUID),
    ]})
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))
    assert d.battery_soc == 24
