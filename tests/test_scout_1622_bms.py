# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-28 (#1622, VW E3 VLAN) — raw FlexRay BMS cell-level telemetry in
the EU Data Act export. Each value ships as "<number> Unit_<X>". Cell voltage
extremes (mV), coolant-return temp, capacity (Ah), recuperated energy (Ws→kWh)
and pack voltage (V) become new diagnostic sensors; the cell-temperature extremes
reuse the existing hv_battery_min/max_temperature_c (fill-if-empty).

The module/cell-ID index fields, the recuperation-overflow flag and the
approximate outside-temp leaf were originally HELD here because their meaning was
a guess. v4.10.0 (#1661) lifted that hold: the official V6.0 field catalogue
documents all three, so they are mapped now — see the test below.

Driven through the real _walk_fields path (payload wrapped in its ``eu_data_act``
container) so a wrong source-key spelling fails loudly (the #1439 lesson).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_VMAX = "BMS_IstZellspannung_hoechste_XIX_BMS_11_XIX_E3V_VLAN_Connect"
_VMIN = "BMS_IstZellspannung_niedrigste_XIX_BMS_11_XIX_E3V_VLAN_Connect"
_TMAX = "BMS_IstTemperatur_hoechste_XIX_BMS_11_XIX_E3V_VLAN_Connect"
_TMIN = "BMS_IstTemperatur_niedrigste_XIX_BMS_11_XIX_E3V_VLAN_Connect"
_COOL = "BMS_RuecklaufTemperatur_XIX_BMS_25_XIX_E3V_VLAN_Connect"
_CAP = "BMS_Kapazitaet_02_XIX_BMS_04_XIX_E3V_VLAN_Connect"
_RECUP = "BMS_Rekuperation_XIX_BMS_05_XIX_E3V_VLAN_Connect"
_PACKV = "BMS_Spannung_XIX_BMS_20_XIX_E3V_VLAN_Connect"
_HELD_INDEX = "BMS_IstTemperaturMax_Modul_ID_XIX_BMS_28_XIX_E3V_VLAN_Connect"
_HELD_OVERFLOW = "BMS_Rekuperation_Ueberlauf_XIX_BMS_05_XIX_E3V_VLAN_Connect"
_HELD_BCM = "BCM1_Aussen_Temp_ungef_XIX_Klima_Sensor_02_MQB_XIX_E3V_VLAN_Connect"

_FULL = {
    _VMAX: "3652.0 Unit_MilliVolt",
    _VMIN: "3649.0 Unit_MilliVolt",
    _TMAX: "21.5 Unit_DegreCelsi",
    _TMIN: "21.0 Unit_DegreCelsi",
    _COOL: "21.5 Unit_DegreCelsi",
    _CAP: "220.20000000000002 Unit_AmperHour",
    _RECUP: "179520.0 Unit_WattSecond",
    _PACKV: "378.5 Unit_Volt",
}


def _map(fields: dict, base: VehicleData | None = None) -> VehicleData:
    return map_dataset_to_vehicle_data(
        _walk_fields({"eu_data_act": fields}), base or VehicleData(vin="X")
    )


def test_cell_voltage_extremes_stay_in_mv() -> None:
    d = _map({_VMAX: "3652.0 Unit_MilliVolt", _VMIN: "3649.0 Unit_MilliVolt"})
    assert d.hv_cell_voltage_max_mv == 3652.0
    assert d.hv_cell_voltage_min_mv == 3649.0


def test_cell_temp_reuses_hv_battery_temp_fields() -> None:
    d = _map({_TMAX: "21.5 Unit_DegreCelsi", _TMIN: "21.0 Unit_DegreCelsi"})
    assert d.hv_battery_max_temperature_c == 21.5
    assert d.hv_battery_min_temperature_c == 21.0


def test_cell_temp_is_fill_if_empty() -> None:
    # a BFF/portal pack temperature already present must win; the BMS cell temp
    # only fills a gap.
    base = VehicleData(vin="X")
    base.hv_battery_max_temperature_c = 30.0
    base.hv_battery_min_temperature_c = 28.0
    d = _map({_TMAX: "21.5 Unit_DegreCelsi", _TMIN: "21.0 Unit_DegreCelsi"}, base)
    assert d.hv_battery_max_temperature_c == 30.0
    assert d.hv_battery_min_temperature_c == 28.0


def test_coolant_capacity_recuperation_pack_voltage() -> None:
    d = _map(
        {
            _COOL: "21.5 Unit_DegreCelsi",
            _CAP: "220.20000000000002 Unit_AmperHour",
            _RECUP: "179520.0 Unit_WattSecond",
            _PACKV: "378.5 Unit_Volt",
        }
    )
    assert d.hv_battery_coolant_return_temp_c == 21.5
    assert d.hv_battery_capacity_ah == 220.2
    # 179520 Ws / 3_600_000 = 0.04986… -> rounded to 3 dp
    assert d.hv_battery_recuperation_kwh == 0.05
    assert d.hv_battery_pack_voltage_v == 378.5


def test_absent_leaves_stay_none() -> None:
    d = _map({})
    for attr in (
        "hv_cell_voltage_max_mv",
        "hv_cell_voltage_min_mv",
        "hv_battery_coolant_return_temp_c",
        "hv_battery_capacity_ah",
        "hv_battery_recuperation_kwh",
        "hv_battery_pack_voltage_v",
    ):
        assert getattr(d, attr) is None


def test_mapped_leaves_reclaimed_from_scout_surface() -> None:
    syn: dict = {}
    flat = _walk_fields({"eu_data_act": _FULL}, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    raw = d.raw_unmapped_fields or {}
    leaves = {k.rsplit(".", 1)[-1] for k in raw}
    for leaf in _FULL:
        assert leaf not in leaves, f"{leaf} still floods the Scout (bare twin)"
        assert f"eu_data_act.{leaf}" not in raw, f"{leaf} qualified twin still floods"


def test_the_three_former_holds_are_now_mapped() -> None:
    """v4.10.0 (#1661) — the #1622 hold on these three is lifted, deliberately.

    #1622 held them because their meaning was a guess at the time. The official
    V6.0 field catalogue arrived afterwards (@Testius007's export, archived under
    #923) and spells all three out: the ID leaves are "Nummer (ID) des Moduls/
    Sensors mit dem aktuell höchsten …", the flag is "Rekuperationleistungssignal
    … mindestens 1x übergelaufen", and the BCM leaf is the "ungefilterter Wert des
    Aussentemperatursensors".

    So this is the hold being RESOLVED, not a suppression: all three are now
    surfaced as their own diagnostic entities. Leaving them held was itself
    costing us — a held leaf is re-filed by the Scout on every single poll, which
    is how #1661's car produced 25 findings a day.
    """
    fields = {
        _HELD_INDEX: "1.0 ",
        "BMS_IstTemperaturMax_Sensor_ID_XIX_BMS_28_XIX_E3V_VLAN_Connect": "3.0 ",
        _HELD_OVERFLOW: "Ueberlauf ",
        _HELD_BCM: "18.5 Unit_DegreCelsi",
        _VMAX: "3652.0 Unit_MilliVolt",
    }
    syn: dict = {}
    flat = _walk_fields({"eu_data_act": fields}, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    assert d.hv_battery_temp_max_location == "1/3"
    assert d.hv_battery_recuperation_overflow is True
    assert d.outside_temp == 18.5
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert not leaves, f"nothing in this payload should still flood: {leaves}"


def test_a_genuinely_unmapped_leaf_still_stays_scout_visible() -> None:
    # the no-suppression policy itself is unchanged: a leaf we have NOT grounded
    # must keep being reported rather than silently dropped.
    unknown = "BMS_SomethingWeHaveNeverSeen_XIX_BMS_42_XIX_E3V_VLAN_Connect"
    syn: dict = {}
    flat = _walk_fields(
        {"eu_data_act": {unknown: "7.0 Unit_Volt", _VMAX: "3652.0 Unit_MilliVolt"}},
        None, syn,
    )
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert unknown in leaves
    assert _VMAX not in leaves  # the mapped leaf IS reclaimed
