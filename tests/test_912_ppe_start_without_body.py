# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#912 / #1403: a PPE Audi's climatisation start goes out without a request body.

On an A6 Avant e-tron (PPE) the start was sent with
``{climatisationWithoutExternalPower, windowHeatingEnabled, climatisationMode}``;
the request stayed ``in_progress`` and the car never started (E:CV.PA.29, "Vehicle
is not responding"). Confirmed by Q6 e-tron owners: a start without a request
body works, the car applies its own settings; every variant with a body was
accepted by the backend and failed in the car.

So, with the PPE option on and no setting given by the caller, the start is a
POST with no body at all (no ``json`` argument, not an empty ``{}``). With a
setting given, the earlier behaviour stays: the car's reported settings plus the
caller's choices. Other cars and the MBB switch are unchanged.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError

_VIN = "WAUZZZF2ZPN000001"
_STATUS = {
    "climatisation": {
        "climatisationSettings": {
            "value": {"targetTemperature_C": 22.5, "climatisationMode": "economy"}
        }
    }
}


def _client() -> VWEUClient:
    client = VWEUClient.__new__(VWEUClient)
    client._tokens = None
    client._vehicle_bases = {}
    client._v2_command_paths = {}
    client._get = AsyncMock(return_value=_STATUS)
    client._post = AsyncMock(return_value={"data": {"requestId": "r1"}})
    client._await_bff_command = AsyncMock(return_value=None)
    return client


def _basic(client: VWEUClient, **kwargs: Any) -> None:
    asyncio.run(client.command_start_climate(_VIN, **kwargs))


def _rich(client: VWEUClient, **kwargs: Any) -> None:
    asyncio.run(client.command_start_climate_control(_VIN, **kwargs))


# ── the basic start ──────────────────────────────────────────────────────────


def test_basic_ppe_start_sends_no_body_at_all() -> None:
    client = _client()
    _basic(client, ppe_mode=True)
    assert client._post.await_count == 1
    url = client._post.await_args.args[0]
    assert url.endswith(f"/vehicle/v1/vehicles/{_VIN}/climatisation/start")
    # No json argument and no other body argument: not even an empty dict.
    assert client._post.await_args.kwargs == {}


def test_basic_ppe_start_reads_no_settings() -> None:
    client = _client()
    _basic(client, ppe_mode=True)
    client._get.assert_not_awaited()


def test_basic_ppe_start_is_still_confirmed_via_pendingrequests() -> None:
    client = _client()
    _basic(client, ppe_mode=True)
    client._await_bff_command.assert_awaited_once()
    assert client._await_bff_command.await_args.args[0] == _VIN


def test_basic_ppe_start_404_falls_back_to_the_combined_endpoint_with_its_body() -> None:
    client = _client()
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


def test_other_commands_still_send_their_json_body() -> None:
    # The no-body path is opt-in per call; stop still sends its empty object.
    client = _client()
    asyncio.run(client.command_stop_climate(_VIN))
    assert client._post.await_args.kwargs == {"json": {}}


# ── the start with options (service call) ────────────────────────────────────


def test_rich_ppe_start_without_any_setting_sends_no_body() -> None:
    client = _client()
    _rich(client, ppe_mode=True)
    assert client._post.await_count == 1
    assert client._post.await_args.args[0].endswith(f"/vehicles/{_VIN}/climatisation/start")
    assert client._post.await_args.kwargs == {}
    client._get.assert_not_awaited()


def test_rich_ppe_start_without_any_setting_is_still_confirmed() -> None:
    client = _client()
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
        {"climatisation_mode": "comfort"},
    ],
    ids=lambda d: next(iter(d)),
)
def test_rich_ppe_start_with_any_one_setting_keeps_the_earlier_body(setting: dict[str, Any]) -> None:
    # Even a falsy value (False) is a setting the caller chose.
    client = _client()
    _rich(client, ppe_mode=True, **setting)
    body = client._post.await_args.kwargs["json"]
    assert isinstance(body, dict) and body
    # Built on the car's reported settings, as before.
    assert body["climatisationMode"] in ("economy", "comfort")
    client._get.assert_awaited_once()
    client._await_bff_command.assert_awaited_once()


def test_rich_ppe_start_with_settings_lays_the_callers_choice_over_the_cars() -> None:
    client = _client()
    _rich(client, ppe_mode=True, glass_heating=True, climatisation_mode="comfort")
    body = client._post.await_args.kwargs["json"]
    assert body == {
        "targetTemperature": 22.5,
        "targetTemperatureUnit": "celsius",
        "windowHeatingEnabled": True,
        "climatisationMode": "comfort",
    }


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
