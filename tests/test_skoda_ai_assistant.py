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
