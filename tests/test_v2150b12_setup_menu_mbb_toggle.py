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

import pytest

from custom_components.vag_connect.config_flow import VagConnectConfigFlow
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MBB_COMMAND_CLIENT_ID,
    CONF_MBB_COMMAND_TOKENS,
    CONF_MBB_COMMANDS_BLOCKED_REASON,
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

def test_menu_has_the_expected_sources() -> None:
    # b12 collapsed the old standalone mbb_login / website_authproxy entries into
    # the Portal toggle. v3.0.0a1 added the experimental companion (ADB) source.
    # b15 added the "audi_mbb_fallback" entry (arm the MBB fallback on an existing
    # device-grant Audi). The two removed ones must stay gone.
    result = asyncio.run(_flow().async_step_user(None))
    assert result["type"] == "menu"
    opts = set(result["menu_options"])
    assert opts == {
        "browser_login", "email_password", "companion_adb", "audi_mbb_fallback",
    }
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


def test_finish_mint_failure_keeps_portal_without_commands() -> None:
    # MBB mint failed → portal entry created, no command channel.
    #
    # #1809 — this used to assert CONF_MEB_COMMANDS_UNAVAILABLE on ANY mint
    # failure, which is how the repair notice came to tell a user whose login
    # hit a 5xx or a timeout that "the durable Car-Net login answered Unknown
    # user". The entry now records WHY, and claims that verdict only when the
    # backend actually gave it (see the GUARD below).
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow._dag_mbb_command = True
    flow._pending_portal_data = {CONF_BRAND: "volkswagen", "username": "u@t.de"}
    flow._pending_portal_title = "Volkswagen EU — u@t.de"
    flow._dag_tokens = _tok("portal-id")
    flow._dag_mbb_tokens = None  # mint failed, reason undetermined
    asyncio.run(flow.async_step_browser_login_finish())
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_MBB_COMMAND_CHANNEL not in data  # reads still work, no commands
    assert data[CONF_MBB_COMMANDS_BLOCKED_REASON] == "unknown"  # flagged, honestly
    assert CONF_MEB_COMMANDS_UNAVAILABLE not in data  # no Car-Net verdict claimed


def test_finish_not_enrolled_still_flags_the_carnet_verdict() -> None:
    # GUARD for the above: when the backend DID answer "Unknown user", the
    # original flag must still be written, so the notice is unchanged for the
    # case it was written for.
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow._dag_mbb_command = True
    flow._pending_portal_data = {CONF_BRAND: "volkswagen", "username": "u@t.de"}
    flow._pending_portal_title = "Volkswagen EU — u@t.de"
    flow._dag_tokens = _tok("portal-id")
    flow._dag_mbb_tokens = None
    flow._dag_mbb_failure_reason = "not_enrolled"
    asyncio.run(flow.async_step_browser_login_finish())
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_MBB_COMMAND_CHANNEL not in data
    assert data[CONF_MEB_COMMANDS_UNAVAILABLE] is True
    assert data[CONF_MBB_COMMANDS_BLOCKED_REASON] == "not_enrolled"


# ── #1809 follow-up: driven through the approve step, not finish alone ───────


def _approved_flow(reason: str) -> VagConnectConfigFlow:
    """A portal + MBB-command flow whose QR poll is done and whose mint failed."""
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow._dismiss_dag_persistent_notification = MagicMock()
    flow._dag_device_code = "device-code"
    flow._dag_poll_task = MagicMock(done=MagicMock(return_value=True))
    flow._dag_mbb = True
    flow._dag_mbb_command = True
    flow._pending_portal_data = {CONF_BRAND: "audi", "username": "u@t.de"}
    flow._pending_portal_title = "Audi — u@t.de"
    flow._dag_tokens = _tok("portal-id")
    flow._dag_mbb_tokens = None
    flow._dag_mbb_failure_reason = reason
    flow._dag_mbb_ineligible = reason == "not_enrolled"
    return flow


@pytest.mark.parametrize("reason", ["unknown", "not_enrolled"])
def test_every_mint_failure_keeps_the_portal_entry(reason: str) -> None:
    # The finish-only tests above could not see this: approve used to reach
    # finish ONLY on a successful mint, and kept the read-only portal entry only
    # for the confirmed "Unknown user". A 5xx or a bare invalid_grant sent the
    # user back to the MBB form and the validated portal reads were lost.
    flow = _approved_flow(reason)
    flow.async_step_mbb_login = AsyncMock(return_value={"type": "form"})
    asyncio.run(flow.async_step_browser_login_approve({}))
    flow.async_step_mbb_login.assert_not_called()
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_MBB_COMMAND_CHANNEL not in data
    assert data[CONF_MBB_COMMANDS_BLOCKED_REASON] == reason
    assert (CONF_MEB_COMMANDS_UNAVAILABLE in data) is (reason == "not_enrolled")


def test_a_phase_one_failure_still_routes_back_to_retry() -> None:
    # GUARD: no app tokens means the sign-in itself failed; there is nothing to
    # keep, so the retry route stays as it was.
    flow = _approved_flow("unknown")
    flow._dag_tokens = None
    flow.async_step_mbb_login = AsyncMock(return_value={"type": "form"})
    asyncio.run(flow.async_step_browser_login_approve({}))
    flow.async_step_mbb_login.assert_called_once()
    flow.async_create_entry.assert_not_called()


def test_a_stale_verdict_does_not_survive_a_new_attempt() -> None:
    # Reconfigure seeds the pending data from entry.data. An earlier
    # "Unknown user" must not outlive an attempt that failed differently…
    flow = _approved_flow("unknown")
    flow._pending_portal_data = {
        **flow._pending_portal_data,
        CONF_MEB_COMMANDS_UNAVAILABLE: True,
        CONF_MBB_COMMANDS_BLOCKED_REASON: "not_enrolled",
    }
    asyncio.run(flow.async_step_browser_login_finish())
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_MEB_COMMANDS_UNAVAILABLE not in data
    assert data[CONF_MBB_COMMANDS_BLOCKED_REASON] == "unknown"


def test_a_successful_reapproval_clears_the_old_verdict() -> None:
    # …and a working command channel must not keep "commands unavailable".
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow._dag_mbb_command = True
    flow._pending_portal_data = {
        CONF_BRAND: "audi", "username": "u@t.de",
        CONF_MEB_COMMANDS_UNAVAILABLE: True,
        CONF_MBB_COMMANDS_BLOCKED_REASON: "unknown",
    }
    flow._pending_portal_title = "Audi — u@t.de"
    flow._dag_tokens = _tok("portal-id")
    flow._dag_mbb_tokens = _tok("mbb-access")
    flow._dag_mbb_client_id = "mbb-client"
    asyncio.run(flow.async_step_browser_login_finish())
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert data[CONF_MBB_COMMAND_CHANNEL] is True
    assert CONF_MEB_COMMANDS_UNAVAILABLE not in data
    assert CONF_MBB_COMMANDS_BLOCKED_REASON not in data
