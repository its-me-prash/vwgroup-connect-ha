# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-30 (#1624/#1630/#1629/#1626) — the modern MEB EU Data Act portal
ships the climate target temperature as a raw bus value under the nested
``climatisation_settings`` block: 0..255 maps to 10..35.5 °C in 0.1 °C steps (the
official dictionary encoding). Four independent reporters cross-validate it
(70/120/120/130 -> 17.0/22.0/22.0/23.0 °C, all sane cabin setpoints; the only
other scale that fits the dictionary, 0..69, yields impossible >54 °C for 120/130).

It feeds the EXISTING ``target_temperature`` field/sensor, fill-if-empty (a
brand-native / BFF / legacy read always wins), and both the qualified path and the
bare leaf are reclaimed from the Scout surface.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict, base: VehicleData | None = None) -> VehicleData:
    return map_dataset_to_vehicle_data(
        _walk_fields({"eu_data_act": fields}), base or VehicleData(vin="X")
    )


def _tt(raw: str, base: VehicleData | None = None) -> object:
    return _map({"climatisation_settings": {"target_temperature": raw}}, base).target_temperature


def test_cross_sample_decodes() -> None:
    # the four reporters' raw values → sane cabin setpoints (raw*0.1 + 10)
    assert _tt("70") == 17.0
    assert _tt("120") == 22.0
    assert _tt("130") == 23.0
    assert _tt("0") == 10.0     # bus 0 = Low/LO
    assert _tt("255") == 35.5   # bus 255 = High/HI


def test_fill_if_empty_brand_native_wins() -> None:
    base = VehicleData(vin="X")
    base.target_temperature = 21.0  # a BFF/brand-native read already set it
    assert _tt("130", base) == 21.0  # portal value must NOT override


def test_out_of_range_is_ignored() -> None:
    # a raw value outside the documented 0..255 bus range is not a temperature
    assert _tt("300") is None
    assert _tt("-5") is None


def test_absent_leaf_stays_none() -> None:
    assert _map({}).target_temperature is None


def test_leaf_reclaimed_from_scout_surface() -> None:
    syn: dict = {}
    flat = _walk_fields(
        {"eu_data_act": {"climatisation_settings": {"target_temperature": "120"}}},
        None, syn,
    )
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    assert d.target_temperature == 22.0
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert "target_temperature" not in leaves, "bare twin still floods the Scout"
