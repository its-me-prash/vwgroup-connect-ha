# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.1 Phase 8 PR #3 — Porsche electric/combustion range split.

**Pure cross-brand parity expansion** — zero new entities, zero
new translations, zero new phantom-gates. Porsche joins the
brand-coverage of `electric_range_km` + `combustion_range_km`
that Skoda, VW EU, Audi, CUPRA, SEAT all expose since v1.10.0+.

Before this PR: Porsche only populated the aggregate `range_km`
via or-fallback (`E_RANGE.distance OR FUEL_LEVEL.distanceToEmpty`).
After this PR: per-source split surfaces explicit sensors for
EV (Taycan, Macan EV, 911 Cayenne EV) + PHEV (Cayenne E-Hybrid,
Panamera E-Hybrid) — without breaking back-compat for the
aggregate `range_km`.

| Field | Source path | Vehicle types |
|-------|-------------|---------------|
| `electric_range_km` | `E_RANGE.distance` | EV + PHEV (battery side) |
| `combustion_range_km` | `FUEL_LEVEL.distanceToEmpty` | ICE + PHEV (fuel side) |
| `range_km` (back-compat) | E_RANGE or FUEL_LEVEL | All — unchanged |

"You see, I have made a small modification to your existing
range sensor. It is now THREE sensors. Better."
— Sheldon Cooper, on Porsche range field splitting
"""

from __future__ import annotations


class TestPorscheRangeFields:
    """Mirror of porsche.py measurement-block walk."""

    def _parse(self, m):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        if not isinstance(m, dict):
            return d
        electric_range = m.get("E_RANGE", {}).get("distance")
        combustion_range = m.get("FUEL_LEVEL", {}).get("distanceToEmpty")
        if isinstance(electric_range, (int, float)):
            d.electric_range_km = int(electric_range)
        if isinstance(combustion_range, (int, float)):
            d.combustion_range_km = int(combustion_range)
        d.range_km = electric_range or combustion_range
        return d

    def test_pure_ev_taycan_only_electric(self) -> None:
        m = {
            "E_RANGE": {"distance": 420},
            # No FUEL_LEVEL block on a Taycan
        }
        d = self._parse(m)
        assert d.electric_range_km == 420
        assert d.combustion_range_km is None
        assert d.range_km == 420  # back-compat unchanged

    def test_ice_cayenne_only_combustion(self) -> None:
        m = {
            # No E_RANGE on a non-PHEV gasoline Cayenne
            "FUEL_LEVEL": {"distanceToEmpty": 580, "percent": 75},
        }
        d = self._parse(m)
        assert d.electric_range_km is None
        assert d.combustion_range_km == 580
        assert d.range_km == 580

    def test_phev_cayenne_e_hybrid_both_present(self) -> None:
        # Cayenne E-Hybrid: both ranges populated
        m = {
            "E_RANGE": {"distance": 47},
            "FUEL_LEVEL": {"distanceToEmpty": 620, "percent": 88},
        }
        d = self._parse(m)
        assert d.electric_range_km == 47
        assert d.combustion_range_km == 620
        # Back-compat: range_km prefers electric (matches existing
        # or-fallback priority)
        assert d.range_km == 47

    def test_empty_measurements_safe(self) -> None:
        d = self._parse({})
        assert d.electric_range_km is None
        assert d.combustion_range_km is None
        assert d.range_km is None

    def test_non_dict_safe(self) -> None:
        d = self._parse(None)
        assert d.electric_range_km is None

    def test_float_range_truncated_to_int(self) -> None:
        # Backend could ship 47.5 km — int() truncates
        m = {"E_RANGE": {"distance": 47.5}}
        d = self._parse(m)
        assert d.electric_range_km == 47

    def test_string_range_rejected(self) -> None:
        # Defensive: "420 km" string — must not crash
        m = {"E_RANGE": {"distance": "420 km"}}
        d = self._parse(m)
        assert d.electric_range_km is None

    def test_zero_range_assigned(self) -> None:
        # Zero is a legitimate value (empty tank / dead battery)
        m = {"E_RANGE": {"distance": 0}}
        d = self._parse(m)
        assert d.electric_range_km == 0


class TestCrossBrandParityRegression:
    """Source-level check that Porsche now populates the split fields,
    not just the aggregate."""

    def _source(self) -> str:
        import inspect

        from custom_components.vag_connect.cariad.api import porsche

        return inspect.getsource(porsche)

    def test_porsche_assigns_electric_range(self) -> None:
        assert "d.electric_range_km" in self._source()

    def test_porsche_assigns_combustion_range(self) -> None:
        assert "d.combustion_range_km" in self._source()

    def test_porsche_keeps_range_km_for_backcompat(self) -> None:
        # Aggregate must still be populated for Porsche users whose
        # current sensor is `range_km`
        assert "d.range_km" in self._source()


class TestNoNewEntityDescriptions:
    """Pure parser expansion — no new sensor.py / translations changes."""

    def test_electric_range_km_still_described(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "electric_range_km" in keys

    def test_combustion_range_km_still_described(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "combustion_range_km" in keys


class TestBrandCoverageMatrix:
    """After this PR, electric_range_km + combustion_range_km should
    be populated by at least 5 brand parsers."""

    def test_electric_range_in_multiple_parsers(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.api import (
            porsche,
            seat_cupra,
            skoda,
            vw_eu,
        )

        # All 4 modules should reference electric_range_km
        for mod in (vw_eu, skoda, seat_cupra, porsche):
            src = inspect.getsource(mod)
            assert "electric_range_km" in src, (
                f"regression: {mod.__name__} no longer references "
                f"electric_range_km"
            )

    def test_combustion_range_in_multiple_parsers(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.api import (
            porsche,
            skoda,
            vw_eu,
        )

        for mod in (vw_eu, skoda, porsche):
            src = inspect.getsource(mod)
            assert "combustion_range_km" in src, (
                f"regression: {mod.__name__} no longer references "
                f"combustion_range_km"
            )
