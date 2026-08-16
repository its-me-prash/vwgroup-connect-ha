# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#602: the Škoda push user-id comes from the mysmob /v1/users endpoint.

Marco Schmidt's v3.2.0 diagnostics still showed push_states={} — decoding the
id_token 'sub' returned nothing on his classic mysmob login, so the push manager
never armed. The MySkoda app + the myskoda library both read the id from
GET /api/v1/users -> .id (verified against skodaconnect/myskoda rest_api.py:700
+ myskoda.py:216, same mysmob backend we use). We now capture it there, during
get_vehicles, so it is set before the push manager arms.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad.api.base import APIError
from custom_components.vag_connect.cariad.api.skoda import SkodaClient, _BASE

VIN = "TMBJR0NX4SY000001"


def _client(user_id=None):
    c = SkodaClient.__new__(SkodaClient)
    c._user_id = user_id
    c._eu_portal = None
    return c


def test_capture_user_id_from_v1_users():
    c = _client()

    async def _get(url: str, **_kw: Any):
        assert url == f"{_BASE}/api/v1/users"
        return {"id": "acct-guid-123", "firstName": "M"}

    c._get = _get  # type: ignore[assignment]
    asyncio.run(c._capture_user_id())
    assert c._user_id == "acct-guid-123"


def test_capture_is_noop_when_already_known():
    c = _client(user_id="already-have-it")
    c._get = AsyncMock()  # type: ignore[assignment]
    asyncio.run(c._capture_user_id())
    assert c._user_id == "already-have-it"
    c._get.assert_not_awaited()


def test_capture_is_fail_soft():
    c = _client()

    async def _get(url: str, **_kw: Any):
        raise APIError(500, url, "server error")

    c._get = _get  # type: ignore[assignment]
    asyncio.run(c._capture_user_id())          # must not raise
    assert c._user_id is None                  # push stays unarmed, poll survives


def test_get_vehicles_captures_user_id_on_native_path():
    c = _client()

    async def _get(url: str, **_kw: Any):
        if "/api/v2/garage" in url:
            return {"vehicles": [{"vin": VIN}]}
        if "/api/v1/users" in url:
            return {"id": "acct-xyz"}
        return {}

    c._get = _get  # type: ignore[assignment]
    c.fetch_images = AsyncMock()  # type: ignore[assignment]
    vins = asyncio.run(c.get_vehicles())
    assert vins == [VIN]
    assert c._user_id == "acct-xyz"            # arming guard will now pass
