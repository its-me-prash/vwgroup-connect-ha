# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion nav reads as CONFIG switches, applied to the running channel."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.switch import (
    COMPANION_READS,
    VagCompanionReadSwitch,
    _companion_read_switches,
)

VW = PRESETS["volkswagen"]


def test_switching_a_read_on_queues_its_paths_for_the_next_poll():
    channel = CompanionChannel(object(), VW, time_fn=time.monotonic, nav_opt_ins=set())
    assert not channel.nav_reads_enabled
    channel.set_nav_opt_in("vehicle_health", True)
    assert channel.nav_opt_ins == {"vehicle_health"}
    # Vehicle Health and vehicle Settings share the opt-in.
    assert channel._nav_only == {"vehicle_health", "vehicle_settings"}


def test_switching_a_read_off_drops_only_its_cached_values():
    channel = CompanionChannel(object(), VW, time_fn=time.monotonic,
                               nav_opt_ins={"vehicle_health", "climate_detail"})
    health = next(n for n in VW.nav_reads if n.name == "vehicle_health")
    climate = next(n for n in VW.nav_reads if n.name == "climate_detail")
    channel._nav_cache.update(odometer_km=322, target_temperature=22.0)
    channel._nav_cache_from.update(odometer_km=health.opt_in, target_temperature=climate.opt_in)
    channel.set_nav_opt_in("vehicle_health", False)
    assert channel.nav_opt_ins == {"climate_detail"}
    assert channel._nav_cache == {"target_temperature": 22.0}


def test_charge_detail_switch_keeps_the_legacy_flag_in_step():
    channel = CompanionChannel(object(), VW, time_fn=time.monotonic, read_charge_detail=True)
    channel.set_nav_opt_in("charge_detail", False)
    assert channel._read_charge_detail is False
    assert "charge_detail" not in channel.nav_opt_ins


def _entry(brand="volkswagen", options=None, data=None):
    entry = MagicMock()
    entry.entry_id = "E1"
    entry.data = {"brand": brand, **(data or {})}
    entry.options = dict(options or {})
    return entry


def _coordinator(companion=True):
    coordinator = MagicMock()
    coordinator.is_companion.return_value = companion
    return coordinator


@pytest.mark.parametrize(("brand", "companion", "count"), [
    ("volkswagen", True, len(COMPANION_READS)),
    ("volkswagen", False, 0),
    ("audi", True, 0),  # the Audi preset has no nav reads
])
def test_switches_exist_only_for_presets_with_nav_reads(brand, companion, count):
    switches = _companion_read_switches(_coordinator(companion), _entry(brand))
    assert len(switches) == count
    assert all(s.entity_category == "config" for s in switches)


def test_switch_state_comes_from_options_then_data():
    sw = VagCompanionReadSwitch(_coordinator(), _entry(data={"companion_read_vehicle_health": True}),
                                "vehicle_health", "companion_read_vehicle_health", "mdi:car-wrench")
    assert sw.is_on
    sw._entry.options = {"companion_read_vehicle_health": False}
    assert not sw.is_on


@pytest.mark.asyncio
async def test_turning_on_applies_live_and_stores_the_option():
    coordinator = _coordinator()
    entry = _entry()
    sw = VagCompanionReadSwitch(coordinator, entry, "parking_position",
                                "companion_read_parking_position", "mdi:map-marker")
    sw.async_write_ha_state = MagicMock()
    await sw.async_turn_on()
    coordinator.set_companion_read.assert_called_once_with("parking_position", True)
    coordinator.hass.config_entries.async_update_entry.assert_called_once_with(
        entry, options={"companion_read_parking_position": True},
    )
