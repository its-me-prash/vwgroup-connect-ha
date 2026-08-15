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


class TestAdvisedIntervalBeatsTheConfiguredOne:
    """#1115 (starwarsfan) — a Škoda owner who had already raised the interval
    to 31 minutes was still told to "raise it to 30 minutes or more", which
    reads as nonsense and leaves nothing to act on. The advice must always
    exceed what the user already runs."""

    def test_below_recommendation_still_advises_the_recommendation(self) -> None:
        from custom_components.vag_connect.const import advised_scan_interval

        assert advised_scan_interval("skoda", 10) == 30
        assert advised_scan_interval("skoda", 29) == 30

    def test_at_or_above_recommendation_steps_up_from_the_user_value(self) -> None:
        from custom_components.vag_connect.const import advised_scan_interval

        # the reporter's exact case: 31 configured must never advise 30
        assert advised_scan_interval("skoda", 31) > 31
        assert advised_scan_interval("skoda", 30) > 30

    def test_advice_never_exceeds_the_selectable_maximum(self) -> None:
        """#1115 (Reluca / christianmhz) — the step-up must be clamped to the
        config-flow ceiling; advising 61/75 min when the picker caps at 60 is an
        instruction the user physically cannot follow. At the ceiling the advice
        equals the max (the caller then suppresses the impossible repair)."""
        from custom_components.vag_connect.const import (
            MAX_SCAN_INTERVAL,
            advised_scan_interval,
        )

        assert MAX_SCAN_INTERVAL == 60
        for brand in ("skoda", "audi", "volkswagen", None):
            for current in (1, 5, 10, 30, 31, 45, 55, 60, 120):
                advised = advised_scan_interval(brand, current)
                assert advised <= MAX_SCAN_INTERVAL, (
                    f"{brand}/{current} advised {advised} above the {MAX_SCAN_INTERVAL} max"
                )
        # at the ceiling there is no headroom: advice pins to the max, not above
        assert advised_scan_interval("skoda", 60) == 60
        assert advised_scan_interval("skoda", 120) == 60

    def test_advice_exceeds_current_while_headroom_remains(self) -> None:
        from custom_components.vag_connect.const import advised_scan_interval

        for brand in ("skoda", "audi", "volkswagen", None):
            for current in (1, 5, 10, 30, 31, 44):  # all below the 60 ceiling
                assert advised_scan_interval(brand, current) > current, (
                    f"{brand}/{current} advised an interval that is not an increase"
                )


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


class TestBudgetAwareAdvice:
    """#1078 — advise from VW's real X-RateLimit budget when we have it, and
    fall back byte-for-byte to the blunt guard when we don't."""

    def _fn(self):
        from custom_components.vag_connect.const import (
            advised_scan_interval_from_budget,
        )
        return advised_scan_interval_from_budget

    def test_tight_budget_widens_beyond_the_blunt_guard(self) -> None:
        now = 1_700_000_000.0
        # 10 calls left, resets in 10 h → 600 min / 10 = 60; guard(skoda,30)=45.
        assert self._fn()(10, now + 10 * 3600, now, 30, brand="skoda") == 60

    def test_epoch_iso_and_delta_reset_parse_alike(self) -> None:
        from datetime import datetime, timezone

        now = 1_700_000_000.0
        reset = now + 3600  # +1 h → spread 1 → clamps up to the guard floor (30)
        assert self._fn()(60, reset, now, 10, brand="skoda") == 30       # epoch
        assert self._fn()(60, 3600, now, 10, brand="skoda") == 30        # delta-s
        iso = datetime.fromtimestamp(reset, tz=timezone.utc).isoformat()
        assert self._fn()(60, iso, now, 10, brand="skoda") == 30         # ISO-8601

    def test_exhausted_budget_backs_off_to_max(self) -> None:
        from custom_components.vag_connect.const import MAX_SCAN_INTERVAL

        now = 1_700_000_000.0
        assert self._fn()(0, now + 3600, now, 10, brand="skoda") == MAX_SCAN_INTERVAL

    def test_fallback_when_header_never_seen(self) -> None:
        from custom_components.vag_connect.const import advised_scan_interval

        now = 1_700_000_000.0
        for brand in ("skoda", "audi", None):
            for cur in (10, 30, 31, 60):
                assert self._fn()(None, now + 3600, now, cur, brand=brand) == \
                    advised_scan_interval(brand, cur)

    def test_fallback_when_reset_unusable(self) -> None:
        from custom_components.vag_connect.const import advised_scan_interval

        now = 1_700_000_000.0
        g = advised_scan_interval("skoda", 30)
        assert self._fn()(10, "not-a-time", now, 30, brand="skoda") == g  # unparseable
        assert self._fn()(10, now - 60, now, 30, brand="skoda") == g      # reset passed
        assert self._fn()(10, None, now, 30, brand="skoda") == g          # missing
