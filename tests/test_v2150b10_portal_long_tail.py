# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b10 — EU Data Act portal long-tail mapping (doors/windows/trip/maintenance).

Enum families + units are resolved from the official data dictionary:
lock 2=locked/3=unlocked, open 2=open/3=closed, window-lifter 2=open/3=closed,
position=% open. Polarity is verified against the existing vw_eu/seat writers
(doors_individual True=open, windows_individual True=closed). Also pins the
doors_locked bug fix, the Scout noise-suppression, and the dict name index.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth import eu_data_dictionary as _dd
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str], **kw) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X", **kw))


# ── doors_locked bug fix ─────────────────────────────────────────────────────

def test_doors_locked_true_when_all_doors_locked() -> None:
    d = _map({
        "locked_state_front_left_door": "2",
        "locked_state_front_right_door": "2",
        "locked_state__rear_left_door": "2",
        "locked_state_rear_right_door": "2",
        "locked_state_tailgate": "2",
    })
    assert d.doors_locked is True

def test_doors_locked_false_when_any_door_unlocked() -> None:
    d = _map({
        "locked_state_front_left_door": "2",
        "locked_state_front_right_door": "3",  # one unlocked
    })
    assert d.doors_locked is False

def test_per_door_locks_override_a_wrong_bare_value() -> None:
    # the bug: a stale/absent bare `locked` left doors_locked False on a locked
    # car. The per-door states must win.
    d = _map({
        "locked_state_front_left_door": "2",
        "locked_state_rear_right_door": "2",
    }, doors_locked=False)
    assert d.doors_locked is True

def test_doors_locked_ignores_unsupported_invalid() -> None:
    d = _map({"locked_state_front_left_door": "0", "locked_state_tailgate": "1"})
    assert d.doors_locked is None


# ── open states → doors_individual (True=open) + aggregates ───────────────────

def test_open_state_maps_doors_individual_true_is_open() -> None:
    d = _map({
        "open_state_front_left_door": "2",   # open
        "open_state_front_right_door": "3",  # closed
    })
    assert d.doors_individual == {"frontLeft": True, "frontRight": False}
    assert d.doors_open is True

def test_all_doors_closed_means_doors_open_false() -> None:
    d = _map({
        "open_state_front_left_door": "3",
        "open_state_rear_left_door": "3",
    })
    assert d.doors_open is False

def test_tailgate_and_bonnet_open_states() -> None:
    d = _map({
        "open_state_tailgate": "3",
        "locked_state_tailgate": "2",
        "open_state_front_engine_bonnet": "3",
    })
    assert d.trunk_open is False
    assert d.trunk_locked is True
    assert d.hood_open is False


# ── window lifter → windows_individual (True=closed) + position ───────────────

def test_window_lifter_true_is_closed() -> None:
    d = _map({
        "state_front_left_door_window_lifter": "3",   # closed
        "state_front_right_door_window_lifter": "2",  # open
        "position_front_left_door_window_lifter": "0",
        "position_front_right_door_window_lifter": "40",
    })
    assert d.windows_individual == {"frontLeft": True, "frontRight": False}
    assert d.windows_open is True  # one window open
    assert d.windows_position == {"frontLeft": 0, "frontRight": 40}


# ── trip statistics (units from the dictionary) ──────────────────────────────

def test_trip_stats_units() -> None:
    d = _map({
        "short_term_data_mileage": "46",       # km
        "short_term_data_travel_time": "87",   # min
        "long_term_data_average_speed": "49",  # km/h
        "long_term_data_travel_time": "3933",  # min
    })
    assert d.last_trip_distance_km == 46
    assert d.last_trip_duration_min == 87
    assert d.lifetime_avg_speed_kmh == 49
    assert d.lifetime_travel_time_min == 3933

def test_consumption_is_mapped() -> None:
    # v2.15.1 (2.15.0 plan) — the b10 "deferred" decision is lifted: the EU
    # portal trip-consumption fields now map into the lifetime/last-trip avg
    # consumption fields with the l/1000km → l/100km (÷10) scale.
    d = _map({
        "long_term_data_average_fuel_consumption": "68",   # 6.8 l/100km
        "long_term_data_average_electr_engine_consumption": "182",  # 18.2 kWh/100km
    })
    assert d.lifetime_avg_fuel_consumption_l_100km == 6.8
    assert d.lifetime_avg_electric_consumption_kwh_100km == 18.2


# ── maintenance + remaining times ────────────────────────────────────────────

def test_maintenance_warnings_and_monthly_mileage() -> None:
    d = _map({
        "maintenance_interval_oil_change_warning": "1",
        "maintenance_interval_inspection_warning": "1",
        "maintenance_interval_monthly_mileage": "257",
    })
    assert d.warning_oil is True
    assert d.warning_inspection is True
    assert d.monthly_mileage_km == 257

def test_remaining_times() -> None:
    d = _map({"remaining_climatisation_time": "0", "remaining_charging_time": "12"})
    assert d.climate_remaining_time_min == 0
    assert d.remaining_charge_time_min == 12


# ── b14: NO suppression — every unmapped field surfaces in the Scout ─────────

def test_nothing_is_suppressed_from_raw_unmapped() -> None:
    # Policy: never hide Scout/raw fields. Anything not mapped this poll — even
    # plumbing/metadata — must still appear so it can be learned + mapped later.
    d = _map({
        "echo": "echo", "key": "abc", "message_id": "m1",
        "some_brand_new_field": "42",
    })
    for k in ("echo", "key", "message_id", "some_brand_new_field"):
        assert k in d.raw_unmapped_fields


# ── dictionary name index (fixes the #500 "Spec field" column) ────────────────

def test_dict_lookup_by_name() -> None:
    entry = _dd.lookup("locked_state_front_left_door")
    assert entry is not None
    assert entry.get("name") == "locked_state_front_left_door"

def test_dict_describe_strips_endpoint_prefix() -> None:
    # the Scout passes the prefixed path; describe must still resolve it.
    assert _dd.describe("eu_data_act.long_term_data_average_speed") == (
        "long_term_data_average_speed (km/h)"
    )
