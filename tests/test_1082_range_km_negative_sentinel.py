# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1082 (fg877khkv8-maker, US ID.4) — VW US/Canada sends ``cruiseRange = -1``
as a "no value" sentinel. Before the fix it was taken literally (Range = -1)
AND, because the generic field was then set, it blocked the valid EV range
(``cruisingRange.range``) from filling it. ``_na_range_km`` screens any negative
reading to ``None`` so the EV fallback supplies the real range; ``0`` stays a
genuine reading.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.vw_na import _na_range_km


def test_negative_sentinel_is_screened_to_none() -> None:
    """The reporter's exact value: cruiseRange -1 must become unknown, not -1."""
    assert _na_range_km(-1, "KM") is None
    assert _na_range_km(-1, "MI") is None
    assert _na_range_km(-42, "KM") is None


def test_zero_is_a_real_reading() -> None:
    """An empty tank/battery genuinely reads 0 — it is not the sentinel."""
    assert _na_range_km(0, "KM") == 0


def test_valid_km_range_is_preserved() -> None:
    assert _na_range_km(300, "KM") == 300
    assert _na_range_km(305.9, "KM") == 305


def test_valid_miles_range_converts_to_km() -> None:
    assert _na_range_km(100, "MI") == 160  # 100 * 1.609344 -> 160
    # unit is compared case-insensitively
    assert _na_range_km(100, "mi") == 160


def test_non_numeric_is_none() -> None:
    assert _na_range_km(None, "KM") is None
    assert _na_range_km("n/a", "KM") is None
    assert _na_range_km("-1", "KM") is None  # a string is not a number we screen
