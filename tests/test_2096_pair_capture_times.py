# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2096 — the state of charge and the odometer show their OWN capture time.

A flat EU Data Act export is an unordered event log. The walker gave every
value the time of the nearest capture entry before it in the list, so when the
portal reordered the list between two downloads the same, unchanged reading
got a different ``data_captured_at`` (up to 2.5 h off on one ID.7).

Two values can be tied to their time by KEY instead of by position: each of
``battery_level_HV.value`` / ``.state`` and ``mileage.value`` / ``.state`` has
a ``timestamp`` entry under a fixed key that is present in exactly the same
exports. Where that key carries ONE time in the file, the value takes it as its
own stamp. Everything else stays exactly as it was before:

* every stamp that was recorded before is recorded again, inherited ones
  included, so the consumers of ``field_captured_ts`` (the #2134 hold release,
  the stale-feed verdict, #465/#529 conflict choice, the ``last_seen`` cap)
  behave as before for every export without a unique pair; the control in these
  tests is the same walk with the pairing switched off;
* only the DISPLAY changes: ``data_captured_at`` for the state of charge and the
  odometer is shown when the stamp is the value's own, not when it was borrowed
  from a neighbouring capture entry. That is carried by
  ``field_captured_inherited``.
"""
from __future__ import annotations

import random
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.auth import _eu_data_act as eda
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

SOC_TS_KEY = "3f5a294b-b672-3963-83d8-bfb54e5b943d"
ODO_TS_KEY = "067f539c-85fe-3067-9c29-d63e177e3712"
SOC_TS = "2026-11-13T06:57:12Z"
ODO_TS = "2026-11-13T06:57:06Z"
SOC_UUID = "ac1108b1-b8cc-3db9-a663-03d387e42223"
ODO_UUID = "30cc36fd-71ca-3c09-9296-e94ebd47bd2b"
NEW_MAP = "field_captured_inherited"


def _p(key: str, name: str, value: str) -> dict[str, str]:
    return {"key": key, "dataFieldName": name, "value": value}


SOC_VALUE = _p(SOC_UUID, "battery_level_HV.value", "81")
SOC_STATE = _p("2a9de7f7-a846-3d18-9883-650de9c4e4e1", "battery_level_HV.state", "VALID")
SOC_STAMP = _p(SOC_TS_KEY, "timestamp", SOC_TS)
ODO_VALUE = _p(ODO_UUID, "mileage.value", "12345")
ODO_STATE = _p("a04d086d-70bb-30c2-8361-68da66b4fd97", "mileage.state", "VALID")
ODO_STAMP = _p(ODO_TS_KEY, "timestamp", ODO_TS)
# Frozen/stale capture markers of the kind the Cupra file carries.
MARKERS = [
    _p("11111111-0000-0000-0000-00000000000%d" % i, "car_captured_utc_timestamp",
       "2026-11-0%dT18:04:38Z" % i)
    for i in (6, 7, 8)
]
CHARGING = _p("22222222-0000-0000-0000-000000000001", "charging_state", "charging")
PLUG = _p("22222222-0000-0000-0000-000000000002",
          "plugStatusItem.plugConnectionState", "connected")
LEAF_SOC = _p("506cb83e-0000-0000-0000-000000000001", "battery_state_report.soc", "74")
MARKER_16 = _p("33333333-0000-0000-0000-000000000009", "car_captured_utc_timestamp",
               "2026-11-16T10:00:00Z")


def _walk(items: list[dict[str, str]]) -> tuple[Any, ...]:
    ts: dict[str, float] = {}
    syn: dict[str, set[str]] = {}
    contested: dict[str, set[str]] = {}
    uuids: dict[str, set[str]] = {}
    inh: set[str] = set()
    flat = _walk_fields({"data": items}, ts, syn, contested, uuids, None, inh)
    return flat, ts, syn, contested, uuids, inh


def _map(items: list[dict[str, str]]) -> VehicleData:
    flat, ts, syn, contested, uuids, inh = _walk(items)
    return map_dataset_to_vehicle_data(
        flat, VehicleData(vin="X"), ts, syn, contested, uuids, inh
    )


def _without_new_map(d: VehicleData) -> dict[str, Any]:
    out = d.to_dict()
    out.pop(NEW_MAP, None)
    return out


def _control(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the pairing off: the walk as it was before #2096."""
    monkeypatch.setattr(eda, "_collect_paired_ts", lambda payload: {})


def _full() -> list[dict[str, str]]:
    return [SOC_VALUE, SOC_STATE, SOC_STAMP, ODO_VALUE, ODO_STATE, ODO_STAMP,
            *MARKERS, CHARGING, PLUG]


def _unpaired() -> list[dict[str, str]]:
    """No time entries; the values follow a capture marker, so they inherit it."""
    return [MARKERS[0], SOC_VALUE, SOC_STATE, ODO_VALUE, ODO_STATE,
            MARKERS[1], MARKERS[2], CHARGING, PLUG]


def _snapshot(soc: str, odo: str, soc_ts: str, odo_ts: str, marker: str):
    return [
        _p("33333333-0000-0000-0000-000000000001", "car_captured_utc_timestamp", marker),
        _p(SOC_UUID, "battery_level_HV.value", soc),
        SOC_STATE,
        _p(SOC_TS_KEY, "timestamp", soc_ts),
        _p(ODO_UUID, "mileage.value", odo),
        ODO_STATE,
        _p(ODO_TS_KEY, "timestamp", odo_ts),
    ]


def _two_snapshots(newest_first: bool) -> list[dict[str, str]]:
    old = _snapshot("57", "12000", "2026-11-12T06:00:00Z", "2026-11-12T06:00:00Z",
                    "2026-11-12T06:00:05Z")
    new = _snapshot("81", "12100", "2026-11-13T06:00:00Z", "2026-11-13T06:00:00Z",
                    "2026-11-13T06:00:05Z")
    return [*new, *old] if newest_first else [*old, *new]


def _vehicle(d: VehicleData) -> dict[str, Any]:
    return merge_channels([("eu_data_act", d)]).to_dict()


def _attrs(vehicle: dict[str, Any], data_key: str) -> dict[str, Any]:
    from custom_components.vag_connect.sensor import (
        VagConnectSensor,
        VagSensorDescription,
    )

    coord = MagicMock()
    coord.data = {"X": vehicle}
    coord.vehicles = coord.data
    coord.is_read_only = MagicMock(return_value=False)
    coord.last_update_success = True
    desc = VagSensorDescription(key=data_key, data_key=data_key)
    return VagConnectSensor(coord, "X", desc).extra_state_attributes or {}


# ── R1: the pairing improvement ──────────────────────────────────────────────
def test_paired_stamps_do_not_depend_on_list_order() -> None:
    seen: set[tuple[Any, Any]] = set()
    rng = random.Random(2096)
    for _ in range(200):
        items = _full()
        rng.shuffle(items)
        d = _map(items)
        assert d.battery_soc == 81
        assert d.odometer_km == 12345
        seen.add((d.field_captured_ts.get("battery_soc"),
                  d.field_captured_ts.get("odometer_km")))
        # a paired stamp is the value's own: not flagged as borrowed
        assert "battery_soc" not in d.field_captured_inherited
        assert "odometer_km" not in d.field_captured_inherited
    assert len(seen) == 1, f"stamps moved with the list order: {seen}"
    soc_iso, odo_iso = next(iter(seen))
    assert soc_iso is not None and soc_iso.startswith("2026-11-13T06:57:12")
    assert odo_iso is not None and odo_iso.startswith("2026-11-13T06:57:06")


def test_one_key_may_repeat_with_the_same_time() -> None:
    d = _map([*_full(), SOC_STAMP])
    assert d.field_captured_ts["battery_soc"].startswith("2026-11-13T06:57:12")
    assert "battery_soc" not in d.field_captured_inherited


def test_only_the_paired_value_gets_its_own_stamp() -> None:
    d = _map([MARKERS[0], SOC_VALUE, SOC_STATE, SOC_STAMP, ODO_VALUE, ODO_STATE,
              *MARKERS[1:]])
    assert d.field_captured_ts["battery_soc"].startswith("2026-11-13T06:57:12")
    assert "battery_soc" not in d.field_captured_inherited
    # no time entry for the odometer: it keeps the stamp it inherited, flagged
    assert d.field_captured_ts["odometer_km"]
    assert d.field_captured_inherited["odometer_km"] is True


def test_the_other_stamped_fields_still_take_the_neighbour_stamp() -> None:
    items = [MARKERS[0], CHARGING, MARKERS[1], PLUG, MARKERS[2],
             SOC_VALUE, SOC_STATE, SOC_STAMP]
    d = _map(items)
    assert d.field_captured_ts["charging_state"].startswith("2026-11-06")
    assert d.field_captured_ts["plug_state"].startswith("2026-11-07")


def test_a_point_with_its_own_sibling_stamp_keeps_it() -> None:
    """The #1688 dialect (``timestampUtc`` beside the value) is a genuine own
    stamp, not a neighbour's."""
    items = [{"dataFieldName": "mileage", "value": "777",
              "timestampUtc": "2026-10-03T16:59:46Z"}]
    d = _map(items)
    assert d.field_captured_ts["odometer_km"].startswith("2026-10-03T16:59:46")
    assert "odometer_km" not in d.field_captured_inherited


# ── R2: nothing is suppressed; consumers equal the walk without pairing ──────
@pytest.mark.parametrize("seed", range(8))
def test_an_export_without_a_pair_equals_the_control_walk(
    seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = _unpaired()
    random.Random(seed).shuffle(items)
    got = _map(items)
    walk = _walk(items)
    _control(monkeypatch)
    want = _map(items)
    assert _without_new_map(got) == _without_new_map(want)
    assert _walk(items) == walk


def test_the_inherited_stamps_are_recorded_as_before() -> None:
    d = _map(_unpaired())
    assert d.field_captured_ts["battery_soc"].startswith("2026-11-06")
    assert d.field_captured_ts["odometer_km"].startswith("2026-11-06")
    assert d.field_captured_ts["charging_state"].startswith("2026-11-08")


@pytest.mark.parametrize("newest_first", [False, True])
def test_two_snapshots_in_one_file_equal_the_control_walk(
    newest_first: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#465/#529: a file with two snapshots carries two times under the SAME key,
    and a flat list does not say which belongs to which value: nothing is paired,
    so the walk and the mapping equal the one made before the pairing existed."""
    items = _two_snapshots(newest_first)
    got_walk = _walk(items)
    got = _map(items)
    _control(monkeypatch)
    assert _walk(items) == got_walk
    want = _map(items)
    assert _without_new_map(got) == _without_new_map(want)
    assert got.field_captured_ts == want.field_captured_ts
    assert got.field_captured_ts["battery_soc"]
    assert got.field_captured_ts["odometer_km"]


@pytest.mark.parametrize("newest_first", [False, True])
def test_two_snapshots_show_no_data_captured_at_for_the_two(
    newest_first: bool,
) -> None:
    vehicle = _vehicle(_map(_two_snapshots(newest_first)))
    for key in ("battery_soc", "odometer_km"):
        attrs = _attrs(vehicle, key)
        assert "data_captured_at" not in attrs
        assert attrs["freshness_source"] == "dataset"


def test_the_age_release_of_a_held_soc_fires_without_a_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2134 reads the stamps of the leaf SoC and of the odometer; on an export
    that has no time entries both are the inherited ones, as before."""
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile
    from tests.test_2134_hv_hold_release import _prev

    items = [MARKER_16, LEAF_SOC, ODO_VALUE, ODO_STATE]
    fresh = _map(items).to_dict()
    assert fresh["field_captured_ts"]["odometer_km"].startswith("2026-11-16T10:00:00")
    merged, notes = reconcile(_prev(), dict(fresh))
    assert merged["battery_soc"] == 74
    assert merged["battery_soc_from_hv"] is False
    assert any("#2134" in n for n in notes)
    # the control (no pairing at all) gives the same verdict
    _control(monkeypatch)
    want, want_notes = reconcile(_prev(), _map(items).to_dict())
    assert (merged["battery_soc"], notes) == (want["battery_soc"], want_notes)


def test_the_age_release_fires_through_the_mapping_with_a_pair() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile
    from tests.test_2134_hv_hold_release import _HELD_TS, _prev

    odo_stamp = _p(ODO_TS_KEY, "timestamp", "2026-11-16T09:00:00Z")
    fresh = _map([MARKER_16, LEAF_SOC, ODO_VALUE, ODO_STATE, odo_stamp]).to_dict()
    merged, notes = reconcile(_prev(), fresh)
    assert merged["battery_soc"] == 74
    assert any("#2134" in n for n in notes)
    assert _HELD_TS < merged["field_captured_ts"]["battery_soc"]


def test_capture_age_and_last_seen_equal_the_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.vag_connect.coordinator import _capture_age_s

    for items in (_unpaired(), _two_snapshots(False), _two_snapshots(True)):
        got = _map(items)
        with monkeypatch.context() as m:
            _control(m)
            want = _map(items)
        assert got.last_seen_at == want.last_seen_at
        # both read the clock: equal up to the milliseconds between the two calls
        assert _capture_age_s(got.to_dict()) == pytest.approx(
            _capture_age_s(want.to_dict()), abs=5.0)


def test_the_conflict_choice_equals_the_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for items in (_two_snapshots(False), _two_snapshots(True)):
        got = _walk(items)
        with monkeypatch.context() as m:
            _control(m)
            assert _walk(items) == got


# ── R3: display only ─────────────────────────────────────────────────────────
def test_an_inherited_stamp_is_not_shown_but_kept() -> None:
    d = _map(_unpaired())
    assert d.field_captured_inherited == {"battery_soc": True, "odometer_km": True}
    vehicle = _vehicle(d)
    assert vehicle["field_captured_ts"]["battery_soc"]  # internal stamp kept
    for key in ("battery_soc", "odometer_km"):
        attrs = _attrs(vehicle, key)
        assert "data_captured_at" not in attrs
        assert attrs["freshness_source"] == "dataset"


def test_a_paired_stamp_is_shown() -> None:
    vehicle = _vehicle(_map(_full()))
    assert _attrs(vehicle, "battery_soc")["data_captured_at"].startswith(
        "2026-11-13T06:57:12")
    assert _attrs(vehicle, "odometer_km")["data_captured_at"].startswith(
        "2026-11-13T06:57:06")
    assert _attrs(vehicle, "battery_soc")["freshness_source"] == "point"


def test_other_fields_still_show_the_neighbour_stamp() -> None:
    vehicle = _vehicle(_map(_unpaired()))
    assert _attrs(vehicle, "charging_state")["data_captured_at"].startswith(
        "2026-11-0")


def test_a_leaf_soc_with_an_inherited_stamp_is_not_shown_either() -> None:
    vehicle = _vehicle(_map([MARKER_16, LEAF_SOC]))
    assert vehicle["field_captured_ts"]["battery_soc"].startswith("2026-11-16T10")
    assert "data_captured_at" not in _attrs(vehicle, "battery_soc")


# ── R4: the UUID alias branch ────────────────────────────────────────────────
@pytest.mark.parametrize("marker_first", [False, True])
def test_an_alias_point_without_its_time_entry_is_marked_inherited(
    marker_first: bool,
) -> None:
    point = _p(SOC_UUID, "value", "81")
    items = [MARKER_16, point] if marker_first else [point, MARKER_16]
    d = _map(items)
    assert d.battery_soc == 81
    assert d.field_source_leaf["battery_soc"] == SOC_UUID
    vehicle = _vehicle(d)
    assert "data_captured_at" not in _attrs(vehicle, "battery_soc")
    if marker_first:
        assert vehicle["field_captured_ts"]["battery_soc"].startswith("2026-11-16")
        assert d.field_captured_inherited["battery_soc"] is True
    else:
        assert "battery_soc" not in d.field_captured_ts


def test_an_alias_point_with_its_time_entry_is_shown() -> None:
    point = _p(SOC_UUID, "value", "81")
    d = _map([MARKER_16, point, SOC_STAMP])
    assert d.field_captured_ts["battery_soc"].startswith("2026-11-13T06:57:12")
    assert "battery_soc" not in d.field_captured_inherited
    assert "data_captured_at" in _attrs(_vehicle(d), "battery_soc")


def test_the_alias_flag_does_not_change_the_conflict_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [MARKERS[0], _p(SOC_UUID, "value", "57"), MARKERS[1],
             _p(SOC_UUID, "value", "81")]
    got = _walk(items)[:5]
    _control(monkeypatch)
    assert _walk(items)[:5] == got


# ── R5: the odometer from its other leaves ───────────────────────────────────
@pytest.mark.parametrize("leaf", ["odometer", "mileage", "totalMileage"])
def test_the_other_odometer_leaves_follow_the_same_rule(leaf: str) -> None:
    d = _map([MARKER_16, _p("44444444-0000-0000-0000-000000000001", leaf, "5555")])
    assert d.odometer_km == 5555
    assert d.field_captured_ts["odometer_km"].startswith("2026-11-16T10:00:00")
    assert d.field_captured_inherited["odometer_km"] is True
    assert "data_captured_at" not in _attrs(_vehicle(d), "odometer_km")


@pytest.mark.parametrize("leaf", ["odometer", "mileage", "totalMileage"])
def test_the_other_odometer_leaves_with_their_own_stamp_are_shown(leaf: str) -> None:
    point = {"dataFieldName": leaf, "value": "5555",
             "timestampUtc": "2026-10-03T16:59:46Z"}
    d = _map([MARKER_16, point])
    assert "odometer_km" not in d.field_captured_inherited
    assert _attrs(_vehicle(d), "odometer_km")["data_captured_at"].startswith(
        "2026-10-03T16:59:46")


# ── the map travels and is dropped with field_captured_ts ────────────────────
def test_the_map_is_listed_with_the_provenance_maps() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import _PROVENANCE_MAPS
    from custom_components.vag_connect.coordinator import (
        _PROVENANCE_MAPS as COORD_MAPS,
    )

    assert NEW_MAP in _PROVENANCE_MAPS
    assert NEW_MAP in COORD_MAPS


def test_a_live_channel_superseding_the_value_drops_the_flag() -> None:
    eu = _map(_unpaired())
    live = VehicleData(vin="X")
    live.battery_soc = 80
    merged = merge_channels([("eu_data_act", eu), ("mbb", live)])
    assert merged.field_sources["battery_soc"] == "mbb"
    assert "battery_soc" not in merged.field_captured_inherited
    assert merged.field_captured_inherited.get("odometer_km") is True


def test_strip_held_drops_the_flag_with_the_stamp() -> None:
    from custom_components.vag_connect.cariad import _channel_merge as cm
    from custom_components.vag_connect.cariad.vehicle_cache import strip_held

    owner = sorted(cm._HELD_PUSH_SOURCES)[0]
    snap = {
        "battery_soc": 55,
        "field_sources": {"battery_soc": owner},
        "field_captured_ts": {"battery_soc": "2026-11-08T10:00:00+00:00"},
        "field_captured_inherited": {"battery_soc": True, "odometer_km": True},
    }
    out = strip_held(snap)
    assert out["field_captured_inherited"] == {"odometer_km": True}
    assert snap["field_captured_inherited"] == {"battery_soc": True, "odometer_km": True}


def test_a_held_soc_keeps_its_own_flag_not_the_fresh_leafs() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile
    from tests.test_2134_hv_hold_release import _fresh, _prev

    held = _prev()  # held 55, stamp recorded as its own
    fresh = _fresh(67, avail=55.5, cap=100.0)
    fresh["field_captured_inherited"] = {"battery_soc": True}
    merged, _ = reconcile(held, fresh)
    assert merged["battery_soc"] == 55
    assert "battery_soc" not in merged["field_captured_inherited"]
    # and the reverse: the held value was recorded as inherited
    held2 = _prev()
    held2["field_captured_inherited"] = {"battery_soc": True}
    fresh2 = _fresh(67, avail=55.5, cap=100.0)
    merged2, _ = reconcile(held2, fresh2)
    assert merged2["field_captured_inherited"]["battery_soc"] is True


def test_a_carried_soc_keeps_its_flag() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile
    from tests.test_2134_hv_hold_release import _prev

    prev = _prev()
    prev["field_captured_inherited"] = {"battery_soc": True}
    merged, _ = reconcile(prev, {"battery_soc": None, "battery_soc_from_hv": None,
                                 "field_captured_ts": {}})
    assert merged["battery_soc"] == 55
    assert merged["field_captured_inherited"]["battery_soc"] is True


def test_the_import_gap_fill_carries_the_flag_per_key() -> None:
    from custom_components.vag_connect.coordinator import _gap_fill_from_export

    current = {"battery_soc": 80, "odometer_km": None,
               "field_sources": {"battery_soc": "mbb"},
               "field_captured_inherited": {}}
    hist = {"battery_soc": 55, "odometer_km": 999,
            "field_sources": {"odometer_km": "eu_data_act",
                              "battery_soc": "eu_data_act"},
            "field_captured_ts": {"odometer_km": "2026-11-08T10:00:00+00:00",
                                  "battery_soc": "2026-11-08T10:00:00+00:00"},
            "field_captured_inherited": {"odometer_km": True, "battery_soc": True}}
    filled = _gap_fill_from_export(current, hist)
    assert filled == ["odometer_km"]
    assert current["field_captured_inherited"] == {"odometer_km": True}


def test_the_imported_value_carried_across_polls_keeps_its_flag() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile

    prev = {"odometer_km": 999, "field_imported_from_export": ["odometer_km"],
            "field_sources": {"odometer_km": "eu_data_act"},
            "field_captured_ts": {"odometer_km": "2026-11-08T10:00:00+00:00"},
            "field_captured_inherited": {"odometer_km": True}}
    merged, _ = reconcile(prev, {"odometer_km": None})
    assert merged["odometer_km"] == 999
    assert merged["field_captured_inherited"] == {"odometer_km": True}
