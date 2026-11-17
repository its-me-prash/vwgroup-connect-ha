# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#912 / #1403: a PPE Audi's climatisation start.

Two A6 e-tron (PPE) on 5.4.0, 17.11.2026, start with no setting given:

* a car that reports its climatisation settings got them back as the body
  (target temperature, unit, at-unlock, four zones, mode) -> status
  ``successful``, the climatisation ran (confirmed in the app);
* a car that reports none got ``{climatisationMode: comfort}`` -> status
  ``in_progress``, the car did not start. Earlier the three-key fallback body
  failed the same way. Q6 e-tron owners report that a start without a body works.

So with the PPE option on and no setting given: the car's own settings as the
body when it reports them, and NO body at all (no ``json`` argument, not ``{}``)
when it reports none. With a setting given, the earlier behaviour stays. Other
cars and the MBB switch are unchanged.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError

_VIN = "WAUZZZF2ZPN000001"
# Shape of the settings the car that started reported (values invented).
_A6_SETTINGS = {
    "targetTemperature_C": 21.5,
    "targetTemperature_F": 71,
    "unitInCar": "celsius",
    "climatisationMode": "comfort",
    "climatizationAtUnlock": False,
    "zoneFrontLeftEnabled": True,
    "zoneFrontRightEnabled": True,
    "zoneRearLeftEnabled": True,
    "zoneRearRightEnabled": True,
    "carCapturedTimestamp": "2026-11-16T08:31:32Z",
}
_A6_BODY = {
    "targetTemperature": 21.5,
    "targetTemperatureUnit": "celsius",
    "climatizationAtUnlock": False,
    "zoneFrontLeftEnabled": True,
    "zoneFrontRightEnabled": True,
    "zoneRearLeftEnabled": True,
    "zoneRearRightEnabled": True,
    "climatisationMode": "comfort",
}


def _status(settings: Any) -> dict[str, Any]:
    return {"climatisation": {"climatisationSettings": {"value": settings}}}


def _client(status: Any = None, *, get_error: Exception | None = None) -> VWEUClient:
    client = VWEUClient.__new__(VWEUClient)
    client._tokens = None
    client._vehicle_bases = {}
    client._v2_command_paths = {}
    if get_error is not None:
        client._get = AsyncMock(side_effect=get_error)
    else:
        client._get = AsyncMock(return_value=_status(_A6_SETTINGS) if status is None else status)
    client._post = AsyncMock(return_value={"data": {"requestId": "r1"}})
    client._await_bff_command = AsyncMock(return_value=None)
    return client


def _no_settings_client() -> VWEUClient:
    # The second car: the climatisation job carries no settings part.
    return _client({"climatisation": {"climatisationStatus": {"value": {"climatisationState": "off"}}}})


def _basic(client: VWEUClient, **kwargs: Any) -> None:
    asyncio.run(client.command_start_climate(_VIN, **kwargs))


def _rich(client: VWEUClient, **kwargs: Any) -> None:
    asyncio.run(client.command_start_climate_control(_VIN, **kwargs))


# ── the basic start ──────────────────────────────────────────────────────────


def test_basic_ppe_start_sends_the_cars_own_settings_when_it_reports_them() -> None:
    client = _client()
    _basic(client, ppe_mode=True)
    assert client._post.await_count == 1
    assert client._post.await_args.args[0].endswith(f"/vehicle/v1/vehicles/{_VIN}/climatisation/start")
    assert client._post.await_args.kwargs == {"json": _A6_BODY}


def test_basic_ppe_start_reads_the_climatisation_job_once() -> None:
    client = _client()
    _basic(client, ppe_mode=True)
    client._get.assert_awaited_once()
    args, kwargs = client._get.await_args
    assert args[0].endswith(f"/vehicle/v1/vehicles/{_VIN}/selectivestatus")
    assert kwargs["params"] == {"jobs": "climatisation"}


@pytest.mark.parametrize(
    "client",
    [
        _no_settings_client(),
        _client(get_error=APIError(502, "u", "bad gateway")),
        _client(_status({})),
        _client(_status(None)),
    ],
    ids=["no settings part", "read fails", "empty settings", "settings null"],
)
def test_basic_ppe_start_sends_no_body_when_the_car_reports_no_settings(client: VWEUClient) -> None:
    _basic(client, ppe_mode=True)
    assert client._post.await_count == 1
    # No json argument and no other body argument: not even an empty dict.
    assert client._post.await_args.kwargs == {}


def test_basic_ppe_start_is_confirmed_via_pendingrequests_in_both_cases() -> None:
    for client in (_client(), _no_settings_client()):
        _basic(client, ppe_mode=True)
        client._await_bff_command.assert_awaited_once()
        assert client._await_bff_command.await_args.args[0] == _VIN


