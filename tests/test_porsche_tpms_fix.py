# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche TPMS parsing — b20 (2026-09-08, androguard enum dump).

The real `MeasurementType` enum has no aggregate `TIRE_PRESSURE` key; the
app requests four separate per-corner keys instead
(`TIRE_PRESSURE_FRONT_LEFT` etc.). The old code requested and parsed a key
that doesn't exist, which is very likely why TPMS sensors have been empty.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.porsche import _MEASUREMENTS, PorscheClient

_VIN = "WP0ZZZ99ZTS300001"


def _client() -> PorscheClient:
    return PorscheClient.__new__(PorscheClient)


class TestMeasurementListCorrections:
    def test_aggregate_tire_pressure_key_no_longer_requested(self) -> None:
        assert "TIRE_PRESSURE" not in _MEASUREMENTS

    def test_four_percorner_tire_pressure_keys_requested(self) -> None:
        for key in (
            "TIRE_PRESSURE_FRONT_LEFT", "TIRE_PRESSURE_FRONT_RIGHT",
            "TIRE_PRESSURE_REAR_LEFT", "TIRE_PRESSURE_REAR_RIGHT",
        ):
            assert key in _MEASUREMENTS

    def test_dead_charging_state_key_removed(self) -> None:
        """CHARGING_STATE was never a real measurement key (absent from the
        real 86/87-member enum) and was never parsed into anything — pure
        dead weight in the request."""
        assert "CHARGING_STATE" not in _MEASUREMENTS


class TestTirePressureParsing:
    @pytest.mark.asyncio
    async def test_percorner_keys_populate_tire_pressure_fields(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={
            "measurements": [
                {"key": "TIRE_PRESSURE_FRONT_LEFT", "value": {"currentPressure": 235.0, "warning": False}},
                {"key": "TIRE_PRESSURE_FRONT_RIGHT", "value": {"currentPressure": 230.0, "warning": False}},
                {"key": "TIRE_PRESSURE_REAR_LEFT", "value": {"currentPressure": 240.0, "warning": True}},
                {"key": "TIRE_PRESSURE_REAR_RIGHT", "value": {"currentPressure": 240.0, "warning": False}},
            ],
        })
        d = await c.get_status(_VIN)
        assert d.tire_pressure_front_left_bar == 2.35
        assert d.tire_pressure_front_right_bar == 2.3
        assert d.tire_pressure_rear_left_bar == 2.4
        assert d.tire_pressure_rear_right_bar == 2.4
        assert d.tire_pressure_warning is True

    @pytest.mark.asyncio
    async def test_missing_tire_pressure_measurements_stay_none(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": []})
        d = await c.get_status(_VIN)
        assert d.tire_pressure_front_left_bar is None
        assert d.tire_pressure_warning is None
