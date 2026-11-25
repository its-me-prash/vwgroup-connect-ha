# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two small guards.

#1316 — a petrol Transporter (no high-voltage battery) reported a secondary
engine range of 0 and got a "Secondary engine range: 0 km" sensor. The sensor is
not created when the value is 0 and the car has no battery; a PHEV with 0 keeps
it, and a non-zero value always keeps it.

#923 — ``position_is_stale`` was set on age alone. A car that never recorded a
position (all coordinates null) was flagged stale although there is no pin to
call stale. The flag is only set when latitude and longitude exist.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.vehicle_cache import reconcile


def _ago(**kw: float) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(**kw)).isoformat()


def _keys(vehicle: dict) -> set[str]:
    from custom_components.vag_connect.sensor import async_setup_entry

    coord = MagicMock()
    coord.vehicles = {"X": vehicle}
    coord.data = coord.vehicles
    coord.is_read_only = MagicMock(return_value=False)
    coord.last_update_success = True
    coord.command_capability_supported = MagicMock(return_value=None)
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    entry = MagicMock()
    entry.runtime_data = coord
    entry.options = {"hide_empty_entities": True}
    entry.data = {"brand": "volkswagen"}
    entry.async_on_unload = lambda x: None
    added: list[Any] = []
    asyncio.run(async_setup_entry(MagicMock(), entry, lambda e: added.extend(e)))
    return {e.entity_description.key for e in added if hasattr(e, "entity_description")}


def _car(**kw: Any) -> dict:
    base = {"vin": "X", "has_combustion": True, "has_battery": False,
            "fuel_level_pct": 80}
    base.update(kw)
    return base


class TestSecondaryRangeZeroWithoutBattery:
    def test_petrol_car_with_zero_gets_no_sensor(self) -> None:
        assert "secondary_engine_range_km" not in _keys(
            _car(secondary_engine_range_km=0))

    def test_phev_with_zero_keeps_the_sensor(self) -> None:
        assert "secondary_engine_range_km" in _keys(
            _car(has_battery=True, secondary_engine_range_km=0))

    def test_non_zero_value_keeps_the_sensor_without_battery(self) -> None:
        assert "secondary_engine_range_km" in _keys(
            _car(secondary_engine_range_km=120))

    def test_missing_value_still_creates_nothing(self) -> None:
        assert "secondary_engine_range_km" not in _keys(_car())


class TestStaleOnlyWithAPosition:
    def test_old_clock_without_any_position_is_not_stale(self) -> None:
        previous = {"last_seen_at": _ago(days=5)}
        merged, notes = reconcile(previous, {"vin": "X"})
        assert merged.get("position_is_stale") is None
        assert not any("stale" in n for n in notes)

    def test_old_clock_with_null_coordinates_is_not_stale(self) -> None:
        previous = {"latitude": None, "longitude": None,
                    "position_captured_at": _ago(days=9)}
        merged, _ = reconcile(previous, {"vin": "X"})
        assert merged.get("position_is_stale") is None

    def test_only_one_coordinate_is_not_a_position(self) -> None:
        previous = {"latitude": 1.0, "longitude": None,
                    "position_captured_at": _ago(days=9)}
        merged, _ = reconcile(previous, {"vin": "X"})
        assert merged.get("position_is_stale") is None

    def test_old_recorded_position_is_still_flagged(self) -> None:
        previous = {"latitude": 1.0, "longitude": 2.0,
                    "position_captured_at": _ago(days=9)}
        merged, notes = reconcile(previous, {"vin": "X"})
        assert merged["latitude"] == 1.0
        assert merged.get("position_is_stale") is True
        assert any("stale" in n for n in notes)
