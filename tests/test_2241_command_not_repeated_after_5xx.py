# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2241 follow-up — a command is not sent again after a 5xx or a broken connection.

The shared ``base._request`` sent every request again after 3, 6 and 12 s on
HTTP 500/502/503/504 and on a transient network error, commands included. The
backend accepts a command and runs it on the car later, so a 5xx, a timeout, a
dropped connection or a broken answer does not show whether the first send
already reached the car, and the repeat could flash, honk or wake it a second
time. A failed connect could not have reached it, but its repeat would run the
command up to 21 s after the press, possibly next to a second press.

A call that is sent once (``send_once``, by default every ``_WRITE_METHODS``
call) now raises at once on all of these. Reads keep their repeats, a
write-method call marked as a read (``send_once=False``) does too, and the 401
refresh with its one retry is unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import pytest
from aiohttp import ClientConnectorError, ClientPayloadError, ServerDisconnectedError

from custom_components.vag_connect.cariad.api import base
from custom_components.vag_connect.cariad.exceptions import APIError

_VIN = "TMBZZZ00000000000"
_URL = f"https://mysmob.api.connect.skoda-auto.cz/api/v2/vehicle-access/{_VIN}/honk-and-flash"
_READ_URL = f"https://mysmob.api.connect.skoda-auto.cz/api/v2/vehicle-status/{_VIN}"


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
    """Answers from a script (a status, or an exception raised at send time)."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.sent: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_kw: Any) -> _Resp:
        self.sent.append((method, url))
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return _Resp(step)


def _client(session: _Session) -> Any:
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient(session, "u@t.invalid", "pw")  # type: ignore[arg-type]
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok-old")  # type: ignore[assignment]

    async def _refresh(**_kw: Any) -> None:
        c._tokens = SimpleNamespace(access_token="tok-new")

    c._refresh_tokens = _refresh  # type: ignore[method-assign]
    return c


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)
    return waited


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _net_errors() -> list[Any]:
    return [
        pytest.param(ClientConnectorError(MagicMock(), OSError(111, "refused")), id="connect"),
        pytest.param(aiohttp.ConnectionTimeoutError("connect timeout"), id="connect-timeout"),
        pytest.param(ServerDisconnectedError(), id="disconnected"),
        pytest.param(ClientPayloadError("broken"), id="payload"),
        pytest.param(asyncio.TimeoutError(), id="timeout"),
    ]


# ── commands: sent once ───────────────────────────────────────────────────


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_command_5xx_goes_out_once_and_is_raised(
    method: str, status: int, sleeps: list[float]
) -> None:
    session = _Session([status, 200, 200, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c._request(method, _URL, json={}))

    assert exc.value.status == status
    assert len(session.sent) == 1
    assert sleeps == []


@pytest.mark.parametrize("error", _net_errors())
def test_a_command_network_error_goes_out_once(error: Exception, sleeps: list[float]) -> None:
    session = _Session([error, 200, 200, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c._post(_URL, json={}))

    assert exc.value.status == 0
    assert type(error).__name__ in exc.value.body
    assert len(session.sent) == 1
    assert sleeps == []


def test_a_command_5xx_leaves_the_retry_budget_memory_alone(sleeps: list[float]) -> None:
    """#1973 counts URLs that spent their whole 5xx budget; a command that is
    sent once never spends one, so it must not be marked."""
    session = _Session([503, 503, 503])
    c = _client(session)

    for _ in range(3):
        with pytest.raises(APIError):
            _run(c._post(_URL, json={}))

    assert len(session.sent) == 3
    assert c._5xx_memory() == {}
    assert c._rate_lockout_remaining() == 0


def test_a_command_after_a_401_refresh_gets_its_one_retry_then_no_more(
    sleeps: list[float],
) -> None:
    session = _Session([401, 500, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c._post(_URL, json={}))

    assert exc.value.status == 500
    assert len(session.sent) == 2
    assert sleeps == []


def test_the_5xx_on_a_command_is_logged(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    session = _Session([502])
    c = _client(session)

    with caplog.at_level(logging.DEBUG, logger=base._LOGGER.name):
        with pytest.raises(APIError):
            _run(c._post(_URL, json={}))

    lines = [r.getMessage() for r in caplog.records]
    hit = [line for line in lines if line.startswith("Server error 502 from")]
    assert len(hit) == 1, lines
    assert "on a POST — not sending it again" in hit[0]
    assert _VIN not in hit[0]
    assert not any("retrying in" in line for line in lines), lines


def test_the_network_error_on_a_command_is_logged(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    session = _Session([ServerDisconnectedError()])
    c = _client(session)

    with caplog.at_level(logging.DEBUG, logger=base._LOGGER.name):
        with pytest.raises(APIError):
            _run(c._post(_URL, json={}))

    lines = [r.getMessage() for r in caplog.records]
    assert any(
        "Transient network error (ServerDisconnectedError) on a POST — not sending it again" in line
        for line in lines
    ), lines


def test_a_send_once_read_is_sent_once_on_a_5xx_too(sleeps: list[float]) -> None:
    session = _Session([500, 200])
    c = _client(session)

    with pytest.raises(APIError):
        _run(c._request("GET", _READ_URL, send_once=True))

    assert len(session.sent) == 1


# ── reads: repeats kept ───────────────────────────────────────────────────


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_read_5xx_keeps_its_repeats(status: int, sleeps: list[float]) -> None:
    session = _Session([status, status, 200])
    c = _client(session)

    assert _run(c._get(_READ_URL)) == {"ok": True}
    assert len(session.sent) == 3
    assert sleeps == [3, 6]


@pytest.mark.parametrize("error", _net_errors())
def test_a_read_network_error_keeps_its_repeats(error: Exception, sleeps: list[float]) -> None:
    session = _Session([error, 200])
    c = _client(session)

    assert _run(c._get(_READ_URL)) == {"ok": True}
    assert len(session.sent) == 2
    assert sleeps == [3]


@pytest.mark.parametrize(
    "fail", [503, ServerDisconnectedError()], ids=["5xx", "network"]
)
def test_a_read_keeps_all_three_repeats(fail: Any, sleeps: list[float]) -> None:
    session = _Session([fail, fail, fail, 200])
    c = _client(session)

    assert _run(c._get(_READ_URL)) == {"ok": True}
    assert len(session.sent) == 4
    assert sleeps == [3, 6, 12]


@pytest.mark.parametrize("first", [500, ServerDisconnectedError()], ids=["5xx", "network"])
def test_a_write_method_marked_read_keeps_its_repeats(first: Any, sleeps: list[float]) -> None:
    session = _Session([first, 200])
    c = _client(session)

    assert _run(c._request("POST", _READ_URL, json={}, send_once=False)) == {"ok": True}
    assert len(session.sent) == 2


# ── real callers ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("first", [503, ServerDisconnectedError()], ids=["5xx", "network"])
def test_skoda_flash_goes_out_once(first: Any, sleeps: list[float]) -> None:
    session = _Session([first, 200, 200, 200])
    c = _client(session)

    with pytest.raises(APIError):
        _run(c.command_flash(_VIN, latitude=1.0, longitude=2.0))

    assert len(session.sent) == 1


def test_skoda_charging_statistics_still_repeats_a_5xx(sleeps: list[float]) -> None:
    session = _Session([500, 200])
    c = _client(session)

    assert _run(c.get_charging_statistics(_VIN)) == {"ok": True}
    assert len(session.sent) == 2


def test_skoda_warning_lights_are_sent_once_on_a_5xx(sleeps: list[float]) -> None:
    session = _Session([500, 200])
    c = _client(session)

    assert _run(c.get_warning_lights(_VIN)) is None
    assert len(session.sent) == 1


@pytest.mark.parametrize("brand", ["seat", "cupra"])
def test_seat_cupra_command_5xx_through_its_own_request_goes_out_once(
    brand: str, sleeps: list[float]
) -> None:
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    session = _Session([503, 200, 200, 200])
    c = SeatCupraClient(MagicMock(), brand, "u@t.invalid", "pw")
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok-old")  # type: ignore[assignment]

    with pytest.raises(APIError) as exc:
        _run(c._post("https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/X/honk-and-flash", json={}))

    assert exc.value.status == 503
    assert len(session.sent) == 1
