# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DrivePulse bus-event mapper (pure functions, no Home Assistant)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.vag_connect.cariad._drivepulse_source import (
    CHANNEL,
    EVENT_TRIP_END,
    EVENT_TRIP_START,
    build_vehicle_data,
    parse_event,
)

VIN = "TESTFAKE000000001"
NOW = datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc)
RECV = datetime(2026, 10, 10, 8, 5, 0, tzinfo=timezone.utc)


def _event(**over):
    data = {
        "device_id": "dongle-1",
        "vehicle": "My Golf",
        "sent_at": "2026-10-10T08:00:00.000Z",
        "fuel_level_pct": 55.4,
        "hv_soc_pct": 80.6,
        "range_km": 412.2,
        "odometer_km": 12345.0,
        "battery_voltage": 12.456,
        "dtc_count": 2,
        "coolant_temp_c": 90,
    }
    data.update(over)
    return data


def test_constants():
    assert CHANNEL == "drivepulse"
    assert EVENT_TRIP_START == "drivepulse_trip_start"
    assert EVENT_TRIP_END == "drivepulse_trip_end"


def test_realistic_event_gives_exactly_four_values():
    out = parse_event(_event(), RECV)
    assert out is not None
    assert out["device_id"] == "dongle-1"
    assert out["values"] == {
        "fuel_level": 55,
        "battery_soc": 81,
        "range_km": 412,
        "voltage_12v": 12.46,
    }
    assert out["ts"] == "2026-10-10T08:00:00+00:00"


@pytest.mark.parametrize("v", [0, 100])
def test_percent_bounds_inclusive(v):
    out = parse_event(_event(fuel_level_pct=v, hv_soc_pct=v), RECV)
    assert out["values"]["fuel_level"] == v
    assert out["values"]["battery_soc"] == v


@pytest.mark.parametrize(
    "key,bad",
    [
        ("fuel_level_pct", -1),
        ("fuel_level_pct", 100.5),
        ("hv_soc_pct", 101),
        ("range_km", 2001),
        ("range_km", -5),
        ("battery_voltage", 5.9),
        ("battery_voltage", 18.1),
        ("fuel_level_pct", True),
        ("fuel_level_pct", "50"),
        ("fuel_level_pct", float("nan")),
        ("fuel_level_pct", float("inf")),
        ("range_km", float("-inf")),
        ("battery_voltage", False),
        ("hv_soc_pct", None),
    ],
)
def test_bad_values_dropped(key, bad):
    out = parse_event(_event(**{key: bad}), RECV)
    assert out is not None
    name = {
        "fuel_level_pct": "fuel_level",
        "hv_soc_pct": "battery_soc",
        "range_km": "range_km",
        "battery_voltage": "voltage_12v",
    }[key]
    assert name not in out["values"]
    assert len(out["values"]) == 3


def test_no_value_left_gives_none():
    ev = _event(
        fuel_level_pct=None, hv_soc_pct="x", range_km=9999, battery_voltage=None
    )
    assert parse_event(ev, RECV) is None


@pytest.mark.parametrize("data", [None, [], "x", 5])
def test_non_dict_gives_none(data):
    assert parse_event(data, RECV) is None


def test_device_id_missing_empty_none_long():
    ev = _event()
    del ev["device_id"]
    assert parse_event(ev, RECV) is None
    assert parse_event(_event(device_id="   "), RECV) is None
    assert parse_event(_event(device_id=None), RECV) is None
    assert parse_event(_event(device_id=123), RECV) is None
    assert parse_event(_event(device_id="a" * 65), RECV) is None
    assert parse_event(_event(device_id="a" * 64), RECV) is not None


def test_device_id_stripped():
    assert parse_event(_event(device_id="  d1 "), RECV)["device_id"] == "d1"


def test_future_sent_at_capped_to_receipt():
    out = parse_event(_event(sent_at="2030-01-01T00:00:00Z"), RECV)
    assert out["ts"] == RECV.isoformat()


def test_offset_and_naive_sent_at():
    out = parse_event(_event(sent_at="2026-10-10T09:00:00+02:00"), RECV)
    assert out["ts"] == "2026-10-10T07:00:00+00:00"
    out = parse_event(_event(sent_at="2026-10-10T08:00:00"), RECV)
    assert out["ts"] == "2026-10-10T08:00:00+00:00"


@pytest.mark.parametrize("bad", ["nonsense", 1760000000, None, ""])
def test_unparseable_sent_at_uses_receipt(bad):
    assert parse_event(_event(sent_at=bad), RECV)["ts"] == RECV.isoformat()


def test_vehicle_name_never_appears():
    out = parse_event(_event(vehicle="Secret Name 123"), RECV)
    assert "Secret Name 123" not in json.dumps(out)
    assert "vehicle" not in out and "vehicle" not in out["values"]


def test_result_json_serialisable():
    out = parse_event(_event(), RECV)
    assert json.loads(json.dumps(out)) == out


def test_ignored_fields_not_carried():
    out = parse_event(_event(), RECV)
    assert set(out["values"]) == {"fuel_level", "battery_soc", "range_km", "voltage_12v"}


