# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.16.3 (#666) — climate temperature set uses PUT + correct body.

torstentosh's Audi Q4 e-tron (PPE) 404'd on every climate.set_temperature.
Root cause (verified against 4 independent CARIAD-BFF clients): the
climatisation/settings write is a PUT with body
{targetTemperature, targetTemperatureUnit:"celsius"}, but we POSTed
{targetTemperature_C} — a POST to a PUT-only route 404s at the gateway.

Fix: PUT + correct body (primary), legacy POST+_C (no-regression fallback),
clean VehicleCommandError if both 404.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    VehicleCommandError,
)


def _client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    from custom_components.vag_connect.cariad.models import TokenSet
    c = VWEUClient(MagicMock(), "u@t.de", "pw")
    c._tokens = TokenSet("acc", "ref", "id")
    c._vehicle_bases = {}  # _base_for_vin -> default BASE
    return c


def _api_error(status: int) -> APIError:
    return APIError(status, "https://x/climatisation/settings", "{}")


class TestClimateTempPut:
    def test_happy_path_puts_correct_verb_and_body(self):
        c = _client()
        c._put = AsyncMock(return_value=None)
        c._post_command = AsyncMock()
        asyncio.run(c.command_set_climate_temperature("VINX", 21.5))
        c._put.assert_awaited_once()
        url = c._put.await_args.args[0]
        assert url.endswith("/vehicle/v1/vehicles/VINX/climatisation/settings")
        assert c._put.await_args.kwargs["json"] == {
            "targetTemperature": 21.5,
            "targetTemperatureUnit": "celsius",
        }
        # Success on PUT -> the legacy fallback is never touched.
        c._post_command.assert_not_called()

    def test_put_404_falls_back_to_legacy_post(self):
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(404))
        c._post_command = AsyncMock(return_value=None)
        asyncio.run(c.command_set_climate_temperature("VINX", 20.0))
        c._post_command.assert_awaited_once()
        args, kwargs = c._post_command.await_args
        assert args[1] == "climatisation/settings"
        assert kwargs["json"] == {"targetTemperature_C": 20.0}

    def test_put_405_also_falls_back(self):
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(405))
        c._post_command = AsyncMock(return_value=None)
        asyncio.run(c.command_set_climate_temperature("VINX", 19.0))
        c._post_command.assert_awaited_once()

    def test_both_404_raises_clean_command_error(self):
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(404))
        c._post_command = AsyncMock(side_effect=_api_error(404))
        with pytest.raises(VehicleCommandError):
            asyncio.run(c.command_set_climate_temperature("VINX", 22.0))

    def test_put_5xx_propagates_without_fallback(self):
        # A non-404/405 error is a real failure, not an endpoint mismatch —
        # it must propagate and NOT silently try the legacy path.
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(500))
        c._post_command = AsyncMock()
        with pytest.raises(APIError):
            asyncio.run(c.command_set_climate_temperature("VINX", 21.0))
        c._post_command.assert_not_called()

    def test_legacy_post_non_404_propagates(self):
        # If PUT 404s but the fallback POST fails with something other than
        # 404 (e.g. 403), surface that real error, not the generic wrapper.
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(404))
        c._post_command = AsyncMock(side_effect=_api_error(403))
        with pytest.raises(APIError) as ei:
            asyncio.run(c.command_set_climate_temperature("VINX", 21.0))
        assert ei.value.status == 403


class TestPutHelper:
    def test_base_has_put_helper(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        assert hasattr(CariadBaseClient, "_put")
