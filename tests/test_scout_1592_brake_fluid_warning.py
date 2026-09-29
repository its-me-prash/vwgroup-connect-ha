# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-28 (#1592, Audi Q6 PPE) — the raw FlexRay/ESC brake-fluid
warning lamp ``BCS_BrkFldWarn_XIX_ESC_03_XIX_HCP1_FlexRay_A``. Ships the enum
``"BCS_BrkFld_Warning_Off "`` (trailing space) when the fluid is OK; mapped to a
PROBLEM binary sensor and reclaimed from the Vehicle Data Scout surface. Only the
OFF sample is observed, so the ON decode is INFERRED (anything not "...off").

The payload uses the real ``eu_data_act`` container the Scout reports the field
under, driven through ``_walk_fields`` so a wrong source-key spelling (the #1439
lesson) fails loudly instead of silently mapping nothing.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_KEY = "BCS_BrkFldWarn_XIX_ESC_03_XIX_HCP1_FlexRay_A"


def _map(value: str, base: VehicleData | None = None) -> VehicleData:
    payload = {"eu_data_act": {_KEY: value}}
    return map_dataset_to_vehicle_data(
        _walk_fields(payload), base or VehicleData(vin="X")
    )


def test_off_is_not_a_warning() -> None:
    # keep the trailing space to prove .strip() runs before .endswith()
    assert _map("BCS_BrkFld_Warning_Off ").brake_fluid_warning is False


def test_inferred_on_is_a_warning() -> None:
    # ON spelling is inferred (only OFF observed); non-"...off" => active
    assert _map("BCS_BrkFld_Warning_On").brake_fluid_warning is True


def test_absent_stays_none() -> None:
    d = map_dataset_to_vehicle_data(
        _walk_fields({"eu_data_act": {}}), VehicleData(vin="X")
    )
    assert d.brake_fluid_warning is None


def test_existing_value_not_clobbered() -> None:
    base = VehicleData(vin="X")
    base.brake_fluid_warning = True
    assert _map("BCS_BrkFld_Warning_Off ", base).brake_fluid_warning is True


def test_reclaimed_from_scout_surface() -> None:
    # A mapped field must ALSO stop flooding the Scout: the flattener emits both
    # the eu_data_act.-qualified path and the bare leaf; listing both in first()
    # reclaims both.
    payload = {"eu_data_act": {_KEY: "BCS_BrkFld_Warning_Off "}}
    syn: dict = {}
    flat = _walk_fields(payload, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    raw_leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert _KEY not in raw_leaves
