# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage-0 EU Data Act — drop-anchored poll scheduling.

The portal delivers on its own ~15-min cadence. Anchoring the next poll to the
newest snapshot's capture time (+ a buffer) catches each drop shortly after it
lands and retries fast when one is overdue — bounded so it can never poll faster
than the floor nor slower than the configured interval.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.vag_connect.coordinator import (
    _DROP_BUFFER_S,
    _DROP_RETRY_S,
    _drop_anchored_sleep_s,
)

_INTERVAL = 900   # 15 min
_FLOOR = 180      # 3 min
_NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


def _sleep(capture_offset_s: float | None) -> float:
    cap = None if capture_offset_s is None else _NOW - timedelta(seconds=capture_offset_s)
    return _drop_anchored_sleep_s(_INTERVAL, cap, _NOW, _FLOOR)


def test_no_capture_time_falls_back_to_interval():
    assert _sleep(None) == float(_INTERVAL)


def test_fresh_capture_sleeps_at_most_the_interval():
    # captured just now → next drop ~interval+buffer away, clamped to interval
    assert _sleep(0) == float(_INTERVAL)


def test_capture_one_interval_old_polls_at_the_floor_to_catch_the_drop():
    # target = now + buffer (60s) → below the floor → floor wins
    assert _sleep(_INTERVAL) == float(_FLOOR)


def test_overdue_drop_retries_fast_but_not_below_the_floor():
    # captured 2 intervals ago → target in the past → retry, clamped to floor
    assert _sleep(2 * _INTERVAL) == float(_FLOOR)
    assert _DROP_RETRY_S <= _FLOOR  # so the retry always clamps up to the floor


def test_mid_window_returns_the_aligned_remaining():
    # captured 500s ago → target = 500s-ago + interval + buffer = now + 460s
    assert _sleep(500) == float(_INTERVAL + _DROP_BUFFER_S - 500)  # 460


def test_result_is_always_within_bounds():
    for off in (None, 0, 100, 500, 899, 900, 901, 1800, 100000):
        s = _sleep(off)
        assert _FLOOR <= s <= _INTERVAL, off
