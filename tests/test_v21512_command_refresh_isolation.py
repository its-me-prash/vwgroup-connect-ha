# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.12 (#584) — a failed remote command must not knock the reads offline.

Reporter CyberChris79 (VW Passat Alltrack, legacy MQB → ``strategy == "mbb"``
PRIMARY read path) pressed lock/unlock/climate a few times while VW's MBB token
backend was flaky (``500 IllegalStateException``). Each failed press triggered
``_refresh_tokens`` which billed the SHARED ``_refresh_history`` storm budget;
after 3 the guard raised for EVERY caller, so the data-read poll tripped it and
all entities went unavailable ("Token refresh storm — please reauthenticate").

Fix: commands bill a SEPARATE ``_cmd_refresh_history`` budget (``for_command``),
and the MBB token exchange retries a transient 5xx with backoff before failing.

Covered here:
  (a) a command-triggered refresh (incl. a storm) never spends the data-plane
      budget, never corrupts/clears the read token, and reads keep refreshing.
  (b) a transient MBB 5xx is retried then gives up cleanly with the verbatim
      error; a 5xx-then-200 recovers.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad.api import base as _base
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.auth import _mbboauth
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import TokenSet


class _Sess:
    def get(self, url: str, headers: Any = None) -> Any:  # pragma: no cover
        raise AssertionError("no network in these tests")


def _mbb_client() -> VWEUClient:
    c = VWEUClient(_Sess(), "u@t.de", "pw")
    c._tokens = TokenSet(
        access_token="READ_BEARER", refresh_token="RT", id_token="i",
        expires_at=0.0, strategy="mbb",
    )
    c._mbb_client_id = "CID"
    return c


# ── (a) command budget isolation ───────────────────────────────────────────


def test_command_refresh_bills_separate_budget(monkeypatch) -> None:
    """A ``for_command`` refresh fills ``_cmd_refresh_history``, NOT the
    data-plane ``_refresh_history`` — so the read poll's budget is untouched."""
    c = _mbb_client()

    async def _fake_refresh(session, refresh_token, *, client_id):
        return _mbboauth.MbbTokenSet(
            access_token="READ_BEARER", refresh_token="RT",
            token_type="Bearer", expires_at=0.0,
        )

    monkeypatch.setattr(_mbboauth, "refresh", _fake_refresh)

    asyncio.run(c._refresh_tokens(for_command=True))

    assert len(c._cmd_refresh_history) == 1
    assert c._refresh_history == []  # data-plane budget untouched


def test_command_storm_does_not_block_data_refresh(monkeypatch) -> None:
    """Even after the COMMAND budget is exhausted (storm on commands), a
    DATA-plane refresh still proceeds and the read token stays intact."""
    c = _mbb_client()

    calls: list[str] = []

    async def _fake_refresh(session, refresh_token, *, client_id):
        calls.append("hit")
        return _mbboauth.MbbTokenSet(
            access_token="READ_BEARER", refresh_token="RT2",
            token_type="Bearer", expires_at=0.0,
        )

    monkeypatch.setattr(_mbboauth, "refresh", _fake_refresh)

    # Exhaust the COMMAND budget.
    for _ in range(_base._REFRESH_MAX_PER_HOUR):
        asyncio.run(c._refresh_tokens(for_command=True))
    # One more command refresh now storms — but ONLY for commands.
    with pytest.raises(AuthenticationError, match="storm"):
        asyncio.run(c._refresh_tokens(for_command=True))

    # The DATA path is unaffected: its budget is empty, so a read refresh works.
    assert c._refresh_history == []
    asyncio.run(c._refresh_tokens(for_command=False))
    assert len(c._refresh_history) == 1
    # The read bearer was refreshed, never cleared/corrupted by the command storm.
    assert c._tokens.access_token == "READ_BEARER"
    assert c._tokens.strategy == "mbb"


def test_data_storm_is_independent_of_command_budget(monkeypatch) -> None:
    """Symmetric guarantee: exhausting the DATA budget does not touch the
    command budget (commands remain independently gated)."""
    c = _mbb_client()

    async def _fake_refresh(session, refresh_token, *, client_id):
        return _mbboauth.MbbTokenSet(
            access_token="READ_BEARER", refresh_token="RT",
            token_type="Bearer", expires_at=0.0,
        )

    monkeypatch.setattr(_mbboauth, "refresh", _fake_refresh)

    for _ in range(_base._REFRESH_MAX_PER_HOUR):
        asyncio.run(c._refresh_tokens(for_command=False))
    with pytest.raises(AuthenticationError, match="storm"):
        asyncio.run(c._refresh_tokens(for_command=False))

    assert c._cmd_refresh_history == []  # command budget never spent


# ── (b) transient MBB 5xx retry/backoff ─────────────────────────────────────


class _Resp:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._b = body

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self) -> str:
        return self._b


class _SeqSession:
    """Returns a scripted sequence of responses, one per POST."""

    def __init__(self, responses: list[_Resp]) -> None:
        self._responses = responses
        self.n = 0

    def post(self, url: str, *, data: Any = None, headers: Any = None,
             timeout: Any = None) -> _Resp:
        r = self._responses[self.n]
        self.n += 1
        return r


def test_transient_5xx_retries_then_gives_up(monkeypatch) -> None:
    """A persistent 500 is retried up to the cap, then surfaces verbatim."""
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    body = '{"error":"IllegalStateException"}'
    sess = _SeqSession(
        [_Resp(500, body) for _ in range(_mbboauth._TOKEN_5XX_MAX_ATTEMPTS)]
    )
    with pytest.raises(AuthenticationError, match="MBB token exchange HTTP 500"):
        asyncio.run(_mbboauth.refresh(sess, "RT", client_id="CID"))
    # It actually retried the full budget (not a single-shot fail).
    assert sess.n == _mbboauth._TOKEN_5XX_MAX_ATTEMPTS


def test_transient_5xx_then_success_recovers(monkeypatch) -> None:
    """A 500 followed by a 200 recovers — the blip is absorbed, no error."""
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    good = (
        '{"access_token":"AT","refresh_token":"RT2",'
        '"token_type":"Bearer","expires_in":3600}'
    )
    sess = _SeqSession([_Resp(503, "blip"), _Resp(200, good)])
    out = asyncio.run(_mbboauth.refresh(sess, "RT", client_id="CID"))
    assert out.access_token == "AT"
    assert out.refresh_token == "RT2"
    assert sess.n == 2


def test_non_5xx_still_fails_immediately(monkeypatch) -> None:
    """A 403 is NOT retried (only 5xx is transient) — one shot, verbatim."""
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    sess = _SeqSession([_Resp(403, "Forbidden")])
    with pytest.raises(AuthenticationError, match="403"):
        asyncio.run(_mbboauth.refresh(sess, "RT", client_id="CID"))
    assert sess.n == 1  # no retry on a non-5xx


async def _no_sleep(_secs: float) -> None:
    return None
