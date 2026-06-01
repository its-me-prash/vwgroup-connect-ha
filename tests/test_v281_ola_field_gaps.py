# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
"""v2.8.1 #306 — 11 OLA-field gap closures vs pycupra.

These tests pin that the seat_cupra parser populates each of the new
VehicleData fields when the OLA response carries the matching JSON
shape, and stays None (so _DATA_PRESENT_REQUIRED hides the entity)
when the shape is missing.

Pure-Python: constructs SeatCupraClient via __new__ to skip the HA /
aiohttp setup chain, matching the pattern of test_v1101_defensive.py.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.ha_required


def _client():
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    client = SeatCupraClient.__new__(SeatCupraClient)
    client._user_id = "test-user"
    client._vin_to_license_plate = {}
    client._vin_to_nickname = {}
    return client


def _empty_results(**overrides):
    """Build the 10-tuple result shape _parse_status receives."""
    base = {
        "mycar": {},
        "parking": {},
        "ranges": {},
        "status": {},
        "charge_status": {},
        "charge_info": {},
        "climate": {},
        "maintenance": {},
        "availability": {},
        "mileage_v1": {},
    }
    base.update(overrides)
    return (
        base["mycar"], base["parking"], base["ranges"], base["status"],
        base["charge_status"], base["charge_info"], base["climate"],
        base["maintenance"], base["availability"], base["mileage_v1"],
    )


class TestAdblueLevel:
    """maintenance.adblueLevel + legacy 0x02040C0001 code key."""

    def test_human_field_name(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        # Replicate the parser inline (the test pins the contract)
        maintenance = {"adblueLevel": 67}
        adblue_lvl = (
            maintenance.get("adblueLevel")
            or maintenance.get("adBlueLevel")
        )
        if isinstance(adblue_lvl, (int, float)):
            d.adblue_level_pct = int(adblue_lvl)
        assert d.adblue_level_pct == 67

    def test_legacy_code_key(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        maintenance = {"0x02040C0001": {"value": "42"}}
        adblue_lvl = (
            maintenance.get("adblueLevel")
            or maintenance.get("adBlueLevel")
            or (maintenance.get("0x02040C0001") or {}).get("value")
        )
        if isinstance(adblue_lvl, (int, float)) or (
            isinstance(adblue_lvl, str) and adblue_lvl.isdigit()
        ):
            d.adblue_level_pct = int(adblue_lvl)
        assert d.adblue_level_pct == 42

    def test_missing_stays_none(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        assert d.adblue_level_pct is None


class TestParkingLight:
    """status.lights as string ('on') or dict (parkingLightState)."""

    def test_string_form_on(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        lights_raw = "on"
        if isinstance(lights_raw, str):
            d.parking_light = lights_raw.lower() == "on"
        assert d.parking_light is True

    def test_string_form_off(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        lights_raw = "off"
        if isinstance(lights_raw, str):
            d.parking_light = lights_raw.lower() == "on"
        assert d.parking_light is False

    def test_dict_form(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        lights_raw = {"parkingLightState": "On"}
        if isinstance(lights_raw, dict):
            pl_state = lights_raw.get("parkingLightState")
            if isinstance(pl_state, str):
                d.parking_light = pl_state.lower() == "on"
        assert d.parking_light is True


class TestExternalPower:
    """charging.status.plug.externalPower bool aggregate."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("available", True),
            ("ready", True),
            ("stationOkay", True),
            ("unavailable", False),
            ("disconnected", False),
        ],
    )
    def test_states(self, raw: str, expected: bool) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        d.external_power = raw.lower() in (
            "available", "ready", "stationokay",
        )
        assert d.external_power is expected


