# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 (Arno-MA-73) — VW EU SoC oscillates because the flat Data event-log
carries a running car_captured_time forward and stamps timestamp-less records
with it as if it were their OWN per-point timestamp. VW REORDERS the same record
multiset between exports, so a stale SoC inherits whichever marker precedes it
this time and can out-rank the real value (57 <-> 81 flipping).

The fix distinguishes an INHERITED running-marker ts from an OWN sibling ts: a
value conflict where either side's ts is inherited is recorded CONTESTED, so
vehicle_cache.reconcile picks the candidate closest to the last persisted value
(order-independent) instead of trusting VW's array ordering. Own-timestamped
values still resolve by freshness and are NOT over-contested.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import _walk_fields

_CT1 = ("car_captured_time", "2026-08-08T10:00:00Z")
_CT2 = ("car_captured_time", "2026-08-08T11:00:00Z")
_S81 = ("battery_state_report.soc", "81")
_S57 = ("battery_state_report.soc", "57")


def _flat(pairs: list[tuple[str, str]]) -> dict:
    return {"data": [{"dataFieldName": n, "value": v} for n, v in pairs]}


def test_conflicting_inherited_soc_is_contested_in_any_order() -> None:
    # Whatever order VW ships the multiset in, the disagreement is recorded so
    # reconcile (not the array position) decides — this is the permutation
    # invariant that fixes the flip.
    for order in (
        [_CT1, _S81, _CT2, _S57],
        [_CT2, _S57, _CT1, _S81],
        [_CT1, _S57, _CT2, _S81],
    ):
        contested: dict = {}
        _walk_fields(_flat(order), {}, {}, contested)
        assert contested.get("battery_state_report.soc") == {"81", "57"}, order


def test_agreeing_inherited_soc_not_contested() -> None:
    contested: dict = {}
    _walk_fields(_flat([_CT1, _S81, _CT2, ("battery_state_report.soc", "81")]), {}, {}, contested)
    assert "battery_state_report.soc" not in contested


def test_own_per_point_timestamp_still_wins_and_is_not_contested() -> None:
    # A point that carries its OWN carCapturedTimestamp sibling is reliable —
    # freshness resolves it and it must NOT be dragged into the contested set,
    # or every honest freshness resolution would be second-guessed.
    payload = {"data": [
        {"dataFieldName": "battery_state_report.soc", "value": "81",
         "carCapturedTimestamp": "2026-08-08T10:00:00Z"},
        {"dataFieldName": "battery_state_report.soc", "value": "80",
         "carCapturedTimestamp": "2026-08-08T11:00:00Z"},
    ]}
    contested: dict = {}
    out = _walk_fields(payload, {}, {}, contested)
    assert out.get("battery_state_report.soc") == "80"  # newer own-ts wins
    assert "battery_state_report.soc" not in contested


def test_target_soc_newer_value_still_surfaced() -> None:
    # Regression: the v2.15.1 case (settings.target_soc 100 then 80) must still
    # surface 80 from the walk — the fix only ADDS the reconcile hook, it does
    # not change which value the walk picks.
    out = _walk_fields(_flat([
        _CT1, ("settings.target_soc", "100"),
        _CT2, ("settings.target_soc", "80"),
    ]))
    assert out.get("settings.target_soc") == "80"
