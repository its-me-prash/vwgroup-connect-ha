# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1850 (@indigomejor, second round) — a restart must not refill the budget.

The budget from the first round works, and @indigomejor confirmed it. What it
does not survive is a Home Assistant restart, and he found that too: four
restarts, each producing the same sequence — startup poll, one poll at the
configured interval, then exactly three polls at the floor, then a stand-down —
and his debug log showing the *same* capture anchor on every poll of that
burst. His control is the proof: without a restart the slow poll still appears
every six hours and no burst follows, because by then the streak is spent.

The cause is that none of the state was persisted. ``_drop_anchor_seen``,
``_drop_overdue_streak`` and ``_newest_capture_at`` are all set in ``__init__``
and written nowhere, so after a restart the predicate saw ``previous is None``
and read "no memory yet" as "a drop landed". The test for the first round says
as much in its own comment — *"The first anchor of an entry's life counts, so
the budget starts full"* — and the premise is fine; the word that was wrong is
**life**. With nothing persisted, "an entry's life" meant "since the last
restart".

**Why a high-water mark rather than persisting ``_drop_anchor_seen``.**
Measured, not assumed: persisting that field alone does not fix this. The first
poll after a restart has not read the portal yet, so ``_cap_anchor`` is None;
the decision block then writes that None over the restored value (deliberately,
for the reason its own comment gives), and the *second* poll reads None again
and resets exactly as before. A high-water mark — the newest anchor ever seen —
is immune, because it only ever moves forward and is never cleared.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.vag_connect.cariad.vehicle_cache import (
    drop_state_from_cache,
    drop_state_to_cache,
)
from custom_components.vag_connect.coordinator import (
    _DROP_RETRY_MAX_STREAK,
    _drop_anchor_advanced,
)

