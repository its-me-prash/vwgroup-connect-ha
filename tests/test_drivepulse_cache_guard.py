"""A held push value (drivepulse) must leave nothing behind in the cache.

``reconcile(previous, fresh)`` carries recorded values forward and derives the
drivetrain flags from what survives. A value owned by a held push source is
not a read of the car: it arrives through a hand-set link and can be days old.
So it is not carried forward, not used as the anchor of the SoC hold, not a
comparison value and not drivetrain evidence.

Tests marked "absichern" pin behaviour that was already correct before the
change; they were not red.
"""
from __future__ import annotations

import copy

from custom_components.vag_connect.cariad import vehicle_cache
from custom_components.vag_connect.cariad.vehicle_cache import reconcile


def _strip_held():
    # Looked up at call time so the guard tests that pin unchanged behaviour
    # still run (and pass) before the function exists.
    return vehicle_cache.strip_held


# --- a / b: carry-forward ---------------------------------------------------

def test_held_fuel_level_is_not_carried_forward():
    previous = {
        "fuel_level": 35,
        "has_combustion": True,
        "field_sources": {"fuel_level": "drivepulse"},
        "source_channel": "eu_data_act+drivepulse",
    }
    fresh = {"has_combustion": True, "field_sources": {}}
    merged, _ = reconcile(previous, fresh)
    assert merged.get("fuel_level") is None


def test_batch_fuel_level_is_still_carried_forward():
    # absichern (war nicht rot)
    previous = {
        "fuel_level": 35,
        "has_combustion": True,
        "field_sources": {"fuel_level": "eu_data_act"},
    }
    fresh = {"has_combustion": True, "field_sources": {}}
    merged, _ = reconcile(previous, fresh)
    assert merged["fuel_level"] == 35


# --- c / d: SoC hold --------------------------------------------------------

def test_held_soc_is_not_the_anchor_of_the_soc_hold():
    previous = {
        "battery_soc": 62,
        "battery_soc_from_hv": True,
        "has_battery": True,
        "field_sources": {
            "battery_soc": "drivepulse",
            "battery_soc_from_hv": "eu_data_act",
        },
    }
    fresh = {
        "battery_soc": 70,
        "battery_soc_from_hv": False,
        "has_battery": True,
        "field_sources": {
            "battery_soc": "eu_data_act",
            "battery_soc_from_hv": "eu_data_act",
        },
    }
    merged, _ = reconcile(previous, fresh)
    assert merged["battery_soc"] == 70


def test_fresh_held_soc_yields_to_the_recorded_value():
    # A poll that merely omits the state of charge looks like a gap to the
    # channel merge, so the held reading fills it there. Across polls the
    # recorded value is still "something this car's own channels have".
    previous = {
        "battery_soc": 55,
        "battery_soc_from_hv": True,
        "has_battery": True,
        "field_sources": {
            "battery_soc": "eu_data_act",
            "battery_soc_from_hv": "eu_data_act",
        },
    }
    fresh = {
        "battery_soc": 48,
        "battery_soc_from_hv": False,
        "has_battery": True,
        "source_channel": "drivepulse+eu_data_act",
        "field_sources": {"battery_soc": "drivepulse", "has_battery": "eu_data_act"},
        "field_captured_ts": {"battery_soc": "2026-11-01T12:00:00+00:00"},
    }
    before = copy.deepcopy(fresh)
    merged, _ = reconcile(previous, fresh)
    assert merged["battery_soc"] == 55
    assert "battery_soc" not in merged["field_sources"]
    assert "battery_soc" not in merged["field_captured_ts"]
    assert merged["source_channel"] == "eu_data_act"
    assert fresh == before, "the caller's fresh snapshot must not be modified"


# --- partial polls: a held value never displaces a recorded one --------------

_T = "2026-11-01T12:00:00+00:00"
_T_PLUS_10 = "2026-11-01T12:10:00+00:00"
_T_PLUS_20 = "2026-11-01T12:20:00+00:00"


def _recorded_fuel(owner: str = "eu_data_act", stamp: str | None = None) -> dict:
    snap: dict = {
        "fuel_level": 40,
        "has_combustion": True,
        "field_sources": {"fuel_level": owner},
        "field_captured_ts": {},
    }
    if stamp is not None:
        snap["field_captured_ts"]["fuel_level"] = stamp
    return snap


def _fresh_held(field: str, value: float, stamp: str) -> dict:
    return {
        field: value,
        "has_combustion": True,
        "has_battery": True,
        "source_channel": "drivepulse+eu_data_act",
        "field_sources": {field: "drivepulse", "has_combustion": "eu_data_act"},
        "field_captured_ts": {field: stamp},
    }


def test_partial_poll_keeps_the_recorded_fuel_over_a_held_one():
    merged, _ = reconcile(_recorded_fuel(), _fresh_held("fuel_level", 70, _T))
    assert merged["fuel_level"] == 40
    assert "fuel_level" not in merged["field_sources"]
    assert "fuel_level" not in merged["field_captured_ts"]
    assert merged["source_channel"] == "eu_data_act"


