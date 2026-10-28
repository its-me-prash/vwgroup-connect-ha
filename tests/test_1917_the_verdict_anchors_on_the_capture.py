# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1917 — the staleness verdict was anchored on the wrong clock.

``_capture_age_s`` read ``last_seen_at`` and its own docstring called that "the
car's own data was captured". It is not. ``last_seen_at`` says when the delivery
was last **seen**, and a channel refreshes that even when every value inside is
old. So the one verdict whose whole job is to flag a frozen feed measured the
wrong thing.

**Measured by a reporter, not inferred.** @tdrieshof's Audi Q6 e-tron (PPE, BE,
portal-only, v5.1.1): the car was at **38 %**, Home Assistant showed **56 %**,
and nothing in the UI suggested the reading was old. His own log carried the
answer:

    EU Data Act portal: *** dataset carried 70 fields (4 value-less)
    EU Data Act: anchored freshness on the per-point capture
      (2026-10-22T14:33:22+00:00) - the vehicle's own capture field was older
      or absent

@HeinMelissen saw the same shape on an Audi Q4 (#1364): a charge target set to
50 while the integration kept showing 80 — the last value it ever saw,
republished forever.

**The capture time was already in the snapshot the whole time.**
``field_captured_ts`` is a documented provenance map (``_PROVENANCE_MAPS`` in
``coordinator.py``); it already supplied the per-sensor ``data_captured_at``
attribute and flipped ``freshness_source`` from "dataset" to "point". The
per-sensor attributes knew when the car captured a value while the verdict did
not. Nothing had to be collected — one function had to look.

**Why no test caught it, measured rather than guessed.** Of the ten test files
that touch this area, only one sets both maps, and **not one** anywhere sets an
OLD capture next to a FRESH delivery. Both tests that call ``_capture_age_s``
directly pass it ``{"last_seen_at": ...}`` and nothing else. The function was
covered exclusively on its fallback path, so the path that mattered had no test
to fail.

**What this does NOT fix**, and the issue stays open for it: the 40 fields in
``CARRY_FORWARD_FIELDS`` still have no age limit of their own (only position
has one, at 24 h). This fixes the *global* verdict — "did the car capture
anything recently" — so a wholly frozen feed is now flagged. A single field
freezing while others keep moving is a per-field problem and is still open.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.const import CONF_SCAN_INTERVAL
from custom_components.vag_connect.coordinator import (
    VagConnectCoordinator,
    _capture_age_s,
)
from custom_components.vag_connect.repairs import STALE_DATA_MIN_AGE_S

VIN = "WVWZZZAUZFW000000"
HOUR = 3600.0


def _ago(hours: float) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()


def _coordinator(interval_min: int = 10) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = SimpleNamespace(
        entry_id="entry1",
        data={"brand": "audi"},
        options={CONF_SCAN_INTERVAL: interval_min},
    )
    return coord


def _close(age: float | None, hours: float) -> bool:
    return age is not None and abs(age - hours * HOUR) < 60


# ── the reported case ───────────────────────────────────────────────────────


def test_a_freshly_seen_delivery_of_old_captures_reads_old() -> None:
    """@tdrieshof's shape. Before the fix this answered a few minutes, because
    the delivery really had just been seen."""
    age = _capture_age_s({
        "vin": VIN,
        "last_seen_at": _ago(0.1),
        "field_captured_ts": {"battery_soc": _ago(48), "odometer_km": _ago(48)},
    })
    assert _close(age, 48), (
        f"the verdict measured the delivery sighting, not the capture: {age}"
    )


def test_the_whole_path_flags_it_stale() -> None:
    """End to end through the verdict, not just the helper. A correct age that
    nothing acts on would be no fix at all — the two halves have to be wired,
    and that connection is what a per-function test cannot see.

    80 h, deliberately above the 72 h bar — see the test below for why that
    number matters more than it looks.
    """
    coord = _coordinator()
    out = coord._redecide_stale({
        "vin": VIN,
        "last_seen_at": _ago(0.1),
        "field_captured_ts": {"battery_soc": _ago(80)},
    })
    assert out["data_stale"] is True


def test_the_reported_48_hours_still_does_not_flag_and_that_is_the_open_half() -> None:
    """**This is the uncomfortable half of #1917, pinned so it is a stated gap
    rather than a surprise.**

    ``STALE_DATA_MIN_AGE_S`` is **72 hours**. @tdrieshof's capture was about two
    days old, so with the anchor corrected his case is measured correctly — 48 h
    instead of six minutes — and still sits under the bar.

    While the anchor was wrong the bar never mattered: the age came out as
    minutes no matter how old the data was, so nothing ever approached 72 h.
    Fixing the anchor is what makes the threshold a live question for the first
    time, and three days is a long time for a feed whose normal cadence is about
    fifteen minutes.

    Lowering it is a user-facing change — more repair cards on more cars — so it
    is a decision rather than a fix, and it is not made here. If the bar moves,
    this test fails and should be rewritten to the new number rather than
    deleted: the fact worth keeping is that somebody chose the number.
    """
    coord = _coordinator()
    out = coord._redecide_stale({
        "vin": VIN,
        "last_seen_at": _ago(0.1),
        "field_captured_ts": {"battery_soc": _ago(48)},
    })
    assert out["data_stale"] is False
    assert STALE_DATA_MIN_AGE_S == 72 * 3600, (
        "the bar moved; rewrite this test to the new number and tell the "
        "reporters on #1917"
    )


def test_the_same_snapshot_without_the_map_is_not_flagged() -> None:
    """The control that makes the test above mean something: identical delivery
    sighting, no capture map, so the old anchor applies and says fresh."""
    coord = _coordinator()
    out = coord._redecide_stale({"vin": VIN, "last_seen_at": _ago(0.1)})
    assert out["data_stale"] is False


# ── newest capture wins ─────────────────────────────────────────────────────


def test_one_fresh_capture_among_old_ones_counts_as_fresh() -> None:
    """The question is "did the car capture ANYTHING recently", so the newest
    stamp decides. Using the oldest would flag every car with a slow-moving
    field — service intervals barely change by nature."""
    age = _capture_age_s({
        "field_captured_ts": {
            "battery_soc": _ago(48),
            "service_due_in_days": _ago(400),
            "range_km": _ago(0.2),
        },
    })
    assert _close(age, 0.2)


def test_every_stamp_old_means_old() -> None:
    age = _capture_age_s({
        "field_captured_ts": {"a": _ago(30), "b": _ago(40), "c": _ago(50)},
    })
    assert _close(age, 30)


def test_a_carried_forward_field_keeps_its_own_old_stamp() -> None:
    """The mechanism #1917 is about: a field carried forward from an earlier
    snapshot keeps its ORIGINAL capture stamp, and that is the point. If every
    field is carried forward, every stamp is old, the newest is old, and the
    verdict fires — which is what did not happen before. 90 h, above the 72 h
    bar, so this tests the wiring and not the threshold."""
    coord = _coordinator()
    carried = {
        "vin": VIN,
        "battery_soc": 56,
        "last_seen_at": _ago(0.05),          # the delivery WAS just seen
        "field_captured_ts": {"battery_soc": _ago(90)},
    }
    out = coord._redecide_stale(carried)
    assert out["battery_soc"] == 56, "the value is still carried, only labelled"
    assert out["data_stale"] is True


# ── the fallback chain, in order ────────────────────────────────────────────


def test_the_dongle_datenstand_is_used_when_there_is_no_map() -> None:
    age = _capture_age_s({"last_seen_at": _ago(0.1), "data_captured_at": _ago(12)})
    assert _close(age, 12)


def test_the_map_beats_the_dongle_stamp() -> None:
    age = _capture_age_s({
        "data_captured_at": _ago(12),
        "field_captured_ts": {"battery_soc": _ago(36)},
    })
    assert _close(age, 36)


@pytest.mark.parametrize(
    ("snapshot", "why"),
    [
        ({"last_seen_at": None}, "no stamp at all"),
        ({}, "empty snapshot"),
        ({"field_captured_ts": {}}, "map present but empty"),
        ({"field_captured_ts": "not-a-map"}, "map is not a dict"),
    ],
    ids=["none", "empty", "empty-map", "map-not-a-dict"],
)
def test_nothing_usable_states_no_verdict(snapshot: dict, why: str) -> None:
    """None means "do not flag", never "fresh". A missing clock must not become
    a reassurance."""
    assert _capture_age_s(dict(snapshot)) is None, why


def test_an_unparseable_stamp_falls_through_rather_than_flagging() -> None:
    """A broken entry in the map must not swallow the fallback: the snapshot
    still has a usable sighting, so use it."""
    age = _capture_age_s({
        "last_seen_at": _ago(5),
        "field_captured_ts": {"battery_soc": "not-a-timestamp"},
    })
    assert _close(age, 5)


def test_a_partly_broken_map_still_uses_its_good_entries() -> None:
    age = _capture_age_s({
        "last_seen_at": _ago(0.1),
        "field_captured_ts": {"bad": "nonsense", "battery_soc": _ago(20)},
    })
    assert _close(age, 20)


# ── behaviour kept on purpose ───────────────────────────────────────────────


def test_a_future_dated_clock_still_raises_no_alarm() -> None:
    """#465: a car whose OCU clock runs ahead yields a negative age, which is
    below any threshold. Deliberately unchanged — a wrong clock must not spam a
    repair."""
    coord = _coordinator()
    future = (datetime.now(tz=timezone.utc) + timedelta(hours=6)).isoformat()
    age = _capture_age_s({"field_captured_ts": {"battery_soc": future}})
    assert age is not None and age < 0
    assert coord._redecide_stale(
        {"vin": VIN, "field_captured_ts": {"battery_soc": future}}
    )["data_stale"] is False


def test_a_datetime_stamp_works_as_well_as_an_iso_string() -> None:
    """The channels are heterogeneous: the BFF and Skoda paths hand over a
    ``datetime``, the portal an ISO string. Both have to measure."""
    dt_stamp = datetime.now(tz=timezone.utc) - timedelta(hours=9)
    assert _close(_capture_age_s({"field_captured_ts": {"a": dt_stamp}}), 9)
    assert _close(_capture_age_s({"last_seen_at": dt_stamp}), 9)


def test_a_naive_datetime_is_read_as_utc() -> None:
    naive = (datetime.now(tz=timezone.utc) - timedelta(hours=7)).replace(tzinfo=None)
    assert _close(_capture_age_s({"field_captured_ts": {"a": naive}}), 7)
