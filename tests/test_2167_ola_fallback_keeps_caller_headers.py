# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2167 — the SEAT/CUPRA 403 fallback keeps the caller's headers.

@matroeh showed that the OLA 403 fallback (retry with the next app-header
set) went out without the caller's own headers: ``SeatCupraClient._request``
popped them, merged in the app headers, and the fallback recursed with
``**kwargs`` only. A lock or unlock carries its ``SecToken`` that way, so the
fallback attempt lost it. He also pointed out the trap in the obvious fix:
forwarding the already merged dict would keep the previous app version,
because the merge lets existing keys win.

Pinned here: the fallback sends the caller's headers AND the fallback app
version; the first attempt still lets a caller header win over the app set;
the fallback is still keyed on a 403 from the OLA host only; and a server
error retried by the shared path (#2159) keeps the app headers of the attempt
it repeats instead of walking the fallback chain.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

_OLA = "https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/X/access/lock"


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    async def text(self, **_kw: Any) -> str:
        return "Forbidden" if self.status == 403 else "error"

    async def json(self, **_kw: Any) -> Any:
        return {"ok": True}

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    def __init__(self, script: list[int]) -> None:
        self.script = list(script)
        self.sent: list[dict[str, str]] = []

    def request(self, method: str, url: str, **kw: Any) -> _Resp:
        self.sent.append(dict(kw.get("headers") or {}))
        return _Resp(self.script.pop(0))


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    from custom_components.vag_connect.cariad.api import base

    async def _fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)


def _client(brand: str, session: _Session) -> Any:
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    c = SeatCupraClient(MagicMock(), brand, "u@t.invalid", "pw")
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok")  # type: ignore[assignment]
    return c


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.mark.parametrize("brand", ["seat", "cupra"])
def test_the_403_fallback_sends_the_sectoken_and_the_fallback_version(brand: str) -> None:
    from custom_components.vag_connect.cariad._ola_headers import get_ola_headers

    session = _Session([403, 200])
    c = _client(brand, session)

    result = _run(c._request("POST", _OLA, headers={"SecToken": "sec-123"}, json={}))

    assert result == {"ok": True}
    assert len(session.sent) == 2
    first, fallback = session.sent
    assert first.get("SecToken") == "sec-123"
    assert first.get("app-version") == get_ola_headers(brand)["app-version"]
    assert fallback.get("SecToken") == "sec-123", fallback
    assert fallback.get("app-version") == get_ola_headers(brand, fallback_index=0)["app-version"]


@pytest.mark.parametrize("brand", ["seat", "cupra"])
def test_the_callers_dict_is_not_written_into(brand: str) -> None:
    session = _Session([403, 200])
    c = _client(brand, session)
    headers = {"SecToken": "sec-123"}

    _run(c._request("POST", _OLA, headers=headers, json={}))

    assert headers == {"SecToken": "sec-123"}


def test_a_caller_header_still_wins_on_the_first_attempt() -> None:
    session = _Session([200])
    c = _client("seat", session)

    _run(c._request("GET", _OLA, headers={"app-version": "9.9.9"}))

    assert session.sent[0]["app-version"] == "9.9.9"


def test_a_403_from_another_host_is_not_retried_with_the_fallback_set() -> None:
    from custom_components.vag_connect.cariad.exceptions import APIError

    session = _Session([403])
    c = _client("seat", session)

    with pytest.raises(APIError):
        _run(c._request("GET", "https://example.invalid/x", headers={"SecToken": "s"}))
    assert len(session.sent) == 1


def test_a_server_error_retry_keeps_the_app_set_of_the_attempt_it_repeats() -> None:
    """500 on the first attempt, 403 on its retry, then the fallback: the
    retry repeats the primary set, the fallback after the 403 sends the
    fallback set, and the SecToken rides along on all three."""
    from custom_components.vag_connect.cariad._ola_headers import get_ola_headers

    session = _Session([500, 403, 200])
    c = _client("seat", session)

    result = _run(c._request("POST", _OLA, headers={"SecToken": "sec-123"}, json={}))

    assert result == {"ok": True}
    versions = [h.get("app-version") for h in session.sent]
    assert versions == [
        get_ola_headers("seat")["app-version"],
        get_ola_headers("seat")["app-version"],
        get_ola_headers("seat", fallback_index=0)["app-version"],
    ]
    assert all(h.get("SecToken") == "sec-123" for h in session.sent)
