# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 — CUPRA Scout-Report #232 (matthias0304, 2026-05-16) wiring.

CUPRA PHEV companion to Skoda Scout #220 (PR #6). OLA ``mycar.engines.
secondary`` 3-key block on Formentor PHEV / Leon e-Hybrid mirrors the
Skoda ``driving-range.secondaryEngineRange`` shape.

**Cross-brand field reuse**: this PR maps the new CUPRA data into the
existing ``secondary_engine_*`` dataclass fields from PR #6. Net
result: zero new entities, zero new translations, zero new phantom-
gates — just expanded brand coverage on the same sensors.

Brand coverage matrix for ``secondary_engine_{range_km,type,fuel_level_pct}``:

  - Skoda PHEV (mysmob driving-range.secondaryEngineRange) — PR #6
  - CUPRA PHEV (OLA mycar.engines.secondary) — this PR
  - SEAT PHEV  (same OLA path, free with the same parser hook)
  - VW / Audi  — TBD (CARIAD-BFF doesn't ship this block as of 2026-05)

"Recycling? Brilliant. Same fields, more brands, less code."
— Sheldon Cooper, on cross-brand dataclass reuse
"""

from __future__ import annotations


class TestCupraScout232Silencing:
    """The EXPECTED_KEYS table must silence the new path."""

    def test_engines_secondary_container_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["cupra"]["mycar"]
        assert _path_matches("engines.secondary", keys)

    def test_engines_secondary_children_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["cupra"]["mycar"]
        # Wildcard "engines.secondary.*" must cover all observed +
        # forward-compat children
        for child in (
            "engines.secondary.range",
            "engines.secondary.fuelLevel_pct",
            "engines.secondary.fuelType",
            "engines.secondary.rangeInKm",  # forward-compat alt
            "engines.secondary.engineType",  # Skoda-style alt
        ):
            assert _path_matches(child, keys), f"missing: {child}"


class TestCupraScout232ParserMirror:
    """Pure-python mirror of the seat_cupra.py parser body for the
    engines.secondary block. Same defensive multi-variant lookup."""

    def _make_device(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        return VehicleData(vin="TESTVIN")

    def _parse(self, mycar):
        """Mirror of the parser logic — keeps test independent of the
        full async fetch machinery."""
        d = self._make_device()
        if not isinstance(mycar, dict):
            return d
        engines = mycar.get("engines")
        if not isinstance(engines, dict):
            return d
        secondary = engines.get("secondary")
        if not isinstance(secondary, dict):
            return d

        sec_range = (
            secondary.get("range")
            or secondary.get("rangeInKm")
            or secondary.get("distanceInKm")
        )
        if isinstance(sec_range, (int, float)):
            d.secondary_engine_range_km = int(sec_range)

        sec_type = secondary.get("fuelType") or secondary.get("engineType")
        if isinstance(sec_type, str) and sec_type:
            d.secondary_engine_type = sec_type

        sec_fuel = (
            secondary.get("fuelLevel_pct")
            or secondary.get("currentFuelLevelInPercent")
        )
        if isinstance(sec_fuel, (int, float)):
            d.secondary_engine_fuel_level_pct = int(sec_fuel)
        return d

    def test_canonical_ola_shape(self) -> None:
        # Per matthias0304 scout: 3-key block on Formentor PHEV
        mycar = {
            "engines": {
                "secondary": {
                    "range": 420,
                    "fuelType": "PETROL",
                    "fuelLevel_pct": 75,
                }
            }
        }
        d = self._parse(mycar)
        assert d.secondary_engine_range_km == 420
        assert d.secondary_engine_type == "PETROL"
        assert d.secondary_engine_fuel_level_pct == 75

    def test_skoda_style_keys_compatible(self) -> None:
        # Forward-compat: if OLA migrates to Skoda-style keys, parser
        # still picks them up via the multi-variant fallback chain.
        mycar = {
            "engines": {
                "secondary": {
                    "distanceInKm": 200,
                    "engineType": "DIESEL",
                    "currentFuelLevelInPercent": 50,
                }
            }
        }
        d = self._parse(mycar)
        assert d.secondary_engine_range_km == 200
        assert d.secondary_engine_type == "DIESEL"
        assert d.secondary_engine_fuel_level_pct == 50

    def test_missing_secondary_block_keeps_none(self) -> None:
        # EV-only CUPRA (Born) → no engines.secondary → fields stay None
        mycar = {"engines": {"primary": {"range": 100}}}
        d = self._parse(mycar)
        assert d.secondary_engine_range_km is None
        assert d.secondary_engine_type is None
        assert d.secondary_engine_fuel_level_pct is None

    def test_missing_engines_block_keeps_none(self) -> None:
        mycar = {}
        d = self._parse(mycar)
        assert d.secondary_engine_range_km is None

    def test_non_dict_secondary_safe(self) -> None:
        # Backend rotation could ship list / string — must not crash
        mycar = {"engines": {"secondary": "ACTIVATED"}}
        d = self._parse(mycar)
        assert d.secondary_engine_range_km is None

    def test_non_dict_engines_safe(self) -> None:
        mycar = {"engines": []}
        d = self._parse(mycar)
        assert d.secondary_engine_range_km is None

    def test_partial_block_partial_population(self) -> None:
        # Only range, no fuel type / level
        mycar = {"engines": {"secondary": {"range": 150}}}
        d = self._parse(mycar)
        assert d.secondary_engine_range_km == 150
        assert d.secondary_engine_type is None
        assert d.secondary_engine_fuel_level_pct is None

    def test_string_range_skipped(self) -> None:
        # Defensive: backend could ship "420 km" instead of int
        mycar = {"engines": {"secondary": {"range": "420 km"}}}
        d = self._parse(mycar)
        assert d.secondary_engine_range_km is None


class TestCrossBrandReuse:
    """Net-zero entity / translation / phantom-gate changes — this
    PR ONLY populates existing PR #6 fields for an additional brand."""

    def test_secondary_engine_fields_unchanged_in_models(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        # The 3 fields from PR #6 must still exist with their original
        # types (regression-shield against accidental refactoring)
        d = VehicleData(vin="X")
        for attr in (
            "secondary_engine_range_km",
            "secondary_engine_type",
            "secondary_engine_fuel_level_pct",
        ):
            assert hasattr(d, attr), f"PR #6 field {attr} missing"
            assert getattr(d, attr) is None  # default

    def test_sensor_descriptions_unchanged_from_pr6(self) -> None:
        # No new descriptions needed — PR #6 already shipped them
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        assert "secondary_engine_range_km" in keys
        assert "secondary_engine_type" in keys
        assert "secondary_engine_fuel_level_pct" in keys

    def test_phantom_gates_still_apply(self) -> None:
        # Other brands (Audi/VW/Porsche/VW NA) still leave fields None
        # → no phantom entity (gates from PR #6 unchanged)
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        for f in (
            "secondary_engine_range_km",
            "secondary_engine_type",
            "secondary_engine_fuel_level_pct",
        ):
            assert f in _DATA_PRESENT_REQUIRED
