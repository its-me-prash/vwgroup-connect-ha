# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An all-"3" door safe-state reading is not a verdict, so it must not make one.

``closures_secured`` is published as "All closures secured" and was computed as
``all(v == 2 for v in the three door safe_state_*)`` plus the boot and bonnet
open states. The three door fields are the ones the data dictionary documents a
``safe (2)`` for, which is why v4.7.11 kept them when it dropped the bonnet and
the tailgate (those document only ``unsupported (0) / invalid (1) / unsafe (3)``).

**Measured 2026-11-03** across every portal payload on this machine — 4442 files
spanning the attachment archive, our own tracker dump and the competing readers'
repositories. Four deliveries carry ``safe_state`` at all, and in all four:

===============================  ==================
field                            observed values
===============================  ==================
``safe_state_front_right_door``  ``3, 3, 3, 3``
``safe_state_rear_left_door``    ``3, 3, 3, 3``
``safe_state_rear_right_door``   ``3, 3, 3, 3``
===============================  ==================

In **three** of those four the doors are demonstrably locked
(``locked_state_* = 2``), every ``open_state_* = 3`` (closed) and every window
position is ``0`` (closed). So the documented ``safe (2)`` is unobserved on the
doors, ``all(v == 2 …)`` could not be satisfied by any real delivery, and the
entity read "not secured" permanently — on locked, shut cars.

The rule is therefore the one v4.7.11 already applied to the other two
closures, reached here by measurement rather than by the dictionary: **a field
that only ever reports its negative value carries no information.** Require one
observed ``2`` before claiming anything. The ``2`` proves the car implements the
field; a ``3`` beside it is then a real "unsafe", so the mixed case keeps
working. With no ``2`` anywhere the verdict stays ``None`` and the binary sensor
does not appear at all (``closures_secured`` is in the no-phantom list in
``binary_sensor.py``).

Stated rather than hidden: a car that genuinely implements the field and
reports every door unsafe now says nothing instead of ``False``. Nothing in the
corpus looks like that, while "sends a constant 3" is four of four — and an
actually open closure still surfaces on its own ``doors_open`` / ``trunk_open``
/ ``hood_open`` entity.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZAUZFW000000"

DOOR_SAFE = (
    "safe_state_front_right_door",
    "safe_state_rear_left_door",
    "safe_state_rear_right_door",
)
DOOR_LOCK = (
    "locked_state_front_left_door",
    "locked_state_front_right_door",
    "locked_state__rear_left_door",  # double underscore in the spec
    "locked_state_rear_right_door",
)
DOOR_OPEN = (
    "open_state_front_left_door",
    "open_state_front_right_door",
    "open_state_rear_left_door",
    "open_state_rear_right_door",
)


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin=VIN))


def _locked_and_shut() -> dict[str, str]:
    """The shape three of the four real payloads have: locked, closed, windows up."""
    f: dict[str, str] = {}
    f.update({n: "2" for n in DOOR_LOCK})
    f.update({"locked_state_tailgate": "2"})
    f.update({n: "3" for n in DOOR_OPEN})
    f.update({"open_state_tailgate": "3", "open_state_front_engine_bonnet": "3"})
    f.update({f"position_{side}_door_window_lifter": "0"
              for side in ("front_left", "front_right", "rear_left", "rear_right")})
    return f


def test_the_real_payload_shape_no_longer_claims_a_problem() -> None:
    """Locked, shut, windows up, all three door safe states at 3 → no verdict.

    This is the case that used to publish "not secured" on every poll for every
    owner whose portal delivers these fields.
    """
    fields = _locked_and_shut()
    fields.update({n: "3" for n in DOOR_SAFE})
    d = _map(fields)
    assert d.closures_secured is None, "an all-3 reading produced a verdict"
    # positive control: the rest of the same payload still parses, so the None
    # above is the gate doing its job and not a dead delivery.
    assert d.doors_locked is True
    assert d.doors_open is False
    assert d.trunk_locked is True


