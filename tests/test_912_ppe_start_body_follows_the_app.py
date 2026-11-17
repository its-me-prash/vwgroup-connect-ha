# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#912: the PPE climate start with settings builds on the car's own settings.

#912/#1403: a PPE start that carries NO settings now goes out without a request
body (see test_912_ppe_start_without_body.py); the tests below cover the body
that is still built, for the start that carries settings (the rich start), and
the builder itself.

Earlier text of this file, still true for that builder:

The Audi app starts climatisation with the same body it uses to save the
climatisation settings: the car's CURRENT settings, target temperature and its
unit included (myAudi 5.9.0, ``SetClimatisationSettings$ActionSerializer``,
twelve keys). With the PPE option on, the integration instead sent three keys,
two of them forced to true whatever the car's settings were. An A6 e-tron and
a Q6 e-tron accepted that request and then refused it at the car.

With the PPE option on the start body is now built from the settings the car
reports. Nothing is forced, and a key the car does not report is not sent.
Without the option nothing changes.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError

_FULL = {
    "targetTemperature_C": 22.5,
    "climatisationWithoutExternalPower": False,
    "climatizationAtUnlock": False,
    "windowHeatingEnabled": False,
    "zoneFrontLeftEnabled": True,
    "zoneFrontRightEnabled": False,
    "zoneRearLeftEnabled": False,
    "zoneRearRightEnabled": False,
    "climatisationMode": "economy",
    "heaterSource": "electric",
    "carCapturedTimestamp": "2026-01-01T00:00:00Z",
}


def _status(settings: Any) -> dict[str, Any]:
    return {"climatisation": {"climatisationSettings": {"value": settings}}}


def _client(status: Any = None, *, get_error: Exception | None = None) -> VWEUClient:
    client = VWEUClient.__new__(VWEUClient)
    client._tokens = None
    client._vehicle_bases = {}
    client._get = AsyncMock(side_effect=get_error) if get_error else AsyncMock(return_value=status)
    client._post_command_with_fallback_paths = AsyncMock(return_value=None)
    client._post = AsyncMock(return_value=None)
    client._await_bff_command = AsyncMock(return_value=None)
    return client


def _basic_body(client: VWEUClient) -> dict[str, Any] | None:
    # #912/#1403: the basic PPE start no longer builds a body. What is tested
    # here is the builder the rich start still lays the caller's choices over.
    return asyncio.run(client._climate_start_body_from_settings("VINX"))


def _rich_body(client: VWEUClient, **kwargs: Any) -> dict[str, Any]:
    asyncio.run(client.command_start_climate_control("VINX", ppe_mode=True, **kwargs))
    return client._post.await_args.kwargs["json"]


# ── the basic start ──────────────────────────────────────────────────────────


def test_the_body_is_the_cars_own_settings() -> None:
    assert _basic_body(_client(_status(_FULL))) == {
        "targetTemperature": 22.5,
        "targetTemperatureUnit": "celsius",
        "climatisationWithoutExternalPower": False,
        "climatizationAtUnlock": False,
        "windowHeatingEnabled": False,
        "zoneFrontLeftEnabled": True,
        "zoneFrontRightEnabled": False,
        "zoneRearLeftEnabled": False,
        "zoneRearRightEnabled": False,
        "climatisationMode": "economy",
    }


def test_nothing_is_forced_to_true() -> None:
    body = _basic_body(_client(_status(_FULL)))
    assert body.get("windowHeatingEnabled") is False
    assert body.get("climatisationWithoutExternalPower") is False


def test_a_key_the_car_does_not_report_is_not_sent() -> None:
    body = _basic_body(_client(_status({"climatisationMode": "comfort", "windowHeatingEnabled": True})))
    assert body == {"climatisationMode": "comfort", "windowHeatingEnabled": True}


def test_status_only_keys_are_not_sent() -> None:
    # The start body of the app has no heater source and no capture time.
    body = _basic_body(_client(_status(_FULL)))
    assert "heaterSource" not in body
    assert "carCapturedTimestamp" not in body
    assert "targetTemperature_C" not in body


def test_the_mode_falls_back_to_comfort_when_the_car_reports_none() -> None:
    body = _basic_body(_client(_status({"windowHeatingEnabled": False})))
    assert body == {"windowHeatingEnabled": False, "climatisationMode": "comfort"}


