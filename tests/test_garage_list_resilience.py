# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Garage-list resilience (b15).

myAudi 5.7.0 moved the garage list from ``/vehicle/v1/vehicles`` to ``/vehicles``
(a new garageinformation module). CARIAD may eventually retire the old path. If
the primary BFF list ever 404s, ``get_vehicles()`` must NOT die — for Audi the
vgql userVehicles list on a different host enumerates the whole garage, so we
fall back to it. Previously the 404 raised APIError before the vgql merge could
run, so the integration lost every Audi vehicle the moment the old path went away.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError
from custom_components.vag_connect.cariad.models import TokenSet


def _client(strategy: str = "device_grant") -> VWEUClient:
    c = VWEUClient(MagicMock(), "u@e.com", "pw", "1234")
    c._tokens = TokenSet(access_token="t", refresh_token="r", id_token="",
                         expires_at=0.0, strategy=strategy)
    c._eu_portal = None            # not a portal entry → reach the BFF garage path
    c._garage_base = MagicMock(return_value="https://bff")  # type: ignore[method-assign]
    return c


@pytest.mark.asyncio
async def test_bff_list_404_falls_back_to_vgql():
    c = _client()
    c._get = AsyncMock(side_effect=APIError(404, "https://bff/vehicle/v1/vehicles", "nf"))
    async def _fetch_images():
        c._image_data = {"WVWZZZ00000000001": {}}
    c.fetch_images = _fetch_images  # type: ignore[method-assign]
    vins = await c.get_vehicles()
    assert vins == ["WVWZZZ00000000001"]   # rescued via the vgql garage

@pytest.mark.asyncio
async def test_bff_list_401_also_recovers():
    c = _client()
    c._get = AsyncMock(side_effect=APIError(401, "https://bff/vehicle/v1/vehicles", "x"))
    async def _fetch_images():
        c._image_data = {"VIN_A": {}, "VIN_B": {}}
    c.fetch_images = _fetch_images  # type: ignore[method-assign]
    vins = await c.get_vehicles()
    assert set(vins) == {"VIN_A", "VIN_B"}

@pytest.mark.asyncio
async def test_bff_list_fail_no_vgql_returns_empty_not_raise():
    # e.g. VW-EU token entry (no vgql) — must fail SOFT, never raise.
    c = _client()
    c._get = AsyncMock(side_effect=APIError(404, "https://bff/vehicle/v1/vehicles", "nf"))
    async def _fetch_images():
        c._image_data = {}
    c.fetch_images = _fetch_images  # type: ignore[method-assign]
    vins = await c.get_vehicles()
    assert vins == []

@pytest.mark.asyncio
async def test_bff_list_success_unchanged():
    # happy path is untouched: the BFF list still drives the result.
    c = _client()
    c._get = AsyncMock(return_value={"data": [{"vin": "VIN1"}]})
    c._resolve_home_regions = AsyncMock()  # type: ignore[method-assign]
    async def _fetch_images():
        c._image_data = {}
    c.fetch_images = _fetch_images  # type: ignore[method-assign]
    vins = await c.get_vehicles()
    assert vins == ["VIN1"]
