# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trip-statistics fetch is throttled to once per hour per VIN.

The CARIAD-BFF ``tripstatistics`` endpoint is dead (404) for the vast majority
of cars post-lockdown, yet ``get_status`` fired all three query types
(shortTerm/longTerm/cyclic) on EVERY poll — 3 wasted GETs + a failed parser
job each time. ``_fetch_trip_statistics`` now fetches at most once per hour per
VIN and reuses the cached raw responses in between, so the downstream parse
still runs every poll (no flicker) without re-hitting a dead endpoint.

Everything here is synthetic.
"""
from __future__ import annotations

import asyncio
from contextlib import nullcontext

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient


def _client() -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._parser_job = lambda name: nullcontext()  # type: ignore[method-assign]
    return c


def test_throttled_to_once_per_hour_same_vin() -> None:
    c = _client()
    calls: list[str] = []

    async def fake_get(url: str, params=None):
        calls.append(params.get("type"))
        return {}  # dead/empty endpoint

    c._get = fake_get  # type: ignore[method-assign]

    async def run():
        r1 = await c._fetch_trip_statistics("VIN1", "https://base")
        r2 = await c._fetch_trip_statistics("VIN1", "https://base")
        return r1, r2

    r1, r2 = asyncio.run(run())
    # first call fetches all three types; second reuses the cache → no new GETs
    assert calls == ["shortTerm", "longTerm", "cyclic"]
    assert r1 == r2 == ({}, {}, {})


def test_cache_returns_last_raw_and_is_per_vin() -> None:
    c = _client()
    responses = {"shortTerm": {"s": 1}, "longTerm": {"l": 2}, "cyclic": {"c": 3}}
    calls: list[str] = []

    async def fake_get(url: str, params=None):
        t = params.get("type")
        calls.append(t)
        return responses[t]

    c._get = fake_get  # type: ignore[method-assign]

    async def run():
        a = await c._fetch_trip_statistics("VINA", "https://b")
        a2 = await c._fetch_trip_statistics("VINA", "https://b")  # cached
        b = await c._fetch_trip_statistics("VINB", "https://b")   # different vin
        return a, a2, b

    a, a2, b = asyncio.run(run())
    assert a == ({"s": 1}, {"l": 2}, {"c": 3})
    assert a2 == a                      # cache hit → same data, no flicker
    assert b == ({"s": 1}, {"l": 2}, {"c": 3})
    # VINA fetched 3 + VINB fetched 3; VINA's second call added nothing
    assert len(calls) == 6


def test_fetch_failure_yields_empties_and_does_not_rehammer() -> None:
    c = _client()
    n = {"count": 0}

    async def boom(url: str, params=None):
        n["count"] += 1
        raise RuntimeError("404 dead endpoint")

    c._get = boom  # type: ignore[method-assign]

    async def run():
        r1 = await c._fetch_trip_statistics("V", "https://b")
        r2 = await c._fetch_trip_statistics("V", "https://b")
        return r1, r2

    r1, r2 = asyncio.run(run())
    assert r1 == ({}, {}, {})
    assert r2 == ({}, {}, {})
    # shortTerm raised → outer except → 1 GET; second call is a cache hit → still 1
    assert n["count"] == 1
