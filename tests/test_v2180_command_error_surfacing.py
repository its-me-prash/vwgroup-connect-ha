# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.0 (#659) — a failing command must not hand the user a traceback.

The dispatcher classified the failure, logged it, and then re-raised the raw
APIError. Home Assistant doesn't know that type, so pressing the wake button
produced "Unexpected exception" plus a full Python traceback in the log and a
generic red error in the UI — the reason we'd just worked out was thrown away.

Straight from a reporter's log (2025 VW Atlas, combustion, Canada):

    command_wake(***) classified as not_entitled
    API error 403 ... /ev/v1/vehicle/{id}/wakeup:
      {"error": {"errorCode": "USER_NOT_AUTHORIZED", ...}}
    [websocket_api] Unexpected exception
    Traceback (most recent call last): ...

Our own pre-flight guards already raise ServiceValidationError, which renders
cleanly — those must pass through untouched rather than get re-wrapped.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

VIN = "WVGZZZ1KZAW123456"


def _coord(raises: BaseException):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.command_wake = AsyncMock(side_effect=raises)
    c._cariad_client = client
    c.async_request_refresh = AsyncMock()
    c.record_command_success = MagicMock()
    c.record_command_failure = MagicMock()
    return c


async def _dispatch(coord):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    await VagConnectCoordinator._dispatch_cmd_locked(coord, VIN, "command_wake")


@pytest.mark.asyncio
async def test_api_error_reaches_the_user_as_a_ha_error() -> None:
    from custom_components.vag_connect.cariad.exceptions import APIError

    c = _coord(APIError(403, "https://x/ev/v1/vehicle/y/wakeup", '{"errorCode":"USER_NOT_AUTHORIZED"}'))
    with pytest.raises(HomeAssistantError):
        await _dispatch(c)


@pytest.mark.asyncio
async def test_the_backend_reason_survives_into_the_message() -> None:
    # A bare HomeAssistantError with no text would trade a traceback for a
    # shrug. The user should still learn what the car said.
    from custom_components.vag_connect.cariad.exceptions import APIError

    c = _coord(APIError(403, "https://x/ev/v1/vehicle/y/wakeup", '{"errorCode":"USER_NOT_AUTHORIZED"}'))
    with pytest.raises(HomeAssistantError) as ei:
        await _dispatch(c)
    assert "USER_NOT_AUTHORIZED" in str(ei.value)


@pytest.mark.asyncio
async def test_the_failure_is_still_classified_and_recorded() -> None:
    # Surfacing must not cost us the bookkeeping the capability tracker needs.
    from custom_components.vag_connect.cariad.exceptions import APIError

    c = _coord(APIError(403, "https://x/y", '{"errorCode":"USER_NOT_AUTHORIZED"}'))
    with pytest.raises(HomeAssistantError):
        await _dispatch(c)
    c.record_command_failure.assert_called_once()


@pytest.mark.asyncio
async def test_service_validation_error_passes_through_unwrapped() -> None:
    # Our own guards already render cleanly and carry a translation key —
    # re-wrapping them would replace a translated message with a raw string.
    c = _coord(ServiceValidationError("spin required"))
    with pytest.raises(ServiceValidationError):
        await _dispatch(c)


@pytest.mark.asyncio
async def test_success_path_untouched() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = _coord(None)
    c._cariad_client.command_wake = AsyncMock(return_value=None)
    await VagConnectCoordinator._dispatch_cmd_locked(c, VIN, "command_wake")
    c.record_command_success.assert_called_once()
    # b7 (P1-1 / P2-twin) — the post-command refresh moved OUT of the inner dispatch
    # to the caller (_cariad_cmd), outside the command lock + error scope, so a
    # refresh/portal error can't masquerade as a command failure. The inner dispatch
    # no longer refreshes; the caller-level refresh is covered in test_entities
    # (test_set_departure_timer_calls_cariad).
    c.async_request_refresh.assert_not_awaited()
