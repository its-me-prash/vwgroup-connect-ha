# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DrivePulse hold: bus events are kept in the integration's own store."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.vag_connect import held_push
from custom_components.vag_connect.cariad._drivepulse_source import (
    EVENT_TRIP_END,
    EVENT_TRIP_START,
)
from custom_components.vag_connect.held_push import (
    DrivePulseHold,
    async_remove_held_store,
    held_store_key,
)

VIN = "TESTVIN0000000001"
OTHER_VIN = "FAKEVIN0000000002"
DEV = "dev-1"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
HOLD_S = 3600.0

_DISK: dict[str, Any] = {}


class _FakeStore:
    """In-memory stand-in for HA's Store; the 'disk' is shared by key."""

    def __init__(self, hass, version, key):
        self.key = key
        self.version = version
        self._pending = None

    async def async_load(self):
        if self.key == "boom":
            raise OSError("disk")
        return _DISK.get(self.key)

    async def async_save(self, data):
        _DISK[self.key] = json.loads(json.dumps(data))

    def async_delay_save(self, data_func, delay=0):
        self._pending = data_func

    async def async_remove(self):
        _DISK.pop(self.key, None)


_STORES: list[_FakeStore] = []


class _FakeBus:
    def __init__(self):
        self.listeners: dict[str, list] = {}

    def async_listen(self, event_type, handler):
        self.listeners.setdefault(event_type, []).append(handler)

        def _unsub():
            self.listeners[event_type].remove(handler)

        return _unsub

    def fire(self, event_type, data, when=T0):
        for h in list(self.listeners.get(event_type, [])):
            h(SimpleNamespace(data=data, time_fired=when))

    def count(self):
        return sum(len(v) for v in self.listeners.values())


@pytest.fixture(autouse=True)
def _patch_store(monkeypatch):
    _DISK.clear()
    _STORES.clear()

    def _make(hass, version, key):
        s = _FakeStore(hass, version, key)
        _STORES.append(s)
        return s

    monkeypatch.setattr(held_push, "Store", _make)
    yield
    _DISK.clear()


def _hass():
    return SimpleNamespace(bus=_FakeBus())


def _clock(box):
    return lambda: box[0]


def _hold(hass, links=None, now_box=None, entry="e1", hold_s=HOLD_S):
    box = now_box or [T0]
    links = {VIN: DEV} if links is None else links
    return DrivePulseHold(hass, entry, links, hold_s=hold_s, now=_clock(box)), box


async def _flush(hold):
    """Run the pending delayed save of the hold's store."""
    store = hold._store
    assert store._pending is not None, "no save was scheduled"
    await store.async_save(store._pending())
    store._pending = None


def _payload(**kw):
    base = {"device_id": DEV, "fuel_level_pct": 55.0}
    base.update(kw)
    return base


def _tag(vin=VIN, entry="e1"):
    """The car tag as the module docstring defines it, computed independently."""
    return hashlib.sha256(f"{entry}:{vin}".encode()).hexdigest()[:16]


def _stored(values, stamp, vin=VIN, entry="e1"):
    """One device's readings as they lie in the store file."""
    return {
        "car": _tag(vin, entry),
        "values": dict(values),
        "stamps": {name: stamp for name in values},
    }


def test_store_key():
    assert held_store_key("abc").endswith(".held_push.abc")


async def test_event_held_and_served():
    hass = _hass()
    hold, _ = _hold(hass)
    await hold.async_load()
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload())
    assert hold.has_fresh(VIN)
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd is not None and vd.fuel_level == 55


async def test_start_event_also_held():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_START, _payload(range_km=300))
    assert hold.has_fresh(VIN)


async def test_vin_compared_case_insensitive():
    hass = _hass()
    hold, _ = _hold(hass, links={VIN.lower(): DEV})
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload())
    assert hold.has_fresh(VIN)
    assert hold.has_fresh(VIN.lower())


