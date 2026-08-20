# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout #1225 (@ChibiDanjo, VW TGI) — the EU Data Act portal ships the CNG tank
level as ``cng_gas_level`` (dict UUID c129d05d, "Gas level in percentage"). It maps
onto the existing ``cng_level_pct`` field/sensor already fed on the SEAT/CUPRA and
VW-EU OLA paths, and — being consumed via ``first()`` — stops surfacing in the Scout.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _dataset(*points: dict) -> dict:
    return {"data": list(points)}


def _parse(payload: dict) -> VehicleData:
    field_ts: dict[str, float] = {}
    field_syn: dict[str, set[str]] = {}
    contested: dict[str, set[str]] = {}
    field_uuids: dict[str, set[str]] = {}
    fields = _walk_fields(payload, field_ts, field_syn, contested, field_uuids)
    return map_dataset_to_vehicle_data(
        fields, VehicleData(vin="X"), field_ts, field_syn, contested, field_uuids
    )


class TestCngGasLevel:
    def test_value_maps_to_cng_level_pct(self) -> None:
        d = _parse(_dataset({"dataFieldName": "cng_gas_level", "value": "45"}))
        assert d.cng_level_pct == 45

    def test_zero_is_a_valid_empty_tank_not_dropped(self) -> None:
        # 0 % is a real reading (empty CNG tank) — must not be treated as None.
        d = _parse(_dataset({"dataFieldName": "cng_gas_level", "value": "0"}))
        assert d.cng_level_pct == 0

    def test_field_is_consumed_and_no_longer_leaks_to_scout(self) -> None:
        d = _parse(_dataset({"dataFieldName": "cng_gas_level", "value": "45"}))
        assert "cng_gas_level" not in (d.raw_unmapped_fields or {})

    def test_camelcase_alias_also_maps(self) -> None:
        d = _parse(_dataset({"dataFieldName": "cngLevel_pct", "value": "60"}))
        assert d.cng_level_pct == 60
