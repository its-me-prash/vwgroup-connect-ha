# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.6 — battery care is settable, not just readable.

The read side shipped in v2.10.0 (`refresh_battery_care` fills
`battery_care_enabled` + `battery_care_target_soc_pct`) and the SEAT/CUPRA
client has had `command_set_battery_care*` just as long. Nothing was ever
wired between them, so users could watch the setting but not change it.

The gate is the interesting part. Every brand client inherits the command
stubs from `CariadBaseClient` (they raise NotImplementedError), so
`hasattr(client, "command_set_battery_care")` is True everywhere and cannot
tell us who actually has the feature. The entities therefore gate on the READ
having produced a value: a car that reports battery-care state is a car whose
backend has it.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

VIN = "WVGZZZ1KZAW123456"


def _coord(**vehicle_extra):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.data = {VIN: {"vin": VIN, "has_battery": True, **vehicle_extra}}
    c._cariad_cmd_optimistic = AsyncMock()
    return c


# ── the switch ──────────────────────────────────────────────────────────────

def _switch(coord):
    from custom_components.vag_connect.switch import VagBatteryCareSwitch

    return VagBatteryCareSwitch(coord, VIN)


def test_switch_reflects_backend_state() -> None:
    assert _switch(_coord(battery_care_enabled=True)).is_on is True
    assert _switch(_coord(battery_care_enabled=False)).is_on is False


def test_switch_unknown_when_backend_silent() -> None:
    # Not False — "we don't know" must not render as "off".
    assert _switch(_coord()).is_on is None


@pytest.mark.asyncio
async def test_switch_sends_the_command() -> None:
    c = _coord(battery_care_enabled=False)
    c.async_set_battery_care = AsyncMock()
    await _switch(c).async_turn_on()
    c.async_set_battery_care.assert_awaited_once_with(VIN, True)


@pytest.mark.asyncio
async def test_switch_off_sends_false() -> None:
    c = _coord(battery_care_enabled=True)
    c.async_set_battery_care = AsyncMock()
    await _switch(c).async_turn_off()
    c.async_set_battery_care.assert_awaited_once_with(VIN, False)


# ── the coordinator dispatch ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_dispatches_care_toggle() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = _coord()
    await VagConnectCoordinator.async_set_battery_care(c, VIN, True)
    args, kwargs = c._cariad_cmd_optimistic.await_args
    assert args[1] == "command_set_battery_care"
    assert kwargs["enabled"] is True
    assert kwargs["optimistic"] == {"battery_care_enabled": True}


@pytest.mark.asyncio
async def test_coordinator_dispatches_care_target() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = _coord()
    await VagConnectCoordinator.async_set_battery_care_target(c, VIN, 80)
    args, kwargs = c._cariad_cmd_optimistic.await_args
    assert args[1] == "command_set_battery_care_target"
    assert kwargs["target_pct"] == 80


@pytest.mark.asyncio
async def test_target_is_not_clamped() -> None:
    # The backend enforces 50-100 and rejects the rest. Clamping here would
    # hide that constraint and silently send something the user didn't pick.
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = _coord()
    await VagConnectCoordinator.async_set_battery_care_target(c, VIN, 20)
    assert c._cariad_cmd_optimistic.await_args.kwargs["target_pct"] == 20


def test_care_commands_share_the_charging_lock() -> None:
    # Both cap the same backend object as target-SoC; racing them would let
    # two settings fight over one value.
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    cls = VagConnectCoordinator._COMMAND_CLASS
    assert cls["command_set_battery_care"] == "charging"
    assert cls["command_set_battery_care_target"] == "charging"
    assert cls["command_set_target_soc"] == "charging"


# ── the number ──────────────────────────────────────────────────────────────

def test_number_target_range_matches_the_backend() -> None:
    from custom_components.vag_connect.number import NUMBER_DESCRIPTIONS

    d = next(x for x in NUMBER_DESCRIPTIONS if x.key == "battery_care_target")
    assert (d.native_min_value, d.native_max_value) == (50, 100)
    assert d.data_key == "battery_care_target_soc_pct"
    assert d.condition == "battery_care"


@pytest.mark.asyncio
async def test_number_sends_the_command() -> None:
    from custom_components.vag_connect.number import (
        NUMBER_DESCRIPTIONS,
        VagConnectNumber,
    )

    d = next(x for x in NUMBER_DESCRIPTIONS if x.key == "battery_care_target")
    c = _coord(battery_care_target_soc_pct=80)
    c.async_set_battery_care_target = AsyncMock()
    n = VagConnectNumber(c, VIN, d)
    await n.async_set_native_value(90.0)
    c.async_set_battery_care_target.assert_awaited_once_with(VIN, 90)


# ── strings ─────────────────────────────────────────────────────────────────

def test_both_entities_named_in_every_language() -> None:
    import glob
    import json

    for f in ["custom_components/vag_connect/strings.json", *sorted(
        glob.glob("custom_components/vag_connect/translations/*.json")
    )]:
        d = json.load(open(f, encoding="utf-8"))
        ent = d.get("entity", {})
        assert ent.get("switch", {}).get("battery_care_switch", {}).get("name"), f
        assert ent.get("number", {}).get("battery_care_target", {}).get("name"), f
