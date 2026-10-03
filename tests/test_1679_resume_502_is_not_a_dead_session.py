# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1679 / #1313 — a 502 on the resume is the site failing, not your session.

When www.volkswagen.de began serving ``/app/authproxy/*`` over HTTP/2 only,
every HTTP/1.1 request came back **502**. A 502 is returned FOR the login path,
so the silent resume landed on exactly the path its "dead SSO" test looks for,
and two harmful things followed:

* it ran a **credential re-login** — replaying the stored password and, on
  accounts with the e-mail challenge, triggering an OTP mail — to recover from
  an outage it could not recover from;
* it reported *"SSO session expired — full re-login required"* and armed a
  re-authentication, so people re-added the channel and re-entered codes, while
  @fschulte2812's cookies from three days earlier were still perfectly valid.

So a 5xx now gets its own verdict, checked before every other one.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
    _LOGIN_PATH,
    _SITE_BASE,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    AuthProxyUnavailableError,
)


class _Resp:
    def __init__(self, url: str, status: int) -> None:
        self.url = url
        self.status = status
        self.history: tuple[Any, ...] = ()

    async def text(self, **_kw: Any) -> str:
        return "<html>Bad Gateway</html>"

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    """Session double that answers every GET with one status."""

    def __init__(self, status: int, landed: str | None = None) -> None:
        self._status = status
        self._landed = landed or f"{_SITE_BASE}{_LOGIN_PATH}"
        self.cookie_jar = SimpleNamespace(
            filter_cookies=lambda *_a, **_k: {},
            update_cookies=lambda *_a, **_k: None,
        )
        self.gets = 0
        self.posts = 0

    def get(self, *_a: Any, **_kw: Any) -> _Resp:
        self.gets += 1
        return _Resp(self._landed, self._status)

    def post(self, *_a: Any, **_kw: Any) -> _Resp:
        self.posts += 1
        return _Resp(self._landed, self._status)


def _conn(session: _Session) -> WebsiteAuthProxyConnector:
    return WebsiteAuthProxyConnector(
        session,  # type: ignore[arg-type]  # a double, deliberately not wrapped
        "someone@example.invalid", "pw", brand="volkswagen",
    )


@pytest.mark.asyncio
async def test_a_502_is_not_reported_as_an_expired_session() -> None:
    conn = _conn(_Session(502))
    with pytest.raises(AuthProxyUnavailableError) as err:
        await conn.refresh()
    msg = str(err.value)
    assert "502" in msg
    assert "server-side" in msg
    assert "not your session" in msg
    # and specifically NOT the verdict that sends people to re-add the channel
    assert not isinstance(err.value, AuthenticationError)


@pytest.mark.asyncio
async def test_a_502_never_burns_a_credential_relogin() -> None:
    """The expensive half of the old bug: a server outage triggered a password
    POST and, for e-mail-challenge accounts, an OTP mail."""
    session = _Session(502)
    conn = _conn(session)
    conn._relogin_allowed = True  # type: ignore[attr-defined]
    with pytest.raises(AuthProxyUnavailableError):
        await conn.refresh()
    assert session.posts == 0, "a 5xx must not replay the stored password"


@pytest.mark.asyncio
async def test_every_server_error_class_is_covered_not_just_502() -> None:
    for status in (500, 502, 503, 504):
        session = _Session(status)
        with pytest.raises(AuthProxyUnavailableError):
            await _conn(session).refresh()
        assert session.posts == 0, status


@pytest.mark.asyncio
async def test_a_real_dead_sso_still_reports_an_expired_session() -> None:
    """The guard must not swallow the genuine case: a 200 landing back on the
    login endpoint is still a dead silent resume."""
    session = _Session(200, landed=f"{_SITE_BASE}{_LOGIN_PATH}")
    conn = _conn(session)
    with pytest.raises(AuthenticationError) as err:
        await conn.refresh()
    assert "SSO session expired" in str(err.value)


@pytest.mark.asyncio
async def test_a_healthy_resume_still_succeeds() -> None:
    session = _Session(200, landed=f"{_SITE_BASE}/app/portal/vehicles")
    conn = _conn(session)
    await conn.refresh()
    assert conn.logged_in is True


def test_the_caller_does_not_arm_a_reauth_for_a_server_outage() -> None:
    """The other half of the fix: the brand base used to set
    ``_supplementary_needs_reauth`` for ANY resume failure and tell the user to
    re-add the channel. A server outage must leave the stored session alone."""
    import inspect

    from custom_components.vag_connect.cariad.api import base

    src = inspect.getsource(base)
    i = src.index("except AuthProxyUnavailableError")
    j = src.index("except AuthenticationError", i)
    branch = src[i:j]
    assert "temporarily unavailable" in branch
    # CODE only: the branch's own comment explains what it must not do, so a
    # naive substring check would trip over the explanation.
    code = "\n".join(
        line for line in branch.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "_supplementary_needs_reauth" not in code, (
        "a server outage must not arm a re-authentication"
    )
    assert "re-add" not in code
    # ...and it has to be caught BEFORE the AuthenticationError branch, or it
    # would never be reached if it ever became a subclass of it.
    assert i < j
