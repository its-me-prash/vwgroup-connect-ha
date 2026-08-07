# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression: the EU-Data-Act portal kickoff must send Duration + traceId.

VW changed the Custom-Data-Request format (mid-2026). The create POST now
REQUIRES a ``Duration`` field — without it the portal 400s
``"Invalid Duration: None. Allowed values are ['No Expiry', 'One Month'] …"`` —
and the euda-apim edge rejects any request without a ``traceId`` header (503).
Verified live 2026-07-12: with both, the create POST returns 201 and the car's
15-min portal feed starts; without them the kickoff silently failed for EVERY
VW EU portal user, so no car got a data feed (issues #465, #709). These tests
pin both so a future portal-format change can't silently regress the feed again.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.auth._data_act_scraper import (
    DataActScraper,
)

_VIN = "WVWZZZAUZFW805377"


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return "{}"

    async def json(self, content_type: Any = None) -> Any:
        return {}


class _CaptureSession:
    """Records the url + kwargs of each GET/POST so headers/body are assertable."""

    def __init__(self, *, get_status: int = 404, post_status: int = 201) -> None:
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []
        self._get_status = get_status
        self._post_status = post_status

    def get(self, url: str, **kw: Any) -> _Resp:
        self.get_calls.append((url, kw))
        return _Resp(self._get_status)

    def post(self, url: str, **kw: Any) -> _Resp:
        self.post_calls.append((url, kw))
        return _Resp(self._post_status)


def _scraper(sess: Any) -> DataActScraper:
    return DataActScraper(sess, brand_name="volkswagen")


def _confirm_readback(scraper: DataActScraper) -> None:
    """#957/#966 — kickoff reads the request back after a 2xx; confirm it landed
    so body/header-shape tests still see a successful kickoff."""
    scraper.get_active_custom_request_identifier = AsyncMock(  # type: ignore[method-assign]
        return_value="READBACK_IDENTIFIER_0001"
    )


@pytest.mark.asyncio
async def test_kickoff_body_includes_duration() -> None:
    """The kickoff POST body carries the now-required ``Duration`` field."""
    sess = _CaptureSession(post_status=201)
    scraper = _scraper(sess)
    scraper._fetch_csrf_token = AsyncMock(return_value="csrf")  # type: ignore[method-assign]
    _confirm_readback(scraper)
    ident = await scraper.kickoff_custom_data_request(_VIN)
    assert ident  # 201 → returns the new Identifier
    assert sess.post_calls, "no POST was made"
    body = sess.post_calls[-1][1]["json"]
    # v2.29.x — asked for as "No Expiry" now; the value this pins is
    # that a valid Duration is sent at all. The month-long window that used to
    # be sent here is what silently stopped every feed after four weeks, and it
    # survives only as the fallback (see test_v2290_portal_feed_no_expiry.py).
    assert body["Duration"] == "No Expiry"
    assert body["Frequency"] == "15mins"  # legacy fields still present (echoed live)


@pytest.mark.asyncio
async def test_kickoff_post_sends_traceid() -> None:
    """The kickoff POST carries a non-empty ``traceId`` header (euda-apim edge)."""
    sess = _CaptureSession(post_status=201)
    scraper = _scraper(sess)
    scraper._fetch_csrf_token = AsyncMock(return_value="csrf")  # type: ignore[method-assign]
    _confirm_readback(scraper)
    await scraper.kickoff_custom_data_request(_VIN)
    headers = sess.post_calls[-1][1]["headers"]
    assert headers.get("traceId")


@pytest.mark.asyncio
async def test_metadata_probe_sends_traceid() -> None:
    """``get_active_custom_request_identifier`` sends a traceId on its GET, and a
    404 (no request) resolves to None (not an error)."""
    sess = _CaptureSession(get_status=404)
    scraper = _scraper(sess)
    result = await scraper.get_active_custom_request_identifier(_VIN)
    assert result is None
    assert sess.get_calls, "no GET was made"
    headers = sess.get_calls[-1][1]["headers"]
    assert headers.get("traceId")
