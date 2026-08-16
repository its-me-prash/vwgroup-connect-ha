# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1082 (jarmbruster74) — one value-safe entitlement fingerprint on every poll.

A non-403 empty/OFFLINE read (login + garage OK, reads return {} or non-dicts, no
403) previously left no trace of WHY: the discriminator DEBUG only fired inside
the 403 path. get_status now emits a 'VW NA read fingerprint' line every poll,
carrying only labels / bools / ints / an HTTP status — never a VIN / UUID / token.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.ha_required

_SECRET_UUID = "11112222-3333-4444-5555-666677778888"
_SECRET_VIN = "WVWZZZ1KZAW001082"
_SECRET_TOKEN = "eyJhbGciOiJSUzI1NiJ9.SECRETTOKENPAYLOAD.sig"


def _client():
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    client = VWNAClient.__new__(VWNAClient)
    client._base = "https://example.test"
    client._country = "us"
    client._vin_to_uuid = {_SECRET_VIN: _SECRET_UUID}
    client._vin_to_model = {}
    client._vin_to_nickname = {}
    client._user_id = "user-abc"
    client._spin = ""
    client.vw_na_data_forbidden = False
    client.vw_na_data_forbidden_reason = ""
    client._last_privileges_status = None
    client._get_read_session_token = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_fingerprint_emitted_on_non_403_empty_read(caplog):
    # jarmbruster74's shape: reads return {} (not dicts we can parse), no 403.
    client = _client()
    client._get = AsyncMock(return_value={})  # type: ignore[method-assign]
    client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.vag_connect.cariad.api.vw_na"
    ):
        await client.get_status(_SECRET_VIN)

    assert "VW NA read fingerprint" in caplog.text
    assert "carnet_read=False" in caplog.text
    assert "client=US" in caplog.text
    assert "scope=openid" in caplog.text
    assert "privileges_status=None" in caplog.text
    # value-safe: no VIN / UUID / token in any record
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert _SECRET_UUID not in blob
    assert _SECRET_VIN not in blob
    assert _SECRET_TOKEN not in blob


@pytest.mark.asyncio
async def test_fingerprint_reports_carnet_and_privileges_status(caplog):
    client = _client()
    client._get_read_session_token = AsyncMock(return_value=_SECRET_TOKEN)  # type: ignore[method-assign]
    client._get = AsyncMock(return_value={})  # type: ignore[method-assign]
    client.get_subscription_privileges = AsyncMock(
        return_value={"subscription_active": True, "capabilities_count": 3}
    )  # type: ignore[method-assign]

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.vag_connect.cariad.api.vw_na"
    ):
        await client.get_status(_SECRET_VIN)

    assert "carnet_read=True" in caplog.text
    assert "subscription_active=True" in caplog.text
    assert "capabilities_count=3" in caplog.text
    assert _SECRET_TOKEN not in "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_fingerprint_silent_when_debug_disabled(caplog):
    client = _client()
    client._get = AsyncMock(return_value={})  # type: ignore[method-assign]
    client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

    with caplog.at_level(
        logging.INFO, logger="custom_components.vag_connect.cariad.api.vw_na"
    ):
        await client.get_status(_SECRET_VIN)

    assert "VW NA read fingerprint" not in caplog.text