@pytest.mark.parametrize(
    "data",
    [
        {"device_id": "other", "fuel_level_pct": 55},
        None,
        "text",
        {"device_id": DEV, "fuel_level_pct": "55"},
        {"device_id": DEV},
        {},
    ],
)
async def test_unusable_events_ignored(data):
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, data)
    assert not hold.has_fresh(VIN)
    assert hold.vehicle_data(VIN, has_battery=True, has_combustion=True) is None


async def test_older_event_does_not_replace_newer():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=40), when=T0)
    hass.bus.fire(
        EVENT_TRIP_END, _payload(fuel_level_pct=90), when=T0 - timedelta(minutes=5)
    )
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd.fuel_level == 40


async def test_newer_event_replaces():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=40), when=T0)
    hass.bus.fire(
        EVENT_TRIP_END, _payload(fuel_level_pct=30), when=T0 + timedelta(minutes=5)
    )
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd.fuel_level == 30


async def test_expiry_via_injected_clock():
    hass = _hass()
    hold, box = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload())
    box[0] = T0 + timedelta(seconds=HOLD_S - 1)
    assert hold.has_fresh(VIN)
    box[0] = T0 + timedelta(seconds=HOLD_S + 1)
    assert not hold.has_fresh(VIN)
    assert hold.vehicle_data(VIN, has_battery=True, has_combustion=True) is None


async def test_unlinked_vin_not_served():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload())
    assert not hold.has_fresh(OTHER_VIN)
    assert hold.vehicle_data(OTHER_VIN, has_battery=True, has_combustion=True) is None


async def test_save_reload_keeps_value_and_stamp():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    when = T0 - timedelta(minutes=10)
    hass.bus.fire(EVENT_TRIP_END, _payload(), when=when)
    await _flush(hold)

    hold2, _ = _hold(_hass())
    await hold2.async_load()
    assert hold2.has_fresh(VIN)
    vd = hold2.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd.fuel_level == 55
    assert vd.field_captured_ts["fuel_level"] == when.isoformat()


async def test_load_drops_expired_and_unlinked():
    old = (T0 - timedelta(seconds=HOLD_S + 60)).isoformat()
    new = (T0 - timedelta(seconds=60)).isoformat()
    _DISK[held_store_key("e1")] = {
        "drivepulse": {
            DEV: _stored({"fuel_level": 50}, old),
            "gone": _stored({"fuel_level": 50}, new),
        }
    }
    hold, _ = _hold(_hass())
    await hold.async_load()
    assert not hold.has_fresh(VIN)
    assert hold._held == {}
    # what was left out does not stay in the file either
    await _flush(hold)
    assert _DISK[held_store_key("e1")] == {"drivepulse": {}}

    _DISK[held_store_key("e1")] = {
        "drivepulse": {DEV: _stored({"fuel_level": 50}, new)}
    }
    hold, _ = _hold(_hass())
    await hold.async_load()
    assert hold.has_fresh(VIN)
    assert hold._store._pending is None, "nothing dropped, so nothing to rewrite"


async def test_a_reading_without_per_field_stamps_is_not_loaded():
    new = (T0 - timedelta(seconds=60)).isoformat()
    _DISK[held_store_key("e1")] = {
        "drivepulse": {
            DEV: {"car": _tag(), "ts": new, "values": {"fuel_level": 50}}
        }
    }
    hold, _ = _hold(_hass())
    await hold.async_load()
    assert not hold.has_fresh(VIN)


async def test_a_dongle_moved_to_another_car_does_not_bring_the_old_reading():
    """The reading belongs to the car it was taken in, not to the device."""
    hass = _hass()
    hold, _ = _hold(hass, links={VIN: DEV})
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=55))
    await _flush(hold)
    assert _DISK[held_store_key("e1")]["drivepulse"][DEV]["car"] == _tag(VIN)

    moved, _ = _hold(_hass(), links={OTHER_VIN: DEV})
    await moved.async_load()
    assert not moved.has_fresh(OTHER_VIN)
    assert moved.vehicle_data(
        OTHER_VIN, has_battery=True, has_combustion=True
    ) is None
    assert moved._held == {}

    # control: the same file, the same car, and the reading is back
    same, _ = _hold(_hass(), links={VIN: DEV})
    await same.async_load()
    assert same.has_fresh(VIN)


