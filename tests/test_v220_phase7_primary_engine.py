# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 7 PR #3 — SEAT/CUPRA `engines.primary` wiring.

Companion to PR #6/#18 `secondary_engine_*` fields. Silenced via
wildcard `engines.primary.*` since v1.16.1 (#122 r1150gs SEAT scout
2026-05-02 — "3 keys observed") but never parsed.

| Field | Path |
|-------|------|
| `primary_engine_type` | `mycar.engines.primary.{fuelType,engineType}` |
| `fuel_tank_capacity_liters` | `mycar.engines.primary.{tankCapacity,tankCapacityInLiters,tankSize}` |

Multi-variant lookup mirrors the secondary block — OLA has historically
shipped alternative spellings, parser handles both directions.

"Now if you'll excuse me, I have a tank of unleaded to monitor."
— Sheldon Cooper, on fuel-capacity sensors
"""

from __future__ import annotations

import pytest


class TestModelFields:
    def test_primary_engine_type_default(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "primary_engine_type")
        assert d.primary_engine_type is None

    def test_fuel_tank_capacity_liters_default(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "fuel_tank_capacity_liters")
        assert d.fuel_tank_capacity_liters is None


class TestPrimaryEngineParser:
    """Mirror of seat_cupra.py primary block."""

    def _parse(self, mycar):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        if not isinstance(mycar, dict):
            return d
        engines = mycar.get("engines")
        if not isinstance(engines, dict):
            return d
        primary = engines.get("primary")
        if not isinstance(primary, dict):
            return d
        primary_type = primary.get("fuelType") or primary.get("engineType")
        if isinstance(primary_type, str) and primary_type:
            d.primary_engine_type = primary_type
        tank_cap = (
            primary.get("tankCapacity")
            or primary.get("tankCapacityInLiters")
            or primary.get("tankSize")
        )
        if isinstance(tank_cap, (int, float)) and tank_cap > 0:
            d.fuel_tank_capacity_liters = int(tank_cap)
        return d

    def test_canonical_ola_shape(self) -> None:
        mycar = {
            "engines": {
                "primary": {
                    "fuelType": "PETROL",
                    "tankCapacity": 50,
                    "range": 700,  # ignored — handled by ranges block
                }
            }
        }
        d = self._parse(mycar)
        assert d.primary_engine_type == "PETROL"
        assert d.fuel_tank_capacity_liters == 50

    def test_skoda_style_keys_compatible(self) -> None:
        # Forward-compat: OLA might rotate to Skoda-style spellings
        mycar = {
            "engines": {
                "primary": {
                    "engineType": "DIESEL",
                    "tankCapacityInLiters": 60,
                }
            }
        }
        d = self._parse(mycar)
        assert d.primary_engine_type == "DIESEL"
        assert d.fuel_tank_capacity_liters == 60

    def test_alternative_tank_size_key(self) -> None:
        mycar = {"engines": {"primary": {"fuelType": "PETROL", "tankSize": 55}}}
        d = self._parse(mycar)
        assert d.fuel_tank_capacity_liters == 55

    def test_missing_primary_block_keeps_none(self) -> None:
        mycar = {"engines": {"secondary": {"range": 200}}}
        d = self._parse(mycar)
        assert d.primary_engine_type is None
        assert d.fuel_tank_capacity_liters is None

    def test_missing_engines_block_keeps_none(self) -> None:
        d = self._parse({})
        assert d.primary_engine_type is None

    def test_zero_tank_capacity_skipped(self) -> None:
        # Defensive: backend has shipped 0 on EV-only variants where
        # the field is technically there but meaningless. Guard rejects.
        mycar = {"engines": {"primary": {"fuelType": "ELECTRIC", "tankCapacity": 0}}}
        d = self._parse(mycar)
        assert d.primary_engine_type == "ELECTRIC"
        assert d.fuel_tank_capacity_liters is None

    def test_string_tank_capacity_rejected(self) -> None:
        mycar = {"engines": {"primary": {"tankCapacity": "50L"}}}
        d = self._parse(mycar)
        assert d.fuel_tank_capacity_liters is None

    def test_empty_fuel_type_rejected(self) -> None:
        mycar = {"engines": {"primary": {"fuelType": ""}}}
        d = self._parse(mycar)
        assert d.primary_engine_type is None

    def test_float_tank_capacity_truncated_to_int(self) -> None:
        # 50.5 liters → int 50 (defensive int-truncation matches
        # the production parser logic)
        mycar = {"engines": {"primary": {"tankCapacity": 50.5}}}
        d = self._parse(mycar)
        assert d.fuel_tank_capacity_liters == 50

    def test_non_dict_primary_safe(self) -> None:
        mycar = {"engines": {"primary": "ACTIVATED"}}
        d = self._parse(mycar)
        assert d.primary_engine_type is None
        assert d.fuel_tank_capacity_liters is None


class TestEntityRegistration:
    @pytest.mark.parametrize(
        "key", ["primary_engine_type", "fuel_tank_capacity_liters"]
    )
    def test_sensor_described(self, key: str) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert key in keys

    @pytest.mark.parametrize(
        "key", ["primary_engine_type", "fuel_tank_capacity_liters"]
    )
    def test_sensor_phantom_gated(self, key: str) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert key in _DATA_PRESENT_REQUIRED


class TestTranslationCoverage:
    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    @pytest.mark.parametrize(
        "key", ["primary_engine_type", "fuel_tank_capacity_liters"]
    )
    def test_lang_has_key(self, lang: str, key: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert key in data["entity"]["sensor"], (
            f"{lang}: missing entity.sensor.{key}"
        )

    def test_strings_json_coverage(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        for key in ("primary_engine_type", "fuel_tank_capacity_liters"):
            assert key in data["entity"]["sensor"]
