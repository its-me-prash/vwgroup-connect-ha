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


def _dl_page(n: int) -> str:
    """Request suffix the reader uses for logbook page ``n`` (app's limit=100)."""
    return f"driverlogs?page={n}&limit=100&returnPollData=false"


def _fl_page(n: int) -> str:
    """Request suffix the reader uses for fuel-log page ``n`` (app's limit=50)."""
    return f"?page={n}&limit=50"


DL_PAGE0 = _dl_page(0)
FL_PAGE0 = _fl_page(0)


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
            "registrationDate": "2026-08-23T16:40:06.000Z",  # user-entered details, NOT a sync stamp
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
    # registrationDate/mainCheck are user-entered vehicle details, not a sync
    # stamp; with no trip and no parking fix the data age is unknown.
    assert data.data_captured_at is None


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
        f"vehicle/{VIN_2009}/{DL_PAGE0}": (200, {"content": [
            # older trip first — the mapper must pick the newest by endTime
            {"endTime": 1788000000000, "totalTripMileage": 0.5,
             "startData": {"odometer": 369280.0}, "endData": {"odometer": 369280.5}},
            {"endTime": 1788273444410, "totalTripMileage": 1.3778710913,
             "totalTripTime": 246670,
             "startData": {"odometer": 369289.7}, "endData": {"odometer": 369291.0}},
        ]}),
        f"vehicle/{VIN_2009}/last-parking-position": (200, {
            "recordedAt": 1788289854000,
            "gpsLocation": {"latitude": 52.5163, "longitude": 13.3777},
        }),
    })
    data = await c.get_status(VIN_2009)
    assert data.odometer_km == 369291                 # precise driverlog end odo, not root 369290
    assert data.last_trip_start_odometer_km == 369290  # round(369289.7)
    assert data.last_trip_distance_km == 1.38          # rounded to 2dp
    assert data.last_trip_duration_min == 4            # 246670 ms → 4 min
    assert data.last_trip_timestamp == "2026-09-01T14:37:24.410000+00:00"
    assert data.position_captured_at == "2026-09-01T19:10:54+00:00"
    # Datenstand = the freshest real stamp; the parking fix is later than the trip end
    assert data.data_captured_at == "2026-09-01T19:10:54+00:00"
    # 1.3778710913 km in 246.67 s → 20.1 km/h, from the logbook alone
    assert data.last_trip_avg_speed_kmh == 20.1
    assert data.last_trip_avg_fuel_consumption_l_100km is None  # no reading on this trip


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


async def test_get_status_maps_ecoscore_refuel_and_score():
    import time
    future_ms = int((time.time() + 86400) * 1000)
    past_ms = 1
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009}, "odometer": 369290}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2009}/{DL_PAGE0}": (200, {"totalElements": 2, "content": [
            {"remark": "01.09.2026", "endTime": 1788273444410,
             "totalTripMileage": 1.38, "totalTripTime": 246670,
             "averageInductionAirTemperature": 24,
             "startData": {"odometer": 369289.7}, "endData": {"odometer": 369291.0},
             "ecoScore": {"ecoScore": 98}},
            {"remark": "29.08.2026", "endTime": 1788000000000,
             "totalTripMileage": 0.5, "ecoScore": {"ecoScore": 100}},
        ]}),
        f"user/fuellog/{VIN_2009}{FL_PAGE0}": (200, {"content": [
            {"createdTimestamp": 1788273155000, "amount": 21.0,
             "postFuelAmount": 24.0, "odometer": 369290.0},
        ]}),
        "user/achievements/v2": (200, {"content": [
            {"points": 3000, "expirationDate": 0},         # never expires
            {"points": 120, "expirationDate": future_ms},  # still valid
            {"points": 50, "expirationDate": past_ms},     # expired → excluded
        ]}),
    })
    data = await c.get_status(VIN_2009)
    assert data.last_trip_eco_score == 98
    assert data.last_trip_intake_air_temp_c == 24
    assert data.trip_count == 2
    assert data.last_refuel_liters_added == 21.0
    assert data.last_refuel_tank_after_l == 24.0
    assert data.last_refuel_tank_before_l == 3.0      # 24 − 21 ("von→auf")
    assert data.last_refuel_odometer_km == 369290
    assert data.score_points_total == 3120            # 3000 + 120, expired 50 dropped
    assert len(data.recent_trips) == 2                # full logbook (Priority C)
    assert data.recent_trips[0]["eco_score"] == 98    # newest first


