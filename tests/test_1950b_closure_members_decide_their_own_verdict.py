# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The #1950 rule, applied to the four sites where it was still live.

#1950 fixed one instance on the EU Data Act portal mapper: the tailgate's lock
enum sat in the per-door ``doors_locked`` aggregation, so the boot decided
whether the doors were locked. A sweep afterwards found the same class of defect
in four more places, every one of them measured rather than reasoned about:

* ``vw_na`` ``doorStatus`` dict-iteration fallback — trunk and hood rode in the
  list that decides BOTH ``doors_open`` and ``doors_locked``;
* ``vw_na`` ``exteriorStatus.doorLockStatus`` roll-up — same, for the lock;
* ``vw_na`` ``windowStatus`` dict-iteration fallback — the roof rode in
  ``windows_open``, and had no other outlet at all;
* ``vw_eu`` ``access.accessStatus.value.doors`` and ``…value.windows`` — the
  bonnet and the boot rode in ``doors_open``, the roof in ``windows_open``, and
  neither ``hood_open`` nor ``sunroof_open`` was ever written in that file, so
  their only effect was to corrupt an aggregate they did not belong to.

``vw_eu`` is inherited unchanged by the Audi, Bentley, Lamborghini, VW
Commercial and Audi-NA clients, so that pair was six brands wide.

**The defect breaks twice, and the second way is the one nobody reports.** It
inverts the verdict against the real members (four locked doors plus an unlocked
boot reads as unlocked), and on a delivery that carries no member of the verdict
at all, a single non-member fabricates one — a locked boot alone reported "doors
locked" on no door evidence whatsoever. ``all([])`` is ``True``: an empty list
asserts everything.

**Two things this deliberately does NOT do.**

``doors_individual`` keeps every member, boot and bonnet included. That is not
an oversight: ``_DOOR_TKEYS`` in ``binary_sensor.py`` carries translated keys
for both and ``VagDoorSensor`` is documented as covering "eine einzelne Tür/
Kofferraum/Motorhaube". Those per-closure entities are intended, and deleting
two supported entities to fix an aggregate would be the wrong trade. Only the
*aggregate* changed.

``windows_individual`` is the opposite case and loses its roof members, because
``_WINDOW_TKEYS`` has no entry for ``roofCover`` or ``sunRoofRear`` — so they
surfaced as WINDOW entities named after the raw backend key. They move to
``sunroof_open``, which already exists and already has a translated name.

The exclusions are DENY-lists, never allow-lists of door names. Both
dict-iteration fallbacks exist precisely so firmware-specific door-id sets work
without an enum list, so an unrecognised spelling has to keep counting as a door
exactly as it did before — otherwise this fix would quietly drop a door the next
firmware invents.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.api.vw_na import VWNAClient
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZAUZFW000000"


# ── harnesses ───────────────────────────────────────────────────────────────


def na(raw: dict[str, Any]) -> VehicleData:
    """The repo's own vw_na pattern: client via __new__, only the HTTP faked."""
    c = VWNAClient.__new__(VWNAClient)
    c._base = "https://example.test"
    c._vin_to_uuid = {VIN: VIN}
    c._vin_to_model = {VIN: "ID.4 Pro"}
    c._vin_to_nickname = {VIN: "test"}
    c._get = AsyncMock(side_effect=[raw, {}, {}])
    return asyncio.run(c.get_status(VIN))


def eu(doors: list | None = None, windows: list | None = None) -> VehicleData:
    c = VWEUClient.__new__(VWEUClient)
    access: dict[str, Any] = {}
    if doors is not None:
        access["doors"] = doors
    if windows is not None:
        access["windows"] = windows
    return c._parse_status(VIN, {"access": {"accessStatus": {"value": access}}}, {})


def member(name: str, *tokens: str) -> dict[str, Any]:
    return {"name": name, "status": list(tokens)}


