# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b13 — Portal-safety: last-known-good carry-forward + monotonic km guard.

A null/partial poll must not blank recorded telemetry, and a backwards
odometer reading must be rejected in favour of the recorded value.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.vehicle_cache import (
    CARRY_FORWARD_FIELDS,
    MONOTONIC_INCREASING_FIELDS,
    reconcile,
    strip_runtime,
    vehicle_cache_key,
)


# ── carry-forward of cumulative telemetry ─────────────────────────────────────

def test_carry_forward_when_fresh_omits_cumulative_field() -> None:
    prev = {"battery_soc": 80, "odometer_km": 12000, "range_km": 300}
    fresh = {"battery_soc": None, "odometer_km": 12010, "range_km": None}
    merged, notes = reconcile(prev, fresh)
    assert merged["battery_soc"] == 80      # carried (fresh was None)
    assert merged["range_km"] == 300        # carried
    assert merged["odometer_km"] == 12010   # fresh wins (had a value, went up)
    assert notes == []


def test_fresh_value_always_wins_over_recorded() -> None:
    prev = {"battery_soc": 80}
    fresh = {"battery_soc": 55}
    merged, _ = reconcile(prev, fresh)
    assert merged["battery_soc"] == 55      # a real fresh reading is never overridden


def test_volatile_fields_are_not_carried_forward() -> None:
    # locks/charging are NOT in the safelist — a stale "unlocked"/"charging"
    # would read as fact, so they must blank to None when omitted.
    assert "doors_locked" not in CARRY_FORWARD_FIELDS
    assert "charging" not in CARRY_FORWARD_FIELDS
    prev = {"doors_locked": True, "charging": True, "battery_soc": 80}
    fresh = {"doors_locked": None, "charging": None, "battery_soc": None}
    merged, _ = reconcile(prev, fresh)
    assert merged["doors_locked"] is None
    assert merged["charging"] is None
    assert merged["battery_soc"] == 80      # cumulative still carried


# ── monotonic odometer guard (the "km discrepancy") ───────────────────────────

def test_backwards_odometer_is_rejected() -> None:
    prev = {"odometer_km": 50000}
    fresh = {"odometer_km": 49000}          # bad reading / stale portal snapshot
    merged, notes = reconcile(prev, fresh)
    assert merged["odometer_km"] == 50000   # kept the recorded value
    assert any("odometer_km" in n for n in notes)


def test_forward_odometer_is_accepted() -> None:
    merged, notes = reconcile({"odometer_km": 50000}, {"odometer_km": 50123})
    assert merged["odometer_km"] == 50123
    assert notes == []


def test_odometer_carried_when_fresh_is_none() -> None:
    merged, notes = reconcile({"odometer_km": 50000}, {"odometer_km": None})
    assert merged["odometer_km"] == 50000   # carry-forward (None) not a regression
    assert notes == []


def test_monotonic_ignores_bool() -> None:
    # guard must not treat False(0) < True(1) numerically
    assert "odometer_km" in MONOTONIC_INCREASING_FIELDS
    merged, notes = reconcile({"odometer_km": True}, {"odometer_km": False})
    assert notes == []


# ── no-previous + serialisation ───────────────────────────────────────────────

def test_no_previous_returns_fresh_untouched() -> None:
    fresh = {"battery_soc": None, "odometer_km": 1}
    merged, notes = reconcile(None, fresh)
    assert merged is fresh
    assert notes == []


def test_strip_runtime_drops_underscore_keys() -> None:
    out = strip_runtime({"battery_soc": 80, "_client": object(), "_poll_failed": True})
    assert out == {"battery_soc": 80}


def test_cache_key_is_entry_scoped() -> None:
    assert vehicle_cache_key("abc123") == "vag_connect_vehicles_abc123"
    assert vehicle_cache_key("a") != vehicle_cache_key("b")
