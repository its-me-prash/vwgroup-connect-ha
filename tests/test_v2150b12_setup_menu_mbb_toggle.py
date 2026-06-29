# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b12 — setup flow trimmed to 2 login paths + the Portal "MBB commands" toggle.

The login menu is now QR (browser) + Portal (email/pw). The Portal step can tick
"enable MBB commands" → it validates the portal (reads) then chains to the MBB QR;
the finish creates a portal-PRIMARY entry WITH a durable-MBB command channel.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.config_flow import VagConnectConfigFlow
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MBB_COMMAND_CLIENT_ID,
    CONF_MBB_COMMAND_TOKENS,
    CONF_MEB_COMMANDS_UNAVAILABLE,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.vag_connect.cariad.models import TokenSet

_VALIDATE = "custom_components.vag_connect.config_flow._validate_credentials"


def _flow() -> VagConnectConfigFlow:
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow.handler = DOMAIN
    flow.flow_id = "test"
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


# ── menu trimmed to 2 ────────────────────────────────────────────────────────

def test_menu_has_exactly_two_login_paths() -> None:
    result = asyncio.run(_flow().async_step_user(None))
    assert result["type"] == "menu"
    opts = set(result["menu_options"])
    assert opts == {"browser_login", "email_password"}
    assert "mbb_login" not in opts
    assert "website_authproxy" not in opts


# ── Portal + MBB toggle (VW) chains to the QR ────────────────────────────────

def test_vw_portal_with_mbb_toggle_chains_to_qr() -> None:
    flow = _flow()
    flow.async_step_browser_login_pending = AsyncMock(
        return_value={"type": "progress"}
    )
    with patch(_VALIDATE, return_value=None):
        asyncio.run(flow.async_step_email_password({
            CONF_BRAND: "volkswagen",
            "username": "u@t.de", "password": "pw",
            CONF_SPIN: "1234", CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            "force_enable_access": False,
            "enable_mbb_commands": True,
        }))
    flow.async_step_browser_login_pending.assert_awaited_once()
    assert flow._dag_mbb is True
    assert flow._dag_mbb_command is True
    assert flow._pending_portal_data[CONF_BRAND] == "volkswagen"


def test_non_vw_with_mbb_toggle_creates_plain_portal_entry() -> None:
    # toggle only applies to VW; Porsche just gets the plain portal entry.
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow.async_step_browser_login_pending = AsyncMock()
    with patch(_VALIDATE, return_value=None):
        asyncio.run(flow.async_step_email_password({
            CONF_BRAND: "porsche",
            "username": "u@t.de", "password": "pw",
            CONF_SPIN: "", CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            "force_enable_access": False,
            "enable_mbb_commands": True,
        }))
    flow.async_step_browser_login_pending.assert_not_awaited()
    flow.async_create_entry.assert_called_once()
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_MBB_COMMAND_CHANNEL not in data


def test_vw_portal_without_toggle_is_plain_portal() -> None:
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow.async_step_browser_login_pending = AsyncMock()
    with patch(_VALIDATE, return_value=None):
        asyncio.run(flow.async_step_email_password({
            CONF_BRAND: "volkswagen",
            "username": "u@t.de", "password": "pw",
            CONF_SPIN: "", CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            "force_enable_access": False,
            "enable_mbb_commands": False,
        }))
    flow.async_step_browser_login_pending.assert_not_awaited()
    flow.async_create_entry.assert_called_once()


# ── finish builds the portal + command-channel entry ─────────────────────────

def _tok(acc: str) -> TokenSet:
    return TokenSet(access_token=acc, refresh_token="r", id_token="idtok", strategy="mbb")


def test_finish_builds_portal_plus_command_channel() -> None:
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow._dag_mbb_command = True
    flow._pending_portal_data = {CONF_BRAND: "volkswagen", "username": "u@t.de"}
    flow._pending_portal_title = "Volkswagen EU — u@t.de"
    flow._dag_tokens = _tok("portal-id")
    flow._dag_mbb_tokens = _tok("mbb-bearer")
    flow._dag_mbb_client_id = "client-xyz"
    asyncio.run(flow.async_step_browser_login_finish())
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert data[CONF_MBB_COMMAND_CHANNEL] is True
    assert data[CONF_MBB_COMMAND_TOKENS]["access_token"] == "mbb-bearer"
    assert data[CONF_MBB_COMMAND_CLIENT_ID] == "client-xyz"
    assert data[CONF_BRAND] == "volkswagen"  # portal data preserved


def test_finish_meb_ineligible_keeps_portal_without_commands() -> None:
    # MBB mint failed (MEB car) → portal entry created, no command channel.
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow._dag_mbb_command = True
    flow._pending_portal_data = {CONF_BRAND: "volkswagen", "username": "u@t.de"}
    flow._pending_portal_title = "Volkswagen EU — u@t.de"
    flow._dag_tokens = _tok("portal-id")
    flow._dag_mbb_tokens = None  # mint failed
    asyncio.run(flow.async_step_browser_login_finish())
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_MBB_COMMAND_CHANNEL not in data  # reads still work, no commands
    assert data[CONF_MEB_COMMANDS_UNAVAILABLE] is True  # b13: flagged for the repair
