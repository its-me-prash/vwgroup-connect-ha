# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2138 — switch an existing entry in place to the volkswagen.de-only mode.

A Volkswagen entry whose main channel is the EU Data Act portal and that also
reads volkswagen.de as a supplementary channel can be converted in the options
to the website-authproxy mode that a new volkswagen.de-only entry gets. The
conversion is one-way and read-only.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.config_flow import (
    CONF_SWITCH_VWDE_ONLY,
    VagConnectConfigFlow,
    VagConnectOptionsFlow,
)
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_PASSWORD,
    CONF_READ_ONLY,
    CONF_SCAN_INTERVAL,
    CONF_STRATEGY,
    CONF_SUPPLEMENTARY_AUTHPROXY,
    CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
    CONF_SUPPLEMENTARY_EU_PORTAL,
    CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
    CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
    CONF_USERNAME,
    CONF_VWEU_DEVICE_GRANT,
    CONF_VWEU_TWOWAY_TOKENS,
    CONF_WEBSITE_AUTHPROXY,
    CONF_WEBSITE_COOKIES,
    STRATEGY_COMPANION_ADB,
    vehicle_unique_id,
)
from custom_components.vag_connect.coordinator import VagConnectCoordinator

COOKIES = [{"name": "auth0", "value": "x", "domain": ".volkswagen.de"}]


def _portal_entry_data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_BRAND: "volkswagen",
        CONF_USERNAME: "u@example.org",
        CONF_PASSWORD: "pw",
        CONF_SCAN_INTERVAL: 15,
        CONF_SUPPLEMENTARY_AUTHPROXY: True,
        CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: COOKIES,
        **extra,
    }


def _flow(data: dict[str, Any], options: dict[str, Any] | None = None) -> VagConnectOptionsFlow:
    entry = MagicMock()
    entry.entry_id = "E1"
    entry.data = data
    entry.options = options or {}
    flow = VagConnectOptionsFlow(entry)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = MagicMock(return_value="reload-task")
    hass.async_create_task = MagicMock()
    flow.hass = hass
    return flow


def _keys(result: dict) -> set[str]:
    return {getattr(k, "schema", None) for k in result["data_schema"].schema}


def _offered(data: dict[str, Any], options: dict[str, Any] | None = None) -> bool:
    flow = _flow(data, options)
    return CONF_SWITCH_VWDE_ONLY in _keys(asyncio.run(flow.async_step_init(None)))


def _convert(data: dict[str, Any], submit: dict[str, Any] | None = None) -> tuple[dict, VagConnectOptionsFlow]:
    flow = _flow(data)
    submit = {CONF_SCAN_INTERVAL: 15, CONF_READ_ONLY: False, CONF_SWITCH_VWDE_ONLY: True, **(submit or {})}
    step = asyncio.run(flow.async_step_init(submit))
    assert step["step_id"] == "switch_vwde_only"
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        asyncio.run(flow.async_step_switch_vwde_only({}))
    return flow.hass.config_entries.async_update_entry.call_args.kwargs["data"], flow


# ── offered only when the conditions hold ────────────────────────────────────

def test_offered_for_volkswagen_with_supplementary_cookies() -> None:
    assert _offered(_portal_entry_data())


def test_not_offered_without_supplementary_flag() -> None:
    data = _portal_entry_data()
    data.pop(CONF_SUPPLEMENTARY_AUTHPROXY)
    assert not _offered(data)


def test_not_offered_without_cookies() -> None:
    assert not _offered(_portal_entry_data(**{CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: []}))
    data = _portal_entry_data()
    data.pop(CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES)
    assert not _offered(data)


def test_not_offered_for_other_brand() -> None:
    assert not _offered(_portal_entry_data(**{CONF_BRAND: "audi"}))


def test_not_offered_when_already_website_only() -> None:
    assert not _offered(_portal_entry_data(**{CONF_WEBSITE_AUTHPROXY: True}))


def test_not_offered_for_companion_entry() -> None:
    assert not _offered(_portal_entry_data(**{CONF_STRATEGY: STRATEGY_COMPANION_ADB}))


def test_offered_when_values_live_in_options() -> None:
    # options-then-data: the options override data
    data = _portal_entry_data()
    data.pop(CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES)
    assert _offered(data, {CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: COOKIES})


def test_ticking_without_eligibility_changes_nothing() -> None:
    flow = _flow({CONF_BRAND: "audi", CONF_SCAN_INTERVAL: 5})
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}) as create:
        asyncio.run(flow.async_step_init({CONF_SCAN_INTERVAL: 5, CONF_SWITCH_VWDE_ONLY: True}))
    flow.hass.config_entries.async_update_entry.assert_not_called()
    assert CONF_SWITCH_VWDE_ONLY not in create.call_args.kwargs["data"]


