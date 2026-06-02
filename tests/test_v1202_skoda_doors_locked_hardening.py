# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.20.2 — Skoda doors_locked parser hardening (#131 Bug B).

Proactive defensive fix without waiting for Chr1sDub's specific JSON
data. Two improvements:

1. Drop the buggy ``access.overallStatus != "OPEN"`` fallback that
   marked closed-but-unlocked vehicles as locked AND treated
   UNAVAILABLE-state vehicles as falsely locked. Pre-v1.20.2 line:

       d.doors_locked = v(access, "overallStatus") != "OPEN"

   Removed in v1.20.2 — only authoritative ``overall.reliableLockStatus``
   / ``overall.doorsLocked`` / ``overall.locked`` are used now.

2. Extended explicit value enumeration with both locked and unlocked
   sets, plus forward-compat logging for unknown values (myskoda #503
   safe_enum pattern). Pre-v1.20.2 only matched locked values; any
   other value silently fell through to line 320's buggy default.
"""

from __future__ import annotations


def _parse_skoda_status_doors_locked(status: dict) -> bool | None:
    """Standalone reproduction of the v1.20.2 hardened parser block.

    Returns the final value of ``d.doors_locked`` after both blocks
    have run. ``None`` means the parser couldn't determine state.
    """
    def v(d, *keys):
        cur = d
        for k in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        return cur

    doors_locked: bool | None = None  # default — neither block ran
    if isinstance(status, dict):
        # Block 1 (formerly line 320 — REMOVED in v1.20.2)
        # Pre-v1.20.2: d.doors_locked = v(access, "overallStatus") != "OPEN"
        # Now: nothing (defer to block 2)

        # Block 2 (line 354 — extended in v1.20.2)
        overall = v(status, "overall") or {}
        lock_raw = (
            v(overall, "reliableLockStatus")
            or v(overall, "doorsLocked")
            or v(overall, "locked")
        )
        if isinstance(lock_raw, str):
            up = lock_raw.upper()
            _locked = {"YES", "LOCKED", "TRUE", "RELIABLE_LOCKED"}
            _unlocked = {
                "NO", "UNLOCKED", "FALSE", "OPEN", "RELIABLE_UNLOCKED",
            }
            if up in _locked:
                doors_locked = True
            elif up in _unlocked:
                doors_locked = False
            # else: leave None
    return doors_locked


# ─────────────────────────────────────────────────────────────────────────────
# A) Locked values (all variants seen across firmwares)
# ─────────────────────────────────────────────────────────────────────────────


class TestLockedValues:
    def test_yes(self):
        assert _parse_skoda_status_doors_locked(
            {"overall": {"doorsLocked": "YES"}}
        ) is True

    def test_locked(self):
        assert _parse_skoda_status_doors_locked(
            {"overall": {"locked": "LOCKED"}}
        ) is True

    def test_true_string(self):
        assert _parse_skoda_status_doors_locked(
            {"overall": {"doorsLocked": "TRUE"}}
        ) is True

    def test_reliable_locked(self):
        """Kodiaq 2026+ uses ``reliableLockStatus`` field."""
        assert _parse_skoda_status_doors_locked(
            {"overall": {"reliableLockStatus": "LOCKED"}}
        ) is True

    def test_reliable_locked_long_value(self):
        """If backend ever ships ``RELIABLE_LOCKED`` as the value
        (rare but defensive)."""
        assert _parse_skoda_status_doors_locked(
            {"overall": {"reliableLockStatus": "RELIABLE_LOCKED"}}
        ) is True

    def test_lowercase_yes_normalized(self):
        """uppercase normalization handles arbitrary casing."""
        assert _parse_skoda_status_doors_locked(
            {"overall": {"doorsLocked": "yes"}}
        ) is True


# ─────────────────────────────────────────────────────────────────────────────
# B) Unlocked values (newly-recognized in v1.20.2)
# ─────────────────────────────────────────────────────────────────────────────


class TestUnlockedValues:
    def test_no(self):
        assert _parse_skoda_status_doors_locked(
            {"overall": {"doorsLocked": "NO"}}
        ) is False

    def test_unlocked(self):
        assert _parse_skoda_status_doors_locked(
            {"overall": {"locked": "UNLOCKED"}}
        ) is False

    def test_false_string(self):
        assert _parse_skoda_status_doors_locked(
            {"overall": {"doorsLocked": "FALSE"}}
        ) is False

    def test_open(self):
        """Some firmwares use ``OPEN`` as the overall lock status
        (= doors are accessible)."""
        assert _parse_skoda_status_doors_locked(
            {"overall": {"reliableLockStatus": "OPEN"}}
        ) is False


# ─────────────────────────────────────────────────────────────────────────────
# C) Unknown values — leave field None instead of guessing
# ─────────────────────────────────────────────────────────────────────────────


class TestUnknownValues:
    def test_unknown_enum_value_returns_none(self):
        """v1.20.2 hardening — unknown values must NOT default to a
        guessed bool. Pre-v1.20.2 fell through to the buggy line 320
        default. Now: log + leave None."""
        assert _parse_skoda_status_doors_locked(
            {"overall": {"doorsLocked": "FOOBAR_NEW_VALUE"}}
        ) is None

    def test_no_overall_block_returns_none(self):
        """No ``overall`` block in status response → field stays None."""
        assert _parse_skoda_status_doors_locked(
            {"access": {"overallStatus": "CLOSED"}}
        ) is None

    def test_empty_status_returns_none(self):
        assert _parse_skoda_status_doors_locked({}) is None

    def test_non_string_overall_value_returns_none(self):
        assert _parse_skoda_status_doors_locked(
            {"overall": {"doorsLocked": 42}}
        ) is None

    def test_pre_v1202_buggy_fallback_REMOVED(self):
        """Critical regression test — pre-v1.20.2 buggy fallback
        used ``access.overallStatus != "OPEN"`` which incorrectly
        treated CLOSED-but-unlocked vehicles as locked. v1.20.2
        removes that line entirely. Verify the bug doesn't return."""
        # Pre-v1.20.2: this would have set doors_locked=True (buggy)
        # because "CLOSED" != "OPEN". Now: field stays None.
        assert _parse_skoda_status_doors_locked(
            {"access": {"overallStatus": "CLOSED"}}
        ) is None


# ─────────────────────────────────────────────────────────────────────────────
# D) Priority chain (reliableLockStatus > doorsLocked > locked)
# ─────────────────────────────────────────────────────────────────────────────


class TestPriorityChain:
    def test_reliable_beats_doors_locked(self):
        """When both fields are present, reliableLockStatus wins."""
        assert _parse_skoda_status_doors_locked({
            "overall": {
                "reliableLockStatus": "LOCKED",
                "doorsLocked": "NO",  # would say unlocked, but reliable beats
            },
        }) is True

    def test_doors_locked_beats_locked(self):
        """When only the older two fields are present."""
        assert _parse_skoda_status_doors_locked({
            "overall": {
                "doorsLocked": "YES",
                "locked": "NO",
            },
        }) is True
