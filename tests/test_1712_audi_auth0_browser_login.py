"""#1712 — Audi EU browser sign-in (myAudi Auth0 authorization code + PKCE).

The CARIAD token exchange refuses this integration with ``invalid assertion
headers`` and the device-code grant is retired for Audi (#1364). The myAudi
app's own Auth0 tenant still issues tokens to a public PKCE client with a
registered ``localhost`` callback, and its token endpoint asks for no
attestation. Ported from audiconnect/audi_connect_ha#905.

Pinned here:

* the PKCE pair and the ``/authorize`` URL carry what the tenant expects;
* the pasted callback is accepted only when it is OUR callback for THIS attempt
  (host, path, ``state``) and rejected with the right key otherwise;
* the token client posts the right grants, stamps ``strategy="audi_auth0"``,
  keeps an unrotated refresh token and the previous id_token, and classifies
  ``invalid_grant`` as dead (reauth) but anything else as transient (retry);
* the base client refreshes an ``audi_auth0`` session at Auth0 — not at the
  IDK endpoint — and a passwordless ``audi_auth0`` entry never re-runs the
  walled password login;
* the config flow routes Audi's browser login to the new step, attaches a
  sign-in for a known account to the existing entry (keeping its password for
  the portal), creates a new entry otherwise, and gives Audi reauths a choice.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from custom_components.vag_connect import config_flow as cf
from custom_components.vag_connect.cariad.api import base as _base
from custom_components.vag_connect.cariad.api.audi import AudiClient
from custom_components.vag_connect.cariad.auth import _audi_auth0 as a0
from custom_components.vag_connect.cariad.auth import _device_grant as dg
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    DeviceLoginExpiredError,
    TokenRefreshRetryError,
)
from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    CONF_USERNAME,
)

CALLBACK = "http://localhost:8080/myaudi-callback"


def _jwt(claims: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{body}.sig"


ID_TOKEN = _jwt({"sub": "auth0|abc123", "email": "Driver@Example.invalid"})

TOKEN_OK = {
    "access_token": "a0-access-1",
    "id_token": ID_TOKEN,
    "refresh_token": "a0-refresh-1",
    "token_type": "Bearer",
    "expires_in": 3600,
}


class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def json(self, content_type: Any = None) -> Any:
        return self._payload


class _Session:
    """Records every POST; answers from a queue of (status, payload)."""

    def __init__(self, *answers: tuple[int, Any]) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict[str, list[str]], dict[str, str]]] = []

    def post(self, url: str, *, data: str, headers: dict[str, str], **kw: Any) -> _Resp:
        self.calls.append((url, parse_qs(data), headers))
        if not self.answers:
            raise ConnectionError("no answer queued")
        status, payload = self.answers.pop(0)
        return _Resp(status, payload)


# ── PKCE + authorize URL ───────────────────────────────────────────────────────


def test_pkce_pair_is_s256_of_the_verifier() -> None:
    verifier, challenge, state = a0.generate_pkce()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    assert 43 <= len(verifier) <= 128
    assert challenge == expected
    assert state and state != verifier


def test_authorize_url_carries_what_the_tenant_expects() -> None:
    url = a0.build_authorization_url("cid@apps_vw-dilab_com", "chal", "st", ui_locales="da-DK")
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == a0.AUTH0_AUTHORIZE_URL
    q = parse_qs(parsed.query)
    assert q["client_id"] == ["cid@apps_vw-dilab_com"]
    assert q["audience"] == [a0.AUTH0_AUDIENCE]
    assert q["redirect_uri"] == [CALLBACK]
    assert q["response_type"] == ["code"]
    assert q["code_challenge"] == ["chal"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == ["st"]
    assert q["ui_locales"] == ["da-DK"]
    assert set(q["scope"][0].split()) >= {"openid", "offline_access"}
    # Spaces travel as %20, as the app sends them — not as "+".
    assert "+" not in parsed.query


def test_client_id_falls_back_to_the_myaudi_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    from custom_components.vag_connect.cariad.auth import _audi_market_config as mc

    monkeypatch.setattr(mc, "cached_audi_market_config", lambda: {})
    assert a0.audi_auth0_client_id() == a0.AUDI_AUTH0_CLIENT_ID
    monkeypatch.setattr(
        mc, "cached_audi_market_config",
        lambda: {"idkClientIDAndroidLive": "rotated@apps_vw-dilab_com"},
    )
    assert a0.audi_auth0_client_id() == "rotated@apps_vw-dilab_com"


# ── callback parsing ───────────────────────────────────────────────────────────


def test_callback_returns_the_code() -> None:
    assert a0.parse_callback_url(f"{CALLBACK}?code=the-code&state=st", "st") == "the-code"


def test_callback_tolerates_a_paste_without_scheme_and_with_whitespace() -> None:
    assert a0.parse_callback_url("  localhost:8080/myaudi-callback?code=c&state=st \n", "st") == "c"


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://example.invalid/?code=c&state=st", a0.ERR_INVALID_CALLBACK),
        ("http://localhost:9999/myaudi-callback?code=c&state=st", a0.ERR_INVALID_CALLBACK),
        ("http://localhost:8080/other?code=c&state=st", a0.ERR_INVALID_CALLBACK),
        (f"{CALLBACK}?code=c&state=someone-elses", a0.ERR_INVALID_CALLBACK),
        (f"{CALLBACK}?state=st", a0.ERR_INVALID_CALLBACK),
        (f"{CALLBACK}?code=c", a0.ERR_INVALID_CALLBACK),
        ("", a0.ERR_INVALID_CALLBACK),
        (f"{CALLBACK}?error=access_denied&state=st", a0.ERR_DENIED),
    ],
)
def test_callback_rejections_carry_the_right_key(url: str, key: str) -> None:
    with pytest.raises(ValueError, match=key):
        a0.parse_callback_url(url, "st")


def test_id_token_claims_never_raise() -> None:
    assert a0.id_token_claims("not-a-jwt") == {}
    assert a0.id_token_claims("a.!!!.c") == {}
    assert a0.id_token_claims(ID_TOKEN)["email"] == "Driver@Example.invalid"


# ── token client ───────────────────────────────────────────────────────────────


def test_code_exchange_posts_the_pkce_grant_and_stamps_the_strategy() -> None:
    sess = _Session((200, TOKEN_OK))
    tokens = asyncio.run(a0.AudiAuth0Grant(sess, "cid").exchange_code("the-code", "verif"))

    url, body, headers = sess.calls[0]
    assert url == a0.AUTH0_TOKEN_URL
    assert body["grant_type"] == ["authorization_code"]
    assert body["client_id"] == ["cid"]
    assert body["code"] == ["the-code"]
    assert body["code_verifier"] == ["verif"]
    assert body["redirect_uri"] == [CALLBACK]
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"

    assert tokens.strategy == "audi_auth0"
    assert tokens.access_token == "a0-access-1"
    assert tokens.refresh_token == "a0-refresh-1"
    assert tokens.id_token == ID_TOKEN
    assert tokens.is_valid()
    assert tokens.expires_at > 0


def test_code_exchange_without_refresh_token_is_a_failure() -> None:
    sess = _Session((200, {k: v for k, v in TOKEN_OK.items() if k != "refresh_token"}))
    with pytest.raises(AuthenticationError, match="refresh token"):
        asyncio.run(a0.AudiAuth0Grant(sess, "cid").exchange_code("c", "v"))


def test_code_exchange_rejection_is_an_auth_error_not_a_retry() -> None:
    sess = _Session((403, {"error": "invalid_grant", "error_description": "Invalid authorization code"}))
    with pytest.raises(AuthenticationError, match="invalid_grant"):
        asyncio.run(a0.AudiAuth0Grant(sess, "cid").exchange_code("c", "v"))


def test_refresh_posts_audience_and_scope_and_rotates() -> None:
    sess = _Session((200, dict(TOKEN_OK, access_token="a0-access-2", refresh_token="a0-refresh-2")))
    tokens = asyncio.run(a0.AudiAuth0Grant(sess, "cid").refresh("a0-refresh-1"))

    _url, body, _h = sess.calls[0]
    assert body["grant_type"] == ["refresh_token"]
    assert body["refresh_token"] == ["a0-refresh-1"]
    assert body["audience"] == [a0.AUTH0_AUDIENCE]
    assert body["scope"] == [a0.AUTH0_SCOPE]
    assert tokens.access_token == "a0-access-2"
    assert tokens.refresh_token == "a0-refresh-2"
    assert tokens.strategy == "audi_auth0"


def test_refresh_keeps_an_unrotated_refresh_token_and_the_old_id_token() -> None:
    sess = _Session((200, {"access_token": "a0-access-2", "expires_in": 600}))
    tokens = asyncio.run(
        a0.AudiAuth0Grant(sess, "cid").refresh("a0-refresh-1", id_token="old-id")
    )
    assert tokens.refresh_token == "a0-refresh-1"
    assert tokens.id_token == "old-id"
    assert tokens.is_valid(), "TokenSet.is_valid needs an id_token, or nothing gets stored"


def test_refresh_invalid_grant_means_reauth() -> None:
    sess = _Session((403, {"error": "invalid_grant", "error_description": "Unknown or invalid refresh token."}))
    with pytest.raises(AuthenticationError):
        asyncio.run(a0.AudiAuth0Grant(sess, "cid").refresh("dead"))


@pytest.mark.parametrize(
    "answer",
    [
        (503, {"error": "server_error"}),
        (429, {"error": "too_many_requests"}),
        (200, {"token_type": "Bearer"}),  # 200 without an access_token
        (400, "not json at all"),
    ],
)
def test_refresh_anything_else_is_transient(answer: tuple[int, Any]) -> None:
    sess = _Session(answer)
    with pytest.raises(TokenRefreshRetryError):
        asyncio.run(a0.AudiAuth0Grant(sess, "cid").refresh("rt"))


def test_refresh_network_failure_is_transient() -> None:
    sess = _Session()  # nothing queued → post() raises
    with pytest.raises(TokenRefreshRetryError):
        asyncio.run(a0.AudiAuth0Grant(sess, "cid").refresh("rt"))


# ── base client wiring ─────────────────────────────────────────────────────────


class _NoNet:
    def get(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise AssertionError("no network in these tests")

    def post(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise AssertionError("no network in these tests")


def _auth0_client(password: str = "") -> AudiClient:
    c = AudiClient(_NoNet(), "u@t.dk", password)
    c._tokens = TokenSet(
        access_token="STALE", refresh_token="a0-refresh-1", id_token="old-id",
        expires_at=0.0, strategy="audi_auth0",
    )
    return c


def test_an_auth0_session_refreshes_at_auth0_not_at_idk(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _auth0_client()
    seen: list[tuple[str, str]] = []

    async def _fake_refresh(self: Any, refresh_token: str, *, id_token: str = "") -> TokenSet:
        seen.append((refresh_token, id_token))
        return TokenSet(
            access_token="FRESH", refresh_token="a0-refresh-2", id_token=id_token,
            expires_at=9e9, strategy="audi_auth0",
        )

    async def _idk_refresh(*a: Any, **k: Any) -> TokenSet:  # pragma: no cover
        raise AssertionError("the IDK endpoint answers 'invalid assertion headers' here")

    monkeypatch.setattr(a0.AudiAuth0Grant, "refresh", _fake_refresh)
    monkeypatch.setattr(c._auth, "refresh", _idk_refresh)
    notified: list[str] = []

    async def _notify() -> None:
        notified.append(c._tokens.access_token)

    c._notify_tokens_changed = _notify  # type: ignore[method-assign]

    asyncio.run(c._refresh_tokens(stale_access_token="STALE"))

    assert seen == [("a0-refresh-1", "old-id")]
    assert c._tokens.access_token == "FRESH"
    assert c._tokens.refresh_token == "a0-refresh-2"
    assert c._tokens.strategy == "audi_auth0", "a refresh must not drop the strategy tag"
    assert notified == ["FRESH"], "the coordinator persists on this callback"


def test_a_dead_auth0_refresh_surfaces_instead_of_rerunning_the_password_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _auth0_client()

    async def _dead(self: Any, refresh_token: str, *, id_token: str = "") -> TokenSet:
        raise AuthenticationError("Auth0 refresh rejected: HTTP 403 invalid_grant")

    monkeypatch.setattr(a0.AudiAuth0Grant, "refresh", _dead)

    async def _never(*a: Any, **k: Any) -> None:  # pragma: no cover
        raise AssertionError("authenticate() must not run for a dead Auth0 session")

    c.authenticate = _never  # type: ignore[method-assign]
    with pytest.raises(AuthenticationError, match="invalid_grant"):
        asyncio.run(c._refresh_tokens(stale_access_token="STALE"))


def test_a_passwordless_auth0_entry_is_told_to_sign_in_again() -> None:
    c = _auth0_client(password="")
    with pytest.raises(DeviceLoginExpiredError, match="audi_auth0"):
        asyncio.run(c.authenticate())


def test_the_auth0_branch_sits_before_the_generic_idk_refresh() -> None:
    """The generic branch — the LAST ``self._auth.refresh(`` in the method — is
    the IDK refresh that answers ``invalid assertion headers``; the Auth0
    branch must be reached before it."""
    src = inspect.getsource(_base.CariadBaseClient._refresh_tokens)
    assert src.index('strategy == "audi_auth0"') < src.rindex("self._auth.refresh(")


def test_images_are_skipped_on_an_auth0_session_without_touching_azs_or_vgql(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Measured live: the AZS proxy refuses the Auth0 token and vgql answers
    401 for every ``vehicle { … }`` sub-field. So neither is called, the image
    map is empty, and the reason is logged once — not on every poll."""
    c = _auth0_client()
    c._tokens = TokenSet(
        access_token="A0", refresh_token="r", id_token=ID_TOKEN, strategy="audi_auth0",
    )

    async def _no_azs() -> str | None:  # pragma: no cover
        raise AssertionError("the AZS proxy must not be called for an Auth0 session")

    class _Fetcher:
        def __init__(self, session: Any) -> None:  # pragma: no cover
            raise AssertionError("vgql must not be called for an Auth0 session")

    c._exchange_azs_token = _no_azs  # type: ignore[method-assign]
    import custom_components.vag_connect.cariad.api.audi as audi_mod

    orig = audi_mod.VehicleImageFetcher
    audi_mod.VehicleImageFetcher = _Fetcher  # type: ignore[misc]
    try:
        with caplog.at_level("INFO"):
            asyncio.run(c.fetch_images())
            asyncio.run(c.fetch_images())
    finally:
        audi_mod.VehicleImageFetcher = orig  # type: ignore[misc]
    assert c._image_data == {}
    assert sum("not available on a browser" in r.message for r in caplog.records) == 1


def test_qr_signin_live_knows_the_browser_sign_in() -> None:
    assert dg.qr_signin_live("audi", "audi_auth0") is True
    assert dg.qr_signin_live("volkswagen", "audi_auth0") is False
    assert dg.qr_signin_live("audi", "device_grant") is False, "the device-code grant stays retired"


# ── config flow ────────────────────────────────────────────────────────────────


class _Entries:
    def __init__(self, *entries: SimpleNamespace) -> None:
        self._entries = list(entries)
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.reloaded: list[str] = []

    def async_get_entry(self, entry_id: str) -> SimpleNamespace | None:
        return next((e for e in self._entries if e.entry_id == entry_id), None)

    def async_update_entry(self, entry: SimpleNamespace, *, data: dict[str, Any] | None = None, **kw: Any) -> None:
        if data is not None:
            entry.data = data
        self.updated.append((entry.entry_id, dict(entry.data)))

    async def async_reload(self, entry_id: str) -> None:
        self.reloaded.append(entry_id)


class _FakeTokenStorage:
    saved: list[tuple[Any, TokenSet]] = []

    def __init__(self, store: Any) -> None:
        self._store = store

    async def save(self, tokens: TokenSet) -> None:
        _FakeTokenStorage.saved.append((self._store, tokens))


@pytest.fixture(autouse=True)
def _no_real_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token persistence is HA storage; capture it instead."""
    import homeassistant.helpers.storage as ha_storage

    import custom_components.vag_connect.cariad.auth._token_storage as ts

    class _FakeStore:
        def __init__(self, hass: Any, version: int, key: str, **kw: Any) -> None:
            self.key = key

    _FakeTokenStorage.saved = []
    monkeypatch.setattr(ts, "TokenStorage", _FakeTokenStorage)
    monkeypatch.setattr(ha_storage, "Store", _FakeStore)


def _flow(*entries: SimpleNamespace, context: dict[str, Any] | None = None) -> tuple[Any, _Entries]:
    reg = _Entries(*entries)
    flow = cf.VagConnectConfigFlow()
    flow.hass = SimpleNamespace(  # type: ignore[assignment]
        config_entries=reg,
        config=SimpleNamespace(
            language="da", country="DK", path=lambda *parts: "/".join(parts),
        ),
    )
    flow.context = context or {}  # type: ignore[assignment]
    flow._async_current_entries = lambda include_ignore=False: list(reg._entries)  # type: ignore[method-assign]
    return flow, reg


def _patch_exchange(monkeypatch: pytest.MonkeyPatch, tokens: TokenSet | None = None, *, raise_: Exception | None = None) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []

    async def _fake(self: Any, code: str, verifier: str) -> TokenSet:
        seen.append((code, verifier))
        if raise_ is not None:
            raise raise_
        return tokens or TokenSet(
            access_token="A0", refresh_token="R0", id_token=ID_TOKEN,
            expires_at=1.7e9, strategy="audi_auth0",
        )

    monkeypatch.setattr(a0.AudiAuth0Grant, "exchange_code", _fake)
    return seen


@pytest.mark.asyncio
async def test_browser_login_routes_audi_to_the_auth0_step() -> None:
    flow, _reg = _flow()
    result = await flow.async_step_browser_login(
        {CONF_BRAND: "audi", CONF_SPIN: "", CONF_SCAN_INTERVAL: 15}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "audi_auth0"
    url = result["description_placeholders"]["authorization_url"]
    q = parse_qs(urlparse(url).query)
    assert q["state"] == [flow._auth0_state]
    assert q["ui_locales"] == ["da-DK"]
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_a_foreign_or_stale_callback_is_refused_and_the_attempt_kept() -> None:
    flow, _reg = _flow()
    await flow.async_step_audi_auth0()
    url_before = flow._auth0_url
    result = await flow.async_step_audi_auth0(
        {"callback_url": f"{CALLBACK}?code=c&state=not-mine"}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth0_callback"}
    assert flow._auth0_url == url_before, "a bad paste does not burn the attempt"

    result = await flow.async_step_audi_auth0(
        {"callback_url": f"{CALLBACK}?error=access_denied&state={flow._auth0_state}"}
    )
    assert result["errors"] == {"base": "auth0_denied"}


@pytest.mark.asyncio
async def test_a_refused_code_starts_a_fresh_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _reg = _flow()
    await flow.async_step_audi_auth0()
    old_state, old_verifier = flow._auth0_state, flow._auth0_verifier
    _patch_exchange(monkeypatch, raise_=AuthenticationError("HTTP 403 invalid_grant"))
    result = await flow.async_step_audi_auth0(
        {"callback_url": f"{CALLBACK}?code=spent&state={old_state}"}
    )
    assert result["errors"] == {"base": "auth0_auth_failed"}
    assert (flow._auth0_state, flow._auth0_verifier) != (old_state, old_verifier)
    assert flow._auth0_state in result["description_placeholders"]["authorization_url"]


@pytest.mark.asyncio
async def test_a_transient_exchange_failure_is_cannot_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _reg = _flow()
    await flow.async_step_audi_auth0()
    _patch_exchange(monkeypatch, raise_=TokenRefreshRetryError("503"))
    result = await flow.async_step_audi_auth0(
        {"callback_url": f"{CALLBACK}?code=c&state={flow._auth0_state}"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_a_new_account_becomes_a_new_passwordless_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _reg = _flow()
    created: list[dict[str, Any]] = []

    async def _set_uid(uid: str, **kw: Any) -> None:
        created.append({"unique_id": uid})

    flow.async_set_unique_id = _set_uid  # type: ignore[method-assign]
    flow._abort_if_unique_id_configured = lambda **kw: None  # type: ignore[method-assign]
    flow.async_create_entry = lambda **kw: created.append(kw) or {"type": "create_entry", **kw}  # type: ignore[method-assign]

    await flow.async_step_browser_login({CONF_BRAND: "audi", CONF_SPIN: "1234", CONF_SCAN_INTERVAL: 15})
    seen = _patch_exchange(monkeypatch)
    result = await flow.async_step_audi_auth0(
        {"callback_url": f"{CALLBACK}?code=the-code&state={flow._auth0_state}"}
    )

    assert seen == [("the-code", flow._auth0_verifier)]
    assert result["type"] == "create_entry"
    assert created[0]["unique_id"] == "audi_Driver@Example.invalid"
    data = created[1]["data"]
    assert data[CONF_BRAND] == "audi"
    assert data[CONF_USERNAME] == "Driver@Example.invalid"
    assert data[CONF_PASSWORD] == ""
    assert data[CONF_SPIN] == "1234"
    assert data["dag_initial_tokens"]["strategy"] == "audi_auth0"
    assert data["dag_initial_tokens"]["refresh_token"] == "R0"
    assert created[1]["title"].endswith("Driver@Example.invalid")


@pytest.mark.asyncio
async def test_a_known_account_attaches_to_its_existing_entry_and_keeps_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The #1712 migration path: the walled email+password entry gains the Auth0
    tokens in BOTH the store and dag_initial_tokens, keeps its password for the
    EU Data Act portal, and is reloaded. No second entry."""
    existing = SimpleNamespace(
        entry_id="e1",
        data={CONF_BRAND: "audi", CONF_USERNAME: "driver@example.invalid", CONF_PASSWORD: "pw", "read_only_mode": True},
    )
    flow, reg = _flow(existing)
    flow.async_create_entry = lambda **kw: pytest.fail("must attach, not create")  # type: ignore[method-assign]

    await flow.async_step_browser_login({CONF_BRAND: "audi", CONF_SPIN: "", CONF_SCAN_INTERVAL: 15})
    _patch_exchange(monkeypatch)
    result = await flow.async_step_audi_auth0(
        {"callback_url": f"{CALLBACK}?code=c&state={flow._auth0_state}"}
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert existing.data[CONF_PASSWORD] == "pw"
    assert existing.data["read_only_mode"] is True
    assert existing.data["dag_initial_tokens"]["strategy"] == "audi_auth0"
    assert reg.reloaded == ["e1"]
    assert len(_FakeTokenStorage.saved) == 1
    assert _FakeTokenStorage.saved[0][1].strategy == "audi_auth0"


@pytest.mark.asyncio
async def test_reauth_of_an_auth0_entry_goes_straight_to_the_browser_step() -> None:
    entry = SimpleNamespace(
        entry_id="e1",
        data={CONF_BRAND: "audi", CONF_USERNAME: "x", CONF_PASSWORD: "",
              "dag_initial_tokens": {"strategy": "audi_auth0", "refresh_token": "dead"}},
    )
    flow, _reg = _flow(entry, context={"entry_id": "e1"})
    result = await flow.async_step_reauth_confirm()
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_audi_auth0"


@pytest.mark.asyncio
async def test_reauth_of_a_password_audi_entry_offers_a_choice() -> None:
    entry = SimpleNamespace(
        entry_id="e1", data={CONF_BRAND: "audi", CONF_USERNAME: "x@y.z", CONF_PASSWORD: "pw"},
    )
    flow, _reg = _flow(entry, context={"entry_id": "e1"})
    result = await flow.async_step_reauth_confirm()
    assert result["type"] == "menu"
    assert result["step_id"] == "reauth_audi_menu"
    assert result["menu_options"] == ["reauth_audi_auth0", "reauth_credentials"]


@pytest.mark.asyncio
async def test_the_credentials_menu_choice_shows_the_old_form_once() -> None:
    entry = SimpleNamespace(
        entry_id="e1", data={CONF_BRAND: "audi", CONF_USERNAME: "x@y.z", CONF_PASSWORD: "pw"},
    )
    flow, _reg = _flow(entry, context={"entry_id": "e1"})
    result = await flow.async_step_reauth_credentials()
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


@pytest.mark.asyncio
async def test_other_brands_reauth_exactly_as_before() -> None:
    entry = SimpleNamespace(
        entry_id="e1", data={CONF_BRAND: "skoda", CONF_USERNAME: "x@y.z", CONF_PASSWORD: "pw"},
    )
    flow, _reg = _flow(entry, context={"entry_id": "e1"})
    result = await flow.async_step_reauth_confirm()
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


@pytest.mark.asyncio
async def test_reauth_writes_the_store_and_the_entry_and_reloads(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = SimpleNamespace(
        entry_id="e1",
        data={CONF_BRAND: "audi", CONF_USERNAME: "x", CONF_PASSWORD: "",
              "dag_initial_tokens": {"strategy": "audi_auth0", "refresh_token": "dead"}},
    )
    flow, reg = _flow(entry, context={"entry_id": "e1"})
    await flow.async_step_reauth_confirm()
    _patch_exchange(monkeypatch)
    result = await flow.async_step_reauth_audi_auth0(
        {"callback_url": f"{CALLBACK}?code=c&state={flow._auth0_state}"}
    )
    assert result == flow.async_abort(reason="reauth_successful")
    assert entry.data["dag_initial_tokens"]["refresh_token"] == "R0"
    assert reg.reloaded == ["e1"]
    assert [t.refresh_token for _s, t in _FakeTokenStorage.saved] == ["R0"]


def test_the_strings_cover_every_new_key() -> None:
    import pathlib

    root = pathlib.Path(cf.__file__).parent
    for name in ["strings.json", *(f"translations/{lang}.json" for lang in "cs da de en es fi fr it nb nl pl sv".split())]:
        doc = json.loads((root / name).read_text(encoding="utf-8"))
        cfg = doc["config"]
        for step in ("audi_auth0", "reauth_audi_auth0"):
            assert "{authorization_url}" in cfg["step"][step]["description"], name
            assert "callback_url" in cfg["step"][step]["data"], name
        assert set(cfg["step"]["reauth_audi_menu"]["menu_options"]) == {"reauth_audi_auth0", "reauth_credentials"}, name
        for key in ("invalid_auth0_callback", "auth0_denied", "auth0_auth_failed"):
            assert key in cfg["error"], name
        assert "http" not in json.dumps(cfg["step"]["audi_auth0"]), "no literal URLs in strings (hassfest)"
