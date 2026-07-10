# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.0 (#666) — charging/settings writes use PUT (same fix as climate).

torstentosh's live test on v2.16.3 confirmed climate temp-set (the PUT fix)
now works, but charge-target still 404'd — because the charging setters
still POSTed charging/settings. The CARIAD BFF exposes charging/settings as
a PUT (verified across four BFF-native clients); our field names were
already correct (targetSOC_pct etc.), only the verb was wrong. All four
charging setters now go through the shared _settings_put_with_fallback:
PUT primary, legacy POST fallback (no regression), clean error if both 404.
The MBB legacy target_soc path is unchanged.
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
    c._vehicle_bases = {}
    c._mbb_command_target = lambda: None  # non-MBB (portal/app) path
    return c


def _api_error(status: int) -> APIError:
    return APIError(status, "https://x/charging/settings", "{}")


class TestChargingSettersUsePut:
    def test_target_soc_puts_correct_body(self):
        c = _client()
        c._put = AsyncMock(return_value=None)
        c._post_command = AsyncMock()
        asyncio.run(c.command_set_target_soc("VINX", 80))
        c._put.assert_awaited_once()
        assert c._put.await_args.args[0].endswith(
            "/vehicle/v1/vehicles/VINX/charging/settings"
        )
        assert c._put.await_args.kwargs["json"] == {"targetSOC_pct": 80}
        c._post_command.assert_not_called()

    def test_charge_mode_puts(self):
        c = _client()
        c._put = AsyncMock(return_value=None)
        c._post_command = AsyncMock()
        asyncio.run(c.command_set_charge_mode("VINX", "timer"))
        assert c._put.await_args.kwargs["json"] == {"chargeMode": "TIMER"}

    def test_min_soc_puts(self):
        c = _client()
        c._put = AsyncMock(return_value=None)
        c._post_command = AsyncMock()
        asyncio.run(c.command_set_min_soc("VINX", 20))
        assert c._put.await_args.kwargs["json"] == {"minChargeLimit_pct": 20}

    def test_max_current_puts(self):
        c = _client()
        c._put = AsyncMock(return_value=None)
        c._post_command = AsyncMock()
        asyncio.run(c.command_set_max_charge_current("VINX", 16))
        assert c._put.await_args.kwargs["json"] == {"maxChargeCurrentAC_A": 16}


class TestChargingFallback:
    def test_put_404_falls_back_to_post(self):
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(404))
        c._post_command = AsyncMock(return_value=None)
        asyncio.run(c.command_set_target_soc("VINX", 80))
        c._post_command.assert_awaited_once()
        args, kwargs = c._post_command.await_args
        assert args[1] == "charging/settings"
        assert kwargs["json"] == {"targetSOC_pct": 80}

    def test_put_405_falls_back(self):
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(405))
        c._post_command = AsyncMock(return_value=None)
        asyncio.run(c.command_set_target_soc("VINX", 80))
        c._post_command.assert_awaited_once()

    def test_both_404_raises_clean(self):
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(404))
        c._post_command = AsyncMock(side_effect=_api_error(404))
        with pytest.raises(VehicleCommandError):
            asyncio.run(c.command_set_target_soc("VINX", 80))

    def test_5xx_propagates_no_fallback(self):
        c = _client()
        c._put = AsyncMock(side_effect=_api_error(500))
        c._post_command = AsyncMock()
        with pytest.raises(APIError):
            asyncio.run(c.command_set_target_soc("VINX", 80))
        c._post_command.assert_not_called()


class TestMbbPathUnchanged:
    def test_target_soc_uses_mbb_when_present(self):
        # A legacy MBB car must still route through the MBB op, NOT the PUT.
        c = _client()
        mbb = MagicMock()
        mbb._command_mbb_op = AsyncMock(return_value=None)
        c._mbb_command_target = lambda: mbb
        c._put = AsyncMock()
        asyncio.run(c.command_set_target_soc("VINX", 80))
        mbb._command_mbb_op.assert_awaited_once()
        c._put.assert_not_called()
