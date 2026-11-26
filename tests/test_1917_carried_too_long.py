# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1917 — a value kept from earlier polls for too long says so.

Since the carried marker, a kept value shows ``freshness_source: carried``
and ``carried_since``. The open half of #1917 was the age: the "Data stale"
sensor judges the newest capture of the whole vehicle, so a car whose
volkswagen.de feed keeps delivering the battery level stays "not stale" while
its target charge level has not arrived for weeks. Nothing said so except the
date in an attribute.

Decided (marking rather than dropping, as asked on the issue; integrations
that read the same portal keep every value without any marking):

- the value is never dropped or set to unknown;
- an entity whose value has been kept for at least "Data stale after (hours)"
  gets ``carried_stale: true`` (false before that), except the fields that do
  not change on their own;
- the "Data stale" sensor lists those fields in ``stale_carried_fields``;
- the age counts from ``carried_since`` or from the value's own capture time
  when that is older, never from a borrowed or future capture time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.vehicle_cache import (
    CARRIED_NEVER_TOO_LONG,
    CARRY_FORWARD_FIELDS,
    carried_too_long,
)

_NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
_H = 3600


def _ago(hours: float) -> str:
    return (_NOW - timedelta(hours=hours)).isoformat()


# ---------------------------------------------------------------------------
# The helper.
# ---------------------------------------------------------------------------


def test_the_excluded_fields_are_all_carried_fields():
    """A typo in the exclusion list would silently exclude nothing."""
    assert CARRIED_NEVER_TOO_LONG <= CARRY_FORWARD_FIELDS


def test_only_values_kept_at_least_the_threshold_are_listed():
    vehicle = {"field_carried_since": {
        "target_soc": _ago(80), "battery_soc": _ago(10), "odometer_km": _ago(72),
    }}
    assert carried_too_long(vehicle, 72 * _H, _NOW) == ["odometer_km", "target_soc"]


def test_fields_that_do_not_change_on_their_own_are_never_listed():
    vehicle = {"field_carried_since": {
        key: _ago(5000) for key in CARRIED_NEVER_TOO_LONG
    }}
    assert carried_too_long(vehicle, 72 * _H, _NOW) == []


def test_an_older_own_capture_time_counts():
    """Stopped arriving 10 h ago, but captured 100 h ago: it is 100 h old."""
    vehicle = {
        "field_carried_since": {"battery_soc": _ago(10)},
        "field_captured_ts": {"battery_soc": _ago(100)},
    }
    assert carried_too_long(vehicle, 72 * _H, _NOW) == ["battery_soc"]


def test_a_borrowed_capture_time_does_not_count():
    vehicle = {
        "field_carried_since": {"battery_soc": _ago(10)},
        "field_captured_ts": {"battery_soc": _ago(100)},
        "field_captured_inherited": {"battery_soc": True},
    }
    assert carried_too_long(vehicle, 72 * _H, _NOW) == []


def test_a_future_capture_time_cannot_hide_an_old_value():
    vehicle = {
        "field_carried_since": {"target_soc": _ago(90)},
        "field_captured_ts": {"target_soc": _ago(-6)},
    }
    assert carried_too_long(vehicle, 72 * _H, _NOW) == ["target_soc"]


def test_a_newer_capture_time_does_not_shorten_the_carry():
    vehicle = {
        "field_carried_since": {"target_soc": _ago(90)},
        "field_captured_ts": {"target_soc": _ago(1)},
    }
    assert carried_too_long(vehicle, 72 * _H, _NOW) == ["target_soc"]


@pytest.mark.parametrize("marks", [None, {}, "x", {"target_soc": ""},
                                   {"target_soc": "not a time"},
                                   {"target_soc": None}])
def test_missing_or_broken_marks_list_nothing(marks):
    vehicle: dict[str, Any] = {} if marks is None else {"field_carried_since": marks}
    assert carried_too_long(vehicle, 72 * _H, _NOW) == []


def test_the_threshold_decides():
    vehicle = {"field_carried_since": {"target_soc": _ago(2)}}
    assert carried_too_long(vehicle, 1 * _H, _NOW) == ["target_soc"]
    assert carried_too_long(vehicle, 3 * _H, _NOW) == []


# ---------------------------------------------------------------------------
# On the entities.
# ---------------------------------------------------------------------------


def _coordinator(vehicle: dict[str, Any], *, hours: int | None = 72):
    """A real coordinator method on a stub, so the option path is the shipped one."""
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.options = {} if hours is None else {"stale_threshold_hours": hours}
    coord.entry.data = {"scan_interval": 5}
    coord.data = {"V": vehicle}
    return coord


