# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1444 (@josie127-neu, Audi) — ``battery_care_mode.bcam_notification``.

The leaf had been left Scout-visible on purpose ("the rest of the
battery_care_mode.* family stays Scout-visible") because its meaning was a
guess. The official V6.0 field catalogue documents it as an enum with a full
value list, so there is nothing left to guess — and a held leaf is re-reported on
every single poll, which is how one unmapped field becomes a stream of issues.

Catalogue values: ``BCAM_NOTIFICATION_INVALID``,
``IMMEDIATE_CHARGING_SOC_RESET_IN_NEXT_CHARGING_PROCESS``,
``IMMEDIATE_CHARGING_NOTIFY_BCAM_IS_OFF``,
``EXTENDED_CHARGING_SOC_RESET_IN_NEXT_CHARGING_PROCESS``,
``EXTENDED_CHARGING_NOTIFY_BCAM_IS_OFF``, ``BCAM_SCORE_VALUE_WARNING``,
``BCAM_SCORE_VALUE_REACHED``.
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


def _note(value: str, base: VehicleData | None = None):
    return _map(
        {"battery_care_mode": {"bcam_notification": value}}, base
    ).battery_care_notification


def test_every_documented_value_maps():
    for v in (
        "IMMEDIATE_CHARGING_SOC_RESET_IN_NEXT_CHARGING_PROCESS",
        "IMMEDIATE_CHARGING_NOTIFY_BCAM_IS_OFF",
        "EXTENDED_CHARGING_SOC_RESET_IN_NEXT_CHARGING_PROCESS",
        "EXTENDED_CHARGING_NOTIFY_BCAM_IS_OFF",
        "BCAM_SCORE_VALUE_WARNING",
        "BCAM_SCORE_VALUE_REACHED",
    ):
        assert _note(v) == v, v


def test_the_prefixed_invalid_sentinel_is_dropped():
    # BCAM_NOTIFICATION_INVALID is the family's "nothing to report" value and
    # must not become a visible state
    assert _note("BCAM_NOTIFICATION_INVALID") is None
    assert _note("INVALID") is None


def test_the_prefix_is_stripped_when_present():
    assert _note("BCAM_NOTIFICATION_BCAM_SCORE_VALUE_REACHED") == (
        "BCAM_SCORE_VALUE_REACHED"
    )


def test_absent_and_blank_stay_none():
    assert _map({}).battery_care_notification is None
    assert _note("   ") is None


def test_existing_value_is_not_overwritten():
    base = VehicleData(vin="X")
    base.battery_care_notification = "ALREADY"
    assert _note("BCAM_SCORE_VALUE_WARNING", base) == "ALREADY"


def test_the_siblings_still_map():
    d = _map({"battery_care_mode": {
        "bcam_notification": "BCAM_SCORE_VALUE_WARNING",
        "bcam_score": "7.5",
        "bcam_score_threshold": "9.0",
    }})
    assert d.battery_care_notification == "BCAM_SCORE_VALUE_WARNING"
    assert d.battery_care_score == 7.5
    assert d.battery_care_score_threshold == 9.0


def test_both_spellings_reclaimed_from_the_scout():
    for fields in (
        {"battery_care_mode": {"bcam_notification": "BCAM_SCORE_VALUE_REACHED"}},
        {"bcam_notification": "BCAM_SCORE_VALUE_REACHED"},
    ):
        syn: dict = {}
        flat = _walk_fields({"eu_data_act": fields}, None, syn)
        d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
        assert d.battery_care_notification == "BCAM_SCORE_VALUE_REACHED"
        leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
        assert "bcam_notification" not in leaves, f"still flooding: {fields}"


def test_the_siblings_are_reclaimed_too():
    """Writing the reclaim test for the new leaf exposed the same defect in the
    two leaves mapped next to it: their candidate lists named the bare leaf and a
    middle ``container.leaf`` spelling the walker never emits, so the
    ``eu_data_act.``-qualified twin was never collapsed and re-filed every poll.
    All three now name the prefixed spelling."""
    syn: dict = {}
    flat = _walk_fields(
        {"eu_data_act": {"battery_care_mode": {
            "bcam_notification": "BCAM_SCORE_VALUE_REACHED",
            "bcam_score": "7.5",
            "bcam_score_threshold": "9.0",
        }}},
        None, syn,
    )
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    assert d.battery_care_score == 7.5
    assert d.battery_care_score_threshold == 9.0
    assert d.battery_care_notification == "BCAM_SCORE_VALUE_REACHED"
    assert not (d.raw_unmapped_fields or {}), (
        f"nothing in this payload should still flood: {d.raw_unmapped_fields}"
    )


def test_the_still_held_sibling_remains_visible():
    # charge_bcam_threshold feeds battery_care_target_soc_pct; the OTHER member
    # the old comment listed stays Scout-visible, and this pins that the hold
    # list was narrowed deliberately rather than emptied by accident.
    syn: dict = {}
    flat = _walk_fields(
        {"eu_data_act": {"battery_care_mode": {"bcam_unknown_future": "1"}}},
        None, syn,
    )
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    assert "bcam_unknown_future" in leaves
