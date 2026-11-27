# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A value that reconcile keeps in place of a rejected reading keeps its own
capture time.

When the odometer jumps too far (#2054) or a monotonic field goes backwards,
reconcile keeps the recorded value. Until now it left the capture time, the
source leaf and the borrowed-time mark of the rejected reading in place, so the
kept value showed a newer capture time than its own. That happened with the
portal's odometer, which carries a capture time, and would have happened with
volkswagen.de once its values carry one (found reviewing #2249).
"""
from __future__ import annotations

import copy

from custom_components.vag_connect.cariad.vehicle_cache import reconcile

_T_OLD = "2026-09-30T06:00:00+00:00"
_T_NEW = "2026-10-05T06:00:00+00:00"


def _snap(odo: float, ts: str | None, leaf: str, *, seen: str | None = None,
          inherited: bool | None = None, **extra: object) -> dict:
    snap: dict = {
        "odometer_km": odo,
        "field_sources": {"odometer_km": "eu_data_act"},
        "field_source_leaf": {"odometer_km": leaf},
        "source_channel": "eu_data_act",
    }
    if seen is not None:
        snap["last_seen_at"] = seen
    if ts is not None:
        snap["field_captured_ts"] = {"odometer_km": ts}
    if inherited is not None:
        snap["field_captured_inherited"] = {"odometer_km": inherited}
    snap.update(extra)
    return snap


def test_jump_over_the_ceiling_keeps_the_recorded_time() -> None:
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD, inherited=False)
    fresh = _snap(100663, _T_NEW, "mileage_km", seen=_T_NEW, inherited=True)
    merged, notes = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26374
    # the capture-time branch of #2054, not the absolute ceiling
    assert any("#2054" in n and " d, ceiling" in n for n in notes)
    assert merged["field_captured_ts"]["odometer_km"] == _T_OLD
    assert merged["field_source_leaf"]["odometer_km"] == "mileage.value"
    assert merged["field_captured_inherited"]["odometer_km"] is False


def test_jump_without_a_time_delta_keeps_the_recorded_time() -> None:
    """The absolute-ceiling branch of #2054, taken without usable last_seen."""
    prev = _snap(26374, _T_OLD, "mileage.value")
    fresh = _snap(500000, _T_NEW, "mileage_km")
    merged, notes = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26374
    assert any("absolute ceiling" in n for n in notes)
    assert merged["field_captured_ts"]["odometer_km"] == _T_OLD
    assert merged["field_source_leaf"]["odometer_km"] == "mileage.value"


def test_reading_that_went_backwards_keeps_the_recorded_time() -> None:
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD)
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW)
    merged, notes = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26374
    assert any("went backwards" in n for n in notes)
    assert merged["field_captured_ts"]["odometer_km"] == _T_OLD
    assert merged["field_source_leaf"]["odometer_km"] == "mileage.value"


def test_recorded_value_without_a_time_shows_none_instead_of_the_rejected_one() -> None:
    prev = _snap(26374, None, "mileage.value", seen=_T_OLD)
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW, inherited=False)
    merged, _ = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26374
    assert "odometer_km" not in (merged.get("field_captured_ts") or {})
    assert "odometer_km" not in (merged.get("field_captured_inherited") or {})


def test_other_fields_keep_their_fresh_times() -> None:
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD)
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW)
    fresh["battery_soc"] = 55
    fresh["field_captured_ts"]["battery_soc"] = _T_NEW
    merged, _ = reconcile(prev, fresh)
    assert merged["field_captured_ts"]["battery_soc"] == _T_NEW


def test_accepted_reading_keeps_its_own_fresh_time() -> None:
    """Guard: a plausible increase is the new value, with the new time."""
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD)
    fresh = _snap(26412, _T_NEW, "mileage_km", seen=_T_NEW)
    merged, notes = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26412
    assert not any("odometer_km" in n for n in notes)
    assert merged["field_captured_ts"]["odometer_km"] == _T_NEW
    assert merged["field_source_leaf"]["odometer_km"] == "mileage_km"


def test_charged_energy_that_went_backwards_keeps_its_recorded_time() -> None:
    prev = {
        "total_charged_energy_kwh": 812.0,
        "field_captured_ts": {"total_charged_energy_kwh": _T_OLD},
    }
    fresh = {
        "total_charged_energy_kwh": 790.0,
        "field_captured_ts": {"total_charged_energy_kwh": _T_NEW},
    }
    merged, notes = reconcile(prev, fresh)
    assert merged["total_charged_energy_kwh"] == 812.0
    assert any("went backwards" in n for n in notes)
    assert merged["field_captured_ts"]["total_charged_energy_kwh"] == _T_OLD


def test_the_inputs_are_not_modified() -> None:
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD, inherited=False)
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW, inherited=True)
    prev_copy, fresh_copy = copy.deepcopy(prev), copy.deepcopy(fresh)
    reconcile(prev, fresh)
    assert prev == prev_copy
    assert fresh == fresh_copy


def test_ambiguity_note_of_the_rejected_reading_is_dropped() -> None:
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD)
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW,
                  ambiguous_fields={"odometer_km": "2 candidates disagree: 26000 vs 26010"})
    merged, _ = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26374
    assert "odometer_km" not in (merged.get("ambiguous_fields") or {})


def test_ambiguity_note_of_the_recorded_value_comes_back() -> None:
    note = "2 candidates disagree: 26374 vs 26380"
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD,
                 ambiguous_fields={"odometer_km": note})
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW)
    merged, _ = reconcile(prev, fresh)
    assert merged["ambiguous_fields"]["odometer_km"] == note


def test_owner_of_the_recorded_value_comes_back() -> None:
    prev = _snap(26374, None, "odometer", seen=_T_OLD)
    prev["field_sources"] = {"odometer_km": "website_authproxy"}
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW)
    merged, _ = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26374
    assert merged["field_sources"]["odometer_km"] == "website_authproxy"
    assert merged["field_source_leaf"]["odometer_km"] == "odometer"
    assert "odometer_km" not in (merged.get("field_captured_ts") or {})


def test_a_cache_without_an_owner_keeps_the_fresh_owner() -> None:
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD)
    del prev["field_sources"]
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW)
    merged, _ = reconcile(prev, fresh)
    assert merged["field_sources"]["odometer_km"] == "eu_data_act"


def test_value_from_the_one_time_export_keeps_its_mark() -> None:
    """#1780: the import branch drops the mark because the fresh reading
    should win; when the guard rejects that reading the mark comes back."""
    prev = _snap(26374, _T_OLD, "mileage.value", seen=_T_OLD,
                 field_imported_from_export=["odometer_km"])
    fresh = _snap(26000, _T_NEW, "mileage_km", seen=_T_NEW)
    merged, _ = reconcile(prev, fresh)
    assert merged["odometer_km"] == 26374
    assert "odometer_km" in merged["field_imported_from_export"]
    assert merged["field_captured_ts"]["odometer_km"] == _T_OLD