def test_the_two_nested_settings_are_passed_on_when_reported() -> None:
    nested = {"duration_min": 30, "startMode": "heating"}
    body = _basic_body(_client(_status({
        "climatisationMode": "comfort",
        "activeVentilationSettings": dict(nested),
        "auxiliaryHeatingSettings": dict(nested),
    })))
    assert body.get("activeVentilationSettings") == nested
    assert body.get("auxiliaryHeatingSettings") == nested


def test_a_value_of_the_wrong_type_is_left_out() -> None:
    body = _basic_body(_client(_status({
        "climatisationMode": "comfort",
        "windowHeatingEnabled": "yes",        # not a boolean
        "targetTemperature_C": True,          # a boolean is not a temperature
        "zoneFrontLeftEnabled": None,
    })))
    assert body == {"climatisationMode": "comfort"}


def test_the_settings_are_read_from_the_climatisation_job() -> None:
    client = _client(_status(_FULL))
    _basic_body(client)
    args, kwargs = client._get.await_args
    assert args[0].endswith("/vehicle/v1/vehicles/VINX/selectivestatus")
    assert kwargs["params"] == {"jobs": "climatisation"}


@pytest.mark.parametrize(
    "client",
    [
        _client(get_error=APIError(502, "u", "bad gateway")),
        _client({}),
        _client(_status(None)),
        _client(_status({})),
        _client({"climatisation": {"climatisationSettings": {"error": {"code": 4111}}}}),
        _client("not a document"),
    ],
    ids=["read fails", "empty answer", "no value", "empty settings", "error block", "no document"],
)
def test_without_readable_settings_the_builder_returns_none(client: VWEUClient) -> None:
    # The caller (the rich start) then falls back to its earlier PPE rule.
    assert _basic_body(client) is None


def test_without_the_option_nothing_is_read_and_the_body_is_unchanged() -> None:
    client = _client(_status(_FULL))
    asyncio.run(client.command_start_climate("VINX"))
    client._get.assert_not_awaited()
    assert client._post_command_with_fallback_paths.await_args.kwargs["primary_payload"] == {
        "targetTemperature": 21.0,
        "targetTemperatureUnit": "celsius",
        "climatisationWithoutExternalPower": True,
        "windowHeatingEnabled": True,
    }


# ── the start with options (service call) ────────────────────────────────────


def test_rich_start_begins_with_the_cars_settings() -> None:
    # One setting is given: with none at all a PPE start goes out without a body.
    body = _rich_body(_client(_status(_FULL)), glass_heating=False)
    assert body.get("climatisationMode") == "economy"
    assert body.get("zoneFrontLeftEnabled") is True
    assert body.get("targetTemperature") == 22.5 and body.get("targetTemperatureUnit") == "celsius"


def test_rich_start_applies_what_the_caller_asked_for() -> None:
    body = _rich_body(
        _client(_status(_FULL)),
        temp_c=19.0, glass_heating=True, seat_fr=True, climatisation_at_unlock=True, climatisation_mode="comfort",
    )
    assert body.get("targetTemperature") == 19.0
    assert body.get("windowHeatingEnabled") is True
    assert body.get("zoneFrontRightEnabled") is True
    assert body.get("zoneFrontLeftEnabled") is False      # a seat choice sets all four zones, as before
    assert body.get("climatizationAtUnlock") is True
    assert body.get("climatisationMode") == "comfort"


def test_rich_start_sends_no_temperature_to_a_car_that_reports_none() -> None:
    settings = {k: v for k, v in _FULL.items() if k != "targetTemperature_C"}
    body = _rich_body(_client(_status(settings)), temp_c=19.0)
    assert "targetTemperature" not in body
    assert "targetTemperatureUnit" not in body


def test_rich_start_without_readable_settings_behaves_as_before() -> None:
    # The earlier PPE rule: the temperature is dropped and the mode is comfort.
    body = _rich_body(_client(get_error=APIError(502, "u", "bad gateway")), temp_c=19.0, glass_heating=True)
    assert body == {"windowHeatingEnabled": True, "climatisationMode": "comfort"}


def test_rich_start_without_the_option_reads_nothing() -> None:
    client = _client(_status(_FULL))
    asyncio.run(client.command_start_climate_control("VINX", temp_c=20.0))
    client._get.assert_not_awaited()
    assert client._post.await_args.kwargs["json"] == {"targetTemperature": 20.0, "targetTemperatureUnit": "celsius"}