def test_control_a_real_gap_is_still_filled_by_the_held_value():
    previous = {"has_combustion": True, "odometer_km": 100, "field_sources": {}}
    merged, _ = reconcile(previous, _fresh_held("fuel_level", 70, _T))
    assert merged["fuel_level"] == 70
    assert merged["field_sources"]["fuel_level"] == "drivepulse"
    assert merged["field_captured_ts"]["fuel_level"] == _T


def test_held_fuel_wins_over_a_dated_recorded_batch_value_by_the_margin():
    merged, _ = reconcile(
        _recorded_fuel(stamp=_T), _fresh_held("fuel_level", 30, _T_PLUS_20)
    )
    assert merged["fuel_level"] == 30
    assert merged["field_sources"]["fuel_level"] == "drivepulse"


def test_held_fuel_inside_the_margin_leaves_the_recorded_value():
    merged, _ = reconcile(
        _recorded_fuel(stamp=_T), _fresh_held("fuel_level", 30, _T_PLUS_10)
    )
    assert merged["fuel_level"] == 40


def test_a_recorded_live_value_is_never_displaced_even_with_a_stamp():
    merged, _ = reconcile(
        _recorded_fuel(owner="website_authproxy", stamp=_T),
        _fresh_held("fuel_level", 30, _T_PLUS_20),
    )
    assert merged["fuel_level"] == 40


def test_state_of_charge_has_no_age_gate_across_polls_either():
    previous = {
        "battery_soc": 54,
        "has_battery": True,
        "field_sources": {"battery_soc": "eu_data_act"},
        "field_captured_ts": {"battery_soc": _T},
    }
    merged, _ = reconcile(previous, _fresh_held("battery_soc", 70, _T_PLUS_20))
    assert merged["battery_soc"] == 54


def test_the_recorded_value_survives_a_run_of_partial_polls():
    """54, then a partial poll with the dongle's 70, then a bare partial poll."""
    cache = {
        "battery_soc": 54,
        "has_battery": True,
        "field_sources": {"battery_soc": "eu_data_act"},
    }
    cache, _ = reconcile(cache, _fresh_held("battery_soc", 70, _T_PLUS_20))
    assert cache["battery_soc"] == 54
    cache, _ = reconcile(cache, {"has_battery": True, "field_sources": {}})
    assert cache["battery_soc"] == 54, "the recorded value was lost to the dongle"


def test_a_field_that_is_never_carried_forward_is_a_gap_every_poll():
    # voltage_12v is not a carry-forward field: without the link a poll that
    # omits it shows nothing, so the held reading is filling a real gap.
    assert "voltage_12v" not in vehicle_cache.CARRY_FORWARD_FIELDS, "control"
    previous = {"voltage_12v": 12.1, "field_sources": {"voltage_12v": "eu_data_act"}}
    merged, _ = reconcile(previous, _fresh_held("voltage_12v", 12.6, _T))
    assert merged["voltage_12v"] == 12.6


# --- a held state of charge is checked against the car's own pack energy ----

def _energy_fresh(owner: str, soc: int = 88) -> dict:
    return {
        "battery_soc": soc,
        "battery_available_kwh": 20.0,
        "battery_cap_kwh": 58.0,
        "has_battery": True,
        "source_channel": f"{owner}+eu_data_act" if owner != "eu_data_act" else owner,
        "field_sources": {
            "battery_soc": owner,
            "battery_available_kwh": "eu_data_act",
            "battery_cap_kwh": "eu_data_act",
        },
        "field_captured_ts": {"battery_soc": _T},
    }


def test_a_held_soc_far_above_the_pack_energy_is_not_shown():
    previous = {"has_battery": True, "odometer_km": 5, "field_sources": {}}
    merged, notes = reconcile(previous, _energy_fresh("drivepulse"))
    assert merged["battery_soc"] is None
    assert "battery_soc" not in merged["field_sources"]
    assert "battery_soc" not in merged["field_captured_ts"]
    assert any("held battery_soc" in n for n in notes)


def test_control_a_batch_soc_is_corrected_from_the_energy_as_before():
    previous = {"has_battery": True, "odometer_km": 5, "field_sources": {}}
    merged, _ = reconcile(previous, _energy_fresh("eu_data_act"))
    assert merged["battery_soc"] == 34


def test_control_a_held_soc_close_to_the_pack_energy_stands():
    previous = {"has_battery": True, "odometer_km": 5, "field_sources": {}}
    merged, _ = reconcile(previous, _energy_fresh("drivepulse", soc=40))
    assert merged["battery_soc"] == 40


def test_control_a_live_soc_is_still_exempt_from_the_energy_check():
    previous = {"has_battery": True, "odometer_km": 5, "field_sources": {}}
    merged, _ = reconcile(previous, _energy_fresh("website_authproxy"))
    assert merged["battery_soc"] == 88


# --- e / f: drivetrain evidence --------------------------------------------

def _ev_previous() -> dict:
    return {
        "battery_soc": 80,
        "has_battery": True,
        "has_combustion": False,
        "is_electric": True,
        "field_sources": {"battery_soc": "eu_data_act"},
    }


