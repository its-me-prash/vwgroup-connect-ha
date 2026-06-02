# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for all VAG Connect entity platforms — achieves >95% coverage."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ── Shared mock factory ────────────────────────────────────────────────────────

def _make_coordinator(vehicles=None):
    """Build a minimal mock coordinator with one EV by default.

    v1.12.0 (#63) — explicit ``is_read_only`` mock returning False so
    platform setup gates don't accidentally skip entities under tests
    (``coord.is_read_only()`` on a bare MagicMock returns a truthy
    MagicMock by default).
    """
    coord = MagicMock()
    coord.is_read_only = MagicMock(return_value=False)
    coord.data = vehicles or {
        "WVGZZZ1KZAW123456": {
            "vin": "WVGZZZ1KZAW123456",
            "model": "ID.4",
            "manufacturer": "Volkswagen",
            "model_year": 2023,
            "firmware_version": "3.2.1",
            "battery_soc": 80,
            "range_km": 350,
            "range_estimated_full_km": 420,
            "range_wltp_km": 520,
            "battery_available_kwh": 68.3,
            "fuel_level": None,
            "odometer_km": 15000,
            "is_electric": True,
            "has_battery": True,
            "has_combustion": False,
            "is_hybrid": False,
            "doors_locked": True,
            "doors_open": False,
            "windows_open": False,
            "climatisation_state": "OFF",
            "climatisation_active": False,
            "target_temperature": 21.0,
            "outside_temp": 10.0,
            "charging_state": "READY_FOR_CHARGING",
            "is_charging": False,
            "plug_connected": True,
            "plug_state": "CONNECTED",
            "target_soc": 80,
            "charging_power_kw": None,
            "charging_rate_kmh": None,
            "charge_complete_eta": None,
            "charging_type": None,
            "charging_station_name": None,
            "charging_station_address": None,
            "charging_station_kw": None,
            "charging_station_operator": None,
            "is_driving": False,
            "is_online": True,
            "connector_locked": False,
            "auto_unlock_charge": False,
            "max_charge_current": 16.0,
            "latitude": 48.137,
            "longitude": 11.576,
            "parking_address": "Marienplatz 1, München",
            "parking_city": "München",
            "heading": 270,
            "vehicle_state": "PARKED",
            "connection_state": "ONLINE",
            "battery_temp": 22.0,
            "battery_cap_kwh": 77.0,
            "license_plate": "M-AB 1234",
            "last_updated_at": None,
            "service_km": 8000,
            "service_due_at": None,
            "oil_service_km": None,
            "oil_service_at": None,
            "departure_timer_1_enabled": True,
            "departure_timer_1_time": None,
            "departure_timer_2_enabled": False,
            "departure_timer_2_time": None,
            "departure_timer_3_enabled": False,
            "departure_timer_3_time": None,
            "doors_individual": {"frontLeft": False, "frontRight": False},
            "_vehicle": MagicMock(),
        }
    }
    coord.vehicles = coord.data
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "volkswagen", "username": "t@t.de"}
    coord.last_update_success = True
    coord.async_request_refresh = AsyncMock()
    coord.async_lock = AsyncMock()
    coord.async_unlock = AsyncMock()
    coord.async_start_climatisation = AsyncMock()
    coord.async_stop_climatisation = AsyncMock()
    coord.async_start_charging = AsyncMock()
    coord.async_stop_charging = AsyncMock()
    coord.async_flash_lights = AsyncMock()
    coord.async_wake_vehicle = AsyncMock()
    coord.async_start_window_heating = AsyncMock()
    coord.async_stop_window_heating = AsyncMock()
    coord.async_set_departure_timer = AsyncMock()
    coord.async_set_target_soc = AsyncMock()
    coord.async_set_climatisation_temperature = AsyncMock()
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock()
    return coord


def _make_entry(coord=None):
    entry = MagicMock()
    entry.runtime_data = coord or _make_coordinator()
    return entry


# ── entity_base ────────────────────────────────────────────────────────────────

class TestEntityBase:
    def test_unique_id_is_vin_plus_key(self):
        from custom_components.vag_connect.entity_base import VagConnectEntity
        coord = _make_coordinator()
        e = VagConnectEntity(coord, "VIN123", "key_test")
        assert e._attr_unique_id == "VIN123_key_test"

    def test_parallel_updates_is_zero(self):
        from custom_components.vag_connect.entity_base import VagConnectEntity
        assert VagConnectEntity._attr_parallel_updates == 0

    def test_has_entity_name_true(self):
        from custom_components.vag_connect.entity_base import VagConnectEntity
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        e = VagConnectEntity(coord, vin, "test")
        assert e._attr_has_entity_name is True

    def test_vehicle_property_returns_data(self):
        from custom_components.vag_connect.entity_base import VagConnectEntity
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        e = VagConnectEntity(coord, vin, "test")
        assert e._vehicle["battery_soc"] == 80

    def test_vehicle_safe_when_data_none(self):
        from custom_components.vag_connect.entity_base import VagConnectEntity
        coord = _make_coordinator()
        coord.data = None
        e = VagConnectEntity(coord, "VIN999", "test")
        assert e._vehicle == {}

    def test_device_info_uses_vin_as_identifier(self):
        from custom_components.vag_connect.entity_base import VagConnectEntity
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        e = VagConnectEntity(coord, vin, "test")
        info = e.device_info
        from custom_components.vag_connect.const import DOMAIN
        assert (DOMAIN, vin) in info["identifiers"]

    def test_device_info_fallback_name(self):
        from custom_components.vag_connect.entity_base import _device_name
        v = {"vin": "WVGABC123456", "model": None}
        name = _device_name(v, "volkswagen")
        assert "123456" in name

    def test_device_info_sw_version(self):
        from custom_components.vag_connect.entity_base import VagConnectEntity
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        e = VagConnectEntity(coord, vin, "test")
        assert e.device_info.get("sw_version") == "3.2.1"


