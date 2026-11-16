# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A refreshed token set keeps the id token when the refresh answer has none.

An id token is optional in an OpenID Connect refresh response. Four refresh
paths built the new token set from the answer alone, so an answer without one
left an empty id token. ``TokenSet.is_valid`` needs an id token, so the token
storage refused to save that set: the file kept the previous set with its old
refresh token, and a restart came back with a refresh token the server may have
rotated away. In memory the id token was gone as well, and with it the user id,
the country and (Volkswagen North America) the S-PIN read session.

Three other paths already kept the previous id token (the browser sign-in, the
MBB recipe and Audi plug&play). The four below now do the same:

- Volkswagen North America, ``VWNAClient._refresh``;
- the ordinary refresh of ``CariadBaseClient`` (Volkswagen, Audi, SEAT, CUPRA,
  Škoda);
- the portal device grant of ``CariadBaseClient``;
- Porsche, ``PorscheClient._refresh``.

Whether a vendor's server leaves the id token out was not measured, so every
path is pinned both ways: without an id token in the answer the previous one
stays, with one the new one is taken.

The Volkswagen North America path also sends the id token to start an S-PIN
read session. A kept id token ages, and a refused session exchange is retried
once and then switches that path off with a warning that the S-PIN may be
wrong, so an id token that has run out is no longer sent there.
"""
from __future__ import annotations

import base64
import copy
import json
import time
from typing import Any

import pytest

from custom_components.vag_connect.cariad.api import porsche as porsche_api
from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
from custom_components.vag_connect.cariad.api.vw_na import VWNAClient
from custom_components.vag_connect.cariad.auth import _audi_market_config
from custom_components.vag_connect.cariad.auth import _device_grant
from custom_components.vag_connect.cariad.auth._token_storage import TokenStorage
from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.models import TokenSet

_SUB = "00000000-0000-4000-8000-000000000001"  # synthetic account id
_VIN = "WVWZZZE1ZTP000001"  # synthetic, padded counter serial


def _jwt(claims: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{body}.sig"


_SIGN_IN_ID = _jwt({"sub": _SUB, "n": "sign-in"})
_REFRESH_ID = _jwt({"sub": _SUB, "n": "refresh"})


# ── the token file ───────────────────────────────────────────────────────────


class _TokenFile:
    """What Home Assistant's Store is to the token storage, as JSON text, so
    anything that does not survive a file does not survive here either."""

    def __init__(self) -> None:
        self.text: str | None = None

    async def async_load(self) -> dict[str, Any] | None:
        return None if self.text is None else json.loads(self.text)

    async def async_save(self, data: dict[str, Any]) -> None:
        self.text = json.dumps(data)

    async def async_remove(self) -> None:
        self.text = None

    def tokens(self) -> dict[str, Any]:
        return dict((json.loads(self.text) if self.text else {}).get("tokens") or {})


# ── the wire ─────────────────────────────────────────────────────────────────


class _Resp:
    url = "https://wire.invalid/"
    headers: dict[str, str] = {}
    history: tuple[Any, ...] = ()

    def __init__(self, status: int, body: Any = None) -> None:
        self.status = status
        self._body = {} if body is None else body

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def json(self, *a: Any, **k: Any) -> Any:
        return copy.deepcopy(self._body)

    async def text(self, *a: Any, **k: Any) -> str:
        return json.dumps(self._body)


def _is_refresh(url: str, kwargs: dict[str, Any]) -> bool:
    form = kwargs.get("data")
    if isinstance(form, dict) and form.get("grant_type") == "refresh_token":
        return True  # OAuth form: CARIAD BFF, OLA, the North America host
    body = kwargs.get("json")
    return isinstance(body, dict) and "token" in body and "refresh-token" in url


class _Wire:
    """Answers refresh grants (with or without an id token), a 401 on the
    first ``reads_401`` reads, the North America garage, and records every
    refresh token presented and every URL read."""

    def __init__(self, *, id_token_in_refresh: bool) -> None:
        self.id_token_in_refresh = id_token_in_refresh
        self.presented: list[str] = []
        self.urls: list[str] = []
        self.reads_401 = 0

    def _refresh(self, kwargs: dict[str, Any]) -> _Resp:
        form = kwargs.get("data") or kwargs.get("json") or {}
        self.presented.append(str(form.get("refresh_token") or form.get("token") or ""))
        n = len(self.presented)
        body: dict[str, Any] = {
            "access_token": f"access-refresh{n}",
            "refresh_token": f"refresh-refresh{n}",
        }
        if self.id_token_in_refresh:
            body["id_token"] = _REFRESH_ID
        return _Resp(200, body)

    def post(self, url: str, **kwargs: Any) -> _Resp:
        if _is_refresh(str(url), kwargs):
            return self._refresh(kwargs)
        self.urls.append(f"POST {url}")
        return _Resp(200, {})

    def get(self, url: str, **kwargs: Any) -> _Resp:
        return self.request("GET", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:
        if _is_refresh(str(url), kwargs):
            return self._refresh(kwargs)
        self.urls.append(f"{method} {url}")
        if self.reads_401 > 0:
            self.reads_401 -= 1
            return _Resp(401)
        if str(url).endswith("/account/v1/garage"):
            return _Resp(200, {"data": {"vehicles": [
                {"vin": _VIN, "vehicleId": "uuid-0001", "modelName": "ID.4"},
            ]}})
        return _Resp(200, {})


@pytest.fixture(autouse=True)
def _password_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """The IDK password sign-in cut down to its result. The page walk is not
    what is measured here."""

    async def _signin(self: Any, email: str, password: str, **kw: Any) -> TokenSet:
        return TokenSet(
            access_token="access-signin",
            refresh_token="refresh-signin",
            id_token=_SIGN_IN_ID,
            code_verifier="verifier-signin",
        )

    monkeypatch.setattr(IDKAuth, "authenticate", _signin)


@pytest.fixture(autouse=True)
def _no_market_config_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audi's refresh also fetches a market config from a CDN. It has nothing
    to do with the id token and is taken off the wire."""

    async def _nothing(*a: Any, **k: Any) -> dict[str, str]:
        return {}

    monkeypatch.setattr(_audi_market_config, "fetch_audi_market_config", _nothing)


