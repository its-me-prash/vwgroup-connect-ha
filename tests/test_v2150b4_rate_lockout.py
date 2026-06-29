# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b1/B4 — account-scoped rate-limit lockout: HTTP 430 (and 429 still firing
after the retry budget) pause ALL requests on the client for a cool-down window
so a rate-limited account is not hammered into a multi-hour lock."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api.base import _LOCKOUT_429_S, _LOCKOUT_430_S
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError
from custom_components.vag_connect.cariad.models import TokenSet


def _resp(status: int, text: str = "") -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.headers = {"Content-Type": "application/json"}
    resp.json = AsyncMock(return_value={})
    resp.text = AsyncMock(return_value=text)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _client_with(responses: list[AsyncMock]) -> tuple[VWEUClient, MagicMock, dict]:
    idx = {"i": 0}

    def side_effect(*_a: object, **_k: object) -> AsyncMock:
        r = responses[min(idx["i"], len(responses) - 1)]
        idx["i"] += 1
        return r

    session = MagicMock()
    session.request = MagicMock(side_effect=side_effect)
    client = VWEUClient(session, "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client, session, idx


class TestLockoutHelpers:
    def test_no_lock_initially(self) -> None:
        c, _, _ = _client_with([_resp(200)])
        assert c._rate_lockout_remaining() == 0

    def test_enter_sets_deadline(self) -> None:
        c, _, _ = _client_with([_resp(200)])
        c._enter_rate_lockout(1800, 429)
        assert 1790 < c._rate_lockout_remaining() <= 1800

    def test_expired_self_clears(self) -> None:
        c, _, _ = _client_with([_resp(200)])
        c._rate_limit_locked_until = time.monotonic() - 1
        assert c._rate_lockout_remaining() == 0
        assert c._rate_limit_locked_until is None


class TestRequestLockout:
    def test_locked_request_raises_without_touching_network(self) -> None:
        c, _session, idx = _client_with([_resp(200)])
        c._enter_rate_lockout(1800, 429)
        with pytest.raises(APIError):
            asyncio.run(c._request("GET", "https://x/y"))
        assert idx["i"] == 0  # never sent

    def test_430_enters_long_lockout(self) -> None:
        c, _session, _ = _client_with([_resp(430, text="locked")])
        with patch(
            "custom_components.vag_connect.cariad.api.base.asyncio.sleep",
            new=AsyncMock(return_value=None),
        ), pytest.raises(APIError):
            asyncio.run(c._request("GET", "https://x/y"))
        assert _LOCKOUT_430_S - 10 < c._rate_lockout_remaining() <= _LOCKOUT_430_S

    def test_429_exhausted_enters_lockout(self) -> None:
        c, _session, _ = _client_with([_resp(429) for _ in range(5)])
        with patch(
            "custom_components.vag_connect.cariad.api.base.asyncio.sleep",
            new=AsyncMock(return_value=None),
        ), pytest.raises(APIError):
            asyncio.run(c._request("GET", "https://x/y"))
        assert 0 < c._rate_lockout_remaining() <= _LOCKOUT_429_S

    def test_200_does_not_lock(self) -> None:
        c, _session, _ = _client_with([_resp(200)])
        asyncio.run(c._request("GET", "https://x/y"))
        assert c._rate_lockout_remaining() == 0
