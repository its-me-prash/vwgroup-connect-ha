# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1661 (@dasebi91, VW ID.7 on ID.SW 5.6) — the #1622 raw-signal dialect again,
but a different signal set: the pack extremes arrive on BMS_28 rather than
BMS_11, and the car adds control units we had never seen deliver (HVL charge
socket, HVLE, eTM thermal management, KL climate, KBI/BCM1 cluster).

Every value below is the one the reporter's car actually sent. Names, units and
semantics are grounded in the official V6.0 portal field catalogue archived
under #923 — all 34 of this car's unmapped leaves are listed there, which is
also where the two traps in here come from: the CSO outdoor-temperature topic is
documented as KELVIN (the pre-existing deci-Kelvin path would read 290.65 K as
-244 °C) and the pack-current signal is documented as charge-positive, so the
sign must survive.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

E3 = "_XIX_E3V_VLAN_Connect"

# verbatim from the diagnostic attached to #1661
REAL = {
    f"BMS_Strom_XIX_BMS_20{E3}": "-0.599999999999909 Unit_Amper",
    f"BMS_Spannung_Zwischenkreis_XIX_BMS_20{E3}": "355.0 Unit_Volt",
    f"BMS_Verbrauch_XIX_BMS_05{E3}": "267870.0 Unit_WattSecond",
    f"BMS_Verbrauch_Ueberlauf_XIX_BMS_05{E3}": "Ueberlauf ",
    f"BMS_Rekuperation_Ueberlauf_XIX_BMS_05{E3}": "Ueberlauf ",
    f"BMS_Temperatur_XIX_BMS_25{E3}": "23.5 Unit_DegreCelsi",
    f"BMS_VorlaufTemperatur_XIX_BMS_25{E3}": "21.0 Unit_DegreCelsi",
    f"BMS_Status_Ventil1_XIX_BMS_25{E3}": "Ventil_nicht_angesteuert ",
    f"BMS_Status_Ventil2_XIX_BMS_25{E3}": "Ventil_nicht_angesteuert ",
    f"BMS_IstZellSpannungMax_Modul_ID_XIX_BMS_28{E3}": "7.0 ",
    f"BMS_IstZellSpannungMax_Zell_ID_XIX_BMS_28{E3}": "1.0 ",
    f"BMS_IstZellSpannungMin_Modul_ID_XIX_BMS_28{E3}": "12.0 ",
    f"BMS_IstZellSpannungMin_Zell_ID_XIX_BMS_28{E3}": "6.0 ",
    f"BMS_IstTemperaturMax_Modul_ID_XIX_BMS_28{E3}": "5.0 ",
    f"BMS_IstTemperaturMax_Sensor_ID_XIX_BMS_28{E3}": "1.0 ",
    f"BMS_IstTemperaturMin_Modul_ID_XIX_BMS_28{E3}": "2.0 ",
    f"BMS_IstTemperaturMin_Sensor_ID_XIX_BMS_28{E3}": "2.0 ",
    f"eTM_Pumpe1_Volumenstrom_XIX_eTM_01{E3}": "5.0 Unit_LiterPerMinut",
    f"eTM_Temperatur_1_XIX_eTM_01{E3}": "23.75 Unit_DegreCelsi",
    f"HVLE_Temperatur_XIX_IPB_03{E3}": "-40.0 Unit_DegreCelsi",
    f"HVL_Steckerstatus_XIX_HVL_01{E3}": "Init ",
    f"KBI_Aussen_Temp_gef_XIX_Temperaturen_01{E3}": "18.0 Unit_DegreCelsi",
    f"KL_Geblspng_Soll_XIX_Klima_12{E3}": "4.6000000000000005 Unit_Volt",
    f"KL_K_Status_XIX_Klima_EV_06{E3}": "Kuehlen_Innenraum_mit_HGK ",
    f"BCM1_Aussen_Temp_ungef_XIX_Klima_Sensor_02_MQB{E3}": "18.0 Unit_DegreCelsi",
    "cso_v1_drivingenvironment_outdoorTemperature_subscribe": "290.6499938964844 ",
}


def _map(fields: dict, base: VehicleData | None = None) -> VehicleData:
    return map_dataset_to_vehicle_data(
        _walk_fields({"eu_data_act": fields}), base or VehicleData(vin="X")
    )


def test_pack_current_keeps_its_sign() -> None:
    # the catalogue says charge current is positive, so a discharging pack must
    # stay negative — normalising it away would invert the reading
    assert _map(REAL).hv_battery_current_a == -0.6


def test_consumption_counter_scaled_from_watt_seconds() -> None:
    # 267870 Ws / 3.6e6 = 0.0744 kWh, same scaling as the recuperation twin
    assert _map(REAL).hv_battery_consumption_kwh == 0.074


def test_counter_overflow_flags() -> None:
    d = _map(REAL)
    assert d.hv_battery_consumption_overflow is True
    assert d.hv_battery_recuperation_overflow is True


