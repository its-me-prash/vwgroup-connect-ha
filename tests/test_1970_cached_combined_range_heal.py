# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1970, second half: the combined range a plug-in hybrid stored before this
version must not come back through carry-forward.

5.4.0 stopped the portal mapper from writing the combined cruising range (leaf
153e8c40, "cruising_range_combined") to ``electric_range_km`` when the car
reports fuel. @martinbos's Audi Q3 showed 150 km there against a real 34. But
``electric_range_km`` is in CARRY_FORWARD_FIELDS, so every poll's ``None``
lets ``reconcile`` bring back the stored 150, and the snapshot is persisted, so
an existing install keeps it for good. The tests of the mapper fix ran on a
fresh poll only and could not see this.

Up to 5.4.0 the snapshot did not record which leaf the electric range came
from, and ``reconcile`` drops the owner of a value it carries. So:

* the mapper now names the leaf, and ``reconcile`` carries that name along
  with a carried value: a real electric range keeps its proof over any number
  of polls that lack one;
* a stored value WITHOUT that name was stored by 5.4.0 or earlier. If no
  channel owns it any more (it was carried) on a car that reads the portal
  alone, it is dropped once the car shows the #1970 shape. If the portal
  delivered it in the last poll, it is dropped only when it equals that same
  poll's range_km read from the combined leaf.

What this can drop wrongly: a real electric range that 5.4.0 carried over a
poll without one, at the first poll of this version, and a value from a
channel the car no longer reads. Both come back with the next real value. Every
fresh poll here is built by the real mapper plus the provenance step the
coordinator runs, because the heal reads ``field_source_leaf`` and a
hand-written fresh dict would only test what it was written to contain.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad._channel_merge import annotate_provenance
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import reconcile

_COMBINED = "153e8c40-4c6c-3c17-a11b-0ecc35d55b81"   # "cruising_range_combined"
_PRIMARY = "0ca40e18-0564-3eda-bcc0-7aee9ef44f04"    # "Value of the primary range"
_PORTAL = ("eu_data_act",)


def _q3(combined: int) -> dict[str, str]:
    """martinbos's shape: only the combined range, a fuel level and a real SoC."""
    return {_COMBINED: str(combined), "fuel_level": "40",
            "battery_level_HV.value": "50"}


def _poll(fields: dict[str, str], channel: str = "eu_data_act") -> dict[str, Any]:
    """One poll as the coordinator hands it to ``reconcile``."""
    d = map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))
    return annotate_provenance(channel, d).to_dict()


def _stored(snap: dict[str, Any], armed: tuple[str, ...] = _PORTAL) -> dict[str, Any]:
    """What the coordinator keeps after a poll: the snapshot plus
    ``channel_status``, one key per armed read channel."""
    return {**snap, "channel_status": {token: {"active": True} for token in armed}}


def _legacy(snap: dict[str, Any]) -> dict[str, Any]:
    """The same snapshot as 5.4.0 or earlier stored it: no electric leaf."""
    leaves = {k: v for k, v in snap["field_source_leaf"].items()
              if k != "electric_range_km"}
    return {**snap, "field_source_leaf": leaves}


def _stored_before_540(combined: int) -> dict[str, Any]:
    """A pre-5.4.0 snapshot: the old mapper also put the combined figure on
    electric_range_km, owned by the portal, and named no leaf for it."""
    snap = _poll(_q3(combined))
    snap["electric_range_km"] = combined
    snap["field_sources"] = {**snap["field_sources"],
                             "electric_range_km": "eu_data_act"}
    return _stored(_legacy(snap))


def _carried_since_540(
    stored: int, combined_now: int, armed: tuple[str, ...] = _PORTAL,
) -> dict[str, Any]:
    """A snapshot after a 5.4.0 poll: electric_range_km carried forward, so no
    channel owns it, and range_km is that poll's combined figure."""
    snap = _poll(_q3(combined_now))
    snap["electric_range_km"] = stored
    return _stored(_legacy(snap), armed)


