# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#632 (@gr6803, CUPRA) — derive is_charging from an *_ACTIVE charge scenario.

gr6803's CUPRA reads over the EU Data Act portal and ships `charging_scenario`
but NOT `current_charge_state`, so the cs-derived `is_charging` stayed False while
the car was actively charging (and `plug_connected` read null).

#1739 refined this: a `*_ACTIVE` scenario is the charging PLAN being active,
which is also true on an UNPLUGGED, idle car (scheduled / optimised charging) or
one still waiting for its departure time — that made an idle Audi report its
charging port connected. So only `IMMEDIATELY_CHARGING_ACTIVE` (charging NOW,
impossible while unplugged) lifts on its own; the scheduled plans lift only when
live power confirms current is flowing. OFF / INVALID / `_FINISHED` are idle and
never lift. The plug is inferred only when the granular field is absent.
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


def test_immediately_charging_active_lifts_on_its_own() -> None:
    # #632 — "charging NOW": a car cannot immediately-charge while unplugged, so
    # this scenario is enough on its own, even when the feed ships no power.
    d = _map({_SCN: "CHARGING_SCENARIO_IMMEDIATELY_CHARGING_ACTIVE"})
    assert d.is_charging is True
    assert d.plug_connected is True


@pytest.mark.parametrize("scenario", [
    "CHARGING_SCENARIO_CHARGING_TO_DEPARTURE_TIME_ACTIVE",
    "CHARGING_SCENARIO_OPTIMISED_CHARGING_ACTIVE",
])
def test_scheduled_active_lifts_only_with_live_power(scenario: str) -> None:
    # #1739 — a SCHEDULED plan is "active" even on an unplugged car or one still
    # waiting for its departure time, so it must lift ONLY when live power proves
    # current is actually flowing.
    with_power = _map({_SCN: scenario, "charging_power": "7.4"})
    assert with_power.is_charging is True
    assert with_power.plug_connected is True
    without_power = _map({_SCN: scenario})
    assert without_power.is_charging is not True   # #1739 — no false positive
    assert without_power.plug_connected is None


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
