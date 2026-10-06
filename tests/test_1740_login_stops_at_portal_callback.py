# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The EU Data Act login walks its own redirect chain and stops at the callback.

Reported by @VWGroupDatahub, who runs the portal: ``/services/callbacklogin`` is
the hop that sets the authenticated session cookie, and the AEM content page it
redirects to is a round trip the login does not need. aiohttp cannot be told to
stop at a particular hop, so the chain is walked by hand.

Walking it by hand means we now own the rules a browser used to apply for us,
and those rules are what this file is about. The interesting one is not the
stopping point — it is that a 303 must not re-post the password to the next hop.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _PORTAL_BASE,
    _PORTAL_CALLBACK_PATH,
    EUDataActConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

_IDP = "https://identity.vwgroup.io"
_AUTHENTICATE = f"{_IDP}/signin-service/v1/client/login/authenticate"
_CALLBACK = f"{_PORTAL_BASE}{_PORTAL_CALLBACK_PATH}"
_AEM_PAGE = f"{_PORTAL_BASE}/content/euda/de/de/user.html"


class _Response:
    """The handful of attributes the follower reads off a response."""

    def __init__(
        self,
        url: str,
        status: int,
        *,
        location: str | None = None,
        body: str = "",
    ) -> None:
        self.url = url
        self.status = status
        self.headers = {"Location": location} if location else {}
        self._body = body

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._body


