# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#649 — Škoda health warning-lights false-positive.

The MySkoda "Vehicle Health Report" shows "All good" / green checkmarks
for a healthy car, yet every Škoda warning binary_sensor
(warning_active / warning_engine / warning_brakes / warning_tyre)
reported "Problem". Root cause: the health endpoint returns ONE
`warningLights` entry per monitored category (ENGINE/BRAKES/TYRE/…)
regardless of whether a defect exists — a healthy car still has a full
list, each entry with an EMPTY `defects` array. The old code flagged a
warning whenever the list was non-empty and added every category to the
"seen" set unconditionally, so every Škoda flipped to Problem.

Fix: a category counts only when its own `defects` list is non-empty;
warning_active/count key off the *defective* categories, not the raw
list length. An all-good car yields all-False.
"""

from __future__ import annotations

from custom_components.vag_connect.cariad.api.skoda import (
    parse_skoda_warning_lights,
)


def _health_all_good() -> list[dict]:
    """Healthy Karoq: every category present, all `defects` empty."""
    return [
        {"category": "ENGINE", "defects": []},
        {"category": "BRAKES", "defects": []},
        {"category": "TYRE", "defects": []},
        {"category": "OIL", "defects": []},
    ]


class TestAllGoodYieldsNoWarning:
    """#649 core: empty defects on every category => all-False."""

    def test_all_good_no_warning_active(self) -> None:
        warn = parse_skoda_warning_lights(_health_all_good())
        assert warn["warning_active"] is False

    def test_all_good_count_zero(self) -> None:
        warn = parse_skoda_warning_lights(_health_all_good())
        assert warn["warning_count"] == 0

    def test_all_good_per_category_false(self) -> None:
        warn = parse_skoda_warning_lights(_health_all_good())
        assert warn["warning_engine"] is False
        assert warn["warning_brakes"] is False
        assert warn["warning_tyre"] is False
        assert warn["warning_oil"] is False

    def test_all_good_no_messages(self) -> None:
        warn = parse_skoda_warning_lights(_health_all_good())
        assert "warning_messages" not in warn


class TestMissingOrEmptyList:
    """An absent/empty warningLights list is a no-op (nothing to assign)."""

    def test_none(self) -> None:
        assert parse_skoda_warning_lights(None) == {}

    def test_empty_list(self) -> None:
        assert parse_skoda_warning_lights([]) == {}

    def test_non_list(self) -> None:
        assert parse_skoda_warning_lights({"warningLights": []}) == {}


class TestRealDefectFlagsCorrectCategory:
    """A non-empty `defects` list flips exactly the right warning."""

    def test_engine_defect_only_engine_true(self) -> None:
        lights = [
            {"category": "ENGINE", "defects": [{"text": "Check engine"}]},
            {"category": "BRAKES", "defects": []},
            {"category": "TYRE", "defects": []},
        ]
        warn = parse_skoda_warning_lights(lights)
        assert warn["warning_active"] is True
        assert warn["warning_count"] == 1
        assert warn["warning_engine"] is True
        assert warn["warning_brakes"] is False
        assert warn["warning_tyre"] is False
        assert warn["warning_messages"] == "Check engine"

    def test_tyre_alias_tire_flags_tyre(self) -> None:
        lights = [{"category": "TIRE", "defects": [{"text": "Low pressure"}]}]
        warn = parse_skoda_warning_lights(lights)
        assert warn["warning_tyre"] is True
        assert warn["warning_active"] is True

    def test_brake_alias_flags_brakes(self) -> None:
        lights = [{"category": "BRAKE", "defects": [{"text": "Pads worn"}]}]
        warn = parse_skoda_warning_lights(lights)
        assert warn["warning_brakes"] is True

    def test_multiple_defects_counted_by_category(self) -> None:
        lights = [
            {"category": "ENGINE", "defects": [{"text": "A"}]},
            {"category": "TYRE", "defects": [{"text": "B"}, {"text": "C"}]},
            {"category": "BRAKES", "defects": []},
        ]
        warn = parse_skoda_warning_lights(lights)
        # two DEFECTIVE categories, not three list entries
        assert warn["warning_count"] == 2
        assert warn["warning_engine"] is True
        assert warn["warning_tyre"] is True
        assert warn["warning_brakes"] is False
        assert warn["warning_messages"] == "A | B | C"


class TestMalformedEntriesIgnored:
    """Defensive: junk entries don't crash and don't false-flag."""

    def test_non_dict_entries_skipped(self) -> None:
        lights = ["junk", 42, {"category": "ENGINE", "defects": []}]
        warn = parse_skoda_warning_lights(lights)
        assert warn["warning_active"] is False

    def test_defect_without_text_still_flags_category(self) -> None:
        lights = [{"category": "ENGINE", "defects": [{"priority": "HIGH"}]}]
        warn = parse_skoda_warning_lights(lights)
        assert warn["warning_engine"] is True
        # no text => no message string
        assert "warning_messages" not in warn
