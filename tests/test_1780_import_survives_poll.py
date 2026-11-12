# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1780 — door / window / trunk / hood / lock values imported from a one-time
export reverted to "unknown" on the next poll, because reconcile() starts from
the fresh poll and these volatile fields are deliberately NOT in
CARRY_FORWARD_FIELDS (a stale live reading there would be misleading).

Owner decision (option A): imported values ARE carried forward — but only when
they were imported from an export (marked in ``field_imported_from_export``) and
the live feed has not since delivered a value. The import's capture time is
carried too, so the sensor's freshness attribute stays honest. A live reading
always wins and drops the import marker. Volatile state that was NOT imported is
untouched — the deliberate fresh-or-unknown rule still holds for it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.vehicle_cache import reconcile

TS = "2026-11-01T10:00:00+00:00"


def _prev_imported() -> dict:
    return {
        "doors_open": False,
        "trunk_locked": True,
        "odometer_km": 100,
        "field_sources": {"doors_open": "eu_data_act", "trunk_locked": "eu_data_act"},
        "field_captured_ts": {"doors_open": TS, "trunk_locked": TS},
        "field_imported_from_export": ["doors_open", "trunk_locked"],
    }


def test_imported_body_state_survives_a_poll_that_omits_it() -> None:
    """FAILS BEFORE THE FIX: doors_open / trunk_locked come back None."""
    merged, _ = reconcile(
        _prev_imported(),
        {"vin": "X", "odometer_km": 101, "doors_open": None, "trunk_locked": None},
    )
    assert merged["doors_open"] is False
    assert merged["trunk_locked"] is True
    # Freshness stays honest: the import's capture time is carried, not faked.
    assert merged["field_captured_ts"]["doors_open"] == TS


def test_a_live_reading_wins_and_drops_the_import_marker() -> None:
    merged, _ = reconcile(
        _prev_imported(),
        {"vin": "X", "doors_open": True, "trunk_locked": None},
    )
    assert merged["doors_open"] is True  # a live reading always wins
    assert "doors_open" not in merged.get("field_imported_from_export", [])
    # trunk_locked had no live value this poll, so it is still carried.
    assert merged["trunk_locked"] is True
    assert "trunk_locked" in merged.get("field_imported_from_export", [])


def test_non_imported_volatile_state_is_not_carried() -> None:
    """The deliberate volatile-state rule is untouched for state that did NOT
    come from an export: no marker -> no carry (fresh-or-unknown holds)."""
    merged, _ = reconcile(
        {"doors_open": False, "odometer_km": 100},  # no import marker
        {"vin": "X", "odometer_km": 101, "doors_open": None},
    )
    assert merged.get("doors_open") is None


def test_an_imported_carry_forward_field_keeps_its_import_provenance() -> None:
    # agy/Gemini finding: battery_soc is in CARRY_FORWARD_FIELDS, so its VALUE
    # carries anyway — but the live-detector must be the fresh poll, not `merged`
    # (already set by the carry-forward loop), or the import's capture time/source
    # is dropped and the #1195 SoC guard reads it without provenance.
    prev = {
        "battery_soc": 55,
        "field_sources": {"battery_soc": "eu_data_act"},
        "field_captured_ts": {"battery_soc": TS},
        "field_imported_from_export": ["battery_soc"],
    }
    merged, _ = reconcile(prev, {"vin": "X", "battery_soc": None})
    assert merged["battery_soc"] == 55
    assert merged["field_captured_ts"]["battery_soc"] == TS
    assert merged["field_sources"]["battery_soc"] == "eu_data_act"


def test_reconcile_does_not_mutate_the_fresh_polls_nested_dicts() -> None:
    # agy/Gemini finding: merged = dict(fresh) is a SHALLOW copy, so the carry
    # must not mutate fresh's nested provenance maps in place.
    fresh_fs: dict = {}
    fresh = {"vin": "X", "doors_open": None, "trunk_locked": None,
             "field_sources": fresh_fs}
    reconcile(_prev_imported(), fresh)
    assert fresh_fs == {}  # fresh's own dict must be untouched
    assert fresh["field_sources"] is fresh_fs
