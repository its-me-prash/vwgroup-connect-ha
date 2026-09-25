# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1316 (EcksteinU) — departure-timer entities must be gated to electric cars.

The three Škoda ``departure_timer_N_time`` sensor descriptions and the three
``departure_timer_N_enabled`` binary_sensors were ungated (condition=None) while
their VW-EU twins already carried ``condition="electric"``. On a combustion
vehicle (has_battery=False) they therefore spawned departure-timer entities that
never apply. This locks in the fix: gated exactly like the electric twins.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

VIN = "TMBJJ7NX1M0000002"

DT_TIME = {
    "departure_timer_1_time": "07:00",
    "departure_timer_2_time": "08:00",
    "departure_timer_3_time": "09:00",
}
DT_EN = {
    "departure_timer_1_enabled": True,
    "departure_timer_2_enabled": True,
    "departure_timer_3_enabled": True,
}


def _keys(added: list[Any]) -> set:
    out = set()
    for e in added:
        desc = getattr(e, "entity_description", None)
        if desc is not None:
            out.add(desc.key)
    return out


def _coord(vehicle: dict) -> Any:
    c = MagicMock()
    c.vehicles = {VIN: vehicle}
    c.data = c.vehicles
    c.is_read_only = MagicMock(return_value=False)
    c.read_capability_hidden = MagicMock(return_value=False)
    c.command_capability_supported = MagicMock(return_value=None)
    c.command_method_available = MagicMock(return_value=False)
    c.async_add_listener = MagicMock(return_value=lambda: None)
    return c


def _run(platform: str, vehicle: dict, brand: str = "skoda") -> list[Any]:
    from importlib import import_module
    mod = import_module(f"custom_components.vag_connect.{platform}")
    entry = MagicMock()
    entry.runtime_data = _coord(vehicle)
    entry.data = {"brand": brand}
    entry.options = {}
    entry.async_on_unload = lambda x: None
    added: list[Any] = []
    asyncio.run(mod.async_setup_entry(MagicMock(), entry, lambda e: added.extend(e)))
    return added


def _departure_keys(keys: set) -> set:
    return {k for k in keys if isinstance(k, str) and k.startswith("departure_timer_")}


def test_departure_timer_time_hidden_on_combustion() -> None:
    v = {"vin": VIN, "has_battery": False, "has_combustion": True, **DT_TIME}
    assert _departure_keys(_keys(_run("sensor", v))) == set()


def test_departure_timer_time_shown_on_electric() -> None:
    v = {"vin": VIN, "has_battery": True, "has_combustion": False, **DT_TIME}
    keys = _keys(_run("sensor", v))
    for k in ("departure_timer_1_time", "departure_timer_2_time", "departure_timer_3_time"):
        assert k in keys


def test_departure_timer_enabled_hidden_on_combustion() -> None:
    v = {"vin": VIN, "has_battery": False, "has_combustion": True, **DT_EN}
    assert _departure_keys(_keys(_run("binary_sensor", v))) == set()


def test_departure_timer_enabled_shown_on_electric() -> None:
    v = {"vin": VIN, "has_battery": True, "has_combustion": False, **DT_EN}
    keys = _keys(_run("binary_sensor", v))
    for k in ("departure_timer_1_enabled", "departure_timer_2_enabled", "departure_timer_3_enabled"):
        assert k in keys
