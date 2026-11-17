# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2165 — one exhausted official API key no longer silences the others.

The official Škoda API budget is 20 requests per hour PER KEY, and one
``SkodaOfficialClient`` carries the keys of several VINs (``keys_by_vin``).
@matroeh showed that the self-block lived in shared attributes: once key A's
response said ``RateLimit-Remaining: 0``, the read for VIN B (key B) returned
``None`` without sending anything. The block, the remaining count and the
reset window are now kept per key, and the read and command paths ask for
their own VIN's key. Two real clients and a recording session; only the HTTP
layer is simulated.
"""
from __future__ import annotations

import asyncio
from typing import Any

_VIN_A = "TMBAAAAAAAAAAAAA1"
_VIN_B = "TMBBBBBBBBBBBBBB2"


class _Resp:
    def __init__(self, status: int, headers: dict[str, str]) -> None:
        self.status = status
        self.headers = headers

    async def json(self, **_kw: Any) -> Any:
        return {"vehicle": {"name": "Enyaq"}} if self.status == 200 else {"title": "x"}

    async def text(self, **_kw: Any) -> str:
        return "x"

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    """Answers per API key from a script; records which key each request used."""

    def __init__(self, by_key: dict[str, tuple[int, dict[str, str]]]) -> None:
        self.by_key = by_key
        self.keys: list[str] = []

    def request(self, method: str, url: str, **kw: Any) -> _Resp:
        key = (kw.get("headers") or {}).get("X-API-Key", "")
        self.keys.append(key)
        status, headers = self.by_key[key]
        return _Resp(status, dict(headers))


def _client(session: _Session) -> Any:
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient(session, "u@t.invalid", "pw")  # type: ignore[arg-type]
    c._session = session  # type: ignore[assignment]
    c.arm_supplementary_official(keys_by_vin={_VIN_A: "key-a", _VIN_B: "key-b"})
    return c


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def test_an_exhausted_key_does_not_block_another_vins_read() -> None:
    session = _Session({
        "key-a": (200, {"RateLimit-Remaining": "0", "RateLimit-Reset": "3600"}),
        "key-b": (200, {"RateLimit-Remaining": "19", "RateLimit-Reset": "3600"}),
    })
    c = _client(session)

    assert _run(c.official_live_read(_VIN_A)) is not None
    assert _run(c.official_live_read(_VIN_B)) is not None, "key B was never tried"
    assert session.keys == ["key-a", "key-b"]

    # A stays blocked for its own window: a second read of A sends nothing.
    assert _run(c.official_live_read(_VIN_A)) is None
    assert session.keys == ["key-a", "key-b"]
    off = c._supplementary_official
    assert off.over_rate_limit_for(_VIN_A) is True
    assert off.over_rate_limit_for(_VIN_B) is False


def test_a_429_on_one_key_does_not_block_another() -> None:
    session = _Session({
        "key-a": (429, {"Retry-After": "600"}),
        "key-b": (200, {}),
    })
    c = _client(session)

    assert _run(c.official_live_read(_VIN_A)) is None
    assert _run(c.official_live_read(_VIN_B)) is not None
    assert session.keys == ["key-a", "key-b"]


def test_the_command_reserve_counts_this_vins_key() -> None:
    """The command fallback keeps headroom for the reads per key: A's last
    request left it 2, B's left it 18."""
    session = _Session({
        "key-a": (200, {"RateLimit-Remaining": "2", "RateLimit-Reset": "3600"}),
        "key-b": (200, {"RateLimit-Remaining": "18", "RateLimit-Reset": "3600"}),
    })
    c = _client(session)
    _run(c.official_live_read(_VIN_B))
    _run(c.official_live_read(_VIN_A))

    assert c.official_command_connector(_VIN_A) is None
    assert c.official_command_connector(_VIN_B) is c._supplementary_official