# ── history paging — acpp serves oldest-first; the newest trips sit on the LAST page ──

def _trip(n: int, *, local: str | None = None, odo: float | None = None) -> dict:
    """Synthetic logbook entry; ``n`` orders it in time (bigger = newer)."""
    t = {"id": 1000 + n, "endTime": 1788000000000 + n * 3_600_000,
         "totalTripMileage": float(n), "remark": f"trip{n}",
         "endData": {"odometer": odo if odo is not None else 369000.0 + n}}
    if local is not None:
        t["driverLogId"] = local
    return t


def _paging_client(pages: dict[int, dict], calls: list[str]):
    """Client whose logbook is served as the given pages; records every path asked."""
    c = _client()
    responses = {
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009}, "odometer": 370680.0}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
    }
    for n, body in pages.items():
        responses[f"vehicle/{VIN_2009}/{_dl_page(n)}"] = (200, body)

    async def fake_get(path):
        calls.append(path)
        return responses.get(path, (404, {"message": f"No static resource {path}"}))
    c._get = fake_get  # type: ignore[assignment]
    return c


async def test_driverlogs_newest_trip_comes_from_the_last_page():
    # Live shape 2026-11-13: page 0 = the OLDEST entries. Reading page 0 only made the
    # reader report a trip a month old and an odometer ~900 km short.
    calls: list[str] = []
    meta = {"totalElements": 5, "totalPages": 3}
    c = _paging_client({
        0: {**meta, "content": [_trip(1), _trip(2)]},
        1: {**meta, "content": [_trip(3), _trip(4)]},
        2: {**meta, "content": [_trip(5, odo=370686.0)]},
    }, calls)
    data = await c.get_status(VIN_2009)
    assert data.odometer_km == 370686               # newest trip, not page-0's 369002
    assert data.last_trip_distance_km == 5.0
    assert data.recent_trips[0]["date"] == "trip5"
    assert data.trip_count == 5
    asked = [p for p in calls if "driverlogs" in p and "polldata" not in p]
    assert asked == [f"vehicle/{VIN_2009}/{_dl_page(n)}" for n in (0, 1, 2)]


async def test_driverlogs_page_cap_keeps_the_newest_pages():
    # 8 pages, cap 5 → page 0 (for totalPages) + the last four (4..7), never 1..3.
    calls: list[str] = []
    meta = {"totalElements": 8, "totalPages": 8}
    c = _paging_client({n: {**meta, "content": [_trip(n + 1)]} for n in range(8)}, calls)
    data = await c.get_status(VIN_2009)
    asked = [p for p in calls if "driverlogs" in p and "polldata" not in p]
    assert asked == [f"vehicle/{VIN_2009}/{_dl_page(n)}" for n in (0, 4, 5, 6, 7)]
    assert data.recent_trips[0]["date"] == "trip8"
    # not every entry was read → no dedupe possible, the server total stands
    assert data.trip_count == 8


async def test_driverlogs_failing_later_page_keeps_what_was_read():
    calls: list[str] = []
    meta = {"totalElements": 3, "totalPages": 2}
    c = _paging_client({0: {**meta, "content": [_trip(1), _trip(2)]}}, calls)  # page 1 → 404
    data = await c.get_status(VIN_2009)
    assert data.recent_trips[0]["date"] == "trip2"
    assert data.trip_count == 3                      # incomplete read → server total


