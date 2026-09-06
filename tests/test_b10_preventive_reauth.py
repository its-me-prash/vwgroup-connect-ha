# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b10 preventive fixes (grounded in audi_connect #835/#845).

P2a — the browser-login notification offers the PLAIN verification_uri as a
manual-entry fallback, because VW's prefilled ``verification_uri_complete``
intermittently 500s / returns INVALID_REQUEST (#835).

P2b — a passwordless (device_grant / durable-MBB) entry sent to reauth must NOT
land on the credential form (it has no stored password → dead end). It re-runs
the QR sign-in and updates the EXISTING entry in place. Crucially the reauth
finish overwrites the PERSISTED token store, not just ``dag_initial_tokens`` —
the coordinator prefers the store when both exist, so a dag-only update would be
a silent no-op.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.config_flow import VagConnectConfigFlow
from custom_components.vag_connect.const import CONF_BRAND, CONF_PASSWORD, DOMAIN


def _flow() -> VagConnectConfigFlow:
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "e1"}
    flow.handler = DOMAIN
    flow.flow_id = "test"
    return flow


def _entry(data: dict) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = data
    return entry


# ── P2a — plain-URL fallback in the login notification ───────────────────────

def test_notification_includes_plain_url_fallback() -> None:
    flow = _flow()
    flow._dag_verification_uri = "https://idp/oidc/device?user_code=ABCD-1234"
    flow._dag_verification_uri_plain = "https://idp/oidc/device"
    flow._dag_user_code = "ABCD-1234"
    with patch(
        "homeassistant.components.persistent_notification.async_create"
    ) as pn:
        flow._fire_dag_persistent_notification()
    msg = pn.call_args.args[1]
    assert "https://idp/oidc/device" in msg
    assert "by hand" in msg  # the fallback sentence is present


def test_notification_omits_fallback_when_no_distinct_plain_url() -> None:
    flow = _flow()
    flow._dag_verification_uri = "https://idp/oidc/device?user_code=ABCD-1234"
    flow._dag_verification_uri_plain = ""  # not captured / same
    flow._dag_user_code = "ABCD-1234"
    with patch(
        "homeassistant.components.persistent_notification.async_create"
    ) as pn:
        flow._fire_dag_persistent_notification()
    assert "by hand" not in pn.call_args.args[1]


# ── P2b — passwordless reauth routes to QR, not the credential form ──────────

def test_reauth_confirm_routes_passwordless_entry_to_qr() -> None:
    flow = _flow()
    flow.hass.config_entries.async_get_entry = MagicMock(
        return_value=_entry({
            CONF_BRAND: "audi",
            "dag_initial_tokens": {"strategy": "device_grant"},
            CONF_PASSWORD: "",
        })
    )
    flow.async_step_reauth_qr = AsyncMock(return_value={"type": "sentinel"})
    result = asyncio.run(flow.async_step_reauth_confirm(None))
    flow.async_step_reauth_qr.assert_awaited_once()
    assert result == {"type": "sentinel"}


def test_reauth_confirm_password_entry_still_shows_form() -> None:
    # regression: a normal email+password entry must NOT be rerouted.
    flow = _flow()
    flow.hass.config_entries.async_get_entry = MagicMock(
        return_value=_entry({
            CONF_BRAND: "audi",
            "username": "me@example.com",
            CONF_PASSWORD: "secret",
        })
    )
    flow.async_step_reauth_qr = AsyncMock()
    result = asyncio.run(flow.async_step_reauth_confirm(None))
    flow.async_step_reauth_qr.assert_not_awaited()
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


def test_reauth_qr_sets_device_grant_state_and_routes_to_pending() -> None:
    flow = _flow()
    flow.hass.config_entries.async_get_entry = MagicMock(
        return_value=_entry({
            CONF_BRAND: "audi",
            "dag_initial_tokens": {"strategy": "device_grant"},
            CONF_PASSWORD: "",
        })
    )
    flow.async_step_browser_login_pending = AsyncMock(return_value={"type": "s"})
    asyncio.run(flow.async_step_reauth_qr(None))
    flow.async_step_browser_login_pending.assert_awaited_once()
    assert flow._reauth_qr is True
    assert flow._reauth_qr_entry_id == "e1"
    assert flow._dag_mbb is False
    assert flow._dag_brand == "audi"


