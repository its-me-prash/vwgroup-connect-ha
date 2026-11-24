# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2202 — Reconfigure with the MBB box UNticked switches the channel off.

The Reconfigure merge keeps every key the base builder does not own, and only
the ticked box had a branch. An armed durable-MBB command channel therefore
stayed armed after the user unticked the box, and the entry kept calling MBB.

Pinned here:
- an explicit False drops the channel flag, its tokens, its client id and the
  two "commands unavailable" verdicts, for Volkswagen and for Audi;
- a submit without the field keeps the channel (v2.17.2 merge, see
  test_v2172_reconfigure_mbb.py);
- the Audi BFF fallback shares the tokens, client id and VIN list and keeps
  them;
- an MBB-primary entry keeps the VIN list it reads its cars from.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MBB_COMMAND_CLIENT_ID,
    CONF_MBB_COMMAND_FALLBACK,
    CONF_MBB_COMMAND_TOKENS,
    CONF_MBB_COMMANDS_BLOCKED_REASON,
    CONF_MBB_VINS,
    CONF_MEB_COMMANDS_UNAVAILABLE,
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_USERNAME,
)

_CHANNEL_KEYS = (
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MBB_COMMAND_TOKENS,
    CONF_MBB_COMMAND_CLIENT_ID,
    CONF_MEB_COMMANDS_UNAVAILABLE,
    CONF_MBB_COMMANDS_BLOCKED_REASON,
)


def _entry(brand: str, data: dict) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.unique_id = f"{brand}_user@example.com"
    entry.data = {CONF_BRAND: brand, CONF_USERNAME: "user@example.com", **data}
    return entry


def _run_reconfigure(entry: MagicMock, extra: dict) -> tuple[MagicMock, dict]:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow

    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.context = {"entry_id": entry.entry_id}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_abort = MagicMock(
        return_value={"type": "abort", "reason": "reconfigure_successful"}
    )
    flow.async_step_browser_login_pending = AsyncMock(
        return_value={"type": "external", "step_id": "browser_login_pending"}
    )
    with patch(
        "custom_components.vag_connect.config_flow._validate_credentials",
        return_value=None,
    ):
        result = asyncio.run(flow.async_step_reconfigure({
            CONF_BRAND: entry.data[CONF_BRAND],
            CONF_USERNAME: entry.data[CONF_USERNAME],
            CONF_PASSWORD: "newpass",
            CONF_SPIN: "",
            **extra,
        }))
    return flow, result


def _new_data(flow: MagicMock) -> dict:
    flow.hass.config_entries.async_update_entry.assert_called_once()
    return flow.hass.config_entries.async_update_entry.call_args[1]["data"]


_ARMED = {
    CONF_MBB_COMMAND_CHANNEL: True,
    CONF_MBB_COMMAND_TOKENS: {"access_token": "AT", "strategy": "mbb"},
    CONF_MBB_COMMAND_CLIENT_ID: "client-1",
    "supplementary_eu_portal": True,
}


def test_untick_drops_the_channel_volkswagen():
    flow, result = _run_reconfigure(
        _entry("volkswagen", _ARMED), {"enable_mbb_commands": False}
    )
    data = _new_data(flow)
    for key in _CHANNEL_KEYS:
        assert key not in data, key
    # everything the box does not own survives
    assert data["supplementary_eu_portal"] is True
    assert data[CONF_PASSWORD] == "newpass"
    assert result["reason"] == "reconfigure_successful"
    flow.async_step_browser_login_pending.assert_not_called()


def test_untick_drops_the_channel_audi():
    flow, _ = _run_reconfigure(
        _entry("audi", _ARMED), {"enable_mbb_commands": False}
    )
    data = _new_data(flow)
    for key in _CHANNEL_KEYS:
        assert key not in data, key


def test_untick_clears_a_failed_mint_verdict():
    # The box was ticked once, the mint failed and left only the verdict; the
    # repair it raises must go once the user no longer asks for commands.
    flow, _ = _run_reconfigure(
        _entry("audi", {
            CONF_MEB_COMMANDS_UNAVAILABLE: True,
            CONF_MBB_COMMANDS_BLOCKED_REASON: "not_enrolled",
        }),
        {"enable_mbb_commands": False},
    )
    data = _new_data(flow)
    assert CONF_MEB_COMMANDS_UNAVAILABLE not in data
    assert CONF_MBB_COMMANDS_BLOCKED_REASON not in data


def test_field_missing_keeps_the_channel():
    flow, _ = _run_reconfigure(_entry("volkswagen", _ARMED), {})
    data = _new_data(flow)
    assert data[CONF_MBB_COMMAND_CHANNEL] is True
    assert data[CONF_MBB_COMMAND_TOKENS] == {"access_token": "AT", "strategy": "mbb"}
    assert data[CONF_MBB_COMMAND_CLIENT_ID] == "client-1"


def test_audi_fallback_keeps_its_bearer():
    # The form shows the box from CONF_MBB_COMMAND_CHANNEL only, so a fallback
    # entry submits False on every Reconfigure. The fallback must survive it.
    fallback = {
        CONF_MBB_COMMAND_FALLBACK: True,
        CONF_MBB_COMMAND_TOKENS: {"access_token": "FB", "strategy": "mbb"},
        CONF_MBB_COMMAND_CLIENT_ID: "client-fb",
        CONF_MBB_VINS: ["WAUZZZ8X3KA000001"],
    }
    flow, _ = _run_reconfigure(
        _entry("audi", fallback), {"enable_mbb_commands": False}
    )
    data = _new_data(flow)
    assert data[CONF_MBB_COMMAND_FALLBACK] is True
    assert data[CONF_MBB_COMMAND_TOKENS] == {"access_token": "FB", "strategy": "mbb"}
    assert data[CONF_MBB_COMMAND_CLIENT_ID] == "client-fb"
    assert data[CONF_MBB_VINS] == ["WAUZZZ8X3KA000001"]


def test_mbb_primary_keeps_its_vehicle_list():
    primary = {
        "dag_initial_tokens": {"access_token": "P", "strategy": "mbb"},
        "mbb_client_id": "client-primary",
        CONF_MBB_VINS: ["WVWZZZTESTVIN0001"],
    }
    flow, _ = _run_reconfigure(
        _entry("volkswagen", primary), {"enable_mbb_commands": False}
    )
    data = _new_data(flow)
    assert data[CONF_MBB_VINS] == ["WVWZZZTESTVIN0001"]
    assert data["mbb_client_id"] == "client-primary"
    assert data["dag_initial_tokens"]["strategy"] == "mbb"


def test_tick_still_routes_to_the_approval():
    flow, result = _run_reconfigure(
        _entry("volkswagen", _ARMED), {"enable_mbb_commands": True}
    )
    flow.async_step_browser_login_pending.assert_awaited_once()
    flow.hass.config_entries.async_update_entry.assert_not_called()
    assert flow._pending_portal_data[CONF_MBB_COMMAND_CHANNEL] is True
    assert result["step_id"] == "browser_login_pending"
