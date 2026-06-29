# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b11 — OFF-switch for the supplementary read channels.

Before b11 a supplementary channel (vw.de / EU Data Act portal) could only ever
be ADDED — the options toggles route on True — so a stuck/dead/redundant channel
kept failing every restart with no way to remove it. b11 surfaces a remove-toggle
(only when the channel is active) that clears it from entry.data + reloads.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.config_flow import VagConnectOptionsFlow
from custom_components.vag_connect.const import (
    CONF_SCAN_INTERVAL,
    CONF_SUPPLEMENTARY_AUTHPROXY,
    CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
    CONF_SUPPLEMENTARY_EU_PORTAL,
    CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
    CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
)


def _flow(data: dict) -> VagConnectOptionsFlow:
    entry = MagicMock()
    entry.entry_id = "E1"
    entry.data = data
    entry.options = {}
    flow = VagConnectOptionsFlow(entry)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = MagicMock(return_value="reload-task")
    hass.async_create_task = MagicMock()
    flow.hass = hass
    return flow


def _schema_keys(result: dict) -> set[str]:
    return {
        getattr(k, "schema", None) for k in result["data_schema"].schema
    }


# ── the remove-toggle only appears when the channel is active ─────────────────

def test_remove_toggles_hidden_when_no_channel() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5})
    keys = _schema_keys(asyncio.run(flow.async_step_init(None)))
    assert "remove_supplementary_authproxy" not in keys
    assert "remove_supplementary_eu_portal" not in keys


def test_remove_toggle_shown_when_vwde_active() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5, CONF_SUPPLEMENTARY_AUTHPROXY: True})
    keys = _schema_keys(asyncio.run(flow.async_step_init(None)))
    assert "remove_supplementary_authproxy" in keys
    assert "remove_supplementary_eu_portal" not in keys


def test_remove_toggle_shown_when_portal_active() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5, CONF_SUPPLEMENTARY_EU_PORTAL: True})
    keys = _schema_keys(asyncio.run(flow.async_step_init(None)))
    assert "remove_supplementary_eu_portal" in keys
    assert "remove_supplementary_authproxy" not in keys


# ── ticking the remove-toggle clears the channel + reloads ───────────────────

def test_remove_vwde_clears_data_and_reloads() -> None:
    flow = _flow({
        CONF_SCAN_INTERVAL: 5,
        CONF_SUPPLEMENTARY_AUTHPROXY: True,
        CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: [{"name": "auth0", "value": "x"}],
    })
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        asyncio.run(flow.async_step_init({
            CONF_SCAN_INTERVAL: 5,
            "remove_supplementary_authproxy": True,
        }))
    new_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert CONF_SUPPLEMENTARY_AUTHPROXY not in new_data
    assert CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES not in new_data
    flow.hass.async_create_task.assert_called_once()  # reload scheduled


def test_remove_portal_clears_creds_and_reloads() -> None:
    flow = _flow({
        CONF_SCAN_INTERVAL: 5,
        CONF_SUPPLEMENTARY_EU_PORTAL: True,
        CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME: "u@t.de",
        CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD: "pw",
    })
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        asyncio.run(flow.async_step_init({
            CONF_SCAN_INTERVAL: 5,
            "remove_supplementary_eu_portal": True,
        }))
    new_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert CONF_SUPPLEMENTARY_EU_PORTAL not in new_data
    assert CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME not in new_data
    assert CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD not in new_data
    flow.hass.async_create_task.assert_called_once()


def test_no_remove_leaves_channel_untouched() -> None:
    # a normal submit (no remove tick) must NOT clear the channel or reload.
    flow = _flow({CONF_SCAN_INTERVAL: 5, CONF_SUPPLEMENTARY_AUTHPROXY: True})
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        asyncio.run(flow.async_step_init({
            CONF_SCAN_INTERVAL: 10,
            "remove_supplementary_authproxy": False,
        }))
    flow.hass.config_entries.async_update_entry.assert_not_called()
    flow.hass.async_create_task.assert_not_called()
