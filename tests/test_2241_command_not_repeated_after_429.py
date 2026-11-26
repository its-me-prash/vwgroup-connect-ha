# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2241 — a command is not sent again after a 429.

Reported by @driemeier for Škoda remote commands. On a 429 without
``Retry-After`` the shared ``base._request`` sent the same request again after
5, 10 and 20 s, so one press could reach the backend four times, and four
refusals then paused every request of the account, reads included, for
30 minutes.

Now a call with a write method (``_WRITE_METHODS``) raises the 429 at once:
one request, no sleep, no account pause. Reads keep the repeats and the pause
after four refusals; ``repeat_on_429=True`` keeps them for a POST that only
reads (Škoda charging statistics), and ``repeat_on_429=False`` sends a read
once (Škoda warning lights, see ``test_2241_skoda_warning_lights_every_6h``).
A ``Retry-After`` and the 5xx repeats are unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from aiohttp import ServerDisconnectedError

from custom_components.vag_connect.cariad.api import base
from custom_components.vag_connect.cariad.exceptions import APIError

_URL = "https://mysmob.api.connect.skoda-auto.cz/api/v2/vehicle-access/TMBZZZ00000000000/honk-and-flash"
_READ_URL = "https://mysmob.api.connect.skoda-auto.cz/api/v2/vehicle-status/TMBZZZ00000000000"


