# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sign-in cookies have to outlive a token refresh.

After a password sign-in the client copies the identity provider's cookies out
of the HTTP session and puts them on the token set, so they are written to the
token file with it. On the next start they are loaded back into the session,
and a later sign-in can then resume the provider's session instead of starting
from nothing.

The chain that loses them, each link read in the source:

- ``authenticate()`` is the only place that puts cookies on a token set.
- The ordinary refresh replaces the whole token set with what
  ``IDKAuth.refresh`` returns, and ``_parse_tokens`` builds that from the three
  tokens alone. ``TokenSet.auth_cookies`` defaults to an empty list.
- The refreshed set is then saved, so the empty list is what the file holds.

So the cookies are in the file from the sign-in until the first refresh, which
is about an hour. While the process keeps running nothing looks wrong, because
the live session still has them. The loss shows after a restart: the file has
no cookies to load.

Everything below runs the real client, the real refresh, and the real token
storage. Two things are replaced: the HTTP session, and the file the storage
writes to. The password login itself is cut down to its two results, a token
set and a cookie in the session, because the form steps are not what is
measured here.
"""
from __future__ import annotations

import json
from http.cookies import SimpleCookie
from typing import Any

import aiohttp
import pytest
from yarl import URL

from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
from custom_components.vag_connect.cariad.auth import _audi_market_config
from custom_components.vag_connect.cariad.auth._token_storage import TokenStorage
from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.models import TokenSet

_EMAIL = "owner@example.test"
_PASSWORD = "a-real-password"

# Every brand whose password sign-in goes through ``CariadBaseClient`` and
# whose refresh takes the ordinary branch. Audi North America is one of them:
# its client is built on the same base and signs in at the provider's North
# American host, which is under the same cookie domain.
_BRANDS = ["audi", "audi_na", "volkswagen", "bentley", "seat", "cupra", "skoda"]

_IDP = URL("https://identity.vwgroup.io/")
_COOKIE = "remembered-device"
_COOKIE_VALUE = "synthetic-cookie-value"


# ─────────────────────────────────────────────────────────────────────────────
# The two things these tests replace: the HTTP session and the token file
# ─────────────────────────────────────────────────────────────────────────────


class _Resp:
    """Just enough of an aiohttp response for the token endpoints."""

    url = "https://wire.invalid/"
    headers: dict[str, str] = {}
    history: tuple[Any, ...] = ()

    def __init__(self, status: int, payload: dict[str, Any] | None = None) -> None:
        self.status = status
        self._payload = payload or {}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def json(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self._payload

    async def text(self, *a: Any, **k: Any) -> str:
        return ""


def _is_refresh(url: str, kwargs: dict[str, Any]) -> bool:
    """A refresh-token exchange, in either of the two shapes the brands use."""
    form = kwargs.get("data")
    if isinstance(form, dict) and form.get("grant_type") == "refresh_token":
        return True  # CARIAD BFF (Volkswagen, Audi, Bentley) and OLA (SEAT, CUPRA)
    body = kwargs.get("json")
    return isinstance(body, dict) and "token" in body and "refresh-token" in url


class _Wire:
    """An HTTP session with a real cookie jar that answers refreshes from a
    script and refuses everything else.

    ``refresh_answers`` is the list of HTTP statuses the token endpoint gives,
    in order. Has to be built inside a running event loop, like the jar.
    """

    def __init__(self, *refresh_answers: int) -> None:
        self._answers = list(refresh_answers)
        self.requests: list[str] = []
        self._minted = 0
        self.cookie_jar = aiohttp.CookieJar()

    def cookies(self) -> dict[str, str]:
        return {morsel.key: morsel.value for morsel in self.cookie_jar}

    def _answer(self, method: str, url: str, kwargs: dict[str, Any]) -> _Resp:
        if not _is_refresh(url, kwargs):
            self.requests.append(f"{method} other")
            return _Resp(400)
        self.requests.append("POST refresh")
        if not self._answers:
            raise AssertionError("a refresh the test did not script")
        status = self._answers.pop(0)
        if status != 200:
            return _Resp(status)
        self._minted += 1
        return _Resp(200, {
            "access_token": f"access-{self._minted}",
            "refresh_token": f"refresh-{self._minted}",
            "id_token": f"id-{self._minted}",
        })

    def post(self, url: str, **kwargs: Any) -> _Resp:
        return self._answer("POST", str(url), kwargs)

    def get(self, url: str, **kwargs: Any) -> _Resp:
        return self._answer("GET", str(url), kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:
        return self._answer(str(method).upper(), str(url), kwargs)


class _TokenFile:
    """What Home Assistant's ``Store`` is to the token storage: it keeps the
    last payload, as JSON text, so anything that does not survive a file does
    not survive here either."""

    def __init__(self) -> None:
        self.text: str | None = None

    async def async_load(self) -> dict[str, Any] | None:
        return None if self.text is None else json.loads(self.text)

    async def async_save(self, data: dict[str, Any]) -> None:
        self.text = json.dumps(data)

    async def async_remove(self) -> None:
        self.text = None


@pytest.fixture(autouse=True)
def _no_market_config_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audi's refresh also fetches a market config from a CDN, at most once a
    day per process. It has nothing to do with sign-in, and whether it fires
    depends on which test ran first, so it is taken off the wire to keep the
    request log exact."""

    async def _nothing(*a: Any, **k: Any) -> dict[str, str]:
        return {}

    monkeypatch.setattr(_audi_market_config, "fetch_audi_market_config", _nothing)


