# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 7 PR #2 — VW EU/Audi tier-B diagnostics.

Two CARIAD-BFF fields that the parser already READS for adjacent
features (timers list, readiness block) but never exposes as
aggregate / diagnostic entities:

| Field | Type | Source path |
|-------|------|-------------|
| `departure_timer_enabled_count` | int (0-3) | `departureTimers.departureTimersStatus.value.timers[*].enabled` |
| `daily_power_budget_available` | bool | `readiness.readinessStatus.value.connectionState.dailyPowerBudgetAvailable` |

Both VW EU + Audi only. Other brands' parsers don't populate these
aggregates → fields stay None → no phantom entities.

"Three timers and only one is enabled? Yes, that is mathematically
one. I do not need to count higher to know this." — Sheldon Cooper,
on aggregate counters
"""

from __future__ import annotations

import pytest


class TestModelFields:
    def test_departure_timer_enabled_count_default(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "departure_timer_enabled_count")
        assert d.departure_timer_enabled_count is None

    def test_daily_power_budget_available_default(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "daily_power_budget_available")
        assert d.daily_power_budget_available is None


class TestDepartureTimerCountAggregation:
    """Mirror of vw_eu.py aggregation — `sum(1 for t if t.enabled is True)`."""

    def _count(self, timers):
        if not timers:
            return None  # not set
        return sum(1 for t in timers if t.get("enabled") is True)

    def test_all_three_enabled(self) -> None:
        timers = [{"enabled": True}, {"enabled": True}, {"enabled": True}]
        assert self._count(timers) == 3

    def test_only_first_enabled(self) -> None:
        timers = [{"enabled": True}, {"enabled": False}, {"enabled": False}]
        assert self._count(timers) == 1

    def test_none_enabled(self) -> None:
        timers = [{"enabled": False}, {"enabled": False}, {"enabled": False}]
        assert self._count(timers) == 0

    def test_empty_list_stays_none(self) -> None:
        # Critical for phantom protection — empty list means no timer
        # block was returned at all (likely non-EV brand) — field
        # must stay None so the gate hides the entity.
        assert self._count([]) is None

    def test_missing_enabled_key_treated_as_false(self) -> None:
        # Defensive: backend could omit `enabled` on a malformed timer.
        # `.get("enabled") is True` returns False → counts as not-enabled.
        timers = [{"enabled": True}, {"departureTime": "ignored"}]
        assert self._count(timers) == 1

    def test_string_enabled_treated_as_false(self) -> None:
        # Defensive: `is True` rejects truthy strings like "ON" — only
        # the literal boolean True counts.
        timers = [{"enabled": "true"}, {"enabled": True}]
        assert self._count(timers) == 1


class TestDailyPowerBudgetParser:
    """`isinstance(..., bool)` guard rejects non-bool variants."""

    def _parse(self, raw_value):
        # Mirror of the vw_eu.py parser logic
        if isinstance(raw_value, bool):
            return raw_value
        return None

    def test_true_assigned(self) -> None:
        assert self._parse(True) is True

    def test_false_assigned(self) -> None:
        assert self._parse(False) is False

    def test_none_stays_none(self) -> None:
        assert self._parse(None) is None

    def test_string_true_rejected(self) -> None:
        # Defensive: string variants must NOT trip — only literal bool
        assert self._parse("true") is None
        assert self._parse("ON") is None

    def test_int_one_rejected(self) -> None:
        # Subtle: `isinstance(1, bool)` is False in Python — int 1 is
        # NOT treated as a bool by isinstance. Good for our guard.
        assert self._parse(1) is None
        assert self._parse(0) is None


class TestEntityRegistration:
    def test_daily_power_budget_described(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
        )

        keys = {d.key for d in BINARY_DESCRIPTIONS}
        assert "daily_power_budget_available" in keys

    def test_daily_power_budget_phantom_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "daily_power_budget_available" in _DATA_PRESENT_REQUIRED

    def test_departure_count_sensor_described(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "departure_timer_enabled_count" in keys

    def test_departure_count_sensor_phantom_gated(self) -> None:
        from custom_components.vag_connect.sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "departure_timer_enabled_count" in _DATA_PRESENT_REQUIRED


class TestTranslationCoverage:
    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_sensor_key(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "departure_timer_enabled_count" in data["entity"]["sensor"]

    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_binary_sensor_key(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert (
            "daily_power_budget_available" in data["entity"]["binary_sensor"]
        )

    def test_strings_json_coverage(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        assert "departure_timer_enabled_count" in data["entity"]["sensor"]
        assert (
            "daily_power_budget_available" in data["entity"]["binary_sensor"]
        )
