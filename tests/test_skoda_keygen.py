# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Official Škoda public-API key minting from the mysmob login (auto-enrollment).

RE'd from MyŠkoda 8.16 (cz.myskoda.api.bff_public_api_keys.v2): the app POSTs to
``mysmob.api.connect.skoda-auto.cz/api/v2/public-api-keys`` with the user's mysmob
Bearer to create an X-API-Key. We reuse the exact Bearer SkodaClient already holds,
gated on a native login and spoofing the real app User-Agent.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import (
    SkodaClient,
    _KEYGEN_USER_AGENT,
    _OFFICIAL_KEY_NAME,
)

VIN = "TMBJJ7NX1M0000005"


def _native_client() -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._tokens = SimpleNamespace(strategy="", access_token="eyJhbGci.payload.sig")  # type: ignore[assignment]
    c._eu_portal = None
    return c


def test_can_mint_gate() -> None:
    c = _native_client()
    assert c.can_mint_official_key is True
    # portal-fallback connector present → never mint (no real Bearer)
    c._eu_portal = object()
    assert c.can_mint_official_key is False
    # portal sentinel token (non-empty strategy) → never mint
    c._eu_portal = None
    c._tokens = SimpleNamespace(  # type: ignore[assignment]
        strategy="data_act_portal", access_token="eu-data-act-portal-cookie-session")
    assert c.can_mint_official_key is False
    # non-JWT access token → never mint
    c._tokens = SimpleNamespace(strategy="", access_token="not-a-jwt")  # type: ignore[assignment]
    assert c.can_mint_official_key is False
    # no token at all
    c._tokens = None
    assert c.can_mint_official_key is False


def test_mint_posts_key_with_spoofed_ua() -> None:
    c = _native_client()
    c._post = AsyncMock(return_value={  # type: ignore[method-assign]
        "id": "k1", "key": "SECRET-XYZ",
        "name": _OFFICIAL_KEY_NAME, "validUntil": "2027-09-01T00:00:00Z"})
    out = asyncio.run(c.mint_api_key(VIN))
    kw = c._post.call_args.kwargs
    assert c._post.call_args.args[0].endswith("/api/v2/public-api-keys")
    assert kw["json"] == {"name": _OFFICIAL_KEY_NAME, "vin": VIN}
    assert kw["headers"]["User-Agent"] == _KEYGEN_USER_AGENT
    assert out is not None and out["key"] == "SECRET-XYZ"


def test_mint_gated_out_never_calls_out() -> None:
    c = _native_client()
    c._eu_portal = object()          # portal-fallback → gated
    c._post = AsyncMock()  # type: ignore[method-assign]
    assert asyncio.run(c.mint_api_key(VIN)) is None
    c._post.assert_not_awaited()


def test_mint_is_failsoft() -> None:
    c = _native_client()
    c._post = AsyncMock(side_effect=Exception("boom"))  # type: ignore[method-assign]
    assert asyncio.run(c.mint_api_key(VIN)) is None
    # a 200 without a key secret is also treated as failure
    c._post = AsyncMock(return_value={"id": "k1"})  # type: ignore[method-assign]
    assert asyncio.run(c.mint_api_key(VIN)) is None


def test_list_and_delete() -> None:
    c = _native_client()
    c._get = AsyncMock(return_value={  # type: ignore[method-assign]
        "maxKeys": 5, "vehicleKeys": [{"vin": VIN, "keysRemaining": 4}]})
    lst = asyncio.run(c.list_api_keys())
    assert lst is not None and lst["vehicleKeys"][0]["keysRemaining"] == 4
    assert c._get.call_args.kwargs["headers"]["User-Agent"] == _KEYGEN_USER_AGENT

    c._request = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert asyncio.run(c.delete_api_key("k1")) is True
    assert c._request.call_args.args[0] == "DELETE"
    assert c._request.call_args.args[1].endswith("/api/v2/public-api-keys/k1")


def test_keygen_records_pii_free_probe_outcomes() -> None:
    # The mint route is RE'd but never run live — diagnostics must report what it
    # actually did, as a PII-free probe (status + response KEY names only).
    from custom_components.vag_connect.cariad.exceptions import APIError

    # success with validUntil
    c = _native_client()
    c._post = AsyncMock(return_value={  # type: ignore[method-assign]
        "id": "k1", "key": "SECRET", "validUntil": "2027-01-01T00:00:00Z"})
    asyncio.run(c.mint_api_key(VIN))
    assert c.probe_outcomes["skoda_official_keygen"] == "POST 2xx key+validUntil"

    # 4xx → status only, never the body (which could echo the VIN we sent)
    c = _native_client()
    c._post = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError(400, "u", "vin TMBJJ7NX1M0000005 rejected"))
    asyncio.run(c.mint_api_key(VIN))
    assert c.probe_outcomes["skoda_official_keygen"] == "POST 400"
    assert VIN not in c.probe_outcomes["skoda_official_keygen"]

    # 2xx but no key secret → shape (key NAMES only), no values
    c = _native_client()
    c._post = AsyncMock(return_value={"id": "k1", "name": "x"})  # type: ignore[method-assign]
    asyncio.run(c.mint_api_key(VIN))
    assert c.probe_outcomes["skoda_official_keygen"] == "POST 2xx no-key [id,name]"

    # list success → counts only
    c = _native_client()
    c._get = AsyncMock(return_value={  # type: ignore[method-assign]
        "maxKeys": 5, "vehicleKeys": [{"vin": VIN, "keysRemaining": 4}]})
    asyncio.run(c.list_api_keys())
    assert c.probe_outcomes["skoda_official_keygen_list"] == "GET 2xx maxKeys=5 vins=1"

    # list 401 → status only
    c = _native_client()
    c._get = AsyncMock(side_effect=APIError(401, "u", "body"))  # type: ignore[method-assign]
    asyncio.run(c.list_api_keys())
    assert c.probe_outcomes["skoda_official_keygen_list"] == "GET 401"
