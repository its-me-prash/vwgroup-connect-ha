# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audi two-way BFF → MBB command failover (b15).

A device-grant Audi normally sends commands over the CARIAD BFF. If VW ever
revokes the device-grant (as it did for Škoda in 2026-08), the BFF starts
refusing commands with 401/403. When the user opted in to the durable MBB
command fallback (``CONF_MBB_COMMAND_FALLBACK``) and the car is MBB-eligible, a
refused command is retried ONCE over MBB before the error reaches the user.

Deliberately narrow: only a BFF *auth refusal* (``APIError`` 401/403) triggers a
retry — never a transient 5xx/404, an S-PIN guard, or one of our own
``HomeAssistantError`` guards. On MBB failure the ORIGINAL BFF error surfaces,
never the fallback's.
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.vag_connect.cariad.exceptions import APIError, SpinError
from custom_components.vag_connect.const import CONF_MBB_COMMAND_FALLBACK
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord(*, flag: bool, primary_error: Exception | None,
           fb_error: Exception | None = None):
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = MagicMock()
    coord.entry.data = {"spin": "1234"}
    if flag:
        coord.entry.data[CONF_MBB_COMMAND_FALLBACK] = True
    coord._vehicles_lock = threading.Lock()
    coord._started = True
    coord._was_available = True
    coord.vehicles = {"VIN1": {}}
    coord.async_request_refresh = AsyncMock()

    client = MagicMock()                                   # primary BFF client
    client.command_lock = AsyncMock(side_effect=primary_error)
    fb = MagicMock()                                       # armed MBB fallback
    fb.command_lock = AsyncMock(side_effect=fb_error)
    client.mbb_fallback_connector = MagicMock(return_value=fb)
    coord._cariad_client = client
    coord._fb = fb                                         # test handle
    return coord


class TestAudiMbbFallback:
    def test_bff_403_recovers_via_mbb(self):
        # BFF 403 (revoked device-grant shape) + fallback succeeds → no raise.
        coord = _coord(flag=True, primary_error=APIError(403, "https://bff/lock", ""))
        asyncio.run(coord._cariad_cmd("VIN1", "command_lock"))
        coord._cariad_client.command_lock.assert_awaited_once_with("VIN1")
        coord._fb.command_lock.assert_awaited_once_with("VIN1")
        coord.async_request_refresh.assert_awaited()

    def test_bff_401_recovers_via_mbb(self):
        coord = _coord(flag=True, primary_error=APIError(401, "https://bff/lock", ""))
        asyncio.run(coord._cariad_cmd("VIN1", "command_lock"))
        coord._fb.command_lock.assert_awaited_once_with("VIN1")

    def test_mbb_also_fails_surfaces_original_bff_error(self):
        # Both fail → surface the ORIGINAL BFF (403) error, never the MBB (500).
        coord = _coord(
            flag=True,
            primary_error=APIError(403, "https://bff/lock", ""),
            fb_error=APIError(500, "https://mbb/lock", ""),
        )
        with pytest.raises(HomeAssistantError) as ei:
            asyncio.run(coord._cariad_cmd("VIN1", "command_lock"))
        assert "403" in str(ei.value)
        assert "500" not in str(ei.value)
        coord._fb.command_lock.assert_awaited_once()

    def test_bff_404_does_not_fall_over(self):
        # 404 is not an auth refusal → no MBB retry; surfaces, fallback untouched.
        coord = _coord(flag=True, primary_error=APIError(404, "https://bff/lock", ""))
        with pytest.raises(HomeAssistantError):
            asyncio.run(coord._cariad_cmd("VIN1", "command_lock"))
        coord._fb.command_lock.assert_not_awaited()

    def test_no_optin_no_fallback(self):
        # Flag off → even a 403 does NOT fall over to MBB (config-gated).
        coord = _coord(flag=False, primary_error=APIError(403, "https://bff/lock", ""))
        with pytest.raises(HomeAssistantError):
            asyncio.run(coord._cariad_cmd("VIN1", "command_lock"))
        coord._fb.command_lock.assert_not_awaited()

    def test_spin_error_does_not_fall_over(self):
        # Our own S-PIN guard is a user error, not a BFF refusal → no MBB retry;
        # surfaces cleanly as ServiceValidationError.
        coord = _coord(flag=True, primary_error=SpinError("wrong S-PIN"))
        with pytest.raises(ServiceValidationError):
            asyncio.run(coord._cariad_cmd("VIN1", "command_lock"))
        coord._fb.command_lock.assert_not_awaited()


class TestArmMbbFallbackConnector:
    """arm_mbb_command_channel(fallback_only=True) must NOT change the primary
    command route — the BFF stays command-primary; the connector is only exposed
    via mbb_fallback_connector()."""

    def _tokenset(self):
        from custom_components.vag_connect.cariad.models import TokenSet
        return TokenSet(access_token="mbb-bearer", refresh_token="r",
                        id_token="", expires_at=0.0, strategy="mbb")

    def test_fallback_only_uses_separate_slot(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        c = VWEUClient(MagicMock(), "u@e.com", "pw", "1234")
        ok = asyncio.run(
            c.arm_mbb_command_channel(self._tokenset(), "cid", ["VIN1"],
                                      fallback_only=True)
        )
        assert ok is True
        # BFF stays command-primary — the normal target must NOT pick it up.
        assert c._mbb_command_target() is None
        # …but the fallback connector IS exposed for the coordinator retry.
        assert c.mbb_fallback_connector() is not None

    def test_channel_mode_uses_command_slot(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        c = VWEUClient(MagicMock(), "u@e.com", "pw", "1234")
        ok = asyncio.run(
            c.arm_mbb_command_channel(self._tokenset(), "cid", ["VIN1"])
        )
        assert ok is True
        # channel mode → commands route through MBB (portal-primary behaviour).
        assert c._mbb_command_target() is not None
        assert c.mbb_fallback_connector() is None