def test_the_fresh_poll_is_the_shape_the_heal_reads() -> None:
    """Instrument check. If the mapper stopped recording the leaf of range_km
    or stopped withholding the combined figure, the red tests below would
    fail for that reason instead of the carry-forward."""
    fresh = _poll(_q3(150))
    assert fresh["electric_range_km"] is None
    assert fresh["range_km"] == 150
    assert fresh["fuel_level"] == 40
    assert fresh["field_source_leaf"].get("range_km") == _COMBINED
    assert "electric_range_km" not in fresh["field_source_leaf"]
    assert fresh["field_sources"].get("electric_range_km") is None


# ── the mapper names the leaf ───────────────────────────────────────────────


@pytest.mark.parametrize(("fields", "value", "leaf"), [
    ({"cruising_range_primary_engine": "380",
      "cruising_range_secondary_engine": "20", "fuel_level": "60"},
     20, "cruising_range_secondary_engine"),
    ({_PRIMARY: "48", "fuel_level": "55", "battery_level_HV.value": "50"},
     48, _PRIMARY),
    ({_COMBINED: "211"}, 211, _COMBINED),
    ({"range": "300", "battery_level_HV.value": "80"}, 300, "range"),
])
def test_the_mapper_names_the_leaf_of_the_electric_range(
    fields: dict[str, str], value: int, leaf: str,
) -> None:
    """One case per chain that can write the electric range: secondary,
    electric-primary, a BEV's combined range, the headline fallback."""
    d = map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))
    assert d.electric_range_km == value
    assert d.field_source_leaf.get("electric_range_km") == leaf


@pytest.mark.parametrize("fields", [
    _q3(150),                                # withheld by the #1970 guard
    {_PRIMARY: "500", "fuel_level": "40"},   # cleared by the #1316 screen
])
def test_a_cleared_electric_range_leaves_no_leaf_behind(fields: dict[str, str]) -> None:
    """The #1316 screen clears the value but leaves ``dist_src`` alone, so the
    name must follow the value, not the bookkeeping."""
    d = map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))
    assert d.electric_range_km is None
    assert "electric_range_km" not in d.field_source_leaf


# ── reconcile carries the leaf with the value ───────────────────────────────


def test_the_leaf_travels_with_a_carried_value() -> None:
    stored = _stored(_poll({_PRIMARY: "48", "fuel_level": "55",
                            "battery_level_HV.value": "50"}))
    fresh = _poll(_q3(150))
    merged, _ = reconcile(stored, fresh)
    assert merged["electric_range_km"] == 48
    assert merged["field_source_leaf"].get("electric_range_km") == _PRIMARY
    assert "electric_range_km" not in fresh["field_source_leaf"]  # not mutated


def test_a_leaf_without_its_value_is_not_carried() -> None:
    """A damaged store: a name with no value. A name must never outlive the
    value it described (#465)."""
    stored = _stored(_poll({_PRIMARY: "48", "fuel_level": "55",
                            "battery_level_HV.value": "50"}))
    stored["electric_range_km"] = None
    merged, _ = reconcile(stored, _poll({"fuel_level": "40"}))
    assert merged["electric_range_km"] is None
    assert "electric_range_km" not in merged["field_source_leaf"]


def test_a_fresh_value_brings_its_own_leaf() -> None:
    stored = _stored(_poll({_PRIMARY: "48", "fuel_level": "55",
                            "battery_level_HV.value": "50"}))
    merged, _ = reconcile(stored, _poll({
        "cruising_range_primary_engine": "380",
        "cruising_range_secondary_engine": "20", "fuel_level": "60",
    }))
    assert merged["electric_range_km"] == 20
    assert (merged["field_source_leaf"].get("electric_range_km")
            == "cruising_range_secondary_engine")


# ── what is dropped ─────────────────────────────────────────────────────────


def test_a_stored_combined_figure_is_not_carried_into_the_next_poll() -> None:
    """The first poll after updating from 5.3.x, combined range unchanged.
    FAILS ON 5.4.0: electric_range_km == 150, carried from the store."""
    merged, _ = reconcile(_stored_before_540(150), _poll(_q3(150)))
    assert merged["electric_range_km"] is None
    assert merged["range_km"] == 150


def test_it_is_dropped_also_when_the_car_drove_since_the_last_poll() -> None:
    """The combined range moved from 150 to 140 between the last old poll and
    the first new one. The stored value still equals the stored range_km, and
    that came from the combined leaf in the same poll.
    FAILS ON 5.4.0: electric_range_km == 150."""
    merged, _ = reconcile(_stored_before_540(150), _poll(_q3(140)))
    assert merged["electric_range_km"] is None
    assert merged["range_km"] == 140


