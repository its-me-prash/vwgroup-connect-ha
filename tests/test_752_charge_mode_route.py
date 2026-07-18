# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#752 audit — charge-mode setter route + payload fix (VW-EU / Audi CARIAD BFF).

Charge mode has its own CARIAD BFF route ``charging/mode`` with body
``{"preferredChargeMode": <lowerCamel>}`` — NOT ``charging/settings`` with a
``chargeMode`` field (an unknown key on that route → 400 / silent no-op, the
same class as the auxiliary-heating spelling bug). A working myAudi client sends
lower-camelCase values (manual/timer proven); the multi-word modes follow the
same camelCase the read side already aliases.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient


def _client() -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._tokens = None
    c._put = AsyncMock(return_value=None)
    c._post = AsyncMock(return_value=None)
    c._post_command = AsyncMock(return_value=None)
    c._v2_command_paths = {}
    return c


def _run(mode: str) -> tuple[str, dict]:
    c = _client()
    asyncio.run(c.command_set_charge_mode("VINX", mode))
    call = c._put.await_args
    return call.args[0], call.kwargs["json"]


def test_route_is_charging_mode_not_settings() -> None:
    url, _ = _run("timer")
    assert url.endswith("/vehicle/v1/vehicles/VINX/charging/mode")
    assert "charging/settings" not in url


@pytest.mark.parametrize("mode,expected", [
    ("manual", "manual"),
    ("timer", "timer"),
    ("preferred_charging_times", "preferredChargingTimes"),
    ("only_own_current", "onlyOwnCurrent"),
    ("timer_charging_with_climatisation", "timerChargingWithClimatisation"),
])
def test_value_is_lower_camel(mode: str, expected: str) -> None:
    _, body = _run(mode)
    assert body == {"preferredChargeMode": expected}


def test_key_is_preferred_charge_mode_not_chargemode() -> None:
    _, body = _run("timer")
    assert "chargeMode" not in body
    assert "preferredChargeMode" in body
