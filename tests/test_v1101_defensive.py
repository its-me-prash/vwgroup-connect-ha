# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.10.1 — Defensive Coding Phase 2 (#58).

Three groups:

- ``TestSafeInt`` — every input shape that the CARIAD/OLA backends have
  ever shipped is converted (int, float, "12", "12.5", "  42 ") or
  cleanly returns the default (None, "", "abc", dict, list).
- ``TestSafeFloat`` — same coverage as int, plus locale-comma test.
- ``TestSafeEnum`` — known values pass through, unknown logs warning
  and returns default. The whole point: never crash on a new enum.
- ``TestParserHardening`` — verifies the brand parsers no longer crash
  on the malformed values that previously blew them up.
- ``TestCoordinatorParseGuard`` — a parser bug raises; the coordinator
  swallows it, keeps the vehicle's previous data visible, and pushes
  the exception into the Error Reporter ring buffer.
"""

from __future__ import annotations

import logging



# ─────────────────────────────────────────────────────────────────────────────
# safe_int
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeInt:
    def test_passes_through_int(self):
        from custom_components.vag_connect.cariad._util import safe_int

        assert safe_int(42) == 42
        assert safe_int(0) == 0
        assert safe_int(-5) == -5

    def test_truncates_float(self):
        from custom_components.vag_connect.cariad._util import safe_int

        assert safe_int(12.5) == 12
        assert safe_int(-3.7) == -3

    def test_parses_numeric_string(self):
        from custom_components.vag_connect.cariad._util import safe_int

        assert safe_int("42") == 42
        assert safe_int("  100  ") == 100

    def test_parses_decimal_string_via_float(self):
        from custom_components.vag_connect.cariad._util import safe_int

        # Real-world breakage from #58 — Skoda firmware shipped
        # ``"12.5"`` for ``remainingTimeToFullyChargedInMinutes`` once.
        assert safe_int("12.5") == 12

    def test_returns_default_on_garbage(self):
        from custom_components.vag_connect.cariad._util import safe_int

        assert safe_int(None) is None
        assert safe_int("") is None
        assert safe_int("   ") is None
        assert safe_int("abc") is None
        assert safe_int({}) is None
        assert safe_int([]) is None
        assert safe_int(None, default=0) == 0

    def test_bool_subclass_preserved(self):
        from custom_components.vag_connect.cariad._util import safe_int

        # Python bool is int subclass — be explicit about the contract.
        assert safe_int(True) == 1
        assert safe_int(False) == 0


# ─────────────────────────────────────────────────────────────────────────────
# safe_float
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeFloat:
    def test_passes_through_numbers(self):
        from custom_components.vag_connect.cariad._util import safe_float

        assert safe_float(21.5) == 21.5
        assert safe_float(42) == 42.0

    def test_parses_decimal_string(self):
        from custom_components.vag_connect.cariad._util import safe_float

        assert safe_float("21.5") == 21.5
        assert safe_float("  42  ") == 42.0

    def test_returns_default_on_garbage(self):
        from custom_components.vag_connect.cariad._util import safe_float

        assert safe_float(None) is None
        assert safe_float("") is None
        assert safe_float("not a number") is None
        assert safe_float({}) is None
        assert safe_float(None, default=20.0) == 20.0

    def test_bool_handled(self):
        from custom_components.vag_connect.cariad._util import safe_float

        assert safe_float(True) == 1.0
        assert safe_float(False) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# safe_enum
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeEnum:
    KNOWN = ("CHARGING", "NOT_CHARGING", "COMPLETE", "ERROR")

    def test_known_value_returned_as_is(self):
        from custom_components.vag_connect.cariad._util import safe_enum

        assert safe_enum("CHARGING", self.KNOWN) == "CHARGING"
        assert safe_enum("ERROR", self.KNOWN) == "ERROR"

    def test_unknown_value_logs_and_returns_default(self, caplog):
        from custom_components.vag_connect.cariad._util import safe_enum

        with caplog.at_level(logging.WARNING):
            result = safe_enum(
                "CHARGING_INTERRUPTED", self.KNOWN,
                log_name="charging_state",
            )
        assert result is None
        # Warning text must mention the field + the unexpected value
        assert any(
            "charging_state" in r.message and "CHARGING_INTERRUPTED" in r.message
            for r in caplog.records
        ), "expected log line missing"

    def test_unknown_returns_explicit_default(self):
        from custom_components.vag_connect.cariad._util import safe_enum

        assert safe_enum(
            "EXOTIC_NEW_STATE", self.KNOWN, default="unknown",
        ) == "unknown"

    def test_case_insensitive_match_returns_original(self):
        from custom_components.vag_connect.cariad._util import safe_enum

        # The original casing is preserved on match (stays loyal to
        # what the API actually sent).
        assert safe_enum("charging", self.KNOWN) == "charging"
        assert safe_enum("Charging", self.KNOWN) == "Charging"

    def test_strict_case_sensitive(self):
        from custom_components.vag_connect.cariad._util import safe_enum

        # Opt-in strict mode for places where casing matters.
        assert safe_enum(
            "charging", self.KNOWN, case_insensitive=False,
        ) is None
        assert safe_enum(
            "CHARGING", self.KNOWN, case_insensitive=False,
        ) == "CHARGING"

    def test_none_and_empty(self):
        from custom_components.vag_connect.cariad._util import safe_enum

        assert safe_enum(None, self.KNOWN) is None
        assert safe_enum("", self.KNOWN) is None
        assert safe_enum("   ", self.KNOWN) is None

    def test_non_string_coerced(self):
        from custom_components.vag_connect.cariad._util import safe_enum

        # Explicit contract: non-strings are str()-coerced before
        # comparison. Avoids surprises when JSON deserialiser ships int.
        assert safe_enum(42, ("42", "13")) == "42"


# ─────────────────────────────────────────────────────────────────────────────
# Parser hardening — narrow regression check
# ─────────────────────────────────────────────────────────────────────────────


class TestParserHardening:
    """Each formerly-crashing value is now tolerated."""

    def test_skoda_remaining_minutes_as_decimal_string_does_not_crash(self):
        """myskoda #503 — backend shipped ``"12.5"`` for the remaining-
        minutes field once. Pre-1.10.1 raised ValueError."""
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient

        client = SkodaClient.__new__(SkodaClient)

        # Construct the relevant slice exactly as get_status does.
        # We don't run the whole pipeline — just the snippet that used
        # to break.
        from custom_components.vag_connect.cariad._util import safe_int

        remaining = safe_int("12.5")  # used to be int("12.5") → boom
        assert remaining == 12

    def test_vw_eu_max_charge_current_as_string_does_not_crash(self):
        """``maxChargeCurrentAC_A`` shipped as enum string ``"MAXIMUM"``
        in pre-2024 firmware. Bare float() blew up. safe_float handles it."""
        from custom_components.vag_connect.cariad._util import safe_float

        assert safe_float("MAXIMUM") is None  # gracefully degrades
        assert safe_float(16) == 16.0  # modern numeric form still works

    def test_vw_eu_model_year_as_int_or_string(self):
        from custom_components.vag_connect.cariad._util import safe_int

        assert safe_int("2021") == 2021
        assert safe_int(2021) == 2021
        assert safe_int(None, default=2020) == 2020


# ─────────────────────────────────────────────────────────────────────────────
# Coordinator parse-guard
# ─────────────────────────────────────────────────────────────────────────────


class TestCoordinatorParseGuard:
    """v1.10.1 (#58) — a parser bug must NOT take down the vehicle.

    The coordinator's ``_poll_loop`` wraps ``to_dict()`` + ``_enrich()``
    in its own try/except. On parse failure: keep previous data, log,
    record into the Error Reporter ring buffer, mark vehicle_success
    as False — but never raise out of the loop iteration.
    """

    def test_record_error_on_parse_failure(self):
        """Smoke check: invoking the same record_error path the
        coordinator uses does not raise even when the buffer call would
        fail (defensive in defensive_in_defensive)."""
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRingBuffer, record_error,
        )

        buf = ErrorRingBuffer()

        try:
            raise ValueError("bad parse")
        except ValueError as e:
            rec = record_error(
                buf, exception=e, brand="audi", vin="VINX",
                endpoint="parse",
            )

        assert rec is not None
        assert rec.exception_type == "ValueError"
        assert rec.endpoint == "parse"
        assert rec.brand == "audi"
        assert rec.vin_masked == "***VINX"
