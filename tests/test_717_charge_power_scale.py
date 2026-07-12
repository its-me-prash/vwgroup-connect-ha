# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#717 — charge power + charge rate 10x unit bug (Golf GTE mk8.5 2025, UK).

`battery_state_report.charge_power` (EU data dict UUID 44ed0d61: "resolution of
0,1 kW") and `battery_state_report.charge_rate` (0c60a14f: "resolution of 0,1")
are reported in 0.1-resolution units. The EU-Data-Act mapper passed them
through 1:1, so a 6.5 kW charge surfaced as 65 kW and a 14.9 km/h rate as 149
(reporter-confirmed against the official app). The mapper now divides both by
10 — the same deci-unit handling the temps + battery-kWh fields already get. The
already-unit aliases (chargePower_kW / chargeRate_kmph) must stay UNSCALED so a
canonical-key car (ID.7 / CUPRA) can never regress.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_717_charge_power_deci_scaled_to_kw() -> None:
    # raw 65 (0.1-kW) → 6.5 kW.
    assert _map({"battery_state_report.charge_power": "65"}).charging_power_kw == 6.5


def test_717_charge_rate_deci_scaled() -> None:
    # raw 149 (0.1) → 14.9.
    assert _map({"battery_state_report.charge_rate": "149"}).charging_rate_kmh == 14.9


def test_717_kw_alias_not_double_scaled() -> None:
    # chargePower_kW already carries kW → must NOT be divided (no regression).
    assert _map({"chargePower_kW": "6.5"}).charging_power_kw == 6.5


def test_717_kmph_alias_not_scaled() -> None:
    # chargeRate_kmph already carries km/h → unscaled.
    assert _map({"chargeRate_kmph": "15"}).charging_rate_kmh == 15
