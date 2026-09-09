# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche get_status measurement inner-value keys — corrected against a real
Taycan mf capture (a public CJNE ha-porscheconnect issue paste, corroborated
across every measurement and matching CJNE's own parsing).

The shipped parser guessed the value member names from the androguard enum
NAMES (which give the measurement KEYS, not the value members), so it read
``openState`` / ``lockState`` / ``distance`` / ``mileage`` / separate
lat+long — none of which exist. On a real Porsche those reads returned nothing
and the core sensors (doors, lock, odometer, range, GPS, climate, charge
power) were silently empty. The real shapes are ``{"isOpen": bool}`` /
``{"isLocked": bool}`` / ``{"kilometers": int}`` / ``{"isOn": bool}`` /
``{"location": "<lat>,<lng>", "direction": int}`` and chargingPower on
CHARGING_RATE.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.porsche import PorscheClient

_VIN = "WP0ZZZ99ZTS300001"


def _client() -> PorscheClient:
    return PorscheClient.__new__(PorscheClient)


async def _status(measurements: list[dict]) -> object:
    c = _client()
    c._get = AsyncMock(return_value={"measurements": measurements})
    return await c.get_status(_VIN)


# A representative slice of a real capture's shapes (synthetic values, no PII).
_REAL = [
    {"key": "BATTERY_LEVEL", "value": {"percent": 87}},
    {"key": "E_RANGE", "value": {"kilometers": 326}},
    {"key": "MILEAGE", "value": {"kilometers": 87966}},
    {"key": "LOCK_STATE_VEHICLE", "value": {"isLocked": True}},
    {"key": "OPEN_STATE_DOOR_FRONT_LEFT", "value": {"isOpen": False}},
    {"key": "OPEN_STATE_DOOR_FRONT_RIGHT", "value": {"isOpen": True}},
    {"key": "OPEN_STATE_LID_FRONT", "value": {"isOpen": False}},
    {"key": "OPEN_STATE_LID_REAR", "value": {"isOpen": True}},
    {"key": "OPEN_STATE_SUNROOF", "value": {"isOpen": False}},
    {"key": "CLIMATIZER_STATE", "value": {"isOn": True, "targetTemperature": 293.15}},
    {"key": "GPS_LOCATION", "value": {"location": "48.137154,11.576124", "direction": 249}},
    {"key": "CHARGING_SUMMARY", "value": {"status": "CHARGING", "mode": "DIRECT", "targetSoC": 85}},
    {"key": "CHARGING_RATE", "value": {"chargingPower": 6.45, "chargingRate": 0.4}},
    {"key": "MAIN_SERVICE_RANGE", "value": {"kilometers": 29934}},
]


class TestRealShapesParse:
    @pytest.mark.asyncio
    async def test_ranges_and_odometer(self) -> None:
        d = await _status(_REAL)
        assert d.battery_soc == 87
        assert d.electric_range_km == 326
        assert d.range_km == 326
        assert d.odometer_km == 87966
        assert d.service_km == 29934

    @pytest.mark.asyncio
    async def test_lock_and_openings(self) -> None:
        d = await _status(_REAL)
        assert d.doors_locked is True
        assert d.doors_open is True          # front-right is open
        assert d.hood_open is False
        assert d.trunk_open is True
        assert d.sunroof_open is False

    @pytest.mark.asyncio
    async def test_climate(self) -> None:
        d = await _status(_REAL)
        assert d.climatisation_active is True
        assert d.climatisation_state == "ON"

    @pytest.mark.asyncio
    async def test_gps_location_string_split(self) -> None:
        d = await _status(_REAL)
        assert d.latitude == pytest.approx(48.137154)
        assert d.longitude == pytest.approx(11.576124)
        assert d.heading == 249

    @pytest.mark.asyncio
    async def test_charging(self) -> None:
        d = await _status(_REAL)
        assert d.charging_state == "CHARGING"
        assert d.is_charging is True
        assert d.charging_power_kw == 6.45     # from CHARGING_RATE, not CHARGING_SUMMARY
        assert d.plug_connected is True
        assert d.plug_state == "CHARGING"
        assert d.target_soc == 85


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_not_plugged_status(self) -> None:
        d = await _status([
            {"key": "CHARGING_SUMMARY", "value": {"status": "NOT_PLUGGED"}},
        ])
        assert d.plug_connected is False
        assert d.is_charging is False

    @pytest.mark.asyncio
    async def test_missing_openings_leave_none_not_false(self) -> None:
        # No open-state blocks at all → the fields must stay unknown, not be
        # falsely reported as closed (the old ``== "OPEN"`` set them False).
        d = await _status([{"key": "BATTERY_LEVEL", "value": {"percent": 50}}])
        assert d.doors_open is None
        assert d.hood_open is None
        assert d.trunk_open is None
        assert d.sunroof_open is None
        assert d.doors_locked is None

    @pytest.mark.asyncio
    async def test_old_openstate_shape_is_ignored(self) -> None:
        # A payload in the OLD guessed shape must NOT produce a reading — proves
        # the parser no longer reads the non-existent string members.
        d = await _status([
            {"key": "OPEN_STATE_DOOR_FRONT_LEFT", "value": {"openState": "OPEN"}},
            {"key": "LOCK_STATE_VEHICLE", "value": {"lockState": "LOCKED"}},
            {"key": "MILEAGE", "value": {"mileage": 12345}},
        ])
        assert d.doors_open is None
        assert d.doors_locked is None
        assert d.odometer_km is None

    @pytest.mark.asyncio
    async def test_malformed_gps_does_not_crash(self) -> None:
        d = await _status([{"key": "GPS_LOCATION", "value": {"location": "not-a-coord"}}])
        assert d.latitude is None
        assert d.longitude is None
