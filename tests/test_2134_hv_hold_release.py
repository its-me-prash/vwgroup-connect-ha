# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2134 — the #1195 partial-dataset SoC hold must be able to release.

@sxiza84 (portal-only ID.3): the recorded HV SoC (55) was held for days while the
leaf (74) and the pack energy (358.5 / 523.0 kWh = 68.5 %) agreed the car had
been charged; the HV pair had stopped eight days earlier, and the held value
even carried the fresh leaf's capture time.

The hold now releases on one of two signals and keeps its own capture time:
  A. the fresh energy ratio is clearly nearer the leaf than the held value;
  B. when the energy figures are absent or inconclusive: the held value is at
     least 24 h older than the leaf AND the car's odometer stamp is newer than
     the held value (the odometer value itself is not compared).
A fresh energy ratio that is clearly nearer the held value vetoes a release.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.vag_connect.cariad.vehicle_cache import (
    reconcile,
    strip_runtime,
)

_FIX = Path(__file__).parent / "fixtures" / "eu_data_act_1195"

_HELD_TS = "2026-11-08T10:00:00+00:00"
_LEAF_TS = "2026-11-16T10:00:00+00:00"
_ODO_TS = "2026-11-16T09:00:00+00:00"
_DAY_S = 24 * 3600
_LEAF = "battery_state_report.soc"
_HV_LEAF = "battery_level_HV"


def _prev(soc: int = 55, held_ts: object = _HELD_TS) -> dict:
    return {
        "battery_soc": soc,
        "battery_soc_from_hv": True,
        "field_captured_ts": {"battery_soc": held_ts},
        "field_source_leaf": {"battery_soc": _HV_LEAF},
        "field_sources": {"battery_soc": "eu_data_act"},
    }


def _fresh(
    soc: int = 74,
    *,
    avail: float | None = None,
    cap: float | None = None,
    leaf_ts: object = _LEAF_TS,
    odo_ts: object | None = _ODO_TS,
) -> dict:
    ts: dict = {"battery_soc": leaf_ts}
    if odo_ts is not None:
        ts["odometer_km"] = odo_ts
    out: dict = {
        "battery_soc": soc,
        "battery_soc_from_hv": False,
        "field_captured_ts": ts,
        "field_source_leaf": {"battery_soc": _LEAF},
        "field_sources": {"battery_soc": "eu_data_act"},
    }
    if avail is not None:
        out["battery_available_kwh"] = avail
        out["battery_cap_kwh"] = cap
    return out


# ── signal A: energy ──────────────────────────────────────────────────────────
def test_reporter_case_releases_via_energy() -> None:
    merged, notes = reconcile(_prev(), _fresh(74, avail=358.5, cap=523.0))
    assert merged["battery_soc"] == 74
    assert merged["battery_soc_from_hv"] is False
    assert any("#2134" in n for n in notes)
    assert merged["field_captured_ts"]["battery_soc"] == _LEAF_TS
    assert merged["field_source_leaf"]["battery_soc"] == _LEAF


def test_energy_alone_releases_without_any_stamp_evidence() -> None:
    # signal A on its own: same-day stamps, no odometer stamp
    merged, notes = reconcile(
        _prev(held_ts="2026-11-16T08:00:00+00:00"),
        _fresh(74, avail=358.5, cap=523.0, odo_ts=None),
    )
    assert merged["battery_soc"] == 74
    assert any("#2134" in n and "energy" in n for n in notes)


def test_released_car_follows_the_leaf_afterwards() -> None:
    merged, _ = reconcile(_prev(), _fresh(74, avail=358.5, cap=523.0))
    prev = strip_runtime(merged)
    merged2, notes2 = reconcile(prev, _fresh(72))
    assert merged2["battery_soc"] == 72
    assert merged2["battery_soc_from_hv"] is False
    assert not any("held recorded" in n for n in notes2)
    merged3, _ = reconcile(strip_runtime(merged2), _fresh(71))
    assert merged3["battery_soc"] == 71


def test_frozen_leaf_still_held_when_energy_agrees_with_held() -> None:
    # held 55, energy 55.5 %, leaf 67: the leaf is the frozen one -> veto, even
    # though the age+trip signal alone would release.
    merged, notes = reconcile(_prev(), _fresh(67, avail=55.5, cap=100.0))
    assert merged["battery_soc"] == 55
    assert merged["battery_soc_from_hv"] is True
    assert any("held recorded 55" in n for n in notes)
    assert not any("#2134" in n for n in notes)


def test_leaf_only_two_points_nearer_does_not_release() -> None:
    # no odometer stamp, so only the energy signal is in play
    merged, _ = reconcile(
        _prev(81), _fresh(79, avail=49.8, cap=100.0, odo_ts=None)
    )
    assert merged["battery_soc"] == 81
    assert merged["battery_soc_from_hv"] is True


