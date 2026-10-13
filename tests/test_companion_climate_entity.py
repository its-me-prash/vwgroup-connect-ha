# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion climate entity: one place for on/off, temperature and the mode."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.vag_connect.climate import (
    PRESET_AIR_CONDITIONING,
    PRESET_WINDOW_HEATING,
    VagClimate,
    VagCompanionClimate,
)
from custom_components.vag_connect.companion.client import CompanionClient

VIN = "WVWZZZTESTVIN0001"


class _TrippedChannel:
    def __getattr__(self, name):  # pragma: no cover - must not run
        raise AssertionError(f"the channel was touched: {name}")


def _client() -> CompanionClient:
    client = CompanionClient.__new__(CompanionClient)
    client._brand = "volkswagen"
    client._channel = _TrippedChannel()
    return client


def _coord(client: CompanionClient, vehicle: dict | None = None):
    coord = MagicMock()
    coord.is_companion = MagicMock(return_value=True)
    coord.command_method_available = MagicMock(return_value=True)
    coord._cariad_client = client
    coord.data = {VIN: dict(vehicle or {})}
    coord.last_update_success = True
    coord.async_start_climatisation = AsyncMock()
    coord.async_stop_climatisation = AsyncMock()
    return coord


def _entity(coord) -> VagCompanionClimate:
    e = VagCompanionClimate(coord, VIN)
    e.async_write_ha_state = MagicMock()
    return e


def test_same_unique_id_as_the_shared_entity():
    coord = _coord(_client())
    assert VagCompanionClimate(coord, VIN).unique_id == VagClimate(coord, VIN).unique_id


def test_presets_and_default():
    e = _entity(_coord(_client()))
    assert e.preset_modes == [PRESET_AIR_CONDITIONING, PRESET_WINDOW_HEATING]
    assert e.preset_mode == PRESET_AIR_CONDITIONING


@pytest.mark.asyncio
async def test_preset_while_off_only_stores():
    client = _client()
    coord = _coord(client)
    e = _entity(coord)
    await e.async_set_preset_mode(PRESET_WINDOW_HEATING)
    assert client.climate_targets.window_heating_only is True
    assert e.preset_mode == PRESET_WINDOW_HEATING
    coord.async_start_climatisation.assert_not_called()


@pytest.mark.asyncio
async def test_preset_while_off_is_allowed_during_the_pause():
    # Local only: no command path, so no request-limit check is reached.
    client = _client()
    coord = _coord(client)
    coord.async_start_climatisation = AsyncMock(side_effect=AssertionError("no start"))
    await _entity(coord).async_set_preset_mode(PRESET_WINDOW_HEATING)
    assert client.climate_targets.window_heating_only is True


@pytest.mark.asyncio
@pytest.mark.parametrize("vehicle", [
    {"climatisation_active": True},
    {"climatisation_active": False, "window_heating_front": True},
])
async def test_preset_change_while_running_is_refused(vehicle):
    client = _client()
    e = _entity(_coord(client, vehicle))
    with pytest.raises(ServiceValidationError):
        await e.async_set_preset_mode(PRESET_WINDOW_HEATING)
    assert client.climate_targets.window_heating_only is False


@pytest.mark.asyncio
async def test_unknown_preset_is_refused():
    e = _entity(_coord(_client()))
    with pytest.raises(ServiceValidationError):
        await e.async_set_preset_mode("boost")


def test_window_heating_alone_shows_on():
    e = _entity(_coord(_client(), {"climatisation_active": False, "window_heating_front": True}))
    assert e.hvac_mode == HVACMode.HEAT_COOL
    assert e.preset_mode == PRESET_WINDOW_HEATING


def test_running_preset_follows_the_app():
    e = _entity(_coord(_client(), {"climatisation_active": True, "climate_start_mode": "air_conditioning"}))
    assert e.preset_mode == PRESET_AIR_CONDITIONING