def test_overflow_negated_form_reads_false() -> None:
    d = _map({f"BMS_Verbrauch_Ueberlauf_XIX_BMS_05{E3}": "kein_Ueberlauf "})
    assert d.hv_battery_consumption_overflow is False


def test_unrecognised_overflow_token_stays_unset() -> None:
    # the flag's job is to say whether the kWh total can be trusted, so an
    # unknown token must not be read as "counter intact"
    d = _map({f"BMS_Verbrauch_Ueberlauf_XIX_BMS_05{E3}": "Something_Else "})
    assert d.hv_battery_consumption_overflow is None


def test_thermal_readings() -> None:
    d = _map(REAL)
    assert d.battery_temp == 23.5                      # traction pack headline
    assert d.hv_battery_coolant_feed_temp_c == 21.0    # feed side
    # rounded to one decimal like every other temperature in the dialect
    assert d.hv_coolant_temp_c == 23.8                 # HV component loop
    assert d.hv_coolant_pump_flow_lpm == 5.0


def test_minus_forty_sentinel_is_never_a_temperature() -> None:
    assert _map(REAL).hv_sac_temperature_c is None
    # a real reading one step above the sentinel still maps
    d = _map({f"HVLE_Temperatur_XIX_IPB_03{E3}": "-39.5 Unit_DegreCelsi"})
    assert d.hv_sac_temperature_c == -39.5


def test_pack_extreme_locations_are_joined_pairs() -> None:
    d = _map(REAL)
    assert d.hv_cell_voltage_max_location == "7/1"
    assert d.hv_cell_voltage_min_location == "12/6"
    assert d.hv_battery_temp_max_location == "5/1"
    assert d.hv_battery_temp_min_location == "2/2"


def test_half_a_location_pair_stays_unset() -> None:
    d = _map({f"BMS_IstZellSpannungMax_Modul_ID_XIX_BMS_28{E3}": "7.0 "})
    assert d.hv_cell_voltage_max_location is None


def test_valve_and_climate_states() -> None:
    d = _map(REAL)
    assert d.hv_battery_valve_1_state == "Ventil_nicht_angesteuert"
    assert d.hv_battery_valve_2_state == "Ventil_nicht_angesteuert"
    assert d.climate_heatpump_state == "Kuehlen_Innenraum_mit_HGK"
    assert d.climate_blower_target_v == 4.6


def test_uninitialised_plug_status_is_not_read_as_unplugged() -> None:
    # "Init" means the signal has not been initialised. Reporting that as "no
    # cable" would be a confident wrong answer.
    assert _map(REAL).plug_connected is None


def test_plug_status_explicit_values() -> None:
    assert _map({f"HVL_Steckerstatus_XIX_HVL_01{E3}": "gesteckt "}).plug_connected is True
    assert _map(
        {f"HVL_Steckerstatus_XIX_HVL_01{E3}": "nicht_gesteckt "}
    ).plug_connected is False


def test_terminal_voltage_fills_pack_voltage_when_absent() -> None:
    assert _map(REAL).hv_battery_pack_voltage_v == 355.0


def test_bms_spannung_still_wins_over_the_terminal_twin() -> None:
    fields = dict(REAL)
    fields[f"BMS_Spannung_XIX_BMS_20{E3}"] = "355.8 Unit_Volt"
    assert _map(fields).hv_battery_pack_voltage_v == 355.8


def test_outside_temperature_prefers_the_damped_cluster_value() -> None:
    assert _map(REAL).outside_temp == 18.0


def test_kelvin_topic_is_not_run_through_the_deci_kelvin_path() -> None:
    # 290.65 K = 17.5 °C. The pre-existing path would have produced -244 °C.
    only_kelvin = {
        "cso_v1_drivingenvironment_outdoorTemperature_subscribe": "290.6499938964844 "
    }
    assert _map(only_kelvin).outside_temp == 17.5


def test_unfiltered_sensor_is_the_last_fallback() -> None:
    only_raw = {
        f"BCM1_Aussen_Temp_ungef_XIX_Klima_Sensor_02_MQB{E3}": "18.0 Unit_DegreCelsi"
    }
    assert _map(only_raw).outside_temp == 18.0


def test_implausible_kelvin_is_ignored() -> None:
    d = _map({"cso_v1_drivingenvironment_outdoorTemperature_subscribe": "17.5 "})
    assert d.outside_temp is None


def test_brand_native_readings_always_win() -> None:
    base = VehicleData(vin="X")
    base.outside_temp = 9.5
    base.battery_temp = 30.0
    d = _map(REAL, base)
    assert d.outside_temp == 9.5
    assert d.battery_temp == 30.0


def test_every_real_leaf_is_reclaimed_from_the_scout() -> None:
    # the whole point: 25 of this car's leaves were re-filed by the Scout on
    # every poll. None of them may remain unmapped.
    syn: dict = {}
    flat = _walk_fields({"eu_data_act": REAL}, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    leftover = sorted(
        k for k in (d.raw_unmapped_fields or {})
        if k.rsplit(".", 1)[-1] in REAL or k in REAL
    )
    assert not leftover, f"still flooding the Scout: {leftover}"
