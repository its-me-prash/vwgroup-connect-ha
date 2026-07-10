# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.2 — EU-Data-Act kickoff follow-up nits (from the 2.17.1 review).

1. The manual "create data request" button must run even when automatic
   provisioning is turned OFF (``force`` bypasses the toggle gate).
2. The runtime self-heal must fire on its first call — a None sentinel, not a
   comparison against 0.0 that suppresses it for the host's first 6 h uptime.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_SCRAPER = "custom_components.vag_connect.cariad.auth._data_act_scraper.DataActScraper"
_SESS = "homeassistant.helpers.aiohttp_client.async_get_clientsession"
_VIN = "WVWZZZAUZFW805377"


def _stub(*, auto: bool) -> Any:
    stub = type("S", (), {})()
    stub.entry = MagicMock()
    stub.entry.options = {"eu_data_act_auto_kickoff": auto, "data_act_identifiers": {}}
    stub.entry.data = {"brand": "volkswagen", "eu_data_act_auto_kickoff": auto}
    client = MagicMock()
    client._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i", strategy="data_act_portal",
    )
    stub._cariad_client = client
    stub.vehicles = {_VIN: {}}
    stub.hass = MagicMock()
    return stub


def test_force_bypasses_toggle_off() -> None:
    # auto-kickoff OFF, but force=True (manual button) → kickoff still runs.
    stub = _stub(auto=False)
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=None)
    scraper.kickoff_custom_data_request = AsyncMock(return_value="NEWID")
    with patch(_SCRAPER, return_value=scraper), patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(
                stub, force=True
            )
        )
    scraper.kickoff_custom_data_request.assert_awaited_once()


def test_no_force_with_toggle_off_skips() -> None:
    # regression: auto-kickoff OFF + no force → must return before the scraper.
    stub = _stub(auto=False)
    with patch(_SCRAPER) as ctor, patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(stub)
        )
    ctor.assert_not_called()


def test_manual_button_forces_and_refreshes() -> None:
    stub = type("S", (), {})()
    stub._ensure_data_act_custom_request_kickoff = AsyncMock()
    stub.async_request_refresh = AsyncMock()
    asyncio.run(VagConnectCoordinator.async_create_data_act_request(stub))
    stub._ensure_data_act_custom_request_kickoff.assert_awaited_once()
    # the force kwarg is what bypasses an OFF toggle
    _, kwargs = stub._ensure_data_act_custom_request_kickoff.await_args
    assert kwargs.get("force") is True
    stub.async_request_refresh.assert_awaited_once()


def test_runtime_kickoff_fires_on_fresh_boot() -> None:
    # monotonic() near 0 on a fresh boot must NOT suppress the first runtime
    # kickoff (the 0.0-comparison bug). None sentinel → first call always runs.
    stub = type("S", (), {})()
    stub._ensure_data_act_custom_request_kickoff = AsyncMock()
    with patch("time.monotonic", return_value=30.0):
        asyncio.run(VagConnectCoordinator._maybe_runtime_data_act_kickoff(stub))
    stub._ensure_data_act_custom_request_kickoff.assert_awaited_once()
    assert stub._last_runtime_kickoff == 30.0


def test_runtime_kickoff_rate_limited_after_first() -> None:
    stub = type("S", (), {})()
    stub._ensure_data_act_custom_request_kickoff = AsyncMock()
    stub._last_runtime_kickoff = 1000.0
    # only 1 h later (< 6 h) → suppressed
    with patch("time.monotonic", return_value=1000.0 + 3600):
        asyncio.run(VagConnectCoordinator._maybe_runtime_data_act_kickoff(stub))
    stub._ensure_data_act_custom_request_kickoff.assert_not_awaited()
    # 6 h + later → runs again
    with patch("time.monotonic", return_value=1000.0 + 6 * 3600 + 1):
        asyncio.run(VagConnectCoordinator._maybe_runtime_data_act_kickoff(stub))
    stub._ensure_data_act_custom_request_kickoff.assert_awaited_once()
