"""#1917 second half (@InfObject) — the batch stamp may not outrank a live clock.

He did not just report this, he diagnosed it, and his reading was right:

    ``_capture_age_s`` selects the single available point timestamp, so the older
    setting dates the whole merged vehicle despite the newer web captures.

On his car the stamp map held **one** entry — ``target_soc`` from the EU Data Act
portal at about 82.5 h — while ``last_seen_at`` stood at about 16.3 h from a live
channel. Because the function preferred "newest entry of the map", and the newest
entry of a one-entry map is also its oldest, the 82-hour stamp dated the whole
merged vehicle and the better evidence was discarded.

Why the map is always the batch clock, which is what makes the rule safe:
``field_captured_ts`` is *written* in exactly one module, the EU Data Act mapper,
and holds at most seven values. ``last_seen_at`` is written by eight channels. So
a map stamp may only override ``last_seen_at`` when that clock is itself batch;
where a live channel contributed, the fresher of the two wins.

Two things are deliberately NOT changed, and both are pinned here so a later
reading does not mistake them for oversights:

* the map is not dropped — it is right for the portal-only car it was built for,
  and that case must still answer with the stamp;
* the age THRESHOLD is untouched. That is the open half of the original report,
  and mixing a correctness fix with a tuning decision would make both harder to
  judge.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.vag_connect.coordinator import (
    _capture_age_s,
    _drop_anchored_sleep_s,
    _has_live_contributor,
)

# The scheduler's own numbers, so the cadence tests below measure the real thing
# rather than a second copy of the arithmetic.
_INTERVAL_S = 600
_FLOOR_S = 180


def _sleep_for(snapshot: dict, now) -> float | None:
    """The sleep the scheduler would pick for this snapshot.

    Mirrors what ``coordinator`` does: rebuild the anchor from the capture age
    this helper returns, then ask the real scheduler.
    """
    from datetime import timedelta

    age = _capture_age_s(snapshot)
    if age is None or age < 0:
        return None
    anchor = now - timedelta(seconds=age)
    return _drop_anchored_sleep_s(_INTERVAL_S, anchor, now, _FLOOR_S, 0)

H = 3600.0


def _ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _near(actual: float | None, expected_hours: float, tol_h: float = 0.3) -> bool:
    return actual is not None and abs(actual - expected_hours * H) < tol_h * H


class TestTheReportedCase:
    """His numbers, end to end."""

    def test_the_eighty_two_hour_verdict_is_gone(self) -> None:
        age = _capture_age_s({
            "source_channel": "eu_data_act+website_authproxy",
            "last_seen_at": _ago(16.3),
            "field_captured_ts": {"target_soc": _ago(82.5)},
        })
        assert _near(age, 16.3), f"expected the live 16.3 h to win, got {age}"

    def test_without_the_fix_it_would_have_been_the_stamp(self) -> None:
        """Same snapshot minus the live contributor: the stamp still decides.

        This is the control for the test above — it shows the 82.5 h is really
        in the data and that only the contributor set changed the answer.
        """
        age = _capture_age_s({
            "source_channel": "eu_data_act",
            "last_seen_at": _ago(16.3),
            "field_captured_ts": {"target_soc": _ago(82.5)},
        })
        assert _near(age, 82.5), f"portal-only must still answer 82.5 h, got {age}"


class TestThePortalOnlyCaseIsUntouched:
    """The case the map was built for. If these break, #1917's first half is back."""

    def test_a_fresh_delivery_of_old_captures_still_reads_old(self) -> None:
        age = _capture_age_s({
            "source_channel": "eu_data_act",
            "last_seen_at": _ago(2),
            "field_captured_ts": {"battery_soc": _ago(48), "odometer_km": _ago(48)},
        })
        assert _near(age, 48), f"the carried-forward capture must win, got {age}"

    def test_an_absent_contributor_set_keeps_the_old_behaviour(self) -> None:
        """Every pre-existing caller passes no source_channel at all."""
        age = _capture_age_s({
            "last_seen_at": _ago(2),
            "field_captured_ts": {"battery_soc": _ago(48)},
        })
        assert _near(age, 48), f"unclassified cars stay on the old path, got {age}"