def test_a_carried_value_equal_to_the_current_combined_figure_is_dropped() -> None:
    """A snapshot that already ran 5.4.0, combined range unchanged.
    FAILS ON 5.4.0: electric_range_km == 150."""
    merged, _ = reconcile(_carried_since_540(150, 150), _poll(_q3(150)))
    assert merged["electric_range_km"] is None


def test_a_phantom_frozen_since_540_is_dropped_after_the_car_drove() -> None:
    """The reporter's likely state: 5.4.0 has carried the 150 for a while and
    the combined range has moved on. No combined figure matches any more; the
    value is dropped because no channel owns it, no leaf names it, and the car
    reads the portal alone. FAILS ON 5.4.0: electric_range_km == 150."""
    merged, _ = reconcile(_carried_since_540(150, 120), _poll(_q3(110)))
    assert merged["electric_range_km"] is None


def test_once_dropped_it_stays_gone() -> None:
    first, _ = reconcile(_stored_before_540(150), _poll(_q3(150)))
    second, _ = reconcile(_stored(first), _poll(_q3(138)))
    assert second["electric_range_km"] is None


# ── what must survive ───────────────────────────────────────────────────────


def test_a_real_range_survives_any_number_of_polls_without_one() -> None:
    """Delivered by this version from a real leaf, then two combined-only
    polls. The value has lost its owner after the first, but its leaf
    travelled with it."""
    first = _stored(_poll({_PRIMARY: "48", "fuel_level": "55",
                           "battery_level_HV.value": "50"}))
    second, _ = reconcile(first, _poll(_q3(150)))
    third, _ = reconcile(_stored(second), _poll(_q3(140)))
    assert third["electric_range_km"] == 48
    assert third["field_source_leaf"].get("electric_range_km") == _PRIMARY


def test_a_delivered_old_value_that_equals_no_combined_figure_is_kept() -> None:
    """The portal delivered 34 in the last poll before the update. 5.4.0 never
    delivered the combined figure, so without a match it is a real range."""
    stored = _carried_since_540(34, 150)
    stored["field_sources"] = {**stored["field_sources"],
                               "electric_range_km": "eu_data_act"}
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 34


def test_a_delivered_old_value_equal_to_this_polls_combined_figure_is_kept() -> None:
    """5.4.0 delivered a real 40 in the last poll; the tank has since run low
    and this poll's combined range happens to be 40 too. Only the SAME poll's
    range_km proves a phantom; a match with a later poll is a coincidence."""
    stored = _legacy(_stored(_poll({_PRIMARY: "40", "fuel_level": "55",
                                    "battery_level_HV.value": "50"})))
    assert stored["field_sources"]["electric_range_km"] == "eu_data_act"
    merged, _ = reconcile(stored, _poll(_q3(40)))
    assert merged["electric_range_km"] == 40


def test_a_phantom_without_any_stored_leaf_goes_one_poll_later() -> None:
    """A snapshot from before 5.1.0 named no leaf at all, so the same-poll
    proof is missing. The phantom is carried once, loses its owner, and the
    next poll with the #1970 shape drops it."""
    stored = _stored_before_540(150)
    stored["field_source_leaf"] = {}
    first, _ = reconcile(stored, _poll(_q3(140)))
    assert first["electric_range_km"] == 150
    second, _ = reconcile(_stored(first), _poll(_q3(130)))
    assert second["electric_range_km"] is None


def test_a_value_another_channel_delivered_is_kept() -> None:
    stored = _stored_before_540(150)
    stored["field_sources"]["electric_range_km"] = "website_authproxy"
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 150


def test_a_carried_value_on_a_car_with_another_channel_is_kept() -> None:
    """Without an owner, the value may have come from the other channel."""
    stored = _carried_since_540(150, 120, armed=("eu_data_act", "website_authproxy"))
    merged, _ = reconcile(stored, _poll(_q3(110)))
    assert merged["electric_range_km"] == 150


