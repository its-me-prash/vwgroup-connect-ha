# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda official public API client (opt-in) — parse, commands, rate-limit.

Grounded against the live OpenAPI spec (docs/research/skoda-official-api.md). The
backend can't be reached until app v8.16 mints a key, so these tests pin the
client against the documented response + request schemas — the contract we build
to. A real key confirms it end-to-end at launch.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.api.skoda_official import SkodaOfficialClient

# A GET /api/v1/vehicles/{vin} body shaped exactly per the OpenAPI VehicleResponse.
_RESPONSE: dict[str, Any] = {
    "vehicle": {
        "vin": "TMBUNParkedEV000001",
        "name": "Enyaq",
        "licensePlate": "PR-SK 123",
        "status": {
            "overall": {
                "doorsLocked": "YES", "locked": "YES",
                "doors": "CLOSED", "windows": "OPEN", "lights": "OFF",
            },
            "detail": {"sunroof": "CLOSED", "trunk": "CLOSED", "bonnet": "OPEN"},
            "carCapturedTimestamp": "2026-08-28T09:15:00Z",
        },
        "fuelStatus": {
            "carType": "ELECTRIC",
            "totalRangeInKm": 305,
            "primaryEngineRange": {
                "engineType": "ELECTRIC",
                "currentSoCInPercent": 62,
                "remainingRangeInKm": 305,
            },
        },
        "odometer": {"mileageInKm": 41230, "carCapturedTimestamp": "2026-08-28T09:15:00Z"},
        "parkingPosition": {
            "state": "PARKED",
            "gpsCoordinates": {"latitude": 50.0755, "longitude": 14.4378},
            "formattedAddress": "Praha",
        },
        "airConditioning": {
            "state": "HEATING",
            "targetTemperature": {"value": 21.5, "unit": "CELSIUS"},
            "windowHeating": {"enabled": True, "front": "ON", "rear": "OFF"},
        },
        "charging": {
            "isVehicleInSavedLocation": True,
            "status": {
                "chargePowerInKw": 11.0,
                "remainingTimeToFullyChargedInMinutes": 90,
                "state": "CHARGING",
                "chargeType": "AC",
                "battery": {"remainingCruisingRangeInMeters": 305000, "stateOfChargeInPercent": 62},
            },
            "settings": {
                "targetStateOfChargeInPercent": 80,
                "batteryCareModeTargetValueInPercent": 80,
                "preferredChargeMode": "MANUAL",
                "maxChargeCurrentAcAmpere": 16,
            },
        },
    }
}


def test_parse_maps_the_full_vehicle():
    d = SkodaOfficialClient._parse_vehicle("TMBUNParkedEV000001", _RESPONSE["vehicle"])
    # identity
    assert d.model == "Enyaq"
    assert d.license_plate == "PR-SK 123"
    # opening / lock
    assert d.doors_locked is True          # overall doorsLocked == "YES"
    assert d.doors_open is False
    assert d.windows_open is True
    assert d.trunk_open is False            # detail.trunk == "CLOSED"
    assert d.last_seen_at == "2026-08-28T09:15:00Z"
    # odometer
    assert d.odometer_km == 41230
    # charging + battery
    assert d.is_charging is True
    assert d.charging_state == "CHARGING"
    assert d.charging_power_kw == 11.0
    assert d.battery_soc == 62
    assert d.electric_range_km == 305          # remainingCruisingRangeInMeters // 1000
    assert d.target_soc == 80
    assert d.battery_care_target_soc_pct == 80
    assert d.preferred_charge_mode == "MANUAL"
    assert d.max_charge_current == 16.0
    # climate
    assert d.climatisation_state == "HEATING"
    assert d.climatisation_active is True
    assert d.target_temperature == 21.5
    assert d.window_heating_front is True
    assert d.window_heating_back is False
    # GPS (the win over EU-DA)
    assert d.latitude == pytest.approx(50.0755)
    assert d.longitude == pytest.approx(14.4378)
    # electric classification
    assert d.is_electric is True
    assert d.is_hybrid is False


def test_parse_hybrid_classification():
    v = {"fuelStatus": {
        "primaryEngineRange": {"engineType": "GASOLINE", "currentFuelLevelInPercent": 55,
                               "remainingRangeInKm": 420},
        "secondaryEngineRange": {"engineType": "ELECTRIC", "currentSoCInPercent": 40,
                                 "remainingRangeInKm": 60},
    }}
    d = SkodaOfficialClient._parse_vehicle("V", v)
    assert d.is_hybrid is True
    assert d.is_electric is False
    assert d.primary_engine_type == "GASOLINE"
    assert d.fuel_level == 55
    assert d.combustion_range_km == 420


