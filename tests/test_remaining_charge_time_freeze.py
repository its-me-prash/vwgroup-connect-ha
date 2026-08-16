# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Remaining-charge-time ETA must not freeze on its last value after a charge.

Sibling of #1090 (charge power/rate). Grounded in a real archived diagnostic:
gr6803's VW ID.7 (#632) reported remaining_charge_time_min = 70 while the car sat
at NOT_READY_FOR_CHARGING with is_charging False; other portal VWs showed 5 and
115 min. Those EU-Data-Act cars never report plug_connected, so the fix keys on
is_charging being explicitly False rather than the plug.
"""
from __future__ import annotations

from unittest.mock import MagicMock

VIN = "WVWZZZE1ZPP000001"

TIME_KEYS = (
    "remaining_charge_time_min",
    "remaining_charge_time_nav_min",
    "remaining_charge_time_bulk_min",
)


def _sensor(key: str, **vehicle):
    from custom_components.vag_connect.sensor import (
        VagConnectSensor,
        VagSensorDescription,
    )

    coord = MagicMock()
    coord.data = {VIN: {"vin": VIN, **vehicle}}
    desc = VagSensorDescription(key=key, data_key=key)
    s = VagConnectSensor.__new__(VagConnectSensor)
    s._vin = VIN
    s.coordinator = coord
    s.entity_description = desc
    return s


def test_stale_eta_zeroed_when_not_charging() -> None:
    for key in TIME_KEYS:
        s = _sensor(key, is_charging=False,
                    charging_state="NOT_READY_FOR_CHARGING", **{key: 70})
        assert s.native_value == 0, key


def test_eta_kept_while_charging() -> None:
    for key in TIME_KEYS:
        s = _sensor(key, is_charging=True,
                    charging_state="CHARGING", **{key: 70})
        assert s.native_value == 70, key


def test_eta_kept_when_charging_state_unknown() -> None:
    # is_charging None (EU-DA portal never parsed it) → the ETA may be real, keep.
    for key in TIME_KEYS:
        s = _sensor(key, is_charging=None, **{key: 42})
        assert s.native_value == 42, key


def test_missing_value_stays_none_not_fabricated_zero() -> None:
    # No stale reading to suppress → unavailable, not a fake 0.
    s = _sensor("remaining_charge_time_min", is_charging=False)
    assert s.native_value is None


def test_climate_remaining_time_untouched() -> None:
    # A non-charge "minutes remaining" sensor must not be zeroed by this rule.
    s = _sensor("climate_remaining_time_min", is_charging=False,
                climate_remaining_time_min=8)
    assert s.native_value == 8
