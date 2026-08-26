# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audi vgql resilience — the myAudi app-API is the primary source, the
www.audi.de web-proxy the fallback.

The web-proxy rejects some accounts' tokens outright, which left an Audi S6 as a
bare "Audi (2021)" with no model. The app-API (what the classic myAudi clients
use) serves those accounts, so it's tried first and the web-proxy backs it up.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.graphql import (
    _AUDI_APP_API_ENDPOINT,
    _GRAPHQL_ENDPOINTS,
    VehicleImageFetcher,
)

_VEHICLE = {
    "vin": "WAUZZZTESTVHN0001",
    "nickname": None,
    "vehicle": {"brand": {"name": "Audi"}, "core": {"modelYear": 2021},
                "media": {"shortName": "S6", "longName": "Audi S6 Avant TDI"},
                "renderPictures": []},
}


class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def json(self) -> Any:
        return self._payload

    async def text(self) -> str:
        return ""


def _fetcher(url_to_payload: dict[str, Any]):
    """A fetcher whose session returns a canned payload per endpoint URL and
    records the ordered list of URLs it was asked to POST."""
    calls: list[str] = []
    sess = MagicMock()

    def _post(url, **_kw):
        calls.append(url)
        status, payload = url_to_payload.get(url, (404, {}))
        return _Resp(status, payload)

    sess.post = _post
    return VehicleImageFetcher(sess), calls


_HAS = {"data": {"userVehicles": [_VEHICLE]}}
_EMPTY = {"data": {"userVehicles": []}}


@pytest.mark.asyncio
async def test_audi_uses_app_api_first_and_skips_the_proxy_when_it_works():
    f, calls = _fetcher({_AUDI_APP_API_ENDPOINT: (200, _HAS)})
    result = await f.fetch_image_data("tok", "audi")
    assert "WAUZZZTESTVHN0001" in result
    assert result["WAUZZZTESTVHN0001"].long_name == "Audi S6 Avant TDI"
    # the app-API answered → the web-proxy is never called
    assert calls == [_AUDI_APP_API_ENDPOINT]


@pytest.mark.asyncio
async def test_audi_falls_back_to_the_web_proxy_when_app_api_is_empty():
    f, calls = _fetcher({
        _AUDI_APP_API_ENDPOINT: (200, _EMPTY),
        _GRAPHQL_ENDPOINTS["audi"]: (200, _HAS),
    })
    result = await f.fetch_image_data("tok", "audi")
    assert "WAUZZZTESTVHN0001" in result
    assert calls == [_AUDI_APP_API_ENDPOINT, _GRAPHQL_ENDPOINTS["audi"]]


@pytest.mark.asyncio
async def test_audi_falls_back_when_app_api_rejects_the_token():
    f, calls = _fetcher({
        _AUDI_APP_API_ENDPOINT: (403, {}),
        _GRAPHQL_ENDPOINTS["audi"]: (200, _HAS),
    })
    result = await f.fetch_image_data("tok", "audi")
    assert "WAUZZZTESTVHN0001" in result
    assert calls == [_AUDI_APP_API_ENDPOINT, _GRAPHQL_ENDPOINTS["audi"]]


@pytest.mark.asyncio
async def test_non_audi_uses_its_own_endpoint_only():
    f, calls = _fetcher({_GRAPHQL_ENDPOINTS["skoda"]: (200, _HAS)})
    await f.fetch_image_data("tok", "skoda")
    assert calls == [_GRAPHQL_ENDPOINTS["skoda"]]
    assert _AUDI_APP_API_ENDPOINT not in calls


@pytest.mark.asyncio
async def test_explicit_url_override_wins():
    f, calls = _fetcher({"https://custom/vgql": (200, _HAS)})
    await f.fetch_image_data("tok", "audi", graphql_url="https://custom/vgql")
    assert calls == ["https://custom/vgql"]
