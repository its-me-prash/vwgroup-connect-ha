# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1661 (@dasebi91, VW ID.7 on ID.SW 5.6) — the portal delivered 43 values of
which only 12 mapped. Ten of the remainder were whole base64-encoded UDS
diagnostic responses, and inside them sat the car's own displayed range, the
complete 12 V battery health cluster, an outside humidity sensor and the
odometer — discarded because the value looked like an opaque string.

The envelope below is the reporter's real payload, verbatim from the diagnostic
attached to the issue (PII-scanned: it carries no VIN, address or account
identifier, only measured values and firmware version strings). Dispatch is on
the DID because the official V6.0 catalogue lists 77 of these across 14 control
units, several as ``_0x1E0E_1``-style instance variants of the same DID.
"""
from __future__ import annotations

import base64
import json

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _uds_envelope,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# @dasebi91's real envelope for DID 0x2AB6, exactly as the portal delivered it.
REAL_RANGE_ENVELOPE = (
    "eyJzY2hlbWEiOiAiZGlhZ0RhdGFSZXN1bHRzX1Jlc3BvbnNlX1NjaGVtYV9WMS4zLmpzb24iLCAi"
    "UmVsZWFzZVZlcnNpb24iOiAiNC4wLjEiLCAiT3BlcmF0aW9uU3RhdHVzIjogIkNvbXBsZXRlZCIs"
    "ICJEZXNjcmlwdGlvbiI6ICJkbTRlX3ZlcjoxLjUuOC1kbTRlLCB2ZWhpY2xlX3N3X3ZlcjpJRC5T"
    "VzUuNiwgcGR4X3ZlcjpWV0U0MV8yMDI1LTA3LTE4XzBfMTA2X2QiLCAiRGlhZ25vc3RpY0RhdGEi"
    "OiBbeyJEaWFnbm9zdGljQWRkcmVzcyI6ICIxMDEwIiwgIkxvZ2ljYWxMaW5rIjogIkxMX0dhdGV3"
    "VURTIiwgIkRpYWdOb2RlU3RhdHVzIjogIlN1Y2Nlc3MiLCAiVGltZXN0YW1wIjogIjIwMjYtMTAt"
    "MDFUMDg6MDI6MzEuMTI2WiIsICJEYXRhT2JqZWN0cyI6IFt7Ik9keFBhdGgiOiAiRGlhZ25TZXJ2"
    "aV9SZWFkRGF0YUJ5SWRlbnRNZWFzdVZhbHVlLlBhcmFtX1JlY29yRGF0YUlkZW50LkNhbGN1bGF0"
    "ZWRfdmFsdWVfcmFuZ2VfZGlzcGxheSIsICJTZW1hbnRpYyI6ICJJREVOVElGSUNBVElPTiIsICJU"
    "SSI6ICIiLCAiUmVzdWx0IjogIlN1Y2Nlc3MiLCAiVmFsdWVzIjogW3siUGFyYW1TaG9ydE5hbWUi"
    "OiAiUGFyYW1fUmVjb3JEYXRhSWRlbnQiLCAiVmFsdWUiOiAiU1RSVUNfQ2FsY3VWYWx1ZVJhbmdl"
    "RGlzcGwifSwgeyJQYXJhbVNob3J0TmFtZSI6ICJQYXJhbV9NYXRjaFJlY29yRGF0YUlkZW50Iiwg"
    "IlZhbHVlIjogIjJBQjYifSwgeyJQYXJhbVNob3J0TmFtZSI6ICJQYXJhbV9EYXRhUmVjb3IiLCAi"
    "U3RydWN0dXJlIjogW3siUGFyYW1TaG9ydE5hbWUiOiAiUGFyYW1fUmFuZ2VTdW1EaXNwbCIsICJW"
    "YWx1ZSI6ICIyNDQifSwgeyJQYXJhbVNob3J0TmFtZSI6ICJQYXJhbV9SYW5nZVByaW1hRHJpdmVE"
    "aXNwbCIsICJWYWx1ZSI6ICIyNDQifSwgeyJQYXJhbVNob3J0TmFtZSI6ICJQYXJhbV9SYW5nZVNv"
    "bmNvRHJpdmVEaXNwbCIsICJWYWx1ZSI6ICIwIn0sIHsiUGFyYW1TaG9ydE5hbWUiOiAiUGFyYW1f"
    "UmFuZ2VVbml0RGlzcGwiLCAiVmFsdWUiOiAia2lsb21ldHJlIn1dfV19XX1dfQ=="
)

RANGE_KEY = (
    "LL_GatewUDS_ReadDataByIdentMeasuValue_Calculated_value_range_display_0x2AB6"
)


def _envelope(link: str, did: str, params: dict[str, object],
              *, status: str = "Success", result: str = "Success",
              ts: str = "2026-10-01T08:02:11.539Z") -> str:
    """Build an envelope in the real 1.3 schema shape and base64 it."""
    doc = {
        "schema": "diagDataResults_Response_Schema_V1.3.json",
        "OperationStatus": "Completed",
        "DiagnosticData": [{
            "DiagnosticAddress": "1046",
            "LogicalLink": link,
            "DiagNodeStatus": status,
            "Timestamp": ts,
            "DataObjects": [{
                "Semantic": "IDENTIFICATION",
                "Result": result,
                "Values": [
                    {"ParamShortName": "Param_MatchRecorDataIdent",
                     "Value": did.removeprefix("0x")},
                    {"ParamShortName": "Param_DataRecor",
                     "Structure": [
                         {"ParamShortName": k, "Value": str(v)}
                         for k, v in params.items()
                     ]},
                ],
            }],
        }],
    }
    return base64.b64encode(json.dumps(doc).encode()).decode()


def _map(raw_fields: dict[str, str], base: VehicleData | None = None) -> VehicleData:
    return map_dataset_to_vehicle_data(
        _walk_fields({"eu_data_act": raw_fields}), base or VehicleData(vin="X")
    )


# --- the decoder itself -----------------------------------------------------

def test_real_payload_decodes() -> None:
    params, captured = _uds_envelope(REAL_RANGE_ENVELOPE)
    assert params["Param_RangeSumDispl"] == "244"
    assert params["Param_RangePrimaDriveDispl"] == "244"
    assert params["Param_RangeSoncoDriveDispl"] == "0"
    assert params["Param_RangeUnitDispl"] == "kilometre"
    assert captured == "2026-10-01T08:02:31.126Z"


def test_garbage_is_fail_soft() -> None:
    for bad in (None, "", "not-base64!!", base64.b64encode(b"not json").decode(),
                base64.b64encode(b'{"DiagnosticData": "wrong type"}').decode()):
        assert _uds_envelope(bad) == ({}, None)


def test_failed_ecu_read_yields_nothing() -> None:
    # a refused/timed-out node must never look like a reading
    env = _envelope("LL_GatewUDS", "0x2AB6", {"Param_RangeSumDispl": 244},
                    status="Failed")
    assert _uds_envelope(env) == ({}, None)
    env = _envelope("LL_GatewUDS", "0x2AB6", {"Param_RangeSumDispl": 244},
                    result="Error")
    assert _uds_envelope(env)[0] == {}


# --- the mappings -----------------------------------------------------------

def test_real_payload_maps_the_displayed_range() -> None:
    d = _map({RANGE_KEY: REAL_RANGE_ENVELOPE})
    assert d.total_range_km == 244
    assert d.primary_engine_range_km == 244
    assert d.secondary_engine_range_km == 0
    # and the per-read capture time #923 asked for
    assert d.last_seen_at is not None


def test_range_ignored_when_unit_is_not_kilometres() -> None:
    env = _envelope("LL_GatewUDS", "0x2AB6", {
        "Param_RangeSumDispl": 150, "Param_RangeUnitDispl": "mile"})
    d = _map({RANGE_KEY: env})
    assert d.total_range_km is None


def test_twelve_volt_cluster_maps() -> None:
    env = _envelope("LL_GatewUDS", "0x2AF7", {
        "Param_BatteVolta": 14.638, "Param_BatteStateOfCharg": 98,
        "Param_BatteTempe": 20, "Param_BatteAgingCapac": 97,
        "Param_BatteCurre": 0.205, "Param_BatteConneState": "connected"})
    d = _map({"LL_GatewUDS_ReadDataByIdentMeasuValue_Low_voltage_battery_0x2AF7": env})
    assert d.voltage_12v == 14.64
    assert d.battery_12v_soc_pct == 98
    assert d.battery_12v_temperature_c == 20
    assert d.battery_12v_health_pct == 97
    assert d.battery_12v_current_a == 0.205


def test_twelve_volt_soc_never_becomes_traction_soc() -> None:
    # the whole point of #1661: this car has NO HV state of charge in its feed.
    # A 98 % starter battery must not be presented as a 98 % traction battery.
    env = _envelope("LL_GatewUDS", "0x2AF7", {"Param_BatteStateOfCharg": 98})
    d = _map({"LL_GatewUDS_ReadDataByIdentMeasuValue_Low_voltage_battery_0x2AF7": env})
    assert d.battery_12v_soc_pct == 98
    assert d.battery_soc is None


def test_humidity_sensor_maps() -> None:
    env = _envelope("LL_AirCondiUDS", "0x27C3", {
        "Param_DewPoint": 13.0, "Param_AirTempe": 18.9,
        "Param_SensoTempe": 23.7, "Param_RelatHumid": 51.0})
    key = "LL_AirCondiUDS_ReadDataByIdentMeasuValue_Humidity_Sensor_Outside_0x27C3"
    d = _map({key: env})
    assert d.outside_temp == 18.9
    assert d.outside_humidity_pct == 51
    assert d.outside_dew_point_c == 13.0


def test_ambient_conditions_give_the_odometer() -> None:
    env = _envelope("LL_BatteEnergContrModulUDS", "0x2BD", {
        "Param_KmMilea": 17106, "Param_Year": 2026, "Param_Month": 10})
    key = ("LL_BatteEnergContrModulUDS_ReadDataByIdentMeasuValue_"
           "Standard_ambient_conditions_0x2BD")
    assert _map({key: env}).odometer_km == 17106


def test_hv_extremes_map_with_cell_voltage_scaled_to_mv() -> None:
    pre = "LL_BatteEnergContrModulUDS_ReadDataByIdentMeasuValue_"
    d = _map({
        f"{pre}High_Voltage_Battery_Maximum_Temperature_0x1E0E": _envelope(
            "LL_BatteEnergContrModulUDS", "0x1E0E",
            {"Param_MeasuTempe": 24.5, "Param_SensoIndex": 13}),
        f"{pre}High_Voltage_Battery_Minimum_Temperature_0x1E0F": _envelope(
            "LL_BatteEnergContrModulUDS", "0x1E0F",
            {"Param_MeasuTempe": 23.5, "Param_SensoIndex": 4}),
        f"{pre}Maximum_Cell_Voltage_0x1E33": _envelope(
            "LL_BatteEnergContrModulUDS", "0x1E33",
            {"Param_CellVolta": 3.728, "Param_CellIndex": 50}),
        f"{pre}Minimum_Cell_Voltage_0x1E34": _envelope(
            "LL_BatteEnergContrModulUDS", "0x1E34",
            {"Param_CellVolta": 3.718, "Param_CellIndex": 94}),
    })
    assert d.hv_battery_max_temperature_c == 24.5
    assert d.hv_battery_min_temperature_c == 23.5
    assert d.hv_cell_voltage_max_mv == 3728.0
    assert d.hv_cell_voltage_min_mv == 3718.0


def test_instance_variant_suffix_is_still_dispatched() -> None:
    # the catalogue ships _0x1E0E_1 / _2 variants from other logical links
    key = ("LL_BatteEnergContrModulUDS_ReadDataByIdentMeasuValue_"
           "High_Voltage_Battery_Maximum_Temperature_0x1E0E_2")
    env = _envelope("LL_BatteEnergContrModulUDS", "0x1E0E",
                    {"Param_MeasuTempe": 24.5})
    assert _map({key: env}).hv_battery_max_temperature_c == 24.5


def test_out_of_range_readings_are_dropped() -> None:
    env = _envelope("LL_GatewUDS", "0x2AF7", {
        "Param_BatteVolta": 999, "Param_BatteStateOfCharg": 255,
        "Param_BatteTempe": -3000})
    d = _map({"LL_GatewUDS_ReadDataByIdentMeasuValue_Low_voltage_battery_0x2AF7": env})
    assert d.voltage_12v is None
    assert d.battery_12v_soc_pct is None
    assert d.battery_12v_temperature_c is None


def test_brand_native_values_always_win() -> None:
    base = VehicleData(vin="X")
    base.total_range_km = 300
    base.voltage_12v = 12.1
    d = _map({
        RANGE_KEY: REAL_RANGE_ENVELOPE,
        "LL_GatewUDS_ReadDataByIdentMeasuValue_Low_voltage_battery_0x2AF7":
            _envelope("LL_GatewUDS", "0x2AF7", {"Param_BatteVolta": 14.6}),
    }, base)
    assert d.total_range_km == 300
    assert d.voltage_12v == 12.1


# --- Scout interaction ------------------------------------------------------

def test_handled_envelope_is_reclaimed_from_the_scout() -> None:
    syn: dict = {}
    flat = _walk_fields({"eu_data_act": {RANGE_KEY: REAL_RANGE_ENVELOPE}}, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    assert d.total_range_km == 244
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert RANGE_KEY not in leaves


def test_unknown_did_stays_scout_visible() -> None:
    # 77 envelopes exist and we decode eight; the rest MUST keep being reported
    # rather than silently swallowed, or we would hide new data from ourselves.
    key = "LL_ThermManagUDS_ReadDataByIdentMeasuValue_Something_New_0x9999"
    syn: dict = {}
    flat = _walk_fields(
        {"eu_data_act": {key: _envelope("LL_ThermManagUDS", "0x9999", {"Param_X": 1})}},
        None, syn,
    )
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert key in leaves
