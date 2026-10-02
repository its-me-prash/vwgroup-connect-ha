# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1637 and 21 more Scouts in two days — the snapshot envelope's ``trigger``
leaf flooded the Scout surface across four brands (VW, VW Commercial, Audi,
CUPRA), always carrying ``TRIGGER_NO_REASON``.

It is mapped to its OWN field rather than into ``report_trigger``: the official
V6.0 portal field catalogue (@Testius007's export in #923) lists 6610 data
points including ``trigger_type`` ("Trigger of the call service": ROA / ICL /
USM / ICL_REMOTE / ROA_REMOTE) and contains no ``trigger`` entry at all, so the
two are different things with disjoint vocabularies. Folding them together would
make a single sensor report values from two unrelated enums.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict, base: VehicleData | None = None) -> VehicleData:
    return map_dataset_to_vehicle_data(
        _walk_fields({"eu_data_act": fields}), base or VehicleData(vin="X")
    )


def test_observed_value_maps_with_prefix_stripped() -> None:
    # the only value seen in the wild, across all 22 reports
    assert _map({"trigger": "TRIGGER_NO_REASON"}).portal_delivery_trigger == "NO_REASON"


def test_a_real_trigger_would_surface_too() -> None:
    # the point of mapping instead of suppressing: an unseen value still shows up
    d = _map({"trigger": "TRIGGER_DOOR_OPENED"})
    assert d.portal_delivery_trigger == "DOOR_OPENED"


def test_unprefixed_value_passes_through() -> None:
    assert _map({"trigger": "SOMETHING_ELSE"}).portal_delivery_trigger == "SOMETHING_ELSE"


def test_absent_leaf_stays_none() -> None:
    assert _map({}).portal_delivery_trigger is None


def test_does_not_touch_report_trigger() -> None:
    # the disjoint-vocabulary guarantee: the envelope marker must never land in
    # the trigger_type sensor, and trigger_type must keep its own value.
    d = _map({"trigger": "TRIGGER_NO_REASON", "trigger_type": "ROA"})
    assert d.report_trigger == "ROA"
    assert d.portal_delivery_trigger == "NO_REASON"


def test_envelope_marker_alone_leaves_report_trigger_empty() -> None:
    d = _map({"trigger": "TRIGGER_NO_REASON"})
    assert d.report_trigger is None


def test_existing_value_is_not_overwritten() -> None:
    base = VehicleData(vin="X")
    base.portal_delivery_trigger = "ALREADY_SET"
    assert _map({"trigger": "TRIGGER_NO_REASON"}, base).portal_delivery_trigger == (
        "ALREADY_SET"
    )


def test_both_spellings_reclaimed_from_the_scout_surface() -> None:
    # the flattener emits the eu_data_act-prefixed path AND the bare leaf; if
    # first() named only one, the twin stayed unmapped and the Scout re-filed it
    # every poll — which is how 22 issues happened.
    syn: dict = {}
    flat = _walk_fields({"eu_data_act": {"trigger": "TRIGGER_NO_REASON"}}, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    assert d.portal_delivery_trigger == "NO_REASON"
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert "trigger" not in leaves, "bare twin still floods the Scout"
