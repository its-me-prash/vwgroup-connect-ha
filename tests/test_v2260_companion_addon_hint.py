# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.26.0 — the companion probe points modern-phone users at the add-on.

adb-shell cannot speak Android 11+ wireless debugging (TLS + pairing); it
reaches the port and fails with InvalidCommandError. Instead of a generic
"cannot connect", the setup now returns a reason that names the add-on.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.companion.transport import CompanionTransportError
from custom_components.vag_connect.config_flow import VagConnectConfigFlow


def _flow():
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.path = MagicMock(return_value="/tmp/adbkey")
    return flow


async def _probe_with(err: Exception) -> str:
    fake = AsyncMock()
    fake.connect = AsyncMock(side_effect=err)
    fake.close = AsyncMock()
    with patch(
        "custom_components.vag_connect.companion.transport.NetworkAdbTransport",
        return_value=fake,
    ):
        _ok, reason = await _flow()._companion_probe("volkswagen", "1.2.3.4", 44559)
    return reason


class TestCompanionAddonHint:
    @pytest.mark.asyncio
    async def test_wireless_debugging_signature_points_to_addon(self) -> None:
        err = CompanionTransportError(
            "could not reach the phone at 1.2.3.4:44559 (InvalidCommandError); check ..."
        )
        assert await _probe_with(err) == "companion_needs_addon"

    @pytest.mark.asyncio
    async def test_generic_refusal_stays_cannot_connect(self) -> None:
        err = CompanionTransportError(
            "could not reach the phone at 1.2.3.4:5555 (ConnectionRefusedError); check ..."
        )
        assert await _probe_with(err) == "companion_cannot_connect"