def test_parse_suppresses_combustion_soc_fuel_mirror():
    """#1310 (indigomejor) — on a combustion primary engine the backend mirrors the
    fuel level into currentSoCInPercent, so the official channel must apply the same
    guard as the mysmob path and NOT re-introduce the 12V=fuel mirror."""
    # combustion, SoC == fuel → suppressed (it's the fuel duplicated, not a 12V SoC)
    d = SkodaOfficialClient._parse_vehicle("V", {"fuelStatus": {"primaryEngineRange": {
        "engineType": "GASOLINE", "currentFuelLevelInPercent": 92,
        "currentSoCInPercent": 92}}})
    assert d.fuel_level == 92
    assert d.primary_engine_soc_pct is None
    # combustion, SoC != fuel → a genuinely distinct value is kept
    d2 = SkodaOfficialClient._parse_vehicle("V", {"fuelStatus": {"primaryEngineRange": {
        "engineType": "DIESEL", "currentFuelLevelInPercent": 92,
        "currentSoCInPercent": 55}}})
    assert d2.primary_engine_soc_pct == 55
    # electric primary → never a fuel mirror, kept unchanged
    d3 = SkodaOfficialClient._parse_vehicle("V", {"fuelStatus": {"primaryEngineRange": {
        "engineType": "ELECTRIC", "currentSoCInPercent": 80}}})
    assert d3.primary_engine_soc_pct == 80


def test_parse_tolerates_sparse_body():
    d = SkodaOfficialClient._parse_vehicle("V", {})
    assert d.vin == "V"
    assert d.battery_soc is None
    assert d.latitude is None


def test_grounded_enum_values_from_spec():
    """Pin the exact state strings the OpenAPI spec documents in its field
    descriptions (the fields are plain strings with no enum type). Getting these
    wrong silently mis-reports state — e.g. doorsLocked is YES/NO/OPENED, never
    'LOCKED'; AC 'ON' does not exist."""
    for val, expect in (("YES", True), ("NO", False), ("OPENED", False), ("UNKNOWN", False)):
        d = SkodaOfficialClient._parse_vehicle("V", {"status": {"overall": {"doorsLocked": val}}})
        assert d.doors_locked is expect, f"doorsLocked={val}"
    for val, expect in (
        ("HEATING", True), ("COOLING", True), ("HEATING_AUXILIARY", True),
        ("VENTILATION", True), ("OFF", False), ("COMPLETED", False), ("UNKNOWN", False),
    ):
        d = SkodaOfficialClient._parse_vehicle("V", {"airConditioning": {"state": val}})
        assert d.climatisation_active is expect, f"ac={val}"
    for val, expect in (
        ("CHARGING", True), ("CONSERVING", True), ("READY_FOR_CHARGING", False),
        ("CONNECT_CABLE", False), ("DISCHARGING", False), ("CHARGING_INTERRUPTED", False),
    ):
        d = SkodaOfficialClient._parse_vehicle("V", {"charging": {"status": {"state": val}}})
        assert d.is_charging is expect, f"charging={val}"
    for val, e_range in (("ELECTRIC", "electric_range_km"), ("GASOLINE", "combustion_range_km"),
                         ("DIESEL", "combustion_range_km"), ("CNG", "combustion_range_km")):
        d = SkodaOfficialClient._parse_vehicle(
            "V", {"fuelStatus": {"primaryEngineRange": {"engineType": val, "remainingRangeInKm": 200}}})
        assert getattr(d, e_range) == 200, f"engineType={val}"


# --- transport: a minimal fake aiohttp session ------------------------------

class _FakeResp:
    def __init__(self, status: int, body: Any, headers: dict[str, str]):
        self.status = status
        self._body = body
        self.headers = headers
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def json(self, content_type=None): return self._body
    async def text(self): return str(self._body)


class _FakeSession:
    def __init__(self, status=200, body=None, headers=None):
        self._status = status
        self._body = body if body is not None else _RESPONSE
        self._headers = headers or {"RateLimit-Remaining": "17", "RateLimit-Reset": "3600"}
        self.calls: list[dict] = []
    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        return _FakeResp(self._status, self._body, self._headers)


def _client(session, api_key="key-abc", vins="VIN1", spin="1234"):
    return SkodaOfficialClient(session, email=vins, password=api_key, spin=spin)


@pytest.mark.asyncio
async def test_get_status_sends_x_api_key_and_tracks_rate_limit():
    s = _FakeSession()
    c = _client(s)
    d = await c.get_status("VIN1")
    assert d.battery_soc == 62
    call = s.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/api/v1/vehicles/VIN1")
    assert call["headers"]["X-API-Key"] == "key-abc"
    # rate-limit budget picked up from the response headers
    assert c.rate_limit_remaining == 17
    assert c.rate_limit_reset_s == 3600


