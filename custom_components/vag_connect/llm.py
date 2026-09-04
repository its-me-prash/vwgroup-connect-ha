# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLM tools for VW Group Connect — expose Škoda's in-car AI "Laura" and the key
Škoda commands to ANY Home Assistant conversation agent.

One ``Tool`` per capability lands in an ``APIInstance.tools`` list, and every
agent — HA's built-in Assist in LLM mode, OpenAI, Anthropic/Claude, Google
Generative AI, Ollama — consumes that identical list through the shared
``conversation.ChatLog`` (each converts the tool's ``vol.Schema`` with the same
``voluptuous_openapi.convert(..., custom_serializer=llm.selector_serializer)``).
The dict a tool returns is fed back to the model as the tool result — which is
exactly what lets an agent read Laura's ``summary`` and then call
``vag_connect__skoda_send_destination`` with the chosen stop.

Two entry points share one ``_TOOL_CLASSES`` list:

* ``async_get_tools`` — the HA 2026.8+ ``llm`` platform contract. Folds our tools
  into the default "assist" API every agent already selects (zero user config).
  Guarded so it is simply inert on any HA build without the ``LLMTools`` contract.
* ``VagConnectLLMAPI`` — a custom ``llm.API`` registered via
  ``llm.async_register_api`` in ``__init__``. Works on every current HA version;
  the user selects "VW Group Connect" under the agent's *Control Home Assistant*
  option. This is the version-robust floor.

Read-only ``ask_assistant`` is advisory (route/charging planning + product Q&A);
it never actuates the car. The command tools are thin wrappers over the existing
services, so HA's own permission/exposure model still applies.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, llm

from .const import DOMAIN

# b13 — HA 2026.9 requires llm tool names to be prefixed with "{domain}__"
# (warns 2026.9, hard-breaks 2027.3 for the async_get_tools/Assist path). The
# tool names AND every in-prompt/in-description cross-reference use the prefixed
# form so the model's tool-chaining hints still match the registered names.
_PROMPT = (
    "This home has a Škoda vehicle. For Škoda EV route or charging planning, or "
    "MyŠkoda product questions, use vag_connect__skoda_ask_assistant (the in-car "
    "AI 'Laura') — it returns a text summary you can act on. If Laura or the user "
    "settles on a destination, push it to the car with "
    "vag_connect__skoda_send_destination. To set a location-specific charge "
    "target, use vag_connect__skoda_set_location_target_soc. Always pass the "
    "vehicle's VIN."
)


class _ServiceTool(llm.Tool):
    """Base tool that calls a vag_connect service (optionally returning its data)."""

    _service: str = ""
    _return_response: bool = False

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> dict[str, Any]:
        result = await hass.services.async_call(
            DOMAIN,
            self._service,
            dict(tool_input.tool_args),
            blocking=True,
            return_response=self._return_response,
            context=llm_context.context,
        )
        if self._return_response:
            return {"success": True, **(result or {})}
        return {"success": True}


class AskAssistantTool(_ServiceTool):
    """Laura — the MyŠkoda in-car AI assistant (read-only advisory)."""

    name = "vag_connect__skoda_ask_assistant"
    description = (
        "Ask the MyŠkoda in-car AI assistant 'Laura' about EV route/charging "
        "planning or Škoda product questions for one vehicle. Read-only advisory "
        "— it cannot control the car. Returns a text 'summary' you can act on "
        "(e.g. then call vag_connect__skoda_send_destination) plus a 'session_id'; "
        "pass that session_id back to continue the same conversation."
    )
    parameters = vol.Schema(
        {
            vol.Required("vin"): cv.string,
            vol.Required("prompt"): cv.string,
            vol.Optional("timezone"): cv.string,
            vol.Optional("session_id"): cv.string,
        }
    )
    _service = "ask_assistant"
    _return_response = True


class SendDestinationTool(_ServiceTool):
    """Push a navigation destination to the Škoda infotainment."""

    name = "vag_connect__skoda_send_destination"
    description = (
        "Send a navigation destination (coordinates + name) to the car's "
        "infotainment so it appears as the next destination."
    )
    parameters = vol.Schema(
        {
            vol.Required("vin"): cv.string,
            vol.Required("latitude"): vol.Coerce(float),
            vol.Required("longitude"): vol.Coerce(float),
            vol.Required("name"): cv.string,
        }
    )
    _service = "send_destination"


class SetLocationTargetSocTool(_ServiceTool):
    """Set the target state of charge for one charging profile (per-location)."""

    name = "vag_connect__skoda_set_location_target_soc"
    description = (
        "Set the target charge level (percent) for a specific charging profile — "
        "e.g. the profile active at the car's current location. profile_id comes "
        "from the charging-profiles sensor."
    )
    parameters = vol.Schema(
        {
            vol.Required("vin"): cv.string,
            vol.Required("profile_id"): vol.Coerce(int),
            vol.Required("target"): vol.All(vol.Coerce(int), vol.Range(20, 100)),
        }
    )
    _service = "set_location_target_soc"


_TOOL_CLASSES: list[type[_ServiceTool]] = [
    AskAssistantTool,
    SendDestinationTool,
    SetLocationTargetSocTool,
]


def _build_tools() -> list[llm.Tool]:
    return [cls() for cls in _TOOL_CLASSES]


def _selector_serializer() -> Any:
    """HA exposed ``selector_serializer`` publicly in 2026.x; older cores only
    have the private ``_selector_serializer``. Fall back across versions — the
    serializer is an OPTIONAL APIInstance field, so ``None`` is fine too."""
    return getattr(llm, "selector_serializer", None) or getattr(
        llm, "_selector_serializer", None
    )


class VagConnectLLMAPI(llm.API):
    """Custom LLM API (Path B) — selectable under any conversation agent's
    *Control Home Assistant* option. Works on all current HA versions."""

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt=_PROMPT,
            llm_context=llm_context,
            tools=_build_tools(),
            custom_serializer=_selector_serializer(),
        )


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: llm.LLMContext, api_id: str
) -> Any:
    """HA 2026.8+ ``llm`` platform hook (Path A): fold our tools into the default
    "assist" API. Fully guarded so it is inert on any HA build that lacks the
    ``LLMTools`` contract (older cores never call this)."""
    if api_id != llm.LLM_API_ASSIST:
        return None
    try:
        from homeassistant.components.llm import LLMTools  # noqa: PLC0415
    except ImportError:
        return None
    return LLMTools(tools=_build_tools(), prompt=_PROMPT)
