# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Merge rules for a held push source (``drivepulse``).

A held source delivers a value when an event arrives and the integration keeps
it until the next one, so it is neither a batch export nor a live read. It also
reaches the car only through a link the user set by hand. The merge therefore
treats it as a third class: it never counts as live, fills only a short list of
fields, never dates the car or proves a drivetrain, and displaces a batch value
only when its own capture stamp is measurably newer.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.vag_connect.cariad._channel_merge import (
    _HELD_FRESHNESS_MARGIN_S,
    gather_and_merge,
    merge_channels,
)
from custom_components.vag_connect.cariad.models import VehicleData

_VIN = "WVWTEST0000FAKE01"
_T0 = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _v(**kw) -> VehicleData:
    return VehicleData(vin=_VIN, **kw)


def _batch(fuel: int = 40, ts: object = None, **kw) -> VehicleData:
    vd = _v(fuel_level=fuel, **kw)
    if ts is not None:
        vd.field_captured_ts = {"fuel_level": ts}
    return vd


def _held(fuel: int | None = 70, ts: object = None, **kw) -> VehicleData:
    vd = _v(fuel_level=fuel, **kw)
    if ts is not None:
        vd.field_captured_ts = {"fuel_level": ts}
    return vd


class TestNotLive:
    def test_a_batch_keeps_fuel_without_stamps(self):
        m = merge_channels([("eu_data_act", _batch()), ("drivepulse", _held())])
        assert m.fuel_level == 40
        assert m.field_sources["fuel_level"] == "eu_data_act"

    def test_e_real_live_channel_beats_both(self):
        live = _v(fuel_level=55)
        m = merge_channels([
            ("eu_data_act", _batch()),
            ("drivepulse", _held()),
            ("website_authproxy", live),
        ])
        assert m.fuel_level == 55
        assert m.field_sources["fuel_level"] == "website_authproxy"

    def test_e_a_live_owner_is_not_displaced_even_with_stamps_on_both_sides(self):
        # The age gate is for a BATCH owner only. A live channel that happens
        # to carry a capture stamp must not be pulled into it, however much
        # newer the held reading claims to be.
        live = _v(fuel_level=55)
        live.field_captured_ts = {"fuel_level": _iso(_T0)}
        held = _held(ts=_iso(_T0 + timedelta(hours=3)))
        for sources in (
            [("website_authproxy", live), ("drivepulse", held)],
            [("eu_data_act", _batch(ts=_iso(_T0))), ("website_authproxy", live),
             ("drivepulse", held)],
        ):
            m = merge_channels(sources)
            assert m.fuel_level == 55
            assert m.field_sources["fuel_level"] == "website_authproxy"
            assert "drivepulse" not in (m.source_channel or "")


class TestAgeGate:
    def test_b_held_twenty_minutes_newer_wins(self):
        held_ts = _iso(_T0 + timedelta(minutes=20))
        m = merge_channels([
            ("eu_data_act", _batch(ts=_iso(_T0))),
            ("drivepulse", _held(ts=held_ts)),
        ])
        assert m.fuel_level == 70
        assert m.field_sources["fuel_level"] == "drivepulse"
        assert m.field_captured_ts["fuel_level"] == held_ts
        assert "drivepulse" in (m.source_channel or "")

    def test_b_offset_and_datetime_stamps_are_accepted(self):
        # batch stamp with an explicit offset, held stamp as a datetime object
        batch_ts = (_T0.astimezone(timezone(timedelta(hours=1)))).isoformat()
        held = _held()
        held.field_captured_ts = {"fuel_level": _T0 + timedelta(minutes=20)}  # type: ignore[dict-item]
        m = merge_channels([
            ("eu_data_act", _batch(ts=batch_ts)), ("drivepulse", held),
        ])
        assert m.fuel_level == 70
        assert m.field_sources["fuel_level"] == "drivepulse"

    def test_b_naive_stamp_counts_as_utc(self):
        naive_batch = _T0.replace(tzinfo=None).isoformat()
        m = merge_channels([
            ("eu_data_act", _batch(ts=naive_batch)),
            ("drivepulse", _held(ts=_iso(_T0 + timedelta(minutes=20)))),
        ])
        assert m.fuel_level == 70

    def test_c_ten_minutes_is_inside_the_margin(self):
        assert _HELD_FRESHNESS_MARGIN_S > 600
        m = merge_channels([
            ("eu_data_act", _batch(ts=_iso(_T0))),
            ("drivepulse", _held(ts=_iso(_T0 + timedelta(minutes=10)))),
        ])
        assert m.fuel_level == 40
        assert m.field_sources["fuel_level"] == "eu_data_act"

    def test_c_batch_without_stamp_stays(self):
        m = merge_channels([
            ("eu_data_act", _batch()),
            ("drivepulse", _held(ts=_iso(_T0 + timedelta(minutes=20)))),
        ])
        assert m.fuel_level == 40
        assert m.field_sources["fuel_level"] == "eu_data_act"

    def test_c_held_without_stamp_stays(self):
        m = merge_channels([
            ("eu_data_act", _batch(ts=_iso(_T0))),
            ("drivepulse", _held()),
        ])
        assert m.fuel_level == 40
        assert m.field_sources["fuel_level"] == "eu_data_act"

    def test_c_unparseable_stamp_stays(self):
        m = merge_channels([
            ("eu_data_act", _batch(ts=_iso(_T0))),
            ("drivepulse", _held(ts="yesterday-ish")),
        ])
        assert m.fuel_level == 40
        m2 = merge_channels([
            ("eu_data_act", _batch(ts="not a time")),
            ("drivepulse", _held(ts=_iso(_T0 + timedelta(minutes=20)))),
        ])
        assert m2.fuel_level == 40

    def test_d_battery_soc_is_not_superseded(self):
        batch = _v(battery_soc=60)
        batch.field_captured_ts = {"battery_soc": _iso(_T0)}
        held = _v(battery_soc=80)
        held.field_captured_ts = {"battery_soc": _iso(_T0 + timedelta(minutes=20))}
        m = merge_channels([("eu_data_act", batch), ("drivepulse", held)])
        assert m.battery_soc == 60
        assert m.field_sources["battery_soc"] == "eu_data_act"


