# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.19.2 — IDK token persistence (#118 eismarkt fix).

Closes #118 ("After every update of VAG Connect, the password must
be entered again"). Root cause: tokens lived only in memory; every
HACS update / HA restart triggered a fresh authenticate() against
the IDK backend, which could fail transiently and surface as
ConfigEntryAuthFailed → user prompted for reauth.

Fix: persist TokenSet to HA storage via the Store helper. Coordinator
loads at setup; every refresh writes back.

Tests cover:
- TokenStorage.load: never-saved / corrupted / version-mismatch /
  parse-error / incomplete tokens → all return None
- TokenStorage.save: valid TokenSet round-trips
- TokenStorage.save: incomplete TokenSet refused (no garbage in storage)
- TokenStorage.clear: idempotent
- CariadBaseClient.set_persisted_tokens: valid tokens skip authenticate()
- CariadBaseClient.set_persisted_tokens: invalid tokens are no-op
- CariadBaseClient._notify_tokens_changed: callback fires after auth/refresh
- CariadBaseClient._notify_tokens_changed: callback exceptions don't propagate
- storage_key_for_entry: per-entry isolation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) TokenStorage load/save/clear round-trips
# ─────────────────────────────────────────────────────────────────────────────


class _DictStore:
    """Dict-backed fake of HA's Store helper for tests."""

    def __init__(self, initial=None):
        self._data = initial

    async def async_load(self):
        return self._data

    async def async_save(self, data):
        self._data = data

    async def async_remove(self):
        self._data = None


