# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 (@shaarkys) — last_seen_at must not regress to a stale capture time.

On the EU Data Act portal the car's own capture timestamp arrives contested: a
fresh block next to a frozen one from an old stop-charging report. shaarkys got a
false "vehicle data hasn't refreshed in 138h" warning because a poll shipping only
the stale candidate (2026-08-15, ~138h old) latched ``last_seen_at`` backwards,
even though live values were current (recorded last_seen_at was that morning).

last_seen_at is the car's own data-capture time and only moves forward, so a poll
carrying an OLDER stamp must hold the recorded newer one. A genuinely fresher
reading still wins and auto-clears the warning.
"""
from __future__ import annotations

from datetime import datetime, timezone

from custom_components.vag_connect.cariad.vehicle_cache import reconcile


class TestLastSeenAtMonotonic:
    def test_stale_contested_stamp_does_not_regress(self) -> None:
        # shaarkys' real values: recorded fresh this morning, poll ships the frozen
        # 138h-old candidate.
        prev = {"last_seen_at": "2026-08-21T06:36:45Z"}
        fresh = {"last_seen_at": "2026-08-15T14:14:31Z"}
        merged, notes = reconcile(prev, fresh)
        assert merged["last_seen_at"] == "2026-08-21T06:36:45Z"
        assert any("last_seen_at went backwards" in n for n in notes)

    def test_a_genuinely_fresher_stamp_wins(self) -> None:
        prev = {"last_seen_at": "2026-08-21T06:36:45Z"}
        fresh = {"last_seen_at": "2026-08-21T09:10:00Z"}
        merged, _ = reconcile(prev, fresh)
        assert merged["last_seen_at"] == "2026-08-21T09:10:00Z"

    def test_datetime_typed_stamps_are_guarded_too(self) -> None:
        # BFF / Škoda paths hand last_seen_at as an aware datetime, not a string.
        prev = {"last_seen_at": datetime(2026, 8, 21, 6, 36, tzinfo=timezone.utc)}
        fresh = {"last_seen_at": datetime(2026, 8, 15, 14, 14, tzinfo=timezone.utc)}
        merged, _ = reconcile(prev, fresh)
        assert merged["last_seen_at"] == prev["last_seen_at"]

    def test_absent_fresh_stamp_carries_the_recorded_one_forward(self) -> None:
        # last_seen_at is in CARRY_FORWARD_FIELDS; a poll without it keeps the last.
        prev = {"last_seen_at": "2026-08-21T06:36:45Z"}
        fresh: dict = {}
        merged, _ = reconcile(prev, fresh)
        assert merged["last_seen_at"] == "2026-08-21T06:36:45Z"

    def test_no_previous_stamp_is_inert(self) -> None:
        prev: dict = {}
        fresh = {"last_seen_at": "2026-08-15T14:14:31Z"}
        merged, _ = reconcile(prev, fresh)
        assert merged["last_seen_at"] == "2026-08-15T14:14:31Z"
