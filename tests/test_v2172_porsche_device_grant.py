# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.2 — Porsche One PingFederate RFC-8628 device-grant auth.

Validates the request/response contract of ``PorscheOneDeviceAuth`` against a
fully mocked session (no network). This module is EXPERIMENTAL / not yet wired
into the config flow — these tests pin the mechanics so a Porsche One owner can
verify it end-to-end against the live tenant.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth.porsche import PorscheOneDeviceAuth
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    TokenExpiredError,
)

_DISCOVERY = {
    "device_authorization_endpoint": "https://identity.porsche.com/as/device",
    "token_endpoint": "https://identity.porsche.com/as/token",
}


class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._p = payload

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def json(self) -> Any:
        # ``self._p`` is already the deserialized body (dict or, for a bare-string
        # API response, a str) — return it as aiohttp's .json() would.
        return self._p

    async def text(self) -> str:
        return self._p if isinstance(self._p, str) else json.dumps(self._p)


class _Session:
    """Routes get/post by URL substring; list values are popped per call."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.posts: list[dict[str, Any]] = []

    def get(self, url: str, **_: Any) -> _Resp:
        return self._match(url)

    def post(self, url: str, *, data: Any = None, **_: Any) -> _Resp:
        self.posts.append({"url": url, "data": data})
        return self._match(url)

    def _match(self, url: str) -> _Resp:
        for key, resp in self.routes.items():
            if key in url:
                if isinstance(resp, list):
                    return resp.pop(0)
                return resp
        raise AssertionError(f"no mock route for {url}")


def _base_routes() -> dict[str, Any]:
    return {
        "clientId": _Resp(200, {"clientId": "PORSCHE-ONE-CID"}),
        ".well-known": _Resp(200, _DISCOVERY),
    }


def test_request_device_code_happy_path() -> None:
    routes = _base_routes()
    routes["/as/device"] = _Resp(200, {
        "device_code": "DEV123",
        "user_code": "ABCD-EFGH",
        "verification_uri": "https://device.identity.porsche.com/activate",
        "verification_uri_complete": "https://device.identity.porsche.com/activate?user_code=ABCD-EFGH",
        "interval": 5,
        "expires_in": 600,
    })
    sess = _Session(routes)
    auth = PorscheOneDeviceAuth(sess)
    out = asyncio.run(auth.request_device_code())
    assert out["device_code"] == "DEV123"
    assert out["user_code"] == "ABCD-EFGH"
    assert out["interval"] == 5
    # the runtime client_id + PingFederate device endpoint were resolved
    assert auth._client_id == "PORSCHE-ONE-CID"
    assert auth._device_endpoint.endswith("/as/device")
    # the device-auth POST carried client_id + the device scope
    dev_post = next(p for p in sess.posts if p["url"].endswith("/as/device"))
    assert dev_post["data"]["client_id"] == "PORSCHE-ONE-CID"
    assert "offline_access" in dev_post["data"]["scope"]


def test_client_id_accepts_bare_string() -> None:
    routes = _base_routes()
    routes["clientId"] = _Resp(200, "BARE-CID")
    routes["/as/device"] = _Resp(200, {"device_code": "d", "user_code": "u"})
    auth = PorscheOneDeviceAuth(_Session(routes))
    asyncio.run(auth.request_device_code())
    assert auth._client_id == "BARE-CID"


def test_poll_once_pending_then_success() -> None:
    routes = _base_routes()
    routes["/as/token"] = [
        _Resp(400, {"error": "authorization_pending"}),
        _Resp(200, {
            "access_token": "AT", "refresh_token": "RT", "id_token": "IT",
        }),
    ]
    auth = PorscheOneDeviceAuth(_Session(routes))
    pending = asyncio.run(auth.poll_once("DEV123"))
    assert pending is None  # still waiting for the owner to approve
    tok = asyncio.run(auth.poll_once("DEV123"))
    assert tok is not None
    assert tok.access_token == "AT"
    assert tok.refresh_token == "RT"


def test_poll_once_slow_down_is_pending() -> None:
    routes = _base_routes()
    routes["/as/token"] = _Resp(400, {"error": "slow_down"})
    auth = PorscheOneDeviceAuth(_Session(routes))
    assert asyncio.run(auth.poll_once("DEV123")) is None


def test_poll_once_access_denied_raises() -> None:
    routes = _base_routes()
    routes["/as/token"] = _Resp(400, {"error": "access_denied"})
    auth = PorscheOneDeviceAuth(_Session(routes))
    with pytest.raises(AuthenticationError):
        asyncio.run(auth.poll_once("DEV123"))


def test_refresh_happy_path() -> None:
    routes = _base_routes()
    routes["/as/token"] = _Resp(200, {"access_token": "AT2", "refresh_token": "RT2"})
    auth = PorscheOneDeviceAuth(_Session(routes))
    tok = asyncio.run(auth.refresh("RT-OLD"))
    assert tok.access_token == "AT2"
    assert tok.refresh_token == "RT2"


def test_refresh_401_raises_token_expired() -> None:
    routes = _base_routes()
    routes["/as/token"] = _Resp(401, {"error": "invalid_grant"})
    auth = PorscheOneDeviceAuth(_Session(routes))
    with pytest.raises(TokenExpiredError):
        asyncio.run(auth.refresh("RT-OLD"))


def test_refresh_keeps_old_refresh_token_when_omitted() -> None:
    routes = _base_routes()
    routes["/as/token"] = _Resp(200, {"access_token": "AT3"})
    auth = PorscheOneDeviceAuth(_Session(routes))
    tok = asyncio.run(auth.refresh("RT-KEEP"))
    assert tok.refresh_token == "RT-KEEP"


def test_discovery_missing_endpoint_raises() -> None:
    routes = _base_routes()
    routes[".well-known"] = _Resp(200, {"token_endpoint": "https://x/as/token"})
    routes["/as/device"] = _Resp(200, {"device_code": "d", "user_code": "u"})
    auth = PorscheOneDeviceAuth(_Session(routes))
    with pytest.raises(AuthenticationError):
        asyncio.run(auth.request_device_code())
