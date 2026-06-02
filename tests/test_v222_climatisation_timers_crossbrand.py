# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.2 — VW EU/Audi climatisationTimers cross-brand expansion.

Triggered by Scout #248 (arvcer, 2026-05-17). The 4 reported paths
were already silenced+parsed in main since v1.17.5/v1.19.3 (arvcer's
installation is on an older version). 3 of 4 fields are actively
populating dataclass fields; the 4th (`climatisationTimers.
climatisationTimersStatus.value`) was a silenced container with
2-key shape but never drilled.

This PR mirrors the existing `departureTimers` parser pattern
(Phase 7 PR #2) for climatisationTimers, populating the existing
`climate_timer_enabled_count` field (cross-brand from Skoda PR #4
Phase 7) on VW EU + Audi.

Defensive: shape unverified per scout `{2 keys}`. Assumption is
mirror of departureTimers (timers list + carCapturedTimestamp).
If actual leaves differ, list-check guard keeps field None
(phantom-gate honest, no false-positive zero count).

"Two timers? Well, that's twice the timer." — Sheldon Cooper.
"""

from __future__ import annotations


class TestClimatisationTimerCountAggregation:
    """Mirror of vw_eu.py climatisationTimers walker."""

    def _count(self, timers):
        if not timers:
            return None
        return sum(
            1 for t in timers if isinstance(t, dict) and t.get("enabled") is True
        )

    def test_all_three_enabled(self) -> None:
        timers = [{"enabled": True}, {"enabled": True}, {"enabled": True}]
        assert self._count(timers) == 3

    def test_only_one_enabled(self) -> None:
        timers = [{"enabled": True}, {"enabled": False}]
        assert self._count(timers) == 1

    def test_none_enabled(self) -> None:
        assert self._count([{"enabled": False}, {"enabled": False}]) == 0

    def test_empty_list_stays_none(self) -> None:
        # Critical: phantom-gate fires on non-PHEV non-EV that doesn't
        # ship the climate timers block at all
        assert self._count([]) is None

    def test_non_dict_entries_safely_skipped(self) -> None:
        # Defensive: backend rotation might ship string entries
        timers = [{"enabled": True}, "MALFORMED", {"enabled": True}]
        assert self._count(timers) == 2

    def test_truthy_string_not_counted(self) -> None:
        # is True rejects "true" / 1 — only literal bool
        timers = [{"enabled": "true"}, {"enabled": True}]
        assert self._count(timers) == 1


class TestVWEuClimatisationParserWiring:
    """Source-level checks for the new wiring."""

    def _source(self) -> str:
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        return inspect.getsource(vw_eu)

    def test_climatisation_timers_read(self) -> None:
        src = self._source()
        assert 'v(\n            raw, "climatisationTimers"' in src or (
            '"climatisationTimers"' in src
            and '"climatisationTimersStatus"' in src
        )

    def test_climate_timer_count_assigned(self) -> None:
        src = self._source()
        assert "d.climate_timer_enabled_count" in src


class TestCrossBrandReuse:
    """`climate_timer_enabled_count` from Phase 7 PR #4 (Skoda).
    This PR adds VW EU/Audi parser hook — same dataclass field,
    expanded brand coverage. No new entity description, no new
    translation needed."""

    def test_existing_dataclass_field(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="X")
        assert hasattr(d, "climate_timer_enabled_count")

    def test_sensor_description_unchanged(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "climate_timer_enabled_count" in keys

    def test_phantom_gate_still_applies(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "climate_timer_enabled_count" in _DATA_PRESENT_REQUIRED


class TestBrandCoverageMatrix:
    """After this PR, climate_timer_enabled_count is populated by
    at least 2 brand parsers (Skoda + VW EU/Audi)."""

    def test_skoda_parser_assigns_field(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.api import skoda

        assert "climate_timer_enabled_count" in inspect.getsource(skoda)

    def test_vw_eu_parser_assigns_field(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        assert "climate_timer_enabled_count" in inspect.getsource(vw_eu)
