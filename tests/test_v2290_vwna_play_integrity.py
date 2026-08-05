# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1012 — VW North America needs a play_integrity_token on the token exchange.

Two US owners could not add the integration. Their debug logs show the sign-in
completing all the way to an authorization code, and only the code->token POST
failing, with HTTP 401 {"errorCode":"INVALID_REQUEST",
"origin":"CarnetSPAuthorizationServer"}.

On 2026-07-30 VW's con-veh token endpoint began requiring a ``play_integrity_token``
form field on the grant. It checks the field is present, not that it is a valid
attestation, so the maintained third-party NA clients send the literal string
``"unavailable"``. Our request matched the working clients byte-for-byte except
for this one missing field, which is why our own note records that v2.25 (before
the server change) authenticated fine.

These tests pin two things: the field IS sent when the token endpoint is a
con-veh host, and it is NOT sent for the other brands that share the same
code path (Skoda / SEAT / CUPRA / VW EU), whose servers do not want it.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.vw_na import BRAND_VW_NA
from custom_components.vag_connect.cariad.auth.idk import IDKAuth

_US_TOKEN_URL = "https://b-h-s.spr.us00.p.con-veh.net/oidc/v1/token"
_NON_CONVEH_URL = "https://emea.bff.cariad.digital/oidc/v1/token"


def _capturing_session() -> tuple[MagicMock, dict]:
    """A session whose POST records its ``data`` and returns a 200 token body."""
    captured: dict = {}

    def _post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.status = 200
        resp.json = AsyncMock(return_value={
            "access_token": "a", "refresh_token": "r", "id_token": "i",
        })
        resp.text = AsyncMock(return_value="{}")
        return resp

    session = MagicMock()
    session.post = MagicMock(side_effect=_post)
    return session, captured


def test_na_exchange_sends_play_integrity_token() -> None:
    session, captured = _capturing_session()
    auth = IDKAuth(session, BRAND_VW_NA, token_url_override=_US_TOKEN_URL)
    asyncio.run(auth._exchange_code("thecode", "theverifier"))

    data = captured["data"]
    assert data["play_integrity_token"] == "unavailable"
    # everything else the working clients send must still be there, unchanged
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "thecode"
    assert data["code_verifier"] == "theverifier"
    assert data["redirect_uri"] == BRAND_VW_NA.redirect_uri
    # public client: no secret, no basic auth
    assert "client_secret" not in data
    assert "con-veh" in captured["url"]


def test_non_conveh_exchange_does_not_send_it() -> None:
    """The field is scoped to the con-veh host, not to the brand: point the same
    NA client at a non-con-veh token endpoint and the field must NOT appear, so
    a future EU-hosted exchange sharing this branch is never given a stray
    Play-Integrity field its server did not ask for."""
    session, captured = _capturing_session()
    auth = IDKAuth(session, BRAND_VW_NA, token_url_override=_NON_CONVEH_URL)
    asyncio.run(auth._exchange_code("thecode", "theverifier"))

    assert "play_integrity_token" not in captured["data"]
    assert "con-veh" not in captured["url"]


def test_na_exchange_persists_the_verifier_for_refresh() -> None:
    """The con-veh refresh grant needs the original PKCE verifier, so the token
    set the exchange returns has to carry it."""
    session, _ = _capturing_session()
    auth = IDKAuth(session, BRAND_VW_NA, token_url_override=_US_TOKEN_URL)
    tokens = asyncio.run(auth._exchange_code("thecode", "kept_verifier"))
    assert tokens.code_verifier == "kept_verifier"


def test_na_refresh_sends_token_and_verifier() -> None:
    """Refresh must replay both the play_integrity_token and the stored
    verifier, or the con-veh server 401s / 400s the refresh."""
    session, captured = _capturing_session()
    auth = IDKAuth(session, BRAND_VW_NA, token_url_override=_US_TOKEN_URL)
    asyncio.run(auth.refresh("the_refresh_token", code_verifier="stored_verifier"))

    data = captured["data"]
    assert data["grant_type"] == "refresh_token"
    assert data["play_integrity_token"] == "unavailable"
    assert data["code_verifier"] == "stored_verifier"


def test_non_conveh_refresh_stays_plain() -> None:
    session, captured = _capturing_session()
    auth = IDKAuth(session, BRAND_VW_NA, token_url_override=_NON_CONVEH_URL)
    asyncio.run(auth.refresh("the_refresh_token", code_verifier="stored_verifier"))

    assert "play_integrity_token" not in captured["data"]
    assert "code_verifier" not in captured["data"]
