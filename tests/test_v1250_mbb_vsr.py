# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""MBB VSR Phase 2 (read-side) tests for v1.25.0 PR-G — Golf 7 GTE Tank.

Tests the new helpers in `cariad/_mbb.py`:
- `build_mbb_vsr_status_url` URL construction
- `parse_mbb_vsr_field` defensive walking of MBB VSR response

Wire-in (`vw_eu.py:_maybe_fill_from_mbb_vsr`) is integration-tested in
the wider test suite; these unit tests focus on the pure-logic helpers.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect" / "cariad"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(f"vag_pure.{name}", _ROOT / file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"vag_pure.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_mbb = _load("_mbb", "_mbb.py")
build_mbb_vsr_status_url = _mbb.build_mbb_vsr_status_url
parse_mbb_vsr_field = _mbb.parse_mbb_vsr_field
MBB_VSR_FIELD_TANK_PCT = _mbb.MBB_VSR_FIELD_TANK_PCT
MBB_VSR_FIELD_TOTAL_RANGE_KM = _mbb.MBB_VSR_FIELD_TOTAL_RANGE_KM


# Fixture from upstream audi_models.py legacy IDS table
_GOLF_GTE_VSR_RESPONSE = {
    "StoredVehicleDataResponse": {
        "vehicleData": {
            "data": [
                {
                    "id": "0x0301",
                    "field": [
                        {
                            "id": "0x030103000A",
                            "tsCarCaptured": "2026-05-09T10:00:00Z",
                            "value": "60",
                            "unit": "%",
                        },
                        {
                            "id": "0x0301030005",
                            "tsCarCaptured": "2026-05-09T10:00:00Z",
                            "value": "450",
                            "unit": "km",
                        },
                    ],
                },
                {
                    "id": "0x0204",
                    "field": [
                        {
                            "id": "0x02040C0001",
                            "value": "1200",
                            "unit": "km",
                        },
                    ],
                },
            ],
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# build_mbb_vsr_status_url
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildMbbVsrStatusUrl:
    def test_volkswagen_de(self):
        url = build_mbb_vsr_status_url(
            "https://msg.volkswagen.de", "volkswagen", "DE", "WVWZZZ7AZRE000001",
        )
        assert url == (
            "https://msg.volkswagen.de/fs-car/bs/vsr/v1/VW/DE/"
            "vehicles/WVWZZZ7AZRE000001/status"
        )

    def test_audi_at(self):
        url = build_mbb_vsr_status_url(
            "https://fal-3a.prd.eu.dp.vwg-connect.com", "audi", "AT",
            "WAUZZZ8VZRE111111",
        )
        assert url == (
            "https://fal-3a.prd.eu.dp.vwg-connect.com/fs-car/bs/vsr/v1/Audi/AT/"
            "vehicles/WAUZZZ8VZRE111111/status"
        )


# ─────────────────────────────────────────────────────────────────────────────
# parse_mbb_vsr_field — happy path
# ─────────────────────────────────────────────────────────────────────────────


class TestParseMbbVsrFieldHappy:
    def test_tank_pct(self):
        assert parse_mbb_vsr_field(_GOLF_GTE_VSR_RESPONSE, MBB_VSR_FIELD_TANK_PCT) == "60"

    def test_total_range_km(self):
        assert parse_mbb_vsr_field(_GOLF_GTE_VSR_RESPONSE, MBB_VSR_FIELD_TOTAL_RANGE_KM) == "450"

    def test_adblue_range_km(self):
        assert parse_mbb_vsr_field(_GOLF_GTE_VSR_RESPONSE, "0x02040C0001") == "1200"

    def test_field_not_present_returns_none(self):
        assert parse_mbb_vsr_field(_GOLF_GTE_VSR_RESPONSE, "0xDEADBEEF") is None


# ─────────────────────────────────────────────────────────────────────────────
# parse_mbb_vsr_field — defensive paths (NEVER raise)
# ─────────────────────────────────────────────────────────────────────────────


class TestParseMbbVsrFieldDefensive:
    def test_none_response(self):
        assert parse_mbb_vsr_field(None, MBB_VSR_FIELD_TANK_PCT) is None

    def test_non_dict_response(self):
        assert parse_mbb_vsr_field("garbage", MBB_VSR_FIELD_TANK_PCT) is None  # type: ignore[arg-type]
        assert parse_mbb_vsr_field([], MBB_VSR_FIELD_TANK_PCT) is None  # type: ignore[arg-type]

    def test_missing_envelope(self):
        assert parse_mbb_vsr_field({}, MBB_VSR_FIELD_TANK_PCT) is None
        assert parse_mbb_vsr_field({"foo": "bar"}, MBB_VSR_FIELD_TANK_PCT) is None

    def test_missing_vehicle_data(self):
        assert parse_mbb_vsr_field(
            {"StoredVehicleDataResponse": {}}, MBB_VSR_FIELD_TANK_PCT,
        ) is None

    def test_missing_data_groups(self):
        assert parse_mbb_vsr_field(
            {"StoredVehicleDataResponse": {"vehicleData": {}}}, MBB_VSR_FIELD_TANK_PCT,
        ) is None

    def test_non_list_data(self):
        assert parse_mbb_vsr_field(
            {"StoredVehicleDataResponse": {"vehicleData": {"data": "garbage"}}},
            MBB_VSR_FIELD_TANK_PCT,
        ) is None

    def test_non_dict_group_skipped(self):
        response = {
            "StoredVehicleDataResponse": {
                "vehicleData": {
                    "data": [
                        "garbage_string",
                        None,
                        {
                            "id": "0x0301",
                            "field": [
                                {"id": MBB_VSR_FIELD_TANK_PCT, "value": "75"},
                            ],
                        },
                    ],
                },
            },
        }
        assert parse_mbb_vsr_field(response, MBB_VSR_FIELD_TANK_PCT) == "75"

    def test_field_value_none_returns_none(self):
        response = {
            "StoredVehicleDataResponse": {
                "vehicleData": {
                    "data": [{
                        "id": "0x0301",
                        "field": [{"id": MBB_VSR_FIELD_TANK_PCT, "value": None}],
                    }],
                },
            },
        }
        assert parse_mbb_vsr_field(response, MBB_VSR_FIELD_TANK_PCT) is None

    def test_field_value_int_coerced_to_string(self):
        response = {
            "StoredVehicleDataResponse": {
                "vehicleData": {
                    "data": [{
                        "id": "0x0301",
                        "field": [{"id": MBB_VSR_FIELD_TANK_PCT, "value": 60}],
                    }],
                },
            },
        }
        assert parse_mbb_vsr_field(response, MBB_VSR_FIELD_TANK_PCT) == "60"

    @given(garbage=st.one_of(
        st.none(), st.text(), st.integers(),
        st.lists(st.integers(), max_size=5),
        st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
    ))
    @settings(max_examples=200)
    def test_never_raises_for_arbitrary_input(self, garbage):
        out = parse_mbb_vsr_field(garbage, MBB_VSR_FIELD_TANK_PCT)
        assert out is None or isinstance(out, str)