# The dict-iteration fallback only engages when the explicit ``*Door`` /
# ``*Window`` keys are absent, so these fixtures use the short spellings.
NA_DOORS_CLOSED = {
    "frontLeft": "CLOSED", "frontRight": "CLOSED",
    "rearLeft": "CLOSED", "rearRight": "CLOSED",
}
NA_DOORS_LOCKED = {
    "frontLeft": "LOCKED", "frontRight": "LOCKED",
    "rearLeft": "LOCKED", "rearRight": "LOCKED",
}
NA_WINDOWS_CLOSED = {
    "frontLeft": "CLOSED", "frontRight": "CLOSED",
    "rearLeft": "CLOSED", "rearRight": "CLOSED",
}
EU_DOORS_CLOSED = [
    member("frontLeft", "locked", "closed"), member("frontRight", "locked", "closed"),
    member("rearLeft", "locked", "closed"), member("rearRight", "locked", "closed"),
]
EU_WINDOWS_CLOSED = [
    member("frontLeft", "closed"), member("frontRight", "closed"),
    member("rearLeft", "closed"), member("rearRight", "closed"),
]


# ── vw_na: doorStatus fallback ──────────────────────────────────────────────


@pytest.mark.parametrize("non_door", ["trunk", "hood"], ids=["trunk", "hood"])
def test_na_an_open_non_door_does_not_open_a_door(non_door: str) -> None:
    d = na({"doorStatus": {**NA_DOORS_CLOSED, non_door: "OPEN"}})
    assert d.doors_open is False, (
        f"four closed doors reported open because the {non_door} was open"
    )


def test_na_the_non_door_keeps_its_own_field() -> None:
    """Excluding it from the aggregate must not drop the reading."""
    assert na({"doorStatus": {**NA_DOORS_CLOSED, "trunk": "OPEN"}}).trunk_open is True
    assert na({"doorStatus": {**NA_DOORS_CLOSED, "hood": "OPEN"}}).hood_open is True


def test_na_a_non_door_alone_states_no_door_verdict() -> None:
    """The fabrication direction. No door reported, so no door verdict."""
    d = na({"doorStatus": {"trunk": "OPEN"}})
    assert d.doors_open is None
    assert d.trunk_open is True


def test_na_an_unlocked_boot_does_not_unlock_the_car() -> None:
    d = na({"doorStatus": {**NA_DOORS_LOCKED, "trunk": "UNLOCKED"}})
    assert d.doors_locked is True, "the boot unlocked four locked doors"


def test_na_all_doors_locked_still_reads_locked() -> None:
    assert na({"doorStatus": NA_DOORS_LOCKED}).doors_locked is True


def test_na_one_unlocked_door_still_unlocks_the_car() -> None:
    d = na({"doorStatus": {**NA_DOORS_LOCKED, "rearRight": "UNLOCKED"}})
    assert d.doors_locked is False


def test_na_an_unrecognised_member_is_still_treated_as_a_door() -> None:
    """The deny-list must not become an allow-list: this fallback exists so a
    firmware-specific door id works without being enumerated anywhere."""
    d = na({"doorStatus": {**NA_DOORS_CLOSED, "middleSlidingLeft": "OPEN"}})
    assert d.doors_open is True


# ── vw_na: exteriorStatus.doorLockStatus ────────────────────────────────────


def test_na_exterior_lock_roll_up_excludes_the_boot() -> None:
    d = na({"exteriorStatus": {"doorLockStatus": {
        **NA_DOORS_LOCKED, "trunk": "UNLOCKED"}}})
    assert d.doors_locked is True


def test_na_exterior_lock_roll_up_does_not_invent_from_the_boot() -> None:
    """The dangerous direction, in the other dialect: a locked boot alone used
    to report the doors locked on no door evidence."""
    d = na({"exteriorStatus": {"doorLockStatus": {"trunk": "LOCKED"}}})
    assert d.doors_locked is None


def test_na_exterior_lock_roll_up_still_works_on_doors() -> None:
    d = na({"exteriorStatus": {"doorLockStatus": NA_DOORS_LOCKED}})
    assert d.doors_locked is True


# ── vw_na: windowStatus fallback ────────────────────────────────────────────


def test_na_an_open_roof_does_not_open_a_window() -> None:
    d = na({"windowStatus": {**NA_WINDOWS_CLOSED, "sunroof": "OPEN"}})
    assert d.windows_open is False


