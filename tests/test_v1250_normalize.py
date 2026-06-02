# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Property tests for `cariad/_normalize.py` helpers (v1.25.0 PR-A).

Same pattern as v1.24.2's `test_v1242_property_safe_helpers.py` —
file-loader bypass for the package init, hypothesis property tests
enforcing NEVER-raise + correctness invariants.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect" / "cariad"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(f"vag_pure.{name}", _ROOT / file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"vag_pure.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_util = _load("_util", "_util.py")
_normalize = _load("_normalize", "_normalize.py")

k_to_c = _normalize.k_to_c
c_to_k = _normalize.c_to_k
derive_drivetrain = _normalize.derive_drivetrain
derive_range_headline = _normalize.derive_range_headline
first_status_value = _normalize.first_status_value
normalize_software_update_state = _normalize.normalize_software_update_state
SOFTWARE_UPDATE_STATES_KNOWN = _normalize.SOFTWARE_UPDATE_STATES_KNOWN


ANY_OBJECT = st.one_of(
    st.none(), st.booleans(), st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(), st.binary(),
    st.lists(st.integers(), max_size=5),
    st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
)


# ─────────────────────────────────────────────────────────────────────────────
# k_to_c / c_to_k
# ─────────────────────────────────────────────────────────────────────────────


class TestKtoC:
    @given(value=ANY_OBJECT)
    @settings(max_examples=300)
    def test_never_raises(self, value):
        out = k_to_c(value)
        assert out is None or isinstance(out, float)

    @given(c=st.floats(min_value=-50, max_value=60, allow_nan=False))
    def test_round_trip(self, c):
        k = c + 273.15
        recovered = k_to_c(k)
        assert recovered is not None
        assert abs(recovered - c) < 0.05  # rounding to 1 decimal

    def test_known_values(self):
        assert k_to_c(273.15) == 0.0
        assert k_to_c(295.15) == 22.0
        # 300 K = 26.85 °C → rounded to 1 decimal = 26.9
        assert k_to_c(300) == 26.9
        # custom decimals param
        assert k_to_c(300, decimals=2) == 26.85

    def test_string_kelvin_parses(self):
        assert k_to_c("295.15") == 22.0
        assert k_to_c("295,15") == 22.0  # locale-comma via safe_float

    def test_garbage_returns_none(self):
        assert k_to_c("not a temp") is None
        assert k_to_c({}) is None
        assert k_to_c([]) is None
        assert k_to_c(None) is None


class TestCtoK:
    @given(value=ANY_OBJECT)
    @settings(max_examples=300)
    def test_never_raises(self, value):
        out = c_to_k(value)
        assert out is None or isinstance(out, float)

    @given(c=st.floats(min_value=-50, max_value=60, allow_nan=False))
    def test_always_positive_for_realistic_celsius(self, c):
        k = c_to_k(c)
        assert k is not None
        assert k > 0  # Kelvin is always > 0 for any realistic Celsius

    def test_known_values(self):
        assert c_to_k(0) == 273.15
        assert c_to_k(22) == 295.15
        assert c_to_k(-10) == 263.15


# ─────────────────────────────────────────────────────────────────────────────
# derive_drivetrain
# ─────────────────────────────────────────────────────────────────────────────


class TestDeriveDrivetrain:
    def test_pure_ev(self):
        assert derive_drivetrain(True, False) == (True, False)

    def test_phev(self):
        assert derive_drivetrain(True, True) == (False, True)

    def test_pure_ice(self):
        assert derive_drivetrain(False, True) == (False, False)

    def test_neither(self):
        assert derive_drivetrain(False, False) == (False, False)

    @given(b=st.booleans(), c=st.booleans())
    def test_exhaustive_invariants(self, b, c):
        is_e, is_h = derive_drivetrain(b, c)
        # Mutual exclusion: can't be both pure-EV and hybrid
        assert not (is_e and is_h)
        # Hybrid implies battery
        if is_h:
            assert b


# ─────────────────────────────────────────────────────────────────────────────
# derive_range_headline
# ─────────────────────────────────────────────────────────────────────────────


