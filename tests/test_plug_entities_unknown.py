# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2135 / #1739 — an electric car whose data ships no plug field must still get
the Charging Cable Connected binary sensor and the Charging Port sensor, showing
"unknown", instead of losing them at the next restart.

Since #1739 the mapper no longer infers ``plug_connected`` from a scheduled
charging plan, so on such a car the value stays None. The default-on hide-empty
spawn gate then skipped both entities. They are exempted for electric cars only;
the value logic is untouched (None stays None).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.binary_sensor import (
    VagConnectBinarySensor,
    async_setup_entry as bs_setup,
)
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.sensor import async_setup_entry as s_setup


def _coord(vehicle: dict) -> Any:
    c = MagicMock()
    c.vehicles = {"X": vehicle}
    c.data = c.vehicles
    c.is_read_only = MagicMock(return_value=False)
    c.last_update_success = True
    c.command_capability_supported = MagicMock(return_value=None)
    c.read_capability_hidden = MagicMock(return_value=False)
    c.async_add_listener = MagicMock(return_value=lambda: None)
    return c


def _entry(coord: Any, hide: bool) -> Any:
    entry = MagicMock()
    entry.runtime_data = coord
    entry.options = {"hide_empty_entities": hide}
    entry.data = {"brand": "skoda"}
    entry.async_on_unload = lambda x: None
    return entry


def _entities(setup: Any, vehicle: dict, hide: bool) -> list[Any]:
    added: list[Any] = []
    asyncio.run(setup(MagicMock(), _entry(_coord(vehicle), hide),
                      lambda e: added.extend(e)))
    return added


def _keys(setup: Any, vehicle: dict, hide: bool) -> set[str]:
    return {
        e.entity_description.key
        for e in _entities(setup, vehicle, hide)
        if hasattr(e, "entity_description")
    }


def _ev(**extra: Any) -> dict:
    return {"vin": "X", "has_battery": True, "has_combustion": False,
            "battery_soc": 80, **extra}


def _ice() -> dict:
    return {"vin": "X", "has_battery": False, "has_combustion": True,
            "odometer_km": 1000}


class TestBinarySensorPlugConnected:
    def test_ev_without_plug_data_gets_entity_that_is_unknown(self) -> None:
        ents = _entities(bs_setup, _ev(), hide=True)
        plug = [e for e in ents
                if getattr(e, "entity_description", None) is not None
                and e.entity_description.key == "plug_connected"]
        assert len(plug) == 1
        assert isinstance(plug[0], VagConnectBinarySensor)
        assert plug[0].is_on is None

    def test_combustion_car_does_not_get_it(self) -> None:
        assert "plug_connected" not in _keys(bs_setup, _ice(), hide=True)

    def test_hide_empty_off_unchanged(self) -> None:
        assert "plug_connected" in _keys(bs_setup, _ev(), hide=False)
        assert "plug_connected" not in _keys(bs_setup, _ice(), hide=False)

    def test_other_empty_keys_are_still_hidden(self) -> None:
        # the exemption is for plug_connected only
        on = _keys(bs_setup, _ev(), hide=True)
        off = _keys(bs_setup, _ev(), hide=False)
        assert off - on  # hide-empty still hides other data-less sensors

    def test_real_values_still_render(self) -> None:
        for val in (True, False):
            ents = _entities(bs_setup, _ev(plug_connected=val), hide=True)
            plug = [e for e in ents
                    if getattr(e, "entity_description", None) is not None
                    and e.entity_description.key == "plug_connected"]
            assert len(plug) == 1
            assert plug[0].is_on is val


class TestSensorPlugState:
    def test_ev_without_plug_data_gets_entity_that_is_unknown(self) -> None:
        ents = _entities(s_setup, _ev(), hide=True)
        plug = [e for e in ents
                if getattr(e, "entity_description", None) is not None
                and e.entity_description.key == "plug_state"]
        assert len(plug) == 1
        assert plug[0].native_value is None

    def test_combustion_car_does_not_get_it(self) -> None:
        assert "plug_state" not in _keys(s_setup, _ice(), hide=True)

    def test_hide_empty_off_unchanged(self) -> None:
        assert "plug_state" in _keys(s_setup, _ev(), hide=False)
        assert "plug_state" not in _keys(s_setup, _ice(), hide=False)

    def test_other_empty_keys_are_still_hidden(self) -> None:
        on = _keys(s_setup, _ev(), hide=True)
        off = _keys(s_setup, _ev(), hide=False)
        assert off - on


def test_mapper_guard_scheduled_plan_at_zero_power_leaves_plug_none() -> None:
    # The #1739 lift is untouched: a scheduled plan at 0 kW with no plug field
    # must NOT turn plug_connected into a value.
    scn = "charging_state_report.charging_scenario"
    for plan in (
        "CHARGING_SCENARIO_OPTIMISED_CHARGING_ACTIVE",
        "CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_ACTIVE",
    ):
        d = map_dataset_to_vehicle_data(
            {scn: plan, "charging_power": "0"}, VehicleData(vin="X")
        )
        assert d.plug_connected is None


def test_exempt_keys_are_electric_only_descriptions() -> None:
    # The exemption relies on the description's own condition="electric" to keep
    # the entity off combustion cars; pin that so dropping it cannot go unseen.
    from custom_components.vag_connect import binary_sensor, sensor

    for mod, descs in ((binary_sensor, binary_sensor.BINARY_DESCRIPTIONS),
                       (sensor, sensor.SENSOR_DESCRIPTIONS)):
        for key in mod._SPAWN_WITHOUT_DATA:
            found = [d for d in descs if d.key == key]
            assert len(found) == 1, key
            assert found[0].condition == "electric", key


def test_exemption_sets_are_exactly_the_plug_keys() -> None:
    # Widening the set would silently bring back the "unknown" flood the
    # hide-empty option exists to prevent.
    from custom_components.vag_connect import binary_sensor, sensor

    assert binary_sensor._SPAWN_WITHOUT_DATA == frozenset({"plug_connected"})
    assert sensor._SPAWN_WITHOUT_DATA == frozenset({"plug_state"})
