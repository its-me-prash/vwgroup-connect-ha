# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1970, second half: the combined range a plug-in hybrid stored before 5.4.0
must not come back through carry-forward.

5.4.0 stopped the portal mapper from writing the combined cruising range (leaf
153e8c40, "cruising_range_combined") to ``electric_range_km`` when the car
reports fuel. @martinbos's Audi Q3 showed 150 km there against a real 34. But
``electric_range_km`` is in CARRY_FORWARD_FIELDS, so every poll's ``None``
lets ``reconcile`` bring back the stored 150, and the snapshot is persisted, so
an existing install keeps it for good. The tests of the mapper fix ran on a
fresh poll only and could not see this.

The snapshot does not record which leaf the stored value came from:
``field_source_leaf`` names only the leaves read with ``record_as``, and the
electric range is not one of them. So the heal works on proof: the fresh poll
shows the #1970 shape, and the stored value equals a combined figure. Every
fresh poll here is built by the real mapper plus the provenance step the
coordinator runs, because the heal reads ``field_source_leaf`` and a
hand-written fresh dict would only test what it was written to contain.
"""
from __future__ import annotations

from typing import Any

from custom_components.vag_connect.cariad._channel_merge import annotate_provenance
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import reconcile

_COMBINED = "153e8c40-4c6c-3c17-a11b-0ecc35d55b81"   # "cruising_range_combined"
_PRIMARY = "0ca40e18-0564-3eda-bcc0-7aee9ef44f04"    # "Value of the primary range"


def _q3(combined: int) -> dict[str, str]:
    """martinbos's shape: only the combined range, a fuel level and a real SoC."""
    return {_COMBINED: str(combined), "fuel_level": "40",
            "battery_level_HV.value": "50"}


def _poll(fields: dict[str, str], channel: str = "eu_data_act") -> dict[str, Any]:
    """One poll as the coordinator hands it to ``reconcile``."""
    d = map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))
    return annotate_provenance(channel, d).to_dict()


def _stored_before_540(combined: int) -> dict[str, Any]:
    """The snapshot a pre-5.4.0 install kept: the same poll, but the old mapper
    also put the combined figure on electric_range_km, owned by the portal."""
    snap = _poll(_q3(combined))
    snap["electric_range_km"] = combined
    snap["field_sources"] = {**snap["field_sources"],
                             "electric_range_km": "eu_data_act"}
    return snap


def _carried_since_540(
    stored: int, combined_now: int, armed: tuple[str, ...] = ("eu_data_act",),
) -> dict[str, Any]:
    """The snapshot after a 5.4.0 poll: electric_range_km carried forward, so
    no channel owns it, and range_km is that poll's combined figure.
    ``channel_status`` is what the coordinator stores after every poll, one
    key per armed read channel."""
    snap = _poll(_q3(combined_now))
    snap["electric_range_km"] = stored
    snap["channel_status"] = {token: {"active": True} for token in armed}
    return snap


def test_the_fresh_poll_is_the_shape_the_heal_reads() -> None:
    """Instrument check. If the mapper stopped recording the leaf of range_km
    or stopped withholding the combined figure, every red test below would
    fail for that reason instead of the carry-forward."""
    fresh = _poll(_q3(150))
    assert fresh["electric_range_km"] is None
    assert fresh["range_km"] == 150
    assert fresh["fuel_level"] == 40
    assert fresh["field_source_leaf"].get("range_km") == _COMBINED
    assert fresh["field_sources"].get("electric_range_km") is None


def test_a_stored_combined_figure_is_not_carried_into_the_next_poll() -> None:
    """The first poll after updating from 5.3.x, combined range unchanged.
    FAILS BEFORE THE FIX: electric_range_km == 150, carried from the store."""
    merged, _ = reconcile(_stored_before_540(150), _poll(_q3(150)))
    assert merged["electric_range_km"] is None
    assert merged["range_km"] == 150


def test_it_is_dropped_also_when_the_car_drove_since_the_last_poll() -> None:
    """The combined range moved from 150 to 140 between the last old poll and
    the first new one. The stored value still equals the stored range_km, and
    that one came from the combined leaf in the same poll.
    FAILS BEFORE THE FIX: electric_range_km == 150."""
    merged, _ = reconcile(_stored_before_540(150), _poll(_q3(140)))
    assert merged["electric_range_km"] is None
    assert merged["range_km"] == 140


def test_a_carried_value_equal_to_the_current_combined_figure_is_dropped() -> None:
    """A snapshot that already ran 5.4.0: no owner, but the value is this
    poll's combined figure. FAILS BEFORE THE FIX: electric_range_km == 150."""
    merged, _ = reconcile(_carried_since_540(150, 150), _poll(_q3(150)))
    assert merged["electric_range_km"] is None


