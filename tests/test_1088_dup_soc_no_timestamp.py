# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1088 — EU Data Act export contains the SAME dataFieldName twice with
different values and NO per-point timestamp (VW EU ID.7 / e-Golf): a stale SoC
was surfaced by array position. The parser now records the disagreement as a
contested field so vehicle_cache.reconcile can pick the candidate closest to the
last persisted value, instead of trusting append order.

The surfaced pick is UNCHANGED (last-append still wins within the ZIP), so #529
is not regressed; this only adds the reconciliation hook that was missing on the
no-real-timestamp tie (the real-timestamp tie already recorded it, #465/M1).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import _walk_fields


def _dup(v1: str, v2: str) -> dict:
    return {"data": [
        {"dataFieldName": "battery_state_report.soc", "value": v1},
        {"dataFieldName": "battery_state_report.soc", "value": v2},
    ]}


def test_disagreeing_dup_soc_no_ts_is_recorded_contested() -> None:
    contested: dict = {}
    fields = _walk_fields(_dup("50", "76"), {}, {}, contested)
    # pick unchanged — last-append still wins inside the ZIP (no #529 regression)
    assert fields["battery_state_report.soc"] == "76"
    # ...but the disagreement is now visible to reconcile
    assert contested.get("battery_state_report.soc") == {"50", "76"}


def test_agreeing_dup_soc_not_contested() -> None:
    contested: dict = {}
    _walk_fields(_dup("50", "50"), {}, {}, contested)
    assert "battery_state_report.soc" not in contested


def test_legacy_caller_without_contested_dict_is_safe() -> None:
    # a caller that passes no contested dict must not crash, and last still wins
    fields = _walk_fields(_dup("50", "76"))
    assert fields["battery_state_report.soc"] == "76"
