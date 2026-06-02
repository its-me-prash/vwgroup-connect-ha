# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.1 Phase 8 PR #4 — VW EU/Audi primary_engine_fuel_level_pct mirror.

Pure cross-brand expansion. Skoda has `primary_engine_fuel_level_pct`
from `driving-range.primaryEngineRange.currentFuelLevelInPercent`
(Phase 8 PR #1 today). This PR adds the VW EU/Audi parser hook
using the existing per-engine walker pattern from PR #2.

Walker now assigns BOTH:
- `primary_engine_fuel_level_pct` when primary engine is combustion
  (Golf 7 GTE older firmware: primary=gasoline; modern ICE-only cars)
- `secondary_engine_fuel_level_pct` when secondary engine is
  combustion (modern PHEV: primary=electric, secondary=gasoline)

This unifies the engine-fuel-level coverage across all Cariad-BFF
brands without speculation. Audi inherits via class inheritance.

"Now we have one walker doing the job of two. Just like Penny on
date night with two text conversations."
— Sheldon Cooper, on consolidated parser logic
"""

from __future__ import annotations


class TestModelFieldExists:
    """The field was added in Phase 8 PR #1 (Skoda). VW EU/Audi
    expansion uses the same dataclass field — pure cross-brand."""

    def test_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "primary_engine_fuel_level_pct")


class TestEngineWalkerBothPositions:
    """The walker now handles BOTH primary AND secondary engine
    blocks — assigns based on position + combustion-type check."""

    def _walk(self, raw):
        # Mirror of production logic in vw_eu.py
        from custom_components.vag_connect.cariad._util import safe_int
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        combustion_types = {"gasoline", "petrol", "diesel", "gas", "cng", "lpg"}
        for engine_path in (
            ("fuelStatus", "rangeStatus", "value", "primaryEngine"),
            ("fuelStatus", "rangeStatus", "value", "secondaryEngine"),
        ):
            block = raw
            for part in engine_path:
                if not isinstance(block, dict):
                    block = None
                    break
                block = block.get(part)
            if not isinstance(block, dict):
                continue
            etype = (block.get("type") or "").lower()
            if etype not in combustion_types:
                continue
            fuel = safe_int(block.get("currentFuelLevel_pct"))
            if fuel is None:
                continue
            position = engine_path[-1]
            if position == "primaryEngine":
                d.primary_engine_fuel_level_pct = fuel
            elif position == "secondaryEngine":
                d.secondary_engine_fuel_level_pct = fuel
        return d

    def test_ice_only_primary_gasoline(self) -> None:
        # Pre-PHEV ICE-only Golf: primary=gasoline, no secondary
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "gasoline",
                            "currentFuelLevel_pct": 75,
                        },
                    }
                }
            }
        }
        d = self._walk(raw)
        assert d.primary_engine_fuel_level_pct == 75
        assert d.secondary_engine_fuel_level_pct is None

    def test_modern_phev_electric_primary_gasoline_secondary(self) -> None:
        # Passat GTE current firmware: primary=electric, secondary=gasoline
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "electric",
                            "currentSOC_pct": 80,
                        },
                        "secondaryEngine": {
                            "type": "gasoline",
                            "currentFuelLevel_pct": 65,
                        },
                    }
                }
            }
        }
        d = self._walk(raw)
        assert d.primary_engine_fuel_level_pct is None
        assert d.secondary_engine_fuel_level_pct == 65

    def test_legacy_golf_gte_2015_flipped(self) -> None:
        # Golf 7 GTE 2015: primary=gasoline, secondary=electric
        # (per v1.11.1 #96 docs — Cariad flipped positions later)
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "gasoline",
                            "currentFuelLevel_pct": 50,
                        },
                        "secondaryEngine": {
                            "type": "electric",
                            "currentSOC_pct": 30,
                        },
                    }
                }
            }
        }
        d = self._walk(raw)
        # Position matters: primary gets assigned regardless of which
        # side is the EV/combustion — semantically correct.
        assert d.primary_engine_fuel_level_pct == 50
        assert d.secondary_engine_fuel_level_pct is None

    def test_diesel_primary(self) -> None:
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "diesel",
                            "currentFuelLevel_pct": 90,
                        },
                    }
                }
            }
        }
        d = self._walk(raw)
        assert d.primary_engine_fuel_level_pct == 90

    def test_pure_ev_no_fuel_at_all(self) -> None:
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "electric",
                            "currentSOC_pct": 85,
                        },
                    }
                }
            }
        }
        d = self._walk(raw)
        assert d.primary_engine_fuel_level_pct is None
        assert d.secondary_engine_fuel_level_pct is None

    def test_missing_fuel_pct_skipped(self) -> None:
        # Backend rotation: engine type ships but currentFuelLevel_pct
        # missing — must skip silently, no crash
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {"type": "gasoline"},
                    }
                }
            }
        }
        d = self._walk(raw)
        assert d.primary_engine_fuel_level_pct is None

    def test_error_container_safe(self) -> None:
        # fuelStatus.rangeStatus rotated to .error container
        # (Phase 7 PR #5 #245) — walker safely skips
        raw = {"fuelStatus": {"rangeStatus": {"error": {"code": 503}}}}
        d = self._walk(raw)
        assert d.primary_engine_fuel_level_pct is None
        assert d.secondary_engine_fuel_level_pct is None


class TestSourceLevelWiring:
    """vw_eu.py parser now assigns to both primary AND secondary
    fields in the same walker."""

    def _source(self) -> str:
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        return inspect.getsource(vw_eu)

    def test_walker_assigns_primary(self) -> None:
        src = self._source()
        assert "d.primary_engine_fuel_level_pct = fuel_pct" in src

    def test_walker_assigns_secondary(self) -> None:
        src = self._source()
        assert "d.secondary_engine_fuel_level_pct = fuel_pct" in src

    def test_walker_uses_position_check(self) -> None:
        # Position string check must be present (semantic correctness)
        src = self._source()
        assert "primaryEngine" in src and "secondaryEngine" in src


class TestCrossBrandCoverageMatrix:
    """After this PR, primary_engine_fuel_level_pct should be wired
    by at least 2 brand parsers (Skoda + VW EU/Audi)."""

    def test_field_referenced_in_skoda(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.api import skoda

        assert "primary_engine_fuel_level_pct" in inspect.getsource(skoda)

    def test_field_referenced_in_vw_eu(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        assert "primary_engine_fuel_level_pct" in inspect.getsource(vw_eu)
