# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2054 (@zintheweb, T-Cross 1.0 TSI 2024) — an implausible odometer UP-jump
must be rejected at ingest.

The reported car latched ``odometer_km = 100663`` (truth 27668): on 2026-10-24
between 14:00 and 14:15 UTC the value jumped from 26374 to 100663 and stayed
there, because ``odometer_km`` is monotonic-protected — once a spuriously HIGH
value is cached, every correct LOWER reading is rejected as "went backwards".
No channel had any jump / plausibility ceiling, so the glitch could enter the
cache in the first place.

The guard sits in ``reconcile`` right before the monotonic loop and rejects an
UP-move that is physically implausible:

* when both capture timestamps resolve (``last_seen_at``) and the elapsed time
  is positive, an affine ceiling ``BURST + RATE * elapsed_days`` — BURST absorbs
  one short-interval drive (a real single-poll jump is < ~200 km; over a 15-min
  poll even 50 km reads as ~4800 km/day, so a flat km/day ceiling would false-
  positive), RATE bounds a long offline-then-resume gap;
* when the elapsed time cannot be established (missing or non-increasing
  timestamps), ONLY an absolute catastrophic ceiling — no real poll ever adds
  tens of thousands of km, so it never fires on real driving yet still catches a
  sentinel-scale glitch.

Scope (user decision 2026-11-11): INGEST-guard only. It prevents any NEW car
from latching; it does NOT auto-heal a cache already stuck high — those users
reload the integration once. (The stateful cross-poll auto-heal was the declined
higher-risk option.)
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.vehicle_cache import reconcile

_T0 = "2026-10-24T14:00:00+00:00"
_T15M = "2026-10-24T14:15:00+00:00"   # +15 minutes (one poll)
_T1D = "2026-10-25T14:00:00+00:00"    # +1 day
_T180D = "2027-04-22T14:00:00+00:00"  # +180 days (a long offline gap)


# ── the reported defect ───────────────────────────────────────────────────────
def test_2054_implausible_jump_within_one_poll_is_rejected() -> None:
    previous = {"odometer_km": 26374, "last_seen_at": _T0}
    fresh = {"odometer_km": 100663, "last_seen_at": _T15M}
    merged, notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 26374, "the +74289 km/15-min glitch must not enter the cache"
    assert any("odometer" in n.lower() for n in notes)


def test_2054_rejection_keeps_the_newer_last_seen_at_untouched() -> None:
    """Rejecting the odometer glitch must not also roll back the fresh capture
    time — only the implausible odometer value is held back."""
    previous = {"odometer_km": 26374, "last_seen_at": _T0}
    fresh = {"odometer_km": 100663, "last_seen_at": _T15M}
    merged, _notes = reconcile(previous, fresh)
    assert merged["last_seen_at"] == _T15M


# ── false-positive guards: real driving must pass ─────────────────────────────
def test_plausible_highway_burst_in_one_poll_is_accepted() -> None:
    """50 km in 15 min is ~4800 km/day instantaneous — a flat km/day ceiling
    would wrongly reject it; the affine BURST term must let it through."""
    previous = {"odometer_km": 26374, "last_seen_at": _T0}
    fresh = {"odometer_km": 26424, "last_seen_at": _T15M}
    merged, _notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 26424


def test_long_offline_then_resume_is_accepted() -> None:
    """A car offline ~6 months accumulates a large real jump; the RATE*elapsed
    term must clear it."""
    previous = {"odometer_km": 10000, "last_seen_at": _T0}
    fresh = {"odometer_km": 40000, "last_seen_at": _T180D}  # +30000 over 180 d
    merged, _notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 40000


def test_normal_daily_increase_is_accepted() -> None:
    previous = {"odometer_km": 26374, "last_seen_at": _T0}
    fresh = {"odometer_km": 26500, "last_seen_at": _T1D}  # +126 km in a day
    merged, _notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 26500


# ── degraded case: timestamps absent / non-increasing → absolute ceiling only ─
def test_catastrophic_jump_without_timestamps_is_rejected() -> None:
    previous = {"odometer_km": 26374}
    fresh = {"odometer_km": 100663}
    merged, _notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 26374, "a sentinel-scale jump must be caught even with no timestamps"


def test_catastrophic_jump_with_equal_timestamps_is_rejected() -> None:
    """elapsed_days == 0 cannot validate a rate, so the absolute ceiling applies."""
    previous = {"odometer_km": 26374, "last_seen_at": _T0}
    fresh = {"odometer_km": 100663, "last_seen_at": _T0}
    merged, _notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 26374


def test_moderate_jump_without_timestamps_is_accepted() -> None:
    """Without timestamps the guard must stay conservative: only a catastrophic
    jump is rejected, so a plausible increase is never falsely frozen."""
    previous = {"odometer_km": 26374}
    fresh = {"odometer_km": 27000}  # +626 km, below the absolute ceiling
    merged, _notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 27000


# ── existing behaviour must be untouched ──────────────────────────────────────
def test_downward_move_still_held_by_the_monotonic_guard() -> None:
    previous = {"odometer_km": 100663, "last_seen_at": _T0}
    fresh = {"odometer_km": 27668, "last_seen_at": _T15M}
    merged, notes = reconcile(previous, fresh)
    assert merged["odometer_km"] == 100663  # unchanged: the existing monotonic rule
    assert any("went backwards" in n for n in notes)


def test_first_poll_without_previous_is_returned_untouched() -> None:
    fresh = {"odometer_km": 100663, "last_seen_at": _T15M}
    merged, notes = reconcile(None, fresh)
    assert merged["odometer_km"] == 100663
    assert notes == []
