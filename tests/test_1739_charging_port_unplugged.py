# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1739 — a scheduled charging PLAN being "active" must not make an unplugged,
idle car report its charging port connected (or that it is charging).

An Audi Q4/Q7 e-tron owner (portal mode) saw the Charging Port read `connected`
on an unplugged car. The cause: a ``*_ACTIVE`` charging SCENARIO
(OPTIMISED_CHARGING_ACTIVE / CHARGING_TO_DEPARTURE_TIME_ACTIVE) is the PLAN being
active, which is true even when the car is unplugged or merely waiting for its
departure time. The honest signal is live power: current flowing proves both
charging and a connected plug. Only IMMEDIATELY_CHARGING_ACTIVE (charging now,
impossible while unplugged) lifts on its own — that stays covered by the #632
test.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_SCN = "charging_state_report.charging_scenario"
_SCHEDULED = [
    "CHARGING_SCENARIO_OPTIMISED_CHARGING_ACTIVE",
    "CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_ACTIVE",
]


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


@pytest.mark.parametrize("scenario", _SCHEDULED)
def test_scheduled_plan_active_but_unplugged_is_not_charging(scenario: str) -> None:
    d = _map({_SCN: scenario})
    assert d.is_charging is not True
    assert d.plug_connected is None  # never inferred from the plan


@pytest.mark.parametrize("scenario", _SCHEDULED)
def test_scheduled_plan_with_live_power_is_charging(scenario: str) -> None:
    d = _map({_SCN: scenario, "charging_power": "7.4"})
    assert d.is_charging is True
    assert d.plug_connected is True  # power flowing proves the plug is in


def test_plugged_in_waiting_for_departure_at_zero_power_is_not_charging() -> None:
    # The common overnight state: cable in, scheduled plan active, 0 kW. The real
    # plug field makes plug_connected True, but the car is NOT charging yet.
    d = _map({
        _SCN: "CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_ACTIVE",
        "charging_plug1_connectionstate": "connected",
    })
    assert d.plug_connected is True       # real plug reading wins
    assert d.is_charging is not True      # but no current flows → not charging
