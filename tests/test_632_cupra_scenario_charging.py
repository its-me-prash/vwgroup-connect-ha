# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#632 (@gr6803, CUPRA) — derive is_charging from an *_ACTIVE charge scenario.

gr6803's CUPRA reads over the EU Data Act portal and ships `charging_scenario`
but NOT `current_charge_state`, so the cs-derived `is_charging` stayed False while
the car was actively charging (and `plug_connected` read null). The three
in-progress scenarios all end `_ACTIVE`; they now lift `is_charging` (and infer
`plug_connected` only when the granular field is absent). OFF / INVALID /
`_FINISHED` are idle and never lift.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_SCN = "charging_state_report.charging_scenario"


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


@pytest.mark.parametrize("scenario", [
    "CHARGING_SCENARIO_IMMEDIATELY_CHARGING_ACTIVE",
    "CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_ACTIVE",
    "CHARGING_SCENARIO_OPTIMISED_CHARGING_ACTIVE",
])
def test_active_scenario_lifts_is_charging_and_infers_plug(scenario: str) -> None:
    d = _map({_SCN: scenario})
    assert d.is_charging is True
    assert d.plug_connected is True


@pytest.mark.parametrize("scenario", [
    "CHARGING_SCENARIO_IMMEDIATELY_CHARGING_FINISHED",
    "CHARGING_SCENARIO_OFF",
    "CHARGING_SCENARIO_INVALID",
])
def test_idle_scenarios_do_not_lift(scenario: str) -> None:
    d = _map({_SCN: scenario})
    assert d.is_charging is not True   # stays False/None
    assert d.plug_connected is None


def test_active_scenario_never_overrides_an_explicit_disconnected_plug() -> None:
    """The plug inference must not clobber a real granular reading."""
    d = _map({
        _SCN: "CHARGING_SCENARIO_IMMEDIATELY_CHARGING_ACTIVE",
        "charging_plug1_connectionstate": "disconnected",
    })
    assert d.is_charging is True          # scenario still lifts charging
    assert d.plug_connected is False      # but the explicit plug reading wins


def test_explicit_charge_state_still_wins_for_a_normal_car() -> None:
    """A car that DOES ship current_charge_state is unaffected by the scenario lift."""
    d = _map({
        "charging_state_report.current_charge_state": "charging",
        _SCN: "CHARGING_SCENARIO_IMMEDIATELY_CHARGING_ACTIVE",
    })
    assert d.is_charging is True