async def test_driverlogs_server_duplicates_collapse_to_one_trip():
    # Live 2026-11-13: one local trip stored 8x (same driverLogId, different id).
    calls: list[str] = []
    dup = "x-coredata://synthetic/Trip/p7"
    content = [_trip(1, local="x-coredata://synthetic/Trip/p1")]
    content += [{**_trip(2, local=dup), "id": 2000 + k} for k in range(8)]
    c = _paging_client({0: {"totalElements": 9, "totalPages": 1, "content": content}}, calls)
    data = await c.get_status(VIN_2009)
    assert data.trip_count == 2
    assert [t["date"] for t in data.recent_trips] == ["trip2", "trip1"]


async def test_fuellog_newest_refuel_comes_from_the_last_page():
    c = _client()
    meta = {"totalElements": 2, "totalPages": 2}
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009}, "odometer": 370680}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"user/fuellog/{VIN_2009}{_fl_page(0)}": (200, {**meta, "content": [
            {"createdTimestamp": 1788273155000, "amount": 21.0, "postFuelAmount": 24.0,
             "odometer": 369290.0}]}),
        f"user/fuellog/{VIN_2009}{_fl_page(1)}": (200, {**meta, "content": [
            {"createdTimestamp": 1793551320000, "amount": 32.0, "postFuelAmount": 62.0,
             "odometer": 370630.0}]}),
    })
    data = await c.get_status(VIN_2009)
    assert data.last_refuel_liters_added == 32.0
    assert data.last_refuel_tank_before_l == 30.0
    assert data.last_refuel_odometer_km == 370630
    # the fill-up time feeds the shared last_refuel_at sensor (ISO, like the Škoda hook)
    assert data.last_refuel_at == "2026-11-01T16:42:00+00:00"
    # price 0.0 / empty station = the owner typed nothing in: no figures, and no
    # lone currency either (live 2026-11-13: the newest fill-up had no price)
    assert data.last_refuel_cost is None
    assert data.last_refuel_currency is None
    assert data.last_refuel_station is None


async def test_fuellog_price_and_station_when_entered():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009}, "odometer": 370680}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"user/fuellog/{VIN_2009}{_fl_page(0)}": (200, {"totalPages": 1, "content": [
            {"createdTimestamp": 1788000000000, "amount": 58.0, "postFuelAmount": 62.0,
             "price": 136.3, "currency": "eur", "stationName": "  Synthetic Station "},
            {"createdTimestamp": 1787000000000, "amount": 22.9, "postFuelAmount": 28.0,
             "price": 50.08, "currency": "EUR", "stationName": "Older"},
        ]}),
    })
    data = await c.get_status(VIN_2009)
    assert data.last_refuel_cost == 136.3                 # newest fill-up, not the older one
    assert data.last_refuel_currency == "EUR"
    assert data.last_refuel_station == "Synthetic Station"


# ── Datenstand, average speed, consumption ──

async def test_data_captured_at_ignores_user_entered_vehicle_details():
    # Live 2026-11-13: registrationDate had become the car's 2008 first registration
    # and the "Datenstand" sensor showed 2008. Both fields are user-entered details.
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {
            "vehicle": {"vin": VIN_2009}, "odometer": 370680.0,
            "registrationDate": "2008-01-01T12:00:00.000Z",
            "mainCheck": "2026-08-23T16:40:06.000Z"}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2009}/{DL_PAGE0}": (200, {"content": [
            {"id": 7, "endTime": 1793555227000, "totalTripMileage": 35.73,
             "totalTripTime": 3102000, "avgFuelConsumption": 11.195106,
             "endData": {"odometer": 370686.0}},
        ]}),
        # no parking fix → the trip end is the freshest stamp
    })
    data = await c.get_status(VIN_2009)
    assert data.data_captured_at == "2026-11-01T17:47:07+00:00"
    assert data.last_trip_avg_fuel_consumption_l_100km == 11.2
    assert data.last_trip_avg_speed_kmh == 41.5          # 35.73 km in 51.7 min


