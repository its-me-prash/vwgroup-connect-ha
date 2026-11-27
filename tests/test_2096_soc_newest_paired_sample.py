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
* ``reconcile`` refuses a sample older than the recorded one;
* the #1195 hold releases on a leaf with an own time newer than the held one,
  and still holds when the time is borrowed, older, or unmarked.
"""
from __future__ import annotations

import random
from datetime import datetime

from custom_components.vag_connect.cariad.vehicle_cache import reconcile
from tests.test_2096_pair_capture_times import (
    SOC_STAMP,
    SOC_STATE,
    SOC_TS,
    _map,
    _p,
    _vehicle,
    _walk,
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


# ── the newer paired sample wins ─────────────────────────────────────────────
def test_newer_leaf_wins_with_its_value_and_time() -> None:
    soc, ts, leaf, inh = _soc([*_hv("32"), *_leaf("31", LATER)])
    assert (soc, ts, leaf, inh) == (31, LATER_ISO, "battery_state_report.soc", False)
    attrs = _vehicle(_map([*_hv("32"), *_leaf("31", LATER)]))
    assert attrs["field_captured_inherited"]["battery_soc"] is False


def test_newer_hv_wins_with_the_hv_time() -> None:
    soc, ts, leaf, inh = _soc([*_hv("32"), *_leaf("35", EARLIER)])
    assert (soc, ts, leaf, inh) == (32, SOC_ISO, "battery_level_HV.value", False)


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
def _snap(soc: int, ts: str, *, own: bool | None = True, from_hv: bool = True) -> dict:
    out: dict = {
        "battery_soc": soc,
        "battery_soc_from_hv": from_hv,
        "field_captured_ts": {"battery_soc": ts},
        "field_source_leaf": {"battery_soc": "battery_state_report.soc"},
        "field_sources": {"battery_soc": "eu_data_act"},
    }
    if own is not None:
        out["field_captured_inherited"] = {"battery_soc": not own}
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


def test_hold_releases_on_a_newer_own_leaf_time() -> None:
    merged, notes = reconcile(_snap(44, SOC_ISO), _snap(50, LATER_ISO, from_hv=False))
    assert merged["battery_soc"] == 50
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO
    assert any("own capture time" in n for n in notes)


def test_hold_stays_on_an_older_own_leaf_time() -> None:
    merged, _ = reconcile(_snap(44, LATER_ISO), _snap(50, SOC_ISO, from_hv=False))
    assert merged["battery_soc"] == 44
    assert merged["field_captured_ts"]["battery_soc"] == LATER_ISO


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
