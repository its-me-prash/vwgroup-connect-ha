# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche + VW NA parser parity tests (v1.24.2 — Audit 2026-05-08).

Pre-v1.24.2 these two clients had ZERO behavioural test coverage —
only smoke import in ``test_cariad.py``. The Audit found ``get_status``
parsers (~75 LOC each) with no fixture-driven tests, while every other
brand has Skoda-style fixtures + happy/degraded test classes.

This file fills the gap with the minimum viable coverage:

- 1 happy-path test per brand (full payload, basic field assertions)
- 1 degraded-payload test per brand (missing keys, garbage shapes,
  the kind of input that crashed in production before defensive
  parsing landed)
- 1 ``_val`` defensive-walker spot test per brand

Tests use the ``importlib.util`` file-loader pattern (same as
test_v1242_property_safe_helpers.py) so they run locally without HA
installed, post v1.24.1's `requirements-test.txt + pytest.ini +
conftest.py` work.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Module loader — bypass package __init__ which imports HA.
_API_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect" / "cariad"


def _load(qualname: str, file: Path):
    spec = importlib.util.spec_from_file_location(qualname, file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = mod
    spec.loader.exec_module(mod)
    return mod


# Need to load the dependency chain manually since we can't go through
# the package init. Order matters: models → exceptions → _util → base
# → idk → porsche/vw_na.
_load("vag_pure_models", _API_ROOT / "models.py")
_load("vag_pure_exceptions", _API_ROOT / "exceptions.py")
_load("vag_pure_util", _API_ROOT / "_util.py")
# Skip base.py + idk.py — they pull in aiohttp; we don't need full
# auth machinery, only the get_status parser, which we exercise by
# constructing the client via __new__ + injecting a mocked _get.
# We still import them via the regular package path BUT under a fake
# `homeassistant` shim so the chain doesn't crash.

# Inject a no-op `homeassistant` shim if HA isn't available, so the
# `custom_components.vag_connect.__init__` chain can complete.
if "homeassistant" not in sys.modules:
    pytest.skip(
        "Porsche + VW NA tests need a homeassistant shim or full HA — "
        "running via CI; skip locally if not installed.",
        allow_module_level=True,
    )

from custom_components.vag_connect.cariad.api.porsche import PorscheClient  # noqa: E402
from custom_components.vag_connect.cariad.api.vw_na import VWNAClient  # noqa: E402
from custom_components.vag_connect.cariad.models import VehicleData  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# A) Porsche — happy + degraded
# ─────────────────────────────────────────────────────────────────────────────


# b19 (CJNE-comparison #1/#2) — single combined payload: one GET on
# /vehicles/{vin}?mf=... returns BOTH the base vehicle fields AND a
# top-level "measurements" array in the same response, confirmed against
# CJNE/pyporscheconnectapi's vehicle.py::_update_vehicle_data. Replaces the
# old two-call (vehicle + /measurements) fixture shape.
_PORSCHE_OVERVIEW_HAPPY: dict = {
    "vin": "WP0ZZZ99ZTS300001",
    "modelName": "Taycan 4S",
    "modelType": {"year": 2024, "engine": "BEV"},
    # Value member names are the REAL ones from a Taycan mf capture (public CJNE
    # ha-porscheconnect paste): isOpen / isLocked / kilometers / location string
    # — not the openState/lockState/distance/mileage/lat+long the parser once
    # guessed from the androguard enum names.
    "measurements": [
        {"key": "BATTERY_LEVEL", "value": {"percent": 78}},
        {"key": "E_RANGE", "value": {"kilometers": 312}},
        {"key": "MILEAGE", "value": {"kilometers": 14250}},
        {"key": "CHARGING_SUMMARY", "value": {
            "status": "NOT_PLUGGED",
            "targetSoC": 80,
        }},
        {"key": "LOCK_STATE_VEHICLE", "value": {"isLocked": True}},
        {"key": "OPEN_STATE_DOOR_FRONT_LEFT",  "value": {"isOpen": False}},
        {"key": "OPEN_STATE_DOOR_FRONT_RIGHT", "value": {"isOpen": False}},
        {"key": "OPEN_STATE_DOOR_REAR_LEFT",   "value": {"isOpen": False}},
        {"key": "OPEN_STATE_DOOR_REAR_RIGHT",  "value": {"isOpen": False}},
        {"key": "OPEN_STATE_LID_FRONT", "value": {"isOpen": False}},
        {"key": "OPEN_STATE_LID_REAR",  "value": {"isOpen": False}},
        {"key": "OPEN_STATE_SUNROOF",   "value": {"isOpen": False}},
        {"key": "GPS_LOCATION", "value": {"location": "47.3769,8.5417", "direction": 90}},
        {"key": "MAIN_SERVICE_RANGE", "value": {"kilometers": 18000}},
        {"key": "OIL_SERVICE_RANGE",  "value": {"kilometers": 12500}},
        {"key": "CLIMATIZER_STATE", "value": {"isOn": False}},
    ],
}


class TestPorscheParserHappy:
    @pytest.mark.asyncio
    async def test_get_status_taycan_4s(self):
        client = PorscheClient.__new__(PorscheClient)
        # Inject mocked _get returning the single combined overview payload.
        client._get = AsyncMock(  # type: ignore[method-assign]
            return_value=_PORSCHE_OVERVIEW_HAPPY,
        )
        d = await client.get_status("WP0ZZZ99ZTS300001")
        assert isinstance(d, VehicleData)
        assert d.vin == "WP0ZZZ99ZTS300001"
        assert d.model == "Taycan 4S"
        assert d.model_year == 2024
        assert d.is_electric is True
        assert d.has_battery is True
        assert d.has_combustion is False
        assert d.battery_soc == 78
        assert d.range_km == 312
        assert d.odometer_km == 14250
        assert d.charging_state == "NOT_PLUGGED"
        assert d.is_charging is False
        assert d.plug_connected is False
        assert d.target_soc == 80
        assert d.doors_locked is True
        assert d.doors_open is False
        assert d.hood_open is False
        assert d.trunk_open is False
        assert d.latitude == 47.3769
        assert d.longitude == 8.5417
        assert d.service_km == 18000
        assert d.oil_service_km == 12500
        assert d.climatisation_state == "OFF"
        assert d.climatisation_active is False
        assert d.manufacturer == "Porsche"


class TestPorscheParserDegraded:
    @pytest.mark.asyncio
    async def test_endpoint_raises(self):
        """Network failure on the single overview call — must not crash,
        returns an empty VehicleData for the VIN (b19: get_status now wraps
        the single _get call in a try/except for exactly this case)."""
        client = PorscheClient.__new__(PorscheClient)
        client._get = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("network down"),
        )
        d = await client.get_status("WP0X")
        assert d.vin == "WP0X"
        # All fields stay at dataclass defaults
        assert d.battery_soc is None
        assert d.range_km is None

    @pytest.mark.asyncio
    async def test_garbage_shapes_in_measurements(self):
        client = PorscheClient.__new__(PorscheClient)
        client._get = AsyncMock(  # type: ignore[method-assign]
            return_value={"modelName": "911", "measurements": "not-a-list"},
        )
        d = await client.get_status("WP0X")
        assert d.model == "911"
        # parser bypasses both garbage paths without raising
        assert d.battery_soc is None

    def test_val_defensive_walker(self):
        """`_val` returns default for non-dict mid-walk."""
        out = PorscheClient._val({"a": {"b": 42}}, "a", "b")
        assert out == 42
        out = PorscheClient._val({"a": "scalar"}, "a", "b", default="fallback")
        assert out == "fallback"
        out = PorscheClient._val({}, "missing", "key", default=0)
        assert out == 0


# ─────────────────────────────────────────────────────────────────────────────
# B) VW NA — happy + degraded
# ─────────────────────────────────────────────────────────────────────────────


# v2.15.3 (#503, MyVW APK DEX-verified) — RvsResponse has NO batteryStatus
# object; EV SoC/range/charged-energy live on charge/summary's BatteryStatus.
# The old fictional rvs-level ``batteryStatus.stateOfChargePercent`` was removed
# from this mock so the test exercises the real DEX shape, not a value the
# parser no longer reads. powerStatus.cruiseRange stays 285 (the RVS range read
# is real) so range_km still asserts 285.
_VW_NA_RAW_HAPPY = {
    "powerStatus": {
        "odometer": 8740,
        "fuelPercentRemaining": None,  # pure EV
        "cruiseRange": 285,
    },
    "doorStatus": {
        "overallStatus": "LOCKED",
        "frontLeftDoor": "CLOSED",
        "frontRightDoor": "CLOSED",
        "rearLeftDoor": "CLOSED",
        "rearRightDoor": "CLOSED",
        "trunk": "CLOSED",
        "hood": "CLOSED",
    },
    "windowStatus": {
        "frontLeftWindow": "CLOSED",
        "frontRightWindow": "CLOSED",
        "rearLeftWindow": "CLOSED",
        "rearRightWindow": "CLOSED",
    },
    "vehicleLocation": {"latitude": 37.7749, "longitude": -122.4194},
    "connectionStatus": {"connectionState": "CONNECTED"},
    "vehicleType": {"engine": "BEV"},
}

# v2.15.3 (#503, MyVW APK DEX-verified) — BatteryAndPlugStatusResponse carries
# sibling batteryStatus + chargingStatus + plugStatus objects. EV SoC lives in
# batteryStatus.currentSOCPct, range in batteryStatus.cruisingRange.range,
# charged energy in batteryStatus.chargeEnergy. The charge-ETA field is the BARE
# remainingChargingTimeToComplete (no ``_min`` suffix — that old name never
# matched, so the ETA silently stayed None).
_VW_NA_CHARGE_HAPPY = {
    "batteryStatus": {
        "currentSOCPct": 82,
        "cruisingRange": {"engineType": "electric", "range": 285},
        "chargeEnergy": 12.5,
    },
    "chargingStatus": {
        "chargingState": "CHARGING",
        "chargePower_kW": 11.0,
        "remainingChargingTimeToComplete": 95,
    },
    "plugStatus": {"plugConnectionState": "CONNECTED"},
    "chargingSettings": {"targetSOC_pct": 90},
}

_VW_NA_CLIMATE_HAPPY = {
    "climatisationStatus": {"climatisationState": "OFF"},
    "climatisationSettings": {"targetTemperature_K": 295.15},  # 22°C
}


class TestVWNAParserHappy:
    @pytest.mark.asyncio
    async def test_get_status_id4_2024(self):
        client = VWNAClient.__new__(VWNAClient)
        client._base = "https://example.test"
        client._vin_to_uuid = {"WVWZZZ7AZRE000001": "uuid-abc"}
        # metadata caches populated by list_vehicles in a real client; get_status
        # now threads model/nickname from them onto VehicleData.
        client._vin_to_model = {"WVWZZZ7AZRE000001": "ID.4 Pro"}
        client._vin_to_nickname = {"WVWZZZ7AZRE000001": "My ID4"}
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            _VW_NA_RAW_HAPPY,
            _VW_NA_CHARGE_HAPPY,
            _VW_NA_CLIMATE_HAPPY,
        ])
        d = await client.get_status("WVWZZZ7AZRE000001")
        assert isinstance(d, VehicleData)
        assert d.vin == "WVWZZZ7AZRE000001"
        assert d.manufacturer == "Volkswagen"
        # get_status threads the cached model + nickname (previously always None
        # for VW US/CA because the cache had zero readers).
        assert d.model == "ID.4 Pro"
        assert d.vehicle_nickname == "My ID4"
        assert d.odometer_km == 8740
        # range_km comes from powerStatus.cruiseRange (RVS, real) — still 285.
        assert d.range_km == 285
        # v2.15.3 (#503) — electric_range_km now sourced from charge/summary
        # batteryStatus.cruisingRange.range (the DEX-real EV-range location).
        assert d.electric_range_km == 285
        # v2.15.3 (#503) — SoC now sourced from charge batteryStatus.currentSOCPct
        # (RvsResponse has no batteryStatus); value unchanged at 82.
        assert d.battery_soc == 82
        assert d.has_battery is True
        assert d.is_electric is True
        assert d.is_hybrid is False
        assert d.doors_locked is True
        assert d.doors_open is False
        assert d.windows_open is False
        assert d.latitude == 37.7749
        assert d.longitude == -122.4194
        assert d.is_online is True
        assert d.charging_state == "CHARGING"
        assert d.is_charging is True
        assert d.charging_power_kw == 11.0
        assert d.plug_connected is True
        assert d.target_soc == 90
        assert d.charge_complete_eta is not None
        assert d.climatisation_state == "OFF"
        # 22 °C — round-trip through Kelvin conversion
        assert d.target_temperature == pytest.approx(22.0, abs=0.05)


class TestVWNAParserDegraded:
    @pytest.mark.asyncio
    async def test_all_endpoints_fail(self):
        client = VWNAClient.__new__(VWNAClient)
        client._base = "https://example.test"
        client._vin_to_uuid = {"VW0X": "uuid"}
        client._vin_to_model = {}
        client._vin_to_nickname = {}
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            RuntimeError("net"),
            RuntimeError("net"),
            RuntimeError("net"),
        ])
        d = await client.get_status("VW0X")
        assert d.vin == "VW0X"
        assert d.manufacturer == "Volkswagen"
        # All gates hit non-dict branch, defaults preserved
        assert d.odometer_km is None
        assert d.battery_soc is None

    @pytest.mark.asyncio
    async def test_garbage_temp_does_not_crash(self):
        """v1.24.2 fix: was bare ``float(temp_k) - 273.15`` — string
        input crashed the whole vehicle's poll. safe_float now."""
        client = VWNAClient.__new__(VWNAClient)
        client._base = "https://example.test"
        client._vin_to_uuid = {"VW0X": "uuid"}
        client._vin_to_model = {}
        client._vin_to_nickname = {}
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            {},  # empty raw
            {},  # empty charge
            {"climatisationSettings": {"targetTemperature_K": "garbage"}},
        ])
        d = await client.get_status("VW0X")
        # safe_float returns None for non-numeric — target_temperature
        # stays None, no exception raised
        assert d.target_temperature is None

    @pytest.mark.asyncio
    async def test_negative_remaining_skips_eta(self):
        """v1.24.2 fix: ``remaining > 0`` guard added. Pre-fix a 0
        or negative value still produced an ETA (now() + 0min).

        Uses the BARE ``remainingChargingTimeToComplete`` key (the name the
        parser actually reads) so a 0 genuinely re-exercises the ``>0`` guard,
        rather than the never-matched ``_min`` alias which would leave the ETA
        None for the wrong reason."""
        client = VWNAClient.__new__(VWNAClient)
        client._base = "https://example.test"
        client._vin_to_uuid = {"VW0X": "uuid"}
        client._vin_to_model = {}
        client._vin_to_nickname = {}
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            {},
            {"chargingStatus": {"remainingChargingTimeToComplete": 0}},
            {},
        ])
        d = await client.get_status("VW0X")
        assert d.charge_complete_eta is None

    def test_val_defensive_walker(self):
        out = VWNAClient._val({"a": {"b": 5}}, "a", "b")
        assert out == 5
        out = VWNAClient._val(None, "a", default="fb")
        assert out == "fb"
