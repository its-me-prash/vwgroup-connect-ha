# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1805 — the CARIAD-BFF ``tripstatistics`` endpoint is simply ABSENT (404) on
most post-lockdown cars and whole model lines (the RS e-tron GT reporter's case).
A 404 means "this car has no trip cluster", not that the parser broke, so it must
not increment ``parser_stats["trip_statistics"].fail`` — the telemetry that flags
genuinely broken parses and shows up in the diagnostics export. A real server
error (5xx) or anything else still counts.

Everything here is synthetic.
"""
from __future__ import annotations

import asyncio

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError


def _client() -> VWEUClient:
    # __new__ skips HA setup; set parser_stats so the REAL _parser_job records
    # into it (its __new__ fallback would otherwise make the counters no-ops).
    c = VWEUClient.__new__(VWEUClient)
    c.parser_stats = {}
    return c


def test_a_404_endpoint_is_not_counted_as_a_parser_failure() -> None:
    c = _client()

    async def get_404(url, params=None):
        raise APIError(404, url, "not found")

    c._get = get_404  # type: ignore[method-assign]
    r = asyncio.run(c._fetch_trip_statistics("V", "https://b"))
    assert r == ({}, {}, {})
    ts = c.parser_stats.get("trip_statistics", {})
    assert ts.get("fail", 0) == 0  # 404 = endpoint absent, not a failure


def test_a_real_server_error_still_counts_as_a_failure() -> None:
    c = _client()

    async def get_500(url, params=None):
        raise APIError(500, url, "boom")

    c._get = get_500  # type: ignore[method-assign]
    r = asyncio.run(c._fetch_trip_statistics("V", "https://b"))
    assert r == ({}, {}, {})
    ts = c.parser_stats.get("trip_statistics", {})
    assert ts.get("fail", 0) == 1  # a genuine failure is still flagged
