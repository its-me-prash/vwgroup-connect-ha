# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1973 — the Škoda setup read loads the garage document before get_status.

The first status read of a setup ran before any capability list existed, so the
battery-health capability skip could not apply and a petrol car paid a full 5xx
retry ladder on that endpoint at every start. ``_setup_initial_reads`` now
fetches the garage document first (Škoda only); the later fetches in the
background finish and in ``_enrich`` hit the 24 h cache, so no request is added.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN = "TMBJJ7NX1M0000009"
_GARAGE = f"/api/v2/garage/vehicles/{VIN}"
_HEALTH = f"/api/v1/vehicle-information/{VIN}/battery-health"


class _Backend:
    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    async def get(self, url: str, **_kw: Any) -> Any:
        self.calls.append(url)
        for frag, result in self.routes.items():
            if frag in url:
                if isinstance(result, Exception):
                    raise result
                return result
        return {}

    def count(self, frag: str) -> int:
        return sum(1 for u in self.calls if frag in u)


async def _no_stats(_vin: str) -> dict[str, Any]:
    return {}


def _garage(cap_ids: list[str]) -> dict[str, Any]:
    return {"capabilities": {"capabilities": [
        {"id": c, "statuses": []} for c in cap_ids
    ]}}


def _coord(brand: str, routes: dict[str, Any]) -> tuple[VagConnectCoordinator, _Backend]:
    client = SkodaClient(MagicMock(), "u@t.de", "pw")
    backend = _Backend(routes)
    client._get = backend.get  # type: ignore[method-assign]
    client.get_charging_statistics = _no_stats  # type: ignore[method-assign]
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": brand}
    coord._cariad_client = client
    client._tokens = SimpleNamespace(strategy="")
    coord._vehicles_lock = threading.Lock()
    coord.vehicle_capabilities = {}
    coord._capabilities_fetched_at = {}
    coord._push_official_mode = MagicMock()  # type: ignore[method-assign]

    async def _merge(_vin: str, result: Any) -> Any:
        return result

    async def _enrich(data: dict[str, Any]) -> dict[str, Any]:
        # same lazy Škoda fetch as the real _enrich
        await coord.refresh_capabilities(data["vin"])
        return data

    coord._merge_supplementary = _merge  # type: ignore[method-assign]
    coord._enrich = _enrich  # type: ignore[method-assign]
    return coord, backend


async def _setup_then_follow_ups(coord: VagConnectCoordinator) -> None:
    await coord._setup_initial_reads([VIN])
    await coord.refresh_capabilities(VIN)  # _bg_finish
    await coord.refresh_capabilities(VIN)  # next _enrich


def test_petrol_skoda_skips_battery_health_on_the_setup_read() -> None:
    coord, backend = _coord("skoda", {_GARAGE: _garage(["CHARGING"])})
    asyncio.run(coord._setup_initial_reads([VIN]))
    assert backend.count(_HEALTH) == 0


def test_capability_present_still_reads_battery_health_at_setup() -> None:
    coord, backend = _coord("skoda", {
        _GARAGE: _garage(["BATTERY_HEALTH_STATE"]),
        _HEALTH: {"status": "HEALTHY", "remainingCapacity": 97},
    })
    asyncio.run(coord._setup_initial_reads([VIN]))
    assert backend.count(_HEALTH) == 1


def test_failed_garage_fetch_still_tries_battery_health_once() -> None:
    coord, backend = _coord("skoda", {
        _GARAGE: RuntimeError("boom"),
        _HEALTH: {"status": "HEALTHY", "remainingCapacity": 90},
    })
    asyncio.run(coord._setup_initial_reads([VIN]))
    assert backend.count(_HEALTH) == 1


def test_no_extra_garage_request_overall() -> None:
    coord, backend = _coord("skoda", {_GARAGE: _garage(["CHARGING"])})
    asyncio.run(_setup_then_follow_ups(coord))
    assert backend.count(_GARAGE) == 1


def test_failed_garage_fetch_is_not_repeated_by_the_follow_ups() -> None:
    coord, backend = _coord("skoda", {_GARAGE: RuntimeError("boom")})
    asyncio.run(_setup_then_follow_ups(coord))
    assert backend.count(_GARAGE) == 1


def test_other_brands_do_not_fetch_capabilities_first() -> None:
    coord, _ = _coord("cupra", {})
    coord.refresh_capabilities = AsyncMock()  # type: ignore[method-assign]
    coord._cariad_client.get_status = AsyncMock(return_value=None)  # type: ignore[method-assign]
    asyncio.run(coord._setup_initial_reads([VIN]))
    coord.refresh_capabilities.assert_not_awaited()


def test_every_follow_up_fetch_goes_through_the_cache() -> None:
    """The tests above drive a stand-in for ``_enrich``; this pins the real code.

    "No request is added overall" holds only while every later fetch (the
    background finish and ``_enrich``) calls ``refresh_capabilities`` without
    ``force``, so it lands on the 24 h cache the setup read just filled.
    """
    import pathlib
    import re

    import custom_components.vag_connect.coordinator as coordinator_module

    source = pathlib.Path(coordinator_module.__file__).read_text(encoding="utf-8")
    calls = re.findall(r"self\.refresh_capabilities\(([^)]*)\)", source)
    assert len(calls) >= 3, calls  # setup read, background finish, _enrich
    assert [c for c in calls if "force" in c] == []
