# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase C — the one-time historical export kickoff (POST requests/all).

The 15-min feed is requests/partial; the one-time export is a different request
type entirely. This contract is mirrored EXACTLY from a real Audi trace
(2026-07-17, captured from the portal's own one-time-download button):

    POST /proxy_api/euda-apim/datarequest/vehicles/{VIN}/requests/all
    {"Name":"Request File","Frequency":null,"StartDate":"…Z",
     "EndDate":null,"DataClusters":null,"EmailFrequency":null}

i.e. much simpler than the 15-min kickoff: no Identifier, no Duration,
Frequency/EndDate/DataClusters/EmailFrequency all null. These tests pin that
shape so a future portal-format change can't silently regress it, and so the
"all" body never drifts back toward the "partial" one.
"""
from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.auth._data_act_scraper import (
    DataActScraper,
    DataActSessionExpiredError,
)

_VIN = "WAUZZZF29MN024037"


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return "{}"


class _CaptureSession:
    def __init__(self, post_status: int = 201) -> None:
        self.post_calls: list[tuple[str, dict]] = []
        self._post_status = post_status

    def post(self, url: str, **kw: Any) -> _Resp:
        self.post_calls.append((url, kw))
        return _Resp(self._post_status)


def _scraper(sess: Any) -> DataActScraper:
    s = DataActScraper(sess, brand_name="audi")
    s._fetch_csrf_token = AsyncMock(return_value="csrf")  # type: ignore[method-assign]
    return s


@pytest.mark.asyncio
async def test_posts_to_requests_all_not_partial() -> None:
    sess = _CaptureSession(post_status=201)
    ok = await _scraper(sess).kickoff_historical_export(_VIN)
    assert ok is True
    url = sess.post_calls[-1][0]
    assert url.endswith(f"/datarequest/vehicles/{_VIN}/requests/all")
    assert "requests/partial" not in url


@pytest.mark.asyncio
async def test_body_matches_the_real_trace() -> None:
    sess = _CaptureSession(post_status=201)
    await _scraper(sess).kickoff_historical_export(_VIN)
    body = sess.post_calls[-1][1]["json"]
    assert body["Name"] == "Request File"
    assert body["Frequency"] is None
    assert body["EndDate"] is None
    assert body["DataClusters"] is None
    assert body["EmailFrequency"] is None
    # The "partial" shape must NOT leak into the "all" body.
    assert "Identifier" not in body
    assert "Duration" not in body


@pytest.mark.asyncio
async def test_startdate_has_millisecond_z_precision() -> None:
    # The browser sends e.g. 2026-07-17T17:58:46.111Z — match it.
    sess = _CaptureSession(post_status=201)
    await _scraper(sess).kickoff_historical_export(_VIN)
    start = sess.post_calls[-1][1]["json"]["StartDate"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", start), start


@pytest.mark.asyncio
async def test_2xx_variants_all_succeed() -> None:
    for status in (200, 201, 202):
        sess = _CaptureSession(post_status=status)
        assert await _scraper(sess).kickoff_historical_export(_VIN) is True


@pytest.mark.asyncio
async def test_non_2xx_returns_false() -> None:
    sess = _CaptureSession(post_status=500)
    assert await _scraper(sess).kickoff_historical_export(_VIN) is False


@pytest.mark.asyncio
async def test_401_raises_session_expired() -> None:
    sess = _CaptureSession(post_status=401)
    with pytest.raises(DataActSessionExpiredError):
        await _scraper(sess).kickoff_historical_export(_VIN)


@pytest.mark.asyncio
async def test_no_csrf_aborts_without_posting() -> None:
    sess = _CaptureSession(post_status=201)
    s = DataActScraper(sess, brand_name="audi")
    s._fetch_csrf_token = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert await s.kickoff_historical_export(_VIN) is False
    assert sess.post_calls == []
