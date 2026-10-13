"""Companion setup, untrusted XML, relay app keys and diagnostic privacy."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.companion.relay import (
    AGENT_TOKEN_HEADER,
    ensure_relay_view,
    handle_agent_request,
    register_relay,
)
from custom_components.vag_connect.companion.screen import parse_ui_dump
from custom_components.vag_connect.config_flow import VagConnectConfigFlow
from custom_components.vag_connect.const import (
    CONF_ADB_HOST,
    CONF_BRAND,
    CONF_COMPANION_ADDON_TOKEN,
    CONF_COMPANION_AGENT_TOKEN,
    CONF_COMPANION_USE_ADDON,
    CONF_COMPANION_USE_RELAY,
    CONF_STRATEGY,
    CONF_VIN,
    STRATEGY_COMPANION_ADB,
)
from custom_components.vag_connect.diagnostics import (
    _REDACT_KEYS,
    async_get_config_entry_diagnostics,
)


def _flow():
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow._companion_probe = AsyncMock(return_value=(True, ""))
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


def _input(**extra):
    return {CONF_BRAND: "volkswagen", CONF_VIN: "WVGZZZ1KZAW123456", **extra}


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["", "   "])
async def test_new_addon_setup_requires_token_before_probe(token):
    flow = _flow()
    result = await flow.async_step_companion_adb(_input(**{
        CONF_ADB_HOST: "192.0.2.1", CONF_COMPANION_USE_ADDON: True,
        CONF_COMPANION_ADDON_TOKEN: token,
    }))
    assert result["errors"] == {"base": "companion_addon_token_required"}
    flow._companion_probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_addon_token_is_forwarded_to_probe():
    flow = _flow()
    result = await flow.async_step_companion_adb(_input(**{
        CONF_ADB_HOST: "192.0.2.1", CONF_COMPANION_USE_ADDON: True,
        CONF_COMPANION_ADDON_TOKEN: "addon-secret",
    }))
    assert result["type"] == "create_entry"
    assert flow._companion_probe.call_args.kwargs["addon_token"] == "addon-secret"


@pytest.mark.asyncio
async def test_agent_token_default_is_random_and_stable_within_flow():
    def default(result):
        return next(key.default() for key in result["data_schema"].schema
                    if key.schema == CONF_COMPANION_AGENT_TOKEN)

    flow = _flow()
    first = default(await flow.async_step_companion_adb())
    assert len(first) >= 32
    assert len(set(first)) >= 16
    assert default(await flow.async_step_companion_adb()) == first
    assert default(await _flow().async_step_companion_adb()) != first


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["a" * 32, "ab" * 32, "abcd" * 16,
                                    "a" * 100 + "bcdefghijklmnopq"])
async def test_low_entropy_agent_token_is_refused(token):
    flow = _flow()
    result = await flow.async_step_companion_adb(_input(**{
        CONF_COMPANION_USE_RELAY: True, CONF_COMPANION_AGENT_TOKEN: token,
    }))
    assert result["errors"] == {"base": "companion_agent_token_weak"}
    flow._companion_probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_generated_agent_token_can_create_entry_without_probe():
    flow = _flow()
    form = await flow.async_step_companion_adb()
    token = next(key.default() for key in form["data_schema"].schema
                 if key.schema == CONF_COMPANION_AGENT_TOKEN)
    result = await flow.async_step_companion_adb(_input(**{
        CONF_COMPANION_USE_RELAY: True, CONF_COMPANION_AGENT_TOKEN: token,
    }))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_COMPANION_AGENT_TOKEN] == token
    flow._companion_probe.assert_not_awaited()


@pytest.mark.parametrize("declaration", [
    '<!DOCTYPE hierarchy [<!ENTITY place "private place">]>',
    '<!DOCTYPE hierarchy SYSTEM "file:///etc/passwd">',
    '<!ENTITY place "private place">',
])
def test_xml_declarations_are_rejected_before_parsing(declaration):
    xml = declaration + '<hierarchy><node text="&place;"/></hierarchy>'
    with patch("custom_components.vag_connect.companion.screen.ET.fromstring") as parse:
        assert parse_ui_dump(xml) == []
    parse.assert_not_called()


def test_normal_dump_still_parses():
    assert parse_ui_dump('<hierarchy><node text="80%"/></hierarchy>')[0].text == "80%"


@pytest.mark.asyncio
@pytest.mark.parametrize("loaded", [True, False])
async def test_full_diagnostics_redacts_companion_tokens_and_hosts(loaded):
    assert {CONF_COMPANION_AGENT_TOKEN, CONF_COMPANION_ADDON_TOKEN,
            CONF_ADB_HOST} <= _REDACT_KEYS
    secrets = {
        CONF_COMPANION_AGENT_TOKEN: "synthetic-agent-secret",
        CONF_COMPANION_ADDON_TOKEN: "synthetic-addon-secret",
        CONF_ADB_HOST: "192.0.2.10",
    }
    options = {key: value + "-option" for key, value in secrets.items()}
    coord = SimpleNamespace(
        vehicles={}, last_update_success=True, cloud_push_active=False,
        push_states={}, push_last_errors={}, is_active=True,
    ) if loaded else None
    entry = SimpleNamespace(
        data={CONF_STRATEGY: STRATEGY_COMPANION_ADB, **secrets},
        options=options, runtime_data=coord,
    )
    result = await async_get_config_entry_diagnostics(MagicMock(), entry)
    encoded = json.dumps(result)
    for key in secrets:
        assert result["config"][key] == "**REDACTED**"
        assert result["options"][key] == "**REDACTED**"
        assert secrets[key] not in encoded
        assert options[key] not in encoded


_CHARGING_LOCATION_LABELS = {
    **{f"charging_location_{n}_name": f"Synthetic place {n}" for n in range(1, 6)},
    "charging_location_current": "Synthetic place 1",
}


@pytest.mark.asyncio
async def test_diagnostics_redacts_charging_location_labels():
    """A charging location's label names where the car charges, so it never
    reaches a diagnostics file people attach to public issues."""
    assert set(_CHARGING_LOCATION_LABELS) <= _REDACT_KEYS
    coord = SimpleNamespace(
        vehicles={"WVGZZZ1KZAW123456": {"battery_soc": 70, **_CHARGING_LOCATION_LABELS}},
        last_update_success=True, cloud_push_active=False,
        push_states={}, push_last_errors={}, is_active=True,
    )
    entry = SimpleNamespace(
        data={CONF_STRATEGY: STRATEGY_COMPANION_ADB}, options={}, runtime_data=coord,
    )
    encoded = json.dumps(await async_get_config_entry_diagnostics(MagicMock(), entry))
    assert "Synthetic place" not in encoded


@pytest.mark.asyncio
async def test_register_and_handle_never_log_agent_token(caplog):
    caplog.set_level(logging.DEBUG)
    hass = SimpleNamespace(data={}, http=MagicMock())
    token = "synthetic-private-agent-token-0123456789"
    register_relay(hass, "entry", token, hold_s=0.001)
    request = SimpleNamespace(headers={AGENT_TOKEN_HEADER: token}, json=AsyncMock(return_value={}))
    assert (await handle_agent_request(hass, request))[0] == 200
    request.json.side_effect = ValueError(token)
    assert (await handle_agent_request(hass, request))[0] == 400
    register_relay(hass, "duplicate", token, hold_s=0.001)
    assert (await handle_agent_request(hass, request))[0] == 404
    assert token not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("modern", [True, False])
async def test_relay_view_uses_supported_hass_app_key(monkeypatch, modern):
    from homeassistant.components.http import const

    key = object() if modern else "hass"
    if modern:
        monkeypatch.setattr(const, "KEY_HASS", key)
    else:
        monkeypatch.delattr(const, "KEY_HASS")
    hass = SimpleNamespace(data={}, http=MagicMock())
    ensure_relay_view(hass)
    view = hass.http.register_view.call_args.args[0]()
    request = SimpleNamespace(app={key: hass})
    with patch("custom_components.vag_connect.companion.relay.handle_agent_request",
               new=AsyncMock(return_value=(200, {"command": None}))) as handle:
        await view.post(request)
    handle.assert_awaited_once_with(hass, request)
