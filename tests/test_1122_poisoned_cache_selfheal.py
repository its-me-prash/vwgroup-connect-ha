# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1122 follow-up (dpk1987) — a snapshot poisoned with the odometer sentinel.

The v3.0.2 guard (`drop_odometer_sentinel`) correctly drops a FRESH 429,496,729
reading, yet the reporter still saw it after updating — because his cache had
stored the sentinel BEFORE the guard existed, and ``reconcile`` then did double
damage with that poisoned ``previous`` snapshot:

1. **Carry-forward** — when a poll's odometer is dropped to ``None`` by the guard,
   ``odometer_km`` (a CARRY_FORWARD field) was refilled from the cached
   429,496,729, endlessly resurrecting it.
2. **Monotonic guard** — ``odometer_km`` is monotonic-increasing, so even once the
   real low reading (1,794) arrived fresh, ``1_794 < 429_496_729`` was treated as
   "went backwards" and the sentinel was KEPT, actively blocking the true value.

``reconcile`` now heals a poisoned snapshot (drops the sentinel from ``previous``)
before either step, so the cache self-heals on the next poll on any channel.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.vehicle_cache import reconcile

_SENTINEL = 429_496_729


def test_poisoned_cache_is_not_carried_forward_when_poll_drops_it() -> None:
    """Fresh poll dropped the sentinel to None → must NOT refill from the poisoned
    cache; the odometer goes unknown rather than showing the sentinel again."""
    merged, _ = reconcile({"odometer_km": _SENTINEL}, {"odometer_km": None})
    assert merged.get("odometer_km") is None


def test_poisoned_cache_does_not_block_the_real_reading() -> None:
    """The reporter's real 1,794 km must land even though it is far below the
    cached sentinel — the monotonic guard must not keep the poison."""
    merged, _ = reconcile({"odometer_km": _SENTINEL}, {"odometer_km": 1_794})
    assert merged.get("odometer_km") == 1_794


def test_a_genuine_backwards_reading_is_still_rejected() -> None:
    """The monotonic guard must still protect a VALID recorded odometer from a
    stale low poll (the feature #1122's fix must not regress)."""
    merged, notes = reconcile({"odometer_km": 100_000}, {"odometer_km": 90_000})
    assert merged.get("odometer_km") == 100_000
    assert any("went backwards" in n for n in notes)


def test_a_valid_odometer_is_still_carried_forward() -> None:
    """A clean cache still back-fills a poll that omitted the odometer."""
    merged, _ = reconcile({"odometer_km": 1_794}, {"odometer_km": None})
    assert merged.get("odometer_km") == 1_794


def test_a_clean_snapshot_is_untouched() -> None:
    """No needless mutation when the cache holds no sentinel."""
    prev = {"odometer_km": 50_000, "battery_soc": 80}
    merged, _ = reconcile(prev, {"odometer_km": 50_010})
    assert merged.get("odometer_km") == 50_010
    assert prev == {"odometer_km": 50_000, "battery_soc": 80}  # not mutated
