# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""``lock_state`` belongs to the charging side and must never decide the doors.

The portal mapper used to read it as the door lock:

    lock = first("lock_state", "central_lock_state")
    if lock is not None and d.doors_locked is None:
        d.doors_locked = str(lock).lower() in ("locked", "safe")

Three independent lines of evidence say that is the wrong subject.

**The catalogue.** The official EU Data Act data dictionary puts ``lock_state``
in cluster "All Data, **Charging**", alongside ``plug_lock_state`` (44534a85),
``charging_plug1_lock_state`` and ``charging_plug2_lock_state``. Every field
that genuinely describes a door or a closure is in "All Data, **Vehicle
Access**": the six ``locked_state_*``, the ``safe_state_*``, the
``open_state_*`` and ``flap_lock_state``. Cluster membership is the same
argument the flap/plug targets in ``models.py`` already turn on — a combustion
tank flap has ``flap_*`` too, which is why those live in Vehicle Access and
``plug_lock_state`` does not.

**The payloads.** Two portal datasets on record carry BOTH spellings, and they
disagree in *opposite* directions. That is what two different subjects look
like; a single mis-signed enum could not do it:

===========================  ====================  =======================
field                        payload A             payload B (#709)
===========================  ====================  =======================
``lock_state``               ``unlocked``          ``locked``
``locked_state_*`` (4+boot)  ``2``  (= locked)     ``3``  (= unlocked)
``open_state_*``             ``3``  (= closed)     ``3``  (= closed)
``position_*_lifter``        ``0``  (= closed)     ``0``  (= closed)
===========================  ====================  =======================

Read as the door lock, payload A says "locked car reports unlocked" and
payload B says "unlocked car reports locked". Read as the charging side, both
are unremarkable: a cable unplugged next to a locked car, and a cable latched
next to an unlocked one.

**The value set.** Observed values are ``locked``, ``unlocked`` and ``new``.
"new" is not a state a door reports.

What the field actually names is NOT established — the dictionary says only
"Describes the lock state", and ``plug_lock_state`` exists separately — so the
mapper publishes nothing rather than guessing a target. It still consumes the
name, because a catalogued field left visible re-files itself to the Vehicle
Data Scout on every poll (the #958/#969/#970 failure mode).

``central_lock_state`` is gone from the read entirely: it appears nowhere in
the dictionary, so a car that sends it is sending something genuinely new and
the Scout should surface it.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZAUZFW000000"

DOORS = (
    "locked_state_front_left_door",
    "locked_state_front_right_door",
    "locked_state__rear_left_door",  # double underscore in the spec
    "locked_state_rear_right_door",
)
CLOSED = (
    "open_state_front_left_door",
    "open_state_front_right_door",
    "open_state_rear_left_door",
    "open_state_rear_right_door",
)


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin=VIN))


@pytest.mark.parametrize("value", ["locked", "unlocked", "safe", "new", "NEW"])
def test_alone_it_decides_nothing(value: str) -> None:
    """A delivery carrying only ``lock_state`` leaves the doors unknown.

    This is the case the override at the per-door block does NOT mask: a
    charging-scoped delivery has no Vehicle Access fields in it, so whatever
    ``lock_state`` said used to be published as the door lock.
    """
    d = _map({"lock_state": value})
    assert d.doors_locked is None


@pytest.mark.parametrize("value", ["locked", "unlocked", "safe", "new"])
def test_it_is_still_consumed(value: str) -> None:
    """Catalogued field, so it must not re-surface to the Scout every poll."""
    d = _map({"lock_state": value})
    assert "lock_state" not in d.raw_unmapped_fields


def test_central_lock_state_is_surfaced_for_discovery() -> None:
    """Not in the dictionary, so it is a find, not a mapped name."""
    d = _map({"central_lock_state": "locked"})
    assert d.doors_locked is None
    assert d.raw_unmapped_fields.get("central_lock_state") == "locked"


def test_payload_a_locked_doors_unlocked_cable() -> None:
    """Doors at 2 with ``lock_state`` saying unlocked: the doors win."""
    fields = {"lock_state": "unlocked", "locked_state_tailgate": "2"}
    fields.update({n: "2" for n in DOORS})
    fields.update({n: "3" for n in CLOSED})
    d = _map(fields)
    assert d.doors_locked is True, "the cable decided the doors"
    assert d.trunk_locked is True


def test_payload_b_unlocked_doors_locked_cable() -> None:
    """The #709 shape: doors at 3 with ``lock_state`` saying locked."""
    fields = {"lock_state": "locked", "locked_state_tailgate": "3"}
    fields.update({n: "3" for n in DOORS})
    fields.update({n: "3" for n in CLOSED})
    d = _map(fields)
    assert d.doors_locked is False
    assert d.trunk_locked is False


def test_a_prior_value_is_not_clobbered() -> None:
    """A brand-native parser's verdict survives a portal poll."""
    pre = VehicleData(vin=VIN)
    pre.doors_locked = True
    d = map_dataset_to_vehicle_data({"lock_state": "unlocked"}, pre)
    assert d.doors_locked is True


def test_the_dead_read_is_gone_from_the_source() -> None:
    """Pins the absence, so the line cannot quietly come back.

    A behaviour test alone would not catch a reintroduction guarded by an
    ``is None`` check that the per-door block then overrides — the shape this
    defect already had once.
    """
    import inspect

    from custom_components.vag_connect.cariad.auth import _eu_data_act

    src = inspect.getsource(_eu_data_act.map_dataset_to_vehicle_data)
    assert 'first("lock_state", "central_lock_state")' not in src
    assert 'd.doors_locked = str(lock).lower()' not in src
    # positive control: the per-door aggregation this file relies on is present
    assert "locked_state_front_left_door" in src
