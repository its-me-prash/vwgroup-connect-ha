# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b11 — proactive durable-MBB bearer refresh.

The key MBB reads (operationList, VSR) run with ``_retry=False`` so a data-plane
ACL 401 can't trigger a refresh storm. That disables the reactive 401→refresh for
them, so once the bearer expired EVERY read 401'd ("Token expired") until a
restart. ``_mbb_ensure_fresh`` refreshes pre-flight when the token is within the
60s expiry skew — verified here for the read path + the no-op cases.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.models import TokenSet


class _Resp:
    def __init__(self, status: int = 200, text: str = '{"ok": 1}') -> None:
        self.status = status
        self._t = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self) -> str:
        return self._t


class _Sess:
    def get(self, url: str, headers: Any = None) -> _Resp:
        return _Resp()


def _client(strategy: str, expires_at: float) -> VWEUClient:
    c = VWEUClient(_Sess(), "u@t.de", "pw")
    c._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i",
        expires_at=expires_at, strategy=strategy,
    )
    c._refresh_tokens = AsyncMock()  # type: ignore[method-assign]
    return c


def test_mbb_get_proactively_refreshes_expired_bearer() -> None:
    c = _client("mbb", time.time() - 10)  # expired
    asyncio.run(c._mbb_get("https://msg.volkswagen.de/x"))
    c._refresh_tokens.assert_awaited_once()


def test_mbb_get_skips_refresh_when_bearer_fresh() -> None:
    c = _client("mbb", time.time() + 3600)  # fresh
    asyncio.run(c._mbb_get("https://msg.volkswagen.de/x"))
    c._refresh_tokens.assert_not_awaited()


def test_ensure_fresh_is_noop_for_non_mbb_strategy() -> None:
    c = _client("idk", time.time() - 10)  # expired but not MBB
    asyncio.run(c._mbb_ensure_fresh())
    c._refresh_tokens.assert_not_awaited()


def test_ensure_fresh_noop_when_expiry_unknown() -> None:
    c = _client("mbb", 0.0)  # unknown expiry → needs_refresh False
    asyncio.run(c._mbb_ensure_fresh())
    c._refresh_tokens.assert_not_awaited()
