# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2096 — the newer of two paired SoC samples wins, with its value and its time.

The ``battery_state_report.soc`` leaf under key 506cb83e has a time of its own:
the ``car_captured_time`` entry under key 72e1ae0b. The VALID HV pair and the
leaf are then two samples of one series, taken at different times. These tests
cover:

* the leaf pair, by key only (other points share the leaf's name, #1195);
* a paired time beats a borrowed one for the same name, whatever the times;
* the newer paired sample gives both value and time; on a tie, or when one
  side has no time of its own, the HV pair wins (#1088) with the HV time;
* ``reconcile`` refuses a sample older than the recorded one, except in the
  #1195 hold case, which the hold and its #2134 release decide;
* in the #1195 hold, a leaf with an own time newer than the held one gives
  that one sample, and the hold stays for the next poll; the hold keeps the
  held value when the time is borrowed, older, or unmarked.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from custom_components.vag_connect.cariad.vehicle_cache import reconcile
from tests.test_2096_pair_capture_times import (
    SOC_STAMP,
    SOC_STATE,
    SOC_TS,
    _map,
    _p,
    _vehicle,
    _walk,
    _walk_all,
)

LEAF_KEY = "506cb83e-f99f-3af3-bbeb-0429b69a78d9"
LEAF_TS_KEY = "72e1ae0b-580f-371a-b3b7-730a66df681e"
FROZEN_KEY = "7bddd5e7-0000-0000-0000-000000000001"  # #1195: same name, other key
HV_KEY = "ac1108b1-b8cc-3db9-a663-03d387e42223"

SOC_ISO = "2026-11-13T06:57:12+00:00"
LATER = "2026-11-13T12:00:00Z"
LATER_ISO = "2026-11-13T12:00:00+00:00"
EARLIER = "2026-11-13T05:00:00Z"
EARLIER_ISO = "2026-11-13T05:00:00+00:00"
LATER_EPOCH = datetime.fromisoformat(LATER_ISO).timestamp()


def _hv(value: str = "32") -> list[dict[str, str]]:
    return [_p(HV_KEY, "battery_level_HV.value", value), SOC_STATE, SOC_STAMP]


def _leaf(value: str, ts: str) -> list[dict[str, str]]:
    return [_p(LEAF_KEY, "battery_state_report.soc", value),
            _p(LEAF_TS_KEY, "car_captured_time", ts)]


def _soc(items: list[dict[str, str]]) -> tuple[object, object, object, object]:
    d = _map(items)
    return (d.battery_soc, d.field_captured_ts.get("battery_soc"),
            d.field_source_leaf.get("battery_soc"),
            d.field_captured_inherited.get("battery_soc"))


# ── the leaf pair ─────────────────────────────────────────────────────────────
def test_leaf_takes_its_own_paired_time() -> None:
    _flat, ts, _syn, _cont, _uuids, inh = _walk(_leaf("31", LATER))
    assert ts["battery_state_report.soc"] == LATER_EPOCH
    assert "battery_state_report.soc" not in inh


def test_leaf_is_paired_by_key_not_by_name() -> None:
    items = [_p(LEAF_TS_KEY, "car_captured_time", LATER),
             _p(FROZEN_KEY, "battery_state_report.soc", "67")]
    _flat, ts, _syn, _cont, _uuids, inh = _walk(items)
    # the frozen point only borrows the marker in front of it
    assert "battery_state_report.soc" in inh


def test_two_leaf_times_pair_nothing() -> None:
    items = [*_hv(), *_leaf("31", LATER),
             _p(LEAF_TS_KEY, "car_captured_time", EARLIER)]
    soc, ts, leaf, inh = _soc(items)
    assert (soc, ts, leaf, inh) == (32, SOC_ISO, "battery_level_HV.value", False)


# ── a paired time beats a borrowed one ───────────────────────────────────────
def test_paired_leaf_beats_a_frozen_twin_in_any_order() -> None:
    newer_marker = _p("33333333-0000-0000-0000-000000000001",
                      "car_captured_utc_timestamp", "2026-11-14T00:00:00Z")
    frozen = _p(FROZEN_KEY, "battery_state_report.soc", "67")
    base = [*_leaf("31", LATER), newer_marker, frozen]
    rng = random.Random(2096)
    for _ in range(100):
        items = base[:]
        rng.shuffle(items)
        flat, ts, _syn, contested, _uuids, inh = _walk(items)
        assert flat["battery_state_report.soc"] == "31", items
        assert ts["battery_state_report.soc"] == LATER_EPOCH
        assert "battery_state_report.soc" not in inh
        assert "battery_state_report.soc" not in contested


def test_paired_leaf_voids_a_contest_between_borrowed_twins() -> None:
    # 76, 76 and 50 under keys of their own, without times of their own; then
    # the paired 55. The #1088 majority step must not put 76 next to 55's time.
    marker = _p("33333333-0000-0000-0000-000000000001",
                "car_captured_utc_timestamp", "2026-11-14T00:00:00Z")
    twins = [_p(f"7bddd5e7-0000-0000-0000-00000000000{i}",
                "battery_state_report.soc", v)
             for i, v in enumerate(("76", "76", "50"), start=1)]
    base = [marker, *twins, *_leaf("55", LATER)]
    rng = random.Random(2248)
    orders = [base, [*_leaf("55", LATER), marker, *twins]]
    for _ in range(100):
        items = base[:]
        rng.shuffle(items)
        orders.append(items)
    for items in orders:
        flat, ts, _syn, contested, _uuids, inh = _walk(items)
        assert flat["battery_state_report.soc"] == "55", items
        assert ts["battery_state_report.soc"] == LATER_EPOCH
        assert "battery_state_report.soc" not in inh
        assert "battery_state_report.soc" not in contested


# ── the newer paired sample wins ─────────────────────────────────────────────
def test_newer_leaf_wins_with_its_value_and_time() -> None:
    soc, ts, leaf, inh = _soc([*_hv("32"), *_leaf("31", LATER)])
    assert (soc, ts, leaf, inh) == (31, LATER_ISO, "battery_state_report.soc", False)
    d = _map([*_hv("32"), *_leaf("31", LATER)])
    # the flag says that the VALID pair was in the export; the leaf name
    # says where the value came from
    assert d.battery_soc_from_hv is True
    attrs = _vehicle(d)
    assert attrs["field_captured_inherited"]["battery_soc"] is False


def test_newer_hv_wins_with_the_hv_time() -> None:
    soc, ts, leaf, inh = _soc([*_hv("32"), *_leaf("35", EARLIER)])
    assert (soc, ts, leaf, inh) == (32, SOC_ISO, "battery_level_HV.value", False)
    assert _map([*_hv("32"), *_leaf("35", EARLIER)]).battery_soc_from_hv is True


def test_an_own_time_without_the_pair_is_no_leaf_evidence() -> None:
    # same name, another key, a timestamp entry in its own record: not the pair
    other = {"key": FROZEN_KEY, "dataFieldName": "battery_state_report.soc",
             "value": "31", "timestamp": LATER}
    _flat, ts, _syn, _cont, _uuids, inh, paired = _walk_all([other])
    assert ts["battery_state_report.soc"] == LATER_EPOCH
    assert "battery_state_report.soc" not in inh
    assert "battery_state_report.soc" not in paired
    d = _map([*_hv("32"), other])
    assert (d.battery_soc, d.battery_soc_from_hv) == (32, True)
    assert d.field_captured_ts["battery_soc"] == SOC_ISO


def test_equal_times_keep_the_hv_pair() -> None:
    soc, ts, leaf, _inh = _soc([*_hv("32"), *_leaf("31", SOC_TS)])
    assert (soc, ts, leaf) == (32, SOC_ISO, "battery_level_HV.value")


def test_hv_without_own_time_keeps_the_hv_value() -> None:
    hv_no_stamp = [_p(HV_KEY, "battery_level_HV.value", "32"), SOC_STATE]
    soc, _ts, _leaf_src, _inh = _soc([*hv_no_stamp, *_leaf("31", LATER)])
    assert soc == 32


def test_choice_does_not_depend_on_list_order() -> None:
    base = [*_hv("32"), *_leaf("31", LATER)]
    rng = random.Random(1088)
    for _ in range(100):
        items = base[:]
        rng.shuffle(items)
        assert _soc(items)[:2] == (31, LATER_ISO), items


# ── reconcile ────────────────────────────────────────────────────────────────
def _snap(
    soc: int, ts: str, *, own: bool | None = True, from_hv: bool = True,
    paired: bool | None = None,
) -> dict:
    out: dict = {
        "battery_soc": soc,
        "battery_soc_from_hv": from_hv,
        "field_captured_ts": {"battery_soc": ts},
        "field_source_leaf": {"battery_soc": "battery_state_report.soc"},
        "field_sources": {"battery_soc": "eu_data_act"},
    }
    if own is not None:
        out["field_captured_inherited"] = {"battery_soc": not own}
    # an own time from the key pair, unless the test says otherwise
    if own if paired is None else paired:
        out["battery_soc_ts_paired"] = True
    return out


def test_an_older_sample_does_not_replace_the_recorded_one() -> None:
    merged, notes = reconcile(_snap(31, LATER_ISO), _snap(32, SOC_ISO))
    assert merged["battery_soc"] == 31
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO
    assert any("older sample" in n for n in notes)


def test_a_newer_sample_replaces_the_recorded_one() -> None:
    merged, _ = reconcile(_snap(32, SOC_ISO), _snap(31, LATER_ISO))
    assert merged["battery_soc"] == 31


def test_an_unmarked_snapshot_is_no_evidence() -> None:
    # a snapshot cached by an older version has no own-time mark
    merged, _ = reconcile(_snap(31, LATER_ISO, own=None), _snap(32, SOC_ISO))
    assert merged["battery_soc"] == 32


def test_a_borrowed_time_is_no_evidence() -> None:
    merged, _ = reconcile(_snap(31, LATER_ISO), _snap(32, SOC_ISO, own=False))
    assert merged["battery_soc"] == 32


def test_a_recorded_time_in_the_future_is_no_evidence() -> None:
    # a car clock that jumped ahead once must not block every later reading
    ahead = (datetime.now(tz=timezone.utc) + timedelta(days=2)).isoformat()
    merged, notes = reconcile(_snap(32, ahead), _snap(31, LATER_ISO))
    assert merged["battery_soc"] == 31
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO
    assert not any("older sample" in n for n in notes)


def test_a_recorded_time_just_ahead_still_counts() -> None:
    # inside the margin: a small clock skew is still a real, newer sample
    soon = (datetime.now(tz=timezone.utc) + timedelta(minutes=2)).isoformat()
    merged, _ = reconcile(_snap(32, soon), _snap(31, LATER_ISO))
    assert merged["battery_soc"] == 32


def test_a_kept_sample_keeps_its_source_leaf() -> None:
    # the recorded value came from the leaf; an older HV sample does not
    # replace it, and the kept value keeps its own leaf name and HV flag
    prev = _snap(31, LATER_ISO, from_hv=False)
    fresh = _snap(32, SOC_ISO)
    fresh["field_source_leaf"] = {"battery_soc": "battery_level_HV.value"}
    merged, notes = reconcile(prev, fresh)
    assert merged["battery_soc"] == 31
    assert merged["field_source_leaf"]["battery_soc"] == "battery_state_report.soc"
    assert merged["battery_soc_from_hv"] is False
    assert any("older sample" in n for n in notes)


def test_a_refused_older_hv_delivery_does_not_start_the_hold() -> None:
    # after a #2134 release the recorded leaf 40 (12:00) has the flag False.
    # An older delivery with a VALID HV pair (45, 06:57) is refused, and it
    # must not set the flag: the next leaf-only 50 with a borrowed time is
    # shown, not held at 40 by the #1195 hold.
    prev = _snap(40, LATER_ISO, from_hv=False)
    merged1, notes = reconcile(prev, _snap(45, SOC_ISO))
    assert merged1["battery_soc"] == 40
    assert merged1["battery_soc_from_hv"] is False
    assert any("older sample" in n for n in notes)
    merged2, notes = reconcile(
        merged1, _snap(50, LATER_ISO, own=False, from_hv=False)
    )
    assert merged2["battery_soc"] == 50
    assert merged2["battery_soc_from_hv"] is False
    assert not any("held recorded" in n for n in notes)


def test_hold_releases_on_a_newer_own_leaf_time() -> None:
    merged, notes = reconcile(_snap(44, SOC_ISO), _snap(50, LATER_ISO, from_hv=False))
    assert merged["battery_soc"] == 50
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO
    assert any("own capture time" in n for n in notes)


def test_hold_stays_on_an_older_own_leaf_time() -> None:
    merged, _ = reconcile(_snap(44, LATER_ISO), _snap(50, SOC_ISO, from_hv=False))
    assert merged["battery_soc"] == 44
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO


def test_an_older_leaf_in_the_hold_case_still_releases_on_energy() -> None:
    # the recorded HV 80 (12:00) against a leaf-only poll with an older paired
    # time (06:57), a parked car and energy figures near 40 % that moved since
    # the recorded poll. This is the #1195 hold case, not an older delivery:
    # the #2134 energy release must stay reachable, as on main
    prev = _energy(_snap(80, LATER_ISO), 62.8, 78.5)
    fresh = _energy(_snap(40, SOC_ISO, from_hv=False), 31.4, 78.5)
    merged, notes = reconcile(prev, fresh)
    assert merged["battery_soc"] == 40
    assert any("hold released" in n for n in notes)
    assert not any("older sample" in n for n in notes)


def test_an_older_leaf_in_the_hold_case_is_held_without_evidence() -> None:
    # the same poll without energy figures: the hold keeps the recorded 80
    # with its own time, and the refusal of an older delivery does not run
    merged, notes = reconcile(_snap(80, LATER_ISO), _snap(40, SOC_ISO, from_hv=False))
    assert merged["battery_soc"] == 80
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO
    assert merged["battery_soc_from_hv"] is True
    assert not any("older sample" in n for n in notes)


def test_a_frozen_older_leaf_in_the_hold_case_meets_the_energy_check() -> None:
    # the recorded HV 80 (12:00) against a leaf-only poll that repeats 80
    # with an older paired time (06:57). The energy figures moved to 40 %
    # on a parked car. The hold keeps 80, and the energy check corrects
    # it, as on main; the older-sample refusal does not run
    prev = _energy(_snap(80, LATER_ISO), 80.0, 100.0)
    fresh = _energy(_snap(80, SOC_ISO, from_hv=False), 40.0, 100.0)
    merged, notes = reconcile(prev, fresh)
    assert merged["battery_soc"] == 40
    assert any("energy-derived" in n for n in notes)
    assert not any("older sample" in n for n in notes)
    assert "battery_soc_ts_paired" not in merged


def test_hold_stays_on_a_borrowed_leaf_time() -> None:
    merged, _ = reconcile(
        _snap(44, SOC_ISO), _snap(50, LATER_ISO, own=False, from_hv=False)
    )
    assert merged["battery_soc"] == 44


def test_energy_veto_still_blocks_the_release() -> None:
    fresh = _snap(74, LATER_ISO, from_hv=False)
    fresh["battery_available_kwh"] = 290.0  # 55.4 % of 523: agrees with the held 55
    fresh["battery_cap_kwh"] = 523.0
    merged, _ = reconcile(_snap(55, SOC_ISO), fresh)
    assert merged["battery_soc"] == 55


# ── review follow-ups ────────────────────────────────────────────────────────
MARKER_13 = _p("33333333-0000-0000-0000-000000000013",
               "car_captured_utc_timestamp", "2026-11-13T13:00:00Z")


def _poll(items: list[dict[str, str]]) -> dict:
    snap = _map(items).to_dict()
    snap["field_sources"] = {**(snap.get("field_sources") or {}),
                             "battery_soc": "eu_data_act"}
    return snap


def _leaf_without_time(value: str) -> list[dict[str, str]]:
    # the leaf without its 72e1ae0b entry: its time is borrowed from the marker
    return [MARKER_13, _p(LEAF_KEY, "battery_state_report.soc", value)]


def test_the_parser_marks_the_hv_pair_also_when_the_leaf_wins() -> None:
    d = _map([*_hv("32"), *_leaf("31", LATER)])
    assert d.battery_soc_from_hv is True
    assert d.field_source_leaf["battery_soc"] == "battery_state_report.soc"
    assert _map(_leaf_without_time("67")).battery_soc_from_hv is False


def test_a_leaf_win_beside_the_hv_pair_keeps_the_hold() -> None:
    # poll 1: the paired leaf (12:00) is newer than the HV pair (06:57) in the
    # same poll and wins. Poll 2: only the leaf, without a time of its own. The
    # car still sends the HV pair, so poll 2 holds the recorded 31.
    poll0 = _poll(_hv("32"))
    merged1, _ = reconcile(poll0, _poll([*_hv("32"), *_leaf("31", LATER)]))
    assert merged1["battery_soc"] == 31
    assert merged1["battery_soc_from_hv"] is True
    merged2, notes = reconcile(merged1, _poll(_leaf_without_time("67")))
    assert merged2["battery_soc"] == 31
    assert merged2["field_captured_ts"]["battery_soc"] == LATER_ISO
    assert merged2["field_source_leaf"]["battery_soc"] == "battery_state_report.soc"
    assert merged2["battery_soc_from_hv"] is True
    assert any("held recorded 31" in n for n in notes)


def _energy(snap: dict, avail: float, cap: float = 100.0) -> dict:
    return {**snap, "battery_available_kwh": avail, "battery_cap_kwh": cap}


def test_a_real_release_follows_the_leaf_from_then_on() -> None:
    # #2134: in a poll WITHOUT the HV pair, the energy sits nearer the leaf;
    # that ends the hold, and the car follows the leaf after that.
    poll0 = _poll(_hv("32"))
    merged1, notes = reconcile(
        poll0, _energy(_poll(_leaf_without_time("60")), 60.0)
    )
    assert merged1["battery_soc"] == 60
    assert any("hold released" in n for n in notes)
    assert merged1["battery_soc_from_hv"] is False
    merged2, notes = reconcile(merged1, _poll(_leaf_without_time("67")))
    assert merged2["battery_soc"] == 67
    assert not any("held recorded" in n for n in notes)


def test_an_own_time_release_takes_one_sample_only() -> None:
    # a newer own leaf time shows that this sample is newer, not that the HV
    # pair stopped: the next leaf without its time is held again
    poll0 = _poll(_hv("32"))
    merged1, notes = reconcile(poll0, _poll(_leaf("31", LATER)))
    assert merged1["battery_soc"] == 31
    assert any("hold kept for the next poll" in n for n in notes)
    assert merged1["battery_soc_from_hv"] is True
    merged2, notes = reconcile(merged1, _poll(_leaf_without_time("67")))
    assert merged2["battery_soc"] == 31
    assert any("held recorded 31" in n for n in notes)


def test_a_leaf_win_beside_the_hv_pair_stands_against_the_energy() -> None:
    # jneuveglise (#2096): HV 81 VALID after a charge to 80, energy 39.1 / 78.5
    # kWh (49.8 %). The paired leaf 81 three seconds later wins; the guard must
    # not turn it into 50, in that poll or in the next leaf-only poll whose
    # leaf gives no #2134 release (80 and 81 sit equally far from 49.8 %).
    hv_ts = "2026-11-13T06:57:15Z"
    hv = [_p(HV_KEY, "battery_level_HV.value", "81"), SOC_STATE,
          _p("3f5a294b-b672-3963-83d8-bfb54e5b943d", "timestamp", "2026-11-13T06:57:12Z")]
    prev = _energy(_poll(_hv("80")), 39.1, 78.5)
    fresh = _energy(_poll([*hv, *_leaf("81", hv_ts)]), 39.1, 78.5)
    assert fresh["field_source_leaf"]["battery_soc"] == "battery_state_report.soc"
    merged1, _ = reconcile(prev, fresh)
    assert merged1["battery_soc"] == 81
    merged2, _ = reconcile(
        merged1, _energy(_poll(_leaf_without_time("80")), 39.1, 78.5)
    )
    assert merged2["battery_soc"] == 81


def test_a_kept_sample_stands_against_the_older_energy() -> None:
    # the recorded value is kept because this delivery is an older snapshot;
    # its energy figures are from that older delivery too, so the guard must
    # not replace the newer value with them, HV car or not
    for from_hv in (True, False):
        prev = _energy(_snap(80, LATER_ISO, from_hv=from_hv), 62.8, 78.5)
        fresh = _energy(_snap(40, SOC_ISO, from_hv=from_hv), 31.4, 78.5)
        merged, notes = reconcile(prev, fresh)
        assert any("older sample" in n for n in notes)
        assert merged["battery_soc"] == 80
        assert merged["battery_soc_ts_paired"] is True


def test_the_hv_win_drops_the_leaves_contest() -> None:
    # two borrowed leaves disagree; the VALID HV pair wins, so the reading is
    # not ambiguous
    twins = [MARKER_13,
             _p("7bddd5e7-0000-0000-0000-000000000001", "battery_state_report.soc", "18"),
             _p("7bddd5e7-0000-0000-0000-000000000002", "battery_state_report.soc", "36")]
    d = _map([*_hv("36"), *twins])
    assert (d.battery_soc, d.battery_soc_from_hv) == (36, True)
    assert "battery_soc" not in d.ambiguous_fields


def test_the_hv_time_is_the_time_of_the_hv_value() -> None:
    # a generic "value" point under the HV key is a separate entry. Its own
    # time is not the time of battery_level_HV.value, which has none here, so
    # the VALID pair wins (#1088) and the leaf's newer time is not compared
    # with the time of another entry
    alias = {"key": HV_KEY, "dataFieldName": "value", "value": "32",
             "timestamp": EARLIER}
    hv_no_stamp = [_p(HV_KEY, "battery_level_HV.value", "32"), SOC_STATE]
    d = _map([alias, *hv_no_stamp, *_leaf("31", LATER)])
    assert (d.battery_soc, d.battery_soc_from_hv) == (32, True)
    assert d.field_source_leaf["battery_soc"] == "battery_level_HV.value"


def test_an_imported_value_keeps_its_own_time_mark() -> None:
    # False (an own time) is carried like True (a borrowed one)
    prev = {"odometer_km": 999, "field_imported_from_export": ["odometer_km"],
            "field_sources": {"odometer_km": "eu_data_act"},
            "field_captured_ts": {"odometer_km": LATER_ISO},
            "field_captured_inherited": {"odometer_km": False}}
    merged, _ = reconcile(prev, {"odometer_km": None})
    assert merged["odometer_km"] == 999
    assert merged["field_captured_inherited"] == {"odometer_km": False}


def test_a_hold_of_a_leaf_value_is_not_contested_again() -> None:
    # the held value came from the leaf; this poll's contested twins are not
    # about it and must not move it
    prev = _snap(31, LATER_ISO)  # a leaf value on a car that sends the pair
    fresh = _snap(67, SOC_ISO, own=False, from_hv=False)
    fresh["contested_fields"] = {"battery_state_report.soc": ["30", "67"]}
    merged, _ = reconcile(prev, fresh)
    assert merged["battery_soc"] == 31


def test_an_older_sample_with_contested_twins_keeps_the_recorded_one() -> None:
    # the older poll's twins are both older than the recorded 31: the twin
    # closest to 31 must not take its place
    fresh = _snap(70, EARLIER_ISO, from_hv=False)
    fresh["contested_fields"] = {"battery_state_report.soc": ["30", "70"]}
    fresh["ambiguous_fields"] = {"battery_soc": "2 candidates disagree: 30 vs 70"}
    merged, notes = reconcile(_snap(31, LATER_ISO, from_hv=False), fresh)
    assert merged["battery_soc"] == 31
    assert "battery_soc" not in merged.get("ambiguous_fields", {})
    assert any("older sample" in n for n in notes)


def test_a_kept_sample_keeps_its_own_ambiguity_note() -> None:
    # #2252: the kept value gets back what describes it, not the rejected
    # sample's note
    prev = _snap(31, LATER_ISO, from_hv=False)
    prev["ambiguous_fields"] = {"battery_soc": "2 candidates disagree: 31 vs 76"}
    fresh = _snap(70, EARLIER_ISO, from_hv=False)
    fresh["ambiguous_fields"] = {"battery_soc": "2 candidates disagree: 30 vs 70"}
    merged, notes = reconcile(prev, fresh)
    assert any("older sample" in n for n in notes)
    assert merged["battery_soc"] == 31
    assert merged["ambiguous_fields"] == prev["ambiguous_fields"]


def test_a_paired_win_voids_a_contest_after_an_own_time() -> None:
    # borrowed 76, 76, 50, then 40 with a time of its own, then the paired 55:
    # 55 wins on the normal path, and the contest of the borrowed twins must not
    # put 76 next to its time
    twins = [_p(f"7bddd5e7-0000-0000-0000-00000000000{i}",
                "battery_state_report.soc", v)
             for i, v in enumerate(("76", "76", "50"), start=1)]
    own = {"key": "7bddd5e7-0000-0000-0000-000000000009",
           "dataFieldName": "battery_state_report.soc", "value": "40",
           "timestamp": "2026-11-12T00:00:00Z"}
    marker = _p("33333333-0000-0000-0000-000000000001",
                "car_captured_utc_timestamp", "2026-11-11T00:00:00Z")
    base = [marker, *twins, own, *_leaf("55", LATER)]
    rng = random.Random(2096)
    orders = [base]
    for _ in range(100):
        items = base[:]
        rng.shuffle(items)
        orders.append(items)
    for items in orders:
        flat, ts, _syn, contested, _uuids, _inh = _walk(items)
        assert flat["battery_state_report.soc"] == "55", items
        assert ts["battery_state_report.soc"] == LATER_EPOCH
        assert "battery_state_report.soc" not in contested
        assert _soc(items)[:2] == (55, LATER_ISO), items


def test_the_paired_leaf_is_found_by_its_own_name() -> None:
    # another SoC name with a newer BORROWED time must not stand in for the
    # paired leaf in the comparison with the HV pair
    bare = _p("55555555-0000-0000-0000-000000000001", "soc", "40")
    base = [*_hv("32"), *_leaf("31", LATER), MARKER_13, bare]
    rng = random.Random(2248)
    orders = [base]
    for _ in range(50):
        items = base[:]
        rng.shuffle(items)
        orders.append(items)
    for items in orders:
        d = _map(items)
        assert d.battery_soc == 31, items
        assert d.field_captured_ts["battery_soc"] == LATER_ISO
        assert d.field_source_leaf["battery_soc"] == "battery_state_report.soc"
        assert d.battery_soc_from_hv is True


def test_a_generic_leaf_name_pairs_the_uuid_not_the_shared_name() -> None:
    # the leaf sent under the generic name "value", known only by its key
    generic_leaf = [_p(LEAF_KEY, "value", "31"),
                    _p(LEAF_TS_KEY, "car_captured_time", LATER)]
    _flat, _ts, _syn, _cont, _uuids, _inh, paired = _walk_all(generic_leaf)
    assert LEAF_KEY in paired
    assert "value" not in paired
    d = _map([*_hv("32"), *generic_leaf])
    assert d.battery_soc == 31
    assert d.field_source_leaf["battery_soc"] == LEAF_KEY
    assert d.field_captured_ts["battery_soc"] == LATER_ISO


def test_the_paired_leaf_win_drops_the_other_names_contest() -> None:
    # the "soc" twins borrow an older time, so first_freshest picks the paired
    # leaf itself; their contest must not mark the paired value ambiguous
    older = _p("33333333-0000-0000-0000-000000000011",
               "car_captured_utc_timestamp", "2026-11-11T00:00:00Z")
    twins = [older, _p("55555555-0000-0000-0000-000000000001", "soc", "31"),
             _p("55555555-0000-0000-0000-000000000002", "soc", "76")]
    d = _map([*_hv("32"), *_leaf("31", LATER), *twins])
    assert d.battery_soc == 31
    assert d.field_source_leaf["battery_soc"] == "battery_state_report.soc"
    assert "battery_soc" not in d.ambiguous_fields


def test_a_leaf_released_on_its_own_time_stands_against_the_energy() -> None:
    # held 40 (06:57), the leaf 74 with a newer own time (12:00), energy 58 %:
    # neither the veto nor the energy release applies, the own time releases,
    # and the energy guard must not then put 58 next to the leaf's time
    fresh = _energy(_snap(74, LATER_ISO, from_hv=False), 58.0)
    merged, notes = reconcile(_snap(40, SOC_ISO), fresh)
    assert any("own capture time" in n for n in notes)
    assert merged["battery_soc"] == 74
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO


def test_an_own_stamp_without_the_pair_is_no_evidence_in_reconcile() -> None:
    # a frozen leaf with a sibling stamp of its own, newer than the held HV
    # value (#1195): no release, and an HV sample is not refused against it
    frozen = _snap(67, LATER_ISO, from_hv=False, paired=False)
    merged, notes = reconcile(_snap(55, SOC_ISO), frozen)
    assert merged["battery_soc"] == 55
    assert not any("hold released" in n for n in notes)
    merged, notes = reconcile(frozen, _snap(55, SOC_ISO))
    assert merged["battery_soc"] == 55
    assert not any("older sample" in n for n in notes)


def test_the_parser_marks_only_a_paired_soc_time() -> None:
    assert _map(_hv("32")).battery_soc_ts_paired is True
    assert _map(_leaf("31", LATER)).battery_soc_ts_paired is True
    other = {"key": FROZEN_KEY, "dataFieldName": "battery_state_report.soc",
             "value": "31", "timestamp": LATER}
    d = _map([other])
    assert d.field_captured_inherited["battery_soc"] is False
    assert d.battery_soc_ts_paired is None


def test_a_held_value_keeps_its_paired_mark() -> None:
    prev = _snap(31, LATER_ISO)  # a leaf value on a car that sends the pair
    merged, _ = reconcile(prev, _poll(_leaf_without_time("67")))
    assert merged["battery_soc"] == 31
    assert merged["battery_soc_ts_paired"] is True


def test_the_age_release_ends_the_hold_also_with_a_newer_own_time() -> None:
    # the HV pair stopped days ago: the 24 h + odometer evidence ends the hold
    # for good, even when the newer own leaf time would release this sample
    prev = _snap(55, "2026-11-08T10:00:00+00:00")
    fresh = _snap(74, "2026-11-16T10:00:00+00:00", from_hv=False)
    fresh["field_captured_ts"]["odometer_km"] = "2026-11-16T09:00:00+00:00"
    merged, notes = reconcile(prev, fresh)
    assert merged["battery_soc"] == 74
    assert any("h older than the leaf" in n for n in notes)
    assert merged["battery_soc_from_hv"] is False


def test_a_leaf_time_in_the_future_does_not_beat_the_hv_pair() -> None:
    ahead = (datetime.now(tz=timezone.utc) + timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    d = _map([*_hv("55"), *_leaf("70", ahead)])
    assert (d.battery_soc, d.battery_soc_from_hv) == (55, True)


def test_the_export_import_brings_the_soc_flags_only_with_the_soc() -> None:
    from custom_components.vag_connect.coordinator import _gap_fill_from_export

    hist = {"battery_soc": 55, "battery_soc_from_hv": True,
            "battery_soc_ts_paired": True}
    live = {"battery_soc": 62, "battery_soc_from_hv": False,
            "battery_soc_ts_paired": None}
    assert _gap_fill_from_export(live, dict(hist)) == []
    assert (live["battery_soc_from_hv"], live["battery_soc_ts_paired"]) == (False, None)
    empty = {"battery_soc": None, "battery_soc_from_hv": None,
             "battery_soc_ts_paired": None}
    filled = _gap_fill_from_export(empty, dict(hist))
    # the flags go with the SoC, but get no import mark of their own
    assert filled == ["battery_soc"]
    assert empty["field_imported_from_export"] == ["battery_soc"]
    assert (empty["battery_soc_from_hv"], empty["battery_soc_ts_paired"]) == (True, True)
    # a dongle-held SoC is replaced: the pair mark follows the export's SoC
    held = {"battery_soc": 70, "battery_soc_from_hv": False,
            "battery_soc_ts_paired": True,
            "field_sources": {"battery_soc": "drivepulse"}}
    hist2 = {"battery_soc": 55, "battery_soc_from_hv": True}
    _gap_fill_from_export(held, hist2)
    assert held["battery_soc"] == 55
    assert held["battery_soc_from_hv"] is True
    assert "battery_soc_ts_paired" not in held


def test_an_imported_soc_does_not_lend_its_flags_to_a_later_reading() -> None:
    # the imported SoC is carried while the feed has none; then a feed SoC
    # with an unpaired time arrives: it must not wear the export's pair mark
    from custom_components.vag_connect.coordinator import _gap_fill_from_export

    # a car without the HV pair: the export's SoC is a paired leaf reading
    snap = {"battery_soc": None}
    _gap_fill_from_export(snap, _snap(55, SOC_ISO, from_hv=False))
    merged1, _ = reconcile(snap, {"battery_soc": None})
    assert (merged1["battery_soc"], merged1["battery_soc_ts_paired"]) == (55, True)
    later = _snap(60, LATER_ISO, from_hv=False, paired=False)
    merged2, _ = reconcile(merged1, later)
    assert merged2["battery_soc"] == 60
    assert "battery_soc_ts_paired" not in merged2


def test_a_paired_time_ahead_of_the_clock_is_not_marked() -> None:
    ahead = (datetime.now(tz=timezone.utc) + timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    hv = [_p(HV_KEY, "battery_level_HV.value", "55"), SOC_STATE,
          _p("3f5a294b-b672-3963-83d8-bfb54e5b943d", "timestamp", ahead)]
    d = _map(hv)
    assert d.battery_soc == 55
    assert d.battery_soc_ts_paired is None


def test_a_derived_soc_loses_the_paired_mark() -> None:
    # never-HV car: the paired leaf 94, energy 67 %: the guard writes 67, and
    # 67 is no dated sample
    fresh = _energy(_snap(94, LATER_ISO, from_hv=False), 67.0)
    merged, notes = reconcile(_snap(90, SOC_ISO, from_hv=False), fresh)
    assert merged["battery_soc"] == 67
    assert "battery_soc_ts_paired" not in merged


def test_an_equal_own_time_does_not_beat_the_pair_in_any_order() -> None:
    t = "2026-11-13T12:00:00Z"
    other = {"key": FROZEN_KEY, "dataFieldName": "battery_state_report.soc",
             "value": "67", "timestamp": t}
    for items in ([*_leaf("55", t), other], [other, *_leaf("55", t)],
                  [_leaf("55", t)[1], other, _leaf("55", t)[0]]):
        flat, _ts, _syn, contested, _uuids, _inh, paired = _walk_all(items)
        assert flat["battery_state_report.soc"] == "55", items
        assert "battery_state_report.soc" in paired
        assert "battery_state_report.soc" not in contested


def test_a_paired_time_never_goes_out_with_another_value() -> None:
    # the paired 60 and two own-stamped 71 at exactly the same time, in any
    # order: whatever value wins, the pair mark goes only with the 60
    t = "2026-11-13T12:00:00Z"
    twins = [{"key": f"7bddd5e7-0000-0000-0000-00000000000{i}",
              "dataFieldName": "battery_state_report.soc", "value": "71",
              "timestamp": t} for i in (1, 2)]
    base = [*_leaf("60", t), *twins]
    rng = random.Random(1088)
    orders = [base]
    for _ in range(50):
        items = base[:]
        rng.shuffle(items)
        orders.append(items)
    for items in orders:
        flat, _ts, _syn, _cont, _uuids, _inh, paired = _walk_all(items)
        assert "battery_state_report.soc" in paired, items
        assert flat["battery_state_report.soc"] == "60", items


def test_an_export_without_the_pair_does_not_clear_the_hv_flag() -> None:
    # the flag is sticky in reconcile (the car sends the pair): an export
    # without the pair can set it but never clear it
    from custom_components.vag_connect.coordinator import _gap_fill_from_export

    held = {"battery_soc": 70, "battery_soc_from_hv": True,
            "field_sources": {"battery_soc": "drivepulse"}}
    _gap_fill_from_export(held, {"battery_soc": 55, "battery_soc_from_hv": False})
    assert held["battery_soc"] == 55
    assert held["battery_soc_from_hv"] is True


def test_a_paired_leaf_is_not_contested_by_another_soc_name() -> None:
    # a car without the HV pair: the paired leaf 31 wins; the "soc" twins'
    # contest must not put another value next to its paired time
    prev = _snap(40, SOC_ISO, from_hv=False)
    fresh = _snap(31, LATER_ISO, from_hv=False)
    fresh["contested_fields"] = {"soc": ["38", "76"]}
    merged, _ = reconcile(prev, fresh)
    assert merged["battery_soc"] == 31
    assert merged["battery_soc_ts_paired"] is True


def test_an_unpaired_hv_time_is_no_evidence_against_the_leaf() -> None:
    # the HV value with a stamp of its own that is not its key pair: the VALID
    # pair wins (#1088), even though the paired leaf is newer
    hv = [{"key": HV_KEY, "dataFieldName": "battery_level_HV.value",
           "value": "32", "timestamp": EARLIER}, SOC_STATE]
    d = _map([*hv, *_leaf("31", LATER)])
    assert (d.battery_soc, d.battery_soc_from_hv) == (32, True)


def test_an_hv_alias_win_drops_the_leaves_contest() -> None:
    # first_freshest picks the HV UUID alias (newest borrowed time); the HV
    # value still must not carry the contest of the "soc" leaves
    older = _p("33333333-0000-0000-0000-000000000011",
               "car_captured_utc_timestamp", "2026-11-11T00:00:00Z")
    items = [older,
             _p("55555555-0000-0000-0000-000000000001", "soc", "18"),
             _p("55555555-0000-0000-0000-000000000002", "soc", "36"),
             *_hv("36"), MARKER_13, _p(HV_KEY, "value", "36")]
    d = _map(items)
    assert (d.battery_soc, d.battery_soc_from_hv) == (36, True)
    assert "battery_soc" not in d.ambiguous_fields