async def test_the_first_event_in_the_new_car_is_served_to_the_new_car():
    hass = _hass()
    _DISK[held_store_key("e1")] = {
        "drivepulse": {DEV: _stored({"fuel_level": 55}, T0.isoformat(), vin=VIN)}
    }
    moved, _ = _hold(hass, links={OTHER_VIN: DEV})
    await moved.async_load()
    moved.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=20))
    vd = moved.vehicle_data(OTHER_VIN, has_battery=False, has_combustion=True)
    assert vd is not None and vd.fuel_level == 20


async def test_stop_writes_a_change_that_is_still_waiting():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=55))
    assert held_store_key("e1") not in _DISK, "control: the save is delayed"
    await hold.async_stop()
    assert hass.bus.count() == 0
    stored = _DISK[held_store_key("e1")]["drivepulse"][DEV]
    assert stored["values"] == {"fuel_level": 55}


async def test_stop_with_nothing_waiting_writes_nothing():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    await hold.async_stop()
    assert held_store_key("e1") not in _DISK
    assert hass.bus.count() == 0


async def test_discard_forgets_everything_and_deletes_the_file():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload())
    await _flush(hold)
    assert held_store_key("e1") in _DISK, "control"
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=30), when=T0 + timedelta(minutes=1))
    await hold.async_discard()
    assert held_store_key("e1") not in _DISK
    assert not hold.has_fresh(VIN)
    assert hass.bus.count() == 0
    # a later stop must not bring the file back
    await hold.async_stop()
    assert held_store_key("e1") not in _DISK


async def test_a_stored_stamp_far_in_the_future_is_not_loaded():
    ahead = (T0 + timedelta(days=1)).isoformat()
    _DISK[held_store_key("e1")] = {
        "drivepulse": {DEV: _stored({"fuel_level": 50}, ahead)}
    }
    hold, _ = _hold(_hass())
    await hold.async_load()
    assert not hold.has_fresh(VIN)
    assert hold.vehicle_data(VIN, has_battery=True, has_combustion=True) is None


async def test_a_stored_stamp_slightly_ahead_is_still_used_and_capped():
    slightly = (T0 + timedelta(minutes=2)).isoformat()
    _DISK[held_store_key("e1")] = {
        "drivepulse": {DEV: _stored({"fuel_level": 50}, slightly)}
    }
    hold, _ = _hold(_hass())
    await hold.async_load()
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd is not None and vd.fuel_level == 50
    assert vd.field_captured_ts["fuel_level"] == T0.isoformat(), (
        "a stamp ahead of the clock must not be written out as newer than now"
    )


async def test_an_event_stamped_ahead_of_the_clock_does_not_shut_out_later_ones():
    """A clock that ran fast for one event must not cost every later reading."""
    hass = _hass()
    hold, box = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=90), when=T0 + timedelta(hours=2))
    assert not hold.has_fresh(VIN)
    box[0] = T0 + timedelta(minutes=5)
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=40), when=T0 + timedelta(minutes=5))
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd is not None and vd.fuel_level == 40


async def test_an_event_with_one_field_keeps_the_other_held_fields():
    """One event rarely carries every field; the rest must not vanish."""
    hass = _hass()
    hold, box = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=55, range_km=400), when=T0)
    later = T0 + timedelta(minutes=30)
    box[0] = later
    hass.bus.fire(
        EVENT_TRIP_START, {"device_id": DEV, "battery_voltage": 12.4}, when=later
    )
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd.fuel_level == 55 and vd.range_km == 400 and vd.voltage_12v == 12.4
    # every field keeps the time ITS value was read
    assert vd.field_captured_ts["fuel_level"] == T0.isoformat()
    assert vd.field_captured_ts["voltage_12v"] == later.isoformat()


