# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1012: the sign-in's PKCE verifier has to survive a token refresh.

Volkswagen North America's token endpoint wants the verifier of the original
sign-in replayed on every refresh. The token set a sign-in returns carries it,
and the first refresh sends it. The token set that refresh RETURNS used to
come back without it, so the second refresh went out without the field.

What is and is not established:

- Established here, through the real ``VWNAClient._refresh`` and the real
  ``IDKAuth.refresh`` with only the HTTP session replaced: which form fields
  each refresh sends.
- NOT established here: that the server rejects a refresh without the
  verifier. That is taken from the #1012 notes (a third-party client's
  observation of ``400 Internal Service validation failure``). The one test
  that depends on it says so in its name and builds that answer into its
  stand-in server.
"""
from __future__ import annotations

import asyncio
from typing import Any

from custom_components.vag_connect.cariad.api.vw_na import BRAND_VW_NA, VWNAClient
from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.models import TokenSet

_VERIFIER = "verifier-from-sign-in"
_US_TOKEN_URL = "https://b-h-s.spr.us00.p.con-veh.net/oidc/v1/token"
_NON_CONVEH_URL = "https://emea.bff.cariad.digital/oidc/v1/token"


class _Response:
    def __init__(self, status: int, payload: dict[str, Any] | None = None) -> None:
        self.status = status
        self._payload = payload or {}

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._payload

    async def text(self, *args: Any, **kwargs: Any) -> str:
        return ""


class _TokenEndpoint:
    """Stands in for the HTTP session. Records every refresh form body.

    ``binds_verifier=True`` answers a refresh without ``code_verifier`` with
    HTTP 400, which is the behaviour the #1012 notes describe.
    """

    def __init__(self, *, binds_verifier: bool = False) -> None:
        self.binds_verifier = binds_verifier
        self.refresh_bodies: list[dict[str, Any]] = []
        self.urls: list[str] = []
        self._minted = 0

    def post(self, url: str, **kwargs: Any) -> _Response:
        data = dict(kwargs.get("data") or {})
        assert data.get("grant_type") == "refresh_token", (
            f"the stand-in only answers refreshes, got {sorted(data)}"
        )
        self.urls.append(str(url))
        self.refresh_bodies.append(data)
        if self.binds_verifier and not data.get("code_verifier"):
            return _Response(400)
        self._minted += 1
        return _Response(200, {
            "access_token": f"access-{self._minted}",
            "refresh_token": f"refresh-{self._minted}",
            "id_token": f"id-{self._minted}",
        })


def _signed_in_client(endpoint: _TokenEndpoint) -> VWNAClient:
    """A client holding the token set a sign-in leaves behind."""
    client = VWNAClient(endpoint, "owner@example.test", "a-password")
    client._tokens = TokenSet(
        access_token="access-0",
        refresh_token="refresh-0",
        id_token="id-0",
        code_verifier=_VERIFIER,
    )
    return client


def _count_sign_ins(client: VWNAClient) -> list[str]:
    """Replace the full sign-in with a recorder that leaves a fresh token set."""
    started: list[str] = []

    async def _sign_in(mfa_code: str | None = None) -> None:
        started.append("sign-in")
        client._tokens = TokenSet(
            access_token="access-after-sign-in",
            refresh_token="refresh-after-sign-in",
            id_token="id-after-sign-in",
            code_verifier=f"verifier-of-sign-in-{len(started)}",
        )

    client.authenticate = _sign_in  # type: ignore[method-assign]
    return started


def test_the_first_refresh_replays_the_verifier() -> None:
    """Control: this held before the fix, and shows the stand-in records."""
    endpoint = _TokenEndpoint()
    client = _signed_in_client(endpoint)

    asyncio.run(client._refresh())

    assert endpoint.urls == [_US_TOKEN_URL]
    assert endpoint.refresh_bodies[0]["refresh_token"] == "refresh-0"
    assert endpoint.refresh_bodies[0]["code_verifier"] == _VERIFIER


def test_the_refreshed_token_set_still_holds_the_verifier() -> None:
    endpoint = _TokenEndpoint()
    client = _signed_in_client(endpoint)

    asyncio.run(client._refresh())

    # the refresh really happened: the rotated token is the one in use
    assert client._tokens is not None
    assert client._tokens.refresh_token == "refresh-1"
    assert client._tokens.code_verifier == _VERIFIER


def test_every_later_refresh_replays_the_verifier_too() -> None:
    endpoint = _TokenEndpoint()
    client = _signed_in_client(endpoint)

    async def _three() -> None:
        for _ in range(3):
            await client._refresh()

    asyncio.run(_three())

    # each refresh used the token the previous one handed out
    assert [b["refresh_token"] for b in endpoint.refresh_bodies] == [
        "refresh-0", "refresh-1", "refresh-2",
    ]
    assert [b.get("code_verifier") for b in endpoint.refresh_bodies] == [
        _VERIFIER, _VERIFIER, _VERIFIER,
    ]


def test_no_sign_in_between_refreshes_if_the_server_binds_the_verifier() -> None:
    """The consequence, IF the server behaves as the #1012 notes say.

    A refresh without the verifier is answered 400 by this stand-in, which the
    client reads as a dead refresh token and answers with a full sign-in. Three
    healthy renewals in a row must not start one.
    """
    endpoint = _TokenEndpoint(binds_verifier=True)
    client = _signed_in_client(endpoint)
    sign_ins = _count_sign_ins(client)

    async def _three() -> None:
        for _ in range(3):
            await client._refresh()

    asyncio.run(_three())

    assert sign_ins == []
    assert len(endpoint.refresh_bodies) == 3


def test_a_token_set_without_a_verifier_still_falls_back_to_a_sign_in() -> None:
    """Unchanged behaviour: nothing to replay means the refresh is refused by a
    binding server and the client signs in again, once."""
    endpoint = _TokenEndpoint(binds_verifier=True)
    client = _signed_in_client(endpoint)
    assert client._tokens is not None
    client._tokens.code_verifier = ""
    sign_ins = _count_sign_ins(client)

    asyncio.run(client._refresh())

    assert sign_ins == ["sign-in"]
    assert "code_verifier" not in endpoint.refresh_bodies[0]


def test_a_refresh_without_a_verifier_returns_none() -> None:
    """Every other caller of the shared refresh passes no verifier, and gets a
    token set without one, on this endpoint and on any other."""
    for url in (_US_TOKEN_URL, _NON_CONVEH_URL):
        endpoint = _TokenEndpoint()
        auth = IDKAuth(endpoint, BRAND_VW_NA, token_url_override=url)

        tokens = asyncio.run(auth.refresh("refresh-0"))

        assert tokens.refresh_token == "refresh-1"
        assert tokens.code_verifier == ""
        assert "code_verifier" not in endpoint.refresh_bodies[0]


def test_the_verifier_is_kept_only_where_it_is_sent() -> None:
    """Off the con-veh endpoint the verifier is neither sent nor kept, the same
    scoping the code exchange applies."""
    endpoint = _TokenEndpoint()
    auth = IDKAuth(endpoint, BRAND_VW_NA, token_url_override=_NON_CONVEH_URL)

    tokens = asyncio.run(auth.refresh("refresh-0", code_verifier=_VERIFIER))

    assert tokens.refresh_token == "refresh-1"
    assert "code_verifier" not in endpoint.refresh_bodies[0]
    assert tokens.code_verifier == ""
