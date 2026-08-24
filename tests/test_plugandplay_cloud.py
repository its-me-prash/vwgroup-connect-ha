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
