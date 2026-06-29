# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b3 — hide entities without data: the per-unique-id dynamic spawner (re-spawns
when a field's value first arrives) + the broad data-present gating that keeps a
device from being flooded with "unknown" sensors."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.entity_base import register_dynamic_spawner


def _spawner_setup(build: Any) -> tuple[Any, list[Any], list[Any]]:
    coord = MagicMock()
    coord.vehicles = {"X": {"vin": "X"}}
    cbs: list[Any] = []
    coord.async_add_listener = lambda cb: cbs.append(cb) or (lambda: None)
    added: list[Any] = []
    entry = MagicMock()
    entry.async_on_unload = lambda x: None
    register_dynamic_spawner(entry, coord, lambda e: added.extend(e), build)
    return coord, cbs, added


class TestPerIdSpawner:
    def test_dedup_and_reevaluate_on_data_arrival(self) -> None:
        def build(vin: str, vehicle: dict) -> list[Any]:
            ents = [MagicMock(unique_id=f"{vin}_a")]
            if vehicle.get("b_ready"):
                ents.append(MagicMock(unique_id=f"{vin}_b"))
            return ents

        coord, cbs, added = _spawner_setup(build)
        assert {e.unique_id for e in added} == {"X_a"}  # b not ready yet
        coord.vehicles["X"]["b_ready"] = True
        cbs[0]()  # next poll
        assert {e.unique_id for e in added} == {"X_a", "X_b"}  # b spawns, a not dup

    def test_never_duplicates_on_repeat_polls(self) -> None:
        def build(vin: str, vehicle: dict) -> list[Any]:
            return [MagicMock(unique_id=f"{vin}_a")]

        _coord, cbs, added = _spawner_setup(build)
        cbs[0]()
        cbs[0]()
        assert len(added) == 1


def _coord(vehicle: dict) -> Any:
    c = MagicMock()
    c.vehicles = {"X": vehicle}
    c.data = c.vehicles
    c.is_read_only = MagicMock(return_value=False)
    c.last_update_success = True
    c.command_capability_supported = MagicMock(return_value=None)
    c.async_add_listener = MagicMock(return_value=lambda: None)
    return c


def _entry(coord: Any, hide: bool) -> Any:
    entry = MagicMock()
    entry.runtime_data = coord
    entry.options = {"hide_empty_entities": hide}
    entry.data = {"brand": "skoda"}  # non-trip-stats brand → simpler path
    entry.async_on_unload = lambda x: None
    return entry


def _setup_count(hide: bool) -> int:
    from custom_components.vag_connect.sensor import async_setup_entry
    vehicle = {
        "vin": "X", "has_battery": True, "has_combustion": False,
        "battery_soc": 80, "odometer_km": 1000,  # the only real data
    }
    added: list[Any] = []
    asyncio.run(async_setup_entry(MagicMock(), _entry(_coord(vehicle), hide),
                                  lambda e: added.extend(e)))
    return len(added)


class TestHideEmptyGating:
    def test_hide_on_is_fewer_than_off(self) -> None:
        on = _setup_count(hide=True)
        off = _setup_count(hide=False)
        assert on > 0          # the populated sensors still spawn
        assert off > on        # OFF additionally spawns the data-less sensors

    def test_populated_sensor_present_when_hidden(self) -> None:
        # with hide on, a sensor whose data IS present must still be created
        from custom_components.vag_connect.sensor import async_setup_entry
        vehicle = {"vin": "X", "has_battery": True, "has_combustion": False,
                   "battery_soc": 55}
        added: list[Any] = []
        asyncio.run(async_setup_entry(
            MagicMock(), _entry(_coord(vehicle), True), lambda e: added.extend(e)
        ))
        keys = {e.entity_description.key for e in added}
        assert "battery_soc" in keys