def test_once_dropped_it_stays_gone() -> None:
    """The next poll must not find anything to bring back."""
    first, _ = reconcile(_stored_before_540(150), _poll(_q3(150)))
    second, _ = reconcile(first, _poll(_q3(138)))
    assert second["electric_range_km"] is None


# ── what must survive ───────────────────────────────────────────────────────


def test_a_value_that_equals_no_combined_figure_is_kept() -> None:
    """A real electric range carried over a poll that lacked one: 34 is no
    combined figure, so it stays. This is also where the heal stops: a phantom
    frozen since 5.4.0 looks the same once the car has driven, and the data
    cannot tell the two apart."""
    merged, _ = reconcile(_carried_since_540(34, 150), _poll(_q3(150)))
    assert merged["electric_range_km"] == 34


def test_a_value_another_channel_delivered_is_kept() -> None:
    """Even when it equals the combined figure, a value the portal did not
    deliver is not the portal's phantom."""
    stored = _stored_before_540(150)
    stored["field_sources"]["electric_range_km"] = "website_authproxy"
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 150


def test_a_carried_value_on_a_car_with_another_channel_is_kept() -> None:
    """A carried value has lost its owner (reconcile does not carry
    field_sources along). On a car that also reads another channel it may
    have come from there, so equality with the combined figure is a
    coincidence, not proof."""
    stored = _carried_since_540(150, 150, armed=("eu_data_act", "website_authproxy"))
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 150


def test_a_carried_value_without_a_channel_record_is_kept() -> None:
    """No channel_status, no way to tell the portal is the only reader."""
    stored = _carried_since_540(150, 150)
    del stored["channel_status"]
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 150


def test_a_real_range_equal_to_the_combined_one_at_fuel_reserve_is_kept() -> None:
    """At fuel reserve the combustion range can read 0 while the fuel level
    does not, so the combined range equals the electric one. Here the stored
    34 came from the secondary leaf; a later poll without that leaf must not
    drop it although 34 is also this poll's combined figure."""
    stored = _poll({"cruising_range_secondary_engine": "34", _COMBINED: "34",
                    "fuel_level": "5", "battery_level_HV.value": "50"})
    assert stored["electric_range_km"] == 34
    assert stored["field_sources"]["electric_range_km"] == "eu_data_act"
    merged, _ = reconcile(stored, _poll(_q3(34)))
    assert merged["electric_range_km"] == 34


def test_the_reserve_case_with_a_named_primary_leaf_is_kept() -> None:
    """Same, but the stored poll named its primary (combustion) range, 0, so
    only the secondary engine field still holds the 34."""
    stored = _poll({"cruising_range_primary_engine": "0",
                    "cruising_range_secondary_engine": "34",
                    "fuel_level": "5", "battery_level_HV.value": "50"})
    assert stored["electric_range_km"] == 34
    assert stored["secondary_engine_range_km"] == 34
    assert stored["combustion_range_km"] == 0
    merged, _ = reconcile(stored, _poll(_q3(34)))
    assert merged["electric_range_km"] == 34


def test_the_reserve_case_with_the_official_secondary_leaf_is_kept() -> None:
    """Same, through the official secondary leaf, which fills no secondary
    engine field; the combustion field holds the 34 instead."""
    stored = _poll({"estimatedcruisingrangesecondary.value": "34", _COMBINED: "34",
                    "fuel_level": "5", "battery_level_HV.value": "50"})
    assert stored["electric_range_km"] == 34
    assert stored["secondary_engine_range_km"] is None
    assert stored["combustion_range_km"] == 34
    merged, _ = reconcile(stored, _poll(_q3(34)))
    assert merged["electric_range_km"] == 34


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


def test_a_car_without_fuel_keeps_its_range() -> None:
    """On a car without fuel the combined range IS the electric range. A
    portal poll from a BEV always delivers it, so the omission is forced here
    to reach the fuel clause on its own."""
    stored = _poll({_COMBINED: "211"})
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


def test_a_legit_primary_electric_range_carries_as_before() -> None:
    """A plug-in whose primary range is the electric one (0ca40e18). Its
    stored range_km equals the stored electric range, but came from that leaf,
    not the combined one, so the equality proves nothing and the value stays
    when a later poll carries only the combined leaf."""
    stored = _poll({_PRIMARY: "48", "fuel_level": "55",
                    "battery_level_HV.value": "50"})
    assert stored["electric_range_km"] == 48
    merged, _ = reconcile(stored, _poll(_q3(150)))
    assert merged["electric_range_km"] == 48