@pytest.fixture(autouse=True)
def _password_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """The password login, cut down to its two results: the identity provider
    sets a cookie on the session, and a token set with a refresh token comes
    back. The first sign-in of a test sets ``_COOKIE_VALUE``, every later one
    a value of its own, so a test can tell which sign-in a cookie is from.
    Patched on the class with ``monkeypatch``, which raises if the method is
    not there."""
    sign_ins = 0

    async def _login(self: Any, email: str, password: str, **kw: Any) -> TokenSet:
        nonlocal sign_ins
        sign_ins += 1
        value = _COOKIE_VALUE if sign_ins == 1 else f"{_COOKIE_VALUE}-{sign_ins}"
        cookie: SimpleCookie = SimpleCookie()
        cookie[_COOKIE] = value
        cookie[_COOKIE]["domain"] = "identity.vwgroup.io"
        cookie[_COOKIE]["path"] = "/"
        self._session.cookie_jar.update_cookies(cookie, response_url=_IDP)
        return TokenSet(
            access_token="access-0", refresh_token="refresh-0", id_token="id-0",
        )

    monkeypatch.setattr(IDKAuth, "authenticate", _login)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _start(brand: str, wire: _Wire, token_file: _TokenFile) -> Any:
    """One run of the integration for an entry, the way coordinator setup wires
    it: the client comes from the factory, the stored token set is loaded into
    it if there is one, the save hook is the storage, and a sign-in runs only
    when nothing was stored."""
    client = CariadClientFactory.create(brand, wire, _EMAIL, _PASSWORD)
    # SEAT and CUPRA take their user id from the login redirect and otherwise
    # read it from the API. That read is not what these tests are about.
    client._auth.user_id = "user-1"
    storage = TokenStorage(token_file)
    stored = await storage.load()
    if stored is not None:
        client.set_persisted_tokens(stored)
    client.on_tokens_changed = storage.save
    if stored is None:
        await client.authenticate()
    return client


async def _stored_cookies(token_file: _TokenFile) -> dict[str, str]:
    """The cookies in the token file, read back through the real loader."""
    stored = await TokenStorage(token_file).load()
    assert stored is not None, "the token file holds no usable token set"
    return {c["name"]: c["value"] for c in stored.auth_cookies}


