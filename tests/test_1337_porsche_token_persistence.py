# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v4.7.7 (#1337) — Porsche token persistence so the captcha is a first-setup
event, not a per-restart one.

The Porsche captcha lives ONLY on the interactive login (/u/login/identifier);
the /oauth/token refresh is never captcha-gated. So if a solved-captcha login's
refresh token is persisted and reused across restarts, the interactive login
(and its captcha) essentially never re-runs. These tests cover the PorscheClient
persistence hooks (save/restore/emit) and the config-flow token bridge.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api.porsche import PorscheClient
from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.config_flow import _validate_credentials

_CREATE = "custom_components.vag_connect.cariad.CariadClientFactory.create"


def _bare_client() -> PorscheClient:
    c = PorscheClient.__new__(PorscheClient)  # skip __init__/network
    c._tokens = None
    c.on_tokens_changed = None
    return c


# ── set_persisted_tokens: restore only a usable (refreshable) token ────────────
def test_restore_only_with_refresh_token() -> None:
    c = _bare_client()
    c.set_persisted_tokens(
        TokenSet(access_token="a", refresh_token="r", id_token="i", expires_at=123)
    )
    assert c._tokens is not None and c._tokens.refresh_token == "r"


def test_restore_ignores_none_and_refreshless() -> None:
    c = _bare_client()
    c.set_persisted_tokens(None)
    assert c._tokens is None
    c.set_persisted_tokens(TokenSet(access_token="a", refresh_token="", id_token="i"))
    assert c._tokens is None  # no refresh token → not reusable → ignored


# ── _emit_tokens: tags strategy, calls the save hook, fail-soft ────────────────
@pytest.mark.asyncio
async def test_emit_tags_strategy_and_calls_hook() -> None:
    c = _bare_client()
    c._tokens = TokenSet(access_token="a", refresh_token="r", id_token="i")
    seen: list[TokenSet] = []
    async def _save(ts: TokenSet) -> None:
        seen.append(ts)
    c.on_tokens_changed = _save
    await c._emit_tokens()
    assert len(seen) == 1
    assert seen[0].strategy == "porsche"  # tagged so it is not treated as portal


@pytest.mark.asyncio
async def test_emit_noop_without_hook_or_tokens() -> None:
    c = _bare_client()
    await c._emit_tokens()  # no tokens, no hook → no crash
    c._tokens = TokenSet(access_token="a", refresh_token="r", id_token="i")
    await c._emit_tokens()  # no hook → no crash


@pytest.mark.asyncio
async def test_emit_is_failsoft_when_hook_raises() -> None:
    c = _bare_client()
    c._tokens = TokenSet(access_token="a", refresh_token="r", id_token="i")
    async def _boom(ts: TokenSet) -> None:
        raise RuntimeError("storage down")
    c.on_tokens_changed = _boom
    await c._emit_tokens()  # must NOT propagate — persistence is best-effort


# ── authenticate() emits, so the coordinator's save hook persists it ───────────
@pytest.mark.asyncio
async def test_authenticate_emits_for_persistence() -> None:
    c = _bare_client()
    c._email = "e@x.com"
    c._password = "pw"
    c._auth = MagicMock()
    c._auth.authenticate = AsyncMock(return_value=TokenSet(
        access_token="AA", refresh_token="RR", id_token="II", expires_at=999))
    seen: list[TokenSet] = []
    async def _save(ts: TokenSet) -> None:
        seen.append(ts)
    c.on_tokens_changed = _save
    await c.authenticate()
    assert c._tokens is not None and c._tokens.refresh_token == "RR"
    assert seen and seen[-1].refresh_token == "RR" and seen[-1].strategy == "porsche"


# ── _validate_credentials bridges the Porsche token to the config flow ─────────
@pytest.mark.asyncio
async def test_validate_returns_porsche_token_dict() -> None:
    client = _bare_client()
    client.authenticate = AsyncMock()  # type: ignore[method-assign]
    client._tokens = TokenSet(
        access_token="AAA", refresh_token="RRR", id_token="III",
        expires_at=888.0, strategy="porsche")
    with patch(_CREATE, return_value=client):
        out = await _validate_credentials(None, "porsche", "e@x.com", "pw")
    assert out == {
        "access_token": "AAA", "refresh_token": "RRR", "id_token": "III",
        "expires_at": 888.0, "strategy": "porsche",
    }


# ── reauth/reconfigure must OVERWRITE the token store (not just entry.data) ─────
@pytest.mark.asyncio
async def test_reauth_overwrites_token_store_with_fresh_token() -> None:
    # The coordinator prefers the persisted store; on reauth it still holds the
    # DEAD token. The entry.data bridge is only promoted when the store is empty,
    # so a reauth MUST overwrite the store or it loops. This covers that fix.
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    saved: list[TokenSet] = []

    class _FakeTS:
        def __init__(self, _store: object) -> None:
            pass
        async def save(self, ts: TokenSet) -> None:
            saved.append(ts)

    with patch(
        "custom_components.vag_connect.cariad.auth._token_storage.TokenStorage",
        _FakeTS,
    ), patch(
        "custom_components.vag_connect.cariad.auth._token_storage.storage_key_for_entry",
        return_value="k",
    ), patch("homeassistant.helpers.storage.Store", MagicMock()):
        await flow._persist_porsche_token_store("e1", {
            "access_token": "A", "refresh_token": "R", "id_token": "I",
            "expires_at": 5.0, "strategy": "porsche",
        })
    assert len(saved) == 1
    assert saved[0].refresh_token == "R"
    assert saved[0].strategy == "porsche"


@pytest.mark.asyncio
async def test_reauth_store_overwrite_is_noop_without_token() -> None:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    # tok=None → no save, no crash (fail-soft)
    await flow._persist_porsche_token_store("e1", None)


@pytest.mark.asyncio
async def test_validate_returns_none_for_non_porsche() -> None:
    client = MagicMock()
    client.authenticate = AsyncMock()
    with patch(_CREATE, return_value=client):
        out = await _validate_credentials(None, "volkswagen", "e@x.com", "pw")
    assert out is None


@pytest.mark.asyncio
async def test_validate_returns_none_when_porsche_has_no_tokens() -> None:
    # A PorscheClient mock with no _tokens (e.g. __new__ without a login) must
    # not crash — the bridge just yields None.
    client = PorscheClient.__new__(PorscheClient)
    client.authenticate = AsyncMock()  # type: ignore[method-assign]
    with patch(_CREATE, return_value=client):
        out = await _validate_credentials(None, "porsche", "e@x.com", "pw")
    assert out is None