async def test_zero_consumption_is_no_reading():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009}, "odometer": 1}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2009}/{DL_PAGE0}": (200, {"content": [
            {"endTime": 1788000000000, "totalTripMileage": 0.01, "totalTripTime": 0,
             "avgFuelConsumption": 0.0},
        ]}),
    })
    data = await c.get_status(VIN_2009)
    assert data.last_trip_avg_fuel_consumption_l_100km is None
    assert data.last_trip_avg_speed_kmh is None           # zero duration → no figure


# ── polldata — per-trip time series of the newest trip ──

def _poll_path(trip_id: int, page: int = 0) -> str:
    return f"vehicle/{VIN_2009}/driverlogs/{trip_id}/polldata?page={page}&limit=300"


def _poll_client(trips: list[dict], polldata: dict[str, dict], calls: list[str]):
    """Client serving ``trips`` as the logbook; ``polldata`` (path → body) is read
    live, so a test can change it between polls."""
    c = _client()
    responses = {
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009}, "odometer": 370680.0}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        f"vehicle/{VIN_2009}/{DL_PAGE0}": (200, {
            "totalElements": len(trips), "totalPages": 1, "content": trips}),
    }

    async def fake_get(path):
        calls.append(path)
        if path in polldata:
            return (200, polldata[path])
        return responses.get(path, (404, {"message": f"No static resource {path}"}))
    c._get = fake_get  # type: ignore[assignment]
    return c


# Live shape: leading placeholder samples (all zeros, then altitude only).
_SAMPLES = [
    {"recordedAt": 1, "speed": 0.0, "engineSpeed": 0.0, "coolant": 0.0, "altitude": 0.0},
    {"recordedAt": 2, "speed": 0.0, "engineSpeed": 0.0, "coolant": 0.0, "altitude": 426.1},
    {"recordedAt": 3, "speed": 1.0, "engineSpeed": 1196.8, "coolant": 46.0, "altitude": 426.3},
    {"recordedAt": 4, "speed": 77.0, "engineSpeed": 2022.4, "coolant": 72.0, "altitude": 428.9},
    {"recordedAt": 5, "speed": 40.0, "engineSpeed": 1500.0, "coolant": 70.0, "altitude": 410.0},
]


async def test_polldata_maxima_land_on_the_newest_trip_row():
    calls: list[str] = []
    trips = [_trip(1, local="L1"), _trip(2, local="L2")]   # ids 1001, 1002
    c = _poll_client(trips, {_poll_path(1002): {
        "totalElements": 5, "totalPages": 1, "content": _SAMPLES}}, calls)
    data = await c.get_status(VIN_2009)
    row = data.recent_trips[0]
    assert row["date"] == "trip2"
    assert row["max_speed_kmh"] == 77.0
    assert row["max_engine_rpm"] == 2022
    assert row["max_coolant_c"] == 72.0
    assert "max_speed_kmh" not in data.recent_trips[1]   # only the newest trip is fetched
    assert [p for p in calls if "polldata" in p] == [_poll_path(1002)]


async def test_polldata_uses_the_highest_id_copy_of_a_duplicated_trip():
    # Live 2026-11-13: of 8 copies only the highest-id one carried samples (682).
    calls: list[str] = []
    copies = [{**_trip(5, local="DUP"), "id": 5000 + k} for k in range(8)]
    c = _poll_client(copies, {_poll_path(5007): {
        "totalElements": 5, "totalPages": 1, "content": _SAMPLES}}, calls)
    data = await c.get_status(VIN_2009)
    assert [p for p in calls if "polldata" in p] == [_poll_path(5007)]
    assert data.trip_count == 1
    assert data.recent_trips[0]["max_speed_kmh"] == 77.0


