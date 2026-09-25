# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1 — a vw.de charging auth-wall must not skip the maintenance read.

Confirmed on three cars (#1313 realynot, #923 JosefAuer84 + dazzzl): charging
(realm vwag-weconnect) returned 403 and, because the two live reads shared one
try, the maintenance read (realm vw-de) — which carries the mileage — never ran.
Each core read now has its own guard; a wall on one is recorded and the next read
still runs. Nothing is re-raised (no needless refresh+retry) as long as some data
came back.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

MOD = "custom_components.vag_connect.cariad.auth._website_authproxy"
VIN = "WVWZZZ0000000345"


def _conn() -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c.probe_outcomes = {}
    c._vin_backend = {}
    c.get_relations = AsyncMock(return_value=MagicMock(vehicles=[]))
    c._gdc = MagicMock(return_value="gdc")
    c.get_warning_lights = AsyncMock(return_value=None)
    c.get_last_lock_action = AsyncMock(return_value=None)
    c.get_relation_detail = AsyncMock(return_value=None)
    c.get_exterior_images = AsyncMock(return_value=[])
    c.get_master_data = AsyncMock(return_value=MagicMock(
        model_name=None, model_year=None, exterior_color_text=None, engine=None,
    ))
    c._should_probe_position = MagicMock(return_value=False)
    c._should_probe_soh = MagicMock(return_value=False)
    c._should_probe_measurements = MagicMock(return_value=False)
    return c


def test_charging_wall_does_not_skip_maintenance() -> None:
    c = _conn()
    c._get_json = AsyncMock(side_effect=[
        AuthenticationError("charging 403"),
        {"data": {"maintenanceStatus": {}}},
    ])
    seen = {}

    def _map_maint(payload, d):
        d.mileage_km = 12345
        seen["maint"] = True
        return d

    with patch(f"{MOD}.map_maintenance_to_vehicle_data", _map_maint):
        d = asyncio.run(c.get_vehicle_data(VIN))
    assert seen.get("maint") is True          # maintenance read despite charging wall
    assert d.mileage_km == 12345              # its data survived (no re-raise)
    assert c.probe_outcomes.get("vwde_core_read:charging")  # wall recorded


def test_both_core_walls_and_empty_tail_reraises() -> None:
    c = _conn()
    c._get_json = AsyncMock(side_effect=[
        AuthenticationError("charging 401"),
        AuthenticationError("maintenance 401"),
    ])
    with pytest.raises(AuthenticationError):
        asyncio.run(c.get_vehicle_data(VIN))
    # both walls recorded before the re-raise
    assert c.probe_outcomes.get("vwde_core_read:charging")
    assert c.probe_outcomes.get("vwde_core_read:maintenance")