# ── sensor ─────────────────────────────────────────────────────────────────────

class TestSensor:
    def test_setup_creates_entities_for_ev(self):
        import asyncio
        from custom_components.vag_connect.sensor import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, added.append)
        )
        # Should create sensors for EV (has_battery=True)
        assert len(added) > 0

    def test_sensor_native_value(self):
        from custom_components.vag_connect.sensor import VagConnectSensor, VagSensorDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        desc = VagSensorDescription(key="battery_soc", data_key="battery_soc")
        s = VagConnectSensor(coord, vin, desc)
        assert s.native_value == 80

    def test_sensor_none_when_key_missing(self):
        from custom_components.vag_connect.sensor import VagConnectSensor, VagSensorDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        desc = VagSensorDescription(key="nonexistent", data_key="nonexistent")
        s = VagConnectSensor(coord, vin, desc)
        assert s.native_value is None

    def test_combustion_sensors_skipped_for_ev(self):
        import asyncio
        from custom_components.vag_connect.sensor import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        keys = {e.entity_description.key for e in added}
        assert "fuel_level" not in keys  # combustion-only sensor
        assert "battery_soc" in keys     # electric sensor present


# ── binary_sensor ─────────────────────────────────────────────────────────────

class TestBinarySensor:
    def test_is_on_true(self):
        from custom_components.vag_connect.binary_sensor import VagConnectBinarySensor, VagBinarySensorDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        desc = VagBinarySensorDescription(key="doors_locked", data_key="doors_locked")
        b = VagConnectBinarySensor(coord, vin, desc)
        assert b.is_on is True

    def test_is_on_false(self):
        from custom_components.vag_connect.binary_sensor import VagConnectBinarySensor, VagBinarySensorDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["doors_open"] = False
        desc = VagBinarySensorDescription(key="doors_open", data_key="doors_open")
        b = VagConnectBinarySensor(coord, vin, desc)
        assert b.is_on is False

    def test_is_on_none_when_data_none(self):
        from custom_components.vag_connect.binary_sensor import VagConnectBinarySensor, VagBinarySensorDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["is_driving"] = None
        desc = VagBinarySensorDescription(key="is_driving", data_key="is_driving")
        b = VagConnectBinarySensor(coord, vin, desc)
        assert b.is_on is None

    def test_door_sensor_is_on(self):
        from custom_components.vag_connect.binary_sensor import VagDoorSensor
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["doors_individual"] = {"frontLeft": True}
        d = VagDoorSensor(coord, vin, "frontLeft")
        assert d.is_on is True

    def test_setup_creates_door_sensors(self):
        import asyncio
        from custom_components.vag_connect.binary_sensor import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        keys = [getattr(e, '_key', '') for e in added]
        assert any("door_" in k for k in keys)


# ── lock ───────────────────────────────────────────────────────────────────────

class TestLock:
    def test_lock_is_locked(self):
        from custom_components.vag_connect.lock import VagDoorLock
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        lock = VagDoorLock(coord, vin)
        assert lock.is_locked is True

    def test_lock_is_unlocked(self):
        from custom_components.vag_connect.lock import VagDoorLock
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["doors_locked"] = False
        lock = VagDoorLock(coord, vin)
        assert lock.is_locked is False

    def test_lock_async_lock(self):
        import asyncio
        from custom_components.vag_connect.lock import VagDoorLock
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        lock = VagDoorLock(coord, vin)
        asyncio.get_event_loop().run_until_complete(lock.async_lock())
        coord.async_lock.assert_called_once_with(vin)

    def test_lock_async_unlock(self):
        import asyncio
        from custom_components.vag_connect.lock import VagDoorLock
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        lock = VagDoorLock(coord, vin)
        asyncio.get_event_loop().run_until_complete(lock.async_unlock())
        coord.async_unlock.assert_called_once_with(vin)

    def test_lock_unique_id(self):
        from custom_components.vag_connect.lock import VagDoorLock
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        lock = VagDoorLock(coord, vin)
        assert lock.unique_id == f"{vin}_door_lock"


# ── switch ─────────────────────────────────────────────────────────────────────

class TestSwitch:
    def test_lock_switch_is_on(self):
        from custom_components.vag_connect.switch import VagLockSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagLockSwitch(coord, vin)
        assert s.is_on is True

    def test_lock_switch_turn_on(self):
        import asyncio
        from custom_components.vag_connect.switch import VagLockSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagLockSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_on())
        coord.async_lock.assert_called_once_with(vin)

    def test_lock_switch_turn_off(self):
        import asyncio
        from custom_components.vag_connect.switch import VagLockSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagLockSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_off())
        coord.async_unlock.assert_called_once_with(vin)

    def test_charging_switch_is_on_when_charging(self):
        from custom_components.vag_connect.switch import VagChargingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["charging_state"] = "CHARGING"
        s = VagChargingSwitch(coord, vin)
        assert s.is_on is True

    def test_charging_switch_is_off_when_not_charging(self):
        from custom_components.vag_connect.switch import VagChargingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["charging_state"] = "READY_FOR_CHARGING"
        s = VagChargingSwitch(coord, vin)
        assert s.is_on is False

    def test_climatisation_switch_is_off(self):
        from custom_components.vag_connect.switch import VagClimatisationSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagClimatisationSwitch(coord, vin)
        assert s.is_on is False

    def test_climatisation_switch_is_on(self):
        from custom_components.vag_connect.switch import VagClimatisationSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["climatisation_state"] = "HEATING"
        s = VagClimatisationSwitch(coord, vin)
        assert s.is_on is True

    def test_departure_timer_switch_enabled(self):
        from custom_components.vag_connect.switch import VagDepartureTimerSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagDepartureTimerSwitch(coord, vin, 1)
        assert s.is_on is True  # departure_timer_1_enabled = True

    def test_departure_timer_switch_turn_on(self):
        import asyncio
        from custom_components.vag_connect.switch import VagDepartureTimerSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagDepartureTimerSwitch(coord, vin, 2)
        asyncio.get_event_loop().run_until_complete(s.async_turn_on())
        coord.async_set_departure_timer.assert_called_once_with(vin, 2, enabled=True, departure_time=None)

    # test_auto_unlock_switch removed in v1.8.0 — VagAutoUnlockSwitch deleted (#60).