# ── 1. the rule itself ───────────────────────────────────────────────────────


def test_a_refreshed_set_without_an_id_token_takes_the_previous_one() -> None:
    previous = TokenSet(access_token="a0", refresh_token="r0", id_token="id-0")
    fresh = TokenSet(access_token="a1", refresh_token="r1", id_token="")
    assert fresh.keep_id_token_from(previous) is fresh
    assert fresh.id_token == "id-0"
    assert fresh.is_valid()
    # nothing else is taken from the previous set
    assert (fresh.access_token, fresh.refresh_token) == ("a1", "r1")


def test_a_refreshed_set_with_its_own_id_token_keeps_it() -> None:
    previous = TokenSet(access_token="a0", refresh_token="r0", id_token="id-0")
    fresh = TokenSet(access_token="a1", refresh_token="r1", id_token="id-1")
    assert fresh.keep_id_token_from(previous).id_token == "id-1"


@pytest.mark.parametrize("previous", [None, TokenSet("a0", "r0", "")])
def test_nothing_to_keep_leaves_the_set_as_it_came(previous: TokenSet | None) -> None:
    fresh = TokenSet(access_token="a1", refresh_token="r1", id_token="")
    assert fresh.keep_id_token_from(previous).id_token == ""


# ── 2. Volkswagen North America, through the real refresh and storage ────────


def _vwna(wire: _Wire, token_file: _TokenFile) -> tuple[VWNAClient, TokenStorage]:
    client = VWNAClient(wire, "owner@example.invalid", "pw", "", country="us")  # type: ignore[arg-type]
    storage = TokenStorage(token_file)
    client.on_tokens_changed = storage.save
    return client, storage


@pytest.mark.parametrize("id_token_in_refresh", [False, True])
async def test_vw_na_writes_the_refreshed_set_and_a_restart_renews_with_it(
    id_token_in_refresh: bool,
) -> None:
    token_file = _TokenFile()
    wire = _Wire(id_token_in_refresh=id_token_in_refresh)
    client, _ = _vwna(wire, token_file)
    await client.authenticate()

    wire.reads_401 = 1  # the access token has run out
    assert await client.get_vehicles() == [_VIN]

    expected_id = _REFRESH_ID if id_token_in_refresh else _SIGN_IN_ID
    # The file first: before the change it kept the sign-in's set, because
    # the storage refused the refreshed one.
    stored = token_file.tokens()
    assert stored.get("refresh_token") == "refresh-refresh1"
    assert stored.get("id_token") == expected_id
    assert client._tokens is not None and client._tokens.id_token == expected_id

    # A restart takes the stored set and renews with the refresh token the
    # last refresh brought, not with the one from the sign-in.
    restarted, storage = _vwna(wire, token_file)
    restarted.set_persisted_tokens(await storage.load())
    wire.reads_401 = 1
    assert await restarted.get_vehicles() == [_VIN]
    assert wire.presented == ["refresh-signin", "refresh-refresh1"]


# ── 3. Volkswagen North America: an expired id token starts no S-PIN session ─


def _spin_client(id_token: str, wire: _Wire) -> VWNAClient:
    client = VWNAClient(wire, "owner@example.invalid", "pw", "1234", country="us")  # type: ignore[arg-type]
    client._tokens = TokenSet(access_token="a", refresh_token="r", id_token=id_token)
    client._user_id = _SUB
    return client


async def test_vw_na_does_not_send_an_expired_id_token_to_the_s_pin_session() -> None:
    wire = _Wire(id_token_in_refresh=True)
    client = _spin_client(_jwt({"sub": _SUB, "exp": int(time.time()) - 3600}), wire)
    assert await client._get_read_session_token(_VIN) is None
    assert not [u for u in wire.urls if "/challenge" in u], wire.urls
    assert not getattr(client, "_spin_read_session_disabled", False)


