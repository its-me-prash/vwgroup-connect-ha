# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda active ventilation (Lüften / airing without heating) as its own switch.

The Škoda command command_start_active_ventilation existed in the API client but
was unreachable from HA — the only ventilation switch is keyed to the SEAT/CUPRA
command_start_ventilation. A diesel Octavia owner asked for the app's "Lüften"
via the HA Tipps und Tricks Facebook group. The new switch routes to the Škoda
command; it can never double up with the SEAT/CUPRA one because each command
lives on a different client.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

VIN = "TMBJJ7NX1M0000001"


def _sw(**vehicle):
    from custom_components.vag_connect.switch import VagActiveVentilationSwitch

    e = VagActiveVentilationSwitch.__new__(VagActiveVentilationSwitch)
    e._vin = VIN
    coord = AsyncMock()
    coord.data = {VIN: {"vin": VIN, **vehicle}}
    e.coordinator = coord
    return e


def test_optimistic_state_reads_the_string() -> None:
    assert _sw().is_on is None  # unparsed on Škoda → unknown
    assert _sw(active_ventilation_state="ventilation").is_on is True
    assert _sw(active_ventilation_state="off").is_on is False
    assert _sw(active_ventilation_state="INVALID").is_on is False


def test_turn_on_off_route_to_the_coordinator() -> None:
    import asyncio

    e = _sw()
    asyncio.run(e.async_turn_on())
    e.coordinator.async_start_active_ventilation.assert_awaited_once_with(VIN)
    asyncio.run(e.async_turn_off())
    e.coordinator.async_stop_active_ventilation.assert_awaited_once_with(VIN)


def test_coordinator_routes_to_the_skoda_command() -> None:
    import asyncio

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_cmd_optimistic = AsyncMock()
    asyncio.run(c.async_start_active_ventilation(VIN))
    args, kwargs = c._cariad_cmd_optimistic.call_args
    assert args[:2] == (VIN, "command_start_active_ventilation")
    assert kwargs["optimistic"] == {"active_ventilation_state": "ventilation"}
    asyncio.run(c.async_stop_active_ventilation(VIN))
    args, kwargs = c._cariad_cmd_optimistic.call_args
    assert args[:2] == (VIN, "command_stop_active_ventilation")
    assert kwargs["optimistic"] == {"active_ventilation_state": "off"}


def test_no_duplicate_switch_by_construction() -> None:
    """The no-duplicate guarantee reduces to which client owns which method."""
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    assert hasattr(SkodaClient, "command_start_active_ventilation")
    assert not hasattr(SkodaClient, "command_start_ventilation")
    assert hasattr(SeatCupraClient, "command_start_ventilation")
    assert not hasattr(SeatCupraClient, "command_start_active_ventilation")