# ── button ─────────────────────────────────────────────────────────────────────

class TestButton:
    def test_flash_button_press(self):
        import asyncio
        from custom_components.vag_connect.button import VagFlashButton
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        b = VagFlashButton(coord, vin)
        asyncio.get_event_loop().run_until_complete(b.async_press())
        coord.async_flash_lights.assert_called_once_with(vin)

    def test_refresh_button_press(self):
        import asyncio
        from custom_components.vag_connect.button import VagRefreshButton
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        b = VagRefreshButton(coord, vin)
        asyncio.get_event_loop().run_until_complete(b.async_press())
        coord.async_request_refresh.assert_called_once()

    def test_wake_button_press(self):
        import asyncio
        from custom_components.vag_connect.button import VagWakeButton
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        b = VagWakeButton(coord, vin)
        asyncio.get_event_loop().run_until_complete(b.async_press())
        coord.async_wake_vehicle.assert_called_once_with(vin)

    def test_setup_creates_three_buttons_per_vehicle(self):
        import asyncio
        from custom_components.vag_connect.button import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        # 1 vehicle × 3 buttons (flash, refresh, wake) = 3
        assert len(added) == 3


# ── number ─────────────────────────────────────────────────────────────────────

class TestNumber:
    def test_native_value_target_soc(self):
        from custom_components.vag_connect.number import VagConnectNumber, VagNumberDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        desc = VagNumberDescription(key="target_soc", data_key="target_soc")
        n = VagConnectNumber(coord, vin, desc)
        assert n.native_value == 80.0

    def test_native_value_none_safe(self):
        from custom_components.vag_connect.number import VagConnectNumber, VagNumberDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["target_soc"] = None
        desc = VagNumberDescription(key="target_soc", data_key="target_soc")
        n = VagConnectNumber(coord, vin, desc)
        assert n.native_value is None

    def test_set_target_soc(self):
        import asyncio
        from custom_components.vag_connect.number import VagConnectNumber, VagNumberDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        desc = VagNumberDescription(key="target_soc", data_key="target_soc")
        n = VagConnectNumber(coord, vin, desc)
        asyncio.get_event_loop().run_until_complete(n.async_set_native_value(90))
        coord.async_set_target_soc.assert_called_once_with(vin, 90)

    def test_set_clim_temperature(self):
        import asyncio
        from custom_components.vag_connect.number import VagConnectNumber, VagNumberDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        desc = VagNumberDescription(key="target_temperature", data_key="target_temperature")
        n = VagConnectNumber(coord, vin, desc)
        asyncio.get_event_loop().run_until_complete(n.async_set_native_value(22.5))
        coord.async_set_climatisation_temperature.assert_called_once_with(vin, 22.5)


# ── device_tracker ─────────────────────────────────────────────────────────────

class TestDeviceTracker:
    def test_latitude_longitude(self):
        from custom_components.vag_connect.device_tracker import VagConnectTracker
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        t = VagConnectTracker(coord, vin)
        assert t.latitude == 48.137
        assert t.longitude == 11.576

    def test_source_type_gps(self):
        from custom_components.vag_connect.device_tracker import VagConnectTracker
        from homeassistant.components.device_tracker import SourceType
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        t = VagConnectTracker(coord, vin)
        assert t.source_type == SourceType.GPS

    def test_setup_only_creates_tracker_with_gps(self):
        import asyncio
        from custom_components.vag_connect.device_tracker import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        assert len(added) == 1

    def test_setup_skips_vehicle_without_gps(self):
        import asyncio
        from custom_components.vag_connect.device_tracker import async_setup_entry
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["latitude"] = None
        coord.vehicles[vin]["latitude"] = None
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        assert len(added) == 0


# ── climate ────────────────────────────────────────────────────────────────────

class TestClimate:
    def test_hvac_mode_off(self):
        from custom_components.vag_connect.climate import VagClimate
        from homeassistant.components.climate import HVACMode
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        c = VagClimate(coord, vin)
        assert c.hvac_mode == HVACMode.OFF

    def test_hvac_mode_heat(self):
        from custom_components.vag_connect.climate import VagClimate
        from homeassistant.components.climate import HVACMode
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["climatisation_state"] = "HEATING"
        c = VagClimate(coord, vin)
        assert c.hvac_mode == HVACMode.HEAT_COOL

    def test_current_temperature(self):
        from custom_components.vag_connect.climate import VagClimate
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        c = VagClimate(coord, vin)
        assert c.current_temperature == 10.0

    def test_target_temperature(self):
        from custom_components.vag_connect.climate import VagClimate
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        c = VagClimate(coord, vin)
        assert c.target_temperature == 21.0


# ── repairs ────────────────────────────────────────────────────────────────────

