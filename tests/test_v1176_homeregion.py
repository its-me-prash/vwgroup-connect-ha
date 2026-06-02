# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.17.6 — HomeRegion helper (evcc port).

Scaffolding-only release. The helper is built + tested + documented
but not yet wired into ``vw_eu.py`` URL builders. Wire-up plan is at
the top of ``custom_components/vag_connect/cariad/_home_region.py``.

Tests cover:
- Cache hit/miss/expiry
- Successful resolution → resolved URI returned
- Discovery 404 → falls back to DEFAULT_BASE
- Discovery network error → falls back to DEFAULT_BASE
- Malformed response → falls back to DEFAULT_BASE
- Trailing-slash normalisation
- Per-VIN isolation in cache
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad._home_region import (
    DEFAULT_BASE,
    DISCOVERY_BASE,
    HomeRegionCache,
    resolve_home_region,
)


class TestHomeRegionCache:
    def test_empty_cache_returns_none(self):
        cache = HomeRegionCache()
        assert cache.get("WAUZZZ8X3KA000001") is None

    def test_set_then_get_returns_value(self):
        cache = HomeRegionCache()
        cache.set("WAUZZZ8X3KA000001", "https://example.com")
        assert cache.get("WAUZZZ8X3KA000001") == "https://example.com"

    def test_per_vin_isolation(self):
        cache = HomeRegionCache()
        cache.set("VIN_A_1234567890", "https://host-a.example")
        cache.set("VIN_B_1234567890", "https://host-b.example")
        assert cache.get("VIN_A_1234567890") == "https://host-a.example"
        assert cache.get("VIN_B_1234567890") == "https://host-b.example"

    def test_expiry_drops_entry(self, monkeypatch):
        """Entries past TTL should be evicted on next get()."""
        from custom_components.vag_connect.cariad import _home_region as mod
        cache = HomeRegionCache()
        cache.set("VIN_EXPIRED_TEST", "https://stale.example")

        # Simulate time travel — patch datetime in the module's namespace.
        future = datetime.now(tz=timezone.utc) + timedelta(days=8)

        class _FakeDateTime:
            @staticmethod
            def now(tz=None):
                return future

        monkeypatch.setattr(mod, "datetime", _FakeDateTime)

        # Note: the entry's expires_at was computed BEFORE the patch.
        # Now mod.datetime.now() returns the future timestamp, which
        # is past the expires_at → entry should be dropped + None returned.
        assert cache.get("VIN_EXPIRED_TEST") is None
        # Subsequent get returns None too (already evicted).
        assert cache.get("VIN_EXPIRED_TEST") is None

    def test_clear_wipes_everything(self):
        cache = HomeRegionCache()
        cache.set("VIN_A", "https://a")
        cache.set("VIN_B", "https://b")
        cache.clear()
        assert cache.get("VIN_A") is None
        assert cache.get("VIN_B") is None


class TestResolveHomeRegionSuccess:
    @pytest.mark.asyncio
    async def test_resolved_uri_returned(self):
        """Standard CARIAD-BFF response → returns the URI from
        homeRegion.baseUri.content."""
        client = AsyncMock()
        client._get = AsyncMock(return_value={
            "homeRegion": {
                "baseUri": {"content": "https://emea.bff.cariad.digital"},
            },
        })
        result = await resolve_home_region(client, "WAUZZZ8X3KA000001")
        assert result == "https://emea.bff.cariad.digital"

    @pytest.mark.asyncio
    async def test_trailing_slash_stripped(self):
        client = AsyncMock()
        client._get = AsyncMock(return_value={
            "homeRegion": {
                "baseUri": {"content": "https://mal-3a.prd.eu.dp.vwg-connect.com/"},
            },
        })
        result = await resolve_home_region(client, "WAUZZZ8X3KA000001")
        assert result == "https://mal-3a.prd.eu.dp.vwg-connect.com"

    @pytest.mark.asyncio
    async def test_calls_correct_discovery_url(self):
        """Verify the discovery endpoint URL pattern matches evcc."""
        client = AsyncMock()
        client._get = AsyncMock(return_value={
            "homeRegion": {"baseUri": {"content": "https://x"}}
        })
        await resolve_home_region(client, "WAUZZZ8X3KA999999")
        # The call URL uses DISCOVERY_BASE + the documented path.
        client._get.assert_awaited_once_with(
            f"{DISCOVERY_BASE}/api/cs/vds/v1/vehicles/WAUZZZ8X3KA999999/homeRegion"
        )

    @pytest.mark.asyncio
    async def test_cache_hit_skips_network(self):
        cache = HomeRegionCache()
        cache.set("WAUZZZ8X3KA000001", "https://cached.example")
        client = AsyncMock()
        client._get = AsyncMock(side_effect=AssertionError(
            "should not hit network when cache is fresh"
        ))
        result = await resolve_home_region(client, "WAUZZZ8X3KA000001", cache=cache)
        assert result == "https://cached.example"
        client._get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_then_populates(self):
        cache = HomeRegionCache()
        client = AsyncMock()
        client._get = AsyncMock(return_value={
            "homeRegion": {"baseUri": {"content": "https://resolved.example"}}
        })
        result = await resolve_home_region(client, "VIN_NEW_LOOKUP", cache=cache)
        assert result == "https://resolved.example"
        assert cache.get("VIN_NEW_LOOKUP") == "https://resolved.example"


