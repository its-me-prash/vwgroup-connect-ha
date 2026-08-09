# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""2.31.0 wave — camping + auto-unlock-plug switches (HA wiring).

Both read-gate on a parsed state (a car that reports it has the feature), mirror
the battery-care wiring, and dispatch through the coordinator to the grounded
Škoda client commands.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

VIN = "TMBJJ7NX1M0000001"


def _coord(**vehicle_extra):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.data = {VIN: {"vin": VIN, "has_battery": True, **vehicle_extra}}
    c._cariad_cmd_optimistic = AsyncMock()
    return c


def _camping(coord):
    from custom_components.vag_connect.switch import VagCampingSwitch

    return VagCampingSwitch(coord, VIN)


def _auto_unlock(coord):
    from custom_components.vag_connect.switch import VagAutoUnlockPlugSwitch

    return VagAutoUnlockPlugSwitch(coord, VIN)


# ── camping ──────────────────────────────────────────────────────────────────

def test_camping_reflects_state() -> None:
    assert _camping(_coord(camping_mode=True)).is_on is True
    assert _camping(_coord(camping_mode=False)).is_on is False


def test_camping_unknown_when_silent() -> None:
    assert _camping(_coord()).is_on is None  # not False


@pytest.mark.asyncio
async def test_camping_turn_on_off_dispatch() -> None:
    c = _coord(camping_mode=False)
    c.async_start_camping = AsyncMock()
    c.async_stop_camping = AsyncMock()
    await _camping(c).async_turn_on()
    c.async_start_camping.assert_awaited_once_with(VIN)
    await _camping(c).async_turn_off()
    c.async_stop_camping.assert_awaited_once_with(VIN)


# ── auto-unlock plug ─────────────────────────────────────────────────────────

def test_auto_unlock_reflects_state() -> None:
    assert _auto_unlock(_coord(auto_unlock_when_charged=True)).is_on is True
    assert _auto_unlock(_coord(auto_unlock_when_charged=False)).is_on is False


@pytest.mark.asyncio
async def test_auto_unlock_turn_on_off_dispatch() -> None:
    c = _coord(auto_unlock_when_charged=False)
    c.async_set_auto_unlock_plug = AsyncMock()
    await _auto_unlock(c).async_turn_on()
    c.async_set_auto_unlock_plug.assert_awaited_with(VIN, True)
    await _auto_unlock(c).async_turn_off()
    c.async_set_auto_unlock_plug.assert_awaited_with(VIN, False)


# ── coordinator dispatch → grounded client commands ──────────────────────────

@pytest.mark.asyncio
async def test_coordinator_camping_dispatch() -> None:
    c = _coord(camping_mode=None)
    await c.async_start_camping(VIN)
    args, kwargs = c._cariad_cmd_optimistic.call_args
    assert args[:2] == (VIN, "command_start_camping")
    assert kwargs["optimistic"] == {"camping_mode": True}


@pytest.mark.asyncio
async def test_coordinator_auto_unlock_maps_enum() -> None:
    c = _coord()
    await c.async_set_auto_unlock_plug(VIN, True)
    _, kwargs = c._cariad_cmd_optimistic.call_args
    assert kwargs["mode"] == "PERMANENT"
    assert kwargs["optimistic"] == {"auto_unlock_when_charged": True}
    await c.async_set_auto_unlock_plug(VIN, False)
    _, kwargs = c._cariad_cmd_optimistic.call_args
    assert kwargs["mode"] == "OFF"