def _sensor(key: str, coordinator: Any):
    from custom_components.vag_connect.sensor import (
        SENSOR_DESCRIPTIONS,
        VagConnectSensor,
    )
    ent = VagConnectSensor.__new__(VagConnectSensor)
    ent.coordinator = coordinator
    ent._vin = "V"
    ent._key = key
    ent.entity_description = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
    return ent


def _attrs(ent: Any) -> dict[str, Any]:
    from custom_components.vag_connect.entity_base import VagConnectEntity
    return VagConnectEntity.extra_state_attributes.fget(ent) or {}


def test_a_value_kept_past_the_threshold_says_carried_stale():
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=80)).isoformat()
    vehicle = {"target_soc": 80, "field_carried_since": {"target_soc": since}}
    attrs = _attrs(_sensor("target_soc", _coordinator(vehicle)))
    assert attrs["freshness_source"] == "carried"
    assert attrs["carried_since"] == since
    assert attrs["carried_stale"] is True


def test_a_value_kept_briefly_says_not_yet():
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat()
    vehicle = {"target_soc": 80, "field_carried_since": {"target_soc": since}}
    attrs = _attrs(_sensor("target_soc", _coordinator(vehicle)))
    assert attrs["carried_stale"] is False


def test_the_option_moves_the_verdict():
    """1 h set, scan interval 5 min: eight intervals are 40 min, so 1 h wins."""
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat()
    vehicle = {"target_soc": 80, "field_carried_since": {"target_soc": since}}
    attrs = _attrs(_sensor("target_soc", _coordinator(vehicle, hours=1)))
    assert attrs["carried_stale"] is True


def test_a_fresh_value_has_no_carried_attributes():
    vehicle = {"target_soc": 80}
    attrs = _attrs(_sensor("target_soc", _coordinator(vehicle)))
    assert "carried_stale" not in attrs
    assert attrs.get("freshness_source") != "carried"


def test_a_field_that_does_not_change_on_its_own_gets_no_verdict():
    since = (datetime.now(tz=timezone.utc) - timedelta(days=60)).isoformat()
    vehicle = {"fuel_tank_capacity_liters": 50,
               "field_carried_since": {"fuel_tank_capacity_liters": since}}
    from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
    if not any(d.key == "fuel_tank_capacity_liters" for d in SENSOR_DESCRIPTIONS):
        pytest.skip("no shipped sensor for the tank size")
    attrs = _attrs(_sensor("fuel_tank_capacity_liters", _coordinator(vehicle)))
    assert attrs["freshness_source"] == "carried"
    assert "carried_stale" not in attrs


def test_without_a_usable_threshold_there_is_no_verdict():
    """A coordinator stand-in without the method (as many tests use)."""
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=80)).isoformat()
    coordinator = MagicMock()
    coordinator.data = {"V": {"target_soc": 80,
                              "field_carried_since": {"target_soc": since}}}
    attrs = _attrs(_sensor("target_soc", coordinator))
    assert attrs["freshness_source"] == "carried"
    assert "carried_stale" not in attrs


def test_the_value_itself_is_untouched():
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=500)).isoformat()
    vehicle = {"target_soc": 80, "field_carried_since": {"target_soc": since}}
    ent = _sensor("target_soc", _coordinator(vehicle))
    assert ent.native_value == 80


# ---------------------------------------------------------------------------
# On the "Data stale" sensor.
# ---------------------------------------------------------------------------


def _stale_sensor(coordinator: Any):
    from custom_components.vag_connect.binary_sensor import VagDataStaleSensor
    ent = VagDataStaleSensor.__new__(VagDataStaleSensor)
    ent.coordinator = coordinator
    ent._vin = "V"
    ent._key = "data_stale"
    return ent


def test_the_data_stale_sensor_lists_values_kept_too_long():
    now = datetime.now(tz=timezone.utc)
    vehicle = {
        "data_stale": False,
        "target_soc": 80, "battery_soc": 61, "fuel_tank_capacity_liters": 50,
        "field_carried_since": {
            "target_soc": (now - timedelta(hours=200)).isoformat(),
            "battery_soc": (now - timedelta(hours=2)).isoformat(),
            "fuel_tank_capacity_liters": (now - timedelta(days=90)).isoformat(),
        },
    }
    ent = _stale_sensor(_coordinator(vehicle))
    assert ent.is_on is False
    assert ent._platform_attributes()["stale_carried_fields"] == ["target_soc"]


def test_the_data_stale_sensor_adds_nothing_when_nothing_is_old():
    now = datetime.now(tz=timezone.utc)
    vehicle = {"data_stale": False, "portal_health": "ok",
               "field_carried_since": {
                   "target_soc": (now - timedelta(hours=2)).isoformat()}}
    attrs = _stale_sensor(_coordinator(vehicle))._platform_attributes()
    assert attrs == {"portal_health": "ok"}
