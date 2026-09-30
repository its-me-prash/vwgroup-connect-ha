# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1590 (Audi Q4 Sportback e-tron) — the BFF returns a STRUCTURED 404 on
selectivestatus every poll for a car it does not serve, spamming the Error
Reporter and hammering the endpoint. get_status now backs off per-VIN after N
consecutive structured 404s (bounded, re-probing), returning ``no_data`` instead
of raising. Transient 404s (generic-router "404 page not found" / cariad
wrapper-404 with retry:true) always re-raise so the coordinator's existing
self-healing path handles them and a working car is never silenced.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import (
    _SELECTIVESTATUS_UNSERVED_STRIKES,
    VWEUClient,
)
from custom_components.vag_connect.cariad.exceptions import APIError

_VIN = "WVWZZZE1ZPX000001"
_URL = "https://emea.bff.cariad.digital/vehicle/v1/vehicles/x/selectivestatus"


def _client() -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._tokens = None  # falsy -> skip the mbb / web / portal branches
    # avoid the HomeRegion network lookup
    c._base_for_vin = lambda vin: "https://emea.bff.cariad.digital"  # type: ignore[method-assign]
    return c


def _err404(body: str = '{"error":"vehicle not found"}') -> APIError:
    return APIError(404, _URL, body)


@pytest.mark.asyncio
async def test_structured_404_backs_off_after_threshold() -> None:
    c = _client()
    c._get = AsyncMock(side_effect=_err404())  # type: ignore[method-assign]
    # The first N-1 structured 404s still raise (a one-off must surface and the
    # coordinator's hard-failure revive must still run) — unchanged behaviour.
    for _ in range(_SELECTIVESTATUS_UNSERVED_STRIKES - 1):
        with pytest.raises(APIError):
            await c.get_status(_VIN)
    # The N-th consecutive structured 404 engages the backoff: no raise, no_data.
    data = await c.get_status(_VIN)
    assert data.no_data is True
    assert _VIN in c.selectivestatus_unserved_vins
    calls = c._get.call_count
    # A further poll while backed off skips the dead read entirely.
    data2 = await c.get_status(_VIN)
    assert data2.no_data is True
    assert c._get.call_count == calls, "backed-off VIN must not hit the endpoint"


@pytest.mark.asyncio
async def test_generic_router_404_is_never_cached() -> None:
    c = _client()
    c._get = AsyncMock(side_effect=_err404("404 page not found"))  # type: ignore[method-assign]
    for _ in range(_SELECTIVESTATUS_UNSERVED_STRIKES + 2):
        with pytest.raises(APIError):
            await c.get_status(_VIN)
    assert _VIN not in c.selectivestatus_unserved_vins


@pytest.mark.asyncio
async def test_cariad_wrapper_404_is_never_cached() -> None:
    c = _client()
    c._get = AsyncMock(side_effect=_err404('{"error":{"retry":true}}'))  # type: ignore[method-assign]
    for _ in range(_SELECTIVESTATUS_UNSERVED_STRIKES + 2):
        with pytest.raises(APIError):
            await c.get_status(_VIN)
    assert _VIN not in c.selectivestatus_unserved_vins


@pytest.mark.asyncio
async def test_per_vin_isolation() -> None:
    c = _client()
    other = "WVWZZZE1ZPX000002"
    c._get = AsyncMock(side_effect=_err404())  # type: ignore[method-assign]
    # VIN_A reaches the threshold and backs off.
    for _ in range(_SELECTIVESTATUS_UNSERVED_STRIKES):
        try:
            await c.get_status(_VIN)
        except APIError:
            pass
    assert _VIN in c.selectivestatus_unserved_vins
    # VIN_B has its own counter: below threshold it still raises and is NOT
    # backed off just because VIN_A was.
    with pytest.raises(APIError):
        await c.get_status(other)
    assert other not in c.selectivestatus_unserved_vins


@pytest.mark.asyncio
async def test_success_resets_strikes() -> None:
    c = _client()
    ss = {"n": 0}

    def _side(url: str | None = None, **kw: object) -> dict:
        if "selectivestatus" in (url or ""):
            ss["n"] += 1
            if ss["n"] <= 2:
                raise _err404()
        return {}  # selectivestatus success + all gap-fill endpoints

    c._get = AsyncMock(side_effect=_side)  # type: ignore[method-assign]
    for _ in range(2):
        with pytest.raises(APIError):
            await c.get_status(_VIN)
    # third selectivestatus read succeeds -> strike counter resets, no backoff
    data = await c.get_status(_VIN)
    assert data.no_data is not True
    assert _VIN not in c.selectivestatus_unserved_vins
    assert c._selectivestatus_404_strikes.get(_VIN, 0) == 0