# ─────────────────────────────────────────────────────────────────────────────
# Positive controls: the instrument can see cookies where they should be
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_sign_in_writes_the_cookies_to_the_token_file(brand: str) -> None:
    token_file = _TokenFile()
    wire = _Wire()

    await _start(brand, wire, token_file)

    assert wire.cookies() == {_COOKIE: _COOKIE_VALUE}
    assert await _stored_cookies(token_file) == {_COOKIE: _COOKIE_VALUE}


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_restart_before_any_refresh_gets_the_cookies_back(brand: str) -> None:
    """The intended round trip, with no refresh in between. This is the part
    that already works, and it is what shows the two tests below fail for the
    refresh and for nothing else."""
    token_file = _TokenFile()
    await _start(brand, _Wire(), token_file)

    restarted = _Wire()
    assert restarted.cookies() == {}, "a new process starts with an empty jar"
    await _start(brand, restarted, token_file)

    assert restarted.cookies() == {_COOKIE: _COOKIE_VALUE}
    assert restarted.requests == [], "the stored tokens were used, no sign-in ran"


# ─────────────────────────────────────────────────────────────────────────────
# The defect
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_refresh_keeps_the_cookies_in_the_token_file(brand: str) -> None:
    token_file = _TokenFile()
    wire = _Wire(200)
    client = await _start(brand, wire, token_file)

    await client._refresh_tokens()

    assert wire.requests == ["POST refresh"]
    stored = await TokenStorage(token_file).load()
    assert stored is not None and stored.access_token == "access-1", (
        "the refreshed token set was not the one written to the file"
    )
    # Why a running entry gives no sign of this: the session still has them.
    assert wire.cookies() == {_COOKIE: _COOKIE_VALUE}
    assert await _stored_cookies(token_file) == {_COOKIE: _COOKIE_VALUE}


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_restart_after_a_refresh_gets_the_cookies_back(brand: str) -> None:
    """What the loss costs. An entry that has been running for more than an
    hour is restarted, and the session it comes back with has to hold the
    provider's cookies, or the next sign-in starts from nothing."""
    token_file = _TokenFile()
    first = _Wire(200)
    client = await _start(brand, first, token_file)
    await client._refresh_tokens()
    assert first.requests == ["POST refresh"], "the refresh did not happen"

    restarted = _Wire()
    await _start(brand, restarted, token_file)

    assert restarted.requests == [], "the stored tokens were used, no sign-in ran"
    assert restarted.cookies() == {_COOKIE: _COOKIE_VALUE}


@pytest.mark.parametrize("brand", _BRANDS)
async def test_the_cookies_are_still_there_after_several_refreshes(brand: str) -> None:
    """An entry refreshes many times between two sign-ins. Keeping the cookies
    across the first refresh only would move the loss by an hour."""
    token_file = _TokenFile()
    wire = _Wire(200, 200, 200)
    client = await _start(brand, wire, token_file)

    for _ in range(3):
        await client._refresh_tokens()

    assert wire.requests == ["POST refresh"] * 3
    stored = await TokenStorage(token_file).load()
    assert stored is not None and stored.access_token == "access-3"
    assert await _stored_cookies(token_file) == {_COOKIE: _COOKIE_VALUE}


# ─────────────────────────────────────────────────────────────────────────────
# What keeping them must not change
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_new_sign_in_replaces_the_cookies_that_were_kept(brand: str) -> None:
    """The cookies are kept until there are newer ones, not for ever. When the
    refresh token is rejected the client signs in again, and what the file
    holds afterwards has to be what that sign-in left in the session."""
    token_file = _TokenFile()
    wire = _Wire(200, 400)
    client = await _start(brand, wire, token_file)
    await client._refresh_tokens()

    await client._refresh_tokens()

    assert wire.requests == ["POST refresh", "POST refresh"]
    assert await _stored_cookies(token_file) == {_COOKIE: f"{_COOKIE_VALUE}-2"}


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_refresh_adds_no_cookies_to_an_entry_that_has_none(brand: str) -> None:
    """A token set that came without cookies, for example one stored before
    cookies were saved at all, stays without them."""
    token_file = _TokenFile()
    await TokenStorage(token_file).save(TokenSet(
        access_token="access-0", refresh_token="refresh-0", id_token="id-0",
    ))
    wire = _Wire(200)
    client = await _start(brand, wire, token_file)

    await client._refresh_tokens()

    assert wire.requests == ["POST refresh"]
    stored = await TokenStorage(token_file).load()
    assert stored is not None and stored.access_token == "access-1"
    assert stored.auth_cookies == []
    assert wire.cookies() == {}