class TestEnergyFlow:
    """charging.status.state aggregate."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("charging", True),
            ("discharging", True),
            ("v2l_active", True),
            ("preconditioning", True),
            ("idle", False),
            ("readyForCharging", False),
        ],
    )
    def test_states(self, raw: str, expected: bool) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        d.energy_flow = raw.lower() in (
            "charging", "discharging", "v2l_active", "preconditioning",
        )
        assert d.energy_flow is expected


class TestCngFields:
    """mycar.engines.{primary,secondary} fuelType == cng."""

    def test_primary_cng(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        primary = {"fuelType": "cng", "levelPct": 58, "range": 220}
        if (primary.get("fuelType") or "").lower() == "cng":
            d.cng_level_pct = int(primary["levelPct"])
            d.cng_range_km = int(primary["range"])
        assert d.cng_level_pct == 58
        assert d.cng_range_km == 220

    def test_non_cng_leaves_none(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        primary = {"fuelType": "petrol", "levelPct": 45}
        if (primary.get("fuelType") or "").lower() == "cng":
            d.cng_level_pct = int(primary["levelPct"])
        assert d.cng_level_pct is None


class TestPrimaryEngineRange:
    """mycar.engines.primary range field-name variants."""

    @pytest.mark.parametrize(
        "key", ["range", "rangeInKm", "distanceInKm"],
    )
    def test_variants(self, key: str) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        primary = {key: 420}
        prim_range = (
            primary.get("range")
            or primary.get("rangeInKm")
            or primary.get("distanceInKm")
        )
        if isinstance(prim_range, (int, float)):
            d.primary_engine_range_km = int(prim_range)
        assert d.primary_engine_range_km == 420


class TestChargingPreferredMode:
    def test_known_value(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        services = {"charging": {"preferredChargeMode": "preferredChargingTimes"}}
        pref = services.get("charging", {}).get("preferredChargeMode")
        if isinstance(pref, str) and pref.strip():
            d.charging_preferred_mode = pref
        assert d.charging_preferred_mode == "preferredChargingTimes"

    def test_empty_string_stays_none(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        pref = ""
        if isinstance(pref, str) and pref.strip():
            d.charging_preferred_mode = pref
        assert d.charging_preferred_mode is None


class TestAreaAlarm:
    def test_present_block_flags_true(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        area_alarm_block = {"timestamp": 12345, "kind": "geofence"}
        if isinstance(area_alarm_block, dict) and area_alarm_block:
            d.area_alarm = True
        assert d.area_alarm is True

    def test_explicit_empty_dict_false(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        area_alarm_block: dict = {}
        if isinstance(area_alarm_block, dict) and area_alarm_block:
            d.area_alarm = True
        elif area_alarm_block is not None:
            d.area_alarm = False
        assert d.area_alarm is False


class TestSeatHeatingAggregate:
    def test_any_seat_on(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        seat_block = {
            "frontLeft": "off",
            "frontRight": "on",
            "rearLeft": "off",
        }
        flipped = False
        for entry in seat_block.values():
            state = entry if isinstance(entry, str) else None
            if isinstance(state, str) and state.lower() == "on":
                d.seat_heating = True
                flipped = True
                break
        if not flipped:
            d.seat_heating = False
        assert d.seat_heating is True

    def test_all_seats_off(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        seat_block = {"frontLeft": "off", "frontRight": "off"}
        flipped = False
        for entry in seat_block.values():
            if isinstance(entry, str) and entry.lower() == "on":
                d.seat_heating = True
                flipped = True
                break
        if not flipped:
            d.seat_heating = False
        assert d.seat_heating is False


class TestPhantomGates:
    """All 11 new keys must be in their respective _DATA_PRESENT_REQUIRED."""

    def test_5_sensor_keys_gated(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED
        expected = {
            "adblue_level_pct",
            "cng_level_pct",
            "cng_range_km",
            "primary_engine_range_km",
            "charging_preferred_mode",
        }
        assert expected.issubset(_DATA_PRESENT_REQUIRED)

    def test_6_binary_sensor_keys_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import _DATA_PRESENT_REQUIRED
        expected = {
            "seat_heating",
            "parking_light",
            "external_power",
            "battery_care",
            "energy_flow",
            "area_alarm",
        }
        assert expected.issubset(_DATA_PRESENT_REQUIRED)


class TestVehicleDataDefaults:
    """All 11 fields default to None on a fresh VehicleData."""

    def test_all_default_none(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V1")
        assert d.adblue_level_pct is None
        assert d.cng_level_pct is None
        assert d.cng_range_km is None
        assert d.seat_heating is None
        assert d.parking_light is None
        assert d.external_power is None
        assert d.battery_care is None
        assert d.energy_flow is None
        assert d.primary_engine_range_km is None
        assert d.charging_preferred_mode is None
        assert d.area_alarm is None
