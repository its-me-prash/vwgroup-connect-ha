# SPDX-License-Identifier: AGPL-3.0-or-later
"""volkswagen.de values carry their own capture time as ``data_captured_at``.

The vw.de status bodies are the car's last upload, not a live reading. A parked
car answers every poll with the same values and the same
``carCapturedTimestamp``, so the poll time says nothing about the age of a
value: a battery level read a minute ago may have been measured hours earlier,
before the car was plugged in. Until now the channel counted as a live read and
its entities carried no capture time; the stamp only reached ``last_seen_at``,
the newest of all blocks for the whole car.

The mappers now record each block's stamp for the values that block set, the
merge carries it with the value, and the entity shows it like a portal value.
The bodies below have the shape seen on an MBB e-Golf, whose ``charging/status``
is refused with ``4004 missingUserConsent`` and whose battery level therefore
comes from ``fuel/status``. Numbers, times and the VIN are invented.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
    map_charging_to_vehicle_data,
    map_fuel_to_vehicle_data,
    map_maintenance_to_vehicle_data,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZAUZFW000000"

FUEL_TS = "2026-09-30T06:15:48Z"
FUEL_ISO = "2026-09-30T06:15:48+00:00"
MAINT_TS = "2026-09-30T06:15:44Z"
MAINT_ISO = "2026-09-30T06:15:44+00:00"

# fuel/status of a battery-electric MBB car: one engine node, the capture time
# beside "properties", every number a string.
FUEL_BEV = {"data": [
    {"id": "primaryEngine", "carCapturedTimestamp": FUEL_TS, "properties": [
        {"name": "engineType", "value": "electric"},
        {"name": "remainingRange_km", "value": "98"},
        {"name": "currentSOC_pct", "value": "57"},
    ]},
]}

MAINTENANCE = {"data": {
    "carCapturedTimestamp": MAINT_TS,
    "inspectionDue_days": 40,
    "inspectionDue_km": 18000,
    "mileage_km": 61234,
}}


def _charging(**blocks: dict[str, Any]) -> dict[str, Any]:
    return {"data": blocks}


class TestFuelStatus:
    def test_the_values_get_the_engine_node_stamp(self) -> None:
        d = map_fuel_to_vehicle_data(FUEL_BEV, VehicleData(vin=VIN))
        assert d.battery_soc == 57
        assert d.field_captured_ts == {
            "battery_soc": FUEL_ISO,
            "electric_range_km": FUEL_ISO,
        }

    def test_a_value_set_before_keeps_its_own_stamp(self) -> None:
        # fill-if-empty: charging/status got there first, so its value and its
        # stamp stand, and only the range is taken from fuel/status.
        d = VehicleData(vin=VIN)
        d.battery_soc = 60
        d.field_captured_ts["battery_soc"] = "2026-09-30T07:00:00+00:00"
        map_fuel_to_vehicle_data(FUEL_BEV, d)
        assert d.battery_soc == 60
        assert d.field_captured_ts["battery_soc"] == "2026-09-30T07:00:00+00:00"
        assert d.field_captured_ts["electric_range_km"] == FUEL_ISO

    def test_each_engine_has_its_own_stamp(self) -> None:
        # The plug-in hybrid list form from #1313: the combustion node carries no
        # capture time, so its values get none, while the electric one does.
        body = {"data": [
            {"id": "primaryEngine", "properties": [
                {"name": "engineType", "value": "gasoline"},
                {"name": "remainingRange_km", "value": "530"},
                {"name": "currentFuelLevel_pct", "value": "76"},
            ]},
            {"id": "secondaryEngine", "carCapturedTimestamp": FUEL_TS,
             "properties": [
                {"name": "engineType", "value": "electric"},
                {"name": "remainingRange_km", "value": "10"},
                {"name": "currentSOC_pct", "value": "23"},
             ]},
        ]}
        d = map_fuel_to_vehicle_data(body, VehicleData(vin=VIN))
        assert d.fuel_level == 76
        assert d.field_captured_ts == {
            "battery_soc": FUEL_ISO,
            "electric_range_km": FUEL_ISO,
        }

    def test_a_combustion_node_with_a_stamp_dates_its_values(self) -> None:
        body = {"data": [
            {"id": "primaryEngine", "carCapturedTimestamp": FUEL_TS,
             "properties": [
                {"name": "engineType", "value": "diesel"},
                {"name": "remainingRange_km", "value": "640"},
                {"name": "currentFuelLevel_pct", "value": "55"},
             ]},
        ]}
        d = map_fuel_to_vehicle_data(body, VehicleData(vin=VIN))
        assert d.field_captured_ts == {
            "fuel_level": FUEL_ISO,
            "combustion_range_km": FUEL_ISO,
        }

    def test_the_dict_form_has_no_stamp_and_records_none(self) -> None:
        body = {"primaryEngine": {"engineType": "electric", "currentSOC_pct": "57"}}
        d = map_fuel_to_vehicle_data(body, VehicleData(vin=VIN))
        assert d.battery_soc == 57
        assert d.field_captured_ts == {}

    def test_an_unparseable_stamp_records_none(self) -> None:
        body = {"data": [
            {"id": "primaryEngine", "carCapturedTimestamp": "not a time",
             "properties": [
                {"name": "engineType", "value": "electric"},
                {"name": "currentSOC_pct", "value": "57"},
             ]},
        ]}
        d = map_fuel_to_vehicle_data(body, VehicleData(vin=VIN))
        assert d.battery_soc == 57
        assert d.field_captured_ts == {}


class TestChargingStatus:
    def test_each_block_dates_its_own_values(self) -> None:
        body = _charging(
            batteryStatus={
                "carCapturedTimestamp": "2026-09-30T06:10:00Z",
                "currentSOC_pct": 57,
                "cruisingRangeElectric_km": 98,
                "navigationTargetSOC_pct": 80,
            },
            chargingStatus={
                "carCapturedTimestamp": "2026-09-30T06:11:00Z",
                "chargingState": "readyForCharging",
            },
            plugStatus={
                "carCapturedTimestamp": "2026-09-30T06:12:00Z",
                "plugConnectionState": "connected",
            },
        )
        d = map_charging_to_vehicle_data(body, VehicleData(vin=VIN))
        battery = "2026-09-30T06:10:00+00:00"
        assert d.field_captured_ts == {
            "battery_soc": battery,
            "electric_range_km": battery,
            "range_km": battery,
            "target_soc": battery,
            "charging_state": "2026-09-30T06:11:00+00:00",
            "plug_state": "2026-09-30T06:12:00+00:00",
        }

    def test_a_block_without_a_stamp_takes_the_body_stamp(self) -> None:
        body = {"data": {
            "carCapturedTimestamp": "2026-09-30T06:00:00Z",
            "batteryStatus": {"currentSOC_pct": 57},
        }}
        d = map_charging_to_vehicle_data(body, VehicleData(vin=VIN))
        assert d.field_captured_ts == {"battery_soc": "2026-09-30T06:00:00+00:00"}

    def test_no_stamp_anywhere_records_none(self) -> None:
        body = _charging(batteryStatus={"currentSOC_pct": 57})
        d = map_charging_to_vehicle_data(body, VehicleData(vin=VIN))
        assert d.battery_soc == 57
        assert d.field_captured_ts == {}

    def test_a_range_already_set_gets_no_stamp_from_here(self) -> None:
        d = VehicleData(vin=VIN)
        d.range_km = 120
        body = _charging(batteryStatus={
            "carCapturedTimestamp": "2026-09-30T06:10:00Z",
            "cruisingRangeElectric_km": 98,
        })
        map_charging_to_vehicle_data(body, d)
        assert d.range_km == 120
        assert "range_km" not in d.field_captured_ts
        assert d.field_captured_ts["electric_range_km"] == "2026-09-30T06:10:00+00:00"


class TestMaintenanceStatus:
    def test_the_odometer_gets_the_body_stamp(self) -> None:
        d = map_maintenance_to_vehicle_data(MAINTENANCE, VehicleData(vin=VIN))
        assert d.odometer_km == 61234
        assert d.field_captured_ts == {"odometer_km": MAINT_ISO}

    def test_no_odometer_no_stamp(self) -> None:
        body = {"data": {"carCapturedTimestamp": MAINT_TS, "inspectionDue_km": 18000}}
        d = map_maintenance_to_vehicle_data(body, VehicleData(vin=VIN))
        assert d.field_captured_ts == {}


class TestMerge:
    def test_the_live_value_brings_its_own_stamp(self) -> None:
        # The portal still holds a days-old battery level with its stamp; the
        # vw.de value supersedes it, and the stamp that survives is the vw.de one.
        portal = VehicleData(vin=VIN)
        portal.battery_soc = 33
        portal.field_captured_ts = {"battery_soc": "2026-09-25T07:15:13+00:00"}
        web = map_fuel_to_vehicle_data(FUEL_BEV, VehicleData(vin=VIN))
        merged = merge_channels([("eu_data_act", portal), ("website_authproxy", web)])
        assert merged.battery_soc == 57
        assert merged.field_sources["battery_soc"] == "website_authproxy"
        assert merged.field_captured_ts["battery_soc"] == FUEL_ISO


class TestSensorAttributes:
    def _attrs(self, vehicle: dict[str, object]) -> dict[str, Any]:
        from custom_components.vag_connect.sensor import (
            VagConnectSensor,
            VagSensorDescription,
        )
        coord = MagicMock()
        coord.data = {VIN: vehicle}
        coord.vehicles = coord.data
        coord.is_read_only = MagicMock(return_value=False)
        coord.last_update_success = True
        desc = VagSensorDescription(key="battery_level", data_key="battery_soc")
        return VagConnectSensor(coord, VIN, desc).extra_state_attributes or {}

    def test_a_stamped_vwde_value_shows_its_capture_time(self) -> None:
        attrs = self._attrs({
            "vin": VIN, "battery_soc": 57,
            "field_sources": {"battery_soc": "website_authproxy"},
            "field_captured_ts": {"battery_soc": FUEL_ISO},
        })
        assert attrs["data_captured_at"] == FUEL_ISO
        assert attrs["freshness_source"] == "point"
        assert "ambiguous_reading" not in attrs

    def test_an_unstamped_vwde_value_gets_nothing(self) -> None:
        # No stamp means no evidence either way, and vw.de has no dataset floor
        # to name, so the entity stays as it was before stamps existed.
        attrs = self._attrs({
            "vin": VIN, "battery_soc": 57,
            "field_sources": {"battery_soc": "website_authproxy"},
        })
        assert "data_captured_at" not in attrs
        assert "freshness_source" not in attrs


def _connector() -> WebsiteAuthProxyConnector:
    """A connector double that runs the real ``get_vehicle_data``."""
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c.probe_outcomes = {}
    c.mbb_eligibility = {}
    c._vin_backend = {}
    c._master_cache = {}
    c._images_cache = {}
    c.get_relations = AsyncMock(return_value=MagicMock(vehicles=[]))
    c._gdc = MagicMock(return_value="gdc")
    c.get_warning_lights = AsyncMock(return_value=None)
    c.get_last_lock_action = AsyncMock(return_value=None)
    c.get_relation_detail = AsyncMock(return_value=None)
    c._should_probe_position = MagicMock(return_value=False)
    c._should_probe_soh = MagicMock(return_value=False)
    c._should_probe_measurements = MagicMock(return_value=False)
    return c


def test_a_poll_of_an_mbb_bev_dates_its_battery_level() -> None:
    bodies = {"vwde_fuel": FUEL_BEV, "vwde_maintenance": MAINTENANCE}

    async def _side(*_a: Any, **kw: Any) -> Any:
        label = kw.get("record_as") or ""
        if label in bodies:
            return bodies[label]
        if label == "vwde_charging":
            raise AuthenticationError("vwde_charging -> HTTP 403")
        return None

    c = _connector()
    c._get_json = AsyncMock(side_effect=_side)
    d = asyncio.run(c.get_vehicle_data(VIN))
    assert d.battery_soc == 57
    assert d.odometer_km == 61234
    assert d.field_captured_ts == {
        "battery_soc": FUEL_ISO,
        "electric_range_km": FUEL_ISO,
        "odometer_km": MAINT_ISO,
    }
    # the car-wide anchor is still the newest of all blocks
    assert d.last_seen_at == FUEL_TS
