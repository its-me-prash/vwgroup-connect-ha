# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the DataPlug / plug&play cloud reader (api/plugandplay.py).

Covers the parts that are validated + deterministic: VIN → model-year decode, the
acpp snapshot → VehicleData mapping, the "VIN not enrolled" 404 → APIError, and the
tester-gated VW (wcg) login guard. No network — the HTTP layer (`_get`) is stubbed.
Synthetic VINs only (never a real one).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.api.plugandplay import (
    PlugAndPlayCloudClient,
    WCGCloudClient,
    _vin_model_year,
)
from custom_components.vag_connect.cariad.models import BRAND_AUDI_ACPP, BRAND_VW_WCG
from custom_components.vag_connect.cariad.exceptions import APIError

# Synthetic VINs (generic A5-B8 / e-Golf prefixes; position 10 = model-year code).
VIN_2009 = "WAUZZZ8T99A000000"   # pos10 = "9" → 2009
VIN_2020 = "WVWZZZAUZLW000000"   # pos10 = "L" → 2020


def _client(brand=BRAND_AUDI_ACPP) -> PlugAndPlayCloudClient:
    c = PlugAndPlayCloudClient(MagicMock(), brand, "user@example.com", "pw")
    c._tokens = MagicMock(access_token="fake-access-token")
    return c


def _stub_get(client, responses):
    """Replace client._get with a canned dispatcher: path -> (status, body)."""
    async def fake_get(path):
        return responses.get(path, (404, {"message": f"No static resource {path}"}))
    client._get = fake_get  # type: ignore[assignment]


def test_vin_model_year():
    assert _vin_model_year(VIN_2009) == 2009
    assert _vin_model_year(VIN_2020) == 2020
    assert _vin_model_year("SHORT") is None


async def test_get_status_maps_snapshot():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {
            "vehicle": {"id": 1, "vin": VIN_2009, "carPlatform": "KWP2000"},
            "odometer": 369290.4, "batteryVoltage": 11.76, "tankFuelAmount": 3.0,
        }),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": ["OIL", "TYRE"]}),
    })
    data = await c.get_status(VIN_2009)
    assert data.vin == VIN_2009
    assert data.odometer_km == 369290          # rounded from float
    assert data.has_combustion is True          # carPlatform present
    assert data.warning_count == 2
    assert data.warning_active is True
    assert data.model_year == 2009


async def test_get_status_no_warnings():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2020}": (200, {"vehicle": {"vin": VIN_2020}, "odometer": 12000}),
        f"vehicle/{VIN_2020}/warning-lights": (200, {"warningLights": []}),
    })
    data = await c.get_status(VIN_2020)
    assert data.warning_count == 0
    assert data.warning_active is False
    assert data.odometer_km == 12000


async def test_unenrolled_vin_raises():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (404, {"message": f"Vehicle with vin: '{VIN_2009}' does not exist"}),
    })
    with pytest.raises(APIError):
        await c.get_raw_snapshot(VIN_2009)


async def test_wcg_login_is_tester_gated():
    c = WCGCloudClient(MagicMock(), BRAND_VW_WCG, "user@example.com", "pw")
    assert c.API_BASE == "https://prod.wcg.cariad.digital"
    with pytest.raises(NotImplementedError):
        await c.authenticate()


# ── get_vehicles — grounded GET /vehicles (no per-user garage resource) ───────

async def test_get_vehicles_parses_the_list():
    c = _client()
    _stub_get(c, {
        "vehicles": (200, [
            {"vehicle": {"id": 1, "vin": VIN_2009, "carPlatform": "KWP2000"}, "odometer": 100},
            {"vehicle": {"id": 2, "vin": VIN_2020}},
        ]),
    })
    assert await c.get_vehicles() == [VIN_2009, VIN_2020]


async def test_get_vehicles_empty_on_unexpected_shape():
    c = _client()
    _stub_get(c, {"vehicles": (200, {"message": "not a list"})})
    assert await c.get_vehicles() == []


async def test_get_vehicles_empty_on_error():
    c = _client()
    _stub_get(c, {"vehicles": (503, "upstream down")})
    assert await c.get_vehicles() == []


# ── get_status: 12V battery + last-parking GPS ───────────────────────────────

async def test_get_status_maps_12v_and_parking_gps():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2020}": (200, {
            "vehicle": {"vin": VIN_2020}, "odometer": 1000, "batteryVoltage": 12.4}),
        f"vehicle/{VIN_2020}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2020}/last-parking-position": (
            200, {"gpsLocation": {"latitude": 48.137, "longitude": 11.575}}),
    })
    data = await c.get_status(VIN_2020)
    assert data.voltage_12v == 12.4
    assert data.latitude == 48.137
    assert data.longitude == 11.575


async def test_get_status_zero_voltage_and_null_island_ignored():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2020}": (200, {"vehicle": {"vin": VIN_2020}, "batteryVoltage": 0}),
        f"vehicle/{VIN_2020}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2020}/last-parking-position": (
            200, {"gpsLocation": {"latitude": 0, "longitude": 0}}),
    })
    data = await c.get_status(VIN_2020)
    assert data.voltage_12v is None     # a zero reading = no dongle sample
    assert data.latitude is None        # 0/0 = "null island" = no GPS fix
    assert data.longitude is None


# ── integration wiring: factory + brand registration ─────────────────────────

def test_factory_creates_acpp_client():
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
    client = CariadClientFactory.create("audi_acpp", MagicMock(), "u@e.com", "pw")
    assert isinstance(client, PlugAndPlayCloudClient)
    assert client._brand.name == "audi_acpp"


def test_audi_acpp_registered_across_wiring():
    from custom_components.vag_connect.const import BRANDS as CONST_BRANDS
    from custom_components.vag_connect.cariad.models import BRANDS as MODEL_BRANDS
    from custom_components.vag_connect.config_flow import _BRAND_OPTIONS
    assert "audi_acpp" in CONST_BRANDS
    assert "audi_acpp" in MODEL_BRANDS
    assert any(o["value"] == "audi_acpp" for o in _BRAND_OPTIONS)
