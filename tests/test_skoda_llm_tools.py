# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v3.0.0 — LLM tool surface (Laura + key commands) for HA conversation agents.

Every agent (built-in Assist LLM mode, OpenAI, Anthropic, Google, Ollama)
consumes the same ``APIInstance.tools`` list via ``homeassistant.helpers.llm``.
These tests pin the tool contract + the two registration paths so a future HA
refactor or a careless rename is caught in CI, not in a tester's house.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# The llm helper (and our llm.py) pull in HA's intent stack, which needs `hassil`;
# a minimal HA test env (older CI matrix) may not have it. Skip cleanly rather
# than erroring the whole collection.
pytest.importorskip("homeassistant.helpers.llm")

from homeassistant.core import Context  # noqa: E402
from homeassistant.helpers import llm  # noqa: E402

from custom_components.vag_connect import llm as vag_llm  # noqa: E402
from custom_components.vag_connect.const import DOMAIN  # noqa: E402

VIN = "TMBJJ7NX1M0000005"
_ROOT = Path(__file__).resolve().parents[1] / "custom_components/vag_connect"


def _ctx() -> llm.LLMContext:
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


def _payload(out):
    """A tool's data, whether or not the installed HA wraps it in a ToolResult.

    b24 — HA 2026.10 introduced ``llm.ToolResult``; builds before it expect the
    bare dict. Asserting on the unwrapped payload keeps these tests honest on
    both, instead of passing locally and failing on whichever version CI
    happens to install.
    """
    return getattr(out, "data", out)


def _hass(service_result: dict | None = None) -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock(return_value=service_result)
    return hass


def test_tool_classes_names_and_services() -> None:
    names = {c.name: c._service for c in vag_llm._TOOL_CLASSES}
    assert names == {
        "vag_connect__skoda_ask_assistant": "ask_assistant",
        "vag_connect__skoda_send_destination": "send_destination",
        "vag_connect__skoda_set_location_target_soc": "set_location_target_soc",
    }
    # only the advisory tool asks for a response payload
    ask = vag_llm.AskAssistantTool
    assert ask._return_response is True
    assert vag_llm.SendDestinationTool._return_response is False


def test_ask_tool_schema_requires_vin_and_prompt() -> None:
    schema = vag_llm.AskAssistantTool().parameters
    schema({"vin": VIN, "prompt": "Reicht meine Ladung bis München?"})
    with pytest.raises(Exception):
        schema({"vin": VIN})  # prompt missing


@pytest.mark.asyncio
async def test_ask_tool_dispatches_service_and_merges_response() -> None:
    hass = _hass({"summary": "You'll make it.", "session_id": "s1"})
    tool = vag_llm.AskAssistantTool()
    out = await tool.async_call(
        hass,
        llm.ToolInput(tool_name=tool.name, tool_args={"vin": VIN, "prompt": "hi"}),
        _ctx(),
    )
    hass.services.async_call.assert_awaited_once()
    args, kwargs = hass.services.async_call.call_args
    assert args[0] == DOMAIN and args[1] == "ask_assistant"
    assert args[2] == {"vin": VIN, "prompt": "hi"}
    assert kwargs["return_response"] is True and kwargs["blocking"] is True
    assert _payload(out) == {
        "success": True, "summary": "You'll make it.", "session_id": "s1",
    }


@pytest.mark.asyncio
async def test_command_tool_does_not_request_response() -> None:
    hass = _hass(None)
    tool = vag_llm.SendDestinationTool()
    out = await tool.async_call(
        hass,
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"vin": VIN, "latitude": 48.1, "longitude": 11.5, "name": "X"},
        ),
        _ctx(),
    )
    _, kwargs = hass.services.async_call.call_args
    assert kwargs["return_response"] is False
    assert _payload(out) == {"success": True}


@pytest.mark.asyncio
async def test_custom_api_instance_exposes_all_tools() -> None:
    api = vag_llm.VagConnectLLMAPI(hass=MagicMock(), id=DOMAIN, name="VW Group Connect")
    inst = await api.async_get_api_instance(_ctx())
    assert {t.name for t in inst.tools} == {
        "vag_connect__skoda_ask_assistant",
        "vag_connect__skoda_send_destination",
        "vag_connect__skoda_set_location_target_soc",
    }
    expected = getattr(llm, "selector_serializer", None) or getattr(
        llm, "_selector_serializer", None
    )
    assert inst.custom_serializer == expected
    assert "vag_connect__skoda_ask_assistant" in inst.api_prompt


def test_platform_hook_is_inert_for_non_assist_api() -> None:
    assert vag_llm.async_get_tools(MagicMock(), _ctx(), "some_other_api") is None


def test_route_details_surfaced_and_registration_wired() -> None:
    src = (_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert '"route_details": result.get("routeDetails")' in src
    assert "_register_llm_api(hass)" in src
    assert "_unregister_llm_api(hass)" in src
    manifest = (_ROOT / "manifest.json").read_text(encoding="utf-8")
    assert '"llm"' in manifest  # after_dependencies


# ── b24: the two deprecations HA 2026.10 reports through its frame helper ────


def test_every_tool_names_the_integration_that_provides_it() -> None:
    """HA 2026.10 reports an LLM tool with no integration and breaks it in 2027.10.

    It is also why ``APIInstance.__post_init__`` reached for HA's frame helper,
    which a MagicMock hass has never set up — so this is the assertion that
    keeps that failure from coming back.
    """
    for cls in vag_llm._TOOL_CLASSES:
        assert cls().integration == DOMAIN, f"{cls.__name__} does not name its integration"


def test_the_api_instance_hands_over_tools_that_all_name_it() -> None:
    """The same thing where HA actually looks at it."""
    for tool in vag_llm._build_tools():
        assert tool.integration == DOMAIN


def test_a_payload_is_wrapped_when_the_installed_ha_has_toolresult(monkeypatch) -> None:
    """The 2026.10+ path, proven without needing 2026.10 installed."""
    class _Stub:
        def __init__(self, data):
            self.data = data

    monkeypatch.setattr(llm, "ToolResult", _Stub, raising=False)
    out = vag_llm._tool_result({"success": True})
    assert isinstance(out, _Stub)
    assert out.data == {"success": True}


def test_a_payload_stays_a_bare_dict_on_builds_without_toolresult(monkeypatch) -> None:
    """The floor this module exists to hold: older HA gets what it expects."""
    monkeypatch.delattr(llm, "ToolResult", raising=False)
    assert vag_llm._tool_result({"success": True}) == {"success": True}


@pytest.mark.asyncio
async def test_the_wrapping_reaches_what_a_tool_actually_returns(monkeypatch) -> None:
    """Not just the helper — the value the agent receives."""
    class _Stub:
        def __init__(self, data):
            self.data = data

    monkeypatch.setattr(llm, "ToolResult", _Stub, raising=False)
    hass = _hass({"summary": "ok"})
    tool = vag_llm.AskAssistantTool()
    out = await tool.async_call(
        hass,
        llm.ToolInput(tool_name=tool.name, tool_args={"vin": VIN, "prompt": "hi"}),
        _ctx(),
    )
    assert isinstance(out, _Stub)
    assert out.data == {"success": True, "summary": "ok"}

