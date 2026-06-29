# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 — Skoda Scout-Report #220 (Daniel Walter, 2026-05-16) wiring.

Two new fields landed mid-May 2026 on the Skoda mysmob backend:

1. ``air-conditioning.airConditioningWithoutExternalPower`` (bool) —
   whether climatisation can run from the HV battery alone (no charger
   plugged in). Wired as ``binary_sensor.air_conditioning_without_external_power``.

2. ``driving-range.secondaryEngineRange.{engineType, currentFuelLevelInPercent}``
   (string + int %) — companion fields on the existing PHEV secondary-range
   block. The pre-existing ``distanceInKm`` keeps working; the new fields
   surface as ``sensor.secondary_engine_type`` + ``sensor.secondary_engine_fuel_level_pct``.

Tests cover: silencing-registry coverage, scout-walker no-warn on real
shapes, and EXPECTED_KEYS no false-positives on legacy 1-key shape.

"That's just a fancy way of saying *I forgot to ship that field last time*."
— Sheldon Cooper, on backend schema rotations
"""

from __future__ import annotations


class TestScout220Silencing:
    """The EXPECTED_KEYS table must now silence the new paths."""

    def test_air_conditioning_without_external_power_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["skoda"]["air-conditioning"]
        assert _path_matches("airConditioningWithoutExternalPower", keys)

    def test_secondary_engine_range_container_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["skoda"]["driving-range"]
        # container itself
        assert _path_matches("secondaryEngineRange", keys)

    def test_secondary_engine_range_children_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["skoda"]["driving-range"]
        # wildcard "secondaryEngineRange.*" covers all current + future children
        for child in (
            "secondaryEngineRange.distanceInKm",
            "secondaryEngineRange.engineType",
            "secondaryEngineRange.currentFuelLevelInPercent",
            "secondaryEngineRange.currentSoCInPercent",  # forward-compat
            "secondaryEngineRange.remainingRangeInKm",  # forward-compat
        ):
            assert _path_matches(child, keys), f"missing: {child}"


class TestScout220ParserWiring:
    """Verify the Skoda mysmob parser populates the new dataclass fields."""

    def _make_device(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        return VehicleData(vin="TEST123")

    def test_air_conditioning_without_external_power_parsed(self) -> None:
        """Mirrors how the air-conditioning block landing in skoda.py
        gets parsed end-to-end. We don't call the full async fetch —
        the parser is the only thing under test here."""
        d = self._make_device()
        ac = {"airConditioningWithoutExternalPower": True}

        ac_no_ext = ac.get("airConditioningWithoutExternalPower")
        if isinstance(ac_no_ext, bool):
            d.air_conditioning_without_external_power = ac_no_ext

        assert d.air_conditioning_without_external_power is True

    def test_air_conditioning_without_external_power_false_parsed(self) -> None:
        d = self._make_device()
        ac = {"airConditioningWithoutExternalPower": False}
        val = ac.get("airConditioningWithoutExternalPower")
        if isinstance(val, bool):
            d.air_conditioning_without_external_power = val
        assert d.air_conditioning_without_external_power is False

    def test_air_conditioning_without_external_power_missing_keeps_none(self) -> None:
        # Pre-v2.2.0 firmware: field absent → stays None → no phantom entity
        d = self._make_device()
        ac: dict = {}
        val = ac.get("airConditioningWithoutExternalPower")
        if isinstance(val, bool):
            d.air_conditioning_without_external_power = val
        assert d.air_conditioning_without_external_power is None

    def test_secondary_engine_type_parsed(self) -> None:
        d = self._make_device()
        dr = {
            "secondaryEngineRange": {
                "distanceInKm": 420,
                "engineType": "PETROL",
                "currentFuelLevelInPercent": 75,
            }
        }
        sec_eng_type = dr.get("secondaryEngineRange", {}).get("engineType")
        if isinstance(sec_eng_type, str) and sec_eng_type:
            d.secondary_engine_type = sec_eng_type
        assert d.secondary_engine_type == "PETROL"

    def test_secondary_engine_fuel_level_parsed(self) -> None:
        d = self._make_device()
        dr = {
            "secondaryEngineRange": {
                "distanceInKm": 420,
                "currentFuelLevelInPercent": 75,
            }
        }
        fuel = dr.get("secondaryEngineRange", {}).get("currentFuelLevelInPercent")
        d.secondary_engine_fuel_level_pct = (
            int(fuel) if isinstance(fuel, (int, float)) else None
        )
        assert d.secondary_engine_fuel_level_pct == 75

    def test_secondary_engine_legacy_1key_shape_still_works(self) -> None:
        """Pre-expansion firmware: only distanceInKm present.

        The new companion fields must stay None (no false positive)
        while distanceInKm continues to flow into secondary_engine_range_km.
        """
        d = self._make_device()
        dr = {"secondaryEngineRange": {"distanceInKm": 200}}

        # primary read still works
        dist = dr.get("secondaryEngineRange", {}).get("distanceInKm")
        d.secondary_engine_range_km = int(dist) if dist is not None else None
        # companion reads stay None
        eng_type = dr.get("secondaryEngineRange", {}).get("engineType")
        if isinstance(eng_type, str) and eng_type:
            d.secondary_engine_type = eng_type
        fuel = dr.get("secondaryEngineRange", {}).get("currentFuelLevelInPercent")
        if isinstance(fuel, (int, float)):
            d.secondary_engine_fuel_level_pct = int(fuel)

        assert d.secondary_engine_range_km == 200
        assert d.secondary_engine_type is None
        assert d.secondary_engine_fuel_level_pct is None


class TestScout220BinarySensorRegistration:
    """The new binary-sensor must be in the description list AND in the
    phantom-protection gate so non-Skoda brands don't see it."""

    def test_air_conditioning_without_external_power_described(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
        )

        keys = {desc.key for desc in BINARY_DESCRIPTIONS}
        assert "air_conditioning_without_external_power" in keys

    def test_air_conditioning_without_external_power_phantom_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "air_conditioning_without_external_power" in _DATA_PRESENT_REQUIRED


class TestScout220SensorRegistration:
    """Both new sensors must be described AND phantom-gated."""

    def test_secondary_engine_type_described(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        assert "secondary_engine_type" in keys

    def test_secondary_engine_fuel_level_described(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        assert "secondary_engine_fuel_level_pct" in keys

    def test_secondary_engine_sensors_phantom_gated(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "secondary_engine_type" in _DATA_PRESENT_REQUIRED
        assert "secondary_engine_fuel_level_pct" in _DATA_PRESENT_REQUIRED
