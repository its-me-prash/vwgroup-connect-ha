# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2077 (@matroeh) — a caller's ``timeout`` must override, not collide.

``get_charging_statistics`` passed ``timeout=ClientTimeout(total=30)`` into
``_request``, and ``_request`` also passed its own ``timeout=`` alongside
``**kwargs`` to the session call. That raised ``TypeError`` (multiple values
for 'timeout') before any request went out, and the method's broad ``except``
swallowed it into ``{}`` — so every charging-statistics sensor silently
disappeared. ``_request`` now pops ``timeout`` from kwargs the way it already
pops ``headers``, so a caller's value overrides the default instead of
colliding.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from aiohttp import ClientTimeout

from custom_components.vag_connect.cariad.api.base import _REQUEST_TIMEOUT


class _Resp:
    def __init__(self) -> None:
        self.status = 200
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    async def json(self, **_k: Any) -> Any:
        return {"ok": True}

    async def text(self, **_k: Any) -> str:
        return ""

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_e: Any) -> None:
        return None


class _Session:
    """Records the ``timeout`` kwarg each ``request()`` actually receives."""

    def __init__(self) -> None:
        self.timeouts: list[Any] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:
        self.timeouts.append(kwargs.get("timeout"))
        return _Resp()


def _client(session: _Session) -> Any:
    # Škoda, not volkswagen, so _request's device-grant re-mint branch can't
    # fire and no auth runs in the test (same reason as test_1973).
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient(session, "u@t.invalid", "pw")  # type: ignore[arg-type]
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok")  # type: ignore[assignment]
    return c


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def test_a_caller_timeout_no_longer_raises_and_overrides() -> None:
    s = _Session()
    c = _client(s)
    caller = ClientTimeout(total=30)
    # Before the fix this raised TypeError (multiple values for 'timeout').
    _run(
        c._request(
            "POST", "https://x.invalid/charging_statistics", json={"a": 1},
            timeout=caller,
        )
    )
    assert s.timeouts == [caller], (
        "the caller's timeout must reach session.request and override the "
        "default — the collision/swallow is the #2077 bug"
    )


def test_the_default_timeout_is_used_when_the_caller_passes_none() -> None:
    s = _Session()
    c = _client(s)
    _run(c._request("GET", "https://x.invalid/thing"))
    assert len(s.timeouts) == 1
    t = s.timeouts[0]
    assert isinstance(t, ClientTimeout) and t.total == _REQUEST_TIMEOUT, (
        "with no caller timeout the default must still be applied"
    )


def test_get_charging_statistics_completes_instead_of_swallowing_to_empty() -> None:
    """End to end: the method that triggered #2077 now reaches the backend and
    returns the response, instead of the TypeError being swallowed into {}."""
    s = _Session()
    c = _client(s)
    out = _run(c.get_charging_statistics("WVWZZZAUZFW000000"))
    assert out == {"ok": True}, "a healthy charging-statistics response is dropped"
    # and it really did carry the method's own 30 s timeout through
    assert s.timeouts and isinstance(s.timeouts[0], ClientTimeout)
    assert s.timeouts[0].total == 30
