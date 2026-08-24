# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1055 (@ChristophCaina) — plug_state ("Charging Port") is now an enum sensor
with localized state labels.

Brands emit the plug-connection state with different casing (Škoda CONNECTED, VW
connected) and VW/CARIAD sometimes sends an 'invalid'/'unsupported' sentinel.
coordinator._enrich normalizes it to a lowercase {connected, disconnected} set
(anything else → None), the sensor declares device_class=ENUM + options, and every
translation carries a state block so Home Assistant shows a localized label
instead of the raw English word.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import threading
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.sensor import SensorDeviceClass

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _make_coord():
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "volkswagen", "username": "t@t.com", "password": "x",
                        "spin": "", "update_interval": 300}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = MagicMock()
    coord._cariad_client._image_data = {}
    coord.vehicle_static_info = {}
    coord._was_available = True
    coord.data = None
    return coord


def _enrich_plug(raw_state):
    coord = _make_coord()
    data = {"vin": "V1", "latitude": None, "longitude": None, "plug_state": raw_state}
    out = asyncio.run(coord._enrich(data))
    return out.get("plug_state")


class TestPlugStateNormalization:
    def test_uppercase_connected_is_lowercased(self):
        assert _enrich_plug("CONNECTED") == "connected"

    def test_mixed_case_disconnected(self):
        assert _enrich_plug("Disconnected") == "disconnected"

    def test_already_lowercase_preserved(self):
        assert _enrich_plug("connected") == "connected"

    def test_invalid_sentinel_becomes_none(self):
        assert _enrich_plug("invalid") is None

    def test_unsupported_sentinel_becomes_none(self):
        assert _enrich_plug("UNSUPPORTED") is None

    def test_unexpected_value_becomes_none(self):
        # any value outside the two real states must not leak as a raw label
        assert _enrich_plug("connecting") is None


class TestPlugStateSensorDescription:
    def test_plug_state_is_enum_with_options(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "plug_state")
        assert desc.device_class == SensorDeviceClass.ENUM
        assert set(desc.options or []) == {"connected", "disconnected"}


class TestPlugStateTranslations:
    def test_all_languages_have_state_labels(self):
        tdir = (
            pathlib.Path(__file__).resolve().parents[1]
            / "custom_components/vag_connect/translations"
        )
        files = sorted(tdir.glob("*.json"))
        assert len(files) >= 12
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            state = d["entity"]["sensor"]["plug_state"]["state"]
            assert state.get("connected"), f"{f.name}: missing connected label"
            assert state.get("disconnected"), f"{f.name}: missing disconnected label"
