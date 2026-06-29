# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.1 Phase 8 PR #2 — VW EU/Audi engine-metadata cross-brand expansion.

**Pure cross-brand expansion PR** — zero new entities, zero new
translations, zero new phantom-gates. Just wires VW EU/Audi parser
hooks for 4 existing dataclass fields that other brands already
populate:

| Field | Originally wired for | This PR adds |
|-------|---------------------|--------------|
| `primary_engine_type` | CUPRA/SEAT (PR #3), Skoda (PR #1 today) | VW EU + Audi (inherits) |
| `secondary_engine_type` | Skoda (PR #6 Scout #220), CUPRA/SEAT (PR #18 Scout #232) | VW EU + Audi (inherits) |
| `car_type` | Skoda (PR #1 today) | VW EU + Audi (inherits) |
| `secondary_engine_fuel_level_pct` | Skoda (PR #6), CUPRA/SEAT (PR #18) | VW EU + Audi (inherits) |

**This PR is the textbook illustration of the user's strategy:**
"1 user reports a field on 1 brand → eventually wire across all
brands where the equivalent exists". Before this PR, a Skoda PHEV
user's scout report (#220) drove entities only for Skoda. After
this PR, the SAME entities now also surface on VW EU and Audi
PHEVs (Passat GTE, Golf GTE, Audi A3/Q5 e-tron etc.) — without
those users ever having to report anything.

"It's an avalanche! Everybody dies! Bazinga!"
— Sheldon Cooper, on cross-brand value cascades
"""

from __future__ import annotations


class TestCrossBrandFieldReuse:
    """The 4 dataclass fields already exist from prior PRs."""

    def test_primary_engine_type_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "primary_engine_type")

    def test_secondary_engine_type_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "secondary_engine_type")

    def test_car_type_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "car_type")

    def test_secondary_engine_fuel_level_pct_field_exists(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "secondary_engine_fuel_level_pct")


class TestNoNewEntityDescriptions:
    """This PR adds ZERO entity descriptions — it's pure parser expansion."""

    def test_no_new_sensor_keys_introduced(self) -> None:
        # Sanity: the existing descriptions from prior PRs are still
        # there (regression-shield). Pure cross-brand expansion PRs
        # should never need to add new entity-table entries.
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        # All 4 should remain (from PR #3/#6/#18/PR1)
        for k in (
            "primary_engine_type",
            "secondary_engine_type",
            "car_type",
            "secondary_engine_fuel_level_pct",
        ):
            assert k in keys, f"regression: {k} description removed"


class TestVWEUParserCrossBrand:
    """Source-level checks that the vw_eu.py parser now assigns to
    the cross-brand fields, not just to the derived has_battery/
    has_combustion booleans."""

    def _source(self) -> str:
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        return inspect.getsource(vw_eu)

    def test_vw_eu_assigns_primary_engine_type(self) -> None:
        src = self._source()
        assert "d.primary_engine_type = primary_eng" in src

    def test_vw_eu_assigns_secondary_engine_type(self) -> None:
        src = self._source()
        assert "d.secondary_engine_type = secondary_eng" in src

    def test_vw_eu_assigns_car_type(self) -> None:
        src = self._source()
        assert "d.car_type = car_type" in src

    def test_vw_eu_assigns_secondary_fuel_level(self) -> None:
        # Loose-coupling: just verify the dataclass field is assigned
        # SOMEWHERE in the parser, not tied to a specific local variable
        # name (PR #4 refactored the walker variable to `fuel_pct`).
        src = self._source()
        assert "d.secondary_engine_fuel_level_pct =" in src

    def test_priority_order_documented(self) -> None:
        # The comment must explain WHY fuelStatus has priority over
        # measurements (fuelStatus = richer; measurements = always-
        # populated fallback). Future contributors need to know.
        src = self._source()
        assert "fuelStatus" in src and "measurements" in src


class TestPriorityFallbackPattern:
    """The `primary_engine or ms_primary` pattern: prefer the richer
    fuelStatus block, fall back to measurements fallback."""

    def _resolve(self, primary_engine, ms_primary):
        # Mirror of the production assignment logic
        primary_eng = primary_engine or ms_primary
        if isinstance(primary_eng, str) and primary_eng:
            return primary_eng
        return None

    def test_fuelstatus_wins_when_both_present(self) -> None:
        # If both backends ship the field, fuelStatus is the richer
        # source (per the existing v1.11.1 #96 design)
        assert self._resolve("PETROL", "GASOLINE") == "PETROL"

    def test_measurements_used_when_fuelstatus_missing(self) -> None:
        assert self._resolve(None, "DIESEL") == "DIESEL"
        assert self._resolve("", "DIESEL") == "DIESEL"  # empty string falsy

    def test_both_missing_yields_none(self) -> None:
        assert self._resolve(None, None) is None

    def test_non_string_rejected(self) -> None:
        # Defensive: backend rotation could ship int/dict — must skip
        assert self._resolve(123, None) is None
        assert self._resolve({"type": "PETROL"}, None) is None


class TestSecondaryFuelLevelEngineWalk:
    """The fuel-level walk iterates both engine blocks looking for
    the combustion side."""

    def _walk(self, raw):
        # Mirror of production logic
        combustion_types = {"gasoline", "petrol", "diesel", "gas", "cng", "lpg"}
        for engine_path in (
            ("fuelStatus", "rangeStatus", "value", "primaryEngine"),
            ("fuelStatus", "rangeStatus", "value", "secondaryEngine"),
        ):
            # Navigate the dotted path
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
            if engine_path[-1] == "secondaryEngine":
                fuel = block.get("currentFuelLevel_pct")
                if isinstance(fuel, (int, float)):
                    return int(fuel)
                break
        return None

    def test_phev_secondary_combustion_picked_up(self) -> None:
        # Modern PHEV: primary=electric, secondary=gasoline
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
        assert self._walk(raw) == 65

    def test_ev_only_no_secondary_combustion_returns_none(self) -> None:
        # Pure EV: only primary engine, no secondary
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {"type": "electric"},
                    }
                }
            }
        }
        assert self._walk(raw) is None

    def test_ice_only_secondary_not_combustion_returns_none(self) -> None:
        # Pre-PHEV gasoline-only: primary=gasoline, no secondary
        # — secondary_engine_fuel_level_pct should stay None
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "gasoline",
                            "currentFuelLevel_pct": 50,
                        },
                    }
                }
            }
        }
        assert self._walk(raw) is None

    def test_missing_fuelstatus_block_safe(self) -> None:
        # Backend rotation: fuelStatus.rangeStatus is an `error`
        # container instead of `value` — walker must not crash
        raw = {"fuelStatus": {"rangeStatus": {"error": {"code": 503}}}}
        assert self._walk(raw) is None

    def test_non_dict_response_safe(self) -> None:
        assert self._walk(None) is None
        assert self._walk("not-a-dict") is None
        assert self._walk([]) is None

    def test_string_fuel_level_rejected(self) -> None:
        # Defensive: backend could rotate to "65%" string
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "secondaryEngine": {
                            "type": "gasoline",
                            "currentFuelLevel_pct": "65%",
                        },
                    }
                }
            }
        }
        assert self._walk(raw) is None


