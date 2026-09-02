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

async def test_get_status_enriches_from_carport():
    # carport master-data → clean "ab Haus" model (with PS), manufacturer, and
    # the real first-delivery date; /vehicles → fuel litres.
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {
            "vehicle": {"vin": VIN_2009, "carPlatform": "KWP2000"},
            "odometer": 369290.0, "batteryVoltage": 11.76, "tankFuelAmount": 3.0,
            "registrationDate": "2026-08-23T16:40:06.000Z",  # dongle last-sync
            "mainCheck": "2026-08-23T16:40:06.000Z"}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2009}/carport": (200, {
            "brandCode": "A", "modelDesc": "A5", "engType": "TDI CR",
            "modelCode": "8T30H9",  # 3rd char "3" → Coupé (Audi sales-type)
            "fuelType": "Diesel", "power": [{"unit": "kW", "value": 176},
                                            {"unit": "hp", "value": 239}],
            "capacity": [{"unit": "ccm", "value": 2967},
                         {"unit": "ccs", "value": 2967000}],
            "engCode": "CCW", "transmissionType": "Manual",
            "transmissionCode": "KMU",
            "interiorColor": "black/black-black/black/star silver",
            "deliveryDate": "1219795200000",  # 2008-08-27
            "exteriorColor": "Phantom Black Pearlescent", "torque": 500,
            "cylinderCount": 6, "warranty": "1282867200000"}),  # 2010-08-27
    })
    data = await c.get_status(VIN_2009)
    # S6 style: manufacturer + full model with the body form, power NOT in the name.
    assert data.model == "A5 Coupé TDI CR"
    assert data.manufacturer == "Audi"
    assert data.fuel_level_liters == 3.0
    assert data.registration_date == "2008-08-27"
    # bonus master-data
    assert data.exterior_color == "Phantom Black Pearlescent"
    assert data.interior_color == "black/black-black/black/star silver"
    assert data.engine_power == "176 kW / 239 PS"
    assert data.engine_torque_nm == 500
    assert data.engine_cylinders == 6
    assert data.engine_displacement_ccm == 2967
    assert data.engine_code == "CCW"
    assert data.fuel_type == "Diesel"
    assert data.transmission == "Manual (Code: KMU)"
    assert data.warranty_until == "2010-08-27"
    # "Datenstand" — the dongle's last-sync time (data freshness), not a reg date
    assert data.data_captured_at == "2026-08-23T16:40:06.000Z"


async def test_body_form_decoded_from_model_code():
    # The 3rd char of the Audi sales-type code (modelCode) → body form; distinctive
    # bodies only, everything else stays bodyless (never guess).
    cases = {
        "8T30H9": "A5 Coupé TDI",       # 3 → Coupé
        "8K50H9": "A5 Avant TDI",       # 5 → Avant
        "8F70H9": "A5 Cabriolet TDI",   # 7 → Cabriolet
        "8TA0H9": "A5 Sportback TDI",   # A → Sportback
        "8K20H9": "A5 TDI",             # 2 (sedan) → no body added
        "8R00H9": "A5 TDI",             # unknown 3rd char → bodyless
        "": "A5 TDI",                    # missing modelCode → bodyless
    }
    for code, expected in cases.items():
        c = _client()
        _stub_get(c, {
            f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009}}),
            f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
            f"vehicle/{VIN_2009}/carport": (200, {
                "brandCode": "A", "modelDesc": "A5", "engType": "TDI",
                "modelCode": code}),
        })
        data = await c.get_status(VIN_2009)
        assert data.model == expected, f"{code!r} → {data.model!r} != {expected!r}"


async def test_get_status_carport_missing_is_graceful():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2020}": (200, {"vehicle": {"vin": VIN_2020}, "odometer": 12000}),
        f"vehicle/{VIN_2020}/warning-lights": (200, {"warningLights": []}),
        # no carport stub → 404 → no model/manufacturer, but no crash
    })
    data = await c.get_status(VIN_2020)
    assert data.model is None
    assert data.manufacturer is None
    assert data.odometer_km == 12000  # the rest still maps


# ── driverlogs (trip logbook) — precise odometer + last-trip stats + freshness ──

async def test_get_status_maps_driverlog_trip_and_parking_freshness():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {
            "vehicle": {"vin": VIN_2009, "carPlatform": "KWP2000"},
            "odometer": 369290.0,  # coarse root — the driverlog end odo must win
        }),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2009}/driverlogs": (200, {"content": [
            # older trip first — the mapper must pick the newest by endTime
            {"endTime": 1788000000000, "totalTripMileage": 0.5,
             "startData": {"odometer": 369280.0}, "endData": {"odometer": 369280.5}},
            {"endTime": 1788273444410, "totalTripMileage": 1.3778710913,
             "totalTripTime": 246670,
             "startData": {"odometer": 369289.7}, "endData": {"odometer": 369291.0}},
        ]}),
        f"vehicle/{VIN_2009}/last-parking-position": (200, {
            "recordedAt": 1788289854000,
            "gpsLocation": {"latitude": 47.696, "longitude": 8.064},
        }),
    })
    data = await c.get_status(VIN_2009)
    assert data.odometer_km == 369291                 # precise driverlog end odo, not root 369290
    assert data.last_trip_start_odometer_km == 369290  # round(369289.7)
    assert data.last_trip_distance_km == 1.38          # rounded to 2dp
    assert data.last_trip_duration_min == 4            # 246670 ms → 4 min
    assert data.last_trip_timestamp == "2026-09-01T14:37:24.410000+00:00"
    assert data.position_captured_at == "2026-09-01T19:10:54+00:00"


async def test_get_status_no_driverlogs_falls_back_to_root_odometer():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2020}": (200, {"vehicle": {"vin": VIN_2020}, "odometer": 12000}),
        f"vehicle/{VIN_2020}/warning-lights": (200, {"warningLights": []}),
        # no driverlogs / no parking → those fields stay None, root odo stands
    })
    data = await c.get_status(VIN_2020)
    assert data.odometer_km == 12000
    assert data.last_trip_distance_km is None
    assert data.last_trip_timestamp is None
    assert data.position_captured_at is None


def test_epoch_ms_to_datetime():
    from custom_components.vag_connect.cariad.api.plugandplay import (
        _epoch_ms_to_datetime,
    )
    assert _epoch_ms_to_datetime("1788273444410") == "2026-09-01T14:37:24.410000+00:00"
    assert _epoch_ms_to_datetime("0") is None
    assert _epoch_ms_to_datetime(None) is None
    assert _epoch_ms_to_datetime("nope") is None


def test_epoch_ms_to_date():
    from custom_components.vag_connect.cariad.api.plugandplay import _epoch_ms_to_date
    assert _epoch_ms_to_date("1219795200000") == "2008-08-27"
    assert _epoch_ms_to_date("0") is None
    assert _epoch_ms_to_date("") is None
    assert _epoch_ms_to_date(None) is None
    assert _epoch_ms_to_date("not-a-number") is None


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
