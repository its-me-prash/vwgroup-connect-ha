# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1439 (maki040) — a failed Data Act kickoff records WHY (portal HTTP status).

The scraper already logs a 503/4xx at attempt time, but after a restart or during
the re-POST backoff the user only saw the generic "no data-request yet". The
coordinator now captures the scraper's last_kickoff_status per VIN into
_data_act_kickoff_error, which diagnostics surfaces — so "503 portal backend" vs
"400-0011 account" is visible without enabling debug logging.
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_DATA_ACT_IDENTIFIERS,
    CONF_EU_DATA_ACT_AUTO_KICKOFF,
)

_SCRAPER = "custom_components.vag_connect.cariad.auth._data_act_scraper.DataActScraper"
_SESSION = "homeassistant.helpers.aiohttp_client.async_get_clientsession"
_MOD = "custom_components.vag_connect.coordinator"
VIN = "WVWZZZ0000000345"


def _coord():
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = "e1"
    c.entry.data = {CONF_BRAND: "volkswagen"}
    c.entry.options = {CONF_EU_DATA_ACT_AUTO_KICKOFF: True, CONF_DATA_ACT_IDENTIFIERS: {}}
    c._vehicles_lock = threading.Lock()
    c._cariad_client = MagicMock()
    c._cariad_client._tokens.strategy = "data_act_portal"
    c.vehicles = {VIN: {"cached": True}}
    c._data_act_kickoff_error = {}
    c._active_vins = lambda vins: vins
    c._notify_data_act_kickoff = lambda vin: None
    return c


def _run(kickoff_status, kickoff_return):
    c = _coord()
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=None)  # no request yet -> kickoff
    scraper.kickoff_custom_data_request = AsyncMock(return_value=kickoff_return)
    scraper.last_kickoff_status = kickoff_status
    with patch(_SCRAPER, return_value=scraper),          patch(_SESSION, return_value=MagicMock()),          patch(f"{_MOD}.dr.async_get", return_value=MagicMock()),          patch(f"{_MOD}._self_update_entry"):
        asyncio.run(c._ensure_data_act_custom_request_kickoff(force=True))
    return c


def test_kickoff_503_is_recorded() -> None:
    c = _run(kickoff_status=503, kickoff_return=None)
    assert c._data_act_kickoff_error.get(VIN) == "HTTP 503"


def test_kickoff_400_is_recorded() -> None:
    c = _run(kickoff_status=400, kickoff_return=None)
    assert c._data_act_kickoff_error.get(VIN) == "HTTP 400"


def test_kickoff_success_clears_the_error() -> None:
    c = _coord()
    c._data_act_kickoff_error[VIN] = "HTTP 503"  # a prior failure recorded
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=None)
    scraper.kickoff_custom_data_request = AsyncMock(return_value="new-id-xyz")
    scraper.last_kickoff_status = None  # success -> reset
    with patch(_SCRAPER, return_value=scraper),          patch(_SESSION, return_value=MagicMock()),          patch(f"{_MOD}.dr.async_get", return_value=MagicMock()),          patch(f"{_MOD}._self_update_entry"):
        asyncio.run(c._ensure_data_act_custom_request_kickoff(force=True))
    assert VIN not in c._data_act_kickoff_error