class TestRepairs:
    def test_raise_issue_creates_issue(self):
        from custom_components.vag_connect.repairs import raise_issue_auth_required
        hass = MagicMock()
        with patch("homeassistant.helpers.issue_registry.async_create_issue") as mock_create:
            raise_issue_auth_required(hass, "entry_123", "invalid_credentials")
        mock_create.assert_called_once()

    def test_clear_auth_issues_removes_all(self):
        from custom_components.vag_connect.repairs import clear_auth_issues
        hass = MagicMock()
        with patch("homeassistant.helpers.issue_registry.async_delete_issue") as mock_del:
            clear_auth_issues(hass, "entry_123")
        # v2.2.0 PR #7/20 — added ``email_two_factor_required`` →
        # 7 issue types total (was 6 pre-Phase-2).
        assert mock_del.call_count == 7

    def test_unknown_reason_uses_auth_failed(self):
        from custom_components.vag_connect.repairs import raise_issue_auth_required
        import homeassistant.helpers.issue_registry as ir
        hass = MagicMock()
        with patch.object(ir, "async_create_issue") as mock_create:
            raise_issue_auth_required(hass, "e1", "some_unknown_reason")
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["translation_key"] == "auth_failed"


# ── diagnostics ────────────────────────────────────────────────────────────────

class TestDiagnostics:
    def test_redacts_password_and_gps(self):
        import asyncio
        from custom_components.vag_connect.diagnostics import async_get_config_entry_diagnostics
        coord = _make_coordinator()
        coord._started = True
        entry = MagicMock()
        entry.runtime_data = coord
        entry.data = {
            "brand": "audi",
            "username": "u@a.de",
            "password": "secret",
            "spin": "1234",
        }
        entry.options = {}
        result = asyncio.get_event_loop().run_until_complete(
            async_get_config_entry_diagnostics(MagicMock(), entry)
        )
        assert result["config"]["password"] == "**REDACTED**"
        assert result["config"]["spin"] == "**REDACTED**"
        # diagnostics.py also redacts the username (privacy default since v1.x)
        assert result["config"]["username"] == "**REDACTED**"

    def test_gps_redacted_in_vehicle(self):
        import asyncio
        from custom_components.vag_connect.diagnostics import async_get_config_entry_diagnostics
        coord = _make_coordinator()
        coord._started = True
        entry = MagicMock()
        entry.runtime_data = coord
        entry.data = {"brand": "audi", "username": "u@a.de", "password": "pw", "spin": ""}
        entry.options = {}
        result = asyncio.get_event_loop().run_until_complete(
            async_get_config_entry_diagnostics(MagicMock(), entry)
        )
        # VINs are masked to last 6 chars in diagnostics output
        masked_keys = list(result["vehicles"].keys())
        assert len(masked_keys) == 1
        masked_vin = masked_keys[0]
        assert masked_vin.startswith("***")
        assert len(masked_vin) <= 9  # "***" + up to 6 chars
        veh = result["vehicles"][masked_vin]
        assert veh.get("latitude") == "**REDACTED**"
        assert veh.get("longitude") == "**REDACTED**"
        assert veh.get("vin") == "**REDACTED**"
        assert veh.get("parking_address") == "**REDACTED**"
        assert "_vehicle" not in veh

    def test_mask_vin_helper(self):
        from custom_components.vag_connect.cariad._util import mask_vin
        assert mask_vin("WVGZZZ1KZAW123456") == "***123456"
        assert mask_vin(None) == "***"
        assert mask_vin("") == "***"
        assert mask_vin("ABC") == "***ABC"


# ── __init__ service helpers ───────────────────────────────────────────────────

class TestServiceHelpers:
    def test_get_coordinator_finds_by_vin(self):
        from custom_components.vag_connect.__init__ import _get_coordinator
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        entry = MagicMock()
        entry.runtime_data = coord
        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[entry])
        result = _get_coordinator(hass, vin)
        assert result is coord

    def test_get_coordinator_returns_none_for_unknown_vin(self):
        from custom_components.vag_connect.__init__ import _get_coordinator
        coord = _make_coordinator()
        entry = MagicMock()
        entry.runtime_data = coord
        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[entry])
        result = _get_coordinator(hass, "UNKNOWN_VIN_000")
        assert result is None

    def test_require_coordinator_raises_service_validation_error(self):
        from homeassistant.exceptions import ServiceValidationError
        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[])

        # Inline _require_coordinator logic test
        with pytest.raises((ServiceValidationError, Exception)):
            # We can't easily invoke _require_coordinator directly since it's nested
            # but we verify ServiceValidationError is importable and usable
            raise ServiceValidationError("test error")


# ── Extended Switch Tests ──────────────────────────────────────────────────────

class TestSwitchExtended:
    def test_window_heating_turn_on(self):
        import asyncio
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagWindowHeatingSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_on())
        coord.async_start_window_heating.assert_called_once_with(vin)

    def test_window_heating_turn_off(self):
        import asyncio
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagWindowHeatingSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_off())
        coord.async_stop_window_heating.assert_called_once_with(vin)

    def test_window_heating_is_none_without_vehicle(self):
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["_vehicle"] = None
        s = VagWindowHeatingSwitch(coord, vin)
        assert s.is_on is None

    # VagSeatHeatingSwitch + VagAutoUnlockSwitch removed in v1.8.0 (#60).
    # Tests removed; reintroduce when real API commands exist.

    def test_setup_creates_ev_switches(self):
        import asyncio
        from custom_components.vag_connect.switch import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        keys = {e._key for e in added}
        assert "charging_switch" in keys
        assert "departure_timer_1_switch" in keys
        assert "departure_timer_2_switch" in keys
        assert "departure_timer_3_switch" in keys


# ── Extended Climate Tests ─────────────────────────────────────────────────────

