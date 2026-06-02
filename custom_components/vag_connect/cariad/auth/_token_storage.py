# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Token persistence via HA's Store helper.

Closes #118 (eismarkt) — "After every update of VAG Connect, the
password must be entered again". Root cause was that we never
persisted IDK tokens between integration restarts (HACS update,
HA restart, config-entry reload). Every fresh setup ran the full
OAuth login pipeline against the live IDK backend, which:

- Counts against the daily request quota (~1500 calls)
- Triggers the v1.8.7 token-refresh-storm protection on
  consecutive failures (myskoda #976 / volkswagencarnet #683
  pattern) → ConfigEntryAuthFailed → user prompted for reauth
- Wastes ~2-3 seconds on every startup

This module wraps HA's ``homeassistant.helpers.storage.Store``
helper to persist the active TokenSet per (config_entry_id, brand)
across restarts. The coordinator loads at setup, and any fresh
login or refresh writes back.

### Storage shape

Per config-entry, single key ``vag_connect_tokens``, version 1:

    {
      "version": 1,
      "tokens": {
        "access_token": "...",
        "refresh_token": "...",
        "id_token": "...",
        "expires_at": 1746450000.0
      }
    }

### Privacy

- Tokens never appear in logs (existing privacy-redaction in
  ``_unexpected_keys.py:_JWT_RE`` handles them in diagnostics
  exports).
- HA's Store helper writes to ``.storage/`` which is part of the
  HA config volume — encrypted at rest if the user enabled disk
  encryption on HA OS, otherwise plain JSON (same trust level as
  the credentials in the config-entry already).
- On config-entry removal: ``async_clear`` is called from the
  coordinator's ``async_unload`` so we don't leave orphan tokens.

### Why a separate module?

- Keeps `CariadBaseClient` HA-agnostic — it just gains optional
  hooks (``set_tokens(tokens)`` + ``on_tokens_changed`` callback)
  that any storage implementation can wire up.
- Makes testing easy — tests can pass a dict-backed fake without
  importing the HA Store helper.
- Future: same module can grow to persist per-VIN home-region
  cache (v1.17.6 follow-up) or push-FCM credentials (v1.18.x
  Phase 2 wire-in).
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import TokenSet

_LOGGER = logging.getLogger(__name__)

# Storage schema version. Bump on incompatible changes (e.g. if we
# ever add per-brand token-isolation in a multi-brand config).
_STORAGE_VERSION = 1

# Storage key suffix. HA's Store helper namespaces by integration
# domain automatically when ``Store(hass, version, key)`` is called
# from inside a custom_component, so the file lives at
# ``.storage/vag_connect_tokens_{config_entry_id}``.
_STORAGE_KEY_PREFIX = "vag_connect_tokens"


class TokenStorage:
    """Persist IDK TokenSet per config-entry across restarts.

    Wraps any backend with a simple ``async_load() / async_save() /
    async_remove()`` contract — typically HA's ``Store`` helper, but
    tests pass a dict-backed fake.

    Lifecycle:

    1. Coordinator setup → ``load()`` returns previously saved
       TokenSet or None
    2. Brand client uses tokens directly if present; calls
       ``authenticate()`` only if None or if refresh fails
    3. After every successful ``authenticate()`` or
       ``_refresh_tokens()``: ``save(tokens)``
    4. On config-entry remove: ``clear()``
    """

    def __init__(self, store: Any) -> None:
        """Initialise.

        Args:
            store: An object with ``async_load() -> dict | None``,
                ``async_save(data: dict) -> None`` and
                ``async_remove() -> None`` coroutine methods.
                In production this is ``homeassistant.helpers.storage.Store``;
                in tests it's a dict-backed fake.
        """
        self._store = store

    async def load(self) -> TokenSet | None:
        """Load the persisted TokenSet, or None if never saved /
        corrupted / version-incompatible.

        Defensive: any error → return None and let the coordinator
        fall back to a full authenticate() flow. Never raises so a
        broken storage file can't stop the integration from setting
        up — worst case is one extra login on next startup.
        """
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "vag_connect token storage load failed (%s) — "
                "falling back to fresh login",
                err,
            )
            return None
        if not isinstance(data, dict):
            return None
        if data.get("version") != _STORAGE_VERSION:
            _LOGGER.info(
                "vag_connect token storage version mismatch "
                "(got %r, want %d) — discarding",
                data.get("version"),
                _STORAGE_VERSION,
            )
            return None
        tok = data.get("tokens")
        if not isinstance(tok, dict):
            return None
        try:
            # v2.8.0 — also restore strategy + auth_cookies. Latent
            # bug fix: the strategy field had been on TokenSet since
            # v2.6.0 but the storage layer never round-tripped it,
            # so the coordinator's watchdog (task #46) never saw
            # the active strategy after a restart.
            raw_cookies = tok.get("auth_cookies")
            auth_cookies: list[dict[str, Any]] = (
                [c for c in raw_cookies if isinstance(c, dict)]
                if isinstance(raw_cookies, list)
                else []
            )
            tokens = TokenSet(
                access_token=str(tok.get("access_token") or ""),
                refresh_token=str(tok.get("refresh_token") or ""),
                id_token=str(tok.get("id_token") or ""),
                expires_at=float(tok.get("expires_at") or 0),
                strategy=str(tok.get("strategy") or ""),
                auth_cookies=auth_cookies,
            )
        except (TypeError, ValueError) as err:
            _LOGGER.info(
                "vag_connect token storage parse failed (%s) — discarding",
                err,
            )
            return None
        if not tokens.is_valid():
            _LOGGER.debug("Persisted tokens incomplete — ignoring")
            return None
        return tokens

    async def save(self, tokens: TokenSet) -> None:
        """Persist ``tokens`` for next restart.

        Defensive: storage write errors are logged but do not raise
        — losing token persistence is annoying (forces one extra
        login next startup), not a runtime bug.
        """
        if not tokens or not tokens.is_valid():
            _LOGGER.debug("Refusing to save incomplete TokenSet")
            return
        payload = {
            "version": _STORAGE_VERSION,
            "tokens": {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "id_token": tokens.id_token,
                "expires_at": tokens.expires_at,
                # v2.8.0 — persist strategy + auth_cookies. See model
                # docstrings for rationale (watchdog needs strategy,
                # OTP needs device-bound cookies surviving restart).
                "strategy": tokens.strategy,
                "auth_cookies": tokens.auth_cookies,
            },
        }
        try:
            await self._store.async_save(payload)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "vag_connect token storage save failed (%s) — "
                "tokens will be regenerated on next restart",
                err,
            )

    async def clear(self) -> None:
        """Remove the persisted TokenSet (e.g. on config-entry remove
        or explicit logout). Idempotent — safe to call multiple times.
        """
        try:
            await self._store.async_remove()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "vag_connect token storage clear failed (%s) — "
                "leaving stale entry",
                err,
            )


def storage_key_for_entry(entry_id: str) -> str:
    """Return the HA Store key for a config-entry's tokens.

    Per-entry isolation: a user with two vehicles on different
    accounts gets two separate token files. Format:

        vag_connect_tokens_<entry_id>

    HA's Store helper auto-prefixes the integration domain to the
    on-disk filename, so the actual file is
    ``.storage/vag_connect_tokens_<entry_id>``.
    """
    return f"{_STORAGE_KEY_PREFIX}_{entry_id}"