class TestFillableOnly:
    def test_f_fills_the_four_gaps(self):
        base = _v(odometer_km=1000)
        held = _v(voltage_12v=12.4, range_km=420, fuel_level=55, battery_soc=70)
        m = merge_channels([("eu_data_act", base), ("drivepulse", held)])
        assert m.voltage_12v == 12.4
        assert m.range_km == 420
        assert m.fuel_level == 55
        assert m.battery_soc == 70
        for f in ("voltage_12v", "range_km", "fuel_level", "battery_soc"):
            assert m.field_sources[f] == "drivepulse"

    def test_f_other_fields_stay_empty(self):
        base = _v(service_km=15000)
        held = _v(
            voltage_12v=12.4, odometer_km=999,
            last_seen_at=_iso(_T0), engine_coolant_temperature_c=88.0,
        )
        m = merge_channels([("eu_data_act", base), ("drivepulse", held)])
        assert m.voltage_12v == 12.4
        assert m.odometer_km is None
        assert m.last_seen_at is None
        assert m.engine_coolant_temperature_c is None
        for f in ("odometer_km", "last_seen_at", "engine_coolant_temperature_c"):
            assert f not in m.field_sources


class TestDrivetrain:
    def test_g_ev_stays_ev_when_held_fills_fuel(self):
        base = _v(has_battery=True, battery_soc=80)
        held = _v(fuel_level=30)
        m = merge_channels([("website_authproxy", base), ("drivepulse", held)])
        assert m.fuel_level == 30  # filled, but proves nothing
        assert m.has_combustion is False
        assert m.is_hybrid is False
        assert m.is_electric is True

    def test_g_ice_stays_ice_when_held_fills_soc(self):
        base = _v(has_combustion=True, fuel_level=50)
        held = _v(battery_soc=70)
        m = merge_channels([("website_authproxy", base), ("drivepulse", held)])
        assert m.battery_soc == 70
        assert m.has_battery is False
        assert m.is_hybrid is False

    def test_g_held_asserted_flag_lifts_nothing(self):
        base = _v(has_combustion=True, fuel_level=50)
        held = _v(has_battery=True, voltage_12v=12.1)
        m = merge_channels([("website_authproxy", base), ("drivepulse", held)])
        assert m.has_battery is False
        assert m.is_hybrid is False


class TestNoDating:
    def test_h_newest_last_seen_from_held_does_not_win(self):
        base = _v(last_seen_at=_iso(_T0), odometer_km=1000)
        held = _v(last_seen_at=_iso(_T0 + timedelta(hours=3)), voltage_12v=12.2)
        m = merge_channels([("eu_data_act", base), ("drivepulse", held)])
        assert m.last_seen_at == _iso(_T0)
        assert m.field_sources["last_seen_at"] == "eu_data_act"

    def test_h_held_position_does_not_win(self):
        base = _v(latitude=47.0, longitude=8.0, position_captured_at=_iso(_T0))
        held = _v(latitude=48.0, longitude=9.0,
                  position_captured_at=_iso(_T0 + timedelta(hours=3)))
        m = merge_channels([("eu_data_act", base), ("drivepulse", held)])
        assert m.latitude == 47.0
        assert m.field_sources["latitude"] == "eu_data_act"


class TestSourceChannel:
    def test_i_listed_when_it_owns_a_field(self):
        m = merge_channels([
            ("eu_data_act", _v(odometer_km=1000)),
            ("drivepulse", _v(voltage_12v=12.3)),
        ])
        assert "drivepulse" in (m.source_channel or "").split("+")

    def test_i_absent_when_it_owns_nothing(self):
        m = merge_channels([
            ("eu_data_act", _batch()),
            ("drivepulse", _held(odometer_km=999,
                                 last_seen_at=_iso(_T0 + timedelta(hours=1)))),
        ])
        assert "drivepulse" not in m.field_sources.values()
        assert m.source_channel == "eu_data_act"


class TestPreferredIgnored:
    def test_j_preferred_drivepulse_is_ignored(self):
        async def _ret(vd: VehicleData) -> VehicleData:
            return vd

        def _run(preferred: str | None) -> VehicleData:
            primary = _batch(odometer_km=1000)
            held = _held(fuel=70, odometer_km=999, voltage_12v=12.2)
            return asyncio.run(gather_and_merge(
                "eu_data_act", primary, [("drivepulse", _ret(held))],
                preferred=preferred,
            ))

        plain = _run(None)
        pref = _run("drivepulse")
        assert pref.fuel_level == plain.fuel_level == 40
        assert pref.odometer_km == plain.odometer_km == 1000
        assert pref.field_sources == plain.field_sources
        assert pref.source_channel == plain.source_channel