def test_na_the_roof_gets_its_own_field_rather_than_being_dropped() -> None:
    """There was no sunroof mapping in this file at all, so excluding the roof
    without routing it would have lost the reading entirely."""
    assert na({"windowStatus": {**NA_WINDOWS_CLOSED, "sunroof": "OPEN"}}).sunroof_open is True
    assert na({"windowStatus": {**NA_WINDOWS_CLOSED, "sunroof": "CLOSED"}}).sunroof_open is False


def test_na_a_roof_alone_states_no_window_verdict() -> None:
    d = na({"windowStatus": {"sunroof": "OPEN"}})
    assert d.windows_open is None
    assert d.sunroof_open is True


def test_na_an_open_window_still_opens_the_aggregate() -> None:
    d = na({"windowStatus": {**NA_WINDOWS_CLOSED, "rearLeft": "OPEN"}})
    assert d.windows_open is True


# ── vw_eu: doors ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("non_door", ["bonnet", "trunk"], ids=["bonnet", "trunk"])
def test_eu_an_open_non_door_does_not_open_a_door(non_door: str) -> None:
    d = eu(doors=[*EU_DOORS_CLOSED, member(non_door, "open")])
    assert d.doors_open is False


def test_eu_a_non_door_alone_states_no_door_verdict() -> None:
    d = eu(doors=[member("trunk", "unlocked", "open")])
    assert d.doors_open is None
    assert d.trunk_open is True


def test_eu_the_bonnet_gets_its_own_field() -> None:
    """Before this, ``hood_open`` was never written anywhere in vw_eu, so the
    bonnet's only effect was to corrupt the door aggregate."""
    assert eu(doors=[*EU_DOORS_CLOSED, member("bonnet", "open")]).hood_open is True
    assert eu(doors=[*EU_DOORS_CLOSED, member("bonnet", "closed")]).hood_open is False


def test_eu_the_per_closure_entities_keep_every_member() -> None:
    """Deliberate: _DOOR_TKEYS translates ``trunk`` and ``bonnet`` on purpose,
    so those entities must survive the aggregate fix."""
    d = eu(doors=[*EU_DOORS_CLOSED, member("bonnet", "open"),
                  member("trunk", "unlocked", "closed")])
    assert set(d.doors_individual) == {
        "frontLeft", "frontRight", "rearLeft", "rearRight", "bonnet", "trunk",
    }
    assert d.doors_individual["bonnet"] is True
    assert d.doors_individual["trunk"] is False


def test_eu_an_open_door_still_opens_the_aggregate() -> None:
    d = eu(doors=[member("frontLeft", "unlocked", "open"),
                  member("frontRight", "locked", "closed"),
                  member("bonnet", "closed")])
    assert d.doors_open is True


# ── vw_eu: windows ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "roof", ["roofCover", "sunRoof", "sunRoofRear"],
    ids=["roofCover", "sunRoof", "sunRoofRear"],
)
def test_eu_an_open_roof_does_not_open_a_window(roof: str) -> None:
    d = eu(windows=[*EU_WINDOWS_CLOSED, member(roof, "open")])
    assert d.windows_open is False
    assert d.sunroof_open is True


@pytest.mark.parametrize(
    "roof", ["roofCover", "sunRoof", "sunRoofRear"],
    ids=["roofCover", "sunRoof", "sunRoofRear"],
)
def test_eu_the_roof_is_not_a_window_entity(roof: str) -> None:
    """_WINDOW_TKEYS has no translation for these, so they surfaced as window
    entities named after the raw backend key."""
    d = eu(windows=[*EU_WINDOWS_CLOSED, member(roof, "open")])
    assert roof not in d.windows_individual
    assert set(d.windows_individual) == {
        "frontLeft", "frontRight", "rearLeft", "rearRight",
    }


def test_eu_a_roof_alone_states_no_window_verdict() -> None:
    d = eu(windows=[member("sunRoof", "open")])
    assert d.windows_open is None
    assert d.sunroof_open is True


def test_eu_an_open_window_still_opens_the_aggregate() -> None:
    d = eu(windows=[member("frontLeft", "open"), member("frontRight", "closed")])
    assert d.windows_open is True


def test_eu_an_unrecognised_window_member_still_counts() -> None:
    d = eu(windows=[*EU_WINDOWS_CLOSED, member("tailgateWindow", "open")])
    assert d.windows_open is True


