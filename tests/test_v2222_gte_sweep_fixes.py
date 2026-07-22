# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.22.2 — GTE deep-sweep follow-ups.

Grounded in a live Golf GTE where two-way commands failed despite a correct,
unlocked S-PIN. Alongside the client-side grant/lock fixes (see
``test_mbb_command_grant_advisory`` + ``test_v2173_mbb_command_errors``), the
sweep surfaced three config/diagnostics bugs covered here:

1. **2FA dropped the MBB command channel.** The non-2FA login chains a
   VW/Audi + "enable MBB commands" tick into the durable-MBB QR before creating
   the entry; the MFA-success path did not, so a 2FA account silently got a
   read-only portal entry.
2. **A per-VIN S-PIN could not be cleared.** Blanking the field left the
   ``CONF_SPIN_BY_VIN`` key absent, and the options→data fold then kept the
   stale value — the override was write-once.
3. **``fcm_push`` showed permanent "capability drift".** Push is opt-in runtime
   state (and can be attestation-walled), so declared-but-not-observed is its
   normal resting state and must not read as drift.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.config_flow import (
    VagConnectConfigFlow,
    VagConnectOptionsFlow,
)
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    CONF_SPIN_BY_VIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_VALIDATE = "custom_components.vag_connect.config_flow._validate_credentials"
_VIN = "WVWZZZAUZFW805377"  # repo-standard MBB test VIN (Golf GTE)


def _flow() -> VagConnectConfigFlow:
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow.handler = DOMAIN
    flow.flow_id = "test"
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


# ── Fix 1: 2FA honours the "enable MBB commands" tick ────────────────────────

def test_email_password_2fa_captures_user_input() -> None:
    # the 2FA detour must stash the raw user_input so the MFA finish can read
    # the enable_mbb_commands tick (previously only _pending_entry_data survived).
    flow = _flow()
    flow.async_step_mfa = AsyncMock(return_value={"type": "form"})
    with patch(_VALIDATE, side_effect=ValueError("two_factor_required")):
        asyncio.run(flow.async_step_email_password({
            CONF_BRAND: "volkswagen", "username": "u@t.de", "password": "pw",
            CONF_SPIN: "", CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            "force_enable_access": False, "enable_mbb_commands": True,
        }))
    assert flow._pending_user_input.get("enable_mbb_commands") is True
    flow.async_step_mfa.assert_awaited_once()


def test_mfa_success_with_mbb_toggle_chains_to_qr() -> None:
    flow = _flow()
    flow.async_step_browser_login_pending = AsyncMock(
        return_value={"type": "progress"}
    )
    flow._pending_brand = "volkswagen"
    flow._pending_username = "u@t.de"
    flow._pending_password = "pw"
    flow._pending_entry_data = {CONF_BRAND: "volkswagen", "username": "u@t.de"}
    flow._pending_user_input = {
        "enable_mbb_commands": True, CONF_BRAND: "volkswagen",
    }
    with patch(_VALIDATE, return_value=None):
        asyncio.run(flow.async_step_mfa({"mfa_code": "123456"}))
    flow.async_step_browser_login_pending.assert_awaited_once()
    assert flow._dag_mbb is True
    assert flow._dag_mbb_command is True
    assert flow._pending_portal_data[CONF_BRAND] == "volkswagen"


def test_mfa_success_without_toggle_creates_plain_entry() -> None:
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow.async_step_browser_login_pending = AsyncMock()
    flow._pending_brand = "volkswagen"
    flow._pending_username = "u@t.de"
    flow._pending_entry_data = {CONF_BRAND: "volkswagen", "username": "u@t.de"}
    flow._pending_user_input = {"enable_mbb_commands": False}
    with patch(_VALIDATE, return_value=None):
        asyncio.run(flow.async_step_mfa({"mfa_code": "123456"}))
    flow.async_step_browser_login_pending.assert_not_awaited()
    flow.async_create_entry.assert_called_once()


