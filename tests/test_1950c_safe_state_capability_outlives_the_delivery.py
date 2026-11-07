# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1950 — "from then on" has to outlive the delivery that proved it.

@Adcad1970 drove 5.2.3 for a day and reported that **All closures secured** went
``unknown`` on a delivery where **Doors Open** was on and **Doors Locked** read
unlocked. His question: *"Should an observed open door give 'not secured' rather
than unknown?"*

**The rule as written already answered him.** The mapper's comment says a 2
"proves the car implements the field, and **from then on** a 3 beside it is a
real unsafe". The implementation scoped "from then on" to the same delivery —
``map_dataset_to_vehicle_data`` is handed a fresh ``VehicleData`` and sees one
dataset — so the proof was thrown away between polls.

**And his car does send the 2.** His sensor reached ``on`` at 13:38, which by the
gate's own logic can only happen when a safe(2) arrives. So the measured premise
behind the gate ("no car has ever sent a 2", 4442 payloads) does not hold for his
car, and for a car like his the entity could only ever read ``on`` or
``unknown`` — never ``off``. That is what made the report worth acting on, and it
was an independent review of the proposal that established it; the first draft
of the fix rested on the old premise.

**Why not simply let an open door force ``off``.** That was the first proposal and
it is worse: the entity would be *created* by an open door and fall back to
``unknown`` the moment the car was shut and locked. A security sensor that says
"no idea" right after you lock up is worse than one that stays absent. That
objection came from the same review.

So the capability is remembered per car and the verdict is finalised in
``reconcile`` — the one function every path runs after the mapper. What is NOT
changed is the behaviour #1739 measured: a car that has never sent a 2 keeps its
``None`` and no entity appears.
"""
from __future__ import annotations

from typing import Any

from custom_components.vag_connect.cariad.vehicle_cache import (
    CAPABILITY_FIELDS,
    CARRY_FORWARD_FIELDS,
    STATIC_MASTER_FIELDS,
    reconcile,
)


def _merge(previous: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    merged, _notes = reconcile(dict(previous), dict(fresh))
    return merged


# ── the reporter's case ─────────────────────────────────────────────────────

def test_a_car_that_proved_the_field_gets_a_real_off() -> None:
    """The 11:44 delivery: doors unlocked and one open, every safe_state a 3,
    and a 2 seen on an earlier delivery."""
    merged = _merge(
        {"safe_state_implemented": True},
        {"safe_state_all_unsafe": True},
    )
    assert merged["closures_secured"] is False, (
        "the proof that this car implements safe_state was thrown away between "
        "deliveries, so an all-unsafe reading still publishes unknown (#1950)"
    )


def test_the_capability_survives_a_delivery_that_omits_it() -> None:
    merged = _merge({"safe_state_implemented": True}, {"odometer_km": 1})
    assert merged["safe_state_implemented"] is True


# ── what must NOT change: #1739's measured behaviour ────────────────────────

def test_a_car_that_never_sent_a_two_still_says_nothing() -> None:
    """4442 payloads, four with safe_state, never a 2. For such a car an all-"3"
    reading is not a verdict, and this change must not turn it into one."""
    merged = _merge({}, {"safe_state_all_unsafe": True})
    assert merged.get("closures_secured") is None, (
        "an all-unsafe reading from a car that has never proved it implements "
        "the field now produces a verdict — that is the permanent 'not secured' "
        "on locked, shut cars that #1739 removed"
    )


def test_absence_is_still_not_a_verdict() -> None:
    """A delivery with no safe_state at all says nothing, even on a proven car."""
    merged = _merge({"safe_state_implemented": True}, {})
    assert merged.get("closures_secured") is None


def test_a_positive_verdict_is_never_overwritten() -> None:
    merged = _merge(
        {"safe_state_implemented": True},
        {"closures_secured": True, "safe_state_all_unsafe": True},
    )
    assert merged["closures_secured"] is True, (
        "the finalisation must only fill a None, never contradict the mapper"
    )


def test_the_mapper_path_is_untouched() -> None:
    """A 2 in this delivery: the mapper already decided, reconcile stays out."""
    merged = _merge({}, {"safe_state_implemented": True, "closures_secured": False})
    assert merged["closures_secured"] is False


# ── the mechanism, and why it is this one ───────────────────────────────────

def test_the_capability_rides_in_its_own_immutable_set() -> None:
    """A capability cannot go stale; a value can.

    ``CARRY_FORWARD_FIELDS`` is staleness-bounded and its own comments record
    what carrying a *value* forever costs: a suppressed 12V SoC was latched at
    100 % for good. "This car implements safe_state" is not a reading and cannot
    become untrue, so it carries unconditionally.

    It lives in its OWN set rather than in ``STATIC_MASTER_FIELDS``, and the
    first attempt put it there. The #465 test enumerates that set against a
    vw.de master-data fixture and failed with a KeyError — for the right
    reason: that set names a SOURCE ("only the vw.de channel supplies these"),
    not merely a carry behaviour, and a capability the car proves about itself
    is neither master data nor vw.de-supplied. Same semantics, different
    meaning, separate set.
    """
    assert "safe_state_implemented" in CAPABILITY_FIELDS
    assert "safe_state_implemented" not in STATIC_MASTER_FIELDS
    assert "safe_state_implemented" not in CARRY_FORWARD_FIELDS
    assert not (CAPABILITY_FIELDS & STATIC_MASTER_FIELDS)


def test_the_per_delivery_ingredient_is_not_carried_forward() -> None:
    """``safe_state_all_unsafe`` describes one delivery. Carried forward it would
    keep producing ``off`` long after the doors were shut."""
    assert "safe_state_all_unsafe" not in STATIC_MASTER_FIELDS
    assert "safe_state_all_unsafe" not in CAPABILITY_FIELDS
    assert "safe_state_all_unsafe" not in CARRY_FORWARD_FIELDS
    merged = _merge({"safe_state_all_unsafe": True}, {"safe_state_implemented": True})
    assert merged.get("safe_state_all_unsafe") is None, (
        "the per-delivery observation survived into a delivery that did not make "
        "it, so a shut car would keep reading not-secured"
    )


def test_neither_field_is_an_entity() -> None:
    """Both are ingredients. A description would turn them into sensors."""
    from custom_components.vag_connect import binary_sensor, sensor

    for modul in (binary_sensor, sensor):
        quelle = __import__("inspect").getsource(modul)
        for feld in ("safe_state_implemented", "safe_state_all_unsafe"):
            assert f'data_key="{feld}"' not in quelle, (
                f"{feld} has an entity description in {modul.__name__}; it is an "
                "internal ingredient, not something to publish"
            )


def test_the_mapper_sets_both_ingredients() -> None:
    """Positive control on the producer. Without it every test above could pass
    while nothing ever sets the fields, and the fix would be inert."""
    import inspect

    from custom_components.vag_connect.cariad.auth import _eu_data_act

    quelle = inspect.getsource(_eu_data_act)
    assert "d.safe_state_implemented = True" in quelle, (
        "nothing sets the capability, so reconcile can never finalise anything"
    )
    assert "d.safe_state_all_unsafe = True" in quelle, (
        "nothing records the all-unsafe delivery, so the verdict never fires"
    )
