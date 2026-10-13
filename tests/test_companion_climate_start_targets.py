# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion climate Start: mode and temperature held in HA by the climate entity.

The 4.6.4 Air Conditioning sheet has no Save; Start applies the selected mode
and the dial. So both are HA-held values: changing them only stores them (no
phone or car traffic), they are restored across restarts, and a poll of an
unchanged dial never overwrites them (a dial changed in the app does).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.vag_connect.companion.client import CompanionClient
from custom_components.vag_connect.climate import VagCompanionClimate

VIN = "WVWZZZTESTVIN0001"


class _TrippedChannel:
    """Any phone access fails the test: storing must never reach the phone."""

    def __getattr__(self, name):  # pragma: no cover - must not run
        raise AssertionError(f"the channel was touched: {name}")


def _client() -> CompanionClient:
    client = CompanionClient.__new__(CompanionClient)
    client._brand = "volkswagen"
    client._channel = _TrippedChannel()
    return client


def _coordinator(client: CompanionClient, vehicle: dict | None = None):
    coord = MagicMock()
    coord.is_companion = MagicMock(return_value=True)
    coord._cariad_client = client
    coord.data = {VIN: dict(vehicle or {})}
    coord.last_update_success = True
    coord._cariad_cmd = AsyncMock(side_effect=AssertionError("no command on a store"))

    async def set_temp(vin, temp_c):
        # The real coordinator glue (companion branch), on this mock.
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        await VagConnectCoordinator.async_set_climatisation_temperature(coord, vin, temp_c)

    coord.async_set_climatisation_temperature = set_temp
    return coord


def _climate(coord):
    coord.command_method_available = MagicMock(return_value=True)
    e = VagCompanionClimate(coord, VIN)
    e.async_write_ha_state = MagicMock()
    return e


@pytest.mark.asyncio
async def test_changing_the_temperature_and_preset_while_off_only_stores():
    client = _client()
    coord = _coordinator(client)
    climate = _climate(coord)
    await climate.async_set_temperature(temperature=23.2)
    await climate.async_set_preset_mode("window_heating")
    assert client.climate_targets.temp_c == 23.0  # snapped to the dial's grid
    assert client.climate_targets.window_heating_only is True
    assert climate.preset_mode == "window_heating"
    coord._cariad_cmd.assert_not_called()
    coord.async_request_refresh.assert_not_called()


def test_the_poll_never_overwrites_the_held_values():
    client = _client()
    client.store_climate_target_temperature(21.0)
    # What the app shows arrives with the poll; the entity keeps HA's values.
    coord = _coordinator(client, {"target_temperature": 25.5,
                                  "climate_start_mode": "window_heating"})
    climate = _climate(coord)
    assert climate.target_temperature == 21.0
    assert climate.preset_mode == "air_conditioning"


def test_not_companion_entries_get_no_targets():
    from custom_components.vag_connect.companion.client import climate_targets_of

    coord = MagicMock()
    coord.is_companion = MagicMock(return_value=False)
    assert climate_targets_of(coord) is None
    coord.is_companion = MagicMock(return_value=True)  # a MagicMock client
    assert climate_targets_of(coord) is None


def test_climate_entity_shows_the_held_temperature():
    from custom_components.vag_connect.climate import VagClimate

    client = _client()
    client.store_climate_target_temperature(24.0)
    coord = _coordinator(client, {"target_temperature": 20.0})
    coord.command_method_available = MagicMock(return_value=True)
    assert VagClimate(coord, VIN).target_temperature == 24.0


def test_with_nothing_held_the_climate_shows_the_dial():
    # Nothing held means Start leaves the dial, so the dial is what it applies.
    client = _client()
    coord = _coordinator(client, {"target_temperature": 22.0})
    climate = _climate(coord)
    assert climate.target_temperature == 22.0
    # Shown, not held: a restart must not turn the dial reading into a target.
    assert climate.extra_restore_state_data.held_temp_c is None
    assert client.climate_targets.temp_c is None
    client.store_climate_target_temperature(23.0)
    assert climate.extra_restore_state_data.held_temp_c == 23.0


