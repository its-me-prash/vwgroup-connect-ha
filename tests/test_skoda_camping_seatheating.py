# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""2.31.0 wave — MyŠkoda camping + seat-heating commands (APK-grounded, LIVE-GATED).

Every route + JSON body asserted here is a literal from the decoded MyŠkoda
8.15.0 app (androguard/apktool): AirConditioningApi ``startCamping``
(POST ``camping/start``, @Body ``AirConditioningTargetTemperatureDto`` =
{temperatureValue, unitInCar}), ``stopCamping`` (POST ``camping/stop``, no body),
``setAirConditioningSeatsHeating`` (POST ``settings/seats-heating``, @Body
``SeatHeatingSettingsDto`` = nullable Booleans frontLeft/frontRight/rearLeft/
rearRight). Not yet confirmed against a real Škoda; these pin the wire shape so
a future live fix is a localised change.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient


def _client() -> SkodaClient:
    client = SkodaClient(MagicMock(), "u@t.de", "pw")
    client._post = AsyncMock()  # type: ignore[method-assign]
    return client


def _post(client: SkodaClient) -> tuple[str, dict]:
    args = client._post.call_args
    return args.args[0], args.kwargs.get("json")


def test_start_camping_carries_target_temperature() -> None:
    client = _client()
    asyncio.run(client.command_start_camping("VIN1", 19.5))
    url, body = _post(client)
    assert url.endswith("/api/v2/air-conditioning/VIN1/camping/start")
    assert body == {"temperatureValue": 19.5, "unitInCar": "CELSIUS"}


def test_start_camping_defaults_to_20c() -> None:
    client = _client()
    asyncio.run(client.command_start_camping("VIN1"))
    _, body = _post(client)
    assert body == {"temperatureValue": 20.0, "unitInCar": "CELSIUS"}


def test_stop_camping_has_no_body() -> None:
    client = _client()
    asyncio.run(client.command_stop_camping("VIN1"))
    url, body = _post(client)
    assert url.endswith("/api/v2/air-conditioning/VIN1/camping/stop")
    assert body == {}


def test_seat_heating_sends_only_the_seats_given() -> None:
    client = _client()
    asyncio.run(client.command_set_seat_heating("VIN1", front_left=True))
    url, body = _post(client)
    assert url.endswith("/api/v2/air-conditioning/VIN1/settings/seats-heating")
    # only the requested seat is present — the others are left untouched
    assert body == {"frontLeft": True}


def test_seat_heating_all_four_seats() -> None:
    client = _client()
    asyncio.run(client.command_set_seat_heating(
        "VIN1", front_left=True, front_right=False,
        rear_left=True, rear_right=False,
    ))
    _, body = _post(client)
    assert body == {
        "frontLeft": True, "frontRight": False,
        "rearLeft": True, "rearRight": False,
    }


def test_seat_heating_none_sends_empty_body() -> None:
    client = _client()
    asyncio.run(client.command_set_seat_heating("VIN1"))
    _, body = _post(client)
    assert body == {}
