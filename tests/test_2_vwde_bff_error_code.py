# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2 — a vw.de auth wall records the decoded BFF error code, not just the status.

So diagnostics can tell a plain dead-session 403 apart from a per-consent refusal
(e.g. userNotEnrolled). Only a KNOWN structured code is surfaced (decode_bff_error
returns nothing for an unknown/free-text body), so nothing sensitive leaks.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
    _http_status_from_exc,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError


def test_http_status_from_exc_carries_bff_detail() -> None:
    exc = AuthenticationError(
        "Website authproxy GET www.volkswagen.de/... → HTTP 403 (BFF 2101 userNotEnrolled)"
    )
    assert _http_status_from_exc(exc) == "403 (BFF 2101 userNotEnrolled)"


def test_http_status_from_exc_plain_status_unchanged() -> None:
    exc = AuthenticationError("Website authproxy GET x → HTTP 401")
    assert _http_status_from_exc(exc) == "401"


class _Resp:
    def __init__(self, status: int, text: str = "") -> None:
        self.status = status
        self._text = text
        self.url = "https://www.volkswagen.de/app/authproxy/vwag-weconnect/proxy/vehicles/WVWZZZ0000000345/charging/status"

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text

    async def json(self, content_type: Any = None) -> Any:
        return {}


class _Session:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    def get(self, url: str, **kw: Any) -> _Resp:
        return self._resp


def _conn(resp: _Resp) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c._session = _Session(resp)  # type: ignore[assignment]
    c._headers = lambda d: d  # type: ignore[assignment]
    c.probe_outcomes = {}
    return c


def test_get_json_auth_fail_decodes_known_bff_code() -> None:
    c = _conn(_Resp(403, '{"error":{"code":2101}}'))
    with pytest.raises(AuthenticationError) as ei:
        asyncio.run(c._get_json("https://x/charging/status", soft=True, record_as="vwde_charging"))
    assert "(BFF 2101 userNotEnrolled)" in str(ei.value)
    assert c.probe_outcomes["vwde_charging"] == "403 (BFF 2101 userNotEnrolled)"


def test_get_json_auth_fail_unknown_body_is_plain_status() -> None:
    c = _conn(_Resp(403, "Forbidden"))  # non-JSON → decode returns None
    with pytest.raises(AuthenticationError) as ei:
        asyncio.run(c._get_json("https://x/charging/status", soft=True, record_as="vwde_charging"))
    assert "BFF" not in str(ei.value)
    assert c.probe_outcomes["vwde_charging"] == "403"