@pytest.mark.asyncio
async def test_set_temperature_with_hvac_mode_stores_then_starts():
    from custom_components.vag_connect.climate import VagClimate

    client = _client()
    coord = _coordinator(client)
    coord.command_method_available = MagicMock(return_value=True)
    seen: list[float | None] = []

    async def start(vin):
        seen.append(client.climate_targets.temp_c)

    coord.async_start_climatisation = start
    entity = VagClimate(coord, VIN)
    await entity.async_set_temperature(temperature=22.5, hvac_mode="heat_cool")
    assert seen == [22.5]  # stored first, so the Start applies it
    await entity.async_set_temperature(temperature=23.0)
    assert seen == [22.5]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["heat", "cool", "auto", "dry", "fan_only"])
async def test_set_temperature_with_an_unlisted_hvac_mode_sends_nothing(mode):
    # Through HA's own schema and service handler: "heat" passes HA's
    # validation, and must not become a Stop (only "off" means Stop).
    try:  # Home Assistant 2026.10 moved both into the services module.
        from homeassistant.components.climate.services import (
            SET_TEMPERATURE_SCHEMA,
        )
        from homeassistant.components.climate.services import (
            _async_service_temperature_set as async_service_temperature_set,
        )
    except ImportError:
        from homeassistant.components.climate import (  # type: ignore[attr-defined,no-redef]
            SET_TEMPERATURE_SCHEMA,
            async_service_temperature_set,
        )
    from homeassistant.const import UnitOfTemperature
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.vag_connect.climate import VagClimate

    client = _client()
    coord = _coordinator(client, {"climatisation_active": True})
    coord.command_method_available = MagicMock(return_value=True)
    coord.async_start_climatisation = AsyncMock()
    coord.async_stop_climatisation = AsyncMock()
    entity = VagClimate(coord, VIN)
    entity.hass = MagicMock()
    entity.hass.config.units.temperature_unit = UnitOfTemperature.CELSIUS
    data = SET_TEMPERATURE_SCHEMA(
        {"entity_id": "climate.car", "temperature": 22, "hvac_mode": mode}
    )
    data.pop("entity_id")
    with pytest.raises(ServiceValidationError) as err:
        await async_service_temperature_set(entity, SimpleNamespace(data=data))
    assert err.value.translation_key == "hvac_mode_not_supported"
    assert err.value.translation_placeholders["hvac_mode"] == mode
    coord.async_start_climatisation.assert_not_called()
    coord.async_stop_climatisation.assert_not_called()
    assert client.climate_targets.temp_c is None  # nothing stored either
    with pytest.raises(ServiceValidationError):
        await entity.async_set_hvac_mode(mode)
    coord.async_stop_climatisation.assert_not_called()
    coord._cariad_cmd.assert_not_called()
    # The listed modes still work through the same handler. The climate runs,
    # so the temperature also goes out as a command.
    coord._cariad_cmd = AsyncMock()
    for ok, called in (("heat_cool", coord.async_start_climatisation),
                       ("off", coord.async_stop_climatisation)):
        data = SET_TEMPERATURE_SCHEMA(
            {"entity_id": "climate.car", "temperature": 22, "hvac_mode": ok}
        )
        data.pop("entity_id")
        await async_service_temperature_set(entity, SimpleNamespace(data=data))
        called.assert_awaited_once_with(VIN)


# -- following the app's dial -------------------------------------------------


def _read(client: CompanionClient, value: float) -> None:
    client.climate_targets.note_app_dial(value)


def test_a_dial_changed_in_the_app_replaces_the_held_value():
    # Live: the app showed 20 while the climate entity kept 22.
    client = _client()
    _read(client, 22.0)
    client.store_climate_target_temperature(22.0)
    coord = _coordinator(client, {"target_temperature": 20.0})
    _read(client, 20.0)  # the dial was turned in the app
    assert client.climate_targets.temp_c == 20.0
    assert _climate(coord).target_temperature == 20.0
    from custom_components.vag_connect.climate import VagClimate

    coord.command_method_available = MagicMock(return_value=True)
    assert VagClimate(coord, VIN).target_temperature == 20.0


