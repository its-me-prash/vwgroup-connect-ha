# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 / #875 / #966 — the volkswagen.de "re-add me" loop.

Three reporters described the same shape, one of them exactly: *"The email OTP
login succeeds, but IMMEDIATELY afterwards the supplementary volkswagen.de
session is reported as expired."* Re-adding produced fresh cookies, the next arm
declared them expired again, and the Repair came straight back — forever.

Root cause: ``refresh()`` classified the outcome with a bare substring test over
the WHOLE landed URL, query string included. A resume that landed correctly back
on volkswagen.de was still declared "SSO session expired" whenever the callback
carried an IDP path inside a query parameter (``redirect_uri=…/signin-service/…``
is the portal's own callback shape). ``begin_login`` had always classified on the
host; ``refresh`` now does too.

The distinction that matters: a dead SSO lands ON the IDP host at /u/login. A
live one lands on volkswagen.de — whatever its query string happens to contain.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError


class _Resp:
    def __init__(self, url: str, status: int = 200) -> None:
        self.url = url
        self.status = status

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def text(self) -> str:
        return ""


def _session_landing(url: str, status: int = 200) -> Any:
    class _S:
        def get(self, u: str, **kw: Any) -> _Resp:
            return _Resp(url, status)

    return _S()


def _conn(url: str, status: int = 200) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector(_session_landing(url, status), "u@x.z", "pw")  # type: ignore[arg-type]
    c.begin_login = AsyncMock()  # must never fire — that is the OTP-storm guard
    return c


@pytest.mark.asyncio
async def test_portal_landing_with_idp_path_in_the_query_is_a_success() -> None:
    """THE REGRESSION. Landed on volkswagen.de, but the query carries an IDP
    path — this used to raise "SSO session expired" and start the loop."""
    conn = _conn(
        "https://www.volkswagen.de/app/authproxy/login-result"
        "?redirectUrl=https%3A%2F%2Fidentity.vwgroup.io%2Fsignin-service%2Fv1%2Fcallback"
    )
    await conn.refresh()
    assert conn.logged_in is True
    conn.begin_login.assert_not_awaited()


@pytest.mark.asyncio
async def test_portal_landing_with_u_login_in_the_query_is_a_success() -> None:
    conn = _conn(
        "https://www.volkswagen.de/de/besitzer-und-nutzer.html?from=%2Fu%2Flogin"
    )
    await conn.refresh()
    assert conn.logged_in is True


@pytest.mark.asyncio
async def test_dead_sso_on_the_idp_still_raises() -> None:
    """The real expired-session case must keep raising — this is what tells the
    user to re-add, and it must not call begin_login (OTP-email storm)."""
    conn = _conn("https://identity.vwgroup.io/u/login?state=ST")
    with pytest.raises(AuthenticationError):
        await conn.refresh()
    assert conn.logged_in is False
    conn.begin_login.assert_not_awaited()


@pytest.mark.asyncio
async def test_dead_sso_on_signin_service_still_raises() -> None:
    conn = _conn("https://identity.vwgroup.io/signin-service/v1/signin")
    with pytest.raises(AuthenticationError):
        await conn.refresh()


@pytest.mark.asyncio
async def test_sso_error_parameter_still_raises() -> None:
    conn = _conn("https://www.volkswagen.de/cb?error=login_required")
    with pytest.raises(AuthenticationError):
        await conn.refresh()


@pytest.mark.asyncio
async def test_landing_on_a_foreign_host_still_raises() -> None:
    conn = _conn("https://example.invalid/whatever")
    with pytest.raises(AuthenticationError):
        await conn.refresh()
