# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.4 — EU Data Act portal data-point overreport fix.

In the REALISTIC portal shape (Variant A), container objects hold *data-point*
nodes ``{dataFieldName, value}`` rather than plain scalars. Before the fix the
walker emitted ONLY the bare leaf key for such a node, never a container-qualified
path, so:

  * the next-charging-timer family (estimated_start/finish_time, target_reach-
    ability) tried ONLY dotted ``profile_state_report.next_charging_timer_inform-
    ation.*`` forms → never matched the bare leaves the walker actually emitted →
    UNMAPPED, chronic raw_unmapped re-reporters;
  * slope ascent/descent share the bare leaf ``physical_value``; latest-wins
    collapsed them to ONE value, so ascent vs descent could not be recovered.

The fix (see ``_eu_data_act._walk_fields`` / ``first``):
  (a) the walker now emits the CONTAINER-QUALIFIED dotted path IN ADDITION to the
      bare leaf for a nested data-point node — so dotted first() forms match and
      ascent/descent disambiguate by their distinct container path;
  (b) ``first()`` synonym-collapses: once a spelling is consumed, every other
      field whose LAST dotted segment + value match it is marked used too, so the
      bare/dotted/qualified twins stop re-surfacing in raw_unmapped (and the
      shared ``physical_value`` only collapses against the sibling it equals,
      keeping ascent ≠ descent);
  (c) safe bare-leaf aliases added to the timer first() lists (unique leaves).

This test encodes Variant A and asserts the timer + slope families POPULATE with
the correct DISTINCT values, and that raw_unmapped shrinks to ONLY the intended
(no-suppress) metadata — no chronic data re-reporters remain.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _variant_a_payload() -> dict:
    """The realistic data-point shape: containers hold {dataFieldName,value} nodes."""
    return {
        "vin": "WVWZZZAUZMW000000",
        "user_id": "user-abc-123",
        "Data": {"key": "dataset-key-xyz"},
        "report_type": "REPORT_TYPE_CONSUMPTION_VALUES",
        "message_id": "RPT_28",
        "timestamp": "2026-06-22T10:00:00Z",
        "car_captured_time": "2026-06-22T09:58:00Z",
        "update_reason": "UPDATE_REASON_CHARGING",
        "state": "VALID",
        "dataPoints": [
            {"dataFieldName": "car_captured_time", "value": "2026-06-22T09:58:00Z"},
            {"dataFieldName": "battery_level_HV", "value": 80.0, "state": "VALID"},
            {"dataFieldName": "outdoor_temperature", "value": 37.5},
            {"dataFieldName": "open", "value": True},
            {"dataFieldName": "value", "value": 388},
            {"dataFieldName": "vin", "value": "WVWZZZAUZMW000000"},
            {"dataFieldName": "user_id", "value": "user-abc-123"},
            {"dataFieldName": "message_id", "value": "RPT_28"},
            {"dataFieldName": "state", "value": "VALID"},
            {"dataFieldName": "report_type", "value": "REPORT_TYPE_CONSUMPTION_VALUES"},
            {"dataFieldName": "update_reason", "value": "UPDATE_REASON_CHARGING"},
            {"dataFieldName": "timestamp", "value": "2026-06-22T10:00:00Z"},
        ],
        "charging_state_report": {
            "charging_scenario": {
                "dataFieldName": "charging_scenario",
                "value": "CHARGING_SCENARIO_IMMEDIATELY_CHARGING_FINISHED",
            },
            "immediate_action_state": {
                "dataFieldName": "immediate_action_state",
                "value": "IMMEDIATE_ACTION_STATE_CHARGE_MODE_SELECTION",
            },
            "profile_charge_reason": {
                "dataFieldName": "profile_charge_reason",
                "value": "PROFILE_CHARGE_REASON_LOW_COST",
            },
        },
        "profile_state_report": {
            "car_captured_time": {
                "dataFieldName": "car_captured_time",
                "value": "2026-06-22T09:57:00Z",
            },
            "instrument_cluster_time": {
                "dataFieldName": "instrument_cluster_time",
                "value": "2026-06-22T09:57:30Z",
            },
            "next_charging_timer_information": {
                "estimated_finish_time": {
                    "dataFieldName": "estimated_finish_time",
                    "value": "2026-06-22T12:00:00Z",
                },
                "estimated_start_time": {
                    "dataFieldName": "estimated_start_time",
                    "value": "2026-06-22T11:00:00Z",
                },
                "target_reachability": {
                    "dataFieldName": "target_reachability",
                    "value": "TARGET_REACHABILITY_REACHABLE",
                },
            },
        },
        "slope_consumption_values": {
            "ascent_slope_consumption": {
                "physical_value": {"dataFieldName": "physical_value", "value": 12.3},
                "value_type": {
                    "dataFieldName": "value_type",
                    "value": "VALUE_TYPE_PHYSICAL",
                },
            },
            "descent_slope_consumption": {
                "physical_value": {"dataFieldName": "physical_value", "value": -4.5},
                "value_type": {
                    "dataFieldName": "value_type",
                    "value": "VALUE_TYPE_PHYSICAL",
                },
            },
        },
    }


