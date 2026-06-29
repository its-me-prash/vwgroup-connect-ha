# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b13 (#465 RaAdNe) — duplicate same-name data-point disambiguation.

VW's portal returns several data points with the SAME logical name (e.g. four
``target_soc`` candidates, two ``soc`` values). We must pick by genuine
freshness, never by array order, and a field nested inside an array (e.g. a
charge profile) must not clobber the active top-level value.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import _walk_fields


def test_duplicate_soc_no_real_ts_keeps_last_not_first() -> None:
    # PREMISE CHANGED in #529 (v2.15.4): this test previously assumed the FIRST
    # duplicate was the correct one when neither carried a real per-point ts.
    # The #529 root-cause trace (S5/S6) disproved that: the portal ZIP is an
    # append-ordered event-log, so on a no-real-ts tie the LATER duplicate is
    # the newer sample and must win — an append-ordered log makes the later
    # duplicate the newer sample. The original "first 90 is live, later 80 is
    # stale" framing was coincidental ordering, not a portal guarantee — when
    # the freshness actually matters the data carries genuine timestamps (see
    # test_duplicate_soc_distinct_real_ts_picks_freshest below), and those still
    # win regardless of array position.
    log = {"data": [
        {"dataFieldName": "soc", "value": "90"},   # earlier append
        {"dataFieldName": "soc", "value": "80"},   # later append = newer sample
    ]}
    assert _walk_fields(log)["soc"] == "80"


def test_duplicate_soc_distinct_real_ts_picks_freshest() -> None:
    log = {"data": [
        {"dataFieldName": "soc", "value": "80", "capturedAt": "2026-06-20T08:00:00Z"},
        {"dataFieldName": "soc", "value": "90", "capturedAt": "2026-06-24T08:00:00Z"},
    ]}
    assert _walk_fields(log)["soc"] == "90"  # freshest genuine timestamp wins


def test_real_ts_beats_unknown_even_when_later_in_array() -> None:
    # a genuine per-point ts must beat a no-ts entry regardless of order
    forward = {"data": [
        {"dataFieldName": "soc", "value": "70"},                                  # no ts, first
        {"dataFieldName": "soc", "value": "80", "capturedAt": "2026-06-24T08:00:00Z"},
    ]}
    assert _walk_fields(forward)["soc"] == "80"
    backward = {"data": [
        {"dataFieldName": "soc", "value": "80", "capturedAt": "2026-06-24T08:00:00Z"},
        {"dataFieldName": "soc", "value": "70"},                                  # no ts, later
    ]}
    assert _walk_fields(backward)["soc"] == "80"


def test_array_nested_field_does_not_clobber_top_level() -> None:
    # a target_soc inside chargingProfiles[] must NOT collapse onto the active
    # top-level target_soc — that was how the wrong profile value won.
    log = {
        "target_soc": "100",  # the active value (matches the app)
        "chargingProfiles": [
            {"target_soc": "80"},
            {"target_soc": "70"},
        ],
    }
    out = _walk_fields(log)
    assert out["target_soc"] == "100"                  # top-level preserved
    assert out.get("chargingProfiles.target_soc") in ("80", "70")  # still discoverable, qualified