_NOW = datetime(2026, 11, 6, 14, 10, 0, tzinfo=timezone.utc)
# The anchor every poll of his burst logged.
_HIS_ANCHOR = datetime(2026, 11, 4, 21, 0, 56, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# The reported scenario, as the sequence of decisions it actually is.
# --------------------------------------------------------------------------

def test_a_restart_with_the_same_anchor_does_not_refill_the_budget() -> None:
    """His four restart rows, with the high-water mark restored.

    No re-implementation of the scheduler's arithmetic here on purpose: the
    wiring is pinned structurally below, and a second copy of the sums is the
    documented way this class of gap got shipped twice.
    """
    high_water, streak = drop_state_from_cache(
        drop_state_to_cache(_HIS_ANCHOR, _DROP_RETRY_MAX_STREAK),
        _NOW, _DROP_RETRY_MAX_STREAK,
    )
    assert high_water == _HIS_ANCHOR
    assert streak == _DROP_RETRY_MAX_STREAK

    # Startup poll: the portal has not been read yet, so there is no anchor.
    assert _drop_anchor_advanced(high_water, None) is False
    # The poll that used to refill it: the anchor is the SAME old capture.
    assert _drop_anchor_advanced(high_water, _HIS_ANCHOR) is False
    # And a second and third time, because nothing has landed.
    assert _drop_anchor_advanced(high_water, _HIS_ANCHOR) is False


def test_a_genuinely_new_entry_still_starts_with_a_full_budget() -> None:
    """The decision from the first round, preserved exactly.

    An entry that has never captured anything has no reason to stand down. With
    no stored state the high-water mark is None, and the first anchor counts.
    """
    high_water, streak = drop_state_from_cache(None, _NOW, _DROP_RETRY_MAX_STREAK)
    assert high_water is None
    assert streak == 0
    assert _drop_anchor_advanced(high_water, _HIS_ANCHOR) is True


def test_a_real_drop_after_a_restart_still_refills_the_budget() -> None:
    high_water, _ = drop_state_from_cache(
        drop_state_to_cache(_HIS_ANCHOR, 3), _NOW, _DROP_RETRY_MAX_STREAK,
    )
    landed = _HIS_ANCHOR + timedelta(minutes=15)
    assert _drop_anchor_advanced(high_water, landed) is True


# --------------------------------------------------------------------------
# Round trip and defensive restore.
# --------------------------------------------------------------------------

def test_round_trip_keeps_both_values() -> None:
    raw = drop_state_to_cache(_HIS_ANCHOR, 2)
    assert isinstance(raw, dict)
    back, streak = drop_state_from_cache(raw, _NOW, _DROP_RETRY_MAX_STREAK)
    assert back == _HIS_ANCHOR
    assert streak == 2


def test_the_round_trip_survives_json_because_the_store_does_not() -> None:
    """``Store`` writes JSON, so the pair has to survive it.

    The direct round-trip above would still pass if the serialiser handed back
    a ``datetime``: the reader would never see it, because the value reaching
    it has been through ``json.dumps`` first. This is the path that actually
    runs.
    """
    import json

    for mark, streak in ((_HIS_ANCHOR, 2), (None, 0), (None, 3)):
        raw = json.loads(json.dumps(drop_state_to_cache(mark, streak)))
        back, got = drop_state_from_cache(raw, _NOW, _DROP_RETRY_MAX_STREAK)
        assert back == mark, (mark, back)
        assert got == streak, (streak, got)


def test_no_state_at_all_is_a_fresh_entry() -> None:
    for raw in (None, {}, [], "nonsense", 7, {"anchor": None, "streak": None}):
        assert drop_state_from_cache(raw, _NOW, _DROP_RETRY_MAX_STREAK) == (None, 0)


def test_a_streak_out_of_range_is_clamped() -> None:
    _, high = drop_state_from_cache(
        {"anchor": None, "streak": 9999}, _NOW, _DROP_RETRY_MAX_STREAK)
    assert high == _DROP_RETRY_MAX_STREAK
    _, low = drop_state_from_cache(
        {"anchor": None, "streak": -5}, _NOW, _DROP_RETRY_MAX_STREAK)
    assert low == 0


def test_an_anchor_in_the_future_is_clamped_to_now() -> None:
    """A future anchor would suppress every reset for as long as it is ahead.

    That is the one way this change could make things *worse* than the bug it
    fixes: a bogus value (a clock that was wrong when the file was written, or
    an edited store) would mean the budget never arms again and alignment is
    dead until someone deletes the file. Clamped, the worst case is one skipped
    refill.
    """
    future = _NOW + timedelta(days=30)
    anchor, _ = drop_state_from_cache(
        drop_state_to_cache(future, 0), _NOW, _DROP_RETRY_MAX_STREAK)
    assert anchor == _NOW
    # And a value just barely ahead is still clamped, not accepted.
    anchor2, _ = drop_state_from_cache(
        drop_state_to_cache(_NOW + timedelta(seconds=5), 0),
        _NOW, _DROP_RETRY_MAX_STREAK)
    assert anchor2 == _NOW


def test_a_naive_timestamp_is_read_as_utc_not_rejected() -> None:
    """``Store`` round-trips through JSON, and an older file or a hand edit can
    carry a stamp with no offset. Dropping it would silently refill the budget,
    which is the bug; reading it as UTC is what every other stamp in this
    integration does."""
    naive = _HIS_ANCHOR.replace(tzinfo=None).isoformat()
    anchor, _ = drop_state_from_cache(
        {"anchor": naive, "streak": 1}, _NOW, _DROP_RETRY_MAX_STREAK)
    assert anchor == _HIS_ANCHOR


def test_a_garbage_anchor_does_not_raise() -> None:
    for bad in ("", "not-a-date", "2026-13-45T99:99:99", 12345, {}, []):
        anchor, streak = drop_state_from_cache(
            {"anchor": bad, "streak": 2}, _NOW, _DROP_RETRY_MAX_STREAK)
        assert anchor is None, bad
        # The streak still survives: an unreadable anchor is not a reason to
        # hand back the budget as well.
        assert streak == 2, bad


# --------------------------------------------------------------------------
# Wiring, pinned structurally — same reason as the first round's test.
# --------------------------------------------------------------------------

def _coordinator_src() -> list[str]:
    path = (Path(__file__).resolve().parent.parent / "custom_components"
            / "vag_connect" / "coordinator.py")
    return path.read_text(encoding="utf-8").splitlines()


def test_the_decision_compares_against_the_high_water_mark() -> None:
    """The call site must pass the persisted mark, not the per-poll anchor.

    This replaces the first round's pin on
    ``_drop_anchor_advanced(_prev_anchor, _cap_anchor)``. That pin was right for
    what it guarded and is wrong now: ``_prev_anchor`` is reset to None by every
    restart, which is the whole of #1850's second round. The predicate itself is
    unchanged — only what is handed to it as "previous".
    """
    lines = _coordinator_src()
    call = next((i for i, ln in enumerate(lines)
                 if "sleep_s: float = _drop_anchored_sleep_s(" in ln), None)
    assert call is not None, "the scheduler call moved"
    start = next(i for i, ln in enumerate(lines)
                 if "_decision_now = datetime.now(" in ln)
    window = [ln.strip() for ln in lines[start:call]]
    assert any(
        "_drop_anchor_advanced(self._drop_anchor_high_water, _cap_anchor)" in ln
        for ln in window
    ), window
    # And the mark has to move forward when a drop lands, or it never advances.
    assert any("self._drop_anchor_high_water = _cap_anchor" in ln
               for ln in window), window


def test_the_mark_and_the_streak_are_actually_persisted() -> None:
    """A field that is computed and never written is the bug, not the fix.

    The key the snapshot WRITES has to be the key setup READS. A plain
    ``'"drop_state"' in src`` check is not that: renaming the written key left
    the read untouched, the substring still matched on the read line, and the
    mutation survived. Measured, which is why this compares the two literals.
    """
    lines = _coordinator_src()
    src = "\n".join(lines)
    assert "drop_state_to_cache(" in src, "the snapshot does not serialise it"
    assert "drop_state_from_cache(" in src, "setup does not restore it"

    written = re.findall(r'"([A-Za-z_]+)":\s*drop_state_to_cache\(', src)
    assert len(written) == 1, f"expected one written key, found {written}"

    read_idx = next(i for i, ln in enumerate(lines)
                    if "drop_state_from_cache(" in ln)
    read_window = "\n".join(lines[read_idx:read_idx + 4])
    read = re.findall(r'cached\.get\("([A-Za-z_]+)"\)', read_window)
    assert len(read) == 1, f"expected one read key near the restore, got {read}"

    assert written[0] == read[0], (
        f"the snapshot writes {written[0]!r} but setup reads {read[0]!r}; the "
        "budget would be saved and never restored"
    )


@pytest.mark.parametrize("name", [
    "_drop_anchor_high_water",
])
def test_the_field_is_initialised(name: str) -> None:
    src = "\n".join(_coordinator_src())
    assert f"self.{name}" in src, name