def test_reauth_qr_mbb_strategy_sets_mbb_flag() -> None:
    flow = _flow()
    flow.hass.config_entries.async_get_entry = MagicMock(
        return_value=_entry({
            CONF_BRAND: "volkswagen",
            "dag_initial_tokens": {"strategy": "mbb"},
            CONF_PASSWORD: "",
        })
    )
    flow.async_step_browser_login_pending = AsyncMock(return_value={"type": "s"})
    asyncio.run(flow.async_step_reauth_qr(None))
    assert flow._dag_mbb is True


def test_browser_login_finish_reauth_guard_diverts_to_reauth_finish() -> None:
    # With _reauth_qr set, finish must divert BEFORE any create/dedup branch.
    flow = _flow()
    flow._dag_tokens = TokenSet("a", "r", "i", 0.0, "device_grant")
    flow._reauth_qr = True
    flow._finish_reauth_qr = AsyncMock(return_value={"type": "abort"})
    # async_create_entry / set_unique_id would be the create path — make them
    # explode so the test fails loudly if the guard doesn't divert.
    flow.async_create_entry = MagicMock(side_effect=AssertionError("create path taken"))
    flow.async_set_unique_id = AsyncMock(side_effect=AssertionError("dedup path taken"))
    asyncio.run(flow.async_step_browser_login_finish(None))
    flow._finish_reauth_qr.assert_awaited_once()


def test_finish_reauth_qr_overwrites_store_and_entry_device_grant() -> None:
    # The load-bearing invariant: reauth overwrites the PERSISTED token store
    # (not just dag_initial_tokens), else the coordinator reloads dead tokens.
    flow = _flow()
    flow._reauth_qr_entry_id = "e1"
    flow._dag_mbb = False
    flow._dag_tokens = TokenSet("newAT", "newRT", "newID", 123.0, "device_grant")
    entry = _entry({CONF_BRAND: "audi", "dag_initial_tokens": {"strategy": "device_grant"}})
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()

    saved = {}
    storage = MagicMock()

    async def _save(ts):
        saved["ts"] = ts
    storage.save = _save

    with patch(
        "custom_components.vag_connect.cariad.auth._token_storage.TokenStorage",
        return_value=storage,
    ), patch(
        "custom_components.vag_connect.cariad.auth._token_storage.storage_key_for_entry",
        return_value="vag_connect_e1",
    ), patch("homeassistant.helpers.storage.Store", return_value=MagicMock()):
        result = asyncio.run(flow._finish_reauth_qr())

    # persisted store overwritten with the fresh device_grant tokens
    assert saved["ts"].access_token == "newAT"
    assert saved["ts"].strategy == "device_grant"
    # entry's dag_initial_tokens also refreshed + reloaded
    new_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data["dag_initial_tokens"]["refresh_token"] == "newRT"
    flow.hass.config_entries.async_reload.assert_awaited_once_with("e1")
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"


def test_finish_reauth_qr_mbb_uses_mbb_tokens() -> None:
    flow = _flow()
    flow._reauth_qr_entry_id = "e1"
    flow._dag_mbb = True
    flow._dag_tokens = TokenSet("oidcAT", "oidcRT", "theIDtoken", 1.0, "device_grant")
    flow._dag_mbb_tokens = TokenSet("mbbAT", "mbbRT", "", 456.0, "mbb")
    flow._dag_mbb_client_id = "XID123"
    entry = _entry({CONF_BRAND: "volkswagen", "dag_initial_tokens": {"strategy": "mbb"}})
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()

    saved = {}
    storage = MagicMock()

    async def _save(ts):
        saved["ts"] = ts
    storage.save = _save

    with patch(
        "custom_components.vag_connect.cariad.auth._token_storage.TokenStorage",
        return_value=storage,
    ), patch(
        "custom_components.vag_connect.cariad.auth._token_storage.storage_key_for_entry",
        return_value="vag_connect_e1",
    ), patch("homeassistant.helpers.storage.Store", return_value=MagicMock()):
        asyncio.run(flow._finish_reauth_qr())

    # MBB bearer stored, but the id_token is carried from the OIDC token set
    assert saved["ts"].access_token == "mbbAT"
    assert saved["ts"].id_token == "theIDtoken"
    assert saved["ts"].strategy == "mbb"
    new_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data["mbb_client_id"] == "XID123"
