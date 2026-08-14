# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1164 (morpheusbdf) — battery_charging_status_soc as a last-resort HV SoC.

The Vehicle Data Scout surfaced a new VW EU Data Act field
``battery_charging_status_soc`` ("70") — the dict describes it as "the current
charging status for the battery" (%, UUID 081f3121-…). It is a genuine HV SoC, so
it is wired as a LAST-resort fallback into the ``battery_soc`` candidate list:
it recovers SoC for a car that ships nothing else, but can never out-compete a
canonical ``soc`` reading (which also makes it safe if a car ever ships it as a
setpoint instead of the live pack level).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_charging_status_soc_recovers_soc_when_nothing_else_is_sent() -> None:
    d = _map({"battery_charging_status_soc": "70"})
    assert d.battery_soc == 70
    assert d.has_battery is True


def test_canonical_soc_still_wins_over_the_fallback() -> None:
    d = _map({"soc": "80", "battery_charging_status_soc": "70"})
    assert d.battery_soc == 80


def test_hv_soc_still_wins_over_the_fallback() -> None:
    d = _map({"hv_soc": "55", "battery_charging_status_soc": "70"})
    assert d.battery_soc == 55
