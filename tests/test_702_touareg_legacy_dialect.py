# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#702 — Touareg-era legacy Car-Net export read as "no vehicle data at all".

The Touareg CR eHybrid (2021) ships its portal export as a flat
`{dataFieldName, value}` dataset whose names are fully qualified
(`RBC.vehicleStates.[0].soc`, `RPC.climaterSettings.[0].targetTemperature`, …)
with NO bare-leaf twin. The walker reads the points fine, but none of the
canonical lookups matched, so a car with a perfectly good SoC in the payload
surfaced completely empty — reporter had live data in the official app and
nothing here.

Two shapes in this dialect differ from the modern portal and are the reason the
aliases can't simply ride the existing lookups:

* `charging` is a BOOLEAN, not the VW state enum — feeding it to the enum
  lookup would make a *charging* car read as not-charging ("true" is not in
  ("charging", "chargingacactive", "active")).
* `targetTemperature` is deci-Kelvin (2930 = 19.85 °C), like the ambient and
  HV-battery temps already handled.

Canonical sources must always win; the legacy aliases only widen coverage for
cars that carry nothing else.

SCOPE — read this before believing #702 is fixed. Every test here hands a dict
straight to the mapper. That proves the mapping is right; it proves nothing
about whether such a payload ever reaches us, and it does not.

The mapper's only production caller is the tail of
``EUDataActConnector.get_vehicle_data``, and that function opens by reading
``/datarequest/vehicles/{vin}/metadata/partial`` — the *continuous* 15-minute
feed. No identifier there means it returns ``no_data=True`` and stops, long
before the mapper. The listing and the download both hardcode ``type=partial``;
``get_active_custom_request_identifier`` only accepts a descriptor whose
``Frequency`` is ``15mins``; and the one endpoint that could enumerate a
one-time export (``_ALL_REQUEST_META_PATH``, ``metadata/all``) is defined and
never called.

The reporter's Touareg is offered *only* a one-time export — he said so in the
thread. So for the car this file is named after, the code above makes exactly
one HTTP call and bails. These aliases are groundwork; the fetch is the
missing piece, and until it exists, #702 stays open.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_702_legacy_soc_maps_and_flags_battery() -> None:
    d = _map({"RBC.vehicleStates.[0].soc": "57"})
    assert d.battery_soc == 57
    # the empty-car symptom: capability detection hung off the same miss.
    assert d.has_battery is True


def test_702_canonical_soc_still_wins() -> None:
    d = _map({
        "battery_state_report.soc": "80",
        "RBC.vehicleStates.[0].soc": "57",
    })
    assert d.battery_soc == 80


def test_702_legacy_charging_true_is_charging() -> None:
    # THE regression guard: routing this boolean through the enum lookup would
    # silently yield is_charging False for a car that IS charging.
    assert _map({"RBC.vehicleStates.[0].charging": "true"}).is_charging is True


def test_702_legacy_charging_false_is_not_charging() -> None:
    assert _map({"RBC.vehicleStates.[0].charging": "false"}).is_charging is False


def test_702_canonical_charge_state_beats_legacy_boolean() -> None:
    d = _map({
        "charging_state_report.current_charge_state": "charging",
        "RBC.vehicleStates.[0].charging": "false",
    })
    assert d.is_charging is True


def test_702_legacy_target_temperature_deci_kelvin() -> None:
    # 2930 dK -> 293.0 K -> 19.85 °C -> 19.9 rounded.
    d = _map({"RPC.climaterSettings.[0].targetTemperature": "2930"})
    assert d.target_temperature == 19.9


def test_702_legacy_target_temperature_invalid_state_skipped() -> None:
    d = _map({
        "RPC.climaterSettings.[0].targetTemperature": "2930",
        "RPC.climaterSettings.[0].targetTemperatureMeasurementState": "invalid",
    })
    assert d.target_temperature is None


def test_702_legacy_max_charge_current_setting() -> None:
    d = _map({"RBC.chargerSettings.[0].maxChargeCurrentAmpere": "32"})
    assert d.charge_max_ac_setting == 32


def test_702_legacy_charge_mode() -> None:
    d = _map({"RBC.chargerSettings.[0].chargeModeSelection.value": "TIMER_BASED_CHARGING"})
    assert d.charge_mode is not None


def test_702_trip_mileage_never_becomes_odometer() -> None:
    # RTS.tripData.[N].mileage is PER-TRIP distance, not the odometer. The
    # dialect ships ~228 of them; promoting one would invent a bogus reading.
    d = _map({
        "RTS.tripData.[0].mileage": "10",
        "RTS.tripData.[1].mileage": "42",
    })
    assert d.odometer_km is None
