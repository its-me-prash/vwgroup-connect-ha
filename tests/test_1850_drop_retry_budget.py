# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1850 — the fast drop-retry must not outlive the drop it is waiting for.

Anchoring the next poll to the portal's own cadence is right: a snapshot one
minute late is worth catching a minute later rather than a whole interval later.
The retry had no budget, though, so on an entry whose feed had stopped it fired
on every single poll — the anchor never moved, the drop was permanently
"overdue", and the clamp pinned the cadence at the floor for as long as the
outage lasted.

@indigomejor measured the consequence on a Škoda Octavia: ``scan_interval`` of
10 minutes, a flat 3.4-minute cadence across three separate days, ~17 polls an
hour, ending in an account-level 429 and then a hard lockout. Raising the
interval could not help, because the interval was only ever the upper bound of
the alignment — never its lower one.

The retry now gets a budget, and a landed drop refills it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.vag_connect.coordinator import (
    _CC_MIN_INTERVAL_S,
    _DROP_BUFFER_S,
    _DROP_RETRY_MAX_STREAK,
    _DROP_RETRY_S,
    _drop_anchor_advanced,
    _drop_anchored_sleep_s,
    _drop_overdue,
)

_NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
_FLOOR = _CC_MIN_INTERVAL_S          # 180 s
_HIS_INTERVAL = 10 * 60              # his scan_interval: 10 → 600 s


def _sleep(age_s: float, streak: int, interval_s: int = _HIS_INTERVAL) -> float:
    """Sleep for a capture `age_s` seconds old after `streak` overdue polls."""
    return _drop_anchored_sleep_s(
        interval_s, _NOW - timedelta(seconds=age_s), _NOW, _FLOOR, streak,
    )


# ── the reported case ─────────────────────────────────────────────────────────
def test_his_measured_cadence_is_what_the_old_code_produced() -> None:
    """Grounding the fix in the report: with no budget spent, a long-overdue
    drop still collapses to the floor — 180 s, which with his ~22 s cycle is
    the 3.4 min he measured for three days."""
    assert _sleep(5 * _HIS_INTERVAL, streak=0) == float(_FLOOR)
    assert _FLOOR == 180
    assert _DROP_RETRY_S <= _FLOOR   # the retry always clamps up to the floor


def test_a_feed_that_stays_down_gets_the_configured_interval_back() -> None:
    """The fix. Once the budget is spent, the user's interval wins — his 10
    minutes instead of the floor's three."""
    assert _sleep(5 * _HIS_INTERVAL, streak=_DROP_RETRY_MAX_STREAK) == float(_HIS_INTERVAL)
    assert _sleep(5 * _HIS_INTERVAL, streak=_DROP_RETRY_MAX_STREAK + 9) == float(_HIS_INTERVAL)


def test_the_budget_is_spent_before_it_runs_out_not_after() -> None:
    """Every poll below the threshold still retries fast — the alignment this
    exists for keeps working for a drop that is merely late."""
    for streak in range(_DROP_RETRY_MAX_STREAK):
        assert _sleep(5 * _HIS_INTERVAL, streak=streak) == float(_FLOOR), streak


# ── what must NOT change ──────────────────────────────────────────────────────
def test_a_drop_that_is_not_overdue_ignores_the_budget() -> None:
    """A streak only ever shortens the overdue branch. A capture mid-window
    still sleeps its aligned remainder, however long the streak is."""
    aligned = float(_HIS_INTERVAL + _DROP_BUFFER_S - 300)   # captured 300 s ago
    for streak in (0, _DROP_RETRY_MAX_STREAK, 99):
        assert _sleep(300, streak=streak) == aligned, streak


def test_no_capture_time_is_still_a_no_op() -> None:
    for streak in (0, 99):
        assert _drop_anchored_sleep_s(
            _HIS_INTERVAL, None, _NOW, _FLOOR, streak,
        ) == float(_HIS_INTERVAL)


def test_the_result_stays_inside_the_bounds_either_way() -> None:
    for streak in (0, 1, _DROP_RETRY_MAX_STREAK, 50):
        for age in (0, 100, 599, 600, 601, 3600, 100000):
            s = _sleep(age, streak=streak)
            assert _FLOOR <= s <= _HIS_INTERVAL, (age, streak)


def test_the_spent_budget_path_is_clamped_like_every_other() -> None:
    """The bound above is the one promise this function makes, and the
    spent-budget path nearly escaped it: returning a bare `interval_s` hands
    back a sleep BELOW the floor whenever the configured interval is shorter
    than the floor. The poll loop never calls it that way — it takes
    `max(scan_interval * 60, floor)` first — but the function is documented as
    clamped, and a caller that trusts the docstring would get an unclamped
    answer only on the one path added here."""
    old = datetime(2026, 10, 17, 11, 0, 0, tzinfo=timezone.utc)   # an hour old
    short = 120                                                   # below the floor
    spent = _drop_anchored_sleep_s(short, old, _NOW, _FLOOR, _DROP_RETRY_MAX_STREAK)
    unspent = _drop_anchored_sleep_s(short, old, _NOW, _FLOOR, 0)
    assert spent == float(_FLOOR), spent
    assert unspent == float(_FLOOR), unspent
    assert spent == unspent


def test_the_old_four_argument_call_still_works() -> None:
    """The streak is optional, so every existing caller and test keeps its
    meaning: no budget spent behaves exactly as before."""
    cap = _NOW - timedelta(seconds=5 * _HIS_INTERVAL)
    assert _drop_anchored_sleep_s(_HIS_INTERVAL, cap, _NOW, _FLOOR) == float(_FLOOR)