def test_margin_is_five_points_not_less() -> None:
    # held 60, leaf 63, ratio 66: held far 6, leaf far 3 -> diff 3 < 5 -> hold
    # (the age+trip signal is absent here).
    merged, _ = reconcile(
        _prev(60), _fresh(63, avail=66.0, cap=100.0, odo_ts=None)
    )
    assert merged["battery_soc"] == 60


# ── signal B: age + trip ──────────────────────────────────────────────────────
def test_no_energy_car_releases_on_age_and_trip() -> None:
    merged, notes = reconcile(_prev(), _fresh(74))
    assert merged["battery_soc"] == 74
    assert merged["battery_soc_from_hv"] is False
    assert any("#2134" in n for n in notes)


def test_no_energy_short_gap_holds() -> None:
    merged, _ = reconcile(
        _prev(held_ts="2026-11-16T08:00:00+00:00"), _fresh(74)
    )
    assert merged["battery_soc"] == 55
    assert merged["battery_soc_from_hv"] is True


def test_long_gap_without_newer_odometer_stamp_holds() -> None:
    # odometer stamp older than the held value: the car did not drive since.
    merged, _ = reconcile(
        _prev(), _fresh(74, odo_ts="2026-11-07T09:00:00+00:00")
    )
    assert merged["battery_soc"] == 55


def test_long_gap_without_any_odometer_stamp_holds() -> None:
    merged, _ = reconcile(_prev(), _fresh(74, odo_ts=None))
    assert merged["battery_soc"] == 55


def test_boundary_exactly_24_hours() -> None:
    held = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
    odo = (held + timedelta(hours=3)).isoformat()
    at = (held + timedelta(seconds=_DAY_S)).isoformat()
    just_under = (held + timedelta(seconds=_DAY_S - 1)).isoformat()
    m_at, _ = reconcile(_prev(held_ts=held.isoformat()), _fresh(74, leaf_ts=at, odo_ts=odo))
    m_under, _ = reconcile(
        _prev(held_ts=held.isoformat()), _fresh(74, leaf_ts=just_under, odo_ts=odo)
    )
    assert m_at["battery_soc"] == 74
    assert m_under["battery_soc"] == 55


def test_odometer_stamp_equal_to_held_does_not_release() -> None:
    m, _ = reconcile(_prev(), _fresh(74, odo_ts=_HELD_TS))
    assert m["battery_soc"] == 55


def test_damaged_stamps_hold_without_exception() -> None:
    for bad in (12345, ["2026-11-08"], {"x": 1}, "not-a-date", True):
        for where in ("held", "leaf", "odo"):
            held = bad if where == "held" else _HELD_TS
            leaf = bad if where == "leaf" else _LEAF_TS
            odo = bad if where == "odo" else _ODO_TS
            merged, _ = reconcile(
                _prev(held_ts=held), _fresh(74, leaf_ts=leaf, odo_ts=odo)
            )
            assert merged["battery_soc"] == 55, (bad, where)
            assert merged["battery_soc_from_hv"] is True


# ── the held value keeps its own capture time ─────────────────────────────────
def test_held_value_keeps_its_own_stamp_and_leaf() -> None:
    fresh = _fresh(67, avail=55.5, cap=100.0)
    fresh["ambiguous_fields"] = {"battery_soc": "2 candidates disagree", "x": "y"}
    snapshot = json.dumps(fresh, sort_keys=True)
    merged, _ = reconcile(_prev(), fresh)
    assert merged["battery_soc"] == 55
    assert merged["field_captured_ts"]["battery_soc"] == _HELD_TS
    assert merged["field_source_leaf"]["battery_soc"] == _HV_LEAF
    assert "battery_soc" not in merged["ambiguous_fields"]
    assert merged["ambiguous_fields"]["x"] == "y"
    # fresh must never be mutated
    assert json.dumps(fresh, sort_keys=True) == snapshot


def test_hold_without_recorded_stamp_drops_the_fresh_one() -> None:
    prev = _prev()
    prev["field_captured_ts"] = {}
    prev["field_source_leaf"] = {}
    merged, _ = reconcile(prev, _fresh(67, avail=55.5, cap=100.0))
    assert merged["battery_soc"] == 55
    assert "battery_soc" not in merged["field_captured_ts"]
    assert "battery_soc" not in merged["field_source_leaf"]


def test_carried_value_keeps_its_own_stamp() -> None:
    fresh = {
        "battery_soc": None,
        "battery_soc_from_hv": None,
        "field_captured_ts": {"odometer_km": _ODO_TS},
    }
    merged, _ = reconcile(_prev(), fresh)
    assert merged["battery_soc"] == 55
    assert merged["battery_soc_from_hv"] is True
    assert merged["field_captured_ts"]["battery_soc"] == _HELD_TS
    assert merged["field_captured_ts"]["odometer_km"] == _ODO_TS
    assert merged["field_source_leaf"]["battery_soc"] == _HV_LEAF
    assert "battery_soc" not in (fresh.get("field_captured_ts") or {})