def test_a_carried_value_without_a_channel_record_is_kept() -> None:
    """No channel_status, no way to tell the portal is the only reader."""
    stored = _carried_since_540(150, 120)
    del stored["channel_status"]
    merged, _ = reconcile(stored, _poll(_q3(110)))
    assert merged["electric_range_km"] == 150


def test_a_value_from_an_export_import_is_kept() -> None:
    """#1780: an imported value carries forward on purpose."""
    stored = _stored_before_540(150)
    stored["field_imported_from_export"] = ["electric_range_km"]
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 150


def test_a_poll_without_the_combined_leaf_carries_as_before() -> None:
    """The fresh poll has no range at all, so it shows nothing about the
    stored value: old but visible, exactly as before."""
    merged, _ = reconcile(
        _stored_before_540(150),
        _poll({"fuel_level": "40", "battery_level_HV.value": "50"}),
    )
    assert merged["electric_range_km"] == 150


def test_an_old_snapshot_of_a_car_without_fuel_keeps_its_range() -> None:
    """On a car without fuel the combined range IS the electric range. A
    portal poll from a BEV always delivers it, so the omission is forced here
    to reach the fuel clause on its own."""
    stored = _stored(_legacy(_poll({_COMBINED: "211"})))
    assert stored["electric_range_km"] == 211
    fresh = _poll({_COMBINED: "211"})
    fresh["electric_range_km"] = None
    merged, _ = reconcile(stored, fresh)
    assert merged["electric_range_km"] == 211


def test_a_real_electric_range_in_the_fresh_poll_wins() -> None:
    """#555/#565 shape: a secondary range is the electric range."""
    merged, _ = reconcile(_stored_before_540(150), _poll({
        "cruising_range_primary_engine": "380",
        "cruising_range_secondary_engine": "20",
        "fuel_level": "60",
    }))
    assert merged["electric_range_km"] == 20


def _reserve(fields: dict[str, str]) -> dict[str, Any]:
    stored = _stored(_poll({**fields, "fuel_level": "5",
                            "battery_level_HV.value": "50"}))
    assert stored["electric_range_km"] == 34
    assert stored["field_sources"]["electric_range_km"] == "eu_data_act"
    return stored


def test_a_real_range_equal_to_the_combined_one_at_fuel_reserve_is_kept() -> None:
    """At fuel reserve the combustion range can read 0 while the fuel level
    does not, so the combined range equals the electric one. Stored by this
    version, the leaf says where the 34 came from."""
    stored = _reserve({"cruising_range_secondary_engine": "34", _COMBINED: "34"})
    merged, _ = reconcile(stored, _poll(_q3(34)))
    assert merged["electric_range_km"] == 34


def test_the_reserve_case_carried_by_540_via_a_named_primary_is_kept() -> None:
    """Stored before this version, so no leaf, and already carried once, so
    no owner either. The poll named its primary (combustion) range, 0, and
    only the secondary engine field still holds the 34."""
    stored = _legacy(_reserve({"cruising_range_primary_engine": "0",
                               "cruising_range_secondary_engine": "34"}))
    stored["field_sources"] = {k: v for k, v in stored["field_sources"].items()
                               if k != "electric_range_km"}
    assert stored["secondary_engine_range_km"] == 34
    assert stored["combustion_range_km"] == 0
    merged, _ = reconcile(stored, _poll(_q3(34)))
    assert merged["electric_range_km"] == 34


def test_the_reserve_case_from_an_old_snapshot_via_the_official_leaf_is_kept() -> None:
    """Same, through the official secondary leaf, which fills no secondary
    engine field; the combustion field holds the 34 instead."""
    stored = _legacy(_reserve({"estimatedcruisingrangesecondary.value": "34",
                               _COMBINED: "34"}))
    assert stored["secondary_engine_range_km"] is None
    assert stored["combustion_range_km"] == 34
    merged, _ = reconcile(stored, _poll(_q3(34)))
    assert merged["electric_range_km"] == 34


def test_an_old_primary_electric_range_is_kept() -> None:
    """A plug-in whose primary range is the electric one (0ca40e18), stored
    before this version. Its stored range_km equals the electric range but
    came from that leaf, not the combined one, so the equality proves
    nothing."""
    stored = _legacy(_stored(_poll({_PRIMARY: "48", "fuel_level": "55",
                                    "battery_level_HV.value": "50"})))
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 48