def test_confirm_step_aborts_when_not_eligible() -> None:
    flow = _flow({CONF_BRAND: "audi"})
    result = asyncio.run(flow.async_step_switch_vwde_only(None))
    assert result["type"] == "abort"
    assert result["reason"] == "vwde_only_switch_unavailable"


def test_confirm_step_shows_form_first_and_writes_nothing() -> None:
    flow = _flow(_portal_entry_data())
    result = asyncio.run(flow.async_step_switch_vwde_only(None))
    assert result["type"] == "form"
    assert result["step_id"] == "switch_vwde_only"
    flow.hass.config_entries.async_update_entry.assert_not_called()


# ── conversion result ─────────────────────────────────────────────────────────

def test_conversion_matches_new_website_entry_data() -> None:
    old = _portal_entry_data()
    new, _ = _convert(old)
    expected = VagConnectConfigFlow._build_website_entry_data(
        "u@example.org", {CONF_PASSWORD: "pw", CONF_SCAN_INTERVAL: 15}, COOKIES,
    )
    for key, value in expected.items():
        assert new[key] == value, key
    assert new[CONF_WEBSITE_AUTHPROXY] is True
    assert new[CONF_READ_ONLY] is True
    assert new[CONF_BRAND] == "volkswagen"
    assert new[CONF_WEBSITE_COOKIES] == COOKIES


def test_conversion_removes_portal_and_supplementary_flags() -> None:
    old = _portal_entry_data(**{
        CONF_SUPPLEMENTARY_EU_PORTAL: True,
        CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME: "p@example.org",
        CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD: "ppw",
        CONF_VWEU_DEVICE_GRANT: True,
        CONF_VWEU_TWOWAY_TOKENS: {"access_token": "t"},
        "dag_initial_tokens": {"strategy": "mbb"},
    })
    new, flow = _convert(old)
    for key in (
        CONF_SUPPLEMENTARY_AUTHPROXY,
        CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
        CONF_SUPPLEMENTARY_EU_PORTAL,
        CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
        CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
        CONF_VWEU_DEVICE_GRANT,
        CONF_VWEU_TWOWAY_TOKENS,
        "dag_initial_tokens",
    ):
        assert key not in new, key
    flow.hass.async_create_task.assert_called_once()  # reload scheduled


def test_conversion_keeps_credentials_and_picked_scan_interval() -> None:
    new, _ = _convert(_portal_entry_data(), {CONF_SCAN_INTERVAL: 30})
    assert new[CONF_USERNAME] == "u@example.org"
    assert new[CONF_PASSWORD] == "pw"
    assert new[CONF_SCAN_INTERVAL] == 30


def test_form_readonly_false_cannot_override_forced_readonly() -> None:
    new, _ = _convert(_portal_entry_data(), {CONF_READ_ONLY: False})
    assert new[CONF_READ_ONLY] is True


def test_no_switch_key_or_remove_keys_stored() -> None:
    new, _ = _convert(_portal_entry_data(), {"remove_supplementary_tibber": False})
    assert CONF_SWITCH_VWDE_ONLY not in new
    assert not any(k.startswith("remove_") for k in new)


# ── unique ids and the coordinator path ───────────────────────────────────────

def test_entity_unique_ids_are_vin_based_and_unchanged() -> None:
    vin = "WVWZZZ3CZ9E123456"
    before = vehicle_unique_id(vin, "odometer")
    new, _ = _convert(_portal_entry_data())
    # the id is built from the VIN and a key only; nothing in the entry data
    # takes part, so the converted data cannot move it.
    assert vehicle_unique_id(vin, "odometer") == before == f"{vin}_odometer"
    assert CONF_STRATEGY not in new


def _coord(data: dict[str, Any], client: Any) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = SimpleNamespace(data=data)
    c._cariad_client = client
    return c


def test_coordinator_selects_website_mode_for_converted_data() -> None:
    new, _ = _convert(_portal_entry_data())
    # setup arms the mode on exactly: brand == volkswagen and the flag truthy
    assert new[CONF_BRAND] == "volkswagen"
    assert new.get(CONF_WEBSITE_AUTHPROXY)
    coord = _coord(new, MagicMock(spec=[]))
    assert coord._primary_channel_name() == "website_authproxy"


def test_coordinator_persists_cookies_for_converted_entry() -> None:
    new, _ = _convert(_portal_entry_data())
    client = MagicMock()
    client._website_proxy = None
    client.get_website_proxy_cookies.return_value = [{"name": "fresh", "value": "y"}]
    coord = _coord(new, client)
    with patch("custom_components.vag_connect.coordinator._self_update_entry") as upd:
        coord._persist_website_cookies()
    upd.assert_called_once()
    assert upd.call_args.kwargs["data"][CONF_WEBSITE_COOKIES] == [{"name": "fresh", "value": "y"}]


def test_supplementary_flag_gone_so_no_second_vwde_channel() -> None:
    new, _ = _convert(_portal_entry_data())
    assert not new.get(CONF_SUPPLEMENTARY_AUTHPROXY)
