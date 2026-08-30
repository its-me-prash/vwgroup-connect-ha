# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Config-flow opt-in for the device-grant Audi MBB command fallback (b15).

A device-grant Audi stores no password, so Reconfigure / Re-auth (both password
gated) can't reach it. The ``audi_mbb_fallback`` menu step runs a one-time MBB
browser confirm and ``browser_login_finish`` attaches the durable Car-Net bearer
to the chosen Audi as ``CONF_MBB_COMMAND_FALLBACK`` (armed as a BFF-refusal
fallback by the coordinator). MEB/ID cars mint no MBB bearer → the flow aborts
with ``mbb_not_eligible``.

This covers the finish-branch STORAGE logic (unit-testable). The interactive QR
itself needs a live smoke test on a real Audi.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.const import (
    CONF_MBB_COMMAND_CLIENT_ID,
    CONF_MBB_COMMAND_FALLBACK,
    CONF_MBB_COMMAND_TOKENS,
)


def _armed_flow(entry_data: dict):
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow
    flow = VagConnectConfigFlow()
    flow._dag_mbb_fallback = True
    flow._dag_tokens = SimpleNamespace(
        id_token="ID", access_token="A", refresh_token="R", expires_at=0.0)
    flow._dag_mbb_tokens = SimpleNamespace(
        access_token="MBB_A", refresh_token="MBB_R", expires_at=123.0)
    flow._dag_mbb_client_id = "REGISTERED_CID"
    flow._dag_user_input = {}
    flow._mbb_fallback_entry_id = "eid"
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.data = dict(entry_data)
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.async_abort = MagicMock(
        side_effect=lambda reason: {"type": "abort", "reason": reason})
    return flow, entry


def test_fallback_finish_arms_and_merges():
    flow, entry = _armed_flow(
        {"brand": "audi", "dag_initial_tokens": {"strategy": "device_grant"}})
    res = asyncio.run(flow.async_step_browser_login_finish())
    assert res["reason"] == "mbb_fallback_armed"
    flow.hass.config_entries.async_update_entry.assert_called_once()
    new_data = flow.hass.config_entries.async_update_entry.call_args[1]["data"]
    assert new_data[CONF_MBB_COMMAND_FALLBACK] is True
    assert new_data[CONF_MBB_COMMAND_CLIENT_ID] == "REGISTERED_CID"
    assert new_data[CONF_MBB_COMMAND_TOKENS]["access_token"] == "MBB_A"
    assert new_data[CONF_MBB_COMMAND_TOKENS]["refresh_token"] == "MBB_R"
    assert new_data[CONF_MBB_COMMAND_TOKENS]["strategy"] == "mbb"
    # existing entry data is preserved (merge, not replace)
    assert new_data["brand"] == "audi"
    assert new_data["dag_initial_tokens"]["strategy"] == "device_grant"
    flow.hass.config_entries.async_reload.assert_awaited_once()


def test_fallback_finish_meb_ineligible_aborts():
    # MEB/ID Audi: the MBB exchange never mints a bearer → _dag_mbb_tokens None.
    flow, entry = _armed_flow({"brand": "audi"})
    flow._dag_mbb_tokens = None
    res = asyncio.run(flow.async_step_browser_login_finish())
    assert res["reason"] == "mbb_not_eligible"
    flow.hass.config_entries.async_update_entry.assert_not_called()


def test_fallback_finish_stores_optional_spin_and_vins():
    flow, entry = _armed_flow({"brand": "audi"})
    flow._dag_user_input = {"mbb_vins": "WVWZZZ0000000001, WVWZZZ0000000002",
                            "spin": "1234"}
    asyncio.run(flow.async_step_browser_login_finish())
    from custom_components.vag_connect.const import CONF_MBB_VINS, CONF_SPIN
    new_data = flow.hass.config_entries.async_update_entry.call_args[1]["data"]
    assert new_data[CONF_MBB_VINS] == ["WVWZZZ0000000001", "WVWZZZ0000000002"]
    assert new_data[CONF_SPIN] == "1234"