async def test_polldata_is_cached_per_trip_and_empty_is_retried_later(monkeypatch):
    import custom_components.vag_connect.cariad.api.plugandplay as pp

    clock = [1000.0]
    monkeypatch.setattr(pp.time, "monotonic", lambda: clock[0])
    calls: list[str] = []
    trips = [_trip(1, local="L1")]   # id 1001
    polldata = {_poll_path(1001): {"totalElements": 0, "totalPages": 0, "content": []}}
    c = _poll_client(trips, polldata, calls)

    def poll_calls():
        return len([p for p in calls if "polldata" in p])

    await c.get_status(VIN_2009)
    assert poll_calls() == 1
    await c.get_status(VIN_2009)                 # empty, inside the retry window
    assert poll_calls() == 1
    clock[0] += pp._POLLDATA_RETRY_S + 1         # window over, samples arrived meanwhile
    polldata[_poll_path(1001)] = {"totalElements": 5, "totalPages": 1, "content": _SAMPLES}
    data = await c.get_status(VIN_2009)
    assert poll_calls() == 2
    assert data.recent_trips[0]["max_engine_rpm"] == 2022
    clock[0] += 10 * pp._POLLDATA_RETRY_S        # a summary is final → never asked again
    await c.get_status(VIN_2009)
    assert poll_calls() == 2


def test_polldata_summary_placeholders_only_gives_nothing():
    from custom_components.vag_connect.cariad.api.plugandplay import _polldata_summary

    assert _polldata_summary(_SAMPLES[:2]) is None      # zeros + altitude-only → no maxima
    assert _polldata_summary([]) is None
    assert _polldata_summary(_SAMPLES) == {
        "max_speed_kmh": 77.0, "max_engine_rpm": 2022, "max_coolant_c": 72.0,
        # 426.1 → 428.9 stays inside the 5 m band; the drop to 410.0 counts
        "elevation_gain_m": 0, "elevation_loss_m": 16}


def test_polldata_summary_braking_elevation_smoothness_warmup():
    from custom_components.vag_connect.cariad.api.plugandplay import _polldata_summary

    m = 60_000  # one minute in ms
    rows = [
        # placeholder: not running, so its isSmooth=True must not count
        {"recordedAt": 0, "speed": 0.0, "engineSpeed": 0.0, "coolant": 0.0,
         "altitude": 0.0, "acceleration": 0.0, "isSmooth": True},
        {"recordedAt": 1 * m, "speed": 10.0, "engineSpeed": 900.0, "coolant": 40.0,
         "altitude": 400.0, "acceleration": 1.2, "isSmooth": True},
        # GPS jitter inside the band (up 3, down 2): neither gain nor loss. Summing
        # raw steps would give 14 up / 10 down instead of 12 / 8.
        {"recordedAt": 2 * m, "speed": 50.0, "engineSpeed": 1800.0, "coolant": 60.0,
         "altitude": 403.0, "acceleration": -0.4, "isSmooth": False},
        {"recordedAt": 150_000, "speed": 55.0, "engineSpeed": 1900.0, "coolant": 65.0,
         "altitude": 401.0, "acceleration": 0.1, "isSmooth": True},
        {"recordedAt": 3 * m, "speed": 60.0, "engineSpeed": 2000.0, "coolant": 75.0,
         "altitude": 412.0, "acceleration": -2.6, "isSmooth": True},
        {"recordedAt": 5 * m, "speed": 30.0, "engineSpeed": 1500.0, "coolant": 82.0,
         "altitude": 404.0, "acceleration": 0.3, "isSmooth": True},
    ]
    # shuffled input: the summary must order by recordedAt itself
    out = _polldata_summary([rows[4], rows[0], rows[5], rows[2], rows[1], rows[3]])
    assert out["max_braking_ms2"] == 2.6
    assert out["max_acceleration_ms2"] == 1.2
    assert out["elevation_gain_m"] == 12          # 400 → 412, jitter ignored
    assert out["elevation_loss_m"] == 8           # 412 → 404
    # 4 of 5 running samples; counting the placeholder too would give 83
    assert out["smooth_share_pct"] == 80
    assert out["warmup_min"] == 4.0               # 40 °C at 1 min → 82 °C at 5 min