def test_real_datasets_keep_dataset_12_stamp_while_values_stay() -> None:
    from tests.test_1195_partial_dataset_soc_hold import _parse

    names = sorted(p.name for p in _FIX.glob("dataset_*.json"))
    previous: dict | None = None
    seq: list = []
    stamps: list = []
    for name in names:
        merged, _ = reconcile(previous, _parse(name))
        seq.append(merged.get("battery_soc"))
        stamps.append((merged.get("field_captured_ts") or {}).get("battery_soc"))
        previous = strip_runtime(merged)
    assert seq == [66, 66, 66, 55], seq
    # #2096: the stamp is the value's OWN paired time (key 3f5a294b), not the
    # neighbouring capture entry the list order happened to put in front of it.
    assert stamps[0] == "2026-08-18T18:02:45.415000+00:00"
    assert stamps[1] == stamps[0]
    assert stamps[2] == stamps[0]
    # Dataset 15 carries the HV pair (55 at 18:43:14.337) and the leaf
    # 506cb83e (55 at 18:43:17 under 72e1ae0b). The newer sample wins, with
    # its time; the frozen 67 under 7bddd5e7 has no time of its own and loses.
    assert stamps[3] == "2026-08-18T18:43:17+00:00"


def test_never_hv_car_is_untouched() -> None:
    prev = {"battery_soc": 67, "battery_soc_from_hv": False}
    merged, notes = reconcile(prev, _fresh(70))
    assert merged["battery_soc"] == 70
    assert not any("#2134" in n for n in notes)


# ── a rejected odometer reading is no evidence ───────────────────────────────
# The release runs before the #2054 jump guard and the monotonic guard further
# down in ``reconcile``. The capture time of a reading those guards throw away
# must not release the held value; before the fix it did.
def _with_odo(snap: dict, km: float, seen: str | None) -> dict:
    out = dict(snap)
    out["odometer_km"] = km
    if seen is not None:
        out["last_seen_at"] = seen
    return out


def _prev_odo(km: float = 10_000, seen: str | None = _HELD_TS) -> dict:
    return _with_odo(_prev(), km, seen)


def _fresh_odo(km: float, seen: str | None = _LEAF_TS, **kw: object) -> dict:
    return _with_odo(_fresh(74, **kw), km, seen)  # type: ignore[arg-type]


def test_plausible_newer_reading_still_releases() -> None:
    merged, notes = reconcile(_prev_odo(), _fresh_odo(10_400))
    assert merged["battery_soc"] == 74
    assert merged["odometer_km"] == 10_400
    assert any("#2134" in n for n in notes)


def test_odometer_jump_over_the_ceiling_does_not_release() -> None:
    # eight days allow 800 + 8 x 1500 = 12,800 km; 30,000 is rejected (#2054)
    merged, notes = reconcile(_prev_odo(), _fresh_odo(40_000))
    assert merged["odometer_km"] == 10_000
    assert any("(#2054)" in n for n in notes)
    assert merged["battery_soc"] == 55
    assert merged["battery_soc_from_hv"] is True
    assert not any("#2134" in n for n in notes)


def test_odometer_jump_without_time_delta_does_not_release() -> None:
    # no usable last_seen_at delta: the absolute 50,000 km ceiling applies
    merged, notes = reconcile(
        _prev_odo(seen=None), _fresh_odo(70_001, seen=None)
    )
    assert merged["odometer_km"] == 10_000
    assert any("absolute ceiling" in n for n in notes)
    assert merged["battery_soc"] == 55
    assert not any("#2134" in n for n in notes)


def test_odometer_going_backwards_does_not_release() -> None:
    merged, notes = reconcile(_prev_odo(), _fresh_odo(9_000))
    assert merged["odometer_km"] == 10_000
    assert any("went backwards" in n for n in notes)
    assert merged["battery_soc"] == 55
    assert not any("#2134" in n for n in notes)


def test_rejected_odometer_does_not_block_the_energy_release() -> None:
    # signal A needs no odometer at all; a rejected reading leaves it alone
    merged, notes = reconcile(
        _prev_odo(), _fresh_odo(40_000, avail=358.5, cap=523.0)
    )
    assert merged["odometer_km"] == 10_000
    assert merged["battery_soc"] == 74
    assert any("#2134" in n for n in notes)


def test_equal_reading_counts_as_plausible() -> None:
    # same km, newer stamp: neither guard rejects it, so the stamp still counts
    merged, notes = reconcile(_prev_odo(), _fresh_odo(10_000))
    assert merged["battery_soc"] == 74
    assert any("#2134" in n for n in notes)
