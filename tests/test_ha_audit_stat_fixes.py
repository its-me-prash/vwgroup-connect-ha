# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HA feature-coverage audit — statistics/device-class corrections.

A lifetime cumulative counter had no state_class (so it got zero long-term
statistics), and a battery-% sensor lacked its BATTERY device_class. Both are now
correct.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

_BY_KEY = {d.key: d for d in SENSOR_DESCRIPTIONS}


def test_lifetime_travel_time_is_total_increasing() -> None:
    d = _BY_KEY["lifetime_travel_time_min"]
    assert d.state_class == SensorStateClass.TOTAL_INCREASING


def test_primary_engine_soc_is_a_battery_device_class() -> None:
    d = _BY_KEY["primary_engine_soc_pct"]
    assert d.device_class == SensorDeviceClass.BATTERY
    assert d.state_class == SensorStateClass.MEASUREMENT  # unchanged
