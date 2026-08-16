# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1082 (fg877khkv8-maker) — a US ID.4 lock/unlock 500 becomes an actionable
message, not a bare HTTP 500.

The lock READ stays healthy; only the write is refused (500 from
LockUnlockService), most likely a vehicle software-level capability limit. We do
NOT hide the control (the project never hides on an unconfirmed 500), but we turn
the opaque 500 into a message that reads as a capability limit. A non-500 error
must propagate unchanged, and a success must not raise.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.ha_required

VIN = "WVWZZZ1KZAW001082"
_URL = "https://example.test/lockunlock/v1/vehicle/uuid-1"


def _client():
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    c = VWNAClient.__new__(VWNAClient)
    c._base = "https://example.test"
    c._vin_to_uuid = {VIN: "uuid-1"}
    return c


def _api_error(status: int):
    from custom_components.vag_connect.cariad.exceptions import APIError

    return APIError(status, _URL, "boom")


@pytest.mark.asyncio
async def test_lock_500_becomes_actionable_capability_error():
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    c = _client()
    c._carnet_command = AsyncMock(side_effect=_api_error(500))  # type: ignore[method-assign]
    with pytest.raises(VehicleCommandError) as ei:
        await c.command_lock(VIN)
    msg = str(ei.value)
    assert "LockUnlockService" in msg
    assert "capability" in msg.lower()


@pytest.mark.asyncio
async def test_unlock_500_also_actionable():
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    c = _client()
    c._carnet_command = AsyncMock(side_effect=_api_error(500))  # type: ignore[method-assign]
    with pytest.raises(VehicleCommandError):
        await c.command_unlock(VIN)


@pytest.mark.asyncio
async def test_non_500_propagates_unchanged():
    from custom_components.vag_connect.cariad.exceptions import APIError

    c = _client()
    c._carnet_command = AsyncMock(side_effect=_api_error(403))  # type: ignore[method-assign]
    with pytest.raises(APIError):        # 403 not remapped
        await c.command_lock(VIN)


@pytest.mark.asyncio
async def test_success_does_not_raise():
    c = _client()
    c._carnet_command = AsyncMock(return_value=None)  # type: ignore[method-assign]
    await c.command_lock(VIN)
    c._carnet_command.assert_awaited_once()
