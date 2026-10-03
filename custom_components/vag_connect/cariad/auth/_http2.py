# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP/2 transport for the volkswagen.de authproxy channel.

**Why this module exists.** As of 2026-10-03 ``www.volkswagen.de/app/authproxy/*``
answers only over HTTP/2. Over HTTP/1.1 every authproxy path returns **502** —
login, logout, the user endpoint, the vehicle reads, all of them. ``aiohttp``,
which this integration uses for every other request, speaks HTTP/1.1 only, so
the channel was dead for everyone while browsers (which negotiate h2 via ALPN)
worked fine.

Found and proven by @eurojojo in #1679 with a client matrix — ``curl`` over h2
returns the expected 302, ``curl --http1.1``, ``urllib`` and ``aiohttp`` with
byte-identical headers all return 502 — then independently confirmed by
@fschulte2812 (#1313: the whole channel back, including the plug-in-hybrid
charge level, with no re-login) and @Joassens (#1659: credential login plus
e-mail code over h2). Normal pages such as ``/de.html`` serve over both
protocols, and identity.vwgroup.io and the CARIAD BFF are unaffected, so this
is scoped to the authproxy.

**Design.** A thin adapter around the connector's OWN aiohttp session, mimicking
just the surface that connector uses: ``.get`` / ``.post`` as async context
managers, a response carrying ``status`` / ``url`` / ``history`` / ``headers``
/ ``text()`` / ``json()``, and ``cookie_jar`` passed straight through. That
keeps all seven call sites and — more importantly — the cookie export/import
code untouched: cookies continue to live in the aiohttp jar, which is what gets
persisted between restarts.

**The SSL-context trap, and why the context here is built from scratch.**
``httpx`` calls ``set_alpn_protocols(["http/1.1", "h2"])`` on whatever context
it is handed. Hand it Home Assistant's SHARED context and every *other* aiohttp
connection in the process starts negotiating h2 and dies with a garbled status
line — @eurojojo hit exactly that, and it surfaced as a bogus "invalid
credentials" on the primary login, which is the worst possible symptom because
it sends people chasing their own password. So this module builds its own
context, in an executor (``ssl.create_default_context`` does blocking file I/O
to load the CA bundle).

**Redirects are followed here, not by httpx**, because the connector reads
``resp.history`` to log the hostname chain — a repeating A → B → A → B is the
signature of a stuck session resume — and because exceeding the budget has to
raise the same ``TooManyRedirects`` the call sites already catch.
"""
from __future__ import annotations

import asyncio
import logging
import ssl
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from typing import Any
from collections.abc import AsyncIterator, Mapping

import httpx
from aiohttp import ClientError, ClientSession, ClientTimeout, TooManyRedirects
from yarl import URL

_LOGGER = logging.getLogger(__name__)

#: Methods that keep their body across a 307/308 but not across a 301/302/303.
_BODY_PRESERVING = frozenset({307, 308})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class H2TooManyRedirects(TooManyRedirects):
    """``TooManyRedirects`` the call sites already catch, without aiohttp's
    ``RequestInfo`` plumbing.

    The connector catches ``TooManyRedirects`` and reads ``.history`` off it
    (defensively, via ``getattr``), so a subclass that carries a history and
    skips the parent's required arguments keeps every existing handler working.
    """

    def __init__(self, history: tuple[Any, ...] = ()) -> None:  # noqa: D107
        Exception.__init__(self, "too many redirects")
        self.history = history


class H2TransportError(ClientError):
    """An httpx transport failure, re-raised as the ``ClientError`` the call
    sites already expect — so a network fault keeps being an ordinary
    "channel unavailable", never an unhandled exception in the poll loop."""


class _H2Response:
    """The slice of an aiohttp response the authproxy connector actually uses.

    Deliberately NOT a general-purpose shim: only ``status``, ``url``,
    ``history``, ``headers``, ``text()`` and ``json()`` are provided, because
    those are the only members the connector touches (verified by reading all
    seven call sites). Anything else should fail loudly rather than silently
    return something plausible.
    """

    def __init__(self, resp: httpx.Response, history: tuple[_H2Response, ...]) -> None:
        self._resp = resp
        self.status = resp.status_code
        self.url = URL(str(resp.url))
        self.history = history
        self.headers = resp.headers

    async def text(self, errors: str = "strict") -> str:
        """Decoded body. ``errors`` mirrors aiohttp's keyword; httpx decodes
        with its own charset detection, so a replacement pass is only needed
        when the caller asked to tolerate junk."""
        try:
            return self._resp.text
        except UnicodeDecodeError:
            if errors == "strict":
                raise
            return self._resp.content.decode("utf-8", errors=errors)

    async def json(self) -> Any:
        return self._resp.json()


class H2Session:
    """aiohttp-shaped session that speaks HTTP/2, sharing the aiohttp cookie jar.

    Wrap the connector's own session once in ``__init__`` and every call site
    keeps working unchanged::

        self._session = H2Session(session)

    Cookies are NOT managed by httpx: they are read out of the aiohttp jar
    before each hop and written back after it, so the jar stays the single
    source of truth that the persistence code already exports.
    """

    def __init__(
        self,
        session: ClientSession,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._aiohttp = session
        self._ctx: ssl.SSLContext | None = None
        self._lock = asyncio.Lock()
        #: Test seam only. With a transport injected no socket is opened and no
        #: SSL context is built, so the cookie bridge, the redirect chain and
        #: the exception mapping can be exercised without a live server.
        self._transport = transport

    # ── the two attributes the connector reaches for besides get/post ──────

    @property
    def cookie_jar(self) -> Any:
        """The aiohttp jar, unchanged — cookie export/import keeps working."""
        return self._aiohttp.cookie_jar

    @property
    def closed(self) -> bool:
        return self._aiohttp.closed

    async def close(self) -> None:
        """Close the wrapped aiohttp session.

        Callers hold the adapter, not the session underneath it, so every
        member they use has to be here — found by a test that closes the
        connector's session through ``conn._session.close()``. There is no
        httpx client to close: one lives per request chain and is closed by its
        own context manager.
        """
        await self._aiohttp.close()

    async def _ensure_ctx(self) -> ssl.SSLContext:
        """The module's OWN SSL context, built once, in an executor.

        Never Home Assistant's shared context: httpx sets ALPN on whatever it
        is handed, and that breaks every other aiohttp connection in the
        process (#1679). ``create_default_context`` reads the CA bundle from
        disk, hence the executor.
        """
        async with self._lock:
            if self._ctx is None:
                loop = asyncio.get_running_loop()
                self._ctx = await loop.run_in_executor(
                    None, ssl.create_default_context
                )
            return self._ctx

    # ── cookie bridge ─────────────────────────────────────────────────────

    def _cookie_header(self, url: str) -> str | None:
        try:
            filtered = self.cookie_jar.filter_cookies(URL(url))
        except Exception:  # noqa: BLE001  # a jar hiccup must not kill the poll
            _LOGGER.debug("HTTP/2: cookie filter failed for %s", URL(url).host)
            return None
        pairs = [f"{name}={morsel.value}" for name, morsel in filtered.items()]
        return "; ".join(pairs) if pairs else None

    def _store_cookies(self, resp: httpx.Response) -> None:
        raw = resp.headers.get_list("set-cookie")
        if not raw:
            return
        for header in raw:
            jar_cookie: SimpleCookie = SimpleCookie()
            try:
                jar_cookie.load(header)
            except Exception:  # noqa: BLE001  # malformed Set-Cookie: skip it
                continue
            try:
                self.cookie_jar.update_cookies(jar_cookie, URL(str(resp.url)))
            except Exception:  # noqa: BLE001
                _LOGGER.debug("HTTP/2: could not store a cookie from %s",
                              URL(str(resp.url)).host)

    # ── request plumbing ──────────────────────────────────────────────────

    @asynccontextmanager
    async def get(self, url: str, **kw: Any) -> AsyncIterator[_H2Response]:
        async with self._request("GET", url, **kw) as resp:
            yield resp

    @asynccontextmanager
    async def post(self, url: str, **kw: Any) -> AsyncIterator[_H2Response]:
        async with self._request("POST", url, **kw) as resp:
            yield resp

    @asynccontextmanager
    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        data: Any = None,
        json: Any = None,
        allow_redirects: bool = True,
        max_redirects: int = 10,
        timeout: ClientTimeout | float | None = None,
        **_ignored: Any,
    ) -> AsyncIterator[_H2Response]:
        total = (
            timeout.total if isinstance(timeout, ClientTimeout) else timeout
        ) or 30.0
        history: list[_H2Response] = []
        target = str(URL(url).with_query(params) if params else URL(url))
        body, send_json = data, json
        hops = 0

        # One client per request CHAIN, not per session and not per hop. The
        # connector has no close hook — its session is closed by the caller —
        # so a client living on the adapter would leak a connection pool; a
        # client per hop would re-handshake on every step of a ten-hop SSO
        # chain. Bound to this context manager it does neither, and the SSL
        # context is cached across chains so the CA bundle is read once.
        client_kw: dict[str, Any] = {"follow_redirects": False}
        if self._transport is not None:
            client_kw["transport"] = self._transport
        else:
            client_kw["http2"] = True
            client_kw["verify"] = await self._ensure_ctx()
        try:
            client = httpx.AsyncClient(**client_kw)
        except ImportError as exc:
            # httpx only gains HTTP/2 through its `h2` extra. The integration
            # declares h2 in its requirements, but an image where that install
            # was skipped would otherwise raise a bare ImportError out of the
            # poll loop — say what is actually missing instead.
            raise H2TransportError(
                "HTTP/2 support is unavailable: the 'h2' package is missing, "
                "so the volkswagen.de channel cannot be reached (it no longer "
                "answers over HTTP/1.1)"
            ) from exc
        async with client:
            async for resp in self._hops(
                client, method, target, headers, body, send_json,
                allow_redirects, max_redirects, float(total), history, hops,
            ):
                yield resp
            return

    async def _hops(  # noqa: PLR0913
        self,
        client: httpx.AsyncClient,
        method: str,
        target: str,
        headers: Mapping[str, str] | None,
        body: Any,
        send_json: Any,
        allow_redirects: bool,
        max_redirects: int,
        total: float,
        history: list[_H2Response],
        hops: int,
    ) -> AsyncIterator[_H2Response]:
        while True:
            req_headers = dict(headers or {})
            cookie = self._cookie_header(target)
            if cookie:
                req_headers["Cookie"] = cookie
            # Body shape, mirroring what the call sites actually pass: a dict of
            # form fields (the credential and OTP POSTs) goes out form-encoded,
            # anything else as a raw body. A GET carries neither.
            body_kw: dict[str, Any] = {}
            if send_json is not None:
                body_kw["json"] = send_json
            elif isinstance(body, Mapping):
                body_kw["data"] = dict(body)
            elif body is not None:
                body_kw["content"] = body

            try:
                # httpx keeps its own jar; the aiohttp jar is the only source of
                # truth here, so never let a stale httpx cookie ride along.
                client.cookies.clear()
                resp = await client.request(
                    method, target, headers=req_headers,
                    timeout=float(total), **body_kw,
                )
            except httpx.HTTPError as exc:
                raise H2TransportError(
                    f"HTTP/2 request to {URL(target).host} failed: "
                    f"{type(exc).__name__}"
                ) from exc

            self._store_cookies(resp)
            shim = _H2Response(resp, tuple(history))

            location = resp.headers.get("location")
            if (
                not allow_redirects
                or resp.status_code not in _REDIRECT_STATUSES
                or not location
            ):
                yield shim
                return

            hops += 1
            if hops > max_redirects:
                raise H2TooManyRedirects(tuple(history))
            history.append(shim)
            target = str(URL(str(resp.url)).join(URL(location)))
            if resp.status_code not in _BODY_PRESERVING:
                method, body, send_json = "GET", None, None
