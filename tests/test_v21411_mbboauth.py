# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.14.11 — MBB OAuth token-exchange module (legacy stack, pre-App-Check).

Validates the request shape (URL / X-Client-Id header / grant_type+token+scope
body) and response parsing against the grounded DEX+probe contract, with a
fully mocked session (no network).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth import _mbboauth
from custom_components.vag_connect.cariad.exceptions import AuthenticationError


class _FakeResp:
    def __init__(self, status: int, payload: dict[str, Any] | str) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def text(self) -> str:
        if isinstance(self._payload, str):
            return self._payload
        return json.dumps(self._payload)


class _FakeSession:
    """Captures the last POST so tests can assert URL/headers/body."""

    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, data: Any = None, headers: Any = None,
             timeout: Any = None) -> _FakeResp:
        self.calls.append({"url": url, "data": data, "headers": headers})
        return self._resp


_GOOD = {
    "access_token": "AT.xxx",
    "refresh_token": "RT.yyy",
    "token_type": "Bearer",
    "expires_in": 3600,
}


@pytest.mark.asyncio
async def test_exchange_id_token_request_shape() -> None:
    sess = _FakeSession(_FakeResp(200, _GOOD))
    out = await _mbboauth.exchange_id_token(sess, "ID.TOKEN", client_id="CID")  # type: ignore[arg-type]

    call = sess.calls[0]
    assert call["url"] == _mbboauth.MBB_TOKEN_URL
    assert call["url"].endswith("/mbbcoauth/mobile/oauth2/v1/token")
    assert call["headers"]["X-Client-Id"] == "CID"
    assert call["data"]["grant_type"] == "id_token"
    assert call["data"]["token"] == "ID.TOKEN"
    assert call["data"]["scope"] == "sc2:fal"
    # response parsed
    assert out.access_token == "AT.xxx"
    assert out.refresh_token == "RT.yyy"  # the durable bit
    assert out.is_valid()
    assert out.expires_at > 0


@pytest.mark.asyncio
async def test_default_client_is_shared_mbb_uuid() -> None:
    sess = _FakeSession(_FakeResp(200, _GOOD))
    await _mbboauth.exchange_id_token(sess, "ID.TOKEN")  # type: ignore[arg-type]
    assert sess.calls[0]["headers"]["X-Client-Id"] == \
        "9523ee15-f6e0-4eb9-9907-59d058d7e16e"
    # bare uuid, NOT a dilab client
    assert "@apps_vw-dilab_com" not in _mbboauth.MBB_SHARED_CLIENT_ID


@pytest.mark.asyncio
async def test_refresh_uses_refresh_grant() -> None:
    sess = _FakeSession(_FakeResp(200, _GOOD))
    await _mbboauth.refresh(sess, "RT.yyy", client_id="CID")  # type: ignore[arg-type]
    assert sess.calls[0]["data"]["grant_type"] == "refresh_token"
    assert sess.calls[0]["data"]["token"] == "RT.yyy"


@pytest.mark.asyncio
async def test_non_200_raises_with_status() -> None:
    sess = _FakeSession(_FakeResp(403, "Forbidden"))
    with pytest.raises(AuthenticationError, match="403"):
        await _mbboauth.exchange_id_token(sess, "ID.TOKEN")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_missing_access_token_raises() -> None:
    sess = _FakeSession(_FakeResp(200, {"refresh_token": "x"}))
    with pytest.raises(AuthenticationError, match="access_token"):
        await _mbboauth.exchange_id_token(sess, "ID.TOKEN")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_empty_id_token_rejected_before_network() -> None:
    sess = _FakeSession(_FakeResp(200, _GOOD))
    with pytest.raises(AuthenticationError, match="id_token"):
        await _mbboauth.exchange_id_token(sess, "")  # type: ignore[arg-type]
    assert sess.calls == []  # never hit the network
