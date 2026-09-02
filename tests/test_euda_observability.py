# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage-0 EU Data Act observability — the connector's own lifecycle bookkeeping.

The portal connector records WHEN its data request was created, WHEN a real
snapshot last arrived, and WHEN / HOW OFTEN a poll came back empty — plus it now
splits a genuine VW-side outage (5xx/429) from a normal "not delivered yet" wait
(404/410). The coordinator surfaces these as diagnostic sensors (#465, #1273).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth import _eu_data_act as m


def _conn() -> m.EUDataActConnector:
    """A bare connector with only the observability attributes initialised."""
    c = m.EUDataActConnector.__new__(m.EUDataActConnector)
    c.last_no_data_reason = ""
    c.last_no_data_at = None
    c.no_data_count = 0
    c.last_snapshot_at = None
    return c


def test_note_no_data_sets_reason_timestamp_and_increments():
    c = _conn()
    c._note_no_data("no_request")
    assert c.last_no_data_reason == "no_request"
    assert isinstance(c.last_no_data_at, str) and c.last_no_data_at
    assert c.no_data_count == 1
    c._note_no_data("portal_error")
    assert c.last_no_data_reason == "portal_error"
    assert c.no_data_count == 2


def test_note_data_ok_clears_reason_and_stamps_snapshot_without_bumping_count():
    c = _conn()
    c._note_no_data("empty")
    assert c.no_data_count == 1
    c._note_data_ok()
    assert c.last_no_data_reason == ""
    assert isinstance(c.last_snapshot_at, str) and c.last_snapshot_at
    # a good poll must NOT count as a no-data poll
    assert c.no_data_count == 1


def test_request_start_date_from_list_descriptor():
    meta = [
        {"Identifier": "AAA", "StartDate": "2026-09-01T10:00:00Z", "Frequency": "15mins"},
        {"Identifier": "BBB", "StartDate": "2026-09-02T20:30:25Z", "Frequency": "15mins"},
    ]
    assert m._request_start_date(meta, "BBB") == "2026-09-02T20:30:25Z"
    # an identifier that isn't present yields None (no phantom timestamp)
    assert m._request_start_date(meta, "ZZZ") is None


def test_request_start_date_from_bare_dict_all_dialect():
    meta = {"Identifier": "CCC", "StartDate": "2026-09-02T20:34:51Z"}
    assert m._request_start_date(meta, "CCC") == "2026-09-02T20:34:51Z"


def test_request_start_date_from_wrapped_items():
    meta = {"items": [{"Identifier": "DDD", "StartDate": "2026-09-03T00:00:00Z"}]}
    assert m._request_start_date(meta, "DDD") == "2026-09-03T00:00:00Z"


def test_request_start_date_ignores_non_string_startdate():
    meta = [{"Identifier": "EEE", "StartDate": 12345}]
    assert m._request_start_date(meta, "EEE") is None
    # no identifier at all → None, never a crash
    assert m._request_start_date([], "EEE") is None
    assert m._request_start_date(None, "EEE") is None


def test_portal_outage_statuses_split_error_from_not_ready():
    # 5xx / 429 are a VW-side portal fault → portal_error; 400/404/410 mean the
    # request just isn't provisioned / no delivery yet → delivery_not_ready.
    for outage in (429, 500, 502, 503, 504):
        assert outage in m._PORTAL_OUTAGE_STATUSES
    for not_ready in (400, 404, 410):
        assert not_ready not in m._PORTAL_OUTAGE_STATUSES
