"""#1950 — the tailgate lock must not decide the door verdict.

Reported by @Adcad1970 on an Audi A6 e-tron (EU Data Act portal): "Doors Locked"
read unlocked for hours while the car was locked, moving at identical timestamps
with identical values to "Trunk Locked". The cause was the tailgate's lock enum
being folded into the per-door aggregation, so on a delivery that carried only
``locked_state_tailgate`` the door verdict was decided entirely by the boot.

That broke both ways, and the direction he did not see is the worse one:

  * a LOCKED tailgate alone made ``doors_locked`` True -- asserting the doors
    were locked on no door evidence at all;
  * an UNLOCKED tailgate alone made it False -- the mirror he reported;
  * four locked doors plus an UNLOCKED tailgate read False -- the doors were
    locked and the integration said they were not.

Only the tailgate's LOCK state was ever involved. An *open* boot
(``open_state_tailgate``) never touched the door verdict, measured in both
directions and pinned below, so that case was never broken and is not what this
fixes.

The file already knew about this hazard: the note at the bare ``locked`` read
uses a dotted spelling specifically so the trunk cannot "mis-set doors_locked
from the trunk state", and the historical ``door_info.*`` path aggregates
``_HIST_SLOTS`` (doors) while sending ``trunk_lid_lock_status`` to
``trunk_locked`` separately. Only the enum path got it wrong.

The existing portal long-tail tests passed throughout, and the reason is worth
recording accurately, because the obvious guess is wrong. It is *not* that they
all supplied door fields alongside the tailgate: ``test_tailgate_and_bonnet_
open_states`` (tests/test_v2150b10_portal_long_tail.py:74) feeds
``locked_state_tailgate`` with no door field at all, which is precisely the
broken shape, and ``test_1797_state_validity_companions.py:209`` does the same.
They passed because **not one of them asserted** ``doors_locked`` on that
payload. The tests sat directly on the defect and said nothing about it. A field
can be exercised by several tests and still be pinned by none.
"""

from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

LOCKED = "2"
UNLOCKED = "3"

ALL_DOORS_LOCKED = {
    "locked_state_front_left_door": LOCKED,
    "locked_state_front_right_door": LOCKED,
    "locked_state__rear_left_door": LOCKED,  # double underscore, per the spec
    "locked_state_rear_right_door": LOCKED,
}


def _map(fields: dict[str, str], **seed: object) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X", **seed))


# ── the fabrication: a verdict with no door behind it ────────────────────────


def test_a_locked_tailgate_alone_never_claims_the_doors_are_locked() -> None:
    """The security-relevant direction. A shut boot is not four shut doors."""
    d = _map({"locked_state_tailgate": LOCKED})
    assert d.doors_locked is None, (
        "a payload carrying only the tailgate lock stated a door verdict; "
        f"got {d.doors_locked!r}, which no door field reported"
    )


def test_an_unlocked_tailgate_alone_never_claims_the_doors_are_unlocked() -> None:
    d = _map({"locked_state_tailgate": UNLOCKED})
    assert d.doors_locked is None


def test_the_tailgate_still_decides_the_boot() -> None:
    """Dropping it from the door aggregation must not drop it altogether."""
    assert _map({"locked_state_tailgate": LOCKED}).trunk_locked is True
    assert _map({"locked_state_tailgate": UNLOCKED}).trunk_locked is False


# ── the mirror he reported ───────────────────────────────────────────────────


def test_an_unlocked_boot_does_not_unlock_the_doors() -> None:
    """His case, the way it presents: locked car, boot unlocked, doors read
    unlocked."""
    d = _map({**ALL_DOORS_LOCKED, "locked_state_tailgate": UNLOCKED})
    assert d.doors_locked is True, (
        "four locked doors read as unlocked because the boot was unlocked"
    )
    assert d.trunk_locked is False


