# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2072 — the range de-duplication no longer takes away a fuel range sensor
that already exists.

Since 2.23.1 a car without a battery gets no ``combustion_range_km`` sensor
when that value equals ``range_km``: three identical "range" sensors were
noise. The rule runs when the entities are built, at a start and on each poll
by the spawner, and it never removes anything, so a sensor that already existed
was simply not provided again and Home Assistant showed it as unavailable
(``restored: true``). That happened to the reporter on 23 November, and with
the #2238 change (a carried main range now follows this poll's fuel range) the
two values are equal far more often, while the reporter's automations read
exactly that sensor.

Pinned here: a fuel range sensor that is already registered for this config
entry is built even when it equals the main range; a car without one keeps the
de-duplication as before; a registry entry of another config entry does not
count; and a registry that answers with anything but a real entity id (as the
mocked one in other tests does) does not switch the rule off.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.const import (
    CONF_STRATEGY,
    DOMAIN,
    STRATEGY_COMPANION_ADB,
    vehicle_unique_id,
)

VIN = "VINX"
ENTRY_ID = "entry-2072"
_COMBUSTION = {
    "vin": VIN, "has_battery": False, "has_combustion": True,
    "range_km": 720, "combustion_range_km": 720, "total_range_km": 720,
}


class _Registry:
    """Just the two lookups the sensor setup uses."""

    def __init__(self, entries: dict[tuple[str, str], tuple[str, str]]) -> None:
        # (platform, unique_id) -> (entity_id, config_entry_id)
        self._by_uid = entries

    def async_get_entity_id(self, platform: str, domain: str, unique_id: str) -> str | None:
        assert domain == DOMAIN
        hit = self._by_uid.get((platform, unique_id))
        return hit[0] if hit else None

    def async_get(self, entity_id: str) -> Any:
        for eid, entry_id in self._by_uid.values():
            if eid == entity_id:
                return SimpleNamespace(entity_id=eid, config_entry_id=entry_id)
        return None


def _built_keys(
    vehicle: dict, monkeypatch: pytest.MonkeyPatch, registry: Any,
    entry_data: dict[str, Any] | None = None,
) -> set[str]:
    from homeassistant.helpers import entity_registry as er

    from custom_components.vag_connect import sensor as sensor_mod

    monkeypatch.setattr(er, "async_get", lambda _hass: registry)
    coord = MagicMock()
    coord.is_read_only = MagicMock(return_value=False)
    coord.is_companion = MagicMock(return_value=False)
    coord.data = {VIN: vehicle}
    coord.vehicles = coord.data
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "volkswagen"}
    coord.command_capability_supported = MagicMock(return_value=True)
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.data = entry_data if entry_data is not None else {"brand": "volkswagen"}
    entry.options = {}
    entry.runtime_data = coord
    added: list = []

    def _collect(entities: Any, **_kw: Any) -> None:
        added.extend(entities)

    asyncio.run(sensor_mod.async_setup_entry(MagicMock(), entry, _collect))
    return {
        e.entity_description.key for e in added if hasattr(e, "entity_description")
    }


def _registered(entry_id: str = ENTRY_ID) -> _Registry:
    uid = vehicle_unique_id(VIN, "combustion_range_km")
    return _Registry({("sensor", uid): ("sensor.tayron_fuel_range", entry_id)})


def test_existing_fuel_range_sensor_is_built_although_equal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = _built_keys(_COMBUSTION, monkeypatch, _registered())
    assert "combustion_range_km" in keys
    assert "range_km" in keys


def test_car_without_the_sensor_keeps_the_deduplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = _built_keys(_COMBUSTION, monkeypatch, _Registry({}))
    assert "combustion_range_km" not in keys
    assert "range_km" in keys


def test_registry_entry_of_another_config_entry_does_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = _built_keys(_COMBUSTION, monkeypatch, _registered("some-other-entry"))
    assert "combustion_range_km" not in keys


def test_total_range_rule_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    uid = vehicle_unique_id(VIN, "total_range_km")
    reg = _Registry({("sensor", uid): ("sensor.tayron_total_range", ENTRY_ID)})
    keys = _built_keys(_COMBUSTION, monkeypatch, reg)
    assert "total_range_km" not in keys


_COMPANION_DATA = {"brand": "volkswagen", CONF_STRATEGY: STRATEGY_COMPANION_ADB}


def test_companion_entry_looks_up_its_own_unique_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = vehicle_unique_id(VIN, "combustion_range_km", companion=True)
    reg = _Registry({("sensor", uid): ("sensor.tayron_fuel_range_2", ENTRY_ID)})
    keys = _built_keys(_COMBUSTION, monkeypatch, reg, _COMPANION_DATA)
    assert "combustion_range_km" in keys


def test_companion_entry_ignores_the_cloud_unique_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = _built_keys(_COMBUSTION, monkeypatch, _registered(), _COMPANION_DATA)
    assert "combustion_range_km" not in keys


def test_an_entity_id_that_is_not_a_string_does_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The entity-id guard on its own: a non-string id with an owner that
    matches this entry must still not read as 'already there'."""
    reg = MagicMock()
    reg.async_get_entity_id = MagicMock(return_value=MagicMock())
    reg.async_get = MagicMock(return_value=SimpleNamespace(config_entry_id=ENTRY_ID))
    keys = _built_keys(_COMBUSTION, monkeypatch, reg)
    assert "combustion_range_km" not in keys


def test_a_mocked_registry_does_not_switch_the_rule_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Other tests run the setup with a MagicMock hass, whose registry answers
    every lookup with a truthy mock. That must not read as 'already there'."""
    keys = _built_keys(_COMBUSTION, monkeypatch, MagicMock())
    assert "combustion_range_km" not in keys
