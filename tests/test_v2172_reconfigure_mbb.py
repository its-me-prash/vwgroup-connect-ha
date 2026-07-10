# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.2 — Reconfigure hardening + enable-MBB-on-existing-entry.

- ``_brand_label`` never KeyErrors on a picker brand missing from BRANDS
  (Bentley rides the Audi IDK tenant, kept out of the parity-locked BRANDS).
- Reconfigure MERGES entry data — a credential update must not wipe an existing
  durable-MBB command channel.
- Ticking "enable MBB commands" in Reconfigure routes into the QR chain and
  updates THIS entry in place (not a new one).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MBB_COMMAND_TOKENS,
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_USERNAME,
)


def _flow():
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow
    return VagConnectConfigFlow()


# ── _brand_label ──────────────────────────────────────────────────────────────

def test_brand_label_known_brand():
    from custom_components.vag_connect.config_flow import _brand_label
    assert _brand_label("audi") == "Audi (myAudi)"


def test_brand_label_bentley_fallback_no_keyerror():
    from custom_components.vag_connect.config_flow import _brand_label
    # bentley is offered in the picker but absent from BRANDS → must not raise
    assert _brand_label("bentley") == "Bentley"
    # a truly-unknown brand → title-cased fallback (underscores → spaces)
    assert _brand_label("some_new_brand") == "Some New Brand"


# ── _create_or_update_portal_entry ────────────────────────────────────────────

def test_finalize_creates_when_not_reconfigure():
    flow = _flow()
    flow._mbb_reconfigure_entry_id = None
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    res = asyncio.run(
        flow._create_or_update_portal_entry(title="T", data={"a": 1})
    )
    assert res == {"type": "create_entry"}
    flow.async_create_entry.assert_called_once()
    assert flow.async_create_entry.call_args[1]["data"] == {"a": 1}


def test_finalize_updates_existing_when_reconfigure():
    flow = _flow()
    flow._mbb_reconfigure_entry_id = "eid"
    entry = MagicMock()
    entry.entry_id = "eid"
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.async_abort = MagicMock(
        return_value={"type": "abort", "reason": "reconfigure_successful"}
    )
    res = asyncio.run(
        flow._create_or_update_portal_entry(title="T", data={"a": 1})
    )
    flow.hass.config_entries.async_update_entry.assert_called_once()
    assert flow.hass.config_entries.async_update_entry.call_args[1]["data"] == {"a": 1}
    flow.hass.config_entries.async_reload.assert_awaited_once()
    assert res["reason"] == "reconfigure_successful"


# ── async_step_reconfigure ────────────────────────────────────────────────────

def _reconfigure_flow(entry):
    flow = _flow()
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
    return flow


def test_reconfigure_preserves_existing_mbb_channel():
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.unique_id = "volkswagen_user@vw.de"
    entry.data = {
        CONF_BRAND: "volkswagen",
        CONF_USERNAME: "user@vw.de",
        CONF_MBB_COMMAND_CHANNEL: True,
        CONF_MBB_COMMAND_TOKENS: {"access_token": "AT"},
    }
    flow = _reconfigure_flow(entry)
    with patch(
        "custom_components.vag_connect.config_flow._validate_credentials",
        return_value=None,
    ):
        asyncio.run(flow.async_step_reconfigure({
            CONF_BRAND: "volkswagen",
            CONF_USERNAME: "user@vw.de",
            CONF_PASSWORD: "newpass",
            CONF_SPIN: "",
        }))
    flow.hass.config_entries.async_update_entry.assert_called_once()
    new_data = flow.hass.config_entries.async_update_entry.call_args[1]["data"]
    # the MBB channel survived the credential update (merge, not replace)
    assert new_data[CONF_MBB_COMMAND_CHANNEL] is True
    assert new_data[CONF_MBB_COMMAND_TOKENS] == {"access_token": "AT"}
    assert new_data[CONF_PASSWORD] == "newpass"


def test_reconfigure_enable_mbb_routes_into_qr_chain():
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.unique_id = "volkswagen_user@vw.de"
    entry.data = {CONF_BRAND: "volkswagen", CONF_USERNAME: "user@vw.de"}
    flow = _reconfigure_flow(entry)
    flow.async_step_browser_login_pending = AsyncMock(
        return_value={"type": "form", "step_id": "browser_login_pending"}
    )
    with patch(
        "custom_components.vag_connect.config_flow._validate_credentials",
        return_value=None,
    ):
        res = asyncio.run(flow.async_step_reconfigure({
            CONF_BRAND: "volkswagen",
            CONF_USERNAME: "user@vw.de",
            CONF_PASSWORD: "pw",
            CONF_SPIN: "",
            "enable_mbb_commands": True,
        }))
    assert res["step_id"] == "browser_login_pending"
    assert flow._mbb_reconfigure_entry_id == "eid"
    assert flow._dag_mbb_command is True
    assert flow._dag_brand == "volkswagen"
    # did NOT do the plain in-place update — it went to the QR chain instead
    flow.hass.config_entries.async_update_entry.assert_not_called()


def test_reconfigure_enable_mbb_ignored_for_non_vw_audi():
    entry = MagicMock()
    entry.entry_id = "eid"
    entry.unique_id = "skoda_user@skoda.cz"
    entry.data = {CONF_BRAND: "skoda", CONF_USERNAME: "user@skoda.cz"}
    flow = _reconfigure_flow(entry)
    flow.async_step_browser_login_pending = AsyncMock()
    with patch(
        "custom_components.vag_connect.config_flow._validate_credentials",
        return_value=None,
    ):
        asyncio.run(flow.async_step_reconfigure({
            CONF_BRAND: "skoda",
            CONF_USERNAME: "user@skoda.cz",
            CONF_PASSWORD: "pw",
            CONF_SPIN: "",
            "enable_mbb_commands": True,  # honored only for VW/Audi
        }))
    flow.async_step_browser_login_pending.assert_not_awaited()
    flow.hass.config_entries.async_update_entry.assert_called_once()
