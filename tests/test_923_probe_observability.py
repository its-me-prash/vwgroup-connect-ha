# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 / #1157 — probe outcomes are visible in diagnostics.

The experimental vw.de probes (parkingposition GPS, battery SoH) run fail-soft:
a 403/404/412 refusal or a degraded empty 200 returns None and never raises. That
made them INVISIBLE — the GPS cohort's diagnostics carried no trace of why a probe
yielded nothing, so we could not tell "the proxy refused (404)" from "the probe
never fired" from "an empty 200". These tests pin the new ``probe_outcomes`` trail:
``_get_json`` records the status, the callers refine a degraded 200 to a
"no-value" label, and the supplementary read merges the connector's outcomes up to
the client so they reach the diagnostics export — even when the read fail-softs.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)

VIN = "WVWZZZAUZ1234567"


class _Resp:
    def __init__(self, status: int, json_data: Any = None) -> None:
        self.status = status
        self._json = json_data

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def json(self, content_type: Any = None) -> Any:
        return self._json

    async def text(self, errors: str | None = None) -> str:
        return ""


class _Session:
    def __init__(self, status: int, json_data: Any = None) -> None:
        self._status = status
        self._json = json_data

    def get(self, url: str, **_kw: Any) -> _Resp:
        return _Resp(self._status, self._json)


def _conn(status: int, json_data: Any = None) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c.probe_outcomes = {}
    c.last_raw_responses = {}
    c._headers = lambda d: d  # type: ignore[assignment]
    c._session = _Session(status, json_data)  # type: ignore[assignment]
    c._ensure_backend = AsyncMock(return_value=None)  # type: ignore[assignment]
    c._gdc = lambda vin: "myvw-wcar-prod"  # type: ignore[assignment]
    c._soh_subpath = None
    return c


# ── _get_json records the status of a probe ────────────────────────────────────

def test_get_json_records_404_for_a_refused_soft_probe() -> None:
    c = _conn(404)
    out = asyncio.run(c._get_json(
        "https://www.volkswagen.de/x/vehicles/V/parkingposition",
        accept="*/*", soft=True, optional=True, record_as="parkingposition",
    ))
    assert out is None
    assert c.probe_outcomes["parkingposition"] == "404"


def test_get_json_records_403_on_the_optional_auth_branch() -> None:
    c = _conn(403)
    out = asyncio.run(c._get_json(
        "https://x", accept="*/*", optional=True, record_as="soh:selectivestatus",
    ))
    assert out is None
    assert c.probe_outcomes["soh:selectivestatus"] == "403"


def test_get_json_records_412_precondition() -> None:
    c = _conn(412)
    out = asyncio.run(c._get_json("https://x", optional=True, record_as="parkingposition"))
    assert out is None
    assert "412" in c.probe_outcomes["parkingposition"]


def test_get_json_records_200_on_success() -> None:
    c = _conn(200, {"data": {"lat": 1.0, "lon": 2.0}})
    body = asyncio.run(c._get_json("https://x", record_as="parkingposition"))
    assert body == {"data": {"lat": 1.0, "lon": 2.0}}
    assert c.probe_outcomes["parkingposition"] == "200"


def test_no_record_without_record_as() -> None:
    c = _conn(404)
    asyncio.run(c._get_json("https://x", soft=True, optional=True))
    assert c.probe_outcomes == {}  # nothing recorded when not asked


# ── callers refine a degraded 200 to a "no-value" label ────────────────────────

def test_parking_refines_a_degraded_200_to_no_coords() -> None:
    c = _conn(200, {"data": {}})  # 200 but no coordinates
    res = asyncio.run(c.get_parking_position(VIN))
    assert res is None
    assert c.probe_outcomes["parkingposition"] == "200 no-coords"


def test_soh_refines_a_degraded_200_to_no_value() -> None:
    c = _conn(200, {"nothing": "useful"})  # 200 but no ubeIndicator_pct
    res = asyncio.run(c.get_battery_health(VIN))
    assert res is None
    # the first candidate is selectivestatus
    assert c.probe_outcomes["soh:selectivestatus"] == "200 no-value"


# ── the supplementary read merges outcomes up to the client (surfaces in diag) ──

def test_read_authproxy_merges_outcomes_even_when_read_fails() -> None:
    client = CariadBaseClient.__new__(CariadBaseClient)
    client.probe_outcomes = {}

    connector = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    connector.probe_outcomes = {"parkingposition": "404", "soh:batteryhealthstate": "404"}
    # the read itself raises → fail-soft to None, but outcomes must still surface
    connector.get_vehicle_data = AsyncMock(side_effect=RuntimeError("boom"))

    res = asyncio.run(client._read_authproxy(connector, VIN))
    assert res is None
    assert client.probe_outcomes["parkingposition"] == "404"
    assert client.probe_outcomes["soh:batteryhealthstate"] == "404"
