# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MyŠkoda AI assistant "Laura" service (APK-grounded, 8.15.0, LIVE-GATED).

POST api/v2/ai-assistant/ask, @Body AIAssistantRequestDto (all optional:
userInput/userTimezone/vin/sessionId/routePlanner) → AIAssistantResponseDto
{type, summary, sessionId, routeDetails}. Read-only advisory — no vehicle
commands in the whole AiAssistantApi package.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient

VIN = "TMBJJ7NX1M0000005"
_ROOT = Path(__file__).resolve().parents[1] / "custom_components/vag_connect"


def _client() -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._post = AsyncMock(return_value={  # type: ignore[method-assign]
        "type": "ROUTE", "summary": "You'll make it with 20% to spare.",
        "sessionId": "sess-1", "routeDetails": {},
    })
    return c


def test_ask_builds_minimal_body() -> None:
    c = _client()
    out = asyncio.run(c.ask_assistant(VIN, "Reicht meine Ladung bis München?"))
    url = c._post.call_args.args[0]
    body = c._post.call_args.kwargs["json"]
    assert url.endswith("/api/v2/ai-assistant/ask")
    assert body == {"userInput": "Reicht meine Ladung bis München?", "vin": VIN}
    assert out["summary"].startswith("You'll make it")


def test_ask_passes_timezone_and_session() -> None:
    c = _client()
    asyncio.run(c.ask_assistant(
        VIN, "next stop?", user_timezone="Europe/Zurich", session_id="sess-1",
    ))
    body = c._post.call_args.kwargs["json"]
    assert body["userTimezone"] == "Europe/Zurich"
    assert body["sessionId"] == "sess-1"


@pytest.mark.asyncio
async def test_coordinator_falls_back_to_ha_timezone() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.config.time_zone = "Europe/Berlin"
    coord._cariad_client = MagicMock()
    coord._cariad_client.ask_assistant = AsyncMock(return_value={"summary": "ok"})
    await coord.async_ask_assistant(VIN, "hi")
    _, kwargs = coord._cariad_client.ask_assistant.call_args
    assert kwargs["user_timezone"] == "Europe/Berlin"


@pytest.mark.asyncio
async def test_coordinator_rejects_non_skoda_brand() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._cariad_client = object()  # no ask_assistant attr
    with pytest.raises(AttributeError, match="Škoda-only"):
        await coord.async_ask_assistant(VIN, "hi")


def test_service_registered_and_in_yaml() -> None:
    import yaml

    src = (_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert '"ask_assistant"' in src
    assert "SupportsResponse" in src
    doc = yaml.safe_load((_ROOT / "services.yaml").read_text(encoding="utf-8"))
    assert "ask_assistant" in doc
    assert doc["ask_assistant"]["fields"]["prompt"]["required"] is True


def _register_and_capture(monkeypatch: pytest.MonkeyPatch, coord: object) -> dict:
    """Register all services against a mock hass, return {name: handler}, and
    point _get_coordinator at the given stub coordinator."""
    import custom_components.vag_connect as vag

    handlers: dict = {}
    hass = MagicMock()
    hass.services.async_register = (
        lambda domain, name, handler, *a, **k: handlers.__setitem__(name, handler)
    )
    hass.services.has_service = MagicMock(return_value=False)
    vag._register_services(hass)
    monkeypatch.setattr(vag, "_get_coordinator", lambda _h, _vin: coord)
    return handlers


@pytest.mark.asyncio
async def test_ask_assistant_handler_remaps_wire_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.0.0 behavioural cover: the handler remaps sessionId->session_id and
    surfaces routeDetails->route_details (not just a source grep)."""
    coord = MagicMock()
    coord.is_read_only = MagicMock(return_value=False)
    coord.async_ask_assistant = AsyncMock(return_value={
        "type": "ROUTE", "summary": "You'll make it with 20% to spare.",
        "sessionId": "sess-9", "routeDetails": {"chargingStops": 1},
    })
    handlers = _register_and_capture(monkeypatch, coord)

    call = MagicMock()
    call.data = {"vin": VIN, "prompt": "Reicht die Ladung bis München?"}
    resp = await handlers["ask_assistant"](call)

    assert resp == {
        "summary": "You'll make it with 20% to spare.",
        "type": "ROUTE",
        "session_id": "sess-9",
        "route_details": {"chargingStops": 1},
    }
    # timezone falls back to "" and session_id defaults to None when omitted
    _, kwargs = coord.async_ask_assistant.call_args
    assert kwargs["session_id"] is None


@pytest.mark.asyncio
async def test_ask_assistant_handler_translates_attributeerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-Škoda coordinator raises AttributeError; the handler must convert it
    to a user-facing ServiceValidationError, not leak the raw error."""
    from homeassistant.exceptions import ServiceValidationError

    coord = MagicMock()
    coord.is_read_only = MagicMock(return_value=False)
    coord.async_ask_assistant = AsyncMock(side_effect=AttributeError("Škoda-only"))
    handlers = _register_and_capture(monkeypatch, coord)

    call = MagicMock()
    call.data = {"vin": VIN, "prompt": "x"}
    with pytest.raises(ServiceValidationError):
        await handlers["ask_assistant"](call)
