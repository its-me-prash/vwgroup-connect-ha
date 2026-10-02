# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1661 (@dasebi91) — an ID.7 reporting a 218 Ah traction pack at 355.8 V, with
per-cell voltages and pack temperatures, still came out ``has_battery=False``.

The drivetrain inference only ever asked for SoC, electric range or charging
state, and this car's portal feed carries none of the three, so the whole EV
entity set stayed hidden. The reporter experienced that as "missing battery
SoC": the sensor was not missing a value, the car was not recognised as electric.

A pack above 60 V DC — the ECE R100 / ISO 6469 high-voltage threshold, which no
48 V mild hybrid can reach — now counts as evidence of a drive battery on its
own. It sets ``has_battery`` only: a pack proves there is a battery, not that
there is no engine.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

E3 = "_XIX_E3V_VLAN_Connect"


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(
        _walk_fields({"eu_data_act": fields}), VehicleData(vin="X")
    )


def test_traction_pack_alone_makes_the_car_electric() -> None:
    # @dasebi91's exact situation: a pack, and no SoC / range / charging state
    d = _map({
        f"BMS_Spannung_XIX_BMS_20{E3}": "355.8 Unit_Volt",
        f"BMS_Kapazitaet_02_XIX_BMS_04{E3}": "218.2 Unit_AmperHour",
        f"BMS_IstZellspannung_hoechste_XIX_BMS_11{E3}": "3722.0 Unit_MilliVolt",
    })
    assert d.battery_soc is None
    assert d.electric_range_km is None
    assert d.has_battery is True


def test_it_does_not_claim_the_car_is_a_pure_ev() -> None:
    # a pack voltage proves a drive battery, not the absence of an engine
    d = _map({f"BMS_Spannung_XIX_BMS_20{E3}": "355.8 Unit_Volt"})
    assert d.has_battery is True
    assert d.is_electric is not True


def test_soc_path_still_declares_a_pure_ev() -> None:
    d = _map({"battery_state_report.soc": "64"})
    assert d.has_battery is True
    assert d.is_electric is True


def test_forty_eight_volt_system_is_not_a_traction_pack() -> None:
    # a mild hybrid sits below the 60 V legal threshold and must not light up
    # the EV entity set
    d = _map({f"BMS_Spannung_XIX_BMS_20{E3}": "48.2 Unit_Volt"})
    assert d.has_battery is not True


def test_threshold_boundary() -> None:
    assert _map({f"BMS_Spannung_XIX_BMS_20{E3}": "59.9 Unit_Volt"}).has_battery is not True
    assert _map({f"BMS_Spannung_XIX_BMS_20{E3}": "60.0 Unit_Volt"}).has_battery is True


def test_pack_plus_fuel_reads_as_a_hybrid_not_an_ev() -> None:
    d = _map({
        f"BMS_Spannung_XIX_BMS_20{E3}": "355.8 Unit_Volt",
        "fuel_level": "42",
    })
    assert d.has_battery is True
    assert d.has_combustion is True
    assert d.is_electric is not True


def test_no_pack_no_claim() -> None:
    d = _map({"odometer": "17110"})
    assert d.has_battery is not True
    assert d.is_electric is not True
