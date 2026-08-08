# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda pay-to-park sessions — READ-ONLY (8.15.0 APK).

Same shape as fueling: surface the current/last paid-parking session (location,
cost, start/stop) from GET api/v1/parking/sessions/mine. The POST that
starts/pays a session is a prohibited financial transaction — no client write
method exists (pinned by a test).
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.coordinator import _parse_parking

_ACTIVE = {"id": "p2", "location": {"name": "Parkhaus Bahnhof"},
           "priceAmount": 3.5, "priceCurrency": "CHF",
           "startTime": "2026-08-08T09:00:00Z", "stopTime": None}
_DONE = {"id": "p1", "location": {"name": "Altstadt"},
         "priceAmount": 6.0, "priceCurrency": "CHF",
         "startTime": "2026-08-01T12:00:00Z", "stopTime": "2026-08-01T14:00:00Z"}


def test_parse_prefers_active_session() -> None:
    out = _parse_parking([_DONE, _ACTIVE])
    assert out["parking_session_active"] is True
    assert out["parking_location"] == "Parkhaus Bahnhof"
    assert out["parking_cost"] == 3.5
    assert out["parking_currency"] == "CHF"
    assert out["parking_started_at"] == "2026-08-08T09:00:00Z"
    assert "parking_ended_at" not in out  # active → no stop


def test_parse_falls_back_to_newest_completed() -> None:
    older = dict(_DONE, id="p0", startTime="2026-07-01T00:00:00Z")
    out = _parse_parking([older, _DONE])
    assert out["parking_session_active"] is False
    assert out["parking_started_at"] == "2026-08-01T12:00:00Z"  # newest
    assert out["parking_ended_at"] == "2026-08-01T14:00:00Z"


def test_parse_accepts_single_object() -> None:
    # 8.15.0 ParkingApi.getParkingSession returns a SINGLE ParkingSessionDto
    # (a bare dict), NOT a list — this is the real production shape.
    out = _parse_parking(_ACTIVE)
    assert out["parking_session_active"] is True
    assert out["parking_location"] == "Parkhaus Bahnhof"
    assert out["parking_cost"] == 3.5
    # a completed single session still parses (and reports its stop time)
    done = _parse_parking(_DONE)
    assert done["parking_session_active"] is False
    assert done["parking_ended_at"] == "2026-08-01T14:00:00Z"


def test_parse_accepts_wrapped_and_empty() -> None:
    assert _parse_parking({"sessions": [_ACTIVE]})["parking_location"] == "Parkhaus Bahnhof"
    assert _parse_parking([]) == {}
    assert _parse_parking({}) == {}
    assert _parse_parking(None) == {}


def test_client_read_hits_mine_route() -> None:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    # real endpoint returns a single ParkingSessionDto object, not a list
    c._get = AsyncMock(return_value=_ACTIVE)  # type: ignore[method-assign]
    out = asyncio.run(c.get_my_parking())
    assert c._get.call_args.args[0].endswith("/api/v1/parking/sessions/mine")
    assert out["id"] == "p2"


def test_client_read_empty_on_error() -> None:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._get = AsyncMock(side_effect=RuntimeError("403"))  # type: ignore[method-assign]
    assert asyncio.run(c.get_my_parking()) == {}


def test_no_parking_write_method_exists() -> None:
    # House rule: no method that starts/pays a parking session (financial).
    for name, _ in inspect.getmembers(SkodaClient, predicate=inspect.isfunction):
        low = name.lower()
        if "parking" in low:
            assert "get" in low, f"SkodaClient.{name} looks like a parking write"