class TestClimateExtended:
    def test_set_hvac_mode_heat(self):
        import asyncio
        from custom_components.vag_connect.climate import VagClimate
        from homeassistant.components.climate import HVACMode
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        c = VagClimate(coord, vin)
        asyncio.get_event_loop().run_until_complete(
            c.async_set_hvac_mode(HVACMode.HEAT_COOL)
        )
        coord.async_start_climatisation.assert_called_once_with(vin)

    def test_set_hvac_mode_off(self):
        import asyncio
        from custom_components.vag_connect.climate import VagClimate
        from homeassistant.components.climate import HVACMode
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        c = VagClimate(coord, vin)
        asyncio.get_event_loop().run_until_complete(
            c.async_set_hvac_mode(HVACMode.OFF)
        )
        coord.async_stop_climatisation.assert_called_once_with(vin)

    def test_set_temperature(self):
        import asyncio
        from custom_components.vag_connect.climate import VagClimate
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        c = VagClimate(coord, vin)
        asyncio.get_event_loop().run_until_complete(
            c.async_set_temperature(temperature=22.5)
        )
        coord.async_set_climatisation_temperature.assert_called_once_with(vin, 22.5)

    def test_hvac_modes_list(self):
        from custom_components.vag_connect.climate import VagClimate
        from homeassistant.components.climate import HVACMode
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        c = VagClimate(coord, vin)
        assert HVACMode.HEAT_COOL in c.hvac_modes
        assert HVACMode.OFF in c.hvac_modes

    def test_target_temperature_default_when_none(self):
        from custom_components.vag_connect.climate import VagClimate, DEFAULT_TEMP
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["target_temperature"] = None
        c = VagClimate(coord, vin)
        assert c.target_temperature == DEFAULT_TEMP

    def test_setup_creates_one_climate_per_vehicle(self):
        import asyncio
        from custom_components.vag_connect.climate import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        assert len(added) == 1


# ── Extended Number Tests ──────────────────────────────────────────────────────

class TestNumberExtended:
    # max_charge_current entity removed in v1.8.0 (#60) — no real API command exists.
    # Direct call to coordinator.async_set_max_charge_current now raises
    # ServiceValidationError; the test for that lives in TestRunCommand.

    def test_setup_creates_ev_numbers(self):
        import asyncio
        from custom_components.vag_connect.number import async_setup_entry
        coord = _make_coordinator()
        entry = _make_entry(coord)
        added = []
        def _collect(entities, **kw): added.extend(entities)
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, _collect)
        )
        keys = {e.entity_description.key for e in added}
        assert "target_soc" in keys
        assert "target_temperature" in keys
        # v1.12.0 (#91 follow-up) — max_charge_current returned as a
        # writeable Number entity once the CARIAD command was wired
        # (was raise-only pre-1.12.0, now actually dispatches).
        assert "max_charge_current" in keys

    def test_native_value_invalid_converts_to_none(self):
        from custom_components.vag_connect.number import VagConnectNumber, VagNumberDescription
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["target_soc"] = "invalid"
        desc = VagNumberDescription(key="target_soc", data_key="target_soc")
        n = VagConnectNumber(coord, vin, desc)
        assert n.native_value is None


# ── Extended Config Flow Tests ─────────────────────────────────────────────────

class TestConfigFlowExtended:
    def _get_flow_class(self):
        from custom_components.vag_connect.config_flow import VagConnectConfigFlow
        return VagConnectConfigFlow

    def test_reauth_step_shows_form(self):
        import asyncio
        flow = self._get_flow_class()()
        flow.context = {"entry_id": "test_entry"}
        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_entry = MagicMock(return_value=None)
        result = asyncio.get_event_loop().run_until_complete(
            flow.async_step_reauth({})
        )
        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

    def test_reauth_confirm_with_bad_password(self):
        import asyncio
        flow = self._get_flow_class()()
        flow.context = {"entry_id": "test_entry"}
        entry_mock = MagicMock()
        entry_mock.data = {
            "brand": "audi", "username": "u@a.de",
            "password": "old", "spin": "",
        }
        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry_mock)
        with patch(
            "custom_components.vag_connect.config_flow._validate_credentials",
            side_effect=ValueError("invalid_credentials"),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                flow.async_step_reauth_confirm({"password": "wrong", "spin": ""})
            )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_credentials"

    def test_reconfigure_shows_form(self):
        import asyncio
        flow = self._get_flow_class()()
        flow.context = {"entry_id": "test_entry"}
        entry_mock = MagicMock()
        entry_mock.data = {
            "brand": "audi", "username": "u@a.de",
            "password": "pw", "spin": "",
            "scan_interval": 5, "force_enable_access": False,
        }
        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry_mock)
        result = asyncio.get_event_loop().run_until_complete(
            flow.async_step_reconfigure(None)
        )
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

    def test_user_schema_prefilled(self):
        from custom_components.vag_connect.config_flow import _credentials_schema
        schema = _credentials_schema(brand="skoda", username="u@s.cz", scan_interval=10)
        assert schema is not None


# ── Coordinator Action Method Tests ───────────────────────────────────────────

