# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b8 (#1310, indigomejor) — last-trip travel-time sensor (last_trip_duration_min).

The value was already parsed into ``last_trip_duration_min`` (minutes) by every
trip-capable brand but had no entity. These pin the descriptor's shape (per-trip
DURATION / minutes / MEASUREMENT — NOT the cumulative TOTAL_INCREASING the lifetime
sibling uses), its gating, and its presence across every i18n file.
"""
from __future__ import annotations

import glob
import json
import os


def test_last_trip_duration_descriptor():
    from homeassistant.components.sensor import (
        SensorDeviceClass,
        SensorStateClass,
    )
    from homeassistant.const import UnitOfTime

    from custom_components.vag_connect.sensor import (
        SENSOR_DESCRIPTIONS,
        _TRIP_STATS_BRANDS,
        _TRIP_STATS_KEYS,
    )

    d = next(x for x in SENSOR_DESCRIPTIONS if x.key == "last_trip_duration_min")
    assert d.data_key == "last_trip_duration_min"
    assert d.device_class == SensorDeviceClass.DURATION
    assert d.native_unit_of_measurement == UnitOfTime.MINUTES
    # per-trip value resets each ignition cycle → MEASUREMENT, never TOTAL_INCREASING
    assert d.state_class == SensorStateClass.MEASUREMENT
    assert d.entity_category is None  # primary, like its last_trip_* siblings
    # gated with the other per-trip keys, and audi_acpp added (trip-sweep finding 7)
    assert "last_trip_duration_min" in _TRIP_STATS_KEYS
    assert "audi_acpp" in _TRIP_STATS_BRANDS


def test_last_trip_duration_i18n_present_in_all_files():
    base = os.path.join(
        os.path.dirname(__file__), "..", "custom_components", "vag_connect"
    )
    files = [os.path.join(base, "strings.json")] + glob.glob(
        os.path.join(base, "translations", "*.json")
    )
    assert len(files) >= 13, files
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        sensor = data["entity"]["sensor"]
        assert "last_trip_duration_min" in sensor, f
        name = sensor["last_trip_duration_min"]["name"]
        assert isinstance(name, str) and name.strip(), f
