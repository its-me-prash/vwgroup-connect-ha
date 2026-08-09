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


# ── the second cause: the cookie round-trip used to narrow a domain cookie ──
#
# Proven by comparing against a comparable open-source client that shipped the
# exact same two-host broadcast model, hit this bug, and moved off it — their
# own note says the old behaviour "silently broke the silent refresh and forced
# a re-login", which is the symptom all three reporters describe. Our code even
# carried a comment claiming it matched theirs; it matched their OLD code.


def _jar_domains(conn: WebsiteAuthProxyConnector) -> set[tuple[str, str]]:
    return {
        (c["domain"] or "", c.key) for c in conn._session.cookie_jar  # type: ignore[attr-defined]
    }


def _real_jar_conn() -> WebsiteAuthProxyConnector:
    import aiohttp

    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    return WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_domain_cookie_survives_the_round_trip_as_a_domain_cookie() -> None:
    """A `.vwgroup.io` cookie must still reach OTHER *.vwgroup.io hosts after a
    restart — that is what the authorize chain needs."""
    conn = _real_jar_conn()
    try:
        conn.import_cookies([
            {"name": "SSO", "value": "v1", "domain": ".vwgroup.io", "path": "/"},
        ])
        # aiohttp normalises the leading dot away, so assert on BEHAVIOUR: the
        # cookie must be filed on the apex, not on one of our two hosts.
        domains = {d for d, _ in _jar_domains(conn)}
        assert "vwgroup.io" in domains, (
            f"domain cookie was re-bound host-only: {domains}"
        )
        # the practical check: a sibling host in the authorize chain gets it
        from yarl import URL

        served = conn._session.cookie_jar.filter_cookies(  # type: ignore[attr-defined]
            URL("https://login.vwgroup.io/")
        )
        assert "SSO" in served, "sibling *.vwgroup.io host did not receive the cookie"
    finally:
        await conn._session.close()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_host_only_cookies_still_reach_both_hosts() -> None:
    """The host-only broadcast is what makes the SSO cookie reachable — it must
    keep working for entries without a dotted domain."""
    from yarl import URL

    conn = _real_jar_conn()
    try:
        conn.import_cookies([
            {"name": "AUTH0", "value": "v2", "domain": "identity.vwgroup.io"},
        ])
        for host in ("https://www.volkswagen.de/", "https://identity.vwgroup.io/"):
            served = conn._session.cookie_jar.filter_cookies(URL(host))  # type: ignore[attr-defined]
            assert "AUTH0" in served, f"host-only cookie missing on {host}"
    finally:
        await conn._session.close()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_foreign_domains_are_still_rejected() -> None:
    conn = _real_jar_conn()
    try:
        conn.import_cookies([
            {"name": "EVIL", "value": "x", "domain": ".example.invalid"},
        ])
        assert "EVIL" not in {k for _, k in _jar_domains(conn)}
    finally:
        await conn._session.close()  # type: ignore[attr-defined]
