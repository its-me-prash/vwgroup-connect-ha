# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.13.1 — exponential backoff on the flaky EU Data Act portal.

The portal returns transient 5xx that come and go within seconds (the whole
portal ecosystem hit this). On a soft call, ``_get_json`` now backs off and
retries the genuinely-transient server errors a couple of times before giving
up as "no data this poll" — recovering polls the portal would otherwise drop.
A 404/410 (data request not provisioned yet) returns immediately (no added
latency); a real 401/403 still raises.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

_SLEEP = "custom_components.vag_connect.cariad.auth._eu_data_act.asyncio.sleep"


def _resp(status, json_data=None):
    r = AsyncMock()
    r.status = status
    r.json = AsyncMock(return_value=json_data if json_data is not None else {})
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    return r


def _session_seq(responses):
    s = MagicMock()
    it = iter(responses)
    s.get = MagicMock(side_effect=lambda *a, **k: next(it))
    return s


def _conn(session):
    return EUDataActConnector(session, brand="volkswagen")


class TestPortalBackoff:
    def test_transient_then_success(self):
        sess = _session_seq([_resp(503), _resp(200, {"ok": 1})])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            out = asyncio.run(conn._get_json("https://x/y", soft=True))
        assert out == {"ok": 1}
        assert sess.get.call_count == 2

    def test_persistent_transient_returns_none_after_retries(self):
        sess = _session_seq([_resp(503), _resp(502), _resp(500)])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            out = asyncio.run(conn._get_json("https://x/y", soft=True))
        assert out is None
        assert sess.get.call_count == 3  # 1 try + 2 retries

    def test_404_returns_immediately_without_retry(self):
        sess = _session_seq([_resp(404)])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()) as sleep:
            out = asyncio.run(conn._get_json("https://x/y", soft=True))
        assert out is None
        assert sess.get.call_count == 1  # 404 is a stable state, not retried
        sleep.assert_not_awaited()

    def test_non_soft_raises_immediately(self):
        sess = _session_seq([_resp(500)])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            with pytest.raises(AuthenticationError):
                asyncio.run(conn._get_json("https://x/y", soft=False))
        assert sess.get.call_count == 1
