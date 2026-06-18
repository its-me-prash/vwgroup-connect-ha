# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.14.6 — website-authproxy session-resume probe (skip the login dance).

Pre-2.14.6 a cookie-resumed website-authproxy session ALWAYS re-ran
``begin_login()`` — it re-hit ``/app/authproxy/login`` and restarted the OIDC
dance even when the persisted cookies were still perfectly valid. When those
cookies were only PARTIALLY valid the authproxy bounced against the IDP and
aiohttp raised ``TooManyRedirects``, which (pre-2.14.5) crashed the poll and
(on 2.14.5) degraded to an unnecessary re-OTP.

v2.14.6 adds ``session_alive()`` — a cheap, redirect-free probe of the
relations data endpoint with the resumed cookies. If the session is still
good we adopt it directly and skip the login flow; only a genuinely dead
session (401/403, or a 3xx bounce to the login page) falls through to
``begin_login()``. That is what makes silent resume actually WORK rather than
merely not-crash.

Also pins the defensive ``TooManyRedirects`` guard added to the credential
POST inside ``begin_login`` (mirrors the begin_login GET guard from 2.14.5).
"""

from __future__ import annotations

from typing import Any

import pytest
from aiohttp import ClientError, TooManyRedirects

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

_LOGIN_HTML = (
    '<html><body><form action="/u/login?state=ST">'
    '<input type="hidden" name="state" value="ST">'
    '<input type="hidden" name="hmac" value="h"></form></body></html>'
)


class _Resp:
    def __init__(self, url: str, status: int = 200, text: str = "") -> None:
        self.url = url
        self.status = status
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text

    async def json(self, content_type: Any = None) -> Any:
        return {}


# ── session_alive() probe ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_alive_true_on_200_skips_redirects() -> None:
    """A clean 200 on the relations probe marks the session alive, and the
    probe must NOT follow redirects (so a stale-session 3xx → login can't be
    mistaken for success, and can't loop)."""
    seen: dict[str, Any] = {}

    class _S:
        def get(self, url: str, **kw: Any) -> _Resp:
            seen["url"] = url
            seen["allow_redirects"] = kw.get("allow_redirects")
            return _Resp(url, 200)

    conn = WebsiteAuthProxyConnector(_S(), "u@x.z", "pw")  # type: ignore[arg-type]
    assert await conn.session_alive() is True
    assert conn.logged_in is True
    assert seen["allow_redirects"] is False
    assert "relations" in seen["url"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 401, 403, 500])
async def test_session_alive_false_on_non_200(status: int) -> None:
    """Anything but 200 — a redirect-to-login or an auth failure — is dead,
    and never marks the connector logged-in."""
    class _S:
        def get(self, url: str, **kw: Any) -> _Resp:
            return _Resp(url, status)

    conn = WebsiteAuthProxyConnector(_S(), "u@x.z", "pw")  # type: ignore[arg-type]
    assert await conn.session_alive() is False
    assert conn.logged_in is False


@pytest.mark.asyncio
async def test_session_alive_false_on_transport_error() -> None:
    """A transport error during the probe is treated as a dead session."""
    class _S:
        def get(self, url: str, **kw: Any) -> Any:
            raise ClientError("boom")

    conn = WebsiteAuthProxyConnector(_S(), "u@x.z", "pw")  # type: ignore[arg-type]
    assert await conn.session_alive() is False
    assert conn.logged_in is False


# ── credential-POST redirect-loop guard ────────────────────────────────────

@pytest.mark.asyncio
async def test_credential_post_redirect_loop_is_clean_auth_error() -> None:
    """A ``TooManyRedirects`` on the credential POST surfaces as a clean
    ``AuthenticationError`` (handled), not an unguarded crash."""
    class _S:
        def get(self, url: str, **kw: Any) -> _Resp:
            return _Resp(
                "https://identity.vwgroup.io/u/login?state=ST", 200, _LOGIN_HTML
            )

        def post(self, url: str, **kw: Any) -> Any:
            raise TooManyRedirects(None, ())  # type: ignore[arg-type]

    conn = WebsiteAuthProxyConnector(_S(), "u@x.z", "pw")  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError) as ei:
        await conn.begin_login()
    assert "redirect loop" in str(ei.value).lower()
