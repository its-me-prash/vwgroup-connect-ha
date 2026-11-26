# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2159 — a retry sends the caller's headers and timeout again.

@matroeh traced intermittently empty Škoda charging-statistics sensors (last
session energy and AC/DC type going ``unknown`` about once an hour) to the
shared ``base._request``: it pops ``headers`` and ``timeout`` out of ``kwargs``
and then retries with ``**kwargs`` alone. After a 401 and a token refresh the
retry therefore went out without ``X-Brand``, ``X-Device-Timezone`` and
``X-Api-Version`` and with the 60 s default instead of the caller's 30 s; on his
installation that retry answered 404. With the options kept, his live retry
after a real 401 answered 200.

The same omission sat in all four recursive paths (401, 429 without
``Retry-After``, 5xx, transient network error), so each is pinned here, plus
the real caller, plus two things the fix must not break: ``Authorization`` is
rebuilt from the CURRENT token on every attempt, and the caller's own dict is
not written into.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from aiohttp import ClientTimeout, ServerDisconnectedError

_URL = "https://prod.emea.mobile.charging.cariad.digital/charging_statistics"
_CALLER_HEADERS = {
    "Accept-Language": "en-US",
    "X-Brand": "skoda",
    "X-Device-Timezone": "GMT",
    "X-Api-Version": "1",
}


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    async def text(self, **_kw: Any) -> str:
        return "error body"

    async def json(self, **_kw: Any) -> Any:
        return {"ok": True}

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    """Answers from a script and records the headers and timeout of every send.

    A script entry that is an exception is raised at send time, which is where
    aiohttp raises a refused connection or a dropped server.
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.sent: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kw: Any) -> _Resp:
        # A copy: the code under test may keep using the dict it passed.
        self.sent.append({"headers": dict(kw.get("headers") or {}),
                          "timeout": kw.get("timeout")})
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return _Resp(step)


def _client(session: _Session) -> Any:
    """A Škoda client: not ``volkswagen``, so the proactive VW-EU re-mint
    branch in ``_request`` cannot fire. The refresh only swaps the token."""
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient(session, "u@t.invalid", "pw")  # type: ignore[arg-type]
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok-old")  # type: ignore[assignment]
    c.refreshes = 0

    async def _refresh(**_kw: Any) -> None:
        c.refreshes += 1
        c._tokens = SimpleNamespace(access_token="tok-new")

    c._refresh_tokens = _refresh  # type: ignore[method-assign]
    return c


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    from custom_components.vag_connect.cariad.api import base

    async def _fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _post(
    c: Any, headers: dict[str, str] | None, timeout: Any, method: str = "POST"
) -> Any:
    kw: dict[str, Any] = {"json": {"x": 1}}
    if headers is not None:
        kw["headers"] = headers
    if timeout is not None:
        kw["timeout"] = timeout
    return _run(c._request(method, _URL, **kw))


def _assert_caller_options(sent: dict[str, Any], timeout: Any) -> None:
    for key, value in _CALLER_HEADERS.items():
        assert sent["headers"].get(key) == value, (key, sent["headers"])
    assert sent["timeout"] is timeout


@pytest.mark.parametrize(
    ("first", "method"),
    [
        pytest.param(401, "POST", id="401-refresh"),
        # #2241 — a POST is a command and is no longer repeated after a 429,
        # so this path is reached by a read.
        pytest.param(429, "GET", id="429-no-retry-after"),
        pytest.param(500, "POST", id="500"),
        pytest.param(503, "POST", id="503"),
        pytest.param(ServerDisconnectedError(), "POST", id="server-disconnected"),
    ],
)
def test_each_retry_path_sends_the_caller_options_again(first: Any, method: str) -> None:
    session = _Session([first, 200])
    c = _client(session)
    timeout = ClientTimeout(total=30)

    result = _post(c, dict(_CALLER_HEADERS), timeout, method)

    assert result == {"ok": True}
    assert len(session.sent) == 2
    _assert_caller_options(session.sent[0], timeout)
    _assert_caller_options(session.sent[1], timeout)


def test_a_401_retry_carries_the_new_token_not_the_old_one() -> None:
    session = _Session([401, 200])
    c = _client(session)

    _post(c, dict(_CALLER_HEADERS), ClientTimeout(total=30))

    assert c.refreshes == 1
    assert session.sent[0]["headers"]["Authorization"] == "Bearer tok-old"
    assert session.sent[1]["headers"]["Authorization"] == "Bearer tok-new"


def test_a_caller_authorization_never_outranks_the_current_token() -> None:
    """Keeping the caller's headers must not keep a stale bearer: the shared
    path always sets ``Authorization`` itself, on every attempt."""
    session = _Session([401, 200])
    c = _client(session)
    headers = {**_CALLER_HEADERS, "Authorization": "Bearer from-caller"}

    _post(c, headers, None)

    assert session.sent[0]["headers"]["Authorization"] == "Bearer tok-old"
    assert session.sent[1]["headers"]["Authorization"] == "Bearer tok-new"


def test_the_callers_dict_is_not_written_into() -> None:
    session = _Session([500, 200])
    c = _client(session)
    headers = dict(_CALLER_HEADERS)

    _post(c, headers, ClientTimeout(total=30))

    assert headers == _CALLER_HEADERS


def test_without_caller_options_a_retry_keeps_the_default_timeout() -> None:
    from custom_components.vag_connect.cariad.api.base import _REQUEST_TIMEOUT

    session = _Session([500, 200])
    c = _client(session)

    _post(c, None, None)

    assert len(session.sent) == 2
    for sent in session.sent:
        assert sent["timeout"].total == _REQUEST_TIMEOUT
        assert "X-Brand" not in sent["headers"]
        assert sent["headers"]["Authorization"] == "Bearer tok-old"


@pytest.mark.parametrize("brand", ["seat", "cupra"])
def test_ola_retry_after_a_server_error_keeps_the_app_headers(brand: str) -> None:
    """SEAT/CUPRA put the app headers in through their own ``_request`` and
    pass them to the shared one as caller headers; the 403 fallback chain is
    keyed on ``_attempt``. With the headers lost, a 5xx retry (``_attempt``
    1, 2, 3) therefore went out with the older fallback app version and then
    with no app headers at all. It now keeps the set of the first attempt.
    The 403 fallback chain itself is not touched by this (its own tests)."""
    from unittest.mock import MagicMock

    from custom_components.vag_connect.cariad._ola_headers import get_ola_headers
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    session = _Session([500, 503, 200])
    c = SeatCupraClient(MagicMock(), brand, "u@t.invalid", "pw")
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok-old")  # type: ignore[assignment]
    primary = get_ola_headers(brand)

    result = _run(c._request("GET", "https://ola.prod.code.seat.cloud.vwgroup.com/v1/x"))

    assert result == {"ok": True}
    assert len(session.sent) == 3
    for sent in session.sent:
        for key, value in primary.items():
            assert sent["headers"].get(key) == value, (key, sent["headers"])


def test_skoda_charging_statistics_survives_a_401() -> None:
    """The caller from the report, end to end: 401, refresh, retry with the
    Škoda-specific headers and its 30 s timeout, and the payload comes back
    instead of the empty best-effort result."""
    session = _Session([401, 200])
    c = _client(session)

    result = _run(c.get_charging_statistics("TMBZZZ00000000000"))

    assert result == {"ok": True}
    assert len(session.sent) == 2
    retry = session.sent[1]
    assert retry["headers"].get("X-Brand") == "skoda"
    assert retry["headers"].get("X-Api-Version") == "1"
    assert retry["headers"].get("X-Device-Timezone") == "GMT"
    assert retry["timeout"].total == 30
    assert retry["headers"]["Authorization"] == "Bearer tok-new"