@pytest.mark.asyncio
async def test_get_vehicles_returns_configured_vins():
    c = _client(_FakeSession(), vins="vin1 , VIN2")
    assert await c.get_vehicles() == ["VIN1", "VIN2"]


@pytest.mark.asyncio
async def test_charge_and_climate_commands_hit_the_right_paths():
    s = _FakeSession(status=202, body={})
    c = _client(s)
    assert await c.command_start_charging("VIN1") is True
    assert s.calls[-1]["url"].endswith("/vehicles/VIN1/charging/start")
    assert s.calls[-1]["method"] == "POST"

    assert await c.command_start_climate("VIN1", target_c=20.0) is True
    assert s.calls[-1]["url"].endswith("/vehicles/VIN1/air-conditioning/start")
    assert s.calls[-1]["json"] == {"targetTemperature": {"value": 20.0, "unit": "CELSIUS"}}

    assert await c.command_stop_active_ventilation("VIN1") is True
    assert s.calls[-1]["url"].endswith("/vehicles/VIN1/active-ventilation/stop")


@pytest.mark.asyncio
async def test_aux_heating_requires_spin_and_sends_it():
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    # with a S-PIN → sent in the body
    s = _FakeSession(status=202, body={})
    c = _client(s, spin="4321")
    assert await c.command_start_aux_heating("VIN1", target_c=22.0) is True
    body = s.calls[-1]["json"]
    assert body["spin"] == "4321"
    assert body["targetTemperature"] == {"value": 22.0, "unit": "CELSIUS"}

    # without a S-PIN → refuses locally, never calls out
    c2 = _client(_FakeSession(), spin="")
    with pytest.raises(AuthenticationError):
        await c2.command_start_aux_heating("VIN1")


@pytest.mark.asyncio
async def test_key_rejected_raises_auth_error():
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    c = _client(_FakeSession(status=401, body={"type": "api-key-expired"}))
    with pytest.raises(AuthenticationError):
        await c.get_status("VIN1")


@pytest.mark.asyncio
async def test_climate_start_without_temp_sends_empty_body_not_none():
    # air-conditioning/start has requestBody required:true — an empty {} is a
    # valid instance but a None body omits the JSON and the server 400s.
    s = _FakeSession(status=202, body={})
    c = _client(s)
    assert await c.command_start_climate("VIN1") is True
    assert s.calls[-1]["url"].endswith("/vehicles/VIN1/air-conditioning/start")
    assert s.calls[-1]["json"] == {}          # NOT None


@pytest.mark.asyncio
async def test_rate_limit_budget_self_blocks_when_exhausted():
    # RateLimit-Remaining 0 → self-block for the reset window; over_rate_limit True.
    s = _FakeSession(headers={"RateLimit-Remaining": "0", "RateLimit-Reset": "1800"})
    c = _client(s)
    await c.get_status("VIN1")
    assert c.rate_limit_remaining == 0
    assert c.over_rate_limit is True
    # a healthy budget does not block
    s2 = _FakeSession(headers={"RateLimit-Remaining": "12", "RateLimit-Reset": "1800"})
    c2 = _client(s2)
    await c2.get_status("VIN1")
    assert c2.over_rate_limit is False


@pytest.mark.asyncio
async def test_per_vin_key_selection_with_fallback():
    # Auto-enrolled keys are VIN-bound: each VIN uses its own minted key, and a VIN
    # without one falls back to the single manual key.
    s = _FakeSession()
    c = SkodaOfficialClient(
        s, email="", password="FALLBACK", spin="",
        keys_by_vin={"VIN1": "KEY-A", "vin2": "KEY-B"})
    await c.get_status("VIN1")
    assert s.calls[-1]["headers"]["X-API-Key"] == "KEY-A"
    await c.get_status("VIN2")                       # map key is upper-cased
    assert s.calls[-1]["headers"]["X-API-Key"] == "KEY-B"
    await c.get_status("VIN9")                       # not enrolled → fallback
    assert s.calls[-1]["headers"]["X-API-Key"] == "FALLBACK"
    # the per-VIN map is itself an authoritative VIN list
    assert set(await c.get_vehicles()) == {"VIN1", "VIN2"}


@pytest.mark.asyncio
async def test_retry_after_on_429_sets_block():
    from custom_components.vag_connect.cariad.exceptions import APIError

    s = _FakeSession(status=429, body={"type": "too-many-requests"},
                     headers={"Retry-After": "600"})
    c = _client(s)
    with pytest.raises(APIError):
        await c.get_status("VIN1")
    # Retry-After was still captured (from the response, before the raise)
    assert c.retry_after_s == 600
    assert c.over_rate_limit is True
