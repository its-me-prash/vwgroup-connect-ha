# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""acpp plug&play — optional fuel-level % from a user-configured tank capacity.

The dongle reports litres, not a %, and the tank size isn't in the feed. When
the user sets ``fuel_tank_capacity`` in Options, ``_enrich`` derives a % from the
litres reading (better gauge/UX) — but only fills ``fuel_level`` when the source
gave none, never overwriting a real percentage.
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord(tank_cap):
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "audi_acpp", "username": "t@t.com", "password": "x",
                        "spin": "", "update_interval": 300,
                        "fuel_tank_capacity": tank_cap}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = MagicMock()
    coord._cariad_client._image_data = {}
    coord.vehicle_static_info = {}
    coord._was_available = True
    coord.data = None
    return coord


def _enrich(coord, data):
    return asyncio.run(coord._enrich(data))


def test_fuel_percent_derived_from_configured_tank():
    out = _enrich(_coord(65), {"vin": "V", "fuel_level_liters": 32.5})
    assert out["fuel_tank_capacity_liters"] == 65
    assert out["fuel_level"] == 50            # 32.5 / 65 * 100


def test_no_tank_config_leaves_percent_unset():
    out = _enrich(_coord(0), {"vin": "V", "fuel_level_liters": 32.5})
    assert out.get("fuel_level") is None
    assert out.get("fuel_tank_capacity_liters") is None


def test_real_percent_is_not_overwritten():
    out = _enrich(_coord(65), {"vin": "V", "fuel_level_liters": 32.5, "fuel_level": 48})
    assert out["fuel_level"] == 48            # a real reading wins


def test_percent_clamped_0_100():
    out = _enrich(_coord(50), {"vin": "V", "fuel_level_liters": 60.0})  # over-full edge
    assert out["fuel_level"] == 100
