# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#534 — battery energy-content 10x unit bug (ID.4 2024, Mettchen).

``energy_contents.{current,maximal}_energy_content.physical_value`` is reported
in 0.1-kWh units (100 Wh). The EU-Data-Act mapper used to pass it through 1:1,
so a 75.6 kWh pack surfaced as 756.0 kWh. The mapper now divides by 10.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_534_max_energy_content_scaled_to_kwh() -> None:
    # raw 756 (0.1-kWh) → 75.6 kWh net capacity (ID.4 2024 ~77 kWh pack).
    d = _map(
        {
            "energy_contents.maximal_energy_content.physical_value": "756",
            "energy_contents.maximal_energy_content.value_type": "valid",
        }
    )
    assert d.battery_cap_kwh == 75.6


def test_534_current_energy_content_scaled_to_kwh() -> None:
    # raw 461 (0.1-kWh) → 46.1 kWh available energy.
    d = _map(
        {
            "energy_contents.current_energy_content.physical_value": "461",
            "energy_contents.current_energy_content.value_type": "valid",
        }
    )
    assert d.battery_available_kwh == 46.1


def test_534_invalid_value_type_still_blocks() -> None:
    # The 10x fix must not weaken the value_type gate.
    d = _map(
        {
            "energy_contents.maximal_energy_content.physical_value": "756",
            "energy_contents.maximal_energy_content.value_type": "invalid",
        }
    )
    assert d.battery_cap_kwh is None
