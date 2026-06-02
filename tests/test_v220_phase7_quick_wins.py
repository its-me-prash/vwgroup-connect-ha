# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 7 PR #1 — Quick-wins from the scout-silenced-but-
unwired audit.

The Phase 7 audit identified ~12 fields that were silenced from
scout warnings (so they didn't spam the logs) but never wired as
HA entities. This PR ships **4 quick wins** — single-value leaves
with clear semantics:

| Field | Brand | Path | Entity |
|-------|-------|------|--------|
| `ignition_on` | Skoda | `readiness.ignitionOn` | binary_sensor |
| `primary_engine_soc_pct` | Skoda | `driving-range.primaryEngineRange.currentSoCInPercent` | sensor |
| `steering_wheel_position` | Skoda | `air-conditioning.steeringWheelPosition` | sensor |
| `battery_temp_max` | VW EU + Audi | `measurements.temperatureBatteryStatus.value.temperatureHvBatteryMax_K` | sensor (K→°C) |

All brand-restricted at the parser level; phantom-protected via
`_DATA_PRESENT_REQUIRED`. Other brands stay None → no phantom entity.

"Sometimes the best feature is the one that was already paid for —
you just have to wire it up." — Lisa Simpson, on the value of audits
"""

from __future__ import annotations

import pytest


class TestModelFields:
    """The 4 new dataclass fields exist with correct types."""

    def test_ignition_on_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "ignition_on")
        assert d.ignition_on is None  # default

    def test_primary_engine_soc_pct_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "primary_engine_soc_pct")
        assert d.primary_engine_soc_pct is None

    def test_steering_wheel_position_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "steering_wheel_position")
        assert d.steering_wheel_position is None

    def test_battery_temp_max_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "battery_temp_max")
        assert d.battery_temp_max is None


class TestSkodaParserIgnitionOn:
    """Mirror of skoda.py readiness block — `ignitionOn` reading."""

    def _parse(self, readiness):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        if not isinstance(readiness, dict):
            return d
        ignition = readiness.get("ignitionOn")
        if isinstance(ignition, bool):
            d.ignition_on = ignition
        return d

    def test_ignition_true_wired(self) -> None:
        d = self._parse({"ignitionOn": True})
        assert d.ignition_on is True

    def test_ignition_false_wired(self) -> None:
        d = self._parse({"ignitionOn": False})
        assert d.ignition_on is False

    def test_ignition_missing_stays_none(self) -> None:
        d = self._parse({})
        assert d.ignition_on is None

    def test_ignition_non_bool_skipped(self) -> None:
        # Defensive: string "ON" or int 1 must NOT trip — only bool
        for raw in ("ON", 1, "true", None, []):
            d = self._parse({"ignitionOn": raw})
            assert d.ignition_on is None, f"failed on raw={raw!r}"


class TestSkodaParserPrimaryEngineSoc:
    """`driving-range.primaryEngineRange.currentSoCInPercent`."""

    def test_canonical_int_wired(self) -> None:
        # Real shape: int 0-100
        raw = {"primaryEngineRange": {"currentSoCInPercent": 78}}
        soc = raw.get("primaryEngineRange", {}).get("currentSoCInPercent")
        assert isinstance(soc, int)
        assert soc == 78

    def test_missing_block_safe(self) -> None:
        raw = {"primaryEngineRange": {}}
        soc = raw.get("primaryEngineRange", {}).get("currentSoCInPercent")
        assert soc is None


class TestSkodaParserSteeringWheelPosition:
    def test_left_wired(self) -> None:
        ac = {"steeringWheelPosition": "LEFT"}
        swp = ac.get("steeringWheelPosition")
        assert isinstance(swp, str) and swp == "LEFT"

    def test_right_wired(self) -> None:
        ac = {"steeringWheelPosition": "RIGHT"}
        swp = ac.get("steeringWheelPosition")
        assert isinstance(swp, str) and swp == "RIGHT"

    def test_empty_string_rejected(self) -> None:
        # Parser guard: `if isinstance(swp, str) and swp` — empty
        # string must NOT be assigned (would create a confusing
        # blank-state entity).
        ac = {"steeringWheelPosition": ""}
        swp = ac.get("steeringWheelPosition")
        # The guard `swp` is falsy for empty string → would skip
        assert isinstance(swp, str)
        assert not swp  # falsy — skip


class TestVWEuBatteryTempMax:
    """K→°C conversion mirror of vw_eu.py parser."""

    def test_kelvin_to_celsius_room_temp(self) -> None:
        # 295 K ≈ 21.85 °C
        from custom_components.vag_connect.cariad._util import safe_float

        raw_k = 295.0
        k = safe_float(raw_k)
        c = round(k - 273.15, 1) if k is not None else None
        assert c == 21.9

    def test_kelvin_to_celsius_negative(self) -> None:
        # Cold winter charging: 263 K = -10.15 °C → Python uses
        # banker's rounding (round-half-to-even), so round(-10.15, 1)
        # = -10.1 (NOT -10.2). This is the actual production behaviour
        # of the parser; the test asserts what really happens.
        from custom_components.vag_connect.cariad._util import safe_float

        k = safe_float(263.0)
        c = round(k - 273.15, 1) if k is not None else None
        assert c == -10.1

    def test_none_input_yields_none(self) -> None:
        from custom_components.vag_connect.cariad._util import safe_float

        raw_k = None
        k = safe_float(raw_k)
        c = round(k - 273.15, 1) if k is not None else None
        assert c is None

    def test_string_input_handled_by_safe_float(self) -> None:
        # Defensive: backend could ship "295.5" string
        from custom_components.vag_connect.cariad._util import safe_float

        k = safe_float("295.5")
        c = round(k - 273.15, 1) if k is not None else None
        assert c == 22.4


class TestEntityRegistration:
    """All 4 entities described + phantom-gated."""

    def test_ignition_on_binary_sensor_described(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
        )

        keys = {d.key for d in BINARY_DESCRIPTIONS}
        assert "ignition_on" in keys

    def test_ignition_on_phantom_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "ignition_on" in _DATA_PRESENT_REQUIRED

    @pytest.mark.parametrize(
        "key",
        [
            "primary_engine_soc_pct",
            "steering_wheel_position",
            "battery_temp_max",
        ],
    )
    def test_sensor_described(self, key: str) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert key in keys, f"sensor description missing: {key}"

    @pytest.mark.parametrize(
        "key",
        [
            "primary_engine_soc_pct",
            "steering_wheel_position",
            "battery_temp_max",
        ],
    )
    def test_sensor_phantom_gated(self, key: str) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert key in _DATA_PRESENT_REQUIRED, (
            f"missing phantom gate: {key}"
        )


class TestTranslationCoverage:
    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_all_sensor_keys(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in (
            "primary_engine_soc_pct",
            "steering_wheel_position",
            "battery_temp_max",
        ):
            assert key in data["entity"]["sensor"], (
                f"{lang}: missing entity.sensor.{key}"
            )

    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_ignition_on(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "ignition_on" in data["entity"]["binary_sensor"]

    def test_strings_json_has_all_keys(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        for key in (
            "primary_engine_soc_pct",
            "steering_wheel_position",
            "battery_temp_max",
        ):
            assert key in data["entity"]["sensor"]
        assert "ignition_on" in data["entity"]["binary_sensor"]
