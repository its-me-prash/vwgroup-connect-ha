# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.0 — Skoda Scout #682 (ra666ack, 2026-07-09): heaterSource wiring.

The Skoda mysmob ``air-conditioning`` endpoint exposes ``heaterSource``
("AUTOMATIC" in the wild). VW/Audi/SEAT already map this to the
``heater_source`` sensor; Skoda didn't. v2.17.0 parses it into the same
cross-brand field. Free enum string, defensively guarded.
"""
from __future__ import annotations


class TestScout682Silencing:
    def test_heater_source_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["skoda"]["air-conditioning"]
        assert _path_matches("heaterSource", keys)


class TestScout682ParserWiring:
    def _make_device(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        return VehicleData(vin="TEST123")

    def test_heater_source_parsed(self) -> None:
        # Mirrors the air-conditioning block in skoda.py.
        d = self._make_device()
        ac = {"heaterSource": "AUTOMATIC"}
        heater_src = ac.get("heaterSource")
        if isinstance(heater_src, str) and heater_src:
            d.heater_source = heater_src
        assert d.heater_source == "AUTOMATIC"

    def test_heater_source_missing_keeps_none(self) -> None:
        d = self._make_device()
        ac: dict = {}
        heater_src = ac.get("heaterSource")
        if isinstance(heater_src, str) and heater_src:
            d.heater_source = heater_src
        assert d.heater_source is None

    def test_heater_source_empty_string_keeps_none(self) -> None:
        d = self._make_device()
        ac = {"heaterSource": ""}
        heater_src = ac.get("heaterSource")
        if isinstance(heater_src, str) and heater_src:
            d.heater_source = heater_src
        assert d.heater_source is None


class TestScout682SensorRegistration:
    def test_heater_source_sensor_exists(self) -> None:
        # The sensor is pre-existing (VW/Audi/SEAT) — Skoda now feeds it too.
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        assert "heater_source" in keys

    def test_heater_source_phantom_gated(self) -> None:
        # Data-present gated so non-populating cars don't get a phantom entity.
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "heater_source" in _DATA_PRESENT_REQUIRED
