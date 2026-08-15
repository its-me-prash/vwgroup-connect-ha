# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda diesel: stop 403-hammering /charging on a car with no HV battery.

A combustion-only Škoda (diesel) has no charging capability, so the /charging
endpoint 403s on every poll forever. Once a prior poll's driving-range told us
carType is pure-combustion, get_status skips that read. EV/PHEV (electric/hybrid)
are never skipped. Reported by a diesel Octavia owner via the HA Tipps und Tricks
Facebook group.
"""
from __future__ import annotations

import asyncio
from typing import Any

from custom_components.vag_connect.cariad.api.base import APIError
from custom_components.vag_connect.cariad.api.skoda import SkodaClient, _BASE

VIN = "TMBXXXXXXXXXXXXXX"


def _client() -> SkodaClient:
    c = SkodaClient.__new__(SkodaClient)
    c.parser_stats = {}
    c._powertrain = {}
    c._eu_portal = None
    c._tokens = None
    c.last_raw_responses = {}

    async def _nostats(_v: str) -> dict:
        return {}

    c.get_charging_statistics = _nostats  # type: ignore[assignment]
    return c


class _Rec:
    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls: list[str] = []

    async def get(self, url: str, **_kw: Any) -> Any:
        self.calls.append(url)
        for frag, r in self.routes.items():
            if frag in url:
                if isinstance(r, Exception):
                    raise r
                return r
        return {}


def test_diesel_skips_charging_from_the_second_poll() -> None:
    c = _client()
    rec = _Rec({
        "/driving-range": {"carType": "diesel",
                           "combustionRange": {"distanceInKm": 700}},
        "/charging/": APIError(403, f"{_BASE}/api/v1/charging/{VIN}", "403"),
    })
    c._get = rec.get  # type: ignore[assignment]

    asyncio.run(c.get_status(VIN))                     # poll 1: attempted → 403
    assert f"{_BASE}/api/v1/charging/{VIN}" in rec.calls
    assert c._powertrain[VIN] == "diesel"
    assert c.parser_stats["charging"]["fail"] == 1

    rec.calls.clear()
    asyncio.run(c.get_status(VIN))                     # poll 2: SKIPPED
    assert f"{_BASE}/api/v1/charging/{VIN}" not in rec.calls
    assert c.parser_stats["charging"]["fail"] == 1     # frozen, not 2


def test_ev_and_phev_never_skip_charging() -> None:
    for ctype in ("hybrid", "electric"):
        c = _client()
        rec = _Rec({
            "/driving-range": {"carType": ctype,
                               "combustionRange": {"distanceInKm": 60}},
            "/charging/": {"status": {
                "battery": {"stateOfChargeInPercent": 55}}},
        })
        c._get = rec.get  # type: ignore[assignment]
        asyncio.run(c.get_status(VIN))
        rec.calls.clear()
        asyncio.run(c.get_status(VIN))                 # poll 2 STILL calls it
        assert f"{_BASE}/api/v1/charging/{VIN}" in rec.calls, ctype
        assert c._powertrain[VIN] in ("hybrid", "electric")
