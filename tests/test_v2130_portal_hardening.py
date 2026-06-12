# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.13.0 Block D (P1) — EU Data Act portal data hardening.

- _walk_fields is LATEST-WINS by timestamp (fixes the jumping SoC/odometer
  the whole portal ecosystem hit — the portal ships an unordered event-log).
- _unzip_json returns {} on empty/no-content/corrupt ZIPs instead of raising
  AuthenticationError (which used to burn the session on a pointless re-login).
"""

from __future__ import annotations

import io
import json
import zipfile

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _parse_ts,
    _unzip_json,
    _walk_fields,
)


def test_walk_fields_latest_wins_by_timestamp() -> None:
    log = {
        "data": [
            {"dataFieldName": "soc", "value": "40", "capturedAt": "2026-06-10T08:00:00Z"},
            {"dataFieldName": "soc", "value": "82", "capturedAt": "2026-06-12T08:00:00Z"},
            {"dataFieldName": "soc", "value": "55", "capturedAt": 1781000000},
        ]
    }
    assert _walk_fields(log)["soc"] == "82"  # newest timestamp wins


def test_walk_fields_no_timestamp_falls_back_to_last() -> None:
    log = {"data": [
        {"dataFieldName": "x", "value": "1"},
        {"dataFieldName": "x", "value": "9"},
    ]}
    assert _walk_fields(log)["x"] == "9"  # last-in-array, not first


def test_walk_fields_datapoint_shape_unchanged() -> None:
    out = _walk_fields({"data": [{"dataFieldName": "mileage.value", "value": "18842"}]})
    assert out["mileage.value"] == "18842"


def test_walk_fields_flat_egolf_unchanged() -> None:
    out = _walk_fields({"state_of_charge": "60", "mileage": "99000"})
    assert out["state_of_charge"] == "60"
    assert out["mileage"] == "99000"


def test_parse_ts_handles_formats() -> None:
    assert _parse_ts(1781000000) == 1781000000.0  # epoch s
    assert _parse_ts(1781000000000) == 1781000000.0  # epoch ms heuristic
    assert _parse_ts("2026-06-12T08:00:00Z") is not None  # ISO
    assert _parse_ts("not-a-date") is None
    assert _parse_ts(None) is None


def test_unzip_json_valid() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("d.json", json.dumps({"a": 1}))
    assert _unzip_json(buf.getvalue(), "d.zip") == {"a": 1}


def test_unzip_json_graceful_on_bad_or_empty() -> None:
    assert _unzip_json(b"garbage-not-a-zip", "x.zip") == {}  # corrupt → {}
    assert _unzip_json(b"anything", "veh_no_content_found.zip") == {}  # no-content
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w"):
        pass
    assert _unzip_json(empty.getvalue(), "e.zip") == {}  # zip with no JSON member