def test_polldata_summary_warm_start_and_never_warm():
    from custom_components.vag_connect.cariad.api.plugandplay import _polldata_summary

    warm = [{"recordedAt": 1, "speed": 5.0, "coolant": 88.0},
            {"recordedAt": 2, "speed": 9.0, "coolant": 90.0}]
    assert _polldata_summary(warm)["warmup_min"] == 0.0   # already warm
    cold = [{"recordedAt": 1, "speed": 5.0, "coolant": 30.0},
            {"recordedAt": 2, "speed": 9.0, "coolant": 50.0}]
    assert "warmup_min" not in _polldata_summary(cold)    # never reached 80 °C


async def test_newest_trip_row_carries_the_ecoscore_breakdown():
    calls: list[str] = []
    eco = {"ecoScore": 92, "accelerationResult": 100, "brakeResult": 92,
           "engineSpeedResult": 100, "speedResult": 98, "coolantTemperatureResult": 100,
           "brakeNegativeCount": 1, "accelerationNegativeCount": 0}
    trips = [{**_trip(1, local="L1"), "ecoScore": {"ecoScore": 80, "brakeResult": 50}},
             {**_trip(2, local="L2"), "ecoScore": eco}]
    c = _poll_client(trips, {}, calls)
    data = await c.get_status(VIN_2009)
    row0, row1 = data.recent_trips
    assert row0["eco_braking"] == 92 and row0["eco_braking_negative_count"] == 1
    assert row0["eco_acceleration"] == 100 and row0["eco_acceleration_negative_count"] == 0
    assert "hard_brakings" not in row0     # rated intervals, not braking events
    assert row0["eco_speed"] == 98 and row0["eco_coolant"] == 100
    assert "eco_braking" not in row1                      # breakdown only on the newest


async def test_plate_and_nickname_only_when_filled_in():
    c = _client()
    _stub_get(c, {
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009},
                                      # "ZZ" is no canton: cannot be a real plate
                                      "licencePlate": " ZZ 0000 ",
                                      "vehicleNickName": "Coupé"}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
    })
    data = await c.get_status(VIN_2009)
    assert data.license_plate == "ZZ 0000"
    assert data.vehicle_nickname == "Coupé"

    c2 = _client()
    _stub_get(c2, {
        # live 2026-11-13: both are empty strings until the owner enters them
        f"vehicle/{VIN_2009}": (200, {"vehicle": {"vin": VIN_2009},
                                      "licencePlate": "", "vehicleNickName": "null"}),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
    })
    data2 = await c2.get_status(VIN_2009)
    assert data2.license_plate is None
    assert data2.vehicle_nickname is None


async def test_polldata_failure_does_not_break_the_read():
    calls: list[str] = []
    trips = [_trip(1, local="L1")]
    c = _poll_client(trips, {}, calls)            # polldata → 404
    data = await c.get_status(VIN_2009)
    assert data.recent_trips[0]["date"] == "trip1"
    assert "max_speed_kmh" not in data.recent_trips[0]


# ── announced end of the plug&play service (market configuration) ──

_MARKET_PATH = "configuration/market?ids=DEU&includeMissingTranslations=false"