def test_the_two_verdicts_can_disagree() -> None:
    """The symptom was that they never could. ``!=`` alone would also pass with
    the door verdict left unset, which is a different fix -- so pin both sides
    by value, not just their inequality."""
    d = _map({**ALL_DOORS_LOCKED, "locked_state_tailgate": UNLOCKED})
    assert (d.doors_locked, d.trunk_locked) == (True, False)
    assert d.doors_locked != d.trunk_locked


def test_an_open_boot_never_touched_the_door_verdict() -> None:
    """The boundary of this fix, pinned so the claim stays true. Only the
    tailgate's LOCK enum was ever in the aggregation; its OPEN enum feeds
    ``trunk_open`` and nothing else."""
    d = _map({**ALL_DOORS_LOCKED, "open_state_tailgate": "2"})  # 2 == open
    assert d.doors_locked is True
    assert d.trunk_open is True

    alone = _map({"open_state_tailgate": "2"})
    assert alone.doors_locked is None, (
        "an open-state field reached the door lock verdict"
    )
    assert alone.trunk_open is True


def test_a_tailgate_only_payload_leaves_the_two_unpaired() -> None:
    """The other half of the mirror: equal values, but only one is a reading."""
    d = _map({"locked_state_tailgate": LOCKED})
    assert d.trunk_locked is True
    assert d.doors_locked is None


# ── the aggregation rule itself, unchanged ───────────────────────────────────


def test_all_four_doors_locked_reads_locked() -> None:
    assert _map(ALL_DOORS_LOCKED).doors_locked is True


def test_one_unlocked_door_unlocks_the_car() -> None:
    d = _map({**ALL_DOORS_LOCKED, "locked_state_rear_right_door": UNLOCKED})
    assert d.doors_locked is False


def test_a_single_door_field_is_enough_to_decide() -> None:
    """Deliveries are partial; one real door reading still beats no reading."""
    assert _map({"locked_state_front_left_door": LOCKED}).doors_locked is True
    assert _map({"locked_state_front_left_door": UNLOCKED}).doors_locked is False


def test_unsupported_and_invalid_door_codes_are_still_ignored() -> None:
    """0=unsupported, 1=invalid. Neither is a lock state."""
    d = _map({"locked_state_front_left_door": "0", "locked_state_tailgate": "1"})
    assert d.doors_locked is None
    assert d.trunk_locked is None


def test_the_door_enum_still_overrides_a_stale_bare_locked() -> None:
    """Why this block exists at all: the bare field was reporting a locked car
    as unlocked, so a real per-door reading has to win over it."""
    d = _map(
        {"locked_state_front_left_door": LOCKED, "locked_state_rear_right_door": LOCKED},
        doors_locked=False,
    )
    assert d.doors_locked is True


def test_the_bare_locked_fallback_still_applies_with_no_door_fields() -> None:
    """A tailgate-only payload must fall through to whatever else was read,
    not to a value the tailgate invented."""
    assert _map({"locked": "true"}).doors_locked is True
    assert _map({"locked": "true", "locked_state_tailgate": UNLOCKED}).doors_locked is True


# ── the path that already had it right, pinned so it stays right ─────────────


def test_the_historical_path_aggregates_doors_only() -> None:
    """``door_info.*`` + ``trunk_lid_info.*``: the boot lock has its own field
    there and must stay out of the door verdict."""
    d = _map({"trunk_lid_info.trunk_lid_lock_status.value": "LOCKED"})
    assert d.trunk_locked is True
    assert d.doors_locked is None


def test_the_historical_path_still_reads_its_doors() -> None:
    d = _map(
        {
            f"door_info.{part}.door_lock_status.value": "LOCKED"
            for part in ("front_left", "front_right", "rear_left", "rear_right")
        }
    )
    assert d.doors_locked is True


def test_the_historical_path_unlocks_on_one_open_door() -> None:
    fields = {
        f"door_info.{part}.door_lock_status.value": "LOCKED"
        for part in ("front_left", "front_right", "rear_left")
    }
    fields["door_info.rear_right.door_lock_status.value"] = "UNLOCKED"
    assert _map(fields).doors_locked is False
