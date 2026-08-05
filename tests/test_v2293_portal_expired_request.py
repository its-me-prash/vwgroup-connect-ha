# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.29.x (#465, second half) — the portal must not adopt an EXPIRED request.

The portal keeps expired requests in metadata/partial. Our
``get_active_custom_request_identifier`` picked the first Frequency=="15mins"
descriptor with no expiry check, so once an old "One Month" request lapsed
(~4 weeks after setup) it kept adopting the stale request forever and never
kicked off a fresh feed — the data silently stopped while the request still
listed. A "No Expiry" request keeps its EndDate ~10 years out and must NOT be
treated as expired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._data_act_scraper import (
    DataActScraper,
)

_VIN = "WVWZZZAUZFW805377"


def _iso(delta_days: int) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=delta_days)).isoformat()


# ── _descriptor_expired (pure) ──────────────────────────────────────────────


class TestDescriptorExpired:
    def test_past_enddate_is_expired(self):
        assert DataActScraper._descriptor_expired({"EndDate": _iso(-1)}) is True

    def test_future_enddate_not_expired(self):
        assert DataActScraper._descriptor_expired({"EndDate": _iso(20)}) is False

    def test_no_expiry_far_future_not_expired(self):
        # "No Expiry" keeps EndDate ~10 years out
        assert DataActScraper._descriptor_expired({"EndDate": _iso(3650)}) is False

    def test_explicit_status_expired(self):
        assert DataActScraper._descriptor_expired({"Status": "EXPIRED"}) is True
        assert DataActScraper._descriptor_expired({"State": "cancelled"}) is True

    def test_date_only_enddate(self):
        past = (datetime.now(tz=timezone.utc) - timedelta(days=2)).date().isoformat()
        assert DataActScraper._descriptor_expired({"EndDate": past}) is True

    def test_unknown_shape_not_expired(self):
        # no recognisable expiry -> treat as active (never drop a valid request)
        assert DataActScraper._descriptor_expired({"foo": "bar"}) is False
        assert DataActScraper._descriptor_expired({"EndDate": "garbage"}) is False


# ── get_active_custom_request_identifier (via a mock session) ───────────────


class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def json(self, content_type: Any = None) -> Any:
        return self._payload


class _Session:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def get(self, url: str, **kw: Any) -> _Resp:  # noqa: ARG002
        return _Resp(200, self._payload)


def _scraper(payload: Any) -> DataActScraper:
    return DataActScraper(_Session(payload), brand_name="volkswagen")


class TestActiveIdentifierSelection:
    @pytest.mark.asyncio
    async def test_active_request_returned(self):
        s = _scraper([
            {"Frequency": "15mins", "Identifier": "ACTIVE-1234567890AB",
             "EndDate": _iso(15)},
        ])
        assert await s.get_active_custom_request_identifier(_VIN) == "ACTIVE-1234567890AB"

    @pytest.mark.asyncio
    async def test_expired_request_ignored_returns_none(self):
        # a lapsed One-Month request still listed -> None so a fresh feed kicks off
        s = _scraper([
            {"Frequency": "15mins", "Identifier": "EXPIRED-1234567890AB",
             "EndDate": _iso(-3)},
        ])
        assert await s.get_active_custom_request_identifier(_VIN) is None

    @pytest.mark.asyncio
    async def test_no_expiry_request_kept(self):
        s = _scraper([
            {"Frequency": "15mins", "Identifier": "NOEXPIRY-1234567890AB",
             "EndDate": _iso(3650)},
        ])
        assert (
            await s.get_active_custom_request_identifier(_VIN)
            == "NOEXPIRY-1234567890AB"
        )

    @pytest.mark.asyncio
    async def test_mixed_skips_expired_takes_active(self):
        s = _scraper([
            {"Frequency": "15mins", "Identifier": "EXPIRED-1234567890AB",
             "EndDate": _iso(-3)},
            {"Frequency": "15mins", "Identifier": "ACTIVE-1234567890AB",
             "EndDate": _iso(15)},
        ])
        assert (
            await s.get_active_custom_request_identifier(_VIN)
            == "ACTIVE-1234567890AB"
        )

    @pytest.mark.asyncio
    async def test_no_enddate_still_adopted(self):
        # a descriptor with no expiry info at all stays adopted (old behaviour):
        # better than dropping a possibly-valid request on an unknown shape
        s = _scraper([
            {"Frequency": "15mins", "Identifier": "LEGACY-1234567890AB"},
        ])
        assert (
            await s.get_active_custom_request_identifier(_VIN)
            == "LEGACY-1234567890AB"
        )
