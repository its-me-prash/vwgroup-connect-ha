# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.3 — MBB command failures surface as clean, correctly-classified errors.

Grounded in a live GTE (Golf GTE, the repo's standard MBB test car) diagnostic
where all three write commands failed with raw ``APIError`` tracebacks:

1. **honk/flash** — ``command_flash`` was the ONE write command missing the
   ``_mbb_command_target()`` gate, so on an MBB car it POSTed the read-only
   bearer to the CARIAD BFF (``400 missing or invalid auth header``) and then
   masked it as a bogus "requires userPosition / no GPS" message.
2. **lock (RLU)** — leg-2 rejected the S-PIN hash with
   ``mbbc.rolesandrights.invalidSecurityPin``; it bubbled as a raw 403 and
   ``classify_command_failure`` mislabeled it ``NOT_ENTITLED`` (phantom renewal).
3. **wake (VSR)** — the durable-MBB grant does not carry the VSR data-refresh
   plane, so ``requests`` 403s with ``VSR.security.9007 / XID_APP_VW``. It
   bubbled as a raw 403 mislabeled ``NOT_ENTITLED`` too.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    CommandFailureReason,
    SpinError,
    VehicleCommandError,
    classify_command_failure,
)
from custom_components.vag_connect.cariad.models import TokenSet

_VIN = "WVWZZZAUZFW805377"  # repo-standard MBB test VIN (Golf GTE)

_INVALID_SPIN_BODY = (
    '{"error":{"errorCode":"mbbc.rolesandrights.invalidSecurityPin",'
    '"description":"The Security PIN is invalid."}}'
)
_VSR_9007_BODY = (
    '{"error":{"errorCode":"VSR.security.9007","description":"Did not find '
    "permission for systemId 'XID_APP_VW', therefore denying access\"}}"
)
_CHALLENGE = {
    "securityPinAuthInfo": {
        "securityToken": "LEVEL1TOKEN",
        "securityPinTransmission": {
            "challenge": "abcdef0123456789",  # valid, even-length hex
            "remainingTries": 3,
        },
    },
}


def _mbb_client() -> VWEUClient:
    c = VWEUClient(MagicMock(), "u@t.de", "pw")
    c._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i", strategy="mbb",
    )
    return c


def _bff_client() -> VWEUClient:
    # No tokens → _mbb_command_target() is None → command_flash uses the BFF.
    return VWEUClient(MagicMock(), "u@t.de", "pw")


def _patch_home_region(monkeypatch) -> None:
    import custom_components.vag_connect.cariad._home_region as _hr

    monkeypatch.setattr(
        _hr, "resolve_home_region",
        AsyncMock(return_value="https://msg.volkswagen.de"),
    )


# ── Fix 1: command_flash MBB gate ────────────────────────────────────────────

def test_flash_on_mbb_raises_clean_error_and_never_touches_bff() -> None:
    c = _mbb_client()  # strategy mbb → _mbb_command_target() is self
    c._post_command = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(VehicleCommandError) as ei:
        asyncio.run(c.command_flash(_VIN))
    # honest message, and the read-only bearer never reached the dead BFF
    assert "mbb" in str(ei.value).lower()
    c._post_command.assert_not_awaited()


def test_flash_on_bff_car_still_posts() -> None:
    # regression guard: a non-MBB car keeps hitting the BFF honkandflash path.
    c = _bff_client()
    c._post_command = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.command_flash("WVWZZZ7AZRE000001"))
    c._post_command.assert_awaited()


# ── Fix 2: RLU invalidSecurityPin → SpinError ────────────────────────────────

def test_rlu_invalid_spin_raises_spinerror(monkeypatch) -> None:
    c = _mbb_client()
    _patch_home_region(monkeypatch)
    c._mbb_country_from_id_token = MagicMock(return_value="DE")  # type: ignore[method-assign]
    c._mbb_get = AsyncMock(return_value=_CHALLENGE)  # leg 1  # type: ignore[method-assign]
    # leg 2 rejects the S-PIN hash
    c._mbb_post_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError(
            403,
            "https://x/api/rolesrights/authorization/v2/security-pin-auth-completed",
            _INVALID_SPIN_BODY,
        )
    )
    with pytest.raises(SpinError) as ei:
        asyncio.run(c._command_rlu_mbb(_VIN, spin="1234", lock=True))
    assert "security pin" in str(ei.value).lower()


def test_rlu_other_403_still_propagates_raw(monkeypatch) -> None:
    # a DIFFERENT 403 (not invalidSecurityPin) must NOT be swallowed as SpinError
    c = _mbb_client()
    _patch_home_region(monkeypatch)
    c._mbb_country_from_id_token = MagicMock(return_value="DE")  # type: ignore[method-assign]
    c._mbb_get = AsyncMock(return_value=_CHALLENGE)  # type: ignore[method-assign]
    c._mbb_post_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError(403, "https://x/completed", '{"error":"forbidden"}')
    )
    with pytest.raises(APIError):
        asyncio.run(c._command_rlu_mbb(_VIN, spin="1234", lock=True))


# ── Fix 3: wake VSR 9007 / XID_APP_VW → VehicleCommandError ───────────────────

def test_wake_vsr_9007_raises_clean_command_error(monkeypatch) -> None:
    c = _mbb_client()
    _patch_home_region(monkeypatch)
    c._mbb_country_from_id_token = MagicMock(return_value="DE")  # type: ignore[method-assign]
    c._mbb_post_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError(
            403,
            "https://msg.volkswagen.de/fs-car/bs/vsr/v1/VW/DE/vehicles/"
            f"{_VIN}/requests",
            _VSR_9007_BODY,
        )
    )
    with pytest.raises(VehicleCommandError) as ei:
        asyncio.run(c._command_wake_mbb(_VIN))
    assert "wake" in str(ei.value).lower()


def test_wake_other_403_still_propagates_raw(monkeypatch) -> None:
    c = _mbb_client()
    _patch_home_region(monkeypatch)
    c._mbb_country_from_id_token = MagicMock(return_value="DE")  # type: ignore[method-assign]
    c._mbb_post_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError(403, "https://x/requests", '{"error":"nope"}')
    )
    with pytest.raises(APIError):
        asyncio.run(c._command_wake_mbb(_VIN))


# ── Fix 4: classify_command_failure marker ───────────────────────────────────

class TestClassifyInvalidSpin:
    def test_invalid_security_pin_is_spin_required_not_entitled(self) -> None:
        exc = APIError(403, "/x", _INVALID_SPIN_BODY)
        # was NOT_ENTITLED (bare-403 fallthrough) → now the actionable reason
        assert classify_command_failure(exc) is CommandFailureReason.SPIN_REQUIRED

    def test_bare_403_still_not_entitled(self) -> None:
        # guard: the fix must not swallow genuine entitlement 403s
        assert (
            classify_command_failure(APIError(403, "/x", "forbidden"))
            is CommandFailureReason.NOT_ENTITLED
        )
