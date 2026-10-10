# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One portal login at a time, and only one per burst.

A single ``EUDataActConnector`` serves every vehicle on an entry (built once in
``cariad/api/base.py``) while the coordinator reads the VINs concurrently, and
seven call sites across the brand clients re-login on a 401. Nothing serialised
them, so a three-car account could fire three simultaneous logins at the portal
for one identity.

This was not our discovery. Two live portal readers shipped the same fix within
two days of each other after meeting it in the field — which is the kind of
agreement worth taking seriously about someone else's infrastructure, and we are
mid-conversation with that operator about request volume.

The test that carries the most weight here is
``test_a_failure_is_not_retried_by_every_follower``: serialising alone would
turn one wrong password into seven sequential attempts, which is worse for the
user than the problem being fixed.
"""
from __future__ import annotations

import asyncio

from aiohttp import ServerDisconnectedError

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    UpstreamUnavailableError,
)


def _connector() -> EUDataActConnector:
    return EUDataActConnector(session=object(), brand="volkswagen")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_concurrent_callers_produce_exactly_one_login() -> None:
    c = _connector()
    calls: list[tuple[str, str]] = []
    started = asyncio.Event()

    async def _impl(email: str, password: str) -> None:
        calls.append((email, password))
        started.set()
        await asyncio.sleep(0.05)      # hold the window open

    c._login_impl = _impl  # type: ignore[method-assign]
    await asyncio.gather(*(c.login("a@b.c", "pw") for _ in range(7)))
    assert len(calls) == 1, f"one identity, one login — got {len(calls)}"


@pytest.mark.asyncio
async def test_logins_never_overlap() -> None:
    """Even if coalescing were removed, two must never run at once."""
    c = _connector()
    inside = 0
    peak = 0

    async def _impl(email: str, password: str) -> None:
        nonlocal inside, peak
        inside += 1
        peak = max(peak, inside)
        await asyncio.sleep(0.02)
        inside -= 1

    c._login_impl = _impl  # type: ignore[method-assign]
    await asyncio.gather(*(c.login("a@b.c", "pw") for _ in range(5)))
    assert peak == 1, f"logins overlapped (peak {peak})"


@pytest.mark.asyncio
async def test_a_later_call_logs_in_again() -> None:
    """Coalescing is scoped to the in-flight window, not cached. A poll an hour
    later must get a real login, or a dead session could never be replaced."""
    c = _connector()
    calls = 0

    async def _impl(email: str, password: str) -> None:
        nonlocal calls
        calls += 1

    c._login_impl = _impl  # type: ignore[method-assign]
    await c.login("a@b.c", "pw")
    await c.login("a@b.c", "pw")
    assert calls == 2


@pytest.mark.asyncio
async def test_a_failure_is_not_retried_by_every_follower() -> None:
    """The reason serialising alone is not enough.

    Seven queued callers behind one wrong password must not become seven
    sequential attempts — the identity provider is entitled to read that as an
    attack, and the user would be locked out by a fix.
    """
    c = _connector()
    attempts = 0

    async def _impl(email: str, password: str) -> None:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.02)
        raise AuthenticationError("portal rejected the credentials")

    c._login_impl = _impl  # type: ignore[method-assign]
    results = await asyncio.gather(
        *(c.login("a@b.c", "wrong") for _ in range(7)),
        return_exceptions=True,
    )
    assert attempts == 1, f"one attempt, not {attempts}"
    assert len(results) == 7
    assert all(isinstance(r, AuthenticationError) for r in results), (
        "every caller must still learn the login failed"
    )


@pytest.mark.asyncio
async def test_a_transient_is_still_mapped_for_every_caller() -> None:
    """The #576/#578 behaviour must survive the change: a connection failure is
    an upstream hiccup, not a credential verdict — for the followers too, or the
    coordinator would escalate one of them to reauth.

    Uses aiohttp's own ServerDisconnectedError, which is what the code
    catches (ClientConnectionError). A bare builtin ConnectionResetError
    is NOT mapped — true before this change as well, and deliberately left
    alone: widening the catch on a hunch is how a real auth failure gets
    reported as a portal outage."""
    c = _connector()

    async def _impl(email: str, password: str) -> None:
        await asyncio.sleep(0.02)
        raise ServerDisconnectedError("portal dropped it")

    c._login_impl = _impl  # type: ignore[method-assign]
    results = await asyncio.gather(
        *(c.login("a@b.c", "pw") for _ in range(4)),
        return_exceptions=True,
    )
    assert all(isinstance(r, UpstreamUnavailableError) for r in results), results
    assert not any(isinstance(r, AuthenticationError) for r in results)


@pytest.mark.asyncio
async def test_a_failed_burst_does_not_poison_the_next_one() -> None:
    """After the window closes, the next call tries again — otherwise a password
    corrected in the UI could never take effect without a restart."""
    c = _connector()
    attempts = 0

    async def _bad(email: str, password: str) -> None:
        nonlocal attempts
        attempts += 1
        raise AuthenticationError("portal rejected the credentials")

    c._login_impl = _bad  # type: ignore[method-assign]
    with pytest.raises(AuthenticationError):
        await c.login("a@b.c", "wrong")

    async def _good(email: str, password: str) -> None:
        nonlocal attempts
        attempts += 1

    c._login_impl = _good  # type: ignore[method-assign]
    await c.login("a@b.c", "right")
    assert attempts == 2