class _Session:
    """Scripted session recording every request the follower makes."""

    def __init__(self, script: dict[tuple[str, str], _Response]) -> None:
        self._script = script
        self.calls: list[dict[str, Any]] = []

    def _answer(self, method: str, url: str, kwargs: dict[str, Any]) -> _Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        try:
            return self._script[(method, url)]
        except KeyError:  # pragma: no cover - a miss is the failure itself
            raise AssertionError(f"unscripted request: {method} {url}") from None

    def get(self, url: str, **kwargs: Any) -> _Response:
        return self._answer("GET", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> _Response:
        return self._answer("POST", url, kwargs)


def _connector(script: dict[tuple[str, str], _Response]) -> tuple[Any, _Session]:
    session = _Session(script)
    return EUDataActConnector(session), session  # type: ignore[arg-type]


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────── the stop itself


def test_the_chain_stops_on_the_callback_and_never_fetches_the_page_behind_it():
    conn, session = _connector({
        ("POST", _AUTHENTICATE): _Response(
            _AUTHENTICATE, 302, location=f"{_PORTAL_BASE}/login"),
        ("GET", f"{_PORTAL_BASE}/login"): _Response(
            f"{_PORTAL_BASE}/login", 302, location=_CALLBACK),
        ("GET", _CALLBACK): _Response(
            _CALLBACK, 302, location=_AEM_PAGE, body="<html>set-cookie</html>"),
    })

    url, html, status = _run(conn._follow_login_redirects(
        "POST", _AUTHENTICATE, headers={"User-Agent": "x"}, data={"password": "s"}))

    assert (url, status) == (_CALLBACK, 302)
    assert html == "<html>set-cookie</html>"
    assert [c["url"] for c in session.calls][-1] == _CALLBACK
    assert all(_AEM_PAGE != c["url"] for c in session.calls)


def test_every_hop_turns_aiohttps_own_redirect_following_off():
    """Without this the library follows the chain itself and the stop is moot."""
    conn, session = _connector({
        ("POST", _AUTHENTICATE): _Response(
            _AUTHENTICATE, 302, location=_CALLBACK),
        ("GET", _CALLBACK): _Response(_CALLBACK, 200),
    })

    _run(conn._follow_login_redirects("POST", _AUTHENTICATE))

    assert session.calls, "no request was made at all"
    assert all(c["allow_redirects"] is False for c in session.calls)


def test_a_landing_that_is_not_a_redirect_is_returned_as_it_is():
    conn, _ = _connector({
        ("POST", _AUTHENTICATE): _Response(
            _AUTHENTICATE, 200, body="<html>wrong password</html>"),
    })

    url, html, status = _run(conn._follow_login_redirects("POST", _AUTHENTICATE))

    assert (url, status) == (_AUTHENTICATE, 200)
    assert "wrong password" in html


def test_a_redirect_without_a_location_header_does_not_loop():
    conn, session = _connector({
        ("POST", _AUTHENTICATE): _Response(_AUTHENTICATE, 302),
    })

    _, _, status = _run(conn._follow_login_redirects("POST", _AUTHENTICATE))

    assert status == 302
    assert len(session.calls) == 1


# ──────────────────────────────────────────────── the rules we took over from the browser


def test_a_303_does_not_repost_the_credentials():
    """The whole point of 303: the body belonged to the first request only."""
    conn, session = _connector({
        ("POST", _AUTHENTICATE): _Response(
            _AUTHENTICATE, 303, location=f"{_IDP}/next"),
        ("GET", f"{_IDP}/next"): _Response(f"{_IDP}/next", 200),
    })

    _run(conn._follow_login_redirects(
        "POST", _AUTHENTICATE, data={"password": "super-secret"}))

    second = session.calls[1]
    assert second["method"] == "GET"
    assert "data" not in second, "the password was carried to the next hop"


def test_a_307_keeps_the_method_and_the_body():
    conn, session = _connector({
        ("POST", _AUTHENTICATE): _Response(
            _AUTHENTICATE, 307, location=f"{_IDP}/moved"),
        ("POST", f"{_IDP}/moved"): _Response(f"{_IDP}/moved", 200),
    })

    _run(conn._follow_login_redirects(
        "POST", _AUTHENTICATE, data={"hmac": "abc"}))

    second = session.calls[1]
    assert second["method"] == "POST"
    assert second["data"] == {"hmac": "abc"}


def test_a_cross_host_hop_drops_credential_headers():
    conn, session = _connector({
        ("POST", _AUTHENTICATE): _Response(
            _AUTHENTICATE, 302, location=f"{_PORTAL_BASE}/elsewhere"),
        ("GET", f"{_PORTAL_BASE}/elsewhere"): _Response(
            f"{_PORTAL_BASE}/elsewhere", 200),
    })

    _run(conn._follow_login_redirects(
        "POST",
        _AUTHENTICATE,
        headers={
            "User-Agent": "x",
            "Authorization": "Bearer leak-me",
            "Cookie": "SESSION=leak-me",
        },
    ))

    crossed = session.calls[1]["headers"]
    assert "Authorization" not in crossed
    assert "Cookie" not in crossed
    assert crossed["User-Agent"] == "x", "harmless headers must survive"
    assert crossed["Referer"] == _AUTHENTICATE


def test_a_same_host_hop_keeps_them():
    conn, session = _connector({
        ("POST", f"{_IDP}/a"): _Response(f"{_IDP}/a", 302, location=f"{_IDP}/b"),
        ("GET", f"{_IDP}/b"): _Response(f"{_IDP}/b", 200),
    })

    _run(conn._follow_login_redirects(
        "POST", f"{_IDP}/a", headers={"Authorization": "Bearer keep-me"}))

    assert session.calls[1]["headers"]["Authorization"] == "Bearer keep-me"


def test_a_non_https_redirect_is_not_followed():
    """An app scheme or a downgrade ends the walk; it never gets a request."""
    conn, session = _connector({
        ("POST", _AUTHENTICATE): _Response(
            _AUTHENTICATE, 302, location="weconnect://authenticated#code=abc"),
    })

    url, _, status = _run(conn._follow_login_redirects("POST", _AUTHENTICATE))

    assert (url, status) == (_AUTHENTICATE, 302)
    assert len(session.calls) == 1


def test_an_endless_chain_raises_instead_of_spinning():
    conn, session = _connector({
        ("POST", f"{_IDP}/loop"): _Response(
            f"{_IDP}/loop", 302, location=f"{_IDP}/loop"),
        ("GET", f"{_IDP}/loop"): _Response(
            f"{_IDP}/loop", 302, location=f"{_IDP}/loop"),
    })

    with pytest.raises(AuthenticationError, match="redirects"):
        _run(conn._follow_login_redirects("POST", f"{_IDP}/loop"))

    assert len(session.calls) == 10, "the cap is what stopped it"


# ───────────────────────────────────────────────────────────── wiring, not shape


def test_the_login_hops_that_can_reach_the_callback_all_use_the_follower():
    """Four hops can land on the callback; the two before credentials cannot.

    Asserted on source because the alternative is driving four full login
    flows to prove a routing decision. The counter-check is the second
    assertion: if someone re-introduces library redirect following on one of
    the four, the count moves and this fails.
    """
    import inspect

    from custom_components.vag_connect.cariad.auth import _eu_data_act as mod

    src = inspect.getsource(mod)
    assert src.count("await self._follow_login_redirects(") == 4
    # step 1 (authorize) and step 2 (identifier) still let aiohttp follow —
    # neither chain reaches the portal callback.
    assert src.count("allow_redirects=True") == 2
