# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
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

    def test_non_soft_retries_then_raises(self):
        """A hard call retries a retriable 5xx, then still raises.

        The retry used to sit inside the soft branch, so a hard call gave up on
        the first hiccup while a transport timeout on the same call retried
        three times. VIN enumeration is a hard call, and an empty VIN list is
        read as "this account has no cars", so failing fast there costs a
        working setup. What must NOT change is the ending: a hard call still
        raises rather than returning an empty result.
        """
        sess = _session_seq([_resp(500), _resp(500), _resp(500)])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            with pytest.raises(AuthenticationError):
                asyncio.run(conn._get_json("https://x/y", soft=False))
        assert sess.get.call_count == 3  # 1 try + 2 retries, same as soft

    def test_non_soft_recovers_when_a_retry_succeeds(self):
        """The point of retrying: a one-off 500 no longer kills the call."""
        ok = _resp(200)
        ok.json = AsyncMock(return_value={"vehicles": []})
        sess = _session_seq([_resp(500), ok])
        conn = _conn(sess)
        with patch(_SLEEP, new=AsyncMock()):
            out = asyncio.run(conn._get_json("https://x/y", soft=False))
        assert out == {"vehicles": []}
