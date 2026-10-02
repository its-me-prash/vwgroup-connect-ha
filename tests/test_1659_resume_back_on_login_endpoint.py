# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1659 (@Joassens) — after EVERY Home Assistant restart the vw.de channel died
with "refresh did not land on the portal
(www.volkswagen.de/app/authproxy/login)" and had to be re-added by hand.

That landing URL is the giveaway: it is the very path the silent refresh GET
requests, so the redirect chain never left the login endpoint — the resume
achieved nothing. But the landing is on the portal host and carries neither
``/u/login`` nor ``/signin-service``, so it matched no dead-SSO test and fell
through to the generic raise, which skips ``relogin_if_allowed()`` altogether.
Users who had opted into the stored-credential re-login never got it, and the
message told them to re-add the channel instead of recovering silently.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.auth import _website_authproxy as wap
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
)

PORTAL = "https://www.volkswagen.de"


class _Resp:
    def __init__(self, url: str, status: int) -> None:
        self.url, self.status = url, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, url: str, status: int = 200) -> None:
        self._url, self._status = url, status
        self.calls = 0

    def get(self, *_a, **_kw):
        self.calls += 1
        return _Resp(self._url, self._status)


def _client(landed: str, status: int = 200, *, relogin: bool = False):
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c._session = _Session(landed, status)
    c._resume_dead_this_cycle = False
    c.logged_in = False
    c._headers = MagicMock(return_value={})
    c._redirect_hosts = MagicMock(return_value=[])

    async def _relogin():
        c.relogin_called = True
        return relogin

    c.relogin_called = False
    c.relogin_if_allowed = _relogin
    return c


LOGIN_URL = f"{PORTAL}{wap._LOGIN_PATH}"


def test_landing_back_on_the_login_endpoint_is_treated_as_a_dead_session() -> None:
    c = _client(LOGIN_URL, status=200)
    with pytest.raises(AuthenticationError) as err:
        asyncio.run(c.refresh())
    # the honest verdict, not the opaque "did not land on the portal"
    assert "full re-login required" in str(err.value)


def test_it_now_reaches_the_opt_in_credential_relogin() -> None:
    # this is the regression that cost @Joassens a manual re-add every restart
    c = _client(LOGIN_URL, status=200)
    with pytest.raises(AuthenticationError):
        asyncio.run(c.refresh())
    assert c.relogin_called is True


def test_a_successful_relogin_recovers_silently() -> None:
    c = _client(LOGIN_URL, status=200, relogin=True)
    asyncio.run(c.refresh())  # no raise: the session was restored
    assert c.relogin_called is True


def test_trailing_slash_is_the_same_landing() -> None:
    c = _client(f"{LOGIN_URL}/", status=200)
    with pytest.raises(AuthenticationError) as err:
        asyncio.run(c.refresh())
    assert "full re-login required" in str(err.value)


def test_query_string_does_not_change_the_verdict() -> None:
    c = _client(f"{LOGIN_URL}?fag=vw-de", status=200)
    with pytest.raises(AuthenticationError) as err:
        asyncio.run(c.refresh())
    assert "full re-login required" in str(err.value)


def test_a_real_portal_landing_still_resumes() -> None:
    c = _client(f"{PORTAL}/app/connect/vehicles", status=200)
    asyncio.run(c.refresh())
    assert c.logged_in is True
    assert c.relogin_called is False


def test_idp_login_landing_keeps_its_existing_verdict() -> None:
    c = _client("https://identity.vwgroup.io/u/login", status=200)
    with pytest.raises(AuthenticationError) as err:
        asyncio.run(c.refresh())
    assert "full re-login required" in str(err.value)
    assert c.relogin_called is True


def test_sso_error_parameter_still_wins() -> None:
    c = _client(f"{PORTAL}/somewhere?error=login_required", status=200)
    with pytest.raises(AuthenticationError) as err:
        asyncio.run(c.refresh())
    assert "silent refresh failed" in str(err.value)


def test_an_unknown_off_portal_landing_still_raises_the_generic_verdict() -> None:
    # unchanged behaviour: only the login-endpoint shape was reclassified
    c = _client("https://example.invalid/somewhere", status=200)
    with pytest.raises(AuthenticationError) as err:
        asyncio.run(c.refresh())
    assert "did not land on the portal" in str(err.value)
