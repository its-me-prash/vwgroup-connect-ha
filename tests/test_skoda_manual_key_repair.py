# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1286 — manual Škoda official-API key fallback. Auto-mint stays the primary
path; when it can't create a key (non-native login, or the keygen rejects the
request), an interactive repair asks the user to paste a MyŠkoda API key + VIN.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.const import CONF_SKODA_OFFICIAL_KEYS


def _flow(entry_id="e1", vins=("VIN1",)):
    from custom_components.vag_connect.repairs import _SkodaOfficialKeyRepairFlow
    f = _SkodaOfficialKeyRepairFlow(entry_id, list(vins))
    f.flow_id = "t"  # satisfy FlowHandler.async_show_form / async_create_entry
    f.handler = "vag_connect"
    return f


# ── the repair flow ───────────────────────────────────────────────────────────

def test_flow_stores_key_and_reloads():
    f = _flow()
    hass = MagicMock()
    entry = MagicMock()
    entry.data = {"brand": "skoda"}
    hass.config_entries.async_get_entry.return_value = entry
    hass.config_entries.async_reload = AsyncMock()
    f.hass = hass
    res = asyncio.run(f.async_step_enter_key({"vin": "vin1", "api_key": "  msk_ABC  "}))
    upd = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    # whitespace stripped, VIN upper-cased, stored like a minted key
    assert upd[CONF_SKODA_OFFICIAL_KEYS]["VIN1"] == {
        "key": "msk_ABC", "id": "manual", "validUntil": "",
    }
    hass.config_entries.async_reload.assert_awaited_once_with("e1")
    assert res["type"] == "create_entry"


def test_flow_empty_key_is_an_error():
    f = _flow()
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = MagicMock(data={})
    f.hass = hass
    res = asyncio.run(f.async_step_enter_key({"vin": "VIN1", "api_key": "   "}))
    hass.config_entries.async_update_entry.assert_not_called()
    assert res["errors"] == {"api_key": "key_required"}


def test_flow_aborts_if_entry_gone():
    f = _flow()
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None
    f.hass = hass
    res = asyncio.run(f.async_step_enter_key({"vin": "VIN1", "api_key": "msk_x"}))
    assert res["type"] == "abort"
    assert res["reason"] == "entry_gone"


def test_form_shown_without_input():
    f = _flow()
    f.hass = MagicMock()
    res = asyncio.run(f.async_step_enter_key(None))
    assert res["type"] == "form"
    assert res["step_id"] == "enter_key"


# ── factory routing ───────────────────────────────────────────────────────────

def test_factory_routes_manual_key_and_splits_vins():
    from custom_components.vag_connect.repairs import (
        _AuthRepairFlow,
        _SkodaOfficialKeyRepairFlow,
        async_create_fix_flow,
    )
    flow = asyncio.run(async_create_fix_flow(
        MagicMock(), "e1_skoda_official_manual_key",
        {"entry_id": "e1", "reason": "skoda_official_manual_key", "vins": "VIN1,VIN2"},
    ))
    assert isinstance(flow, _SkodaOfficialKeyRepairFlow)
    assert flow._vins == ["VIN1", "VIN2"]
    # any other reason still goes to the generic auth repair
    other = asyncio.run(async_create_fix_flow(
        MagicMock(), "e1_invalid_credentials",
        {"entry_id": "e1", "reason": "invalid_credentials"},
    ))
    assert isinstance(other, _AuthRepairFlow)


# ── coordinator reconcile: raise when missing, clear when covered ──────────────

def _coord(entry_data):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = "e1"
    c.entry.data = dict(entry_data)
    return c


def test_reconcile_raises_when_a_vin_has_no_key():
    c = _coord({})
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_manual_key"
    ) as raise_, patch(
        "custom_components.vag_connect.repairs.clear_issue_skoda_official_manual_key"
    ) as clear_:
        c._reconcile_skoda_manual_key_repair(["VIN1", "VIN2"])
    raise_.assert_called_once()
    assert raise_.call_args.args[2] == ["VIN1", "VIN2"]
    clear_.assert_not_called()


def test_reconcile_clears_when_all_vins_have_keys():
    c = _coord({CONF_SKODA_OFFICIAL_KEYS: {"VIN1": {"key": "k"}}})
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_manual_key"
    ) as raise_, patch(
        "custom_components.vag_connect.repairs.clear_issue_skoda_official_manual_key"
    ) as clear_:
        c._reconcile_skoda_manual_key_repair(["VIN1"])
    clear_.assert_called_once()
    raise_.assert_not_called()
