# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 — manual refresh must not crash when Reconfigure nulls the client.

Mattheisen87 saw ``'NoneType' object has no attribute 'get_status'`` right after
a Reconfigure. A Reconfigure runs an unload that sets ``self._cariad_client =
None``; ``_async_update_data`` had checked the client for None at the top, then
``await``-ed ``_refresh_mbb_command_capabilities()`` — and the unload landed in
that window, so the following ``self._cariad_client.get_status`` dereferenced
None. The fix captures the client into a local right after the guard and uses
that local, so a mid-flight null can't turn the read into a NoneType crash.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock

from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN = "WVWZZZ3CZ9W025570"


def _coord(client) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._started = True
    c._cariad_client = client
    c._vehicles_lock = threading.Lock()
    c.vehicles = {VIN: {"cached": True}}
    return c


class TestReconfigureClientRace:
    def test_client_nulled_mid_flight_does_not_crash_and_uses_captured(self) -> None:
        client = AsyncMock()
        client.get_status = AsyncMock(return_value=object())  # non-VehicleData → skipped
        coord = _coord(client)

        # Simulate the Reconfigure unload landing during the pre-fetch await:
        # _refresh_mbb_command_capabilities() nulls self._cariad_client.
        async def _null_the_client() -> None:
            coord._cariad_client = None

        coord._refresh_mbb_command_capabilities = AsyncMock(side_effect=_null_the_client)
        coord._persist_website_cookies = lambda: None

        # Must NOT raise 'NoneType' object has no attribute 'get_status'.
        result = asyncio.run(coord._async_update_data())

        # The captured client's get_status was still used (proof of the fix:
        # self._cariad_client is None by now, so without the local capture the
        # list comprehension would AttributeError before any await).
        client.get_status.assert_awaited_once_with(VIN)
        assert coord._cariad_client is None          # the unload did happen
        assert result == {VIN: {"cached": True}}     # cached data returned

    def test_client_none_at_entry_returns_cached(self) -> None:
        coord = _coord(None)
        result = asyncio.run(coord._async_update_data())
        assert result == {VIN: {"cached": True}}
