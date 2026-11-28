# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2138 — a volkswagen.de resume that lands on the e-mail code page asks for
the code instead of failing.

@erikbp's live test: the sign-in resumed from saved cookies and the identity
provider answered with ``identity.vwgroup.io/u/mfa-email-challenge``. The
resume path only knew three outcomes (back on volkswagen.de, a terms wall, the
login page), so it stopped with "did not reach the VW identity login" and the
user was told the sign-in failed, although only a fresh e-mail code was missing.
The credential POST already treats that page as the e-mail-code step; the
resume path now does the same.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

PORTAL_OK = "https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html"
MFA = "https://identity.vwgroup.io/u/mfa-email-challenge?state=ST2138"
MFA_FORM = (
    '<html><body><form method="post" action="/u/mfa-email-challenge?state=ST2138">'
    '<input type="hidden" name="_csrf" value="C1">'
    '<input type="text" name="code" value="">'
    "</form></body></html>"
)


class _Resp:
    def __init__(self, url: str, status: int, text: str) -> None:
        self.url, self.status, self._text = url, status, text
        self.history: tuple[Any, ...] = ()

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:  # noqa: ARG002
        return self._text


class _Session:
    def __init__(self, gets: list[tuple[str, int, str]],
                 posts: list[tuple[str, int, str]] | None = None) -> None:
        self._gets, self._posts = list(gets), list(posts or [])
        self.got: list[str] = []
        self.posted: list[str] = []

    def get(self, url: str, **_kw: Any) -> _Resp:
        self.got.append(url)
        return _Resp(*(self._gets.pop(0) if self._gets else (PORTAL_OK, 200, "")))

    def post(self, url: str, **_kw: Any) -> _Resp:
        self.posted.append(url)
        return _Resp(*(self._posts.pop(0) if self._posts else (PORTAL_OK, 200, "")))


def _client(sess: _Session) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c._session = sess
    c._resume_dead_this_cycle = False
    c.logged_in = False
    c._headers = MagicMock(return_value={})
    c._otp_url = c._otp_state = c._otp_html = None
    return c


def test_a_resume_on_the_code_page_asks_for_the_code() -> None:
    c = _client(_Session([(MFA, 200, MFA_FORM)]))
    assert asyncio.run(c.begin_login()) == "otp_required"
    assert c._otp_url == MFA
    assert c._otp_state == "ST2138"
    assert c._otp_html == MFA_FORM
    assert c.logged_in is False


def test_the_code_then_finishes_the_login() -> None:
    sess = _Session([(MFA, 200, MFA_FORM)], posts=[(PORTAL_OK, 200, "")])
    c = _client(sess)
    assert asyncio.run(c.begin_login()) == "otp_required"
    assert asyncio.run(c.submit_otp("123456")) is True
    assert c.logged_in is True
    assert sess.posted and "/u/mfa-email-challenge" in sess.posted[0]


def test_the_older_email_challenge_path_is_recognised_too() -> None:
    url = "https://identity.vwgroup.io/u/email-challenge?state=S"
    c = _client(_Session([(url, 200, MFA_FORM)]))
    assert asyncio.run(c.begin_login()) == "otp_required"


def test_a_terms_link_on_the_code_page_does_not_turn_it_into_a_terms_wall() -> None:
    page = MFA_FORM.replace("</form>", '</form><a href="/u/terms">Terms</a>')
    c = _client(_Session([(MFA, 200, page)]))
    assert asyncio.run(c.begin_login()) == "otp_required"


def test_any_other_identity_page_still_fails_as_before() -> None:
    other = "https://identity.vwgroup.io/u/something-else?state=S"
    c = _client(_Session([(other, 200, "<html></html>")]))
    with pytest.raises(AuthenticationError, match="did not reach the VW identity login"):
        asyncio.run(c.begin_login())


def test_a_resume_back_on_volkswagen_de_is_unchanged() -> None:
    c = _client(_Session([(PORTAL_OK, 200, "")]))
    assert asyncio.run(c.begin_login()) == "ok"
    assert c.logged_in is True
