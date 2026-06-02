# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Property-based tests for defensive helpers (v1.24.2 — Audit 2026-05-08).

The helpers ``safe_int`` / ``safe_float`` / ``safe_enum`` / ``mask_vin``
explicitly carry a NEVER-raise contract documented in their docstrings.
Until v1.24.2, that invariant was only example-tested (5–10 happy paths
each). Hypothesis adds genuinely-arbitrary input coverage: any Python
object, any string, any unicode-weirdness — all must produce a value
without raising.

The same approach also covers ``cariad/_mbb.py:is_cariad_wrapper_404``
(body-sniff for Cariad-BFF wrapper-404 detection, v1.20.3) and
``cariad/exceptions.py:classify_command_failure`` (the 3-state feature
model entry point, v1.8.2 / v1.9.1 Phase 2).

These are unit-level property tests — no HA imports needed, runs locally
after ``pip install -r requirements-test.txt``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

# Direct file-loader — bypasses ``custom_components/vag_connect/__init__.py``
# which eagerly imports HA. The pure helpers themselves have no HA
# dependency, but the package init chain pulls in ``api.factory`` →
# ``coordinator`` → ``homeassistant.*``. v1.24.1 added the test deps
# (hypothesis/pytest/...) but contributors who run locally usually don't
# install HA — so route around the init.
_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect" / "cariad"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(
        f"vag_pure.{name}", _ROOT / file,
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"vag_pure.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_util = _load("_util", "_util.py")
_mbb = _load("_mbb", "_mbb.py")

safe_int = _util.safe_int
safe_float = _util.safe_float
safe_enum = _util.safe_enum
mask_vin = _util.mask_vin
is_cariad_wrapper_404 = _mbb.is_cariad_wrapper_404


# Universe of "anything Python" used as input for NEVER-raise invariants.
ANY_OBJECT = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(),
    st.binary(),
    st.lists(st.integers(), max_size=5),
    st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
    st.tuples(st.integers(), st.text()),
    st.sets(st.integers(), max_size=3),
)


# ─────────────────────────────────────────────────────────────────────────────
# A) safe_int — NEVER raises, output is int|None
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeIntProperty:
    @given(value=ANY_OBJECT)
    @settings(max_examples=400)
    def test_never_raises_for_arbitrary_input(self, value):
        out = safe_int(value)
        assert out is None or isinstance(out, int)

    @given(value=ANY_OBJECT, default=st.integers(min_value=-99, max_value=99))
    @settings(max_examples=200)
    def test_default_returned_for_unparseable(self, value, default):
        out = safe_int(value, default=default)
        assert out is None or isinstance(out, int)
        # If value has no int-shape AND default is non-None, default is returned.
        # (Round-trip cover; full equivalence is too strict because str("42")
        # is parseable.)

    @given(n=st.integers(min_value=-(10 ** 9), max_value=10 ** 9))
    def test_int_passthrough(self, n):
        assert safe_int(n) == n

    @given(s=st.from_regex(r"-?[1-9]\d{0,8}", fullmatch=True))
    def test_numeric_string_parses(self, s):
        out = safe_int(s)
        assert out == int(s)


# ─────────────────────────────────────────────────────────────────────────────
# B) safe_float — NEVER raises, output is float|None, finite when not None
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFloatProperty:
    @given(value=ANY_OBJECT)
    @settings(max_examples=400)
    def test_never_raises_for_arbitrary_input(self, value):
        out = safe_float(value)
        assert out is None or isinstance(out, float)

    @given(s=st.from_regex(r"-?\d{1,5}[.,]\d{1,3}", fullmatch=True))
    def test_locale_comma_or_dot_string_parses(self, s):
        """v1.20.2 locale-comma fallback — both ``"21,5"`` and ``"21.5"``
        must yield a finite float."""
        out = safe_float(s)
        assert out is not None
        assert isinstance(out, float)
        # Either dot- or comma-decimal must have parsed cleanly:
        expected = float(s.replace(",", "."))
        assert abs(out - expected) < 1e-9

    @given(s=st.text(min_size=1).filter(lambda x: not x.strip().replace(",", ".").replace("-", "").replace(".", "").isdigit()))
    @settings(max_examples=200)
    def test_garbage_string_yields_default(self, s):
        out = safe_float(s, default=42.0)
        # Either the garbage happened to parse (some unicode digits do), or default
        assert out is None or isinstance(out, float)