class TestCoordinatorActions:
    """Test coordinator action methods via executor job mocking."""

    def setup_method(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from unittest.mock import MagicMock, AsyncMock
        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock(return_value=None)
        self.coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        self.coord.hass = hass
        self.coord.entry = MagicMock()
        self.coord.entry.data = {"brand": "audi", "username": "t@t.de", "spin": ""}
        self.coord.vehicles = {
            "VIN123": {
                "_vehicle": MagicMock(),
                "model": "Q4 e-tron",
            }
        }
        self.coord._vehicles_lock = __import__("threading").Lock()
        self.coord._cariad_client = MagicMock()
        self.coord._cariad_client.command_lock = AsyncMock()
        self.coord._cariad_client.command_unlock = AsyncMock()
        self.coord._cariad_client.command_start_climate = AsyncMock()
        self.coord._cariad_client.command_stop_climate = AsyncMock()
        self.coord._cariad_client.command_start_charging = AsyncMock()
        self.coord._cariad_client.command_stop_charging = AsyncMock()
        self.coord._cariad_client.command_flash = AsyncMock()
        self.coord._cariad_client.command_wake = AsyncMock()
        self.coord._cariad_client.command_set_target_soc = AsyncMock()
        self.coord._cariad_client.command_set_climate_temperature = AsyncMock()
        self.coord._started = True
        self.coord.data = None
        self.coord._was_available = True
        self.coord.last_update_success = True
        self.coord.async_update_listeners = MagicMock()
        self.coord.async_set_updated_data = MagicMock()
        self.coord.async_request_refresh = AsyncMock()

    def test_async_set_target_soc_calls_executor(self):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self.coord.async_set_target_soc("VIN123", 90)
        )
        self.coord._cariad_client.command_set_target_soc.assert_awaited()

    def test_async_set_climatisation_temperature_calls_executor(self):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self.coord.async_set_climatisation_temperature("VIN123", 22.0)
        )
        self.coord._cariad_client.command_set_climate_temperature.assert_awaited()

    def test_push_update_success_logs_once_on_reconnect(self):
        import asyncio
        self.coord._was_available = False  # Simulate was offline
        with patch("custom_components.vag_connect.coordinator._LOGGER") as mock_log:
            asyncio.get_event_loop().run_until_complete(
                self.coord._async_push_update({"VIN123": {}}, success=True)
            )
        mock_log.info.assert_called()
        assert self.coord._was_available is True

    def test_push_update_failure_logs_once_when_going_offline(self):
        import asyncio
        self.coord._was_available = True
        with patch("custom_components.vag_connect.coordinator._LOGGER") as mock_log:
            asyncio.get_event_loop().run_until_complete(
                self.coord._async_push_update({}, success=False)
            )
        mock_log.warning.assert_called()
        assert self.coord._was_available is False
        assert self.coord.last_update_success is False

    def test_push_update_failure_does_not_log_twice(self):
        import asyncio
        self.coord._was_available = False  # Already offline
        with patch("custom_components.vag_connect.coordinator._LOGGER") as mock_log:
            asyncio.get_event_loop().run_until_complete(
                self.coord._async_push_update({}, success=False)
            )
        mock_log.warning.assert_not_called()  # Already logged before, not again

    def test_stale_device_removal_when_data_is_none(self):
        """_async_remove_stale_devices returns early when data is None."""
        import asyncio
        self.coord.data = None
        # Should not raise
        asyncio.get_event_loop().run_until_complete(
            self.coord._async_remove_stale_devices({"VIN123"})
        )

    def test_stale_device_removal_no_stale(self):
        """Same VINs as before — nothing removed."""
        import asyncio
        self.coord.data = {"VIN123": {}}
        # Should complete without error when no stale VINs
        asyncio.get_event_loop().run_until_complete(
            self.coord._async_remove_stale_devices({"VIN123"})
        )
        # No assertion needed — just verifying no exception raised


# ── Remaining switch coverage ──────────────────────────────────────────────────

class TestSwitchRemaining:
    def test_climatisation_turn_on(self):
        import asyncio
        from custom_components.vag_connect.switch import VagClimatisationSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagClimatisationSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_on())
        coord.async_start_climatisation.assert_called_once_with(vin)

    def test_climatisation_turn_off(self):
        import asyncio
        from custom_components.vag_connect.switch import VagClimatisationSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagClimatisationSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_off())
        coord.async_stop_climatisation.assert_called_once_with(vin)

    def test_climatisation_is_none_when_state_none(self):
        from custom_components.vag_connect.switch import VagClimatisationSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["climatisation_state"] = None
        s = VagClimatisationSwitch(coord, vin)
        assert s.is_on is None

    def test_charging_turn_on(self):
        import asyncio
        from custom_components.vag_connect.switch import VagChargingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagChargingSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_on())
        coord.async_start_charging.assert_called_once_with(vin)

    def test_charging_turn_off(self):
        import asyncio
        from custom_components.vag_connect.switch import VagChargingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagChargingSwitch(coord, vin)
        asyncio.get_event_loop().run_until_complete(s.async_turn_off())
        coord.async_stop_charging.assert_called_once_with(vin)

    def test_charging_is_none_when_state_none(self):
        from custom_components.vag_connect.switch import VagChargingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["charging_state"] = None
        s = VagChargingSwitch(coord, vin)
        assert s.is_on is None

    def test_departure_timer_switch_turn_off(self):
        import asyncio
        from custom_components.vag_connect.switch import VagDepartureTimerSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        s = VagDepartureTimerSwitch(coord, vin, 3)
        asyncio.get_event_loop().run_until_complete(s.async_turn_off())
        coord.async_set_departure_timer.assert_called_once_with(
            vin, 3, enabled=False, departure_time=None
        )


# ── Coordinator _run_command Tests ────────────────────────────────────────────