# ── the condition the streak is counted against ───────────────────────────────
def test_overdue_is_the_same_condition_the_sleep_branches_on() -> None:
    """The caller counts the streak with _drop_overdue and the scheduler
    branches on it, so the two cannot drift apart. Pinned because a second copy
    of this arithmetic in the poll loop is exactly how they would."""
    assert _drop_overdue(_HIS_INTERVAL, None, _NOW) is False
    just_inside = _NOW - timedelta(seconds=_HIS_INTERVAL + _DROP_BUFFER_S - 1)
    just_outside = _NOW - timedelta(seconds=_HIS_INTERVAL + _DROP_BUFFER_S + 1)
    assert _drop_overdue(_HIS_INTERVAL, just_inside, _NOW) is False
    assert _drop_overdue(_HIS_INTERVAL, just_outside, _NOW) is True
    # And the sleep agrees on both sides of that boundary. One second before it
    # the drop is not overdue, so the aligned remainder (1 s) clamps up to the
    # floor; one second after it the spent budget hands back the interval.
    assert _sleep(_HIS_INTERVAL + _DROP_BUFFER_S - 1, streak=99) == float(_FLOOR)
    assert _sleep(_HIS_INTERVAL + _DROP_BUFFER_S + 1, streak=99) == float(_HIS_INTERVAL)


def test_a_frozen_feed_does_not_look_like_a_fresh_drop_every_poll() -> None:
    """The flaw that made the first version of this fix do nothing at all.

    The loop does not keep the car's own `last_seen_at`. It rebuilds the anchor
    as `now - capture_age`, and the `now` it subtracts from is a different
    `datetime.now()` call than the one inside the age helper — so a feed that is
    completely frozen still produces a slightly different anchor on every poll.
    Measured on a frozen capture: four distinct values across five polls,
    differing by two to three MICROSECONDS.

    With an equality test, every one of those read as a new drop, the streak
    reset on every poll, the budget was never spent, and the cadence stayed
    pinned at the floor exactly as before the fix. The values below are the
    real measured ones.
    """
    base = datetime(2026, 10, 12, 9, 19, 35, 999994, tzinfo=timezone.utc)
    jittered = [
        base,
        base.replace(microsecond=999997),
        base.replace(microsecond=999999),
        base.replace(microsecond=999999),
        base.replace(microsecond=999998),
    ]
    # Consecutive polls on a frozen feed: none of these counts as a new drop,
    # including the one that jitters BACKWARDS.
    for prev, cur in zip(jittered, jittered[1:]):
        assert _drop_anchor_advanced(prev, cur) is False, (prev, cur)

    # A real drop lands minutes later and does count.
    assert _drop_anchor_advanced(base, base + timedelta(minutes=15)) is True
    # The first anchor of an entry's life counts, so the budget starts full.
    assert _drop_anchor_advanced(None, base) is True
    # No capture at all is not a drop.
    assert _drop_anchor_advanced(base, None) is False
    # Backwards never refills the budget.
    assert _drop_anchor_advanced(base, base - timedelta(minutes=15)) is False


def test_the_poll_loop_actually_feeds_the_streak_in() -> None:
    """A wiring pin, and it says so: the budget lives on the coordinator while
    the decision lives in the scheduler, so the two have to be connected. The
    pure tests above would all still pass with the call site reverted to four
    arguments — that is how the same class of gap got shipped twice in this
    repository, so it is checked structurally rather than not at all.

    Anchored on the call's own lines, not on a search of the whole file: an
    earlier version of a test like this matched an unrelated construct
    elsewhere in the module and passed on a mutant.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "custom_components"
           / "vag_connect" / "coordinator.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    call = next(i for i, ln in enumerate(lines)
                if "sleep_s: float = _drop_anchored_sleep_s(" in ln)
    args = [ln.strip() for ln in lines[call:call + 8]]
    assert "self._drop_overdue_streak," in args, (
        f"the scheduler is not given the streak: {args}"
    )

    # And the bookkeeping. Taken as the WHOLE block between the decision
    # timestamp and the scheduler call, rather than a fixed number of lines
    # around one of them: a line window broke the moment a debug log grew
    # inside the block, which is a test that fails for the wrong reason.
    start = next(i for i, ln in enumerate(lines)
                 if "_decision_now = datetime.now(" in ln)
    window = [ln.strip() for ln in lines[start:call]]
    assert window, "the bookkeeping block is not above the scheduler call"
    assert any("self._drop_overdue_streak += 1" in ln for ln in window), window
    assert any("_drop_overdue(" in ln for ln in window), window

    # The arguments, in order. A substring check on the call name alone passes
    # with them swapped, and swapped they turn the predicate inside out: the
    # recovery case (a feed delivering again, one drop late) would then keep
    # standing down instead of resuming the alignment.
    assert any(
        "_drop_anchor_advanced(_prev_anchor, _cap_anchor)" in ln for ln in window
    ), window

    # The one line that makes the streak a streak. Deleting it leaves
    # _drop_anchor_seen at its __init__ value of None forever, so
    # _drop_anchor_advanced(None, anything) is True on every poll, the streak
    # resets every poll, and #1850 is back in full — with every other test in
    # this file, and the rest of the suite, still green. Measured: the suite
    # passes with that single line removed.
    assert any("self._drop_anchor_seen = _cap_anchor" in ln for ln in window), window