class TestResolveHomeRegionFallback:
    @pytest.mark.asyncio
    async def test_network_error_returns_default(self):
        client = AsyncMock()
        client._get = AsyncMock(side_effect=ConnectionError("network down"))
        result = await resolve_home_region(client, "WAUZZZ8X3KA000001")
        assert result == DEFAULT_BASE

    @pytest.mark.asyncio
    async def test_404_returns_default(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = AsyncMock()
        client._get = AsyncMock(side_effect=APIError(404, "url", ""))
        result = await resolve_home_region(client, "WAUZZZ8X3KA000001")
        assert result == DEFAULT_BASE

    @pytest.mark.asyncio
    async def test_malformed_response_returns_default(self):
        """Missing homeRegion key, missing baseUri, non-string content,
        non-http URL → all default."""
        client = AsyncMock()
        for bad_response in (
            None,
            {},
            {"homeRegion": None},
            {"homeRegion": {}},
            {"homeRegion": {"baseUri": None}},
            {"homeRegion": {"baseUri": {}}},
            {"homeRegion": {"baseUri": {"content": None}}},
            {"homeRegion": {"baseUri": {"content": 42}}},
            {"homeRegion": {"baseUri": {"content": "not-a-url"}}},
        ):
            client._get = AsyncMock(return_value=bad_response)
            result = await resolve_home_region(client, "WAUZZZ8X3KA000001")
            assert result == DEFAULT_BASE, f"failed for {bad_response!r}"

    @pytest.mark.asyncio
    async def test_failure_caches_default_too(self):
        """A failed lookup should cache DEFAULT_BASE so we don't retry
        every time. evcc does this for the same reason."""
        cache = HomeRegionCache()
        client = AsyncMock()
        client._get = AsyncMock(side_effect=ConnectionError("transient"))
        result = await resolve_home_region(client, "VIN_FAIL_TEST", cache=cache)
        assert result == DEFAULT_BASE
        # Cache should now contain DEFAULT_BASE for that VIN.
        assert cache.get("VIN_FAIL_TEST") == DEFAULT_BASE

    @pytest.mark.asyncio
    async def test_no_cache_provided_works_too(self):
        """Passing cache=None should still work — useful for one-off
        diagnostics calls."""
        client = AsyncMock()
        client._get = AsyncMock(return_value={
            "homeRegion": {"baseUri": {"content": "https://abc"}}
        })
        result = await resolve_home_region(client, "WAUZZZ8X3KA000001", cache=None)
        assert result == "https://abc"


class TestDefaultBaseConsistency:
    def test_default_base_matches_vw_eu_base(self):
        """If DEFAULT_BASE drifts from vw_eu._BASE, the wire-in plan
        documented in _home_region.py becomes incorrect. Lock the
        invariant."""
        from custom_components.vag_connect.cariad.api.vw_eu import _BASE as VW_BASE
        assert DEFAULT_BASE == VW_BASE