def _ev_fresh_with_fuel(owner: str) -> dict:
    return {
        "battery_soc": 79,
        "has_battery": True,
        "has_combustion": False,
        "is_electric": True,
        "fuel_level": 40,
        "field_sources": {"battery_soc": "eu_data_act", "fuel_level": owner},
    }


def test_held_fuel_level_is_no_combustion_evidence():
    merged, _ = reconcile(_ev_previous(), _ev_fresh_with_fuel("drivepulse"))
    assert merged.get("has_combustion") is not True
    assert merged.get("is_hybrid") is not True


def test_batch_fuel_level_still_promotes_combustion():
    # absichern (war nicht rot)
    merged, _ = reconcile(_ev_previous(), _ev_fresh_with_fuel("eu_data_act"))
    assert merged["has_combustion"] is True
    assert merged["is_hybrid"] is True


def test_held_value_is_gone_from_the_second_run_on():
    cache, _ = reconcile(_ev_previous(), _ev_fresh_with_fuel("drivepulse"))
    for _ in range(2):
        fresh = {
            "battery_soc": 78,
            "has_battery": True,
            "field_sources": {"battery_soc": "eu_data_act"},
        }
        cache, _ = reconcile(cache, fresh)
        assert cache.get("fuel_level") is None
        assert cache.get("has_combustion") is not True
        assert cache.get("is_hybrid") is not True


# --- g: strip_held ----------------------------------------------------------

def _held_snapshot() -> dict:
    return {
        "fuel_level": 35,
        "odometer_km": 12000,
        "field_sources": {"fuel_level": "drivepulse", "odometer_km": "eu_data_act"},
        "field_captured_ts": {"fuel_level": "t1", "odometer_km": "t2"},
        "field_source_leaf": {"fuel_level": "leaf.a", "odometer_km": "leaf.b"},
        "ambiguous_fields": {"fuel_level": ["x"], "odometer_km": ["y"]},
        "source_channel": "eu_data_act+drivepulse",
    }


def test_strip_held_removes_field_and_every_map_entry():
    out = _strip_held()(_held_snapshot())
    assert out["fuel_level"] is None
    assert out["odometer_km"] == 12000
    assert out["field_sources"] == {"odometer_km": "eu_data_act"}
    assert out["field_captured_ts"] == {"odometer_km": "t2"}
    assert out["field_source_leaf"] == {"odometer_km": "leaf.b"}
    assert out["ambiguous_fields"] == {"odometer_km": ["y"]}
    assert out["source_channel"] == "eu_data_act"


def test_strip_held_only_held_channel_becomes_none():
    snap = {
        "fuel_level": 35,
        "field_sources": {"fuel_level": "drivepulse"},
        "source_channel": "drivepulse",
    }
    out = _strip_held()(snap)
    assert out["source_channel"] is None
    assert out["fuel_level"] is None
    assert out["field_sources"] == {}


def test_strip_held_is_idempotent():
    strip = _strip_held()
    once = strip(_held_snapshot())
    twice = strip(once)
    assert twice == once
    assert twice is once


def test_strip_held_does_not_mutate_input():
    snap = _held_snapshot()
    before = copy.deepcopy(snap)
    _strip_held()(snap)
    assert snap == before


def test_strip_held_returns_same_object_when_nothing_to_do():
    snap = {
        "fuel_level": 35,
        "field_sources": {"fuel_level": "eu_data_act"},
        "source_channel": "eu_data_act",
    }
    assert _strip_held()(snap) is snap


def test_strip_held_survives_missing_and_mistyped_maps():
    strip = _strip_held()
    bare = {"fuel_level": 35}
    assert strip(bare) is bare
    wrong = {"fuel_level": 35, "field_sources": ["drivepulse"]}
    assert strip(wrong) is wrong
    partial = {
        "fuel_level": 35,
        "field_sources": {"fuel_level": "drivepulse"},
        "field_captured_ts": "not-a-map",
        "source_channel": 7,
    }
    out = strip(partial)
    assert out["fuel_level"] is None
    assert out["field_sources"] == {}
    assert out["field_captured_ts"] == "not-a-map"
    assert out["source_channel"] == 7


# --- h: odometer guards for a batch value -----------------------------------

def test_odometer_jump_guard_unchanged_for_batch():
    # absichern (war nicht rot)
    previous = {
        "odometer_km": 26374,
        "last_seen_at": "2026-11-01T10:00:00+00:00",
        "field_sources": {"odometer_km": "eu_data_act"},
    }
    fresh = {
        "odometer_km": 100663,
        "last_seen_at": "2026-11-01T10:15:00+00:00",
        "field_sources": {"odometer_km": "eu_data_act"},
    }
    merged, _ = reconcile(previous, fresh)
    assert merged["odometer_km"] == 26374


def test_odometer_monotonic_unchanged_for_batch():
    # absichern (war nicht rot)
    previous = {
        "odometer_km": 26374,
        "field_sources": {"odometer_km": "eu_data_act"},
    }
    fresh = {
        "odometer_km": 26000,
        "field_sources": {"odometer_km": "eu_data_act"},
    }
    merged, _ = reconcile(previous, fresh)
    assert merged["odometer_km"] == 26374