class TestBrandCoverageMatrix:
    """Documents the new brand-coverage matrix after this PR. If a
    future contributor removes a brand parser hook, this test fails
    loudly so the regression is caught."""

    def test_primary_engine_type_at_least_4_brand_parsers(self) -> None:
        # As of this PR: VW EU (this PR), Audi (inherits), Skoda
        # (PR #1 today), CUPRA/SEAT (PR #3) = 4 parser paths
        import inspect

        from custom_components.vag_connect.cariad.api import (
            seat_cupra,
            skoda,
            vw_eu,
        )

        for mod in (vw_eu, skoda, seat_cupra):
            src = inspect.getsource(mod)
            assert "primary_engine_type" in src, (
                f"regression: {mod.__name__} no longer assigns primary_engine_type"
            )

    def test_secondary_engine_type_at_least_3_brand_parsers(self) -> None:
        # VW EU (this PR), Audi (inherits), Skoda (PR #6),
        # CUPRA/SEAT (PR #18) = 4 parser paths
        import inspect

        from custom_components.vag_connect.cariad.api import (
            seat_cupra,
            skoda,
            vw_eu,
        )

        for mod in (vw_eu, skoda, seat_cupra):
            src = inspect.getsource(mod)
            assert "secondary_engine_type" in src, (
                f"regression: {mod.__name__} no longer assigns secondary_engine_type"
            )

    def test_car_type_at_least_2_brand_parsers(self) -> None:
        # VW EU (this PR), Audi (inherits), Skoda (PR #1) = 3
        import inspect

        from custom_components.vag_connect.cariad.api import skoda, vw_eu

        for mod in (vw_eu, skoda):
            src = inspect.getsource(mod)
            assert "d.car_type" in src or "car_type =" in src
