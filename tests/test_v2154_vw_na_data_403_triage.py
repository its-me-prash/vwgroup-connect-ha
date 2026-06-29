# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.4 (#503) — VW NA read-path 403 triage + entitlement surfacing.

login + garage succeed but the per-vehicle reads (rvs / charge / climate)
return HTTP 403. These tests prove the new diagnostics:

1. ``_classify_data_403`` maps an attestation-marker body to ``"attestation"``
   and a bare / entitlement body to ``"entitlement"`` / ``"bare-403"``.
2. ``get_status`` emits ONE value-free DEBUG triage line and sets the
   ``vw_na_data_forbidden`` + reason flags the coordinator reads — and the log
   leaks NO UUID / VIN / body fragment / token.

Pure-Python: constructs VWNAClient via ``__new__`` to skip the HA / aiohttp
setup chain, matching test_v210_vw_na_endpoints.py.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.ha_required


_SECRET_UUID = "11112222-3333-4444-5555-666677778888"
_SECRET_VIN = "WVWZZZ1KZAW000503"
_SECRET_TOKEN = "eyJhbGciOiJSUzI1NiJ9.SECRETTOKENPAYLOAD.sig"

# A realistic attestation 403 body whose marker sits PAST the 200-char clip
# that str(APIError) applies — proves we classify off exc.body, not str(exc).
_ATTESTATION_BODY = (
    '{"error":{"message":"Forbidden","'
    + ("padding " * 40)  # > 200 chars before the marker
    + f'"vin":"{_SECRET_VIN}","uuid":"{_SECRET_UUID}",'
    '"detail":"missing-device-token: x-firebase-appcheck required"}}'
)
_ENTITLEMENT_BODY = (
    '{"error":{"message":"Forbidden","code":"not_entitled",'
    f'"vin":"{_SECRET_VIN}","subscription":"expired"}}'
)
_BARE_BODY = f'{{"error":"Forbidden","uuid":"{_SECRET_UUID}"}}'


def _client():
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    client = VWNAClient.__new__(VWNAClient)
    client._base = "https://example.test"
    client._vin_to_uuid = {_SECRET_VIN: _SECRET_UUID}
    client._vin_to_model = {}
    client._vin_to_nickname = {}
    client._user_id = "user-abc"
    client._spin = ""
    client.vw_na_data_forbidden = False
    client.vw_na_data_forbidden_reason = ""
    client._last_privileges_status = None
    return client


def _api_error(status: int, body: str):
    from custom_components.vag_connect.cariad.exceptions import APIError

    # url carries a secret too — proves the triage never echoes it.
    return APIError(status, f"https://example.test/rvs/v1/vehicle/{_SECRET_UUID}", body)


# ---------------------------------------------------------------------------
# 1) _classify_data_403 — markers only
# ---------------------------------------------------------------------------


class TestClassifyData403:
    def test_attestation_marker_past_str_clip(self):
        from custom_components.vag_connect.cariad.api.vw_na import _classify_data_403

        exc = _api_error(403, _ATTESTATION_BODY)
        # The 200-char str() clip must NOT hide the marker.
        assert "missing-device-token" not in str(exc)
        assert _classify_data_403(exc) == "attestation"

    def test_entitlement_marker(self):
        from custom_components.vag_connect.cariad.api.vw_na import _classify_data_403

        assert _classify_data_403(_api_error(403, _ENTITLEMENT_BODY)) == "entitlement"

    def test_bare_403(self):
        from custom_components.vag_connect.cariad.api.vw_na import _classify_data_403

        assert _classify_data_403(_api_error(403, _BARE_BODY)) == "bare-403"


# ---------------------------------------------------------------------------
# 2) get_status — flags + value-free triage log
# ---------------------------------------------------------------------------


def _assert_no_secret_leak(caplog):
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert _SECRET_UUID not in blob, "UUID leaked into log"
    assert _SECRET_VIN not in blob, "VIN leaked into log"
    assert _SECRET_TOKEN not in blob, "token leaked into log"
    assert "missing-device-token" not in blob, "body fragment leaked into log"
    assert "x-firebase-appcheck" not in blob, "body fragment leaked into log"
    assert "not_entitled" not in blob, "body fragment leaked into log"


class TestGetStatusTriage:
    @pytest.mark.asyncio
    async def test_attestation_403_surfaces_attestation(self, caplog):
        client = _client()
        client._get = AsyncMock(side_effect=_api_error(403, _ATTESTATION_BODY))  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]
        client._last_privileges_status = 403

        with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect.cariad.api.vw_na"):
            d = await client.get_status(_SECRET_VIN)

        assert client.vw_na_data_forbidden is True
        assert client.vw_na_data_forbidden_reason == "attestation"
        assert d.vin == _SECRET_VIN  # data object still returned (last-known shows)
        # The classification label IS logged...
        assert "VW NA data 403 classified as attestation" in caplog.text
        # ...but no secret/body fragment is.
        _assert_no_secret_leak(caplog)

    @pytest.mark.asyncio
    async def test_entitlement_403_surfaces_entitlement(self, caplog):
        client = _client()
        client._get = AsyncMock(side_effect=_api_error(403, _ENTITLEMENT_BODY))  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(
            return_value={"subscription_active": False}
        )  # type: ignore[method-assign]

        with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect.cariad.api.vw_na"):
            await client.get_status(_SECRET_VIN)

        assert client.vw_na_data_forbidden is True
        assert client.vw_na_data_forbidden_reason == "entitlement"
        assert "VW NA data 403 classified as entitlement" in caplog.text
        _assert_no_secret_leak(caplog)

    @pytest.mark.asyncio
    async def test_bare_403_with_active_sub_does_not_surface(self, caplog):
        client = _client()
        client._get = AsyncMock(side_effect=_api_error(403, _BARE_BODY))  # type: ignore[method-assign]
        # Privileges succeeded and reports an ACTIVE subscription → a bare 403
        # is likely transient; do NOT raise the entitlement Repair issue.
        client.get_subscription_privileges = AsyncMock(
            return_value={"subscription_active": True, "capabilities_count": 5}
        )  # type: ignore[method-assign]
        client._last_privileges_status = None

        with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect.cariad.api.vw_na"):
            await client.get_status(_SECRET_VIN)

        assert client.vw_na_data_forbidden is False
        assert client.vw_na_data_forbidden_reason == "bare-403"
        assert "VW NA data 403 classified as bare-403" in caplog.text
        _assert_no_secret_leak(caplog)

    @pytest.mark.asyncio
    async def test_successful_read_clears_flag(self, caplog):
        client = _client()
        # Pretend a prior poll had flagged it.
        client.vw_na_data_forbidden = True
        client.vw_na_data_forbidden_reason = "entitlement"
        client._get = AsyncMock(return_value={"powerStatus": {}})  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.get_status(_SECRET_VIN)

        assert client.vw_na_data_forbidden is False
        assert client.vw_na_data_forbidden_reason == ""