def test_an_unchanged_dial_keeps_the_value_chosen_in_ha():
    client = _client()
    _read(client, 20.0)
    client.store_climate_target_temperature(23.0)
    for _ in range(3):
        _read(client, 20.0)  # the poll reads the dial HA has not moved
    assert client.climate_targets.temp_c == 23.0
    _read(client, 21.5)
    assert client.climate_targets.temp_c == 21.5


def test_nothing_held_stays_nothing_held():
    # Start keeps leaving the dial alone; the number already shows the read.
    client = _client()
    _read(client, 20.0)
    _read(client, 24.0)
    assert client.climate_targets.temp_c is None


def test_a_non_number_read_is_ignored():
    client = _client()
    _read(client, 20.0)
    client.store_climate_target_temperature(23.0)
    for junk in (None, "LO", True):
        client.climate_targets.note_app_dial(junk)
    assert client.climate_targets.app_dial_c == 20.0
    _read(client, 20.0)
    assert client.climate_targets.temp_c == 23.0


def test_the_dial_is_saved_with_the_held_value():
    client = _client()
    _read(client, 20.0)
    client.store_climate_target_temperature(23.0)
    data = _climate(_coordinator(client)).extra_restore_state_data
    assert data.held_temp_c == 23.0
    assert data.as_dict()["app_dial_c"] == 20.0


async def _restore(client, held, dial):
    climate = _climate(_coordinator(client))
    extra = SimpleNamespace(as_dict=lambda: {
        "held_temp_c": held, "app_dial_c": dial, "window_heating_only": False,
    })
    climate.async_get_last_extra_data = AsyncMock(return_value=extra)
    with patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()):
        await climate.async_added_to_hass()


@pytest.mark.asyncio
@pytest.mark.parametrize(("first_read", "held"), [(20.0, 23.0), (19.0, 19.0)])
async def test_restore_then_read(first_read, held):
    # Saved: 23 held against a dial at 20. Unchanged dial keeps 23; a dial
    # moved while HA was down wins.
    client = _client()
    await _restore(client, 23.0, 20.0)
    assert client.climate_targets.temp_c == 23.0
    _read(client, first_read)
    assert client.climate_targets.temp_c == held


@pytest.mark.asyncio
@pytest.mark.parametrize(("first_read", "held"), [(20.0, 23.0), (19.0, None)])
async def test_read_then_restore(first_read, held):
    # The first read can land before the climate entity is restored.
    client = _client()
    _read(client, first_read)
    await _restore(client, 23.0, 20.0)
    assert client.climate_targets.temp_c == held


@pytest.mark.asyncio
async def test_a_restore_without_the_dial_lets_the_first_read_win():
    # Saved by a version that did not keep the dial: nothing to compare with.
    client = _client()
    await _restore(client, 22.0, None)
    assert client.climate_targets.temp_c == 22.0
    _read(client, 20.0)
    assert client.climate_targets.temp_c == 20.0
    _read(client, 20.0)
    client.store_climate_target_temperature(23.0)
    _read(client, 20.0)
    assert client.climate_targets.temp_c == 23.0


@pytest.mark.asyncio
async def test_a_value_set_in_ha_before_the_first_read_is_kept():
    client = _client()
    await _restore(client, 22.0, None)
    client.store_climate_target_temperature(24.0)  # chosen in HA after the restart
    _read(client, 20.0)
    assert client.climate_targets.temp_c == 24.0


@pytest.mark.asyncio
async def test_the_poll_feeds_the_dial_read_to_the_targets():
    client = _client()
    channel = MagicMock()
    channel.read = AsyncMock(return_value={"target_temperature": 20.0})
    channel.nav_read_at = {}
    channel.request_state = None
    channel.live_app_version = None
    channel.source_data_age_s = None
    client._channel = channel
    client._source_channel = "adb"
    client._last_data = None
    client.climate_targets.app_dial_c = 22.0
    client.store_climate_target_temperature(22.0)
    data = await client.get_status(VIN)
    assert data.target_temperature == 20.0
    assert client.climate_targets.temp_c == 20.0
