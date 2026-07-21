"""v2.20.0 — additional MyŠkoda mysmob command routes (APK-grounded, LIVE-GATED).

Each route + JSON body asserted here is a literal string from the decoded
MyŠkoda 8.14.0 app (routes ``.../set-care-mode``, ``.../set-auto-unlock-plug``,
``.../active-ventilation/{start,stop}`` and the DTO fields ``chargingCareMode``,
``autoUnlockPlug``, ``durationInSeconds``). These commands are not yet confirmed
against a real Skoda Connect car — the tests pin the grounded wire shape so a
future live fix is a localised change.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient


def _client() -> SkodaClient:
    client = SkodaClient(MagicMock(), "u@t.de", "pw")
    client._post = AsyncMock()  # type: ignore[method-assign]
    client._put = AsyncMock()  # type: ignore[method-assign]
    return client


def _call(client: SkodaClient) -> tuple[str, dict]:
    """Return (url, json_body) of the single command call, whichever verb it
    used — charging-SETTINGS routes are PUT (v2.20.1 #866), actions are POST."""
    args = (
        client._put.call_args
        if client._put.call_args is not None
        else client._post.call_args
    )
    url = args.args[0]
    body = args.kwargs.get("json")
    return url, body


def test_battery_care_mode_on() -> None:
    client = _client()
    asyncio.run(client.command_set_battery_care("VIN1", True))
    url, body = _call(client)
    assert url.endswith("/api/v1/charging/VIN1/set-care-mode")
    # v2.20.1 (#866) — string enum, PUT (upstream myskoda), not a JSON bool.
    assert body == {"chargingCareMode": "ACTIVATED"}
    client._put.assert_awaited_once()


def test_battery_care_mode_off() -> None:
    client = _client()
    asyncio.run(client.command_set_battery_care("VIN1", False))
    _, body = _call(client)
    assert body == {"chargingCareMode": "DEACTIVATED"}


def test_auto_unlock_plug_passes_mode_through() -> None:
    client = _client()
    asyncio.run(client.command_set_auto_unlock_plug("VIN1", "PERMANENT"))
    url, body = _call(client)
    assert url.endswith("/api/v1/charging/VIN1/set-auto-unlock-plug")
    # mode is caller-supplied verbatim — we do NOT invent an enum value.
    assert body == {"autoUnlockPlug": "PERMANENT"}


def test_start_active_ventilation_default_duration() -> None:
    client = _client()
    asyncio.run(client.command_start_active_ventilation("VIN1"))
    url, body = _call(client)
    assert url.endswith("/api/v2/air-conditioning/VIN1/active-ventilation/start")
    assert body == {"durationInSeconds": 1800}  # default 30 min → seconds


def test_start_active_ventilation_custom_duration() -> None:
    client = _client()
    asyncio.run(client.command_start_active_ventilation("VIN1", duration_min=10))
    _, body = _call(client)
    assert body == {"durationInSeconds": 600}


def test_stop_active_ventilation() -> None:
    client = _client()
    asyncio.run(client.command_stop_active_ventilation("VIN1"))
    url, body = _call(client)
    assert url.endswith("/api/v2/air-conditioning/VIN1/active-ventilation/stop")
    assert body == {}
