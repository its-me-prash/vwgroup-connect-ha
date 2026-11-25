# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche app callback moved to an https app link — #1337 (25.11.2026).

Porsche removed ``my-porsche-app://auth0/callback`` from the Auth0 client's
allowed callbacks. Measured without credentials against /authorize with our
client_id: the old value gets "Callback URL mismatch" (403), the https app
link below redirects to the login page (302); only the en-GB path is
registered. Existing sessions keep refreshing, every NEW login or reauth
failed.

Two things are pinned here:

(a) the redirect_uri every step sends — /authorize and the code exchange
    carry the new value; the refresh grant carries none (as before, and as
    the reference client does), so the refresh path that keeps existing
    sessions alive is untouched;
(b) a ``Location`` pointing at the https callback with ``code=`` ends the
    flow: the code is read from the header and the URL is never requested.
    With the old custom scheme aiohttp could not have fetched it anyway;
    with an https URL it could, and the code would then never reach our
    token exchange.

The URL is written out literally on purpose, so putting the old value back
into the module turns this file red.
"""
from __future__ import annotations

import json as _json
from urllib.parse import urlsplit

import pytest

from custom_components.vag_connect.cariad.auth import porsche as porsche_auth
from custom_components.vag_connect.cariad.auth.porsche import PorscheAuth
from custom_components.vag_connect.cariad.models import BRAND_PORSCHE

_NEW_CB = "https://security.porsche.com/auth/en-GB/app/callback"
_OLD_CB = "my-porsche-app://auth0/callback"
_CB_HOST = "security.porsche.com"


class _Resp:
    def __init__(self, status: int, headers: dict | None = None, text: str = "") -> None:
        self.status = status
        self.headers = headers or {}
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def text(self) -> str:
        return self._text

    async def json(self) -> dict:
        return _json.loads(self._text) if self._text else {}


class _Session:
    """Queue-backed stand-in that records every request it is asked for."""

    def __init__(self, get_responses=None, post_responses=None) -> None:
        self._get_q = list(get_responses or [])
        self._post_q = list(post_responses or [])
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self._get_q.pop(0)

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._post_q.pop(0)

    def requested_hosts(self) -> set[str]:
        return {
            (urlsplit(url).hostname or "").lower()
            for url, _ in self.get_calls + self.post_calls
        }


def _token_body(**extra) -> str:
    return _json.dumps({
        "access_token": "AT", "refresh_token": "RT", "expires_in": 3600, **extra,
    })


# ── (a) the redirect_uri each step sends ─────────────────────────────────

class TestRedirectUriSent:
    def test_module_and_brand_config_carry_the_https_callback(self):
        assert porsche_auth._REDIRECT_URI == _NEW_CB
        assert BRAND_PORSCHE.redirect_uri == _NEW_CB

    async def test_authorize_and_code_exchange_send_the_new_callback(self):
        # An already-valid Auth0 session: /authorize hands the code straight
        # back, so the same test covers the authorize request, the
        # callback-as-end check and the real (unmocked) code exchange.
        session = _Session(
            get_responses=[
                _Resp(302, {"Location": f"{_NEW_CB}?code=EXISTING&state=x"}),
            ],
            post_responses=[_Resp(200, text=_token_body())],
        )
        tokens = await PorscheAuth(session).authenticate("a@b.com", "pw")

        assert tokens.access_token == "AT"
        authorize_url, authorize_kwargs = session.get_calls[0]
        assert authorize_url == "https://identity.porsche.com/authorize"
        assert authorize_kwargs["params"]["redirect_uri"] == _NEW_CB
        assert authorize_kwargs["allow_redirects"] is False

        assert len(session.post_calls) == 1
        token_url, token_kwargs = session.post_calls[0]
        assert token_url == "https://identity.porsche.com/oauth/token"
        assert token_kwargs["json"]["grant_type"] == "authorization_code"
        assert token_kwargs["json"]["code"] == "EXISTING"
        assert token_kwargs["json"]["redirect_uri"] == _NEW_CB
        # The callback itself was never requested.
        assert len(session.get_calls) == 1
        assert _CB_HOST not in session.requested_hosts()

    async def test_refresh_sends_no_redirect_uri(self):
        # The refresh grant does not take a redirect_uri; ours never sent one
        # and the reference client does not either. This is the path that
        # keeps existing Porsche sessions alive, so it stays as it was.
        session = _Session(post_responses=[_Resp(200, text=_token_body())])
        tokens = await PorscheAuth(session).refresh("old-refresh-token")

        assert tokens.access_token == "AT"
        _, kwargs = session.post_calls[0]
        body = kwargs["json"]
        assert body["grant_type"] == "refresh_token"
        assert "redirect_uri" not in body
        assert _OLD_CB not in _json.dumps(body)


# ── (b) the https callback in a Location header ends the flow ────────────

class TestCallbackLocationEndsTheFlow:
    async def test_full_password_flow_reads_code_from_location(self, monkeypatch):
        monkeypatch.setattr(porsche_auth, "_POST_PASSWORD_SETTLE_S", 0)
        session = _Session(
            get_responses=[
                _Resp(302, {"Location": "/u/login/identifier?state=ABC"}),
                # the resume hop after the password POST hands back the code
                _Resp(302, {"Location": f"{_NEW_CB}?code=FROM_HOP&state=ABC"}),
            ],
            post_responses=[
                _Resp(200),  # identifier step
                _Resp(302, {"Location": "/authorize/resume?state=ABC"}),  # password
                _Resp(200, text=_token_body()),  # code exchange
            ],
        )
        tokens = await PorscheAuth(session).authenticate("a@b.com", "pw")

        assert tokens.access_token == "AT"
        got = [url for url, _ in session.get_calls]
        assert got == [
            "https://identity.porsche.com/authorize",
            "https://identity.porsche.com/authorize/resume?state=ABC",
        ]
        assert all(kw["allow_redirects"] is False for _, kw in session.get_calls)
        assert _CB_HOST not in session.requested_hosts()
        token_url, token_kwargs = session.post_calls[-1]
        assert token_url == "https://identity.porsche.com/oauth/token"
        assert token_kwargs["json"]["code"] == "FROM_HOP"
        assert token_kwargs["json"]["redirect_uri"] == _NEW_CB
        assert token_kwargs["json"]["code_verifier"]

    async def test_follow_returns_code_without_requesting_the_callback(self):
        session = _Session(
            get_responses=[_Resp(302, {"Location": f"{_NEW_CB}?code=AFTER_HOP&state=x"})],
        )
        code = await PorscheAuth(session)._follow_to_code(
            "/authorize/resume?state=x", "https://identity.porsche.com/u/login/password",
        )
        assert code == "AFTER_HOP"
        assert len(session.get_calls) == 1
        assert _CB_HOST not in session.requested_hosts()

    async def test_callback_with_error_is_terminal_and_never_requested(self):
        session = _Session()  # any request would pop an empty queue
        code = await PorscheAuth(session)._follow_to_code(
            f"{_NEW_CB}?error=access_denied&state=x",
            "https://identity.porsche.com/u/login/password",
        )
        assert code is None
        assert session.get_calls == []

    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            (f"{_NEW_CB}?code=C1&state=x", "C1"),
            ("https://SECURITY.porsche.com/auth/en-GB/app/callback?code=C2", "C2"),
            (f"{_NEW_CB}?state=x", None),
            # not the registered callback → not the end of the flow
            (f"{_OLD_CB}?code=OLD", None),
            ("https://security.porsche.com/auth/de-DE/app/callback?code=X", None),
            ("https://security.porsche.com/auth/en-GB/app/callback2?code=X", None),
            ("http://security.porsche.com/auth/en-GB/app/callback?code=X", None),
            ("https://evil.example/auth/en-GB/app/callback?code=X", None),
            ("/authorize/resume?state=x&code=X", None),
        ],
    )
    def test_extract_code_only_from_the_registered_callback(self, location, expected):
        assert PorscheAuth._extract_code(location) == expected
