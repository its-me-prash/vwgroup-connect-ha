# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-28 (#1603, VW Passat eTSI) — the bare portal climate on/off flag
``climacontrol`` ("true"/"false"; official dict 993a7694 = "heating in the
vehicle is in the preheating state"). It is the same datum the existing
``climatisation_active`` binary sensor exposes, so it is folded in as a coarse
FALLBACK (fill-if-empty: the richer ``climatisation_state`` enum and brand-native
reads win) and reclaimed from the Scout surface. No new entity.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(payload: dict, base: VehicleData | None = None) -> VehicleData:
    return map_dataset_to_vehicle_data(
        _walk_fields(payload), base or VehicleData(vin="X")
    )


def test_climacontrol_false() -> None:
    d = _map({"eu_data_act": {"climacontrol": "false"}})
    assert d.climatisation_active is False


def test_climacontrol_true() -> None:
    d = _map({"eu_data_act": {"climacontrol": "true"}})
    assert d.climatisation_active is True


def test_climacontrol_is_case_and_space_robust() -> None:
    d = _map({"eu_data_act": {"climacontrol": "TRUE "}})
    assert d.climatisation_active is True


def test_state_enum_wins_over_climacontrol() -> None:
    # climatisation_state is derived first; a HEATING enum sets active True and
    # the coarse climacontrol=false fallback must NOT override it.
    d = _map(
        {
            "climatisation_state": "CLIMATISATION_STATE_HEATING",
            "eu_data_act": {"climacontrol": "false"},
        }
    )
    assert d.climatisation_active is True


def test_brand_native_value_not_clobbered() -> None:
    base = VehicleData(vin="X")
    base.climatisation_active = True
    d = _map({"eu_data_act": {"climacontrol": "false"}}, base)
    assert d.climatisation_active is True


def test_reclaimed_from_scout_surface() -> None:
    payload = {"eu_data_act": {"climacontrol": "false"}}
    syn: dict = {}
    flat = _walk_fields(payload, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    raw_leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert "climacontrol" not in raw_leaves
