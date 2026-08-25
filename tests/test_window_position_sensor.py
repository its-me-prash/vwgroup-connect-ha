# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-window opening-position (%) sensors — parsed into ``windows_position`` from
the EU-DA window-lifter positions, exposed one entity per populated window slot.
Self-gating: a car that reports no window position spawns no entity.
"""
from __future__ import annotations

import asyncio

from tests.test_entities import _make_coordinator, _make_entry


def test_window_position_native_value_and_translation_key():
    from custom_components.vag_connect.sensor import VagWindowPositionSensor

    coord = _make_coordinator()
    vin = list(coord.data.keys())[0]
    coord.data[vin]["windows_position"] = {"frontLeft": 0, "frontRight": 40}

    s = VagWindowPositionSensor(coord, vin, "frontRight")
    assert s.native_value == 40
    assert s.translation_key == "window_position_front_right"
    assert s.native_unit_of_measurement == "%"

    closed = VagWindowPositionSensor(coord, vin, "frontLeft")
    assert closed.native_value == 0  # 0 % = fully closed, a real reading not None

    # a slot the car didn't report → no value
    absent = VagWindowPositionSensor(coord, vin, "rearLeft")
    assert absent.native_value is None


def _spawn(coord):
    entry = _make_entry(coord)
    added: list = []
    asyncio.run(_async_setup(coord, entry, added))
    return added


async def _async_setup(coord, entry, added):
    from custom_components.vag_connect.sensor import async_setup_entry

    def _collect(entities, **kw):
        added.extend(entities)

    await async_setup_entry(coord.hass, entry, _collect)


def test_window_position_sensors_are_self_gating():
    from custom_components.vag_connect.sensor import VagWindowPositionSensor

    # car WITH window positions → one entity per populated slot
    coord = _make_coordinator()
    vin = list(coord.data.keys())[0]
    coord.data[vin]["windows_position"] = {"frontLeft": 0, "rearRight": 100}
    win = [e for e in _spawn(coord) if isinstance(e, VagWindowPositionSensor)]
    assert {e._window_id for e in win} == {"frontLeft", "rearRight"}

    # car WITHOUT window positions → no such entity (no "unknown" clutter)
    coord2 = _make_coordinator()
    vin2 = list(coord2.data.keys())[0]
    coord2.data[vin2].pop("windows_position", None)
    assert not [e for e in _spawn(coord2) if isinstance(e, VagWindowPositionSensor)]
