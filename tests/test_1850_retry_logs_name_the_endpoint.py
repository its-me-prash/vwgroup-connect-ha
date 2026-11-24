# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1850 — the 429 and 5xx debug lines name the call they are about.

@indigomejor caught a 430 lockout on 5.5.0 with debug on. Two 429s arrived
0.14 s apart in one poll, and the lines read only "Rate limited (429) —
retrying in 5s", so the log could not say which call each one came from. The
lockout warning already names host and path since #1850; the retry lines now
do the same, through the same ``_redact_url``: query dropped, VIN and UUID
path segments masked.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest

_VIN = "WVWZZZAUZFW000000"
_STATUS = (
    "https://mysmob.api.connect.skoda-auto.cz/api/v2/vehicle-status/"
    f"{_VIN}?token=SECRETTOKEN"
)
_MASKED = "mysmob.api.connect.skoda-auto.cz/api/v2/vehicle-status/<vin>"


class _Resp:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        self.headers.update(headers or {})

    async def text(self, **_kw: Any) -> str:
        return "error body"

    async def json(self, **_kw: Any) -> Any:
        return {"ok": True}

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    """Answers from a script of responses, then 200."""

    def __init__(self, *responses: _Resp) -> None:
        self.responses = list(responses)

    def request(self, method: str, url: str, **_kw: Any) -> _Resp:
        return self.responses.pop(0) if self.responses else _Resp(200)


def _client(session: _Session) -> Any:
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient(session, "u@t.invalid", "pw")  # type: ignore[arg-type]
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok")  # type: ignore[assignment]
    return c


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    from custom_components.vag_connect.cariad.api import base

    async def _fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)


def _log_of(session: _Session, caplog: pytest.LogCaptureFixture) -> str:
    c = _client(session)
    with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect"):
        try:
            asyncio.new_event_loop().run_until_complete(c._request("GET", _STATUS))
        except Exception:  # noqa: BLE001 - only the log is under test
            pass
    return caplog.text


def _assert_masked(text: str) -> None:
    assert _VIN not in text, "the VIN reached the log"
    assert "SECRETTOKEN" not in text, "the query reached the log"


def test_a_retried_429_names_the_call(caplog: pytest.LogCaptureFixture) -> None:
    text = _log_of(_Session(_Resp(429), _Resp(200)), caplog)
    assert f"Rate limited (429) from {_MASKED} — retrying in 5s" in text
    _assert_masked(text)


def test_a_429_with_retry_after_names_the_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = _log_of(_Session(_Resp(429, {"Retry-After": "120"})), caplog)
    assert f"Rate limited (429) from {_MASKED} with Retry-After 120s" in text
    _assert_masked(text)


def test_a_retried_5xx_names_the_call(caplog: pytest.LogCaptureFixture) -> None:
    text = _log_of(_Session(_Resp(500), _Resp(200)), caplog)
    assert f"Server error 500 from {_MASKED} — retrying in 3s" in text
    _assert_masked(text)