async def test_each_field_expires_on_its_own():
    hass = _hass()
    hold, box = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=55), when=T0)
    mid = T0 + timedelta(minutes=50)
    box[0] = mid
    hass.bus.fire(
        EVENT_TRIP_START, {"device_id": DEV, "battery_voltage": 12.4}, when=mid
    )
    box[0] = T0 + timedelta(seconds=HOLD_S + 60)
    assert hold.has_fresh(VIN)
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd.fuel_level is None, "the fuel reading is past its hold time"
    assert vd.voltage_12v == 12.4


async def test_an_older_event_adds_a_field_but_does_not_replace_a_newer_one():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(EVENT_TRIP_END, _payload(fuel_level_pct=40), when=T0)
    earlier = T0 - timedelta(minutes=5)
    hass.bus.fire(
        EVENT_TRIP_END, _payload(fuel_level_pct=90, range_km=300), when=earlier
    )
    vd = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert vd.fuel_level == 40
    assert vd.range_km == 300
    assert vd.field_captured_ts["range_km"] == earlier.isoformat()


@pytest.mark.parametrize("content", [None, "junk", {"drivepulse": []}, {"x": 1}, {"drivepulse": {DEV: 5}}])
async def test_load_survives_broken_structure(content):
    if content is not None:
        _DISK[held_store_key("e1")] = content
    hold, _ = _hold(_hass())
    await hold.async_load()
    assert not hold.has_fresh(VIN)


async def test_load_survives_exception():
    hold = DrivePulseHold(_hass(), "boom", {VIN: DEV}, now=lambda: T0)
    # key becomes held_store_key("boom"); force the fake to raise via key swap
    hold._store.key = "boom"
    await hold.async_load()
    assert not hold.has_fresh(VIN)


async def test_unsubscribe_stops_listening():
    hass = _hass()
    hold, _ = _hold(hass)
    unsub = hold.async_start()
    assert hass.bus.count() == 2
    unsub()
    assert hass.bus.count() == 0
    hass.bus.fire(EVENT_TRIP_END, _payload())
    assert not hold.has_fresh(VIN)


@pytest.mark.parametrize("links", [None, {}, {"": DEV}, {VIN: ""}, {VIN: 5}, {5: DEV}])
async def test_no_links_no_listener(links):
    hass = _hass()
    hold = DrivePulseHold(hass, "e1", links, now=lambda: T0)
    unsub = hold.async_start()
    assert hass.bus.count() == 0
    unsub()
    assert not hold.has_fresh(VIN)


async def test_stored_content_has_no_vin_or_name():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(
        EVENT_TRIP_END, _payload(vehicle_name="Mein Golf", vin=VIN)
    )
    await _flush(hold)
    blob = json.dumps(_DISK[held_store_key("e1")])
    assert VIN not in blob and "Golf" not in blob
    assert DEV in blob


async def test_remove_store_and_missing_store():
    _DISK[held_store_key("e1")] = {"drivepulse": {}}
    await async_remove_held_store(_hass(), "e1")
    assert held_store_key("e1") not in _DISK
    await async_remove_held_store(_hass(), "e1")  # nothing there: no raise


async def test_remove_store_never_raises(monkeypatch):
    def _bad(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(held_push, "Store", _bad)
    await async_remove_held_store(_hass(), "e1")


async def test_drivetrain_fit_passed_through():
    hass = _hass()
    hold, _ = _hold(hass)
    hold.async_start()
    hass.bus.fire(
        EVENT_TRIP_END, _payload(fuel_level_pct=55, hv_soc_pct=70, range_km=400)
    )
    ev = hold.vehicle_data(VIN, has_battery=True, has_combustion=False)
    assert ev.fuel_level is None and ev.battery_soc == 70
    ice = hold.vehicle_data(VIN, has_battery=False, has_combustion=True)
    assert ice.fuel_level == 55 and ice.battery_soc is None
