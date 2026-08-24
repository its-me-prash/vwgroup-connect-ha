# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923-sweep — a deterministic scan of the diagnostic archive found ELEVEN
output fields (beyond the charge_type/charging_reason/target-SoC ones) that
leaked a backend no-reading sentinel (`invalid` / `unavailable` / `unsupported`)
straight to the user, on real cars, across brands:

  charging_state, charging_scenario, profile_charge_reason,
  external_power_supply_state, charge_rate_unit, start_stop_action,
  start_stop_modification, plug_led_color,
  next_charging_timer_target_soc_reachable, charging_preferred_mode,
  climatisation_state

Each write path now screens the value through the shared drop_charge_sentinel
guard. These tests pin the two most-exposed paths (EU-DA portal + CARIAD BFF)
plus the cross-brand charging_state; a sentinel must become None and a real
value must survive.

Everything here is synthetic.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

SENTINELS = ("invalid", "INVALID", "unavailable", "unsupported")


def _map(fields: dict[str, object]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def _bff(raw: dict) -> VehicleData:
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client._parse_status("VINX", raw, parking={})


# ── EU Data Act portal ───────────────────────────────────────────────────────
# (input portal key, output VehicleData attribute, a real value that must survive)
EU_DA_FIELDS = [
    ("current_charge_state", "charging_state", "charging"),
    ("charging_scenario", "charging_scenario", "IMMEDIATELY_CHARGING"),
    ("profile_charge_reason", "profile_charge_reason", "timer"),
    ("external_power_supply_state", "external_power_supply_state", "available"),
    ("charge_rate_unit", "charge_rate_unit", "km_per_hour"),
    ("start_stop_action", "start_stop_action", "start"),
    ("start_stop_modification", "start_stop_modification", "modified"),
]


@pytest.mark.parametrize("in_key,attr,real", EU_DA_FIELDS)
@pytest.mark.parametrize("sentinel", SENTINELS)
def test_eu_da_sentinel_dropped(in_key, attr, real, sentinel):
    assert getattr(_map({in_key: sentinel}), attr) is None


@pytest.mark.parametrize("in_key,attr,real", EU_DA_FIELDS)
def test_eu_da_real_value_kept(in_key, attr, real):
    got = getattr(_map({in_key: real}), attr)
    assert got is not None, f"{attr} lost its real value {real!r}"


def test_eu_da_prefixed_sentinel_dropped():
    # the portal also ships prefixed enum spellings — the last-segment test must catch them
    assert _map({"start_stop_action": "START_STOP_ACTION_INVALID"}).start_stop_action is None
    assert _map({"charge_rate_unit": "CHARGE_RATE_UNIT_UNAVAILABLE"}).charge_rate_unit is None


# ── CARIAD BFF (vw_eu _parse_status) ─────────────────────────────────────────

def _wrap(*path_and_value):
    """Build a nested {k: {k: {...: value}}} raw dict from a key path + value."""
    *keys, value = path_and_value
    node: dict = {keys[-1]: value}
    for k in reversed(keys[:-1]):
        node = {k: node}
    return node


BFF_CASES = [
    ("charging_state", _wrap("charging", "chargingStatus", "value", "chargingState", "invalid"), "charging_state"),
    ("charging_scenario", _wrap("charging", "chargingStatus", "value", "chargingScenario", "invalid"), "charging_scenario"),
    ("plug_led_color", _wrap("charging", "plugStatus", "value", "ledColor", "invalid"), "plug_led_color"),
    ("climatisation_state", _wrap("climatisation", "climatisationStatus", "value", "climatisationState", "invalid"), "climatisation_state"),
    ("charging_preferred_mode", _wrap("charging", "chargeMode", "value", "preferredChargeMode", "invalid"), "charging_preferred_mode"),
    ("nct", _wrap("automation", "chargingProfiles", "value", "nextChargingTimer", "targetSOCreachable", "invalid"), "next_charging_timer_target_soc_reachable"),
]


@pytest.mark.parametrize("name,raw,attr", BFF_CASES)
def test_bff_sentinel_dropped(name, raw, attr):
    assert getattr(_bff(raw), attr) is None


def test_bff_real_values_kept():
    assert _bff(_wrap("charging", "chargingStatus", "value", "chargingState", "charging")).charging_state == "charging"
    assert _bff(_wrap("charging", "plugStatus", "value", "ledColor", "green")).plug_led_color == "green"
    assert _bff(_wrap("climatisation", "climatisationStatus", "value", "climatisationState", "cooling")).climatisation_state is not None


def test_bff_charging_state_sentinel_leaves_is_charging_unknown():
    # a sentinel must not be read as "charging"; is_charging stays unknown (None)
    d = _bff(_wrap("charging", "chargingStatus", "value", "chargingState", "invalid"))
    assert d.charging_state is None
    assert d.is_charging is None
