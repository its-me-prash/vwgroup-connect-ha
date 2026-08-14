# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#912 (@Mirjam9, Audi A6 PPE) — the rich climate-start confirms like the basic one.

`command_start_climate_control` used a raw `_post` and skipped the pendingrequests
confirmation that the basic `command_start_climate` already runs, so an async
backend rejection (the PPE `E:CV.PA.31`) surfaced as a false "OK". The rich path
now routes its response through the same `_await_bff_command` poll — best-effort,
only raising on an explicit terminal rejection, so it can never regress a working
command.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

VIN = "WVWZZZAUZ1234567"


def _client() -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._base_for_vin = lambda vin: "https://bff.test"  # type: ignore[assignment]
    c._post = AsyncMock(return_value={"data": {"requestId": "req-1"}})  # type: ignore[assignment]
    c._await_bff_command = AsyncMock(return_value=None)  # type: ignore[assignment]
    if hasattr(VWEUClient, "_mbb_command_target"):
        c._mbb_command_target = lambda: None  # type: ignore[assignment]
    return c


def test_rich_climate_start_confirms_via_pendingrequests() -> None:
    c = _client()
    asyncio.run(c.command_start_climate_control(VIN, temp_c=21.0))
    c._post.assert_awaited_once()
    c._await_bff_command.assert_awaited_once()
    # the confirmation is fed the actual POST response (so it can match the req id)
    _args = c._await_bff_command.await_args
    assert _args.args[0] == VIN
    assert _args.args[2] == {"data": {"requestId": "req-1"}}