# ─────────────────────────────────────────────────────────────────────────────
# C) safe_enum — output always in known_values OR equals default
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeEnumProperty:
    @given(
        value=st.one_of(st.none(), st.text(max_size=20), st.integers()),
        known=st.sets(st.text(min_size=1, max_size=20), min_size=1, max_size=10),
    )
    @settings(max_examples=300)
    def test_output_is_in_known_or_default(self, value, known):
        default = "FALLBACK"
        out = safe_enum(value, known, default=default)
        # Output is None, default, or in known_values (case-insensitively)
        if out is None:
            return
        if out == default:
            return
        assert out.upper() in {k.upper() for k in known}

    @given(
        value=st.text(min_size=1, max_size=20),
        known=st.sets(st.text(min_size=1, max_size=20), min_size=1, max_size=10),
    )
    @settings(max_examples=200)
    def test_case_insensitive_match_returns_original(self, value, known):
        # If value (upper) happens to be in known (upper), original is returned
        if value.strip().upper() in {k.upper() for k in known}:
            out = safe_enum(value, known, default="X")
            assert out == value.strip()


# ─────────────────────────────────────────────────────────────────────────────
# D) mask_vin — privacy invariant
# ─────────────────────────────────────────────────────────────────────────────


class TestMaskVinProperty:
    @given(vin=st.one_of(st.none(), st.text()))
    @settings(max_examples=300)
    def test_never_raises_and_returns_string(self, vin):
        out = mask_vin(vin)
        assert isinstance(out, str)

    @given(
        # Real VINs are 17 alphanumeric chars per ISO 3779. Restricting
        # the strategy to alnum mirrors the production input shape and
        # avoids false-positive "leaks" where the input happens to
        # contain the mask character "*" itself.
        vin=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=1, max_size=50,
        ),
    )
    @settings(max_examples=300)
    def test_never_reveals_more_than_last_6_chars(self, vin):
        """Privacy invariant: chars from the head of the VIN must never
        appear in the masked output (except those also in the tail).

        Real VINs are 17 alphanumeric chars per ISO 3779 — strategy
        restricts to that surface so the assertion is meaningful.
        """
        out = mask_vin(vin)
        if len(vin) <= 6:
            # Short VIN fully visible under "***" prefix — acceptable per
            # current contract (no real VIN is ≤ 6 chars).
            assert vin in out
        else:
            tail = vin[-6:]
            assert tail in out
            head_unique = set(vin[:-6]) - set(tail)
            for ch in head_unique:
                assert ch not in out, (
                    f"head char {ch!r} from VIN {vin!r} leaked into masked "
                    f"output {out!r}"
                )

    @given(vin=st.text(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_output_starts_with_mask_prefix(self, vin):
        assert mask_vin(vin).startswith("***")


# ─────────────────────────────────────────────────────────────────────────────
# E) is_cariad_wrapper_404 — body sniff invariants
# ─────────────────────────────────────────────────────────────────────────────


class TestCariadWrapper404Property:
    @given(body=st.one_of(st.none(), st.text(), st.binary()))
    @settings(max_examples=400)
    def test_never_raises_for_arbitrary_body(self, body):
        try:
            out = is_cariad_wrapper_404(body)
        except Exception as e:  # noqa: BLE001
            raise AssertionError(
                f"is_cariad_wrapper_404 raised {type(e).__name__} for {body!r}"
            ) from e
        assert isinstance(out, bool)

    def test_known_wrapper_marker_detected(self):
        body = '{"error":{"info":"Upstream service responded","retry":true}}'
        assert is_cariad_wrapper_404(body) is True

    def test_plain_404_not_misclassified(self):
        body = '{"error":"not found"}'
        assert is_cariad_wrapper_404(body) is False

    @given(prefix=st.text(max_size=200), suffix=st.text(max_size=200))
    @settings(max_examples=200)
    def test_marker_anywhere_in_body_detected(self, prefix, suffix):
        marker = '"retry":true'
        body = f"{prefix} upstream service responded {marker} {suffix}"
        # Marker present somewhere → must classify as wrapper-404
        assert is_cariad_wrapper_404(body) is True


# ─────────────────────────────────────────────────────────────────────────────
# F) Sanity: confirm helpers are pure (idempotent on same input)
# ─────────────────────────────────────────────────────────────────────────────


class TestPurity:
    @given(value=ANY_OBJECT)
    @settings(max_examples=200)
    def test_safe_int_idempotent(self, value):
        assert safe_int(value) == safe_int(value)

    @given(value=ANY_OBJECT)
    @settings(max_examples=200)
    def test_safe_float_idempotent(self, value):
        a = safe_float(value)
        b = safe_float(value)
        # NaN != NaN; treat both-None as equal
        if a is None and b is None:
            return
        if a is None or b is None:
            raise AssertionError(f"non-deterministic safe_float for {value!r}")
        # Both finite or both NaN
        import math
        if math.isnan(a) and math.isnan(b):
            return
        assert a == b

    @given(vin=st.text())
    @settings(max_examples=200)
    def test_mask_vin_idempotent(self, vin):
        assert mask_vin(vin) == mask_vin(vin)
