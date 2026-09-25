# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1434 follow-up (to skornehl PR #1435) — the Data Act portal kickoff also
skips a user-disabled vehicle.

``_ensure_data_act_custom_request_kickoff`` iterated ``self.vehicles`` unfiltered,
so in EU-Data-Act portal mode a car the user disabled in HA still had its 15-min
Custom Data Request probed / kicked (~once per 6 h, reachable from the periodic
loop and from ``_async_update_data``). It now filters through ``_active_vins()``
like every other periodic path, so a disabled vehicle stays fully quiet.
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

_MOD = "custom_components.vag_connect.coordinator"
_SCRAPER = "custom_components.vag_connect.cariad.auth._data_act_scraper.DataActScraper"
_SESSION = "homeassistant.helpers.aiohttp_client.async_get_clientsession"

VIN_ACTIVE = "WVWZZZ3CZ9W025570"
VIN_DISABLED = "WVGZZZE27PP016396"  # a sold car, device disabled by the user


def _registry_with_disabled(vin: str):
    from homeassistant.helpers import device_registry as dr
    reg = MagicMock()

    def _get(identifier, _entry_id):
        _domain, this_vin = identifier
        dev = MagicMock()
        dev.disabled_by = dr.DeviceEntryDisabler.USER if this_vin == vin else None
        return dev

    reg.async_get_device_by_identifier.side_effect = _get
    return reg


def _coord():
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = "e1"
    c.entry.data = {CONF_BRAND: "volkswagen"}
    c.entry.options = {
        CONF_EU_DATA_ACT_AUTO_KICKOFF: True,
        # the active VIN already has an adopted identifier, so a match → continue
        # → no POST and no entry write, keeping the test free of persist plumbing.
        CONF_DATA_ACT_IDENTIFIERS: {VIN_ACTIVE: "id-active"},
    }
    c._vehicles_lock = threading.Lock()
    c._cariad_client = MagicMock()
    c._cariad_client._tokens.strategy = "data_act_portal"
    c.vehicles = {VIN_ACTIVE: {"cached": True}, VIN_DISABLED: {"cached": True}}
    return c


def _run(disabled_vin: str):
    coord = _coord()
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value="id-active")
    scraper.kickoff_custom_data_request = AsyncMock(return_value=None)
    with patch(_SCRAPER, return_value=scraper),          patch(_SESSION, return_value=MagicMock()),          patch(f"{_MOD}.dr.async_get", return_value=_registry_with_disabled(disabled_vin)),          patch(f"{_MOD}._self_update_entry"):
        asyncio.run(coord._ensure_data_act_custom_request_kickoff(force=False))
    asked = [call.args[0] for call in scraper.get_active_custom_request_identifier.call_args_list]
    return asked, scraper


def test_kickoff_skips_user_disabled_vin() -> None:
    asked, scraper = _run(disabled_vin=VIN_DISABLED)
    assert VIN_ACTIVE in asked
    assert VIN_DISABLED not in asked          # the fix: disabled VIN never reaches the portal
    scraper.kickoff_custom_data_request.assert_not_called()


def test_kickoff_still_processes_active_when_none_disabled() -> None:
    # control — a clean registry must not drop the active vehicle
    asked, _ = _run(disabled_vin="NONE_MATCHES")
    assert VIN_ACTIVE in asked
    assert VIN_DISABLED in asked