class _Resp:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers: dict[str, str] = {"Content-Type": "application/json", **(headers or {})}

    async def text(self, **_kw: Any) -> str:
        return "error body"

    async def json(self, **_kw: Any) -> Any:
        return {"ok": True}

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    """Answers from a script; records method and URL of every send.

    A script entry is a status, or ``(status, headers)``.
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.sent: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_kw: Any) -> _Resp:
        self.sent.append((method, url))
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, tuple):
            return _Resp(step[0], step[1])
        return _Resp(step)


def _client(session: _Session) -> Any:
    """A Škoda client: not ``volkswagen``, so the proactive VW-EU re-mint in
    ``_request`` cannot fire. The refresh only swaps the token."""
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


# ── commands ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post"])
def test_a_command_429_goes_out_once_and_is_raised(method: str, sleeps: list[float]) -> None:
    session = _Session([429, 200, 200, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c._request(method, _URL, json={}))

    assert exc.value.status == 429
    assert len(session.sent) == 1
    assert sleeps == []


def test_a_command_429_does_not_pause_the_account(sleeps: list[float]) -> None:
    """The reads that still work keep working: no account lockout is armed,
    and the next GET goes out to the server instead of being refused here."""
    session = _Session([429, 200])
    c = _client(session)

    with pytest.raises(APIError):
        _run(c._post(_URL, json={}))

    assert c._rate_limit_locked_until is None
    assert c._rate_lockout_remaining() == 0
    assert _run(c._get(_READ_URL)) == {"ok": True}
    assert session.sent == [("POST", _URL), ("GET", _READ_URL)]


def test_a_second_press_sends_one_more_request(sleeps: list[float]) -> None:
    """One press is one request, also the next time: nothing is held locally."""
    session = _Session([429, 429])
    c = _client(session)

    for _ in range(2):
        with pytest.raises(APIError) as exc:
            _run(c._post(_URL, json={}))
        assert exc.value.status == 429

    assert len(session.sent) == 2
    assert sleeps == []


def test_the_command_429_is_logged_with_the_masked_endpoint(
    sleeps: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    session = _Session([429])
    c = _client(session)

    with caplog.at_level(logging.DEBUG, logger=base._LOGGER.name):
        with pytest.raises(APIError):
            _run(c._post(_URL, json={}))

    lines = [r.getMessage() for r in caplog.records]
    hit = [line for line in lines if line.startswith("Rate limited (429) from")]
    assert len(hit) == 1, lines
    assert "not sending it again" in hit[0]
    assert "TMBZZZ00000000000" not in hit[0]
    assert not any("Account rate-limit lockout" in line for line in lines), lines


def test_a_command_after_a_401_refresh_is_still_a_command(sleeps: list[float]) -> None:
    session = _Session([401, 429, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c._post(_URL, json={}))

    assert exc.value.status == 429
    assert len(session.sent) == 2


def test_a_command_429_after_a_5xx_repeat_is_not_repeated(sleeps: list[float]) -> None:
    """The 5xx repeats of a command are not part of this change; a 429 on the
    repeat is raised like one on the first attempt."""
    session = _Session([500, 429, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c._post(_URL, json={}))

    assert exc.value.status == 429
    assert len(session.sent) == 2
    assert sleeps == [3]


def test_a_command_429_with_retry_after_still_pauses_the_account(sleeps: list[float]) -> None:
    session = _Session([(429, {"Retry-After": "120"}), 200])
    c = _client(session)

    with pytest.raises(APIError):
        _run(c._post(_URL, json={}))

    assert len(session.sent) == 1
    assert 100 < c._rate_lockout_remaining() <= 120
    with pytest.raises(APIError) as exc:
        _run(c._get(_READ_URL))
    assert "lockout active" in exc.value.body
    assert len(session.sent) == 1


# ── reads ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_a_read_429_keeps_its_repeats_and_the_pause(method: str, sleeps: list[float]) -> None:
    session = _Session([429, 429, 429, 429])
    c = _client(session)

    with pytest.raises(APIError):
        _run(c._request(method, _READ_URL))

    assert len(session.sent) == 4
    assert sleeps == [5, 10, 20]
    assert c._rate_lockout_remaining() > base._LOCKOUT_429_S - 60


def test_a_read_429_that_clears_returns_the_data(sleeps: list[float]) -> None:
    session = _Session([429, 200])
    c = _client(session)

    assert _run(c._get(_READ_URL)) == {"ok": True}
    assert len(session.sent) == 2


def test_a_post_marked_read_keeps_the_repeats(sleeps: list[float]) -> None:
    session = _Session([429, 429, 200])
    c = _client(session)

    assert _run(c._request("POST", _READ_URL, json={}, repeat_on_429=True)) == {"ok": True}
    assert len(session.sent) == 3
    assert sleeps == [5, 10]


@pytest.mark.parametrize(
    "first",
    [
        pytest.param(401, id="after-401"),
        pytest.param(500, id="after-5xx"),
        pytest.param(ServerDisconnectedError(), id="after-network-error"),
    ],
)
def test_the_read_mark_survives_the_other_repeat_paths(first: Any, sleeps: list[float]) -> None:
    session = _Session([first, 429, 200])
    c = _client(session)

    assert _run(c._request("POST", _READ_URL, json={}, repeat_on_429=True)) == {"ok": True}
    assert len(session.sent) == 3


def test_the_read_mark_is_not_sent_to_the_server(sleeps: list[float]) -> None:
    seen: list[dict[str, Any]] = []

    class _Recording(_Session):
        def request(self, method: str, url: str, **kw: Any) -> _Resp:
            seen.append(kw)
            return super().request(method, url, **kw)

    c = _client(_Recording([200]))
    _run(c._request("POST", _READ_URL, json={}, repeat_on_429=True))

    assert "repeat_on_429" not in seen[0]


def test_a_read_marked_send_once_goes_out_once_and_does_not_pause(
    sleeps: list[float],
) -> None:
    session = _Session([429, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c._request("GET", _READ_URL, repeat_on_429=False))

    assert exc.value.status == 429
    assert sleeps == []
    assert c._rate_lockout_remaining() == 0
    assert _run(c._get(_READ_URL)) == {"ok": True}
    assert len(session.sent) == 2


def test_a_write_marked_send_once_is_still_sent_once(sleeps: list[float]) -> None:
    session = _Session([429, 200])
    c = _client(session)

    with pytest.raises(APIError):
        _run(c._request("POST", _URL, json={}, repeat_on_429=False))

    assert len(session.sent) == 1


# ── the real callers ──────────────────────────────────────────────────────


def test_the_reported_sequence_warning_lights_429_then_flash(sleeps: list[float]) -> None:
    """@driemeier's log: warning-lights 429 at start-up, flash a minute later.
    The read is sent once and starts no pause, so the flash reaches Škoda."""
    session = _Session([429, 200])
    c = _client(session)

    assert _run(c.get_warning_lights("TMBZZZ00000000000")) is None
    _run(c.command_flash("TMBZZZ00000000000", latitude=1.0, longitude=2.0))

    assert [m for m, _ in session.sent] == ["GET", "POST"]
    assert "/warning-lights/" in session.sent[0][1]
    assert session.sent[1][1].endswith("/honk-and-flash")
    assert sleeps == []
    assert c._rate_lockout_remaining() == 0


def test_skoda_flash_from_the_report_goes_out_once(sleeps: list[float]) -> None:
    session = _Session([429, 200, 200, 200])
    c = _client(session)

    with pytest.raises(APIError) as exc:
        _run(c.command_flash("TMBZZZ00000000000", latitude=1.0, longitude=2.0))

    assert exc.value.status == 429
    assert len(session.sent) == 1
    assert session.sent[0][0] == "POST"
    assert session.sent[0][1].endswith("/honk-and-flash")


def test_skoda_charging_statistics_still_repeats_a_429(sleeps: list[float]) -> None:
    """The one periodic read on this path that is a POST."""
    session = _Session([429, 200])
    c = _client(session)

    assert _run(c.get_charging_statistics("TMBZZZ00000000000")) == {"ok": True}
    assert len(session.sent) == 2
    assert session.sent[0][0] == "POST"


@pytest.mark.parametrize("brand", ["seat", "cupra"])
def test_seat_cupra_command_through_its_own_request_goes_out_once(
    brand: str, sleeps: list[float]
) -> None:
    """SEAT/CUPRA wrap the shared ``_request`` with their own; a command 429
    must not be repeated there either."""
    from unittest.mock import MagicMock

    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    session = _Session([429, 200, 200, 200])
    c = SeatCupraClient(MagicMock(), brand, "u@t.invalid", "pw")
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok-old")  # type: ignore[assignment]

    with pytest.raises(APIError) as exc:
        _run(c._post("https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/X/honk-and-flash", json={}))

    assert exc.value.status == 429
    assert len(session.sent) == 1