class TestDeriveRangeHeadline:
    def test_ev_picks_electric_first(self):
        out = derive_range_headline(
            electric_km=300, total_km=350, combustion_km=None, has_battery=True,
        )
        assert out == 300

    def test_phev_with_battery_prefers_electric(self):
        out = derive_range_headline(
            electric_km=50, total_km=600, combustion_km=550, has_battery=True,
        )
        assert out == 50

    def test_phev_without_electric_falls_to_total(self):
        out = derive_range_headline(
            electric_km=None, total_km=600, combustion_km=550, has_battery=True,
        )
        assert out == 600

    def test_ice_picks_total(self):
        out = derive_range_headline(
            electric_km=None, total_km=800, combustion_km=750, has_battery=False,
        )
        assert out == 800

    def test_ice_falls_to_combustion_if_no_total(self):
        out = derive_range_headline(
            electric_km=None, total_km=None, combustion_km=750, has_battery=False,
        )
        assert out == 750

    def test_all_none_returns_none(self):
        out = derive_range_headline(
            electric_km=None, total_km=None, combustion_km=None, has_battery=True,
        )
        assert out is None

    def test_zero_electric_does_not_get_replaced_by_truthy_fallback(self):
        """Bug-fix vs. old vw_eu.py:865-870 ``electric or total`` chain
        which returned 0 falsy → wrong fallback."""
        out = derive_range_headline(
            electric_km=0, total_km=400, combustion_km=None, has_battery=True,
        )
        assert out == 0  # NOT 400


# ─────────────────────────────────────────────────────────────────────────────
# first_status_value
# ─────────────────────────────────────────────────────────────────────────────


class TestFirstStatusValue:
    def test_happy_path(self):
        node = {"status": [{"value": "CLOSED", "ts": "2026-05-08T..."}]}
        assert first_status_value(node) == "CLOSED"

    def test_uses_first_when_multiple(self):
        node = {"status": [{"value": "OPEN"}, {"value": "CLOSED"}]}
        assert first_status_value(node) == "OPEN"

    def test_default_for_none(self):
        assert first_status_value(None, default="UNKNOWN") == "UNKNOWN"

    def test_default_for_non_dict(self):
        assert first_status_value("garbage", default="X") == "X"
        assert first_status_value([1, 2, 3], default="X") == "X"

    def test_default_for_missing_status_key(self):
        assert first_status_value({"foo": "bar"}, default="X") == "X"

    def test_default_for_empty_list(self):
        assert first_status_value({"status": []}, default="X") == "X"

    def test_default_for_non_dict_first_element(self):
        assert first_status_value({"status": ["raw_string"]}, default="X") == "X"

    def test_default_for_missing_value_key(self):
        assert first_status_value({"status": [{"ts": "..."}]}, default="X") == "X"

    def test_default_for_explicit_none_value(self):
        assert first_status_value({"status": [{"value": None}]}, default="X") == "X"

    @given(garbage=ANY_OBJECT)
    @settings(max_examples=100)
    def test_never_raises(self, garbage):
        out = first_status_value(garbage, default="DEFAULT")
        # Just must not raise — no other invariant
        assert out is not None or out is None  # tautology, focus is no-raise


# ─────────────────────────────────────────────────────────────────────────────
# normalize_software_update_state (myskoda PR #565 backport)
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizeSoftwareUpdateState:
    def test_update_available(self):
        is_avail, raw = normalize_software_update_state("UPDATE_AVAILABLE")
        assert is_avail is True
        assert raw == "UPDATE_AVAILABLE"

    def test_no_update_available_myskoda_pr_565(self):
        """myskoda PR #565 added this enum value — old parsers crashed."""
        is_avail, raw = normalize_software_update_state("NO_UPDATE_AVAILABLE")
        assert is_avail is False
        assert raw == "NO_UPDATE_AVAILABLE"

    def test_not_activated_myskoda_207(self):
        is_avail, raw = normalize_software_update_state("NOT_ACTIVATED")
        assert is_avail is False
        assert raw == "NOT_ACTIVATED"

    def test_up_to_date(self):
        is_avail, raw = normalize_software_update_state("UP_TO_DATE")
        assert is_avail is False
        assert raw == "UP_TO_DATE"

    def test_lowercase_works(self):
        is_avail, _ = normalize_software_update_state("up_to_date")
        assert is_avail is False

    def test_with_whitespace(self):
        is_avail, raw = normalize_software_update_state("  UPDATE_AVAILABLE  ")
        assert is_avail is True
        assert raw == "UPDATE_AVAILABLE"

    def test_unknown_enum_returns_none_for_avail(self):
        """Forward-compat: future firmware adds new state, we don't crash."""
        is_avail, raw = normalize_software_update_state("FUTURE_STATE_42")
        assert is_avail is None
        assert raw == "FUTURE_STATE_42"

    def test_none_input(self):
        is_avail, raw = normalize_software_update_state(None)
        assert is_avail is None
        assert raw is None

    def test_empty_string(self):
        is_avail, raw = normalize_software_update_state("")
        assert is_avail is None
        assert raw is None

    @given(value=ANY_OBJECT)
    @settings(max_examples=200)
    def test_never_raises(self, value):
        is_avail, raw = normalize_software_update_state(value)
        assert is_avail is None or isinstance(is_avail, bool)
        assert raw is None or isinstance(raw, str)
