# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""acpp (Audi plug&play dongle) resilience — 401 self-heal + poll cadence.

The acpp client is a standalone class (not a BaseClient), so it never inherited
the base 401→refresh path: a stale ~1h token 401'd every poll, raised APIError,
and flooded the Error Reporter (~20 repeated 401s, reported by Prash). Now it
refreshes-and-retries on 401 (rotating the refresh token), and a *persistent* 401
raises AuthenticationError so the coordinator fires one re-auth Repair instead of
spamming. It also polls hourly (the dongle only uploads after a drive).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.plugandplay import PlugAndPlayCloudClient
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import BRAND_AUDI_ACPP, TokenSet


class _Resp:
    def __init__(self, status: int, body: Any):
        self.status = status
        self._b = body
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def json(self, content_type: Any = None): return self._b
    async def text(self): return str(self._b)


class _Session:
    """Returns the queued (status, body) responses in order, one per GET."""
    def __init__(self, *responses: tuple[int, Any]):
        self._responses = list(responses)
        self.calls = 0
    def get(self, url: str, headers: Any = None, timeout: Any = None):
        i = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        status, body = self._responses[i]
        return _Resp(status, body)


def _client(session: _Session) -> PlugAndPlayCloudClient:
    c = PlugAndPlayCloudClient(session, BRAND_AUDI_ACPP, "user@example.com", "pw")
    c._tokens = TokenSet(
        access_token="dead", refresh_token="refresh-1", id_token="", expires_at=0.0,
    )
    return c


@pytest.mark.asyncio
async def test_get_refreshes_and_retries_on_401():
    s = _Session((401, {"e": "unauth"}), (200, {"ok": True}))
    c = _client(s)
    c._auth.refresh = AsyncMock(return_value=TokenSet(  # type: ignore[method-assign]
        access_token="fresh", refresh_token="refresh-2", id_token="", expires_at=0.0,
    ))
    status, body = await c._get("vehicle/VIN1")
    assert status == 200 and body == {"ok": True}
    c._auth.refresh.assert_awaited_once_with("refresh-1")
    # the rotated token is kept for the next poll
    assert c._tokens.access_token == "fresh"
    assert c._tokens.refresh_token == "refresh-2"
    assert s.calls == 2   # exactly one retry, no loop


@pytest.mark.asyncio
async def test_get_surfaces_401_when_refresh_fails():
    s = _Session((401, {"e": "unauth"}))
    c = _client(s)
    c._auth.refresh = AsyncMock(side_effect=RuntimeError("refresh boom"))  # type: ignore[method-assign]
    status, _ = await c._get("vehicle/VIN1")
    assert status == 401           # surfaced, not retried into a loop
    assert s.calls == 1


@pytest.mark.asyncio
async def test_get_does_not_refresh_without_a_refresh_token():
    s = _Session((401, {"e": "unauth"}))
    c = _client(s)
    c._tokens = TokenSet(access_token="dead", refresh_token="", id_token="", expires_at=0.0)
    c._auth.refresh = AsyncMock()  # type: ignore[method-assign]
    status, _ = await c._get("vehicle/VIN1")
    assert status == 401
    c._auth.refresh.assert_not_called()


@pytest.mark.asyncio
async def test_persistent_401_raises_auth_error_not_apierror():
    # get_raw_snapshot must raise AuthenticationError on a persistent 401 so the
    # coordinator suppresses the per-poll Error-Reporter flood + fires one reauth.
    c = PlugAndPlayCloudClient(MagicMock(), BRAND_AUDI_ACPP, "u", "p")
    c._tokens = MagicMock(access_token="x")

    async def _fake_get(path: str, _retry: bool = True):
        return 401, {"e": "unauth"}
    c._get = _fake_get  # type: ignore[assignment]
    with pytest.raises(AuthenticationError):
        await c.get_raw_snapshot("VIN1")


def test_acpp_polls_hourly_by_default():
    from custom_components.vag_connect.const import recommended_scan_interval
    assert recommended_scan_interval("audi_acpp") == 60      # dongle syncs on-drive
    assert recommended_scan_interval("skoda") == 30          # unchanged
