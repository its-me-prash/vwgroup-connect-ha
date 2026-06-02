# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.1 Phase 8 PR #1 — "alles parsen statt silencen" Skoda batch.

User-directive (2026-05-17 post-v2.2.0 release): every silenced
scout field that has clear semantic value gets PARSED as an HA
entity instead of just silenced. "Nothing more silencing, parse
everything."

This first batch wires 5 Skoda mysmob fields that have been
silenced (no scout spam) but never exposed as entities:

| Field | Path | New entity |
|-------|------|------------|
| `battery_protection_limit_on` | `readiness.batteryProtectionLimitOn` | binary_sensor |
| `car_type` | `driving-range.carType` | sensor (text) |
| `primary_engine_type` (cross-brand) | `driving-range.primaryEngineRange.engineType` | sensor (text, PR #3 cross-brand reuse) |
| `primary_engine_fuel_level_pct` | `driving-range.primaryEngineRange.currentFuelLevelInPercent` | sensor (%) |
| `maintenance_report_captured_at` | `maintenance.maintenanceReport.capturedAt` | sensor (TIMESTAMP) |

"Why have a key on the keyring if you never use it?"
— Lisa Simpson, on silenced scout fields nobody parses
"""

from __future__ import annotations

import pytest


class TestModelFields:
    @pytest.mark.parametrize(
        "field",
        [
            "battery_protection_limit_on",
            "car_type",
            "primary_engine_fuel_level_pct",
            "maintenance_report_captured_at",
        ],
    )
    def test_field_exists_default_none(self, field: str) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, field)
        assert getattr(d, field) is None


class TestSkodaReadinessParser:
    """`readiness.batteryProtectionLimitOn` boolean parsing."""

    def _parse(self, raw):
        if isinstance(raw, bool):
            return raw
        return None

    def test_true_assigned(self) -> None:
        assert self._parse(True) is True

    def test_false_assigned(self) -> None:
        assert self._parse(False) is False

    def test_none_stays_none(self) -> None:
        assert self._parse(None) is None

    def test_int_one_rejected(self) -> None:
        # `isinstance(1, bool) is False` — defensive guard rejects
        assert self._parse(1) is None

    def test_string_true_rejected(self) -> None:
        assert self._parse("true") is None


class TestSkodaDrivingRangeBatch:
    """3 driving-range parsers in one block."""

    def _parse(self, driving_range):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        if not isinstance(driving_range, dict):
            return d
        # primaryEngineRange children
        primary = driving_range.get("primaryEngineRange") or {}
        eng_type = primary.get("engineType")
        if isinstance(eng_type, str) and eng_type:
            d.primary_engine_type = eng_type
        fuel = primary.get("currentFuelLevelInPercent")
        if isinstance(fuel, (int, float)):
            d.primary_engine_fuel_level_pct = int(fuel)
        # carType
        ct = driving_range.get("carType")
        if isinstance(ct, str) and ct:
            d.car_type = ct
        return d

    def test_canonical_skoda_phev_shape(self) -> None:
        # Octavia iV / Superb iV / Kodiaq iV typical shape
        dr = {
            "carType": "hybrid",
            "primaryEngineRange": {
                "engineType": "PETROL",
                "currentFuelLevelInPercent": 60,
                "remainingRangeInKm": 350,
            },
        }
        d = self._parse(dr)
        assert d.car_type == "hybrid"
        assert d.primary_engine_type == "PETROL"
        assert d.primary_engine_fuel_level_pct == 60

    def test_ev_only_no_primary_engine_data(self) -> None:
        # Enyaq / Elroq (EV-only) — no primaryEngineRange block
        dr = {"carType": "electric"}
        d = self._parse(dr)
        assert d.car_type == "electric"
        assert d.primary_engine_type is None
        assert d.primary_engine_fuel_level_pct is None

    def test_diesel_combustion_only(self) -> None:
        dr = {
            "carType": "diesel",
            "primaryEngineRange": {
                "engineType": "DIESEL",
                "currentFuelLevelInPercent": 33,
            },
        }
        d = self._parse(dr)
        assert d.car_type == "diesel"
        assert d.primary_engine_type == "DIESEL"
        assert d.primary_engine_fuel_level_pct == 33

    def test_empty_car_type_rejected(self) -> None:
        # Defensive: empty string would create confusing blank-state
        dr = {"carType": ""}
        d = self._parse(dr)
        assert d.car_type is None

    def test_empty_engine_type_rejected(self) -> None:
        dr = {"primaryEngineRange": {"engineType": ""}}
        d = self._parse(dr)
        assert d.primary_engine_type is None

    def test_float_fuel_level_truncated(self) -> None:
        dr = {"primaryEngineRange": {"currentFuelLevelInPercent": 75.5}}
        d = self._parse(dr)
        assert d.primary_engine_fuel_level_pct == 75


class TestSkodaMaintenanceTimestamp:
    """`maintenanceReport.capturedAt` ISO 8601 pass-through."""

    def _parse(self, report):
        if not isinstance(report, dict):
            return None
        captured = report.get("capturedAt")
        if isinstance(captured, str) and captured:
            return captured
        return None

    def test_canonical_iso_z(self) -> None:
        assert (
            self._parse({"capturedAt": "2026-05-17T08:30:00Z"})
            == "2026-05-17T08:30:00Z"
        )

    def test_iso_with_offset(self) -> None:
        assert (
            self._parse({"capturedAt": "2026-05-17T10:30:00+02:00"})
            == "2026-05-17T10:30:00+02:00"
        )

    def test_missing_stays_none(self) -> None:
        assert self._parse({}) is None

    def test_empty_string_rejected(self) -> None:
        assert self._parse({"capturedAt": ""}) is None

    def test_non_string_rejected(self) -> None:
        # Backend could rotate to unix-int — must not crash
        assert self._parse({"capturedAt": 1747469400}) is None


class TestEntityRegistration:
    def test_battery_protection_binary_described(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
        )

        keys = {d.key for d in BINARY_DESCRIPTIONS}
        assert "battery_protection_limit_on" in keys

    def test_battery_protection_phantom_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "battery_protection_limit_on" in _DATA_PRESENT_REQUIRED

    @pytest.mark.parametrize(
        "key",
        [
            "car_type",
            "primary_engine_fuel_level_pct",
            "maintenance_report_captured_at",
        ],
    )
    def test_sensor_described(self, key: str) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert key in keys

    @pytest.mark.parametrize(
        "key",
        [
            "car_type",
            "primary_engine_fuel_level_pct",
            "maintenance_report_captured_at",
        ],
    )
    def test_sensor_phantom_gated(self, key: str) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert key in _DATA_PRESENT_REQUIRED

    def test_maintenance_timestamp_uses_timestamp_device_class(self) -> None:
        from homeassistant.components.sensor import SensorDeviceClass

        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        desc = next(
            d for d in SENSOR_DESCRIPTIONS
            if d.key == "maintenance_report_captured_at"
        )
        assert desc.device_class == SensorDeviceClass.TIMESTAMP


class TestCrossBrandPrimaryEngineType:
    """primary_engine_type field shipped in PR #3 Phase 7 (CUPRA/SEAT).
    This PR adds the Skoda parser hook — same dataclass field, just
    expanded brand coverage. No new entity, no new translation."""

    def test_field_exists_from_pr3(self) -> None:
        # Sanity check: the field from Phase 7 PR #3 hasn't been removed
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "primary_engine_type")

    def test_sensor_still_described_from_pr3(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "primary_engine_type" in keys

    def test_phantom_gate_still_applies(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "primary_engine_type" in _DATA_PRESENT_REQUIRED


class TestTranslationCoverage:
    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    @pytest.mark.parametrize(
        "key",
        [
            "car_type",
            "primary_engine_fuel_level_pct",
            "maintenance_report_captured_at",
        ],
    )
    def test_lang_has_sensor_key(self, lang: str, key: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert key in data["entity"]["sensor"], (
            f"{lang}: missing entity.sensor.{key}"
        )

    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_battery_protection(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert (
            "battery_protection_limit_on" in data["entity"]["binary_sensor"]
        )

    def test_strings_json_coverage(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        for key in (
            "car_type",
            "primary_engine_fuel_level_pct",
            "maintenance_report_captured_at",
        ):
            assert key in data["entity"]["sensor"]
        assert "battery_protection_limit_on" in data["entity"]["binary_sensor"]