class TestTheFresherOfTheTwoWins:
    """Not "live always wins" — the fresher wins. Both directions."""

    def test_a_fresh_stamp_beats_an_older_live_clock(self) -> None:
        age = _capture_age_s({
            "source_channel": "eu_data_act+mbb",
            "last_seen_at": _ago(30),
            "field_captured_ts": {"battery_soc": _ago(1)},
        })
        assert _near(age, 1), f"the stamp was fresher and must win, got {age}"

    def test_an_equal_pair_is_stable(self) -> None:
        stamp = _ago(10)
        age = _capture_age_s({
            "source_channel": "eu_data_act+mbb",
            "last_seen_at": stamp,
            "field_captured_ts": {"battery_soc": stamp},
        })
        assert _near(age, 10), f"got {age}"

    def test_a_live_only_car_with_no_stamps_falls_through(self) -> None:
        age = _capture_age_s({
            "source_channel": "website_authproxy",
            "last_seen_at": _ago(4),
            "field_captured_ts": {},
        })
        assert _near(age, 4), f"got {age}"


class TestTheBrokenClockGuardSurvives:
    """#465 — a car whose clock runs ahead must raise no false alarm, and the
    new branch must not resurrect the masking the #465 guard removed."""

    def test_every_stamp_future_dated_still_yields_the_negative(self) -> None:
        age = _capture_age_s({
            "source_channel": "eu_data_act",
            "last_seen_at": _ago(50),
            "field_captured_ts": {"battery_soc": _ago(-6)},
        })
        assert age is not None and age < 0, f"the #465 behaviour is gone: {age}"

    def test_a_future_stamp_does_not_mask_a_sane_one(self) -> None:
        age = _capture_age_s({
            "source_channel": "eu_data_act",
            "last_seen_at": _ago(1),
            "field_captured_ts": {"a": _ago(-6), "b": _ago(90), "c": _ago(95)},
        })
        assert _near(age, 90), f"the sane stamps must decide, got {age}"

    def test_a_future_stamp_beside_a_live_clock_does_not_win_by_being_negative(
        self,
    ) -> None:
        """The new branch takes min() of two ages, and a negative would win it
        outright — the exact failure the #465 guard was added for. A
        future-dated stamp on a car with a live contributor must therefore not
        drag the verdict negative."""
        age = _capture_age_s({
            "source_channel": "eu_data_act+mbb",
            "last_seen_at": _ago(20),
            "field_captured_ts": {"battery_soc": _ago(-6)},
        })
        assert age is not None and age < 0, (
            "an all-future map keeps the #465 behaviour rather than mixing with "
            f"the live clock; got {age}"
        )


class TestTheContributorTest:
    """The proxy itself. It decides which path a car takes, so it gets its own
    cases rather than only being exercised through the function above."""

    def test_the_two_real_batch_tokens_are_batch(self) -> None:
        assert not _has_live_contributor({"source_channel": "eu_data_act"})
        assert not _has_live_contributor({"source_channel": "data_act_portal"})

    def test_a_mixed_car_has_a_live_contributor(self) -> None:
        assert _has_live_contributor(
            {"source_channel": "eu_data_act+website_authproxy"})

    def test_case_does_not_matter(self) -> None:
        assert not _has_live_contributor({"source_channel": "EU_DATA_ACT"})

    def test_unclassifiable_is_not_live(self) -> None:
        """Conservative on purpose: an unknown car keeps the old behaviour."""
        for raw in (None, "", "   ", 42, [], {}):
            assert not _has_live_contributor({"source_channel": raw}), raw
        assert not _has_live_contributor({})

    def test_every_other_known_token_counts_as_live(self) -> None:
        from custom_components.vag_connect._channel_labels import _CHANNEL_LABELS

        batch = {t for t in _CHANNEL_LABELS if "data_act" in t}
        assert batch, "control: the batch family must be findable by its marker"
        for token in _CHANNEL_LABELS:
            expected = token not in batch
            assert _has_live_contributor({"source_channel": token}) is expected, (
                f"{token} classified wrongly"
            )