def test_basic_ppe_start_404_falls_back_to_the_combined_endpoint_with_its_body() -> None:
    client = _no_settings_client()
    client._post = AsyncMock(side_effect=[
        APIError(404, "u", "v1 gone"),
        APIError(404, "u", "v2 gone"),
        {"data": {"requestId": "r2"}},
    ])
    _basic(client, ppe_mode=True)
    calls = client._post.await_args_list
    assert calls[0].args[0].endswith(f"/vehicle/v1/vehicles/{_VIN}/climatisation/start")
    assert calls[0].kwargs == {}
    assert calls[1].args[0].endswith(f"/vehicle/v2/vehicles/{_VIN}/climatisation/start")
    assert calls[1].kwargs == {}
    assert calls[2].args[0].endswith("/climatisation/start-stop")
    assert calls[2].kwargs == {"json": {"action": "start"}}
    client._await_bff_command.assert_awaited_once()


def test_basic_start_without_ppe_option_is_unchanged() -> None:
    client = _client()
    _basic(client)
    assert client._post.await_args.kwargs == {
        "json": {
            "targetTemperature": 21.0,
            "targetTemperatureUnit": "celsius",
            "climatisationWithoutExternalPower": True,
            "windowHeatingEnabled": True,
        }
    }
    client._get.assert_not_awaited()


def test_basic_start_hands_the_mbb_switch_the_command_untouched() -> None:
    client = _client()
    target = AsyncMock()
    client._mbb_command_target = lambda: target  # type: ignore[method-assign]
    _basic(client, ppe_mode=True)
    target._command_mbb_op.assert_awaited_once_with(_VIN, "climate_start")
    client._post.assert_not_awaited()
    client._get.assert_not_awaited()


def test_other_commands_still_send_their_json_body() -> None:
    client = _client()
    asyncio.run(client.command_stop_climate(_VIN))
    assert client._post.await_args.kwargs == {"json": {}}


# ── the start with options (service call) ────────────────────────────────────


def test_rich_ppe_start_without_any_setting_sends_the_cars_settings() -> None:
    # Exactly what the A6 that started got from 5.4.0.
    client = _client()
    _rich(client, ppe_mode=True)
    assert client._post.await_count == 1
    assert client._post.await_args.args[0].endswith(f"/vehicles/{_VIN}/climatisation/start")
    assert client._post.await_args.kwargs == {"json": _A6_BODY}
    client._get.assert_awaited_once()


def test_rich_ppe_start_without_any_setting_and_no_settings_sends_no_body() -> None:
    # Not {"climatisationMode": "comfort"}: that is what failed on the second A6.
    client = _no_settings_client()
    _rich(client, ppe_mode=True)
    assert client._post.await_count == 1
    assert client._post.await_args.kwargs == {}


def test_rich_ppe_start_without_any_setting_is_confirmed_in_both_cases() -> None:
    for client in (_client(), _no_settings_client()):
        _rich(client, ppe_mode=True)
        client._await_bff_command.assert_awaited_once()


@pytest.mark.parametrize(
    "setting",
    [
        {"temp_c": 20.0},
        {"glass_heating": False},
        {"seat_fl": True},
        {"seat_fr": False},
        {"seat_rl": True},
        {"seat_rr": False},
        {"climatisation_at_unlock": False},
        {"climatisation_mode": "economy"},
    ],
    ids=lambda d: next(iter(d)),
)
def test_rich_ppe_start_with_any_one_setting_and_no_settings_keeps_the_earlier_body(setting: dict[str, Any]) -> None:
    # With a setting given the earlier rule stays, also on a car without
    # settings: temperature dropped, mode comfort unless chosen. Even a falsy
    # value (False) is a setting the caller chose, so a body goes out.
    client = _no_settings_client()
    _rich(client, ppe_mode=True, **setting)
    body = client._post.await_args.kwargs["json"]
    assert isinstance(body, dict) and body
    assert "targetTemperature" not in body
    assert body["climatisationMode"] in ("comfort", "economy")


def test_rich_ppe_start_with_settings_lays_the_callers_choice_over_the_cars() -> None:
    client = _client()
    _rich(client, ppe_mode=True, glass_heating=True, climatisation_mode="economy")
    assert client._post.await_args.kwargs["json"] == {**_A6_BODY, "windowHeatingEnabled": True, "climatisationMode": "economy"}


def test_rich_start_without_ppe_option_and_no_setting_still_sends_its_empty_body() -> None:
    client = _client()
    _rich(client)
    assert client._post.await_args.kwargs == {"json": {}}
    client._get.assert_not_awaited()
    client._await_bff_command.assert_awaited_once()


def test_rich_start_without_ppe_option_with_settings_is_unchanged() -> None:
    client = _client()
    _rich(client, temp_c=20.0, glass_heating=True)
    assert client._post.await_args.kwargs == {
        "json": {
            "targetTemperature": 20.0,
            "targetTemperatureUnit": "celsius",
            "windowHeatingEnabled": True,
        }
    }
