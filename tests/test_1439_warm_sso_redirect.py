# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1439 (maki040) — a warm-SSO app-scheme redirect no longer discards the auth.

When Auth0 already holds a session it 302s the authorize request straight to the
brand app-scheme redirect_uri (e.g. ``myaudi:///#access_token=...``). aiohttp
cannot follow a non-http redirect and raises NonHttpUrlRedirectClientError, which
used to be swallowed by the broad except and fall through to the portal strategy,
throwing away a valid hybrid authentication. The callback fragment carries the
tokens; ``authenticate`` now captures them.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.client_exceptions import NonHttpUrlRedirectClientError
from yarl import URL

from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.cariad.exceptions import AuthenticationError


def _client(redirect_uri: str = "myaudi:///") -> IDKAuth:
    c = IDKAuth.__new__(IDKAuth)
    c.last_redirect_url = None
    c._brand = MagicMock()
    c._brand.redirect_uri = redirect_uri
    return c


def test_hybrid_callback_returns_tokens() -> None:
    c = _client()
    ref = "myaudi:///#access_token=AAA&id_token=III&code=CCC"
    ts = asyncio.run(c._warm_sso_callback_tokens(ref, True, "v"))
    assert ts.access_token == "AAA"
    assert ts.id_token == "III"
    assert ts.refresh_token == ""
    assert c.last_redirect_url == ref


def test_code_only_callback_exchanges() -> None:
    c = _client()
    c._exchange_code = AsyncMock(
        return_value=TokenSet(access_token="X", refresh_token="Y", id_token="Z")
    )
    ts = asyncio.run(c._warm_sso_callback_tokens("myaudi:///?code=CCC", False, "verif"))
    c._exchange_code.assert_awaited_once_with("CCC", "verif")
    assert ts.access_token == "X"


def test_hybrid_missing_id_falls_back_to_code_exchange() -> None:
    c = _client()
    c._exchange_code = AsyncMock(
        return_value=TokenSet(access_token="X", refresh_token="Y", id_token="Z")
    )
    ts = asyncio.run(c._warm_sso_callback_tokens("myaudi:///#access_token=AAA&code=CCC", True, "v"))
    c._exchange_code.assert_awaited_once()
    assert ts.access_token == "X"


def test_empty_callback_raises() -> None:
    c = _client()
    with pytest.raises(AuthenticationError):
        asyncio.run(c._warm_sso_callback_tokens("myaudi:///", True, "v"))


def test_authenticate_catches_nonhttp_redirect_and_returns_tokens() -> None:
    c = IDKAuth.__new__(IDKAuth)
    c.last_redirect_url = None
    c._brand = MagicMock()
    c._brand.redirect_uri = "myaudi:///"
    c._brand.scope = "openid profile"
    c._brand.client_id = "CID"
    c._authorize_url = "https://identity.vwgroup.io/oidc/v1/authorize"
    c._base_headers = MagicMock(return_value={})
    c._session = MagicMock()
    c._session.get = MagicMock(
        side_effect=NonHttpUrlRedirectClientError(
            URL("myaudi:///#access_token=AAA&id_token=III")
        )
    )
    ts = asyncio.run(c.authenticate("e@x.de", "pw", hybrid_full=True))
    assert ts.access_token == "AAA"
    assert ts.id_token == "III"
