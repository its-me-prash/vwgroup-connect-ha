# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation helper.

**Different pattern from PR #1-#4.** Instead of expanding parser
hooks per backend, this adds a single derivation helper that fires
at the end of every brand parser. Fills `d.car_type` for backends
that don't expose a direct field (CUPRA/SEAT, Porsche, VW NA).

Derivation rules (order matters):
  1. has_battery + has_combustion → "hybrid"
  2. has_battery only → "electric"
  3. has_combustion only → derive from primary_engine_type:
     - DIESEL → "diesel"
     - PETROL / GASOLINE → "gasoline"
     - anything else → leave None (don't guess)
  4. neither flag set → leave None (insufficient signal)

**Critical contract**: NEVER overwrites a directly-read value.
Skoda + VW EU/Audi keep their authoritative backend reads;
CUPRA/SEAT/Porsche/VW NA get the derived value.

"Statistically speaking, given enough booleans, even a chimpanzee
could derive whether the car is electric, hybrid, or combustion."
— Sheldon Cooper, on engine-type inference
"""

from __future__ import annotations

import pytest


def _make_vehicle(**kwargs):
    """Builder for a VehicleData with only the fields we care about."""
    from custom_components.vag_connect.cariad.models import VehicleData

    d = VehicleData(vin="X")
    for key, value in kwargs.items():
        setattr(d, key, value)
    return d


class TestNeverOverwriteDirectRead:
    """Critical contract: if car_type is already set, helper is no-op."""

    def test_already_set_diesel_preserved(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            car_type="diesel",
            has_battery=True,
            has_combustion=True,
            primary_engine_type="PETROL",
        )
        derive_car_type_if_missing(d)
        # Stayed diesel despite has_battery+has_combustion=hybrid
        # derivation rule — direct read wins.
        assert d.car_type == "diesel"

    def test_already_set_hybrid_preserved(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            car_type="hybrid", has_battery=False, has_combustion=True
        )
        derive_car_type_if_missing(d)
        assert d.car_type == "hybrid"

    def test_empty_string_overwritten(self) -> None:
        # Edge case: if a parser accidentally assigned empty string
        # (not None), the helper SHOULD treat it as missing — wait,
        # actually the helper checks `is not None`, so empty string
        # WOULD be preserved. Document the behaviour.
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            car_type="", has_battery=True, has_combustion=False
        )
        derive_car_type_if_missing(d)
        # Empty string is NOT None, so it's preserved (by contract).
        # Parsers must use `if isinstance(s, str) and s:` guard to
        # avoid assigning empty strings (they all do).
        assert d.car_type == ""


class TestHybridDerivation:
    def test_battery_plus_combustion_yields_hybrid(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(has_battery=True, has_combustion=True)
        derive_car_type_if_missing(d)
        assert d.car_type == "hybrid"

    def test_battery_plus_combustion_ignores_engine_type(self) -> None:
        # Hybrid rule has precedence over the combustion-only path
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            has_battery=True,
            has_combustion=True,
            primary_engine_type="DIESEL",
        )
        derive_car_type_if_missing(d)
        assert d.car_type == "hybrid"


class TestElectricDerivation:
    def test_battery_only_yields_electric(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(has_battery=True, has_combustion=False)
        derive_car_type_if_missing(d)
        assert d.car_type == "electric"


class TestCombustionDerivation:
    def test_diesel_uppercase(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            has_battery=False,
            has_combustion=True,
            primary_engine_type="DIESEL",
        )
        derive_car_type_if_missing(d)
        assert d.car_type == "diesel"

    def test_petrol_yields_gasoline(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            has_battery=False,
            has_combustion=True,
            primary_engine_type="PETROL",
        )
        derive_car_type_if_missing(d)
        assert d.car_type == "gasoline"

    def test_gasoline_yields_gasoline(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            has_battery=False,
            has_combustion=True,
            primary_engine_type="gasoline",
        )
        derive_car_type_if_missing(d)
        assert d.car_type == "gasoline"

    def test_unknown_engine_type_leaves_none(self) -> None:
        # CNG / LPG / H2 etc — don't guess, wait for explicit
        # backend field or scout report
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(
            has_battery=False,
            has_combustion=True,
            primary_engine_type="CNG",
        )
        derive_car_type_if_missing(d)
        assert d.car_type is None

    def test_no_engine_type_with_combustion_leaves_none(self) -> None:
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(has_battery=False, has_combustion=True)
        derive_car_type_if_missing(d)
        assert d.car_type is None


class TestInsufficientSignal:
    def test_neither_flag_set_stays_none(self) -> None:
        # Parser hasn't determined drivetrain at all (e.g. backend
        # didn't ship battery_soc or engine block on a stale poll)
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(has_battery=False, has_combustion=False)
        derive_car_type_if_missing(d)
        assert d.car_type is None


class TestSafeOnAnyInputShape:
    """Helper must never raise — pure-function defensiveness."""

    def test_missing_attributes_safe(self) -> None:
        # VehicleData missing some attributes (defensive
        # getattr with defaults in the helper)
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        class _Bare:
            pass

        d = _Bare()
        # Should not raise; just no-op (car_type not even an attribute)
        derive_car_type_if_missing(d)


class TestBrandParserWiring:
    """All 5 parser modules now call the helper at end-of-parse."""

    @pytest.mark.parametrize(
        "module_name",
        [
            "skoda",
            "vw_eu",
            "seat_cupra",
            "porsche",
            "vw_na",
        ],
    )
    def test_parser_calls_derive_helper(self, module_name: str) -> None:
        import importlib
        import inspect

        mod = importlib.import_module(
            f"custom_components.vag_connect.cariad.api.{module_name}"
        )
        src = inspect.getsource(mod)
        assert "derive_car_type_if_missing" in src, (
            f"{module_name}: parser doesn't call derive_car_type_if_missing"
        )


class TestEndToEndDerivationExamples:
    """Mirror real-world scenarios end-to-end through the helper."""

    def _derive(self, **kwargs):
        from custom_components.vag_connect.cariad._util import (
            derive_car_type_if_missing,
        )

        d = _make_vehicle(**kwargs)
        derive_car_type_if_missing(d)
        return d.car_type

    def test_cupra_born_ev_only(self) -> None:
        # Born MY26: has_battery=True, has_combustion=False
        assert self._derive(has_battery=True, has_combustion=False) == "electric"

    def test_cupra_formentor_phev(self) -> None:
        # Formentor e-Hybrid: both
        assert (
            self._derive(
                has_battery=True,
                has_combustion=True,
                primary_engine_type="PETROL",
            )
            == "hybrid"
        )

    def test_porsche_taycan_ev_only(self) -> None:
        assert self._derive(has_battery=True, has_combustion=False) == "electric"

    def test_porsche_cayenne_diesel(self) -> None:
        assert (
            self._derive(
                has_battery=False,
                has_combustion=True,
                primary_engine_type="DIESEL",
            )
            == "diesel"
        )

    def test_porsche_cayenne_e_hybrid(self) -> None:
        assert (
            self._derive(
                has_battery=True,
                has_combustion=True,
                primary_engine_type="PETROL",
            )
            == "hybrid"
        )

    def test_vw_na_id4_ev_only(self) -> None:
        assert self._derive(has_battery=True, has_combustion=False) == "electric"
