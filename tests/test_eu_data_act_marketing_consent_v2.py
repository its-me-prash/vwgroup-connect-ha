# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The single-page marketing question on the portal login is declined once.

Since late October 2026 the identity provider shows accounts that never answered
the marketing question (first seen on SEAT and CUPRA) a page at
``identity.vwgroup.io/v2/login/ui/marketing-consent?relayState=…&state=…``. It
carries no ``callback=``, so the older skip — which only follows a callback —
returned ``None`` and the login ended in ``MarketingConsentError``.

The page's "not now" posts ``relayState`` and ``state`` to the same path plus
``/skip``. These tests pin the decline end to end through ``login()``:

* exactly one POST, by hand (no automatic redirects), Referer and Origin on the
  identity host, then the redirect walked to the portal callback;
* the page coming back after the POST → no second POST, the existing message;
* a missing ``relayState`` or ``state``, a foreign host, cleartext, or the
  ``/skip`` URL itself → no POST at all, the existing message;
* a decline that redirects off the login hosts is not followed;
* no query value reaches the log.

Not measured against a real account: the request shape follows the page's own
form as described in two independent reports.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    _marketing_consent_skip_request,
)
from custom_components.vag_connect.cariad.exceptions import MarketingConsentError

_RS = "RS-not-for-logs-4711"
_ST = "ST-not-for-logs-0815"
_PAGE = "https://identity.vwgroup.io/v2/login/ui/marketing-consent"
_PAGE_URL = f"{_PAGE}?relayState={_RS}&state={_ST}"
_SKIP_URL = f"{_PAGE}/skip"
_CALLBACK = (
    "https://eu-data-act.vwgroup-datahub.com/services/callbacklogin?code=c0de"
)
_SIGNIN_HTML = (
    '<form action="/signin-service/v1/CLIENT/login/identifier">'
    '<input type="hidden" name="hmac" value="email_hmac">'
    '<input type="hidden" name="_csrf" value="csrf1">'
    '<input type="hidden" name="relayState" value="rs1">'
    "</form>"
)
_PASSWORD_HTML = (
    "<script>window._IDK = {templateModel: "
    '{"hmac":"fresh_pw_hmac","relayState":"rs1",'
    '"postAction":"/signin-service/v1/CLIENT/login/authenticate"}, '
    'csrf_token: "csrf2"};</script>'
)
_MARKETING_HTML = "<html><form><button>Not now</button></form></html>"


class _Resp:
    def __init__(
        self,
        url: str,
        *,
        status: int = 200,
        text: str = "",
        location: str = "",
    ) -> None:
        self.url, self.status, self._text = url, status, text
        self.headers: dict[str, str] = {"Location": location} if location else {}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:  # noqa: ARG002
        return self._text


class _Session:
    """prime → authorize → identifier → credential POST → landing → (skip).

    Every skip POST is recorded with its keyword arguments, and every GET that
    is not routed is recorded AND raises, so "nothing was sent" is checked
    rather than assumed.
    """

    def __init__(
        self,
        landing: str,
        *,
        skip_response: _Resp | None = None,
        get_routes: dict[str, _Resp] | None = None,
    ) -> None:
        self._landing = landing
        self._skip = skip_response
        self._routes = get_routes or {}
        self.skip_posts: list[tuple[str, dict[str, Any]]] = []
        self.gets: list[tuple[str, dict[str, Any]]] = []
        self.unexpected: list[str] = []

    def get(self, url: str, **kw: Any) -> _Resp:
        if url.endswith("/") and "vwgroup-datahub" in url:
            return _Resp(url, text="<html>portal</html>")
        if "authorize" in url:
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/identifier",
                text=_SIGNIN_HTML,
            )
        self.gets.append((url, kw))
        if url in self._routes:
            return self._routes[url]
        self.unexpected.append(url)
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, **kw: Any) -> _Resp:
        if url.endswith("/login/identifier"):
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "authenticate?relayState=rs1",
                text=_PASSWORD_HTML,
            )
        if "/login/authenticate" in url:
            return _Resp(self._landing, text=_MARKETING_HTML)
        if "marketing-consent" in url:
            self.skip_posts.append((url, kw))
            if self._skip is None:
                raise AssertionError(f"a skip POST was sent: {url}")
            return self._skip
        raise AssertionError(f"unmatched POST {url}")


def _callback_route() -> dict[str, _Resp]:
    return {
        _CALLBACK: _Resp(
            _CALLBACK,
            status=302,
            location="https://eu-data-act.vwgroup-datahub.com/de/de/user.html",
        )
    }


# ── the decline, end to end ──────────────────────────────────────────────────
class TestTheDeclineCompletesTheLogin:
    @pytest.mark.asyncio
    async def test_one_post_then_the_portal_callback(self) -> None:
        sess = _Session(
            _PAGE_URL,
            skip_response=_Resp(_SKIP_URL, status=302, location=_CALLBACK),
            get_routes=_callback_route(),
        )
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        await conn.login("user@example.com", "secret")

        assert conn.logged_in is True
        assert len(sess.skip_posts) == 1
        url, kw = sess.skip_posts[0]
        assert url == _SKIP_URL
        assert list(kw["data"]) == [("relayState", _RS), ("state", _ST)]
        assert kw["allow_redirects"] is False
        assert kw["headers"]["Referer"] == _PAGE_URL
        assert kw["headers"]["Origin"] == "https://identity.vwgroup.io"
        # The callback was reached, and Origin did not travel past the POST.
        assert [u for u, _ in sess.gets] == [_CALLBACK]
        follow_headers = sess.gets[0][1]["headers"]
        assert "Origin" not in follow_headers
        assert follow_headers["Referer"] == _SKIP_URL
        assert sess.unexpected == []

    @pytest.mark.asyncio
    async def test_a_trailing_slash_on_the_page_path_is_the_same_page(self) -> None:
        sess = _Session(
            f"{_PAGE}/?relayState={_RS}&state={_ST}",
            skip_response=_Resp(_SKIP_URL, status=302, location=_CALLBACK),
            get_routes=_callback_route(),
        )
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        await conn.login("user@example.com", "secret")
        assert conn.logged_in is True
        assert [u for u, _ in sess.skip_posts] == [_SKIP_URL]


