# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Move 1 / data-quality — the ambiguous-reading signal (contested_fields: two
portal samples with the SAME car_captured_time but different values, recorded by
_walk_fields) is surfaced on the data_source_channel diagnostic sensor so a user
can see which reading was uncertain this cycle. Portal rivals expose a bare
ambiguous_reading bool; ours names the fields and the tied values. Nothing is
surfaced on a clean poll, so the recorder is never bloated.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.sensor import VagConnectSensor, VagSensorDescription


def _coord(vehicle: dict) -> MagicMock:
    coord = MagicMock()
    coord.data = {"X": {"vin": "X", "source_channel": "eu_data_act", **vehicle}}
    coord.vehicles = coord.data
    coord.is_read_only = MagicMock(return_value=False)
    coord.last_update_success = True
    return coord


def _sensor(vehicle: dict) -> VagConnectSensor:
    desc = VagSensorDescription(key="data_source_channel", data_key="source_channel")
    return VagConnectSensor(_coord(vehicle), "X", desc)


def test_contested_fields_surfaced() -> None:
    # contested tie is surfaced alongside the friendly channel overview
    s = _sensor({"contested_fields": {"battery_soc": ["50", "71"]}})
    assert s.extra_state_attributes == {
        "channels": ["EU Data Act portal"],
        "raw": "eu_data_act",
        "contested_fields": {"battery_soc": ["50", "71"]},
    }


def test_channel_overview_without_contested() -> None:
    # a clean poll still names its source(s); no contested_fields key
    attrs = _sensor({"contested_fields": {}}).extra_state_attributes
    assert attrs == {"channels": ["EU Data Act portal"], "raw": "eu_data_act"}
    assert "contested_fields" not in attrs


def test_no_attributes_when_no_source_and_no_contested() -> None:
    coord = _coord({})
    coord.data["X"]["source_channel"] = None
    desc = VagSensorDescription(key="data_source_channel", data_key="source_channel")
    assert VagConnectSensor(coord, "X", desc).extra_state_attributes is None