# ── closures_secured: the fifth site, and the opposite remedy ───────────────
#
# This one was not an arithmetic error but a NAME error: the entity is published
# as "All closures secured" while deciding from at most three doors (the spec
# documents safe_state only for front_right / rear_left / rear_right; there is
# no front_left field). Measured before the change: three safe doors plus an
# OPEN tailgate gave True while ``trunk_open`` was True on the same object.
#
# Prash's decision (2026-10-28) was to widen the arithmetic so the name becomes
# true, rather than rename the entity. The widening uses the boot's and the
# bonnet's OPEN state and explicitly not their ``safe_state_*`` fields — that is
# the exact regression v4.7.11 fixed, after a live SEAT/CUPRA delivery carried
# ``safe_state_front_engine_bonnet=3`` on a CLOSED bonnet. The last test here
# pins that case so the widening cannot resurrect it.

from custom_components.vag_connect.cariad.auth._eu_data_act import (  # noqa: E402
    map_dataset_to_vehicle_data,
)

# The three door safe_state fields the dictionary documents. There is no
# ``safe_state_front_left_door`` in the spec at all.
#
# Single underscore on rear_left, and that is not a typo: the spec is
# inconsistent on exactly this door, writing ``locked_state__rear_left_door``
# with two underscores but ``safe_state_rear_left_door`` and
# ``open_state_rear_left_door`` with one. The mapper matches all three verbatim.
# An earlier draft of this fixture used two here, which silently read nothing
# and left only two doors in play — so the fixture, not the code, was wrong.
PORTAL_DOORS_SAFE = {
    "safe_state_front_right_door": "2",
    "safe_state_rear_left_door": "2",
    "safe_state_rear_right_door": "2",
}


def portal(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin=VIN))


def test_an_open_boot_is_not_all_closures_secured() -> None:
    """The reported absurdity: the boot standing open while the entity claimed
    every closure was secured."""
    d = portal({**PORTAL_DOORS_SAFE, "open_state_tailgate": "2"})  # 2 == open
    assert d.trunk_open is True
    assert d.closures_secured is False


def test_an_open_bonnet_is_not_all_closures_secured() -> None:
    d = portal({**PORTAL_DOORS_SAFE, "open_state_front_engine_bonnet": "2"})
    assert d.hood_open is True
    assert d.closures_secured is False


@pytest.mark.parametrize(
    "extra",
    [{}, {"open_state_tailgate": "3"}, {"open_state_front_engine_bonnet": "3"}],
    ids=["doors-only", "boot-closed", "bonnet-closed"],
)
def test_secured_doors_with_nothing_open_still_reads_secured(
    extra: dict[str, str]
) -> None:
    assert portal({**PORTAL_DOORS_SAFE, **extra}).closures_secured is True


def test_one_unsafe_door_still_decides() -> None:
    d = portal({**PORTAL_DOORS_SAFE, "safe_state_rear_right_door": "3",
                "open_state_tailgate": "3"})
    assert d.closures_secured is False


def test_no_usable_door_reading_states_no_verdict() -> None:
    """0 = unsupported, 1 = invalid. Neither is a safe state, and an empty set
    must not become a verdict."""
    d = portal({"safe_state_front_right_door": "0",
                "safe_state_rear_right_door": "1"})
    assert d.closures_secured is None


def test_the_v4_7_11_bonnet_regression_does_not_come_back() -> None:
    """A live SEAT/CUPRA delivery carried ``safe_state_front_engine_bonnet=3``
    while ``open_state_front_engine_bonnet=3`` said the bonnet was CLOSED. The
    dictionary documents no safe(2) for the bonnet at all, so that 3 is not a
    usable unsafe signal. Widening the aggregate must therefore read the OPEN
    state, never the safe_state — otherwise this flips to False on a car whose
    bonnet is shut, which is what v4.7.11 fixed.
    """
    d = portal({
        **PORTAL_DOORS_SAFE,
        "safe_state_front_engine_bonnet": "3",      # not a reliable "unsafe"
        "open_state_front_engine_bonnet": "3",      # 3 == closed
    })
    assert d.hood_open is False
    assert d.closures_secured is True, (
        "the bonnet's undocumented safe_state=3 flipped a secured car to "
        "unsecured again -- the v4.7.11 regression"
    )