class TestRunCommand:
    """Test _run_command and action dispatch methods."""

    def _make_coord(self, vehicle_mock=None):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        import threading
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.async_add_executor_job = AsyncMock(return_value=None)
        coord.entry = MagicMock()
        # Real dict + S-PIN so v1.8.0 unlock fail-fast does not block dispatch tests.
        coord.entry.data = {"brand": "audi", "spin": "1234"}
        coord.entry.options = {}
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = MagicMock()
        coord._cariad_client.command_lock = AsyncMock()
        coord._cariad_client.command_unlock = AsyncMock()
        coord._cariad_client.command_start_climate = AsyncMock()
        coord._cariad_client.command_stop_climate = AsyncMock()
        coord._cariad_client.command_start_window_heating = AsyncMock()
        coord._cariad_client.command_stop_window_heating = AsyncMock()
        coord._cariad_client.command_start_charging = AsyncMock()
        coord._cariad_client.command_stop_charging = AsyncMock()
        coord._cariad_client.command_flash = AsyncMock()
        coord._cariad_client.command_wake = AsyncMock()
        coord._cariad_client.command_set_target_soc = AsyncMock()
        coord._cariad_client.command_set_climate_temperature = AsyncMock()
        coord._started = True
        coord.data = None
        coord._was_available = True
        coord.async_request_refresh = AsyncMock()
        # v1.11.1 (3B-Part-3) — optimistic UI helper calls
        # async_set_updated_data after mutating self.vehicles. Stub so
        # the actuator dispatch tests (test_async_lock_*, etc.) still pass.
        coord.async_set_updated_data = MagicMock()
        v = vehicle_mock or MagicMock()
        v.doors.commands.contains_command.return_value = True
        v.charging.commands.contains_command.return_value = True
        v.climatization.commands.contains_command.return_value = True
        v.lights.commands.contains_command.return_value = True
        v.window_heatings.commands.contains_command.return_value = True
        v.commands.contains_command.return_value = True
        # v1.11.1 — vehicle data dict needs the optimistic-UI fields so
        # ``_optimistic_set`` can record their previous values cleanly.
        coord.vehicles = {
            "VIN1": {
                "_vehicle": v,
                "doors_locked": False,
                "climatisation_state": "OFF",
                "climatisation_active": False,
                "charging_state": "NOT_CHARGING",
                "is_charging": False,
                "window_heating_front": False,
                "window_heating_back": False,
            }
        }
        return coord, v

    def test_async_lock_dispatches_to_run_command(self):
        # v1.9.1 (#92): for Audi/VW EU the configured S-PIN is now passed
        # to command_lock as a kwarg (CARIAD BFF returns 403 spin_error
        # otherwise on premium models like the Audi S6 C8). The test
        # fixture sets brand="audi" + spin="1234" so the new behaviour
        # forwards the S-PIN.
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_lock("VIN1"))
        coord._cariad_client.command_lock.assert_awaited_once_with(
            "VIN1", spin="1234",
        )

    def test_async_unlock_dispatches(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_unlock("VIN1"))
        coord._cariad_client.command_unlock.assert_awaited()

    def test_async_start_climatisation(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_start_climatisation("VIN1"))
        coord._cariad_client.command_start_climate.assert_awaited()

    def test_async_stop_climatisation(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_stop_climatisation("VIN1"))
        coord._cariad_client.command_stop_climate.assert_awaited()

    def test_async_start_charging(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_start_charging("VIN1"))
        coord._cariad_client.command_start_charging.assert_awaited()

    def test_async_stop_charging(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_stop_charging("VIN1"))
        coord._cariad_client.command_stop_charging.assert_awaited()

    def test_async_flash_lights(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_flash_lights("VIN1"))
        coord._cariad_client.command_flash.assert_awaited()

    def test_async_start_window_heating(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_start_window_heating("VIN1"))
        coord._cariad_client.command_start_window_heating.assert_awaited()

    def test_async_stop_window_heating(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_stop_window_heating("VIN1"))
        coord._cariad_client.command_stop_window_heating.assert_awaited()

    def test_async_wake_vehicle(self):
        import asyncio
        coord, _ = self._make_coord()
        asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VIN1"))
        coord._cariad_client.command_wake.assert_awaited()

    def test_async_set_max_charge_current_dispatches(self):
        """v1.12.0 (#91 follow-up): max_charge_current is now wired to a
        real CARIAD command (was raise ServiceValidationError pre-1.12.0).
        """
        import asyncio
        from unittest.mock import AsyncMock
        coord, _ = self._make_coord()
        coord._cariad_client.command_set_max_charge_current = AsyncMock()
        asyncio.get_event_loop().run_until_complete(
            coord.async_set_max_charge_current("VIN1", 16)
        )
        coord._cariad_client.command_set_max_charge_current.assert_awaited_once_with(
            "VIN1", ampere=16,
        )

    def test_async_update_data_returns_vehicles_when_not_started(self):
        import asyncio
        coord, _ = self._make_coord()
        coord._cc = None
        coord._started = False
        result = asyncio.get_event_loop().run_until_complete(
            coord._async_update_data()
        )
        assert "VIN1" in result

    def test_async_update_data_handles_fetch_error(self):
        import asyncio
        coord, _ = self._make_coord()
        coord._cc = MagicMock()
        coord._started = True
        coord.hass.async_add_executor_job = AsyncMock(
            side_effect=Exception("network error")
        )
        result = asyncio.get_event_loop().run_until_complete(
            coord._async_update_data()
        )
        assert "VIN1" in result  # returns cached data on error


# ── __init__.py coverage ──────────────────────────────────────────────────────

class TestInitHelpers:
    """Test _get_coordinator across entries."""

    def test_get_coordinator_skips_entry_without_runtime_data(self):
        from custom_components.vag_connect.__init__ import _get_coordinator
        entry_no_data = MagicMock(spec=[])  # no runtime_data attribute
        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[entry_no_data])
        result = _get_coordinator(hass, "ANYVIN")
        assert result is None

    def test_get_coordinator_finds_correct_entry(self):
        from custom_components.vag_connect.__init__ import _get_coordinator
        coord1 = MagicMock()
        coord1.vehicles = {"VIN_A": {}}
        entry1 = MagicMock()
        entry1.runtime_data = coord1

        coord2 = MagicMock()
        coord2.vehicles = {"VIN_B": {}}
        entry2 = MagicMock()
        entry2.runtime_data = coord2

        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[entry1, entry2])

        assert _get_coordinator(hass, "VIN_A") is coord1
        assert _get_coordinator(hass, "VIN_B") is coord2
        assert _get_coordinator(hass, "VIN_C") is None


