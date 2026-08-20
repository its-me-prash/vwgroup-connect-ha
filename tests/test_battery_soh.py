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


class TestSoHPrecedence:
    """A REAL backend SoH (Audi batteryHealthState) must win over the
    nominal-derived estimate; the estimate is only a fallback (v4.1.0b1)."""

    def _make_coord(self):
        from unittest.mock import MagicMock, AsyncMock
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.const import CONF_BATTERY_NOMINAL_KWH
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.async_add_executor_job = AsyncMock(return_value=None)
        coord.entry = MagicMock()
        # a nominal that WOULD derive 95% from a 73 kWh current-max pack
        coord.entry.data = {"brand": "audi", "username": "t@t.com", "password": "x",
                            "spin": "", "update_interval": 300,
                            CONF_BATTERY_NOMINAL_KWH: 77}
        coord._vehicles_lock = __import__("threading").Lock()
        coord._cariad_client = MagicMock()
        coord._was_available = True
        coord.data = None
        return coord

    def test_measured_soh_survives_a_configured_nominal(self) -> None:
        import asyncio
        coord = self._make_coord()
        # backend already set 88 (real SoH); the nominal would derive 95
        data = {"battery_cap_kwh": 73.0, "battery_soh_pct": 88,
                "latitude": None, "longitude": None}
        result = asyncio.run(coord._enrich(data))
        assert result["battery_soh_pct"] == 88  # measured wins, not the 95 estimate

    def test_derived_soh_still_fills_in_when_backend_gave_none(self) -> None:
        import asyncio
        coord = self._make_coord()
        data = {"battery_cap_kwh": 73.0,  # no battery_soh_pct from the backend
                "latitude": None, "longitude": None}
        result = asyncio.run(coord._enrich(data))
        assert result["battery_soh_pct"] == 95  # fallback estimate applies
