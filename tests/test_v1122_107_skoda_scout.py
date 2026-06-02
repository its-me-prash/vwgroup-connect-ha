# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.12.2 — #107 Skoda Scout coverage (tritanium73's report).

First community Scout report from a non-maintainer (tritanium73 on
2026-05-01). 14 new paths reported across 4 endpoints. v1.12.2
registers them in EXPECTED_KEYS["skoda"] so the Scout stops firing.
"""

from __future__ import annotations



class TestSkodaScout107:
    def test_renders_lightmode_darkmode_registered_at_two_segments(self):
        """v1.12.2 (#107) — wildcards `renders.lightMode.*` only matched
        3-segment paths; tritanium73's report shows 2-segment
        `renders.lightMode` was unmatched. Now both registered."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["skoda"]["vehicle-status"]
        for path in ("renders.lightMode", "renders.darkMode"):
            assert _path_matches(path, keys), f"missing: {path}"
        # Wildcards still work for 3-segment children
        assert _path_matches("renders.lightMode.MAIN_VIEW", keys)

    def test_air_conditioning_six_new_paths(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["skoda"]["air-conditioning"]
        for path in (
            "runningRequests",
            "steeringWheelPosition",
            "windowHeatingState.unspecified",
            "timers",
            "outsideTemperature",
            "errors",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_driving_range_carType_and_primaryEngineRange(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["skoda"]["driving-range"]
        assert _path_matches("carType", keys)
        assert _path_matches("primaryEngineRange", keys)

    def test_maintenance_four_new_meta_blocks(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["skoda"]["maintenance"]
        for path in (
            "maintenanceReport.capturedAt",
            "preferredServicePartner",
            "predictiveMaintenance",
            "customerService",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_full_107_payload_silent(self):
        """Replay verbatim Scout findings from #107. All 14 paths must
        classify as expected — Scout returns empty per endpoint."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )

        # vehicle-status — renders block
        vs = {
            "renders": {"lightMode": {}, "darkMode": {}},
        }
        assert list(detect_unexpected("skoda", "vehicle-status", vs)) == []

        # air-conditioning — 6 new paths (use empty containers / scalars)
        ac = {
            "runningRequests": [],
            "steeringWheelPosition": "LEFT",
            "windowHeatingState": {"unspecified": "INVALID"},
            "timers": [],
            "outsideTemperature": {},
            "errors": [],
        }
        assert list(detect_unexpected("skoda", "air-conditioning", ac)) == []

        # driving-range — 2 new paths
        dr = {"carType": "diesel", "primaryEngineRange": {}}
        assert list(detect_unexpected("skoda", "driving-range", dr)) == []

        # maintenance — 4 new paths
        m = {
            "maintenanceReport": {"capturedAt": "2026-04-30T17:10:52Z"},
            "preferredServicePartner": {},
            "predictiveMaintenance": {},
            "customerService": {},
        }
        assert list(detect_unexpected("skoda", "maintenance", m)) == []

    def test_seat_cupra_inheritance_NOT_affected(self):
        """Defensive: SEAT/CUPRA share OLA endpoints, NOT Skoda's
        mysmob endpoints. The new ``vehicle-status``/``air-conditioning``/
        ``driving-range``/``maintenance`` registrations stay
        Skoda-only."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        # SEAT/CUPRA endpoints don't include any of these names
        cupra_endpoints = set(EXPECTED_KEYS["cupra"].keys())
        assert "vehicle-status" not in cupra_endpoints
        assert "driving-range" not in cupra_endpoints
        assert "maintenance" not in cupra_endpoints
