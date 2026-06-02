# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.12.0 — five MINOR features bundled.

Feature scope (each closes or partials a planned issue):

- ``Test12VBattery`` — Issue #23: lvBattery job parsing + voltage sensor
  + warning_12v_low binary sensor at 11.5 V threshold
- ``TestPerLightSensors`` — #91 leftover: dynamic per-light binary sensor
  creation from `lights_individual` dict
- ``TestSmartWakeCounter`` — Issue #55: wake_count_today increment +
  daily reset + soft-cap budget enforcement
- ``TestWriteableMaxChargeCurrent`` — #91 follow-up: Number entity
  registered + dispatches to coordinator + new vw_eu command
- ``TestReadOnlyMode`` — Issue #63: is_read_only() helper + 5 platform
  gates (lock, switch, climate, number, button-non-refresh)
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


def _vw_eu():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client


# ─────────────────────────────────────────────────────────────────────────────
# #23 — 12V battery
# ─────────────────────────────────────────────────────────────────────────────


class Test12VBattery:
    def test_voltage_parsed_from_lvbattery_job(self):
        client = _vw_eu()
        raw = {
            "lvBattery": {
                "lvBatteryStatus": {"value": {"batteryVoltage_V": 12.6}},
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.voltage_12v == 12.6
        assert d.warning_12v_low is False  # 12.6 > 11.5

    def test_warning_triggered_below_threshold(self):
        client = _vw_eu()
        raw = {
            "lvBattery": {
                "lvBatteryStatus": {"value": {"batteryVoltage_V": 11.2}},
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.voltage_12v == 11.2
        assert d.warning_12v_low is True

    def test_no_lvbattery_means_none(self):
        """Vehicles whose API doesn't expose lvBattery (older platforms,
        Skoda mysmob) leave both fields as None — phantom-protection
        in sensor.py + binary_sensor.py then skips entity creation."""
        client = _vw_eu()
        d = client._parse_status("V", {}, parking={})
        assert d.voltage_12v is None
        assert d.warning_12v_low is None

    def test_voltage_string_form_parsed_via_safe_float(self):
        """Older firmware sometimes ships ``"12.5"`` as string. v1.10.1
        safe_float helper handles it."""
        client = _vw_eu()
        raw = {
            "lvBattery": {
                "lvBatteryStatus": {"value": {"batteryVoltage_V": "12.5"}},
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.voltage_12v == 12.5

    def test_lvbattery_in_selectivestatus_jobs(self):
        from custom_components.vag_connect.cariad.api.vw_eu import (
            _SELECTIVE_STATUS_JOBS,
        )
        assert "lvBattery" in _SELECTIVE_STATUS_JOBS

    def test_voltage_sensor_registered(self):
        from custom_components.vag_connect.sensor import (
            SENSOR_DESCRIPTIONS, _DATA_PRESENT_REQUIRED,
        )
        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "voltage_12v" in keys
        assert "voltage_12v" in _DATA_PRESENT_REQUIRED

    def test_warning_binary_sensor_registered(self):
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS, _DATA_PRESENT_REQUIRED,
        )
        keys = {d.key for d in BINARY_DESCRIPTIONS}
        assert "warning_12v_low" in keys
        assert "warning_12v_low" in _DATA_PRESENT_REQUIRED


# ─────────────────────────────────────────────────────────────────────────────
# #91 leftover — per-light binary sensors
# ─────────────────────────────────────────────────────────────────────────────


class TestPerLightSensors:
    def test_setup_creates_one_entity_per_light(self):
        from custom_components.vag_connect.binary_sensor import (
            VagLightSensor, _async_setup_light_sensors,
        )

        coord = MagicMock()
        vehicle = {"lights_individual": {"frontLeft": True, "rearRight": False}}
        entities: list = []
        asyncio.get_event_loop().run_until_complete(
            _async_setup_light_sensors(coord, "VINX", vehicle, entities)
        )
        assert len(entities) == 2
        assert all(isinstance(e, VagLightSensor) for e in entities)
        ids = {e._light_id for e in entities}
        assert ids == {"frontLeft", "rearRight"}

    def test_no_lights_individual_creates_no_entities(self):
        """Phantom protection: empty dict → no per-light entities."""
        from custom_components.vag_connect.binary_sensor import (
            _async_setup_light_sensors,
        )
        coord = MagicMock()
        vehicle = {"lights_individual": {}}
        entities: list = []
        asyncio.get_event_loop().run_until_complete(
            _async_setup_light_sensors(coord, "VINX", vehicle, entities)
        )
        assert entities == []

    def test_light_sensor_is_on_reads_individual_dict(self):
        from custom_components.vag_connect.binary_sensor import VagLightSensor

        coord = MagicMock()
        coord.data = {"VINX": {"lights_individual": {"frontLeft": True, "rearLeft": False}}}
        coord.is_vehicle_available.return_value = True
        sensor = VagLightSensor.__new__(VagLightSensor)
        sensor.coordinator = coord
        sensor._vin = "VINX"
        sensor._light_id = "frontLeft"
        sensor._key = "light_frontLeft"
        assert sensor.is_on is True

        sensor._light_id = "rearLeft"
        assert sensor.is_on is False

        sensor._light_id = "missing"
        assert sensor.is_on is None


# ─────────────────────────────────────────────────────────────────────────────
# #55 — Smart Wake counter
# ─────────────────────────────────────────────────────────────────────────────


def _coord_with_vehicle():
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "audi"}
    coord.entry.options = {}
    coord._vehicles_lock = threading.Lock()
    coord.vehicles = {"VINX": {}}
    coord._cariad_client = MagicMock()
    coord._cariad_client.command_wake = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    coord.async_set_updated_data = MagicMock()
    coord.record_command_success = MagicMock()
    coord.record_command_failure = MagicMock()
    return coord


class TestSmartWakeCounter:
    def test_first_wake_sets_count_to_one(self):
        coord = _coord_with_vehicle()
        asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VINX"))
        assert coord.vehicles["VINX"]["wake_count_today"] == 1

    def test_subsequent_wakes_increment(self):
        coord = _coord_with_vehicle()
        for _ in range(2):
            asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VINX"))
            # v1.13.0 (#63) — clear the 5-min cooldown so the loop can
            # advance the budget counter without hitting wake_cooldown_active.
            # v1.25.0 PR-D: state moved to dispatcher
            d = getattr(coord, "_dispatcher", None)
            if d is not None and hasattr(d, "_wake_last_at"):
                d._wake_last_at.clear()
        assert coord.vehicles["VINX"]["wake_count_today"] == 2

    def test_wake_budget_exhausted_raises(self):
        from homeassistant.exceptions import ServiceValidationError
        from custom_components.vag_connect.coordinator import _WAKE_BUDGET_PER_DAY

        coord = _coord_with_vehicle()
        # Fill the budget
        for _ in range(_WAKE_BUDGET_PER_DAY):
            asyncio.get_event_loop().run_until_complete(
                coord.async_wake_vehicle("VINX")
            )
            # v1.13.0 (#63) — clear the 5-min cooldown between iterations
            # so the budget-exhaust path is the one being tested.
            # v1.25.0 PR-D: state moved to dispatcher
            d = getattr(coord, "_dispatcher", None)
            if d is not None and hasattr(d, "_wake_last_at"):
                d._wake_last_at.clear()
        # One more should raise (budget exhausted, not cooldown)
        with pytest.raises(ServiceValidationError):
            asyncio.get_event_loop().run_until_complete(
                coord.async_wake_vehicle("VINX")
            )

    def test_daily_reset_at_new_date(self):
        coord = _coord_with_vehicle()
        # Pre-populate yesterday's count at the budget
        from custom_components.vag_connect.coordinator import _WAKE_BUDGET_PER_DAY
        yesterday = (datetime.now(tz=timezone.utc) - timedelta(days=1)).date()
        coord._wake_counts = {"VINX": (yesterday, _WAKE_BUDGET_PER_DAY)}
        # Today should reset and proceed
        asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VINX"))
        today = datetime.now(tz=timezone.utc).date()
        assert coord._wake_counts["VINX"] == (today, 1)

    def test_wake_count_today_sensor_registered(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "wake_count_today" in keys


# ─────────────────────────────────────────────────────────────────────────────
# #91 follow-up — Writeable max_charge_current Number
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteableMaxChargeCurrent:
    def test_command_set_max_charge_current_uses_correct_payload(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

        client = VWEUClient.__new__(VWEUClient)
        client._post_command = AsyncMock()
        asyncio.get_event_loop().run_until_complete(
            client.command_set_max_charge_current("VINX", 16)
        )
        client._post_command.assert_awaited_once_with(
            "VINX", "charging/settings", json={"maxChargeCurrentAC_A": 16},
        )

    def test_coordinator_async_set_max_charge_current_dispatches(self):
        coord = _coord_with_vehicle()
        coord._cariad_client.command_set_max_charge_current = AsyncMock()
        asyncio.get_event_loop().run_until_complete(
            coord.async_set_max_charge_current("VINX", 16)
        )
        coord._cariad_client.command_set_max_charge_current.assert_awaited_once_with(
            "VINX", ampere=16,
        )

    def test_number_entity_registered(self):
        from custom_components.vag_connect.number import NUMBER_DESCRIPTIONS

        keys = {d.key for d in NUMBER_DESCRIPTIONS}
        assert "max_charge_current" in keys

    def test_number_entity_has_ampere_unit_and_electric_condition(self):
        from custom_components.vag_connect.number import NUMBER_DESCRIPTIONS
        from homeassistant.const import UnitOfElectricCurrent

        desc = next(d for d in NUMBER_DESCRIPTIONS if d.key == "max_charge_current")
        assert desc.native_unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert desc.condition == "electric"
        assert desc.native_min_value == 6
        assert desc.native_max_value == 32


# ─────────────────────────────────────────────────────────────────────────────
# #63 — Read-only mode
# ─────────────────────────────────────────────────────────────────────────────


def _coord_with_read_only(read_only: bool):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "audi"}
    coord.entry.options = {"read_only_mode": read_only}
    coord.vehicles = {"VINX": {"has_battery": True, "model": "Test"}}
    coord._cariad_client = MagicMock()
    # v1.25.0 PR-C — platforms now use register_dynamic_spawner which calls
    # coordinator.async_add_listener(). DataUpdateCoordinator initialises
    # ``_listeners`` in ``__init__``; bypassed here via ``__new__``. Stub
    # ``async_add_listener`` so the listener-registration path runs without
    # AttributeError.
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


class TestReadOnlyMode:
    def test_helper_reads_options_first(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.options = {"read_only_mode": True}
        coord.entry.data = {}
        assert coord.is_read_only() is True

    def test_helper_falls_back_to_data(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.options = {}
        coord.entry.data = {"read_only_mode": True}
        assert coord.is_read_only() is True

    def test_helper_default_false(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.options = {}
        coord.entry.data = {}
        assert coord.is_read_only() is False

    def test_lock_setup_skipped_when_read_only(self):
        from custom_components.vag_connect.lock import async_setup_entry as lock_setup

        coord = _coord_with_read_only(True)
        entry = MagicMock()
        entry.runtime_data = coord
        added = []
        asyncio.get_event_loop().run_until_complete(
            lock_setup(MagicMock(), entry, added.append)
        )
        # Lock platform returned early — no entities passed to add
        assert added == []

    def test_climate_setup_skipped_when_read_only(self):
        from custom_components.vag_connect.climate import async_setup_entry

        coord = _coord_with_read_only(True)
        entry = MagicMock()
        entry.runtime_data = coord
        added = []
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, added.append)
        )
        assert added == []

    def test_number_setup_skipped_when_read_only(self):
        from custom_components.vag_connect.number import async_setup_entry

        coord = _coord_with_read_only(True)
        entry = MagicMock()
        entry.runtime_data = coord
        added = []
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, added.append)
        )
        assert added == []

    def test_normal_mode_creates_entities(self):
        """Read-only=False → entities ARE created."""
        from custom_components.vag_connect.lock import async_setup_entry as lock_setup

        coord = _coord_with_read_only(False)
        entry = MagicMock()
        entry.runtime_data = coord
        added: list[list] = []
        # async_add_entities is normally called with a list — capture it
        def _capture(things):
            added.append(list(things))
        asyncio.get_event_loop().run_until_complete(
            lock_setup(MagicMock(), entry, _capture)
        )
        assert added and len(added[0]) == 1  # one VagDoorLock for VINX