def _market_client(market_answer, calls: list[str], *, kvps: str | None = "DEUA00000"):
    """Client whose car has a dealer KVPS id (market prefix) and a market answer."""
    c = _client()
    veh: dict = {"vehicle": {"vin": VIN_2009}, "odometer": 1}
    if kvps is not None:
        veh["vehicleSpecificDealer"] = {"dealer": {"kvpsId": kvps}}
    responses = {
        f"vehicle/{VIN_2009}": (200, veh),
        f"vehicle/{VIN_2009}/warning-lights": (200, {"warningLights": []}),
        _MARKET_PATH: market_answer,
    }

    async def fake_get(path):
        calls.append(path)
        return responses.get(path, (404, {"message": f"No static resource {path}"}))
    c._get = fake_get  # type: ignore[assignment]
    return c


def _shutdown_body(notification: str, end: str) -> list:
    # live shape 2026-11-13 (market DEU), other blocks trimmed
    return [{"market": "DEU", "email": "", "services": [], "link": [],
             "shutdown": {"notificationDate": notification, "shutdownDate": end,
                          "market": "DEU"}}]


async def test_service_end_date_from_the_market_configuration():
    calls: list[str] = []
    c = _market_client((200, _shutdown_body("2025-12-15", "2026-12-31")), calls)
    data = await c.get_status(VIN_2009)
    assert data.cloud_service_end_date == "2026-12-31"
    assert calls.count(_MARKET_PATH) == 1
    await c.get_status(VIN_2009)                     # within a day: from the cache
    assert calls.count(_MARKET_PATH) == 1


async def test_service_end_not_shown_before_its_notification_date():
    calls: list[str] = []
    c = _market_client((200, _shutdown_body("2999-01-01", "2999-12-31")), calls)
    data = await c.get_status(VIN_2009)
    assert data.cloud_service_end_date is None       # the app would not show it yet either


async def test_unknown_market_or_no_dealer_means_no_end_date(monkeypatch):
    import custom_components.vag_connect.cariad.api.plugandplay as pp

    clock = [9000.0]
    monkeypatch.setattr(pp.time, "monotonic", lambda: clock[0])
    calls: list[str] = []
    # live 2026-11-13: CHE → 404 "Market configuration not found"
    c = _market_client((404, {"message": "Market configuration not found"}), calls)
    data = await c.get_status(VIN_2009)
    assert data.cloud_service_end_date is None
    clock[0] += 2 * pp._POLLDATA_RETRY_S             # past the failure window, inside the day
    await c.get_status(VIN_2009)
    assert calls.count(_MARKET_PATH) == 1            # a 404 is an answer: cached for the day

    calls2: list[str] = []
    c2 = _market_client((200, _shutdown_body("2025-12-15", "2026-12-31")), calls2, kvps=None)
    data2 = await c2.get_status(VIN_2009)
    assert data2.cloud_service_end_date is None      # no dealer → no market → no guess
    assert not [p for p in calls2 if p.startswith("configuration/market")]


async def test_market_configuration_failure_is_retried_after_an_hour(monkeypatch):
    import custom_components.vag_connect.cariad.api.plugandplay as pp

    clock = [5000.0]
    monkeypatch.setattr(pp.time, "monotonic", lambda: clock[0])
    calls: list[str] = []
    c = _market_client((503, "upstream down"), calls)
    await c.get_status(VIN_2009)
    await c.get_status(VIN_2009)
    assert calls.count(_MARKET_PATH) == 1            # not hammered on every poll
    clock[0] += pp._POLLDATA_RETRY_S + 1             # an hour later, not a day
    await c.get_status(VIN_2009)
    assert calls.count(_MARKET_PATH) == 2


def test_service_end_sensor_is_a_phantom_gated_date():
    from homeassistant.components.sensor import SensorDeviceClass

    from custom_components.vag_connect import sensor as s

    desc = next(d for d in s.SENSOR_DESCRIPTIONS if d.key == "cloud_service_end_date")
    assert desc.device_class == SensorDeviceClass.DATE
    assert desc.entity_category is None              # visible, not tucked into diagnostics
    assert "cloud_service_end_date" in s._DATA_PRESENT_REQUIRED


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
