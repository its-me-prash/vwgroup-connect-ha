# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A failure the log cannot describe is a failure nobody can diagnose.

@georghaberkorn68-ctrl (#1866) attached a twelve-minute debug log from a CUPRA
entry and the only trace of the failure in it was one sentence: *Could not
fetch SEAT/CUPRA user ID*. A 401, a 403, a timeout and a malformed body all
came out identical, and the question put to him — 401 or 403? — could not be
answered from any log the code was able to produce.

**v3.0.2 reconciliation (APK audit 2026-11-18, #1867).** The code that #1866
instrumented was a fallback HTTP call to ``GET /v1/users``. The mySEAT/myCUPRA
3.0.2 APK has **no such endpoint** — it does not exist on OLA and always
answered 404, which is exactly the "Could not fetch SEAT/CUPRA user ID:
APIError (HTTP 404)" line in #1867's log. The user id is derived solely from
the id_token ``sub`` claim (the ``User-ID`` header the app sends). So the dead
fallback was removed: there is no longer an HTTP call here to name a status
for. ``_fetch_user_id`` now only parses the JWT, and the thing that must stay
legible — and must never leak — is the JWT-parse failure and the no-``sub``
case. These tests pin that: the exception **class** is named, and a VIN or a
token never reaches the log. The removed HTTP-status-naming parametrisation is
gone with the endpoint it described.
"""
from __future__ import annotations

import logging

import pytest


class _Boom:
    """Minimal stand-in exercising ``_fetch_user_id`` with a given id_token."""

    def __init__(self, id_token: str | None) -> None:
        if id_token is None:
            self._tokens = None
        else:
            self._tokens = type("_Tok", (), {"id_token": id_token})()
        self._user_id: str | None = None
        self._access_token = ""


async def _run(id_token: str | None) -> _Boom:
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    obj = _Boom(id_token)
    await SeatCupraClient._fetch_user_id(obj)  # type: ignore[arg-type]
    return obj


_SECRET_VIN = "WVWZZZ1KZAW123456"
# a syntactically-JWT token whose payload segment is a secret-bearing blob
_SECRET_PAYLOAD = "eyJhY2Nlc3NfdG9rZW4iOiJ2ZXJ5c2VjcmV0In0"  # {"access_token":"verysecret"}


@pytest.mark.asyncio
async def test_malformed_jwt_names_its_class_and_no_http(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A token that is not a decodable JWT: the parse error's class is named,
    and — since there is no HTTP call any more — nothing says "HTTP"."""
    caplog.set_level(logging.WARNING)
    await _run("not.a.jwt")
    msgs = [r.getMessage() for r in caplog.records]
    assert any("id_token" in m for m in msgs), msgs
    # a class name is present (e.g. JSONDecodeError / ValueError / Error)
    assert any("Error" in m for m in msgs), msgs
    assert not any("HTTP" in m for m in msgs), msgs


@pytest.mark.asyncio
async def test_missing_sub_is_reported_clearly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A well-formed id_token without a ``sub`` claim: a clear message, no
    invented HTTP status, no secret."""
    import base64
    import json

    caplog.set_level(logging.WARNING)
    payload = base64.urlsafe_b64encode(json.dumps({"email": "u@t.de"}).encode()).rstrip(b"=").decode()
    await _run(f"eyJhbGciOiJSUzI1NiJ9.{payload}.sig")
    msgs = [r.getMessage() for r in caplog.records]
    assert any("user ID" in m for m in msgs), msgs
    assert not any("HTTP" in m for m in msgs), msgs


@pytest.mark.asyncio
async def test_no_token_is_reported_clearly(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    obj = await _run(None)
    assert obj._user_id is None
    assert any("user ID" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_neither_the_payload_nor_a_secret_reaches_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reason this line stays narrow: the only thing logged is the
    exception class or a static sentence — never the token payload or a VIN."""
    caplog.set_level(logging.DEBUG)
    await _run(f"eyJhbGciOiJSUzI1NiJ9.{_SECRET_PAYLOAD}.{_SECRET_VIN}")
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert _SECRET_VIN not in blob
    assert _SECRET_PAYLOAD not in blob
    assert "verysecret" not in blob


@pytest.mark.asyncio
async def test_the_failure_is_still_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    """The user id is optional — a missing one must not sink the login."""
    caplog.set_level(logging.WARNING)
    obj = await _run("not.a.jwt")
    assert obj._user_id is None