def test_mfa_success_non_vw_with_toggle_creates_plain_entry() -> None:
    # the MBB channel is VW/Audi-only; a 2FA Porsche+tick still gets a portal.
    flow = _flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow.async_step_browser_login_pending = AsyncMock()
    flow._pending_brand = "porsche"
    flow._pending_username = "u@t.de"
    flow._pending_entry_data = {CONF_BRAND: "porsche"}
    flow._pending_user_input = {"enable_mbb_commands": True}
    with patch(_VALIDATE, return_value=None):
        asyncio.run(flow.async_step_mfa({"mfa_code": "123456"}))
    flow.async_step_browser_login_pending.assert_not_awaited()
    flow.async_create_entry.assert_called_once()


# ── Fix 2: a per-VIN S-PIN can be cleared ────────────────────────────────────

def _options_flow(entry_data: dict) -> VagConnectOptionsFlow:
    entry = MagicMock()
    entry.data = entry_data
    entry.options = {}
    entry.entry_id = "e1"
    flow = VagConnectOptionsFlow(entry)
    flow.hass = MagicMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    return flow


def test_per_vin_spin_set_is_folded_into_dict() -> None:
    flow = _options_flow({CONF_BRAND: "volkswagen"})
    asyncio.run(flow.async_step_init({f"{CONF_SPIN_BY_VIN}_{_VIN}": "5678"}))
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert data[CONF_SPIN_BY_VIN] == {_VIN: "5678"}


def test_per_vin_spin_blank_clears_override() -> None:
    # blanking the field must persist an explicit (empty) dict so the fold
    # actually removes the override — the write-once bug.
    flow = _options_flow({CONF_BRAND: "volkswagen", CONF_SPIN_BY_VIN: {_VIN: "5678"}})
    asyncio.run(flow.async_step_init({f"{CONF_SPIN_BY_VIN}_{_VIN}": ""}))
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_SPIN_BY_VIN in data
    assert data[CONF_SPIN_BY_VIN] == {}


def test_options_without_per_vin_fields_leave_key_untouched() -> None:
    # a submit from a form that had NO per-VIN fields must not invent the key.
    flow = _options_flow({CONF_BRAND: "volkswagen"})
    asyncio.run(flow.async_step_init({CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL}))
    data = flow.async_create_entry.call_args.kwargs["data"]
    assert CONF_SPIN_BY_VIN not in data


# ── Fix 3: push channels are not "capability drift" ──────────────────────────

def _make_coordinator(brand: str = "volkswagen") -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = MagicMock()
    coord.entry.data = {CONF_BRAND: brand}
    coord.vehicles = {}
    coord._cariad_client = None
    coord._skoda_push = None
    coord._cupra_seat_push = None
    coord._audi_vw_push = None
    return coord


def test_fcm_push_excluded_from_capability_drift() -> None:
    coord = _make_coordinator("volkswagen")
    snap = coord.capabilities_snapshot()
    vw = snap["volkswagen"]
    # declared on, not observed (no push manager live) — but NOT flagged as drift
    assert vw["declared"].get("fcm_push") is True
    assert vw["observed"].get("fcm_push") is False
    assert "fcm_push" not in vw["drift"]
    assert not (
        {"ola_push", "fcm_push", "mqtt_push", "dag_login"} & set(vw["drift"])
    )


def test_vehicle_data_capabilities_still_drift() -> None:
    # the exclusion is surgical: a declared vehicle-data capability that never
    # produced a field is still surfaced (empty garage → every data cap drifts).
    coord = _make_coordinator("volkswagen")
    snap = coord.capabilities_snapshot()
    vw = snap["volkswagen"]
    channels = {"ola_push", "fcm_push", "mqtt_push", "dag_login"}
    expected = {
        k for k, v in vw["declared"].items() if v is True
    } - channels
    assert set(vw["drift"]) == expected