class TestNoLoop:
    @pytest.mark.asyncio
    async def test_the_page_coming_back_gets_no_second_post(self) -> None:
        again = f"{_PAGE}?relayState=RS2&state=ST2"
        sess = _Session(
            _PAGE_URL,
            skip_response=_Resp(_SKIP_URL, status=302, location=again),
            get_routes={again: _Resp(again, text=_MARKETING_HTML)},
        )
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        with pytest.raises(MarketingConsentError):
            await conn.login("user@example.com", "secret")
        assert len(sess.skip_posts) == 1
        assert conn.last_login_interaction == "marketing_consent"

    @pytest.mark.parametrize("status", [200, 400, 500])
    @pytest.mark.asyncio
    async def test_a_decline_without_a_redirect_falls_through(
        self, status: int
    ) -> None:
        sess = _Session(
            _PAGE_URL,
            skip_response=_Resp(_SKIP_URL, status=status, text=_MARKETING_HTML),
        )
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        with pytest.raises(MarketingConsentError):
            await conn.login("user@example.com", "secret")
        assert len(sess.skip_posts) == 1
        assert sess.gets == []


class TestNoPost:
    @pytest.mark.parametrize(
        "landing",
        [
            pytest.param(f"{_PAGE}?state={_ST}", id="no-relayState"),
            pytest.param(f"{_PAGE}?relayState={_RS}", id="no-state"),
            pytest.param(f"{_PAGE}?relayState=&state={_ST}", id="empty-relayState"),
            pytest.param(_PAGE, id="no-query"),
            pytest.param(
                f"http://identity.vwgroup.io/v2/login/ui/marketing-consent"
                f"?relayState={_RS}&state={_ST}",
                id="cleartext",
            ),
            pytest.param(
                f"https://attacker.example/v2/login/ui/marketing-consent"
                f"?relayState={_RS}&state={_ST}",
                id="foreign-host",
            ),
            pytest.param(
                f"https://identity.vwgroup.io.attacker.example/v2/login/ui/"
                f"marketing-consent?relayState={_RS}&state={_ST}",
                id="lookalike-host",
            ),
            pytest.param(
                f"{_SKIP_URL}?relayState={_RS}&state={_ST}",
                id="the-skip-url-itself",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_falls_through_to_the_existing_message(self, landing: str) -> None:
        sess = _Session(landing)  # any skip POST raises inside the session
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        with pytest.raises(MarketingConsentError):
            await conn.login("user@example.com", "secret")
        assert sess.skip_posts == []
        assert sess.gets == []


class TestTheRedirectAfterTheDeclineIsPinned:
    @pytest.mark.parametrize(
        "location",
        [
            pytest.param("https://attacker.example/cb?code=x", id="foreign-host"),
            pytest.param(
                "http://eu-data-act.vwgroup-datahub.com/services/callbacklogin",
                id="cleartext",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_an_off_list_redirect_is_not_followed(self, location: str) -> None:
        sess = _Session(
            _PAGE_URL,
            skip_response=_Resp(_SKIP_URL, status=302, location=location),
        )
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        with pytest.raises(MarketingConsentError):
            await conn.login("user@example.com", "secret")
        assert len(sess.skip_posts) == 1
        assert sess.gets == [], "the off-list redirect target was fetched"


@pytest.mark.asyncio
async def test_no_query_value_reaches_the_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    again = f"{_PAGE}?relayState={_RS}&state={_ST}"
    sess = _Session(
        _PAGE_URL,
        skip_response=_Resp(_SKIP_URL, status=302, location=again),
        get_routes={again: _Resp(again, text=_MARKETING_HTML)},
    )
    conn = EUDataActConnector(sess)  # type: ignore[arg-type]
    with pytest.raises(MarketingConsentError):
        await conn.login("user@example.com", "secret")
    assert "declin" in caplog.text or "marketing question" in caplog.text
    assert _RS not in caplog.text
    assert _ST not in caplog.text


# ── the recogniser on its own ────────────────────────────────────────────────
def test_the_recogniser_builds_the_skip_target_from_the_page_itself() -> None:
    assert _marketing_consent_skip_request(_PAGE_URL) == (
        _SKIP_URL,
        [("relayState", _RS), ("state", _ST)],
    )


@pytest.mark.parametrize(
    "url",
    [
        f"{_SKIP_URL}?relayState={_RS}&state={_ST}",
        f"https://identity.vwgroup.io@attacker.example/v2/login/ui/marketing-consent"
        f"?relayState={_RS}&state={_ST}",
        "https://identity.vwgroup.io/signin-service/v1/CLIENT/consent/marketing"
        f"?relayState={_RS}&state={_ST}",
        f"https://identity.vwgroup.io/v2/login/ui/terms-and-conditions"
        f"?relayState={_RS}&state={_ST}",
    ],
)
def test_the_recogniser_refuses_other_pages(url: str) -> None:
    assert _marketing_consent_skip_request(url) is None
