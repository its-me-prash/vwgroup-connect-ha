# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1002 / #1022 — is_charging must recognise the 15-min feed's SCREAMING_SNAKE
charging-state enum, not only the one-time export's camelCase spelling.

The MEB feed sends charging_state_report.current_charge_state as
CHARGE_STATE_CHARGING_HV_BATTERY; the old camelCase-only tuple never matched it,
so ID.5 / ID.7 read "not charging" while they were actively charging.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_NAME = "charging_state_report.current_charge_state"


def _is_charging(value: str) -> bool | None:
    fields = _walk_fields([{"dataFieldName": _NAME, "value": value}])
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X")).is_charging


class TestIsChargingFeedDialect:
    def test_screaming_snake_hv_battery(self) -> None:
        # #1022's exact raw value from a live charging ID.7.
        assert _is_charging("CHARGE_STATE_CHARGING_HV_BATTERY") is True

    def test_camelcase_one_time_export_still_works(self) -> None:
        # #764's Leon VZ e-Hybrid dialect must keep matching (no regression).
        assert _is_charging("chargingHvBattery") is True

    def test_screaming_snake_ac_active(self) -> None:
        assert _is_charging("CHARGE_STATE_CHARGING_AC_ACTIVE") is True

    def test_not_charging_is_false(self) -> None:
        assert _is_charging("CHARGE_STATE_NOT_CHARGING") is False

    def test_ready_for_charging_is_false(self) -> None:
        # "ready ... charging" contains the substring but the car is NOT charging,
        # so a naive contains() would be wrong; the normalised match must be exact.
        assert _is_charging("CHARGE_STATE_READY_FOR_CHARGING") is False
