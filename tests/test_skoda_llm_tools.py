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


def _hass(service_result: dict | None = None) -> MagicMock:
    hass = MagicMock()
    hass.services.async_call = AsyncMock(return_value=service_result)
    return hass


def test_tool_classes_names_and_services() -> None:
    names = {c.name: c._service for c in vag_llm._TOOL_CLASSES}
    assert names == {
        "skoda_ask_assistant": "ask_assistant",
        "skoda_send_destination": "send_destination",
        "skoda_set_location_target_soc": "set_location_target_soc",
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
    assert out == {"success": True, "summary": "You'll make it.", "session_id": "s1"}


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
    assert out == {"success": True}


@pytest.mark.asyncio
async def test_custom_api_instance_exposes_all_tools() -> None:
    api = vag_llm.VagConnectLLMAPI(hass=MagicMock(), id=DOMAIN, name="VW Group Connect")
    inst = await api.async_get_api_instance(_ctx())
    assert {t.name for t in inst.tools} == {
        "skoda_ask_assistant",
        "skoda_send_destination",
        "skoda_set_location_target_soc",
    }
    expected = getattr(llm, "selector_serializer", None) or getattr(
        llm, "_selector_serializer", None
    )
    assert inst.custom_serializer == expected
    assert "skoda_ask_assistant" in inst.api_prompt


def test_platform_hook_is_inert_for_non_assist_api() -> None:
    assert vag_llm.async_get_tools(MagicMock(), _ctx(), "some_other_api") is None


def test_route_details_surfaced_and_registration_wired() -> None:
    src = (_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert '"route_details": result.get("routeDetails")' in src
    assert "_register_llm_api(hass)" in src
    assert "_unregister_llm_api(hass)" in src
    manifest = (_ROOT / "manifest.json").read_text(encoding="utf-8")
    assert '"llm"' in manifest  # after_dependencies
