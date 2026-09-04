# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.12.4 (#438) — token-refresh transient 5xx must not be an auth failure.

During the VW-side EU Data Act / CARIAD outage the token endpoint returns
502/503 on otherwise-valid refresh tokens. Treating that as
``AuthenticationError`` wrongly triggered the Home Assistant reauth flow and
spammed Error-Reporter issues (#435–#439) for a server-side blip.

``refresh()`` now raises ``UpstreamUnavailableError`` (a non-auth transient
the coordinator tolerates) on 5xx. A 400 still means a genuinely rejected
refresh token (→ full re-login).

b10 update: a **401** on the refresh endpoint is ``invalid_client`` (RFC 6749
§5.2) — a transient client-auth wobble on the shared identity.vwgroup.io IDP,
NOT a dead user grant (which is the 400 above). audi_connect saw exactly this
recurring "late-August VW token wobble" (#835/#840/#843) where a hard reauth was
a misclassification, and our own device-grant + MBB refresh paths already treat
invalid_client as retryable — so the IDK/mysmob path now raises
``TokenRefreshRetryError`` on 401 too, and it self-heals next poll (a persistent
401 still reaches reauth via the storm guard). A **403** (and any other non-200)
still raises ``AuthenticationError`` — only 401 is the evidenced-transient case.
"""

from __future__ import annotations

import types

import pytest

from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    TokenExpiredError,
    TokenRefreshRetryError,
    UpstreamUnavailableError,
)


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False

    async def json(self) -> dict:
        return {}


class _Session:
    """Minimal aiohttp-ish session: every POST returns the canned status."""

    def __init__(self, status: int) -> None:
        self._status = status

    def post(self, *_a: object, **_kw: object) -> _Resp:
        return _Resp(self._status)


def _brand(name: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        name=name,
        client_id="cid",
        client_secret="",
        user_agent="ua/1.0",
        android_package_name="de.test.app",
    )


def _auth(name: str, status: int) -> IDKAuth:
    """Build an IDKAuth without running __init__; refresh() raises on the
    canned status before it touches anything else."""
    a = IDKAuth.__new__(IDKAuth)
    a._brand = _brand(name)  # type: ignore[attr-defined]
    a._session = _Session(status)  # type: ignore[assignment]
    a._get_token_endpoint = lambda: "https://token.example/oidc/token"  # type: ignore[method-assign]
    return a


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_cariad_refresh_5xx_is_upstream_unavailable(status: int) -> None:
    """A 5xx on the CARIAD token endpoint → UpstreamUnavailableError, not auth."""
    with pytest.raises(UpstreamUnavailableError):
        await _auth("volkswagen", status).refresh("rt")


@pytest.mark.asyncio
async def test_cariad_refresh_400_is_token_expired() -> None:
    """400 still means the refresh token is genuinely rejected (full re-login)."""
    with pytest.raises(TokenExpiredError):
        await _auth("volkswagen", 400).refresh("rt")


@pytest.mark.asyncio
async def test_cariad_refresh_401_is_retryable() -> None:
    """b10 — 401 invalid_client is a transient wobble, not a hard auth failure.

    Must be a ``TokenRefreshRetryError`` (sibling of AuthenticationError) so the
    coordinator self-heals next poll instead of hard-bouncing into reauth.
    """
    with pytest.raises(TokenRefreshRetryError):
        await _auth("volkswagen", 401).refresh("rt")


@pytest.mark.asyncio
async def test_cariad_refresh_403_still_raises_auth() -> None:
    """403 (and any other non-200) stays a genuine auth failure — only 401 flips."""
    with pytest.raises(AuthenticationError):
        await _auth("volkswagen", 403).refresh("rt")


@pytest.mark.asyncio
async def test_skoda_refresh_5xx_is_upstream_unavailable() -> None:
    """Škoda's proprietary refresh endpoint gets the same transient treatment."""
    with pytest.raises(UpstreamUnavailableError):
        await _auth("skoda", 503).refresh("rt")


@pytest.mark.asyncio
async def test_skoda_refresh_400_is_token_expired() -> None:
    with pytest.raises(TokenExpiredError):
        await _auth("skoda", 400).refresh("rt")


@pytest.mark.asyncio
async def test_skoda_refresh_401_is_retryable() -> None:
    """b10 — same 401→transient classification on the mysmob refresh endpoint."""
    with pytest.raises(TokenRefreshRetryError):
        await _auth("skoda", 401).refresh("rt")
