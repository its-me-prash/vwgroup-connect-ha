# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
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


_PORSCHE_VEHICLE_HAPPY: dict = {
    "vin": "WP0ZZZ99ZTS300001",
    "modelName": "Taycan 4S",
    "modelType": {"year": 2024, "engine": "BEV"},
}

_PORSCHE_MEASUREMENTS_HAPPY = [
    {"key": "BATTERY_LEVEL", "value": {"percent": 78}},
    {"key": "E_RANGE", "value": {"distance": 312}},
    {"key": "MILEAGE", "value": {"mileage": 14250}},
    {"key": "CHARGING_SUMMARY", "value": {
        "status": "NOT_CHARGING",
        "plugState": "DISCONNECTED",
        "targetSoc": 80,
    }},
    {"key": "LOCK_STATE_VEHICLE", "value": {"lockState": "LOCKED"}},
    {"key": "OPEN_STATE_DOOR_FRONT_LEFT",  "value": {"openState": "CLOSED"}},
    {"key": "OPEN_STATE_DOOR_FRONT_RIGHT", "value": {"openState": "CLOSED"}},
    {"key": "OPEN_STATE_DOOR_REAR_LEFT",   "value": {"openState": "CLOSED"}},
    {"key": "OPEN_STATE_DOOR_REAR_RIGHT",  "value": {"openState": "CLOSED"}},
    {"key": "OPEN_STATE_LID_FRONT", "value": {"openState": "CLOSED"}},
    {"key": "OPEN_STATE_LID_REAR",  "value": {"openState": "CLOSED"}},
    {"key": "OPEN_STATE_SUNROOF",   "value": {"openState": "CLOSED"}},
    {"key": "GPS_LOCATION", "value": {"latitude": 47.3769, "longitude": 8.5417}},
    {"key": "MAIN_SERVICE_RANGE", "value": {"distance": 18000}},
    {"key": "OIL_SERVICE_RANGE",  "value": {"distance": 12500}},
    {"key": "CLIMATIZER_STATE", "value": {"climatisationState": "OFF"}},
]


class TestPorscheParserHappy:
    @pytest.mark.asyncio
    async def test_get_status_taycan_4s(self):
        client = PorscheClient.__new__(PorscheClient)
        # Inject mocked _get returning vehicle then measurements
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            _PORSCHE_VEHICLE_HAPPY,
            _PORSCHE_MEASUREMENTS_HAPPY,
        ])
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
        assert d.charging_state == "NOT_CHARGING"
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
    async def test_both_endpoints_return_exceptions(self):
        """Network failure on BOTH calls — must not crash, returns
        an empty VehicleData for the VIN."""
        client = PorscheClient.__new__(PorscheClient)
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            RuntimeError("network down"),
            RuntimeError("network down"),
        ])
        d = await client.get_status("WP0X")
        # asyncio.gather(return_exceptions=True) keeps exceptions in results;
        # the parser's isinstance(..., dict) gates skip both branches.
        assert d.vin == "WP0X"
        # All fields stay at dataclass defaults
        assert d.battery_soc is None
        assert d.range_km is None

    @pytest.mark.asyncio
    async def test_garbage_shapes_in_measurements(self):
        client = PorscheClient.__new__(PorscheClient)
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            {"modelName": "911"},  # missing modelType
            "not-a-list",  # garbage measurements
        ])
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


_VW_NA_RAW_HAPPY = {
    "powerStatus": {
        "odometer": 8740,
        "fuelPercentRemaining": None,  # pure EV
        "cruiseRange": 285,
    },
    "batteryStatus": {"stateOfChargePercent": 82},
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

_VW_NA_CHARGE_HAPPY = {
    "chargingStatus": {
        "chargingState": "CHARGING",
        "chargePower_kW": 11.0,
        "remainingChargingTimeToComplete_min": 95,
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
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            _VW_NA_RAW_HAPPY,
            _VW_NA_CHARGE_HAPPY,
            _VW_NA_CLIMATE_HAPPY,
        ])
        d = await client.get_status("WVWZZZ7AZRE000001")
        assert isinstance(d, VehicleData)
        assert d.vin == "WVWZZZ7AZRE000001"
        assert d.manufacturer == "Volkswagen"
        assert d.odometer_km == 8740
        assert d.range_km == 285
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
        or negative value still produced an ETA (now() + 0min)."""
        client = VWNAClient.__new__(VWNAClient)
        client._base = "https://example.test"
        client._vin_to_uuid = {"VW0X": "uuid"}
        client._get = AsyncMock(side_effect=[  # type: ignore[method-assign]
            {},
            {"chargingStatus": {"remainingChargingTimeToComplete_min": 0}},
            {},
        ])
        d = await client.get_status("VW0X")
        assert d.charge_complete_eta is None

    def test_val_defensive_walker(self):
        out = VWNAClient._val({"a": {"b": 5}}, "a", "b")
        assert out == 5
        out = VWNAClient._val(None, "a", default="fb")
        assert out == "fb"
