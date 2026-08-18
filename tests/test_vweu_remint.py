# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way — proactive re-mint of the ~1 h device-grant Bearer (#1217).

The 650d46ca Bearer is non-refreshable and an expired one can come back 403 (not
401) from the CARIAD BFF, so the reactive 401-retry alone let the entry freeze
after ~1 h (leMineGaming). ``_request`` now re-mints PROACTIVELY once the token
is within ``_DEVICE_GRANT_REMINT_SKEW_S`` of expiry. These pin that.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.models import TokenSet


class _FakeResp:
    """Minimal async-context-manager stand-in for an aiohttp response (204)."""

    def __init__(self, status: int = 204) -> None:
        self.status = status
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False

    async def json(self) -> dict:
        return {}

    async def text(self) -> str:
        return ""


def _client(expires_in: float, password: str = "pw") -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._tokens = TokenSet(
        access_token="old", refresh_token="", id_token="",
        expires_at=time.time() + expires_in, strategy="device_grant",
    )
    c._brand = MagicMock()
    c._brand.name = "volkswagen"
    c._brand.user_agent = "ua"
    c._vweu_email = "e@x"
    c._vweu_password = password
    c._session = MagicMock()
    c._session.request = MagicMock(return_value=_FakeResp(204))
    c._refresh_tokens = AsyncMock()
    c._rate_lockout_remaining = MagicMock(return_value=0)
    c._capture_rate_limit_headers = MagicMock()
    return c


def test_proactive_remint_when_token_near_expiry() -> None:
    c = _client(expires_in=60)  # inside the 5-min skew
    asyncio.run(c._request("GET", "https://emea.bff.cariad.digital/x"))
    c._refresh_tokens.assert_awaited_once()


def test_no_remint_when_token_fresh() -> None:
    c = _client(expires_in=3600)  # far from expiry
    asyncio.run(c._request("GET", "https://emea.bff.cariad.digital/x"))
    c._refresh_tokens.assert_not_awaited()


def test_no_remint_without_stored_password() -> None:
    # Without a stored password we cannot headlessly re-mint, so don't try —
    # the reactive path + coordinator reauth remain the fallback.
    c = _client(expires_in=60, password="")
    asyncio.run(c._request("GET", "https://emea.bff.cariad.digital/x"))
    c._refresh_tokens.assert_not_awaited()


def test_no_remint_for_non_device_grant_strategy() -> None:
    c = _client(expires_in=60)
    c._tokens = TokenSet(
        access_token="old", refresh_token="r", id_token="",
        expires_at=time.time() + 60, strategy="classic",
    )
    asyncio.run(c._request("GET", "https://emea.bff.cariad.digital/x"))
    c._refresh_tokens.assert_not_awaited()
