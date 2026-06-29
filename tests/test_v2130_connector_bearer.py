# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.13.0 Block A2 — EUDataActConnector device-code Bearer mode.

When constructed with an access_token (the device-grant portal token), the
connector authenticates every proxy_api call via Authorization: Bearer instead
of the cookie-scrape session, and login() becomes a no-op. With no token the
cookie path is byte-identical to before (existing entries keep working).
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector


class _Resp:
    def __init__(self, headers: dict | None) -> None:
        self.status = 200
        self._h = headers

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def json(self, content_type: Any = None) -> Any:
        return {"vehicles": [{"vin": "WVWZZZ1KZAW000001"}]}

    async def read(self) -> bytes:
        return b""


class _RecordSession:
    """Records the headers of the last GET so tests can assert Bearer auth."""

    def __init__(self) -> None:
        self.last_headers: dict = {}

    def get(self, url: str, headers: dict | None = None, **kw: Any) -> _Resp:
        self.last_headers = headers or {}
        return _Resp(headers)


@pytest.mark.asyncio
async def test_bearer_injected_on_proxy_api_calls() -> None:
    s = _RecordSession()
    conn = EUDataActConnector(s, brand="volkswagen", access_token="TOK123")  # type: ignore[arg-type]
    await conn.list_vehicle_vins()
    assert s.last_headers.get("Authorization") == "Bearer TOK123"


@pytest.mark.asyncio
async def test_cookie_mode_has_no_authorization_header() -> None:
    s = _RecordSession()
    conn = EUDataActConnector(s, brand="volkswagen")  # type: ignore[arg-type]  # no token → cookie mode
    await conn.list_vehicle_vins()
    assert "Authorization" not in s.last_headers


@pytest.mark.asyncio
async def test_login_is_noop_in_bearer_mode() -> None:
    conn = EUDataActConnector(_RecordSession(), brand="volkswagen", access_token="TOK")  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")  # must NOT scrape
    assert conn.logged_in is True


def test_set_bearer_switches_mode() -> None:
    conn = EUDataActConnector(_RecordSession(), brand="volkswagen")  # type: ignore[arg-type]
    assert conn._bearer is None
    conn.set_bearer("LATER")
    assert conn._bearer == "LATER"
    assert conn.logged_in is True
