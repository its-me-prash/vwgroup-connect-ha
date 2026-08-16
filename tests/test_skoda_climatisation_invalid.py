# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda: the AC "INVALID" no-state marker reads as unavailable, not "INVALID".

Marco Schmidt's gasoline Octavia (HA Tipps und Tricks Facebook group) returned
air-conditioning state "INVALID"; the climate-state sensor showed the raw
"INVALID" string. It now maps to None (unavailable), while a real state passes
through unchanged. climatisation_active was already False for INVALID.
"""
from __future__ import annotations

import asyncio
from typing import Any

from custom_components.vag_connect.cariad.api.skoda import SkodaClient, _BASE

VIN = "TMBJR0NX4SY000001"


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

    async def get(self, url: str, **_kw: Any) -> Any:
        for frag, r in self.routes.items():
            if frag in url:
                return r
        return {}


def _run(ac_state: str):
    c = _client()
    rec = _Rec({
        "/air-conditioning/": {
            "state": ac_state,
            "targetTemperature": {"temperatureValue": 28.5, "unitInCar": "CELSIUS"},
        },
        "/driving-range": {"carType": "gasoline",
                           "primaryEngineRange": {"remainingRangeInKm": 640}},
    })
    c._get = rec.get  # type: ignore[assignment]
    return asyncio.run(c.get_status(VIN))


def test_invalid_state_suppressed_to_none() -> None:
    d = _run("INVALID")
    assert d.climatisation_state is None
    assert d.climatisation_active is False
    assert d.target_temperature == 28.5   # other AC fields still parse


def test_real_state_passes_through() -> None:
    d = _run("ON")
    assert d.climatisation_state == "ON"
    assert d.climatisation_active is True
