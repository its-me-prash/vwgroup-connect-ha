# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1679 — the volkswagen.de authproxy only answers over HTTP/2.

Over HTTP/1.1 every ``/app/authproxy/*`` path returns 502, so the channel was
dead for everyone while browsers worked. @eurojojo proved it with a client
matrix (curl over h2 → 302, ``curl --http1.1`` / urllib / aiohttp with
byte-identical headers → 502), @fschulte2812 (#1313) got the whole channel back
with an h2 transport including the plug-in-hybrid charge level, and @Joassens
(#1659) confirmed credential login plus e-mail code over h2. aiohttp 3.13.5
speaks HTTP/1.1 only — the string "http2" does not occur anywhere in the
package — so the transport has to come from elsewhere.

These tests exercise the PLUMBING, which is the part that can be wrong: the
cookie bridge to the aiohttp jar (so persisted cookies keep working), the
redirect chain and its history, the body handling across a 303 vs a 307, and
the exception mapping onto the errors the call sites already catch. Protocol
negotiation itself is httpx's job and is not re-tested here.
"""
from __future__ import annotations

import ssl

import aiohttp
import httpx
import pytest
from aiohttp import ClientError, ClientTimeout, TooManyRedirects
from yarl import URL

from custom_components.vag_connect.cariad.auth._http2 import (
    H2Session,
    H2TooManyRedirects,
    H2TransportError,
)

SITE = "https://www.volkswagen.de/app/authproxy/login"


def _session() -> aiohttp.ClientSession:
    """An aiohttp session with an unsafe jar, exactly as the connector gets."""
    return aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))


def _h2(session: aiohttp.ClientSession, handler) -> H2Session:
    return H2Session(session, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_a_plain_get_returns_status_url_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.volkswagen.de"
        return httpx.Response(200, text="<html>hello</html>")

    session = _session()
    try:
        async with _h2(session, handler).get(
            SITE, headers={"Accept": "text/html"},
            timeout=ClientTimeout(total=5),
        ) as resp:
            assert resp.status == 200
            assert str(resp.url) == SITE
            assert "hello" in await resp.text(errors="replace")
            assert resp.history == ()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_query_params_are_applied() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, text="")

    session = _session()
    try:
        async with _h2(session, handler).get(
            SITE, params={"client_id": "abc", "state": "xyz"}
        ):
            pass
        assert seen == {"client_id": "abc", "state": "xyz"}
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_cookies_from_the_aiohttp_jar_are_sent() -> None:
    """The jar stays the single source of truth — it is what gets persisted
    between restarts, so a request must carry what it holds."""
    sent: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers.get("cookie"))
        return httpx.Response(200, text="")

    session = _session()
    try:
        jar_cookie: dict[str, str] = {"auth0": "SSOVALUE", "csrf": "TOKEN"}
        session.cookie_jar.update_cookies(jar_cookie, URL(SITE))
        async with _h2(session, handler).get(SITE):
            pass
        assert sent and sent[0]
        assert "auth0=SSOVALUE" in sent[0]
        assert "csrf=TOKEN" in sent[0]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_set_cookie_lands_in_the_aiohttp_jar() -> None:
    """...and the other direction: what the server sets must end up where the
    export/import code looks for it, or a login would not survive a restart."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers=[("set-cookie", "auth0=FRESH; Path=/"),
                          ("set-cookie", "other=2; Path=/")], text="")

    session = _session()
    try:
        async with _h2(session, handler).get(SITE):
            pass
        stored = session.cookie_jar.filter_cookies(URL(SITE))
        assert stored["auth0"].value == "FRESH"
        assert stored["other"].value == "2"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_redirect_chain_is_followed_and_recorded() -> None:
    """The connector logs the hostname chain from ``resp.history`` — a
    repeating A → B → A → B is the signature of a stuck session resume — so the
    hops have to be there, in order, each with a url."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.volkswagen.de":
            return httpx.Response(
                302, headers={"location": "https://identity.vwgroup.io/u/login"})
        if request.url.path == "/u/login":
            return httpx.Response(
                302, headers={"location": "https://identity.vwgroup.io/u/final"})
        return httpx.Response(200, text="done")

    session = _session()
    try:
        async with _h2(session, handler).get(SITE, max_redirects=10) as resp:
            assert resp.status == 200
            assert str(resp.url).endswith("/u/final")
            hosts = [URL(str(h.url)).host for h in resp.history]
            assert hosts == ["www.volkswagen.de", "identity.vwgroup.io"]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_relative_location_is_resolved_against_the_current_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(302, headers={"location": "/app/authproxy/next"})
        return httpx.Response(200, text="ok")

    session = _session()
    try:
        async with _h2(session, handler).get(SITE) as resp:
            assert str(resp.url) == "https://www.volkswagen.de/app/authproxy/next"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_exceeding_the_budget_raises_what_the_call_sites_catch() -> None:
    """The connector already has ``except TooManyRedirects`` handlers that turn
    this into an ordinary auth failure. A new exception type would have walked
    straight past them."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": SITE})

    session = _session()
    try:
        with pytest.raises(TooManyRedirects) as err:
            async with _h2(session, handler).get(SITE, max_redirects=3):
                pass
        assert isinstance(err.value, H2TooManyRedirects)
        assert len(err.value.history) == 3
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_redirects_can_be_switched_off() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://elsewhere.test/"})

    session = _session()
    try:
        async with _h2(session, handler).get(
            SITE, allow_redirects=False
        ) as resp:
            assert resp.status == 302
            assert resp.headers["location"] == "https://elsewhere.test/"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_303_drops_the_body_and_a_307_keeps_it() -> None:
    """The credential POST lands on a 302/303 in the real flow; re-POSTing the
    password to the redirect target would be both wrong and a secret leak."""
    seen: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.content))
        if len(seen) == 1:
            return httpx.Response(
                303, headers={"location": "https://www.volkswagen.de/after"})
        return httpx.Response(200, text="ok")

    session = _session()
    try:
        async with _h2(session, handler).post(
            SITE, data={"password": "s3cret", "_csrf": "t"}
        ) as resp:
            assert resp.status == 200
        assert seen[0][0] == "POST" and b"password" in seen[0][1]
        assert seen[1][0] == "GET" and seen[1][1] == b""
    finally:
        await session.close()

    seen.clear()

    def handler307(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.content))
        if len(seen) == 1:
            return httpx.Response(
                307, headers={"location": "https://www.volkswagen.de/after"})
        return httpx.Response(200, text="ok")

    session = _session()
    try:
        async with _h2(session, handler307).post(SITE, data={"a": "b"}):
            pass
        assert seen[1][0] == "POST" and b"a=b" in seen[1][1]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_transport_failure_is_an_ordinary_client_error() -> None:
    """A network fault has to keep being "channel unavailable" rather than an
    unhandled exception in the poll loop."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    session = _session()
    try:
        with pytest.raises(ClientError) as err:
            async with _h2(session, handler).get(SITE):
                pass
        assert isinstance(err.value, H2TransportError)
        # the host may be logged, the password or cookies never
        assert "volkswagen.de" in str(err.value)
        assert "no route" not in str(err.value)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_the_jar_is_passed_through_not_copied() -> None:
    """``export_cookies``/``import_cookies`` reach the jar through the session
    object, so the adapter must expose the very same jar."""
    session = _session()
    try:
        adapter = H2Session(session)
        assert adapter.cookie_jar is session.cookie_jar
        assert adapter.closed is False
    finally:
        await session.close()


def test_the_two_alpn_buckets_are_genuinely_different_objects() -> None:
    """The premise the fix rests on, checked before the fix is checked.

    HA 2026.2 keys the context cache on the ALPN set (core PR #161330). That is
    the whole reason we may now ask HA for a context at all: the one we get for
    ``h2`` is a DIFFERENT object from the ``http/1.1`` one its aiohttp
    connector uses, so httpx mutating ours cannot reach aiohttp's.

    If a future HA collapsed those two into one object, the test below would
    still pass while #1679 came back process-wide — so the bucketing itself is
    asserted here rather than assumed.
    """
    from homeassistant.util.ssl import (
        SSL_ALPN_HTTP11,
        SSL_ALPN_HTTP11_HTTP2,
        SSLCipherList,
        client_context,
    )

    h2 = client_context(SSLCipherList.PYTHON_DEFAULT, SSL_ALPN_HTTP11_HTTP2)
    h11 = client_context(SSLCipherList.PYTHON_DEFAULT, SSL_ALPN_HTTP11)
    assert isinstance(h2, ssl.SSLContext)
    assert h2 is not h11, (
        "HA no longer buckets its SSL contexts per ALPN set — handing httpx a "
        "context aiohttp also uses reintroduces #1679 for the whole process"
    )
    # Cached, so no certificate is read per request chain.
    assert client_context(SSLCipherList.PYTHON_DEFAULT, SSL_ALPN_HTTP11_HTTP2) is h2


@pytest.mark.asyncio
async def test_httpx_is_handed_the_h2_bucket_and_never_aiohttps(monkeypatch) -> None:
    """The ALPN trap, pinned where it can actually bite: the live call.

    httpx calls ``set_alpn_protocols`` on whatever context it is given. Ask for
    the ``http/1.1`` bucket — a one-word slip, and exactly the line HA's own
    ``aiohttp_client`` contains, so a plausible thing to copy — and httpx
    rewrites the context every other integration's HTTPS runs on. @eurojojo saw
    that as a bogus "invalid credentials" on an unrelated login.

    Captured from the real construction path (no injected transport), so this
    fails if the bucket changes, if ``verify`` stops being passed, or if
    ``http2`` is dropped. Identity, not a string search: an assertion on the
    source text passes against a context that merely looks right.
    """
    from homeassistant.util.ssl import (
        SSL_ALPN_HTTP11,
        SSL_ALPN_HTTP11_HTTP2,
        SSLCipherList,
        client_context,
    )

    from custom_components.vag_connect.cariad.auth import _http2

    captured: dict[str, object] = {}
    real_client = _http2.httpx.AsyncClient

    def _recorder(**kw: object) -> httpx.AsyncClient:
        captured.update(kw)
        # Swap the socket out, keep everything else the code chose.
        kw.pop("verify", None)
        kw.pop("http2", None)
        return real_client(
            transport=httpx.MockTransport(
                lambda _r: httpx.Response(200, text="ok")
            ),
            **kw,
        )

    monkeypatch.setattr(_http2.httpx, "AsyncClient", _recorder)

    session = _session()
    try:
        # No transport argument: this is the production branch that picks a
        # context, which the rest of this file's tests deliberately bypass.
        async with H2Session(session).get(SITE) as resp:
            assert resp.status == 200
    finally:
        await session.close()

    assert captured.get("http2") is True, (
        "h2 was not requested; volkswagen.de answers 502 over HTTP/1.1"
    )
    handed = captured.get("verify")
    assert handed is client_context(
        SSLCipherList.PYTHON_DEFAULT, SSL_ALPN_HTTP11_HTTP2
    ), "httpx must get the h2 ALPN bucket"
    assert handed is not client_context(
        SSLCipherList.PYTHON_DEFAULT, SSL_ALPN_HTTP11
    ), "that is the context aiohttp uses — mutating it is #1679 process-wide"


def test_the_context_is_no_longer_built_by_hand() -> None:
    """A secondary guard, and a weak one by nature: it only says the old
    machinery is gone. The test above is what proves the new route is right.

    Kept because the hand-built context was the thing that had to go — it did
    blocking disk I/O behind an executor hop and a lock, all of which HA's
    pre-warmed cache makes unnecessary.
    """
    import inspect

    from custom_components.vag_connect.cariad.auth import _http2

    src = inspect.getsource(_http2)
    assert "run_in_executor" not in src
    assert "create_default_context" not in src
    assert "_ensure_ctx" not in src
