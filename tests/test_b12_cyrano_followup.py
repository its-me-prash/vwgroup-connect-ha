# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b12 — #1340 (@cyrano330) follow-up fixes.

1. Repair-routing: an EU Audi whose IDK + portal logins BOTH succeed but whose
   portal then 401s on vehicle enumeration (even after a re-login) must surface
   the ``data_act_session_expired`` repair, NOT ``invalid_credentials`` — the
   password is provably fine. A distinct ``PortalSessionExpiredError`` carries
   that case; it is raised only on the SECOND enumeration 401 (reachable only
   after a successful login), and routed as a soft (retrying) setup error.

2. Diagnostics no longer 500 when the entry is in setup_error: the handler
   dereferenced the coordinator (entry.runtime_data), which is None before setup
   completes — exactly when the download is most useful. It now returns a
   redacted partial (config + note) instead.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    PortalSessionExpiredError,
)
from custom_components.vag_connect.cariad.models import TokenSet


# ── the distinct exception ───────────────────────────────────────────────────

def test_session_expired_is_subclass_of_auth_error() -> None:
    # MUST stay a subclass so existing `except AuthenticationError` still catches
    # it (backward compatible); only the coordinator's dedicated branch treats it
    # specially, and it must be caught BEFORE the credential catch-all.
    assert issubclass(PortalSessionExpiredError, AuthenticationError)
    e = PortalSessionExpiredError("portal 401")
    assert e.reason == "portal 401"
    assert "wrong-password problem" in str(e).lower() or "not a wrong-password" in str(e).lower()


# ── the reason is a SOFT setup error (retries), not HARD (reauth-hard) ────────

def test_session_expired_reason_is_soft_retry() -> None:
    from custom_components.vag_connect import (
        _HARD_AUTH_SETUP_ERRORS,
        _SETUP_ERRORS,
    )
    assert "data_act_session_expired" in _SETUP_ERRORS
    assert "data_act_session_expired" not in _HARD_AUTH_SETUP_ERRORS
    # contrast: a genuine credential failure stays HARD
    assert "invalid_credentials" in _HARD_AUTH_SETUP_ERRORS


# ── vw_eu enumeration retry raises the distinct exception on the 2nd 401 ──────

class TestVwEuEnumerationRetry:
    def _client(self, portal: MagicMock):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        c = VWEUClient.__new__(VWEUClient)
        c._eu_portal = portal
        c._email = "me@example.com"
        c._password = "secret"
        # non-device_grant_portal → takes the portal.login() retry branch
        c._tokens = TokenSet("a", "r", "i", 0.0, "data_act_portal")
        return c

    def test_second_401_after_relogin_is_session_expired(self) -> None:
        portal = MagicMock()
        # 401 on both the first and the post-login retry enumeration
        portal.list_vehicle_vins = AsyncMock(side_effect=AuthenticationError("401"))
        portal.login = AsyncMock()
        c = self._client(portal)
        with pytest.raises(PortalSessionExpiredError):
            asyncio.run(c.get_vehicles())
        portal.login.assert_awaited_once()  # the one re-login happened

    def test_first_401_then_success_is_not_flagged(self) -> None:
        # a transient first 401 that recovers after re-login must NOT be surfaced
        # as session-expired — data flows normally.
        portal = MagicMock()
        portal.list_vehicle_vins = AsyncMock(
            side_effect=[AuthenticationError("401"), ["WVWZZZ1KZAM000001"]]
        )
        portal.login = AsyncMock()
        portal.get_relation_nickname = AsyncMock(return_value=None)
        c = self._client(portal)
        vins = asyncio.run(c.get_vehicles())
        assert vins == ["WVWZZZ1KZAM000001"]


# ── diagnostics guard on setup_error (runtime_data is None) ───────────────────

def test_diagnostics_returns_partial_when_setup_incomplete() -> None:
    from custom_components.vag_connect.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    hass = MagicMock()
    entry = MagicMock()
    entry.runtime_data = None  # setup never completed
    entry.data = {"brand": "audi", "username": "me@example.com", "password": "secret"}
    entry.options = {}
    entry.state = "setup_error"

    result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    assert "note" in result
    assert "config" in result
    assert result["entry_state"] == "setup_error"
    # secrets stay redacted even on the partial path (reuses _scrub)
    assert result["config"].get("password") != "secret"
