# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Token-refresh rejection is CLASSIFIED, not blanket-failed.

Only ``invalid_grant`` (a dead/revoked refresh token) is a hard failure a fresh
login fixes. Every other rejection — ``invalid_client`` / ``server_error`` / a 5xx
/ a network blip — is transient and must NOT bounce the user to a fresh QR /
credential reauth prompt. ``TokenRefreshRetryError`` carries that case and is a
SIBLING of ``AuthenticationError`` (not a subclass); the poll loop reauths only on
``isinstance(err, AuthenticationError)``, so the transient case retries next poll.
Covers the device-grant refresh AND the MBB refresh (the upstream gap), while the
MBB id_token LOGIN exchange keeps raising ``AuthenticationError``.
"""
from __future__ import annotations

import asyncio
import json as _json
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth import _mbboauth
from custom_components.vag_connect.cariad.auth._device_grant import (
    DeviceAuthorizationGrant,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    TokenRefreshRetryError,
)


# ── the load-bearing invariant ──────────────────────────────────────────────

def test_retry_error_is_not_a_subtype_of_auth_error() -> None:
    # If this ever becomes a subclass, the poll loop's isinstance() reauth gate
    # would catch it again and silently undo the whole fix.
    assert not issubclass(TokenRefreshRetryError, AuthenticationError)
    assert issubclass(TokenRefreshRetryError, Exception)
    assert not isinstance(TokenRefreshRetryError("x"), AuthenticationError)


def test_retry_error_is_self_healing_not_reporter_noise() -> None:
    from custom_components.vag_connect.coordinator import _is_selfhealing_poll_error
    assert _is_selfhealing_poll_error(TokenRefreshRetryError("x")) is True
    assert _is_selfhealing_poll_error(AuthenticationError("x")) is False


# ── fakes ───────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status: int, payload: Any = None, *, boom: bool = False):
        self._status = status
        self._payload = payload
        self._boom = boom

    async def __aenter__(self) -> "_Resp":
        if self._boom:
            raise ConnectionError("network down")
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    @property
    def status(self) -> int:
        return self._status

    async def json(self, content_type: Any = None) -> Any:
        return self._payload

    async def text(self) -> str:
        return _json.dumps(self._payload) if isinstance(self._payload, dict) else ""


class _Session:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    def post(self, *_a: Any, **_k: Any) -> _Resp:
        return self._resp


def _grant(resp: _Resp) -> DeviceAuthorizationGrant:
    return DeviceAuthorizationGrant(_Session(resp), "client@apps_vw-dilab_com")  # type: ignore[arg-type]


# ── device-grant refresh classification ─────────────────────────────────────

def test_device_invalid_grant_is_hard_auth_error() -> None:
    with pytest.raises(AuthenticationError):
        asyncio.run(_grant(_Resp(400, {"error": "invalid_grant"})).refresh("rt"))


@pytest.mark.parametrize("status,err", [
    (400, "invalid_client"),
    (503, "server_error"),
    (400, "some_unknown_error"),
    (400, ""),
])
def test_device_non_invalid_grant_is_retryable(status: int, err: str) -> None:
    with pytest.raises(TokenRefreshRetryError):
        asyncio.run(_grant(_Resp(status, {"error": err})).refresh("rt"))


def test_device_network_blip_is_retryable() -> None:
    with pytest.raises(TokenRefreshRetryError):
        asyncio.run(_grant(_Resp(0, boom=True)).refresh("rt"))


def test_device_200_without_token_is_retryable() -> None:
    with pytest.raises(TokenRefreshRetryError):
        asyncio.run(_grant(_Resp(200, {"expires_in": 3600})).refresh("rt"))


def test_device_success_returns_tokenset() -> None:
    ts = asyncio.run(
        _grant(_Resp(200, {"access_token": "ey.a.b", "expires_in": 3600})).refresh("rt")
    )
    assert ts.access_token == "ey.a.b"


# ── MBB refresh vs login classification ─────────────────────────────────────

def test_mbb_refresh_invalid_grant_is_hard() -> None:
    with pytest.raises(AuthenticationError):
        asyncio.run(_mbboauth.refresh(_Session(_Resp(400, {"error": "invalid_grant"})), "rt"))  # type: ignore[arg-type]


def test_mbb_refresh_transient_is_retryable() -> None:
    # 400 (non-5xx) so no backoff-sleep; non-invalid_grant → retryable
    with pytest.raises(TokenRefreshRetryError):
        asyncio.run(_mbboauth.refresh(_Session(_Resp(400, {"error": "server_error"})), "rt"))  # type: ignore[arg-type]


def test_mbb_refresh_200_without_token_is_retryable() -> None:
    # A 200 whose body parses fine but carries no access_token is a backend hiccup,
    # not invalid_grant — on the refresh path it must be transient, mirroring the
    # device-grant case above. Regresses to a hard AuthenticationError without the
    # pre-parse guard in _post_token (pytest.raises would then not catch it).
    with pytest.raises(TokenRefreshRetryError):
        asyncio.run(_mbboauth.refresh(_Session(_Resp(200, {"expires_in": 3600})), "rt"))  # type: ignore[arg-type]


def test_mbb_login_200_without_token_stays_auth_error() -> None:
    # The LOGIN exchange (retryable=False) keeps the same 200-without-token as a
    # hard AuthenticationError — a login that yields no token really did fail.
    with pytest.raises(AuthenticationError):
        asyncio.run(_mbboauth.exchange_id_token(_Session(_Resp(200, {"expires_in": 3600})), "idtok"))  # type: ignore[arg-type]


def test_mbb_empty_refresh_token_is_hard() -> None:
    with pytest.raises(AuthenticationError):
        asyncio.run(_mbboauth.refresh(_Session(_Resp(200, {})), ""))  # type: ignore[arg-type]


def test_mbb_login_exchange_failure_stays_auth_error() -> None:
    # The id_token LOGIN exchange must NOT be reclassified — pytest.raises(
    # AuthenticationError) would not catch the sibling retry type, so this passing
    # proves it stayed a hard auth error.
    with pytest.raises(AuthenticationError):
        asyncio.run(_mbboauth.exchange_id_token(_Session(_Resp(400, {"error": "server_error"})), "idtok"))  # type: ignore[arg-type]
