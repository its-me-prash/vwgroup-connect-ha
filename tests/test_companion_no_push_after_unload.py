"""A poll the unload lets finish must not spawn entities on the dead entry.

HA removes an entry's listeners only after ``async_unload_entry`` returns, and
the companion unload lets a running screen walk finish. Live 2026-10-10: that
walk's push spawned four new sensors (charging power, speed, remaining time,
vehicle status) on the cleared platform, tied to the shut-down coordinator, so
they kept their charging values forever and the reloaded entry's own sensors
were rejected as duplicate unique ids.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.vag_connect.coordinator import VagConnectCoordinator
from custom_components.vag_connect.entity_base import register_dynamic_spawner


class _Ent:
    def __init__(self, uid: str) -> None:
        self.unique_id = uid


def _spawner(state: ConfigEntryState):
    entry = MagicMock()
    entry.state = state
    coordinator = MagicMock()
    coordinator.vehicles = {}
    listeners: list = []
    coordinator.async_add_listener.side_effect = lambda cb: listeners.append(cb)
    added: list = []
    register_dynamic_spawner(
        entry, coordinator, lambda ents: added.extend(ents),
        lambda vin, v: [_Ent(f"{vin}_charging_power_kw")],
    )
    return entry, coordinator, listeners, added


def test_spawner_adds_nothing_while_its_entry_unloads() -> None:
    entry, coordinator, listeners, added = _spawner(ConfigEntryState.LOADED)
    entry.state = ConfigEntryState.UNLOAD_IN_PROGRESS
    coordinator.vehicles = {"VIN1": {"charging_power_kw": 2.0}}
    listeners[0]()
    assert added == []


def test_spawner_still_adds_late_data_on_a_loaded_entry() -> None:
    entry, coordinator, listeners, added = _spawner(ConfigEntryState.LOADED)
    coordinator.vehicles = {"VIN1": {"charging_power_kw": 2.0}}
    listeners[0]()
    assert [e.unique_id for e in added] == ["VIN1_charging_power_kw"]


@pytest.mark.asyncio
async def test_a_poll_finishing_during_shutdown_pushes_nothing() -> None:
    coordinator = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coordinator._shutting_down = True
    coordinator._was_available = True
    coordinator.async_set_updated_data = MagicMock()
    coordinator.async_update_listeners = MagicMock()
    await coordinator._async_push_update({"VIN1": {"charging_power_kw": 2.0}})
    await coordinator._async_push_update({}, success=False)
    coordinator.async_set_updated_data.assert_not_called()
    coordinator.async_update_listeners.assert_not_called()


def test_the_unload_guard_tolerates_a_core_without_the_state(monkeypatch) -> None:
    # hacs.json allows cores older than ConfigEntryState.UNLOAD_IN_PROGRESS.
    from custom_components.vag_connect import entity_base

    monkeypatch.setattr(entity_base, "_UNLOAD_IN_PROGRESS", None)
    entry, coordinator, listeners, added = _spawner(ConfigEntryState.LOADED)
    coordinator.vehicles = {"VIN1": {"charging_power_kw": 2.0}}
    listeners[0]()
    assert [e.unique_id for e in added] == ["VIN1_charging_power_kw"]
