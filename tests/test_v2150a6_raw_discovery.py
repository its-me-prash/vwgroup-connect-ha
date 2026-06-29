# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b1/A6 — raw field discovery: unmapped portal fields surfaced (with their
REAL values) on ONE disabled diagnostic sensor's attributes, fed by the same
unmapped detection that feeds the Vehicle Data Scout (one pass, both worlds)."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _RAW_FIELD_CAP,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.sensor import VagConnectSensor, VagSensorDescription


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


class TestParserRawCapture:
    def test_unmapped_fields_captured_with_values(self) -> None:
        d = _map({"soc": "80", "totally_unknown_x": "42", "another_unknown": "hi"})
        assert d.battery_soc == 80                      # mapped → consumed
        assert "soc" not in d.raw_unmapped_fields       # not surfaced as raw
        assert d.raw_unmapped_fields["totally_unknown_x"] == "42"
        assert d.raw_unmapped_fields["another_unknown"] == "hi"

    def test_all_mapped_leaves_raw_empty(self) -> None:
        assert _map({"soc": "80"}).raw_unmapped_fields == {}

    def test_cap_respected(self) -> None:
        fields = {f"unknown_{i:04d}": str(i) for i in range(_RAW_FIELD_CAP + 50)}
        assert len(_map(fields).raw_unmapped_fields) == _RAW_FIELD_CAP


def _coord(raw: dict[str, str]) -> MagicMock:
    coord = MagicMock()
    coord.data = {"X": {"vin": "X", "raw_unmapped_fields": raw}}
    coord.vehicles = coord.data
    coord.is_read_only = MagicMock(return_value=False)
    coord.last_update_success = True
    return coord


def _sensor(raw: dict[str, str]) -> VagConnectSensor:
    desc = VagSensorDescription(key="raw_api_fields", data_key="raw_unmapped_fields")
    return VagConnectSensor(_coord(raw), "X", desc)


class TestRawSensor:
    def test_native_value_is_count(self) -> None:
        assert _sensor({"a": "1", "b": "2"}).native_value == 2

    def test_empty_is_none(self) -> None:
        assert _sensor({}).native_value is None

    def test_attributes_carry_all_fields(self) -> None:
        assert _sensor({"a": "1", "b": "2"}).extra_state_attributes == {
            "fields": {"a": "1", "b": "2"}
        }

    def test_attributes_none_when_empty(self) -> None:
        assert _sensor({}).extra_state_attributes is None
