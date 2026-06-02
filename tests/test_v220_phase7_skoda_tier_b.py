# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 7 PR #4 — Skoda tier-B trio from scout-audit.

Three Skoda mysmob fields silenced since v1.12.2 (#107 tritanium73
2026-05-01) but never parsed:

| Field | Path |
|-------|------|
| `climate_timer_enabled_count` | `air-conditioning.timers[*].enabled` |
| `climate_running_requests_count` | `air-conditioning.runningRequests` |
| `vehicle_at_saved_location` | `charging.isVehicleInSavedLocation` |

`climate_timer_enabled_count` is Skoda parity to VW EU/Audi's
`departure_timer_enabled_count` from PR #2.

"Knock knock knock Penny. Knock knock knock Penny. Knock knock knock
running-requests-count." — Sheldon Cooper, on pending-modem-ack
diagnostics
"""

from __future__ import annotations

import pytest


class TestModelFields:
    @pytest.mark.parametrize(
        "field",
        [
            "climate_timer_enabled_count",
            "climate_running_requests_count",
            "vehicle_at_saved_location",
        ],
    )
    def test_field_exists_with_default_none(self, field: str) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, field)
        assert getattr(d, field) is None


class TestClimateTimerCount:
    """Skoda parity to PR #2 departure timer count — same aggregation."""

    def _count(self, timers):
        if not isinstance(timers, list) or not timers:
            return None
        return sum(
            1 for t in timers if isinstance(t, dict) and t.get("enabled") is True
        )

    def test_all_three_enabled(self) -> None:
        timers = [
            {"id": 1, "enabled": True},
            {"id": 2, "enabled": True},
            {"id": 3, "enabled": True},
        ]
        assert self._count(timers) == 3

    def test_only_one_enabled(self) -> None:
        timers = [
            {"id": 1, "enabled": True},
            {"id": 2, "enabled": False},
            {"id": 3, "enabled": False},
        ]
        assert self._count(timers) == 1

    def test_none_enabled(self) -> None:
        timers = [{"enabled": False}, {"enabled": False}]
        assert self._count(timers) == 0

    def test_empty_list_stays_none(self) -> None:
        # Critical: empty list (no timers at all) → None, NOT 0.
        # Phantom-gate hides the entity on brands without the block.
        assert self._count([]) is None

    def test_non_list_stays_none(self) -> None:
        assert self._count(None) is None
        assert self._count({}) is None

    def test_non_dict_entries_skipped(self) -> None:
        # Defensive: backend rotation could ship string entries
        timers = [{"enabled": True}, "MALFORMED", {"enabled": True}]
        assert self._count(timers) == 2

    def test_truthy_string_not_counted(self) -> None:
        # `is True` rejects truthy variants — only literal True counts
        timers = [{"enabled": "true"}, {"enabled": True}]
        assert self._count(timers) == 1


class TestClimateRunningRequests:
    """Count of in-flight modem-ack waiting requests."""

    def _parse(self, running):
        if isinstance(running, list):
            return len(running)
        return None

    def test_three_pending(self) -> None:
        assert self._parse([{}, {}, {}]) == 3

    def test_empty_list_returns_zero(self) -> None:
        # NB: distinct from `climate_timer_enabled_count` semantics —
        # empty `runningRequests` is meaningful (= "no commands
        # pending"), so 0 is the correct value. The list-presence
        # itself is the brand-restriction signal.
        assert self._parse([]) == 0

    def test_missing_returns_none(self) -> None:
        assert self._parse(None) is None

    def test_non_list_returns_none(self) -> None:
        assert self._parse({}) is None
        assert self._parse("requests") is None


class TestVehicleAtSavedLocation:
    """`isinstance(..., bool)` guard."""

    def _parse(self, raw):
        if isinstance(raw, bool):
            return raw
        return None

    def test_true_assigned(self) -> None:
        assert self._parse(True) is True

    def test_false_assigned(self) -> None:
        assert self._parse(False) is False

    def test_none_stays_none(self) -> None:
        assert self._parse(None) is None

    def test_int_one_rejected(self) -> None:
        # `isinstance(1, bool) is False` — see PR #2 test for context
        assert self._parse(1) is None

    def test_string_true_rejected(self) -> None:
        assert self._parse("true") is None


class TestEntityRegistration:
    @pytest.mark.parametrize(
        "key",
        [
            "climate_timer_enabled_count",
            "climate_running_requests_count",
        ],
    )
    def test_sensor_described(self, key: str) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert key in keys

    @pytest.mark.parametrize(
        "key",
        [
            "climate_timer_enabled_count",
            "climate_running_requests_count",
        ],
    )
    def test_sensor_phantom_gated(self, key: str) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert key in _DATA_PRESENT_REQUIRED

    def test_vehicle_at_saved_location_binary_sensor_described(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
        )

        keys = {d.key for d in BINARY_DESCRIPTIONS}
        assert "vehicle_at_saved_location" in keys

    def test_vehicle_at_saved_location_phantom_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "vehicle_at_saved_location" in _DATA_PRESENT_REQUIRED


class TestTranslationCoverage:
    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    @pytest.mark.parametrize(
        "key",
        [
            "climate_timer_enabled_count",
            "climate_running_requests_count",
        ],
    )
    def test_lang_has_sensor_key(self, lang: str, key: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert key in data["entity"]["sensor"], (
            f"{lang}: missing entity.sensor.{key}"
        )

    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_binary_sensor_key(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "vehicle_at_saved_location" in data["entity"]["binary_sensor"]

    def test_strings_json_coverage(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        for key in (
            "climate_timer_enabled_count",
            "climate_running_requests_count",
        ):
            assert key in data["entity"]["sensor"]
        assert "vehicle_at_saved_location" in data["entity"]["binary_sensor"]