@pytest.mark.parametrize("n_threes", [1, 2, 3])
def test_any_number_of_threes_alone_is_still_no_verdict(n_threes: int) -> None:
    fields = {n: "3" for n in DOOR_SAFE[:n_threes]}
    assert _map(fields).closures_secured is None


def test_one_observed_two_restores_the_verdict() -> None:
    """A 2 proves the car implements the field, so a 3 beside it means unsafe."""
    d = _map({
        "safe_state_front_right_door": "2",
        "safe_state_rear_right_door": "3",
    })
    assert d.closures_secured is False


def test_all_two_is_secured() -> None:
    assert _map({n: "2" for n in DOOR_SAFE}).closures_secured is True


def test_a_two_plus_an_open_boot_is_not_secured() -> None:
    """The #1950b widening still applies once there is a verdict to widen."""
    fields = {n: "2" for n in DOOR_SAFE}
    fields["open_state_tailgate"] = "2"  # 2 == open
    d = _map(fields)
    assert d.trunk_open is True
    assert d.closures_secured is False


def test_unsupported_and_invalid_are_still_ignored() -> None:
    assert _map({"safe_state_front_right_door": "0",
                 "safe_state_rear_left_door": "1"}).closures_secured is None


def test_the_dropped_leaves_are_still_consumed_when_no_verdict_is_made() -> None:
    """The gate must not stop the read-and-discard that keeps the Scout quiet.

    The bonnet and tailgate consumption sits OUTSIDE the verdict branch; this
    pins that, because moving it inside would be an easy and silent regression.
    """
    fields = {n: "3" for n in DOOR_SAFE}
    fields.update({"safe_state_front_engine_bonnet": "3", "safe_state_tailgate": "3"})
    d = _map(fields)
    assert d.closures_secured is None
    for leaf in (*DOOR_SAFE, "safe_state_front_engine_bonnet", "safe_state_tailgate"):
        assert leaf not in d.raw_unmapped_fields, f"{leaf} re-surfaced to the Scout"


def test_a_prior_verdict_is_not_clobbered_by_an_all_three_delivery() -> None:
    pre = VehicleData(vin=VIN)
    pre.closures_secured = True
    d = map_dataset_to_vehicle_data({n: "3" for n in DOOR_SAFE}, pre)
    assert d.closures_secured is True


def test_the_gate_is_in_the_source() -> None:
    """Pins the gate itself, not just one of its outcomes.

    **The prohibition is anchored on a line, not on a substring (#1950c).** It
    used to read ``assert "if _safe_present:" not in src``, which also matched
    ``elif _safe_present:`` — a branch added in #1950c that records *whether this
    delivery was all-unsafe* and assigns no verdict at all. The check forbade
    legitimate code because the forbidden text is a substring of it, the same
    shape as a prohibition tripping over its own explanatory comment.

    What must stay forbidden is an **un-gated verdict**: a bare
    ``if _safe_present:`` as a statement of its own, which would let any
    safe_state reading produce one and bring back the permanent "not secured" on
    locked, shut cars. So the match is on a stripped line.
    """
    import inspect

    from custom_components.vag_connect.cariad.auth import _eu_data_act

    src = inspect.getsource(_eu_data_act.map_dataset_to_vehicle_data)
    assert "if 2 in _safe_present:" in src
    ungated = [ln for ln in src.splitlines() if ln.strip() == "if _safe_present:"]
    assert not ungated, (
        "an un-gated 'if _safe_present:' is back, so any safe_state reading can "
        "produce a verdict again — that is the permanent 'not secured' this file "
        f"exists to prevent: {ungated}"
    )
    # positive control: the aggregate this file is about is still here
    assert "all(v == 2 for v in _safe_present)" in src
    # and the ingredient branch #1950c added is a RECORD, not a verdict
    assert "elif _safe_present:" in src, (
        "the all-unsafe observation is no longer recorded, so reconcile can "
        "never finalise the verdict for a car that proved the field earlier"
    )
