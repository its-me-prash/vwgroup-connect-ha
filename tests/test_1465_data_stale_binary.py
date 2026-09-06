# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 — automatable ``data_stale`` binary_sensor (device_class=PROBLEM).

The stale-data signal already exists as ``portal_health=stale`` + a 72 h Repair;
this adds a boolean a user can drive an automation off, brand-agnostic and gated on
a populated capture timestamp so it self-hides for reads that carry none. The flag
itself is set in the coordinator from the SAME capture-age + threshold as the
Repair, so the two can never disagree.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.binary_sensor import VagDataStaleSensor

VIN = "WVWZZZTESTVIN0001"


def _sensor(vehicle: dict) -> VagDataStaleSensor:
    coord = MagicMock()
    coord.data = {VIN: vehicle}
    return VagDataStaleSensor(coord, VIN)


def test_is_on_maps_the_flag() -> None:
    assert _sensor({"data_stale": True}).is_on is True
    assert _sensor({"data_stale": False}).is_on is False
    assert _sensor({"data_stale": None}).is_on is None   # no capture ts → unknown
    assert _sensor({}).is_on is None                     # absent → unknown


def test_attributes_surface_age_and_health_when_present() -> None:
    s = _sensor({
        "data_stale": True,
        "minutes_since_last_snapshot": 4800,
        "portal_health": "stale",
    })
    attrs = s._platform_attributes()
    assert attrs is not None
    assert attrs["minutes_since_last_snapshot"] == 4800
    assert attrs["portal_health"] == "stale"


def test_attributes_none_when_no_portal_signals() -> None:
    # a Škoda-native/BFF read carries data_stale but no portal_health/age → no attrs
    assert _sensor({"data_stale": True})._platform_attributes() is None