class TestTokenStorageLoad:
    @pytest.mark.asyncio
    async def test_never_saved_returns_none(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        store = _DictStore(initial=None)
        ts = TokenStorage(store)
        assert await ts.load() is None

    @pytest.mark.asyncio
    async def test_non_dict_returns_none(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        store = _DictStore(initial="garbage")
        ts = TokenStorage(store)
        assert await ts.load() is None

    @pytest.mark.asyncio
    async def test_version_mismatch_returns_none(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        store = _DictStore(initial={
            "version": 999,
            "tokens": {
                "access_token": "a", "refresh_token": "r", "id_token": "i",
                "expires_at": 1000.0,
            },
        })
        ts = TokenStorage(store)
        assert await ts.load() is None

    @pytest.mark.asyncio
    async def test_missing_tokens_dict_returns_none(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage, _STORAGE_VERSION,
        )
        store = _DictStore(initial={"version": _STORAGE_VERSION})
        ts = TokenStorage(store)
        assert await ts.load() is None

    @pytest.mark.asyncio
    async def test_incomplete_tokens_returns_none(self):
        """If access_token or id_token is empty, the TokenSet is_valid()
        check rejects the load — better re-login than half-broken state.

        v2.6.0 — empty refresh_token is INTENTIONALLY allowed (hybrid
        flow and Data Act portal both produce token sets without one).
        Only access_token + id_token are required.
        """
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage, _STORAGE_VERSION,
        )
        # Empty access_token — definitively invalid
        store = _DictStore(initial={
            "version": _STORAGE_VERSION,
            "tokens": {
                "access_token": "", "refresh_token": "r", "id_token": "i",
                "expires_at": 1000.0,
            },
        })
        assert await TokenStorage(store).load() is None

        # Empty id_token — definitively invalid
        store2 = _DictStore(initial={
            "version": _STORAGE_VERSION,
            "tokens": {
                "access_token": "a", "refresh_token": "r", "id_token": "",
                "expires_at": 1000.0,
            },
        })
        assert await TokenStorage(store2).load() is None

    @pytest.mark.asyncio
    async def test_v260_empty_refresh_token_is_valid(self):
        """v2.6.0 contract: hybrid flow + Data Act portal both return
        TokenSets with empty refresh_token. Those must load successfully
        — the coordinator handles re-login when the access_token expires.
        """
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage, _STORAGE_VERSION,
        )
        store = _DictStore(initial={
            "version": _STORAGE_VERSION,
            "tokens": {
                "access_token": "a", "refresh_token": "", "id_token": "i",
                "expires_at": 1000.0,
            },
        })
        loaded = await TokenStorage(store).load()
        assert loaded is not None
        assert loaded.access_token == "a"
        assert loaded.refresh_token == ""
        assert loaded.id_token == "i"

    @pytest.mark.asyncio
    async def test_valid_tokens_load_correctly(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage, _STORAGE_VERSION,
        )
        store = _DictStore(initial={
            "version": _STORAGE_VERSION,
            "tokens": {
                "access_token": "AT", "refresh_token": "RT",
                "id_token": "IT", "expires_at": 1746450000.0,
            },
        })
        ts = TokenStorage(store)
        loaded = await ts.load()
        assert loaded is not None
        assert loaded.access_token == "AT"
        assert loaded.refresh_token == "RT"
        assert loaded.id_token == "IT"
        assert loaded.expires_at == 1746450000.0

    @pytest.mark.asyncio
    async def test_load_swallows_storage_errors(self):
        """If the underlying Store helper raises, load() returns None
        instead of propagating — broken storage shouldn't kill setup."""
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        store = MagicMock()
        store.async_load = AsyncMock(side_effect=OSError("disk full"))
        ts = TokenStorage(store)
        assert await ts.load() is None


class TestTokenStorageSave:
    @pytest.mark.asyncio
    async def test_save_then_load_roundtrips(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        from custom_components.vag_connect.cariad.models import TokenSet
        store = _DictStore()
        ts = TokenStorage(store)
        tokens = TokenSet(
            access_token="A", refresh_token="R", id_token="I",
            expires_at=1746450000.0,
        )
        await ts.save(tokens)
        loaded = await ts.load()
        assert loaded == tokens

    @pytest.mark.asyncio
    async def test_save_refuses_incomplete_tokens(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        from custom_components.vag_connect.cariad.models import TokenSet
        store = _DictStore()
        ts = TokenStorage(store)
        bad = TokenSet(access_token="", refresh_token="R", id_token="I")
        await ts.save(bad)
        # Storage stays empty — no garbage written
        assert store._data is None

    @pytest.mark.asyncio
    async def test_save_swallows_storage_errors(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        from custom_components.vag_connect.cariad.models import TokenSet
        store = MagicMock()
        store.async_save = AsyncMock(side_effect=OSError("disk full"))
        ts = TokenStorage(store)
        # Should not raise — just log
        await ts.save(TokenSet(
            access_token="A", refresh_token="R", id_token="I",
        ))


class TestTokenStorageClear:
    @pytest.mark.asyncio
    async def test_clear_idempotent(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        store = _DictStore(initial={"version": 1, "tokens": {}})
        ts = TokenStorage(store)
        await ts.clear()
        await ts.clear()  # second call still safe
        assert store._data is None

    @pytest.mark.asyncio
    async def test_clear_swallows_errors(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            TokenStorage,
        )
        store = MagicMock()
        store.async_remove = AsyncMock(side_effect=OSError("io error"))
        ts = TokenStorage(store)
        await ts.clear()  # never raises


class TestStorageKey:
    def test_per_entry_isolation(self):
        from custom_components.vag_connect.cariad.auth._token_storage import (
            storage_key_for_entry,
        )
        k1 = storage_key_for_entry("entry_A")
        k2 = storage_key_for_entry("entry_B")
        assert k1 != k2
        assert "entry_A" in k1
        assert "entry_B" in k2
        assert k1.startswith("vag_connect_tokens")


# ─────────────────────────────────────────────────────────────────────────────
# B) CariadBaseClient hook integration
# ─────────────────────────────────────────────────────────────────────────────


class TestSetPersistedTokens:
    def test_valid_tokens_set_internal_state(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        from custom_components.vag_connect.cariad.models import TokenSet
        c = CariadBaseClient.__new__(CariadBaseClient)
        c._tokens = None
        c._brand = MagicMock(name="brand")
        c._brand.name = "skoda"
        tok = TokenSet(access_token="A", refresh_token="R", id_token="I")
        c.set_persisted_tokens(tok)
        assert c._tokens == tok

    def test_none_is_noop(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        c = CariadBaseClient.__new__(CariadBaseClient)
        c._tokens = None
        c._brand = MagicMock()
        c.set_persisted_tokens(None)
        assert c._tokens is None

    def test_incomplete_tokens_ignored(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        from custom_components.vag_connect.cariad.models import TokenSet
        c = CariadBaseClient.__new__(CariadBaseClient)
        c._tokens = None
        c._brand = MagicMock()
        bad = TokenSet(access_token="", refresh_token="R", id_token="I")
        c.set_persisted_tokens(bad)
        assert c._tokens is None


class TestNotifyTokensChanged:
    @pytest.mark.asyncio
    async def test_callback_fires_with_tokens(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        from custom_components.vag_connect.cariad.models import TokenSet
        c = CariadBaseClient.__new__(CariadBaseClient)
        c._tokens = TokenSet(access_token="A", refresh_token="R", id_token="I")
        c.on_tokens_changed = AsyncMock()
        await c._notify_tokens_changed()
        c.on_tokens_changed.assert_awaited_once_with(c._tokens)

    @pytest.mark.asyncio
    async def test_no_callback_no_op(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        from custom_components.vag_connect.cariad.models import TokenSet
        c = CariadBaseClient.__new__(CariadBaseClient)
        c._tokens = TokenSet(access_token="A", refresh_token="R", id_token="I")
        c.on_tokens_changed = None
        await c._notify_tokens_changed()  # no raise

    @pytest.mark.asyncio
    async def test_no_tokens_no_callback(self):
        """If client has no tokens (e.g. cleared on logout), don't
        spam the callback with None — would write garbage to storage."""
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        c = CariadBaseClient.__new__(CariadBaseClient)
        c._tokens = None
        c.on_tokens_changed = AsyncMock()
        await c._notify_tokens_changed()
        c.on_tokens_changed.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_propagate(self):
        """A failing storage callback must NOT crash auth/refresh —
        runtime tokens are still valid in-memory."""
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        from custom_components.vag_connect.cariad.models import TokenSet
        c = CariadBaseClient.__new__(CariadBaseClient)
        c._tokens = TokenSet(access_token="A", refresh_token="R", id_token="I")
        c.on_tokens_changed = AsyncMock(side_effect=OSError("disk full"))
        await c._notify_tokens_changed()  # never raises
        c.on_tokens_changed.assert_awaited_once()