class TestTheSideEffectOnThePollCadenceIsDeliberate:
    """``_capture_age_s`` is not only the staleness verdict — it is also the
    poll anchor.

    ``coordinator.py`` rebuilds the drop-anchored schedule from this exact
    helper ("reconstructed from the same capture-age helper the staleness
    watchdog uses"), so changing which clock wins changes when the next poll
    happens. That was not the goal of the #1917 fix and it was found by reading
    the scheduler afterwards rather than before, so it is pinned here instead of
    left to be discovered by whoever next touches the cadence.

    Measured, with a 600 s interval and a 180 s floor:

    * the reported car (stamp 82.5 h, live 16.3 h) sleeps 180 s either way — both
      clocks are long overdue, so the verdict changes and the cadence does not;
    * a car with a *fresh* live capture (3 min) behind an older stamp (2 h) goes
      from 180 s to 480 s, because the drop is no longer considered overdue.

    The direction matters: the change makes such a car poll **less**, not more.
    A portal the operator has asked community clients to go easier on is not a
    place to add traffic by accident, and this adds none.
    """

    def test_the_reported_car_keeps_its_cadence(self) -> None:
        now = datetime.now(timezone.utc)
        mixed = _sleep_for(
            {
                "source_channel": "eu_data_act+website_authproxy",
                "last_seen_at": _ago(16.3),
                "field_captured_ts": {"target_soc": _ago(82.5)},
            },
            now,
        )
        batch_only = _sleep_for(
            {
                "source_channel": "eu_data_act",
                "last_seen_at": _ago(16.3),
                "field_captured_ts": {"target_soc": _ago(82.5)},
            },
            now,
        )
        assert mixed == batch_only, (
            f"the cadence must not move for this car: {mixed} vs {batch_only}"
        )

    def test_a_fresh_live_capture_stops_the_fast_retry(self) -> None:
        now = datetime.now(timezone.utc)
        snapshot = {
            "last_seen_at": _ago(0.05),
            "field_captured_ts": {"battery_soc": _ago(2)},
        }
        mixed = _sleep_for({**snapshot, "source_channel": "eu_data_act+mbb"}, now)
        batch_only = _sleep_for({**snapshot, "source_channel": "eu_data_act"}, now)
        assert batch_only is not None and mixed is not None
        assert mixed > batch_only, (
            "a fresh live capture must stand the poll down, not speed it up: "
            f"{mixed} vs {batch_only}"
        )

    def test_the_change_never_polls_faster_than_before(self) -> None:
        """The property that matters, over every pairing of the two clocks.

        Whatever the two ages are, adding a live contributor may only leave the
        sleep the same or make it longer. A shorter sleep would mean the fix
        silently increased traffic.
        """
        now = datetime.now(timezone.utc)
        for stamp_h in (0.02, 0.2, 2, 20, 82.5):
            for live_h in (0.02, 0.2, 2, 20, 82.5):
                snapshot = {
                    "last_seen_at": _ago(live_h),
                    "field_captured_ts": {"battery_soc": _ago(stamp_h)},
                }
                mixed = _sleep_for(
                    {**snapshot, "source_channel": "eu_data_act+mbb"}, now)
                batch_only = _sleep_for(
                    {**snapshot, "source_channel": "eu_data_act"}, now)
                assert mixed is not None and batch_only is not None
                assert mixed >= batch_only, (
                    f"stamp={stamp_h}h live={live_h}h: the live contributor made "
                    f"it poll FASTER ({mixed} < {batch_only})"
                )
