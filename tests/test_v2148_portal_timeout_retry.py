# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.14.8 — EU Data Act portal: transport-timeout retry (no pointless re-login).

v2.13.1 added backoff/retry for transient HTTP 5xx, but only for a *received*
response — the retry loop inspected ``resp.status``. A transport-level
``asyncio.TimeoutError`` (or ``ClientConnectionError``) from ``_session.get()``
itself never produced a ``resp``, so it bypassed the retry entirely and
propagated. That's exactly the cluster seen in the auto-filed Error Reporter
issues #481/#482/#483 (``TimeoutError`` at ``get_status`` → ``get_vehicle_data``
→ ``_get_json``), and it surfaced as a failed poll instead of "no data this
poll".

v2.14.8 wraps the network call in the retry loop: a timeout/disconnect is
treated like a transient 5xx — retried with the same backoff, then a ``soft``
call gives up as ``None`` ("no data this poll") and a hard call re-raises the
ORIGINAL error. It is never converted to ``AuthenticationError`` (that would
force the pointless re-login v2.12.4 fought).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _PORTAL_RETRY_DELAYS,
    EUDataActConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

_SLEEP = "custom_components.vag_connect.cariad.auth._eu_data_act.asyncio.sleep"


def _ok(json_data: Any) -> AsyncMock:
    r = AsyncMock()
    r.status = 200
    r.json = AsyncMock(return_value=json_data)
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    return r


def _timeout_cm() -> AsyncMock:
    """A ``session.get(...)`` CM whose ``__aenter__`` raises like a real
    aiohttp request timeout (the transport error, before any response)."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=TimeoutError("portal slow"))
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _session_seq(items: list[Any]) -> MagicMock:
    s = MagicMock()
    it = iter(items)
    s.get = MagicMock(side_effect=lambda *a, **k: next(it))
    return s


def _conn(session: Any) -> EUDataActConnector:
    return EUDataActConnector(session, brand="volkswagen")


_ATTEMPTS = len(_PORTAL_RETRY_DELAYS) + 1  # initial try + retries


class TestPortalTimeoutRetry:
    def test_soft_timeout_then_success_recovers_poll(self) -> None:
        """A timeout that clears on retry recovers the poll (no error)."""
        sess = _session_seq([_timeout_cm(), _ok({"ok": 1})])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            out = asyncio.run(conn._get_json("https://x/y", soft=True))
        assert out == {"ok": 1}
        assert sess.get.call_count == 2

    def test_soft_persistent_timeout_returns_none_not_auth_error(self) -> None:
        """Persistent timeouts on a soft call → None ("no data this poll"),
        NOT AuthenticationError, and the call was retried."""
        sess = _session_seq([_timeout_cm() for _ in range(_ATTEMPTS)])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            out = asyncio.run(conn._get_json("https://x/y", soft=True))
        assert out is None
        assert sess.get.call_count == _ATTEMPTS  # 1 try + retries

    def test_hard_timeout_reraises_timeout_not_auth_error(self) -> None:
        """A hard (non-soft) call re-raises the original TimeoutError after
        retries — it must NOT become AuthenticationError (no re-login churn)."""
        sess = _session_seq([_timeout_cm() for _ in range(_ATTEMPTS)])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            with pytest.raises(TimeoutError):
                asyncio.run(conn._get_json("https://x/y", soft=False))
        assert sess.get.call_count == _ATTEMPTS

    def test_status_5xx_path_still_works(self) -> None:
        """Regression shield: the existing HTTP-status retry path is untouched —
        a non-soft 5xx still raises AuthenticationError immediately."""
        r = AsyncMock()
        r.status = 500
        r.__aenter__ = AsyncMock(return_value=r)
        r.__aexit__ = AsyncMock(return_value=False)
        sess = _session_seq([r])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            with pytest.raises(AuthenticationError):
                asyncio.run(conn._get_json("https://x/y", soft=False))
        assert sess.get.call_count == 1