@pytest.mark.asyncio
async def test_turn_on_starts_and_turn_off_stops():
    coord = _coord(_client())
    e = _entity(coord)
    await e.async_turn_on()
    coord.async_start_climatisation.assert_awaited_once_with(VIN)
    await e.async_turn_off()
    coord.async_stop_climatisation.assert_awaited_once_with(VIN)


@pytest.mark.asyncio
async def test_turn_on_with_window_heating_chosen_uses_the_held_mode():
    # The client's command_start_climate starts what ClimateTargets holds.
    client = _client()
    coord = _coord(client)
    e = _entity(coord)
    await e.async_set_preset_mode(PRESET_WINDOW_HEATING)
    await e.async_turn_on()
    coord.async_start_climatisation.assert_awaited_once_with(VIN)
    assert client.climate_targets.window_heating_only is True




def _read(client, value):
    client.climate_targets.note_app_dial(value)


def test_saved_data_holds_only_held_values():
    client = _client()
    _read(client, 20.0)
    e = _entity(_coord(client, {"target_temperature": 20.0}))
    assert e.extra_restore_state_data.as_dict() == {
        "held_temp_c": None, "app_dial_c": 20.0, "window_heating_only": False,
    }
    client.store_climate_target_temperature(23.0)
    client.store_climate_start_mode(True)
    assert e.extra_restore_state_data.as_dict() == {
        "held_temp_c": 23.0, "app_dial_c": 20.0, "window_heating_only": True,
    }


async def _restore(client, saved):
    e = _entity(_coord(client))
    e.async_get_last_extra_data = AsyncMock(
        return_value=SimpleNamespace(as_dict=lambda: saved) if saved is not None else None
    )
    with patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()):
        await e.async_added_to_hass()
    return e


@pytest.mark.asyncio
async def test_restart_restores_mode_and_temperature():
    client = _client()
    await _restore(client, {"held_temp_c": 23.0, "app_dial_c": 20.0, "window_heating_only": True})
    assert client.climate_targets.window_heating_only is True
    assert client.climate_targets.temp_c == 23.0
    _read(client, 19.0)  # dial moved in the app while HA was down: it wins
    assert client.climate_targets.temp_c == 19.0


@pytest.mark.asyncio
async def test_restart_with_nothing_saved_holds_nothing():
    client = _client()
    await _restore(client, None)
    assert client.climate_targets.temp_c is None
    assert client.climate_targets.window_heating_only is False


def _poll(e, coord, vehicle):
    coord.data[VIN] = dict(vehicle)
    e._handle_coordinator_update()


def test_window_heating_run_ends_back_to_air_conditioning():
    client = _client()
    client.store_climate_start_mode(True)
    coord = _coord(client)
    e = _entity(coord)
    _poll(e, coord, {"window_heating_front": True})
    assert e.preset_mode == PRESET_WINDOW_HEATING
    _poll(e, coord, {"window_heating_front": False})
    assert client.climate_targets.window_heating_only is False
    assert e.preset_mode == PRESET_AIR_CONDITIONING


def test_a_choice_never_started_is_kept():
    client = _client()
    client.store_climate_start_mode(True)
    coord = _coord(client)
    e = _entity(coord)
    for _ in range(3):
        _poll(e, coord, {"window_heating_front": False, "climatisation_active": False})
    assert client.climate_targets.window_heating_only is True


def test_a_refused_start_keeps_the_window_heating_choice():
    # The coordinator shows climatisation_active optimistically on a Start and
    # reverts it when the Start is refused (pause, gap, gate). That is no run.
    client = _client()
    client.store_climate_start_mode(True)
    coord = _coord(client)
    e = _entity(coord)
    _poll(e, coord, {"climatisation_active": True})   # optimistic
    _poll(e, coord, {"climatisation_active": False})  # reverted
    assert client.climate_targets.window_heating_only is True


def test_the_dial_minimum_is_lo():
    assert _entity(_coord(_client())).min_temp == 15.5
