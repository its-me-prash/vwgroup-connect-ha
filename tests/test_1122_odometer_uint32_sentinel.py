# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1122 (dpk1987, Golf 8 mHeV, VW EU) — the odometer stuck at 429,496,729 km.

He reported an odometer "over 400,000" that had not moved since 1 Aug 2026, and
his diagnostics gave the exact figure: **429,496,729 km**. That is ``0xFFFFFFFF /
10`` — the uint32 "no value" sentinel scaled by the odometer field's 0.1 km unit.

The EU Data Act path already drops the RAW ``4294967295`` (its
``_GLOBAL_SENTINELS`` set), but not the /10-scaled form, and none of the
brand-backend odometer paths (vw_eu BFF, vw.de authproxy, Škoda, SEAT/CUPRA,
Porsche, VW NA) screened it at all — the same write-path trap the #1104 charge
sentinel had. ``drop_odometer_sentinel`` is the single shared guard now wrapped
around every odometer write; these tests pin its behaviour, the reporter's exact
value first.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._util import drop_odometer_sentinel


# ── the reporter's exact value + the uint sentinel family ────────────────────

def test_the_reporters_exact_value_is_dropped() -> None:
    """429,496,729 km = 0xFFFFFFFF / 10 — his stuck reading."""
    assert drop_odometer_sentinel(429_496_729) is None
    assert drop_odometer_sentinel(429_496_729.6) is None


def test_the_raw_uint_sentinels_are_dropped() -> None:
    assert drop_odometer_sentinel(4_294_967_295) is None   # uint32 max
    assert drop_odometer_sentinel(2_147_483_647) is None    # int32 max
    assert drop_odometer_sentinel(-2_147_483_648) is None   # int32 min (negative)


def test_a_negative_reading_is_dropped() -> None:
    assert drop_odometer_sentinel(-1) is None


# ── real readings must survive, with their type ─────────────────────────────

def test_a_real_odometer_is_kept_unchanged() -> None:
    """His neighbour's 85,103 km reading, and the original int is returned."""
    kept = drop_odometer_sentinel(85_103)
    assert kept == 85_103
    assert isinstance(kept, int)


def test_zero_is_a_real_reading_and_survives() -> None:
    """A brand-new car reads 0 km — not a sentinel."""
    assert drop_odometer_sentinel(0) == 0


def test_a_plausible_high_mileage_car_is_kept() -> None:
    """Just under the ceiling — a real taxi/van must not be screened."""
    assert drop_odometer_sentinel(1_999_999) == 1_999_999


def test_the_uint16_scaled_case_is_deliberately_not_screened() -> None:
    """0xFFFF / 10 = 6553.5 is a plausible 6553 km reading, not a sentinel —
    screening it would invent a data loss on a low-mileage car."""
    assert drop_odometer_sentinel(6553.5) == 6553.5


# ── type-preservation + pass-through, matching drop_charge_sentinel ─────────

def test_a_numeric_string_reading_is_preserved_as_given() -> None:
    kept = drop_odometer_sentinel("85103")
    assert kept == "85103"
    assert isinstance(kept, str)


def test_a_numeric_string_sentinel_is_dropped() -> None:
    assert drop_odometer_sentinel("429496729") is None


def test_none_passes_through() -> None:
    assert drop_odometer_sentinel(None) is None


def test_a_non_numeric_value_is_left_to_the_caller() -> None:
    """A dict/garbage the caller couldn't type-check is returned untouched,
    exactly as drop_charge_sentinel does — the guard only judges numbers."""
    sentinel = {"unexpected": "shape"}
    assert drop_odometer_sentinel(sentinel) is sentinel
    assert drop_odometer_sentinel("not-a-number") == "not-a-number"