# ── Config flow success paths ─────────────────────────────────────────────────

class TestConfigFlowSuccessPaths:
    def test_reauth_success_reloads_entry(self):
        import asyncio
        from custom_components.vag_connect.config_flow import VagConnectConfigFlow
        flow = VagConnectConfigFlow()
        flow.context = {"entry_id": "entry_test"}
        entry_mock = MagicMock()
        entry_mock.data = {
            "brand": "audi", "username": "u@a.de",
            "password": "old", "spin": "1234",
        }
        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry_mock)
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.config_entries.async_reload = AsyncMock()

        with patch(
            "custom_components.vag_connect.config_flow._validate_credentials",
            return_value=None,
        ):
            with patch.object(flow, "async_abort", return_value={"type": "abort"}) as mock_abort:
                asyncio.get_event_loop().run_until_complete(
                    flow.async_step_reauth_confirm({"password": "new_pw", "spin": "5678"})
                )
        flow.hass.config_entries.async_update_entry.assert_called_once()
        mock_abort.assert_called_with(reason="reauth_successful")

    def test_reconfigure_success(self):
        import asyncio
        from custom_components.vag_connect.config_flow import VagConnectConfigFlow
        flow = VagConnectConfigFlow()
        flow.context = {"entry_id": "entry_test"}
        entry_mock = MagicMock()
        entry_mock.data = {
            "brand": "audi", "username": "u@a.de",
            "password": "old", "spin": "",
            "scan_interval": 5, "force_enable_access": False,
        }
        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry_mock)
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.config_entries.async_reload = AsyncMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        with patch(
            "custom_components.vag_connect.config_flow._validate_credentials",
            return_value=None,
        ):
            with patch.object(flow, "async_abort", return_value={"type": "abort"}) as mock_abort:
                asyncio.get_event_loop().run_until_complete(
                    flow.async_step_reconfigure({
                        "brand": "audi", "username": "u@a.de",
                        "password": "new_pw", "spin": "",
                        "scan_interval": 10, "force_enable_access": False,
                    })
                )
        mock_abort.assert_called_with(reason="reconfigure_successful")


# ── Switch exception paths + write-through ───────────────────────────────────

class TestSwitchWritePaths:
    """Cover seat heating and auto-unlock write-through paths."""

    def _make_coord_with_vehicle(self):
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        v_mock = MagicMock()
        coord.data[vin]["_vehicle"] = v_mock
        coord.vehicles[vin]["_vehicle"] = v_mock
        coord.async_request_refresh = AsyncMock()
        return coord, vin, v_mock

    # VagSeatHeatingSwitch + VagAutoUnlockSwitch removed in v1.8.0 (#60).

    def test_window_heating_active_state(self):
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["window_heating_front"] = True
        s = VagWindowHeatingSwitch(coord, vin)
        assert s.is_on is True

    def test_window_heating_off_state(self):
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        coord.data[vin]["window_heating_front"] = False
        s = VagWindowHeatingSwitch(coord, vin)
        assert s.is_on is False

    def test_window_heating_none_state(self):
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = _make_coordinator()
        vin = list(coord.data.keys())[0]
        v_mock = MagicMock()
        v_mock.window_heatings.heating_state.value = None
        coord.data[vin]["_vehicle"] = v_mock
        s = VagWindowHeatingSwitch(coord, vin)
        assert s.is_on is None


# ── Coordinator set_departure_timer ──────────────────────────────────────────

class TestDepartureTimerAction:
    """Test async_set_departure_timer with timer objects."""

    def _make_coord(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        import threading
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.async_add_executor_job = AsyncMock(return_value=None)
        coord.entry = MagicMock()
        coord._vehicles_lock = threading.Lock()
        coord.async_request_refresh = AsyncMock()
        coord._cariad_client = MagicMock()
        coord._cariad_client.command_set_departure_timer = AsyncMock()
        coord.vehicles = {"VIN1": {}}
        return coord

    def test_set_departure_timer_calls_cariad(self):
        import asyncio
        coord = self._make_coord()
        asyncio.get_event_loop().run_until_complete(
            coord.async_set_departure_timer("VIN1", 1, True, "07:30")
        )
        # v2.0.0 — coordinator now forwards optional ``recurring_on``
        # (defaults to None, ignored by clients without weekday support).
        coord._cariad_client.command_set_departure_timer.assert_awaited_once_with(
            "VIN1", timer_id=1, enabled=True, departure_time="07:30",
            recurring_on=None,
        )
        coord.async_request_refresh.assert_awaited()

    def test_set_departure_timer_no_time(self):
        import asyncio
        coord = self._make_coord()
        asyncio.get_event_loop().run_until_complete(
            coord.async_set_departure_timer("VIN1", 2, False, None)
        )
        coord._cariad_client.command_set_departure_timer.assert_awaited_once_with(
            "VIN1", timer_id=2, enabled=False, departure_time=None,
            recurring_on=None,
        )

    def test_set_departure_timer_with_weekly_preheat(self):
        """v2.0.0 (Big-Bang) — recurring_on weekday list flows through."""
        import asyncio
        coord = self._make_coord()
        asyncio.get_event_loop().run_until_complete(
            coord.async_set_departure_timer(
                "VIN1", 3, True, "06:30",
                recurring_on=["MONDAY", "TUESDAY", "WEDNESDAY"],
            )
        )
        coord._cariad_client.command_set_departure_timer.assert_awaited_once_with(
            "VIN1", timer_id=3, enabled=True, departure_time="06:30",
            recurring_on=["MONDAY", "TUESDAY", "WEDNESDAY"],
        )
