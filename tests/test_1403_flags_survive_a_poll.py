# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1403 — the reading survived the next poll and the flag did not, so the
entity appeared on import and vanished a quarter of an hour later.

``CARRY_FORWARD_FIELDS`` holds ``battery_soc``, ``electric_range_km``,
``fuel_level`` and ``combustion_range_km``, but not one ``has_*`` or ``is_*``
flag, and the merge starts as a copy of the FRESH poll. So a car whose charge
level had been filled in by the one-time-export import kept the number and lost
the flag on the very next feed snapshot. Measured before the fix:
``reconcile({battery_soc: 31, has_battery: True}, <feed poll with no battery
fields>)`` returned ``battery_soc`` 31 together with ``has_battery`` **False**.

That flag gates every electric entity, and it is checked before the hide-empty
gate, so the result was not an entity reading unknown. There was no entity.

The flags are now re-derived at the end of the merge from the evidence that
survived it, through the same shared rule the channel merge and the import both
use. Two properties are pinned here because getting either wrong would be worse
than the original bug:

* It can only ever promote. A channel that knows nothing about combustion must
  never be able to flatten a plug-in hybrid into an EV.
* ``is_electric`` and ``is_hybrid`` come from one call to a rule that returns
  them as mutually exclusive, so no snapshot can ever claim both.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.vehicle_cache import (
    CARRY_FORWARD_FIELDS,
    reconcile,
)


def _poll(previous: dict | None, fresh: dict) -> dict:
    """Run one merge the way the poll loop does and return the snapshot."""
    merged, _notes = reconcile(previous, dict(fresh, vin="TESTVIN0000000001"))
    return merged


def test_the_premise_still_holds() -> None:
    """Guard the assumption this whole fix rests on.

    If a future change adds the flags to the carry-forward set, the re-derivation
    becomes redundant and this test says so out loud rather than letting both
    mechanisms drift.
    """
    for flag in ("has_battery", "has_combustion", "is_electric", "is_hybrid"):
        assert flag not in CARRY_FORWARD_FIELDS
    # And the evidence the re-derivation depends on IS carried forward.
    for evidence in ("battery_soc", "electric_range_km",
                     "fuel_level", "combustion_range_km"):
        assert evidence in CARRY_FORWARD_FIELDS


def test_the_imported_battery_survives_the_next_poll() -> None:
    """The reporter's case. FAILS BEFORE THE FIX: has_battery came back False."""
    merged = _poll(
        # after the import
        {
            "battery_soc": 31,
            "electric_range_km": 148,
            "has_battery": True,
            "is_electric": True,
            "odometer_km": 6775,
        },
        # the next 15-minute feed snapshot: his feed carries no battery fields
        {"odometer_km": 6780, "has_battery": False, "is_electric": False},
    )
    assert merged["battery_soc"] == 31
    assert merged["electric_range_km"] == 148
    assert merged["has_battery"] is True
    assert merged["is_electric"] is True


def test_a_contradicted_flag_is_noted() -> None:
    """The notes are what a reporter can read back to us, so a poll that claimed
    False against surviving evidence has to be visible rather than silent."""
    _merged, notes = reconcile(
        {"battery_soc": 31, "has_battery": True},
        {"vin": "TESTVIN0000000001", "has_battery": False},
    )
    assert any("has_battery was reported False" in n for n in notes)


def test_an_absent_flag_is_not_noted() -> None:
    """An absent flag claims nothing, so filling it in is not a discrepancy.

    Noting it would put a line in every ordinary merge of an electric car, which
    is exactly what the notes list exists to stand out from, and two older portal
    safety tests assert that a clean carry-forward merge produces no notes at all.
    """
    merged, notes = reconcile(
        {"battery_soc": 31, "has_battery": True},
        {"vin": "TESTVIN0000000001", "odometer_km": 10},
    )
    assert merged["has_battery"] is True
    assert notes == []


def test_a_plug_in_hybrid_is_not_flattened_into_an_ev() -> None:
    """Both kinds of evidence carry forward, so both flags must come back."""
    merged = _poll(
        {
            "battery_soc": 40,
            "fuel_level": 55,
            "combustion_range_km": 380,
            "has_battery": True,
            "has_combustion": True,
            "is_hybrid": True,
        },
        {"odometer_km": 1},
    )
    assert merged["has_battery"] is True
    assert merged["has_combustion"] is True
    assert merged["is_hybrid"] is True
    # The one thing that must never happen to a PHEV.
    assert not merged.get("is_electric")


def test_a_combustion_car_never_grows_a_battery() -> None:
    merged = _poll(
        {"fuel_level": 70, "combustion_range_km": 410, "has_combustion": True},
        {"odometer_km": 1},
    )
    assert not merged.get("has_battery")
    assert merged["has_combustion"] is True
    assert not merged.get("is_electric")


def test_a_car_we_know_nothing_about_stays_unclassified() -> None:
    """No evidence means no claim, rather than a default of "electric"."""
    merged = _poll({"odometer_km": 5}, {"odometer_km": 6})
    for flag in ("has_battery", "has_combustion", "is_electric", "is_hybrid"):
        assert not merged.get(flag)


def test_no_snapshot_can_claim_electric_and_hybrid_at_once() -> None:
    """The two come from a single call to a rule that makes them exclusive."""
    for previous in (
        {"battery_soc": 50, "has_battery": True, "is_electric": True},
        {"battery_soc": 50, "fuel_level": 20, "has_battery": True,
         "has_combustion": True, "is_hybrid": True},
        {"fuel_level": 20, "has_combustion": True},
    ):
        merged = _poll(previous, {"odometer_km": 1})
        assert not (merged.get("is_electric") and merged.get("is_hybrid"))


@pytest.mark.parametrize("previous", [None, {}])
def test_the_first_poll_contract_is_untouched(previous: dict | None) -> None:
    """A falsy ``previous`` still returns the fresh poll unchanged.

    The re-derivation sits after that early return on purpose: on a first poll
    the channel merge has just set the flags from this very snapshot, so there is
    nothing to repair and nothing to second-guess.
    """
    fresh = {"vin": "TESTVIN0000000001", "battery_soc": 50}
    merged, notes = reconcile(previous, fresh)
    assert merged is fresh
    assert notes == []
