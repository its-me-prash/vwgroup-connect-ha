# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1022 — charge power scale by UUID, not by the value's fractional part.

The portal emits ``battery_state_report.charge_power`` under several dict UUIDs
with DIFFERENT units: ``c8cb205f`` is "The float value" (already kW), the others
state "resolution of 0,1 kW" (deci-kW). The pre-existing fractional-part heuristic
(integer => deci, decimals => kW) guessed right for the reported ID.7 value
(10.399994) but breaks for a car charging at an exact integer kW (11.0 -> 1.1).
Keying by the UUID fixes that; the heuristic stays as the fallback for cars that
ship the field name without a mapped encoding UUID.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
    _walk_fields,
)
from custom_components.vag_connect.cariad.models import VehicleData

_NAME = "battery_state_report.charge_power"
_FLOAT_UUID = "c8cb205f-01c6-3c81-bda1-059b99ae6515"   # already kW
_DECI_UUID = "44ed0d61-98c4-36df-b860-b077929a5797"    # deci-kW


def _cp_kw(payload: list) -> float | None:
    fields = _walk_fields(payload)
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X")).charging_power_kw


def _pt(value: str, uuid: str | None = None) -> dict:
    pt = {"dataFieldName": _NAME, "value": value}
    if uuid:
        pt["key"] = uuid
    return [pt]


class TestChargePowerUuid:
    def test_float_uuid_exact_integer_kw_not_divided(self) -> None:
        # THE fix: a round 11 kW via the float UUID must stay 11.0, not become 1.1.
        assert _cp_kw(_pt("11", _FLOAT_UUID)) == 11.0

    def test_float_uuid_fractional_kept(self) -> None:
        assert _cp_kw(_pt("10.399994", _FLOAT_UUID)) == 10.4

    def test_deci_uuid_divided_by_ten(self) -> None:
        assert _cp_kw(_pt("65", _DECI_UUID)) == 6.5

    def test_float_uuid_wins_over_the_heuristic(self) -> None:
        # even an integer that the heuristic would /10 stays kW when the float
        # UUID tags it.
        assert _cp_kw(_pt("22", _FLOAT_UUID)) == 22.0


class TestChargePowerNameFallback:
    """No encoding UUID present => the fractional heuristic behaves exactly as
    before (no regression)."""

    def test_integer_treated_as_deci(self) -> None:
        assert _cp_kw(_pt("65")) == 6.5

    def test_fractional_treated_as_kw(self) -> None:
        assert _cp_kw(_pt("10.4")) == 10.4

    def test_low_ac_integer_still_deci(self) -> None:
        # #764 (Leon VZ e-Hybrid): 19 -> 1.9 kW on an 11 kW AC charge.
        assert _cp_kw(_pt("19")) == 1.9