# ---- build_vehicle_data -------------------------------------------------

def _snap(ts="2026-10-10T08:30:00+00:00", **values):
    vals = {
        "fuel_level": 50,
        "battery_soc": 70,
        "range_km": 300,
        "voltage_12v": 12.5,
    }
    vals.update(values)
    return {"device_id": "d", "ts": ts, "values": vals}


def _build(snap, *, bat=True, comb=True, now=NOW, max_age=7200.0):
    return build_vehicle_data(
        VIN, snap, has_battery=bat, has_combustion=comb, now=now, max_age_s=max_age
    )


@pytest.mark.parametrize(
    "bat,comb,fuel,soc",
    [
        (True, True, 50, 70),
        (True, False, None, 70),
        (False, True, 50, None),
        (False, False, None, None),
    ],
)
def test_drivetrain_fit(bat, comb, fuel, soc):
    vd = _build(_snap(), bat=bat, comb=comb)
    assert vd is not None
    assert vd.fuel_level == fuel
    assert vd.battery_soc == soc
    assert vd.range_km == 300
    assert vd.voltage_12v == 12.5
    assert vd.vin == VIN


def test_expiry():
    assert _build(_snap(), max_age=1799.0) is None
    assert _build(_snap(), max_age=1800.0) is not None


@pytest.mark.parametrize(
    "snap",
    [
        None,
        "x",
        [],
        {"values": {"range_km": 5}},
        {"ts": "2026-10-10T08:30:00+00:00"},
        {"ts": "2026-10-10T08:30:00+00:00", "values": []},
        {"ts": "garbage", "values": {"range_km": 5}},
        {"ts": 5, "values": {"range_km": 5}},
    ],
)
def test_broken_snapshot_gives_none(snap):
    assert _build(snap) is None


def test_nothing_set_gives_none():
    snap = {"ts": "2026-10-10T08:30:00+00:00", "values": {"fuel_level": 50}}
    assert _build(snap, comb=False) is None


def test_values_revalidated():
    vd = _build(_snap(range_km=99999, voltage_12v="12", fuel_level=True))
    assert vd.range_km is None
    assert vd.voltage_12v is None
    assert vd.fuel_level is None
    assert vd.battery_soc == 70


def test_set_fields_stamped():
    vd = _build(_snap(), bat=True, comb=False)
    ts = "2026-10-10T08:30:00+00:00"
    assert vd.field_captured_ts == {
        "battery_soc": ts,
        "range_km": ts,
        "voltage_12v": ts,
    }


def test_forbidden_fields_untouched():
    vd = _build(_snap())
    assert vd.has_battery is False
    assert vd.has_combustion is False
    assert vd.is_electric is False
    assert vd.is_hybrid is False
    assert vd.last_seen_at is None
    assert vd.odometer_km is None
    assert vd.latitude is None
    assert vd.longitude is None


def test_future_snapshot_ts_not_expired():
    # a stored ts slightly after now is clock skew, not an expiry
    assert _build(_snap(ts=(NOW + timedelta(seconds=5)).isoformat())) is not None


@pytest.mark.parametrize(
    "ahead_s,usable",
    [(299, True), (301, False), (86400, False)],
)
def test_a_stamp_far_ahead_of_the_clock_is_rejected(ahead_s, usable):
    # a stamp from the future would never expire and would win every age check
    snap = _snap(ts=(NOW + timedelta(seconds=ahead_s)).isoformat())
    assert (_build(snap) is not None) is usable


def test_a_stamp_ahead_of_the_clock_is_written_out_capped_at_now():
    vd = _build(_snap(ts=(NOW + timedelta(seconds=120)).isoformat()))
    assert set(vd.field_captured_ts.values()) == {NOW.isoformat()}


def test_each_field_is_dated_by_its_own_stamp():
    old = (NOW - timedelta(seconds=7300)).isoformat()   # past max_age 7200
    fresh = (NOW - timedelta(seconds=60)).isoformat()
    snap = {
        "values": {"fuel_level": 50, "range_km": 300, "voltage_12v": 12.5},
        "stamps": {"fuel_level": old, "range_km": fresh, "voltage_12v": "garbage"},
        "ts": fresh,
    }
    vd = _build(snap)
    assert vd.fuel_level is None, "its own stamp is past the hold time"
    assert vd.range_km == 300
    # an unreadable own stamp drops the field; the snapshot ts must not rescue it
    assert vd.voltage_12v is None
    assert vd.field_captured_ts == {"range_km": fresh}


def test_a_field_without_its_own_stamp_falls_back_to_the_snapshot_ts():
    fresh = (NOW - timedelta(seconds=60)).isoformat()
    snap = {"values": {"range_km": 300}, "stamps": {}, "ts": fresh}
    vd = _build(snap)
    assert vd.range_km == 300 and vd.field_captured_ts == {"range_km": fresh}


def test_all_fields_expired_gives_none():
    old = (NOW - timedelta(seconds=7300)).isoformat()
    snap = {"values": {"range_km": 300}, "stamps": {"range_km": old}}
    assert _build(snap) is None
