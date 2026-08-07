# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1078 — a short-token brand (Škoda) polled at the default interval refreshes
its token on almost every cycle and trips the refresh-storm guard, then reports
it as "reauthenticate" — which does nothing for a frequency problem. The fix:
the DATA-plane storm sets a flag the coordinator turns into an actionable
"raise your update interval" Repair, and a brand-aware recommended interval
keeps Škoda out of the trap in the first place.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.const import (
    DEFAULT_SCAN_INTERVAL,
    recommended_scan_interval,
)
from custom_components.vag_connect.cariad.api import base as _base
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import TokenSet


def _client() -> VWEUClient:
    c = VWEUClient(MagicMock(), "u@t.de", "pw")
    c._tokens = TokenSet("acc", "ref", "id")
    # A refresh that always succeeds — we exercise the storm guard, not auth.
    c._auth.refresh = AsyncMock(return_value=TokenSet("acc2", "ref2", "id2"))
    return c


class TestRecommendedInterval:
    def test_skoda_is_raised_to_thirty(self) -> None:
        assert recommended_scan_interval("skoda") == 30
        assert recommended_scan_interval("Skoda") == 30  # case-insensitive

    def test_other_brands_keep_the_default(self) -> None:
        assert recommended_scan_interval("audi") == DEFAULT_SCAN_INTERVAL
        assert recommended_scan_interval("volkswagen") == DEFAULT_SCAN_INTERVAL
        assert recommended_scan_interval(None) == DEFAULT_SCAN_INTERVAL


class TestStormFlag:
    def test_data_storm_sets_the_flag(self) -> None:
        c = _client()
        assert c.refresh_storm_detected is False
        for _ in range(_base._REFRESH_MAX_PER_HOUR):
            asyncio.run(c._refresh_tokens())
        with pytest.raises(AuthenticationError, match="storm"):
            asyncio.run(c._refresh_tokens())
        assert c.refresh_storm_detected is True

    def test_command_storm_does_not_set_the_data_flag(self) -> None:
        # A remote-command storm has its own budget and its own remedy; it must
        # not raise the "raise your poll interval" Repair for reads.
        c = _client()
        for _ in range(_base._REFRESH_MAX_PER_HOUR):
            asyncio.run(c._refresh_tokens(for_command=True))
        with pytest.raises(AuthenticationError, match="storm"):
            asyncio.run(c._refresh_tokens(for_command=True))
        assert c.refresh_storm_detected is False

    def test_successful_refresh_clears_the_flag(self) -> None:
        c = _client()
        c.refresh_storm_detected = True
        asyncio.run(c._refresh_tokens())  # fresh budget → succeeds → clears
        assert c.refresh_storm_detected is False


class TestRepair:
    def test_raise_carries_brand_and_intervals(self) -> None:
        from custom_components.vag_connect import repairs

        hass = MagicMock()
        with patch.object(repairs.ir, "async_create_issue") as m:
            repairs.raise_issue_refresh_interval_too_frequent(
                hass, "entry1", brand="skoda", current=10, recommended=30
            )
        m.assert_called_once()
        kw = m.call_args.kwargs
        assert kw["translation_key"] == "refresh_interval_too_frequent"
        assert kw["translation_placeholders"] == {
            "brand": "skoda",
            "current": "10",
            "recommended": "30",
        }

    def test_clear_deletes_the_issue(self) -> None:
        from custom_components.vag_connect import repairs

        hass = MagicMock()
        with patch.object(repairs.ir, "async_delete_issue") as m:
            repairs.clear_refresh_interval_issue(hass, "entry1")
        m.assert_called_once()
