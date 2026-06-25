# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b13 (#504, E1) — legacy Car-Net charger-dialect SoC alias.

Some cars report only the charger/battery report shape, where the traction SoC
is `battery_level_HV.value` rather than the canonical `battery_state_report.soc`.
Map it — but as a LAST resort, so a car that reports both still uses the
canonical source.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_charger_dialect_hv_level_maps_to_soc() -> None:
    d = _map({"battery_level_HV.value": "90"})
    assert d.battery_soc == 90
    assert d.has_battery is True


def test_canonical_soc_wins_when_both_present() -> None:
    # a car reporting both must use the canonical source, not the HV-level alias
    d = _map({"battery_state_report.soc": "80", "battery_level_HV.value": "90"})
    assert d.battery_soc == 80


def test_no_soc_source_leaves_battery_unset() -> None:
    d = _map({"some_other_field": "1"})
    assert d.battery_soc is None


def test_charger_dialect_charge_energy_maps_to_session() -> None:
    # v2.15.3 — battery_state_report.charge_energy is PER-SESSION (EU data-dict:
    # "charged energy in kWh, 0..1000, EV must be connected to charger" — a gauge
    # that reads 0 when idle), so it maps to charge_session_energy_kwh, NOT the
    # lifetime total_charged_energy_kwh.
    d = _map({"battery_state_report.charge_energy": "12.5"})
    assert d.charge_session_energy_kwh == 12.5
    assert d.total_charged_energy_kwh is None


def test_negative_charge_energy_ignored() -> None:
    d = _map({"battery_state_report.charge_energy": "-1"})
    assert d.charge_session_energy_kwh is None
    assert d.total_charged_energy_kwh is None