@pytest.mark.parametrize("claims", [
    {"sub": _SUB, "exp": int(time.time()) + 3600},  # still valid
    {"sub": _SUB},                                   # no exp claim: as before
])
async def test_vw_na_still_starts_the_s_pin_session_with_a_usable_id_token(
    claims: dict[str, Any],
) -> None:
    wire = _Wire(id_token_in_refresh=True)
    client = _spin_client(_jwt(claims), wire)
    await client._get_read_session_token(_VIN)
    assert [u for u in wire.urls if "/challenge" in u], wire.urls


def test_an_id_token_that_cannot_be_read_counts_as_not_expired() -> None:
    assert VWNAClient._id_token_expired("not-a-jwt") is False
    assert VWNAClient._id_token_expired(_jwt({"exp": "soon"})) is False
    assert VWNAClient._id_token_expired(_jwt({"exp": True})) is False


# ── 4. the ordinary refresh of the base client ───────────────────────────────

_BASE_BRANDS = ["audi", "volkswagen", "seat", "cupra", "skoda"]


async def _base_client(brand: str, wire: _Wire, token_file: _TokenFile) -> Any:
    client = CariadClientFactory.create(brand, wire, "owner@example.invalid", "pw")
    # SEAT and CUPRA otherwise read their user id from the API.
    client._auth.user_id = "user-1"
    client.on_tokens_changed = TokenStorage(token_file).save
    await client.authenticate()
    return client


@pytest.mark.parametrize("id_token_in_refresh", [False, True])
@pytest.mark.parametrize("brand", _BASE_BRANDS)
async def test_the_base_refresh_keeps_the_id_token_and_writes_the_set(
    brand: str, id_token_in_refresh: bool,
) -> None:
    token_file = _TokenFile()
    wire = _Wire(id_token_in_refresh=id_token_in_refresh)
    client = await _base_client(brand, wire, token_file)

    await client._refresh_tokens()

    expected_id = _REFRESH_ID if id_token_in_refresh else _SIGN_IN_ID
    assert client._tokens.id_token == expected_id
    stored = token_file.tokens()
    assert stored.get("refresh_token") == "refresh-refresh1"
    assert stored.get("id_token") == expected_id


# ── 5. the portal device grant of the base client ────────────────────────────


@pytest.mark.parametrize("id_token_in_refresh", [False, True])
async def test_the_portal_device_grant_refresh_keeps_the_id_token(
    monkeypatch: pytest.MonkeyPatch, id_token_in_refresh: bool,
) -> None:
    async def _grant_refresh(self: Any, refresh_token: str) -> TokenSet:
        return TokenSet(
            access_token="access-dag",
            refresh_token="refresh-dag",
            id_token=_REFRESH_ID if id_token_in_refresh else "",
            strategy="device_grant_portal",
        )

    monkeypatch.setattr(_device_grant.DeviceAuthorizationGrant, "refresh", _grant_refresh)
    token_file = _TokenFile()
    client = CariadClientFactory.create(
        "volkswagen", _Wire(id_token_in_refresh=False), "owner@example.invalid", "",
    )
    client._tokens = TokenSet(
        access_token="access-portal",
        refresh_token="refresh-portal",
        id_token=_SIGN_IN_ID,
        strategy="device_grant_portal",
    )
    client.on_tokens_changed = TokenStorage(token_file).save

    await client._refresh_tokens()

    expected_id = _REFRESH_ID if id_token_in_refresh else _SIGN_IN_ID
    assert client._tokens.id_token == expected_id
    assert client._tokens.strategy == "device_grant_portal"
    stored = token_file.tokens()
    assert stored.get("refresh_token") == "refresh-dag"
    assert stored.get("id_token") == expected_id


# ── 6. Porsche ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("id_token_in_refresh", [False, True])
async def test_porsche_refresh_keeps_the_id_token_and_writes_the_set(
    monkeypatch: pytest.MonkeyPatch, id_token_in_refresh: bool,
) -> None:
    async def _porsche_refresh(self: Any, refresh_token: str) -> TokenSet:
        return TokenSet(
            access_token="access-porsche-2",
            refresh_token="refresh-porsche-2",
            id_token=_REFRESH_ID if id_token_in_refresh else "",
        )

    monkeypatch.setattr(porsche_api.PorscheAuth, "refresh", _porsche_refresh)
    token_file = _TokenFile()
    client = porsche_api.PorscheClient(
        _Wire(id_token_in_refresh=False), "owner@example.invalid", "pw",  # type: ignore[arg-type]
    )
    client._tokens = TokenSet(
        access_token="access-porsche-1",
        refresh_token="refresh-porsche-1",
        id_token=_SIGN_IN_ID,
        strategy="porsche",
    )
    client.on_tokens_changed = TokenStorage(token_file).save

    await client._refresh()

    expected_id = _REFRESH_ID if id_token_in_refresh else _SIGN_IN_ID
    assert client._tokens.id_token == expected_id
    stored = token_file.tokens()
    assert stored.get("refresh_token") == "refresh-porsche-2"
    assert stored.get("id_token") == expected_id