def _map() -> VehicleData:
    ts_out: dict[str, float] = {}
    syn_out: dict[str, set[str]] = {}
    flat = _walk_fields(_variant_a_payload(), ts_out, syn_out)
    d = VehicleData(vin="WVWZZZAUZMW000000")
    map_dataset_to_vehicle_data(flat, d, ts_out, syn_out)
    return d


# ── timer family populates from the bare data-point leaves ──────────────────────
def test_next_charge_timer_start_finish_populate() -> None:
    d = _map()
    assert d.next_charge_timer_start_at == "2026-06-22T11:00:00Z"
    assert d.next_charge_timer_finish_at == "2026-06-22T12:00:00Z"


def test_next_charge_target_reachability_populates() -> None:
    d = _map()
    assert d.next_charge_target_reachability == "REACHABLE"


# ── slope disambiguates ascent vs descent despite the shared bare leaf ──────────
def test_slope_ascent_descent_distinct() -> None:
    d = _map()
    assert d.ascent_slope_consumption == 12.3
    assert d.descent_slope_consumption == -4.5
    # the shared bare ``physical_value`` must NOT collapse them to one value
    assert d.ascent_slope_consumption != d.descent_slope_consumption


# ── raw_unmapped no longer carries the chronic data re-reporters ────────────────
def test_overreporters_gone_from_raw_unmapped() -> None:
    raw = _map().raw_unmapped_fields
    for gone in (
        "estimated_start_time",
        "estimated_finish_time",
        "target_reachability",
        "physical_value",
        "value_type",
    ):
        assert gone not in raw, f"{gone} still re-surfaces in raw_unmapped"
    # the (a) qualified paths must NOT become new orphans either
    for qualified in (
        "profile_state_report.next_charging_timer_information.estimated_start_time",
        "slope_consumption_values.ascent_slope_consumption.physical_value",
        "slope_consumption_values.descent_slope_consumption.physical_value",
        "slope_consumption_values.ascent_slope_consumption.value_type",
        "charging_state_report.charging_scenario",
    ):
        assert qualified not in raw, f"{qualified} is a new orphan re-reporter"


def test_raw_unmapped_is_only_intended_metadata() -> None:
    """v2.18.1 — envelope/identity/UUID metadata (vin / user_id / state /
    timestamp / value / message_id / Data.key / …) is now the carve-out from
    no-suppression and is dropped from the raw/Scout surface. What remains is only
    the real, still-unmapped telemetry the Scout is meant to surface for future
    mapping."""
    raw = _map().raw_unmapped_fields
    intended = {
        "battery_level_HV",
        "open",
    }
    assert set(raw) == intended, f"unexpected raw_unmapped delta: {set(raw) ^ intended}"


# ── no-suppression: leaf-name collision with EQUAL value must NOT cross-collapse ──
def test_leaf_collision_equal_value_not_suppressed() -> None:
    """The old leaf+value heuristic wrongly removed an UNRELATED field that merely
    shared a leaf name AND value with a consumed one (e.g. consumed
    ``battery_state_report.soc=55`` + unrelated ``front_left_tyre.soc=55`` →
    front_left_tyre.soc vanished from raw_unmapped). The explicit-synonym map
    fixes this: the two are NOT synonyms (different physical nodes), so the
    unrelated field STAYS Scout-visible."""
    flat = {
        "battery_state_report.soc": "55",
        "front_left_tyre.soc": "55",  # distinct datum, same leaf + same value
    }
    # No synonym map entry links these two — they came from different nodes.
    d = VehicleData(vin="X")
    map_dataset_to_vehicle_data(flat, d, None, {})
    raw = d.raw_unmapped_fields
    assert d.battery_soc == 55  # the consumed one mapped fine
    assert "battery_state_report.soc" not in raw  # consumed → reclaimed
    assert "front_left_tyre.soc" in raw, (
        "no-suppression VIOLATION: unrelated front_left_tyre.soc was cross-collapsed"
    )


def test_slope_values_distinct_after_collapse() -> None:
    """ascent(12.3) and descent(-4.5) must remain distinct even though both emit
    the shared bare leaf ``physical_value`` — the synonym map keeps each tied to
    its own container-qualified twin."""
    d = _map()
    assert d.ascent_slope_consumption == 12.3
    assert d.descent_slope_consumption == -4.5
    assert d.ascent_slope_consumption != d.descent_slope_consumption
