# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Battery State of Health (%). VW ships no SoH field and even the official app
derives none, so we cannot guess it. When the user supplies the car's nameplate
NET capacity (CONF_BATTERY_NOMINAL_KWH), SoH% = current max capacity / nominal,
bounded to a plausibility band so a per-entry nominal only applies to the car it
actually fits (multi-car safety).
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import _battery_soh_pct


class TestSoH:
    def test_degraded_and_as_new(self) -> None:
        assert _battery_soh_pct(73.0, 77) == 95    # a 77 kWh pack down to 73
        assert _battery_soh_pct(77.0, 77) == 100   # as new
        assert _battery_soh_pct(51.0, 52) == 98

    def test_none_without_a_nominal(self) -> None:
        assert _battery_soh_pct(73.0, 0) is None
        assert _battery_soh_pct(73.0, None) is None
        assert _battery_soh_pct(None, 77) is None
        assert _battery_soh_pct(0, 77) is None

    def test_plausibility_band_excludes_gross_mismatch(self) -> None:
        # e-up! capacity (32) under an ID.4 nominal (77) -> below 60% -> skip,
        # so a multi-car account doesn't show a wrong SoH for the other car.
        assert _battery_soh_pct(32.0, 77) is None
        # nominal too small (>105%) -> skip
        assert _battery_soh_pct(85.0, 77) is None

    def test_booleans_are_never_read_as_numbers(self) -> None:
        assert _battery_soh_pct(True, 77) is None
        assert _battery_soh_pct(73.0, True) is None
