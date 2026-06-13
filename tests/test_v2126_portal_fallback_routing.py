# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.12.6 — universal EU Data Act portal read-routing fallback.

When a brand's native backend is blocked (e.g. CUPRA/SEAT online services
behind VW's 2026-06 device-attestation wall) the auth resolver falls the
login back to the read-only EU Data Act portal and retains the connector on
``self._eu_portal``. Before this change, only VW EU re-routed its *reads*
through the portal — CUPRA/SEAT/Škoda fell back at login but the next poll
still hit the dead native endpoint, so you'd get a successful login and then
no data. These tests pin that get_vehicles()/get_status() now route through
the portal when it's active, and that the native path is untouched when it
isn't.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.models import VehicleData


def _portal(vins=None, vin="VINPORTAL01"):
    p = MagicMock()
    p.list_vehicle_vins = AsyncMock(return_value=vins if vins is not None else [vin])
    p.get_vehicle_data = AsyncMock(return_value=VehicleData(vin=vin))
    p.login = AsyncMock()
    p.get_relation_nickname = AsyncMock(return_value=None)
    return p


def _seatcupra(brand="cupra"):
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
    return SeatCupraClient(MagicMock(), brand, "u@t.de", "pw")


def _skoda():
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient
    return SkodaClient(MagicMock(), "u@t.de", "pw")


class TestSeatCupraPortalRouting:
    def test_get_vehicles_routes_through_portal(self):
        client = _seatcupra("cupra")
        portal = _portal(vins=["VINPORTAL01"])
        client._eu_portal = portal
        vins = asyncio.run(client.get_vehicles())
        assert vins == ["VINPORTAL01"]
        portal.list_vehicle_vins.assert_awaited_once()

    def test_get_status_routes_through_portal(self):
        client = _seatcupra("seat")
        portal = _portal(vin="VINPORTAL02")
        client._eu_portal = portal
        data = asyncio.run(client.get_status("VINPORTAL02"))
        assert data.vin == "VINPORTAL02"
        portal.get_vehicle_data.assert_awaited_once_with("VINPORTAL02")

    def test_no_portal_uses_native_garage(self):
        # _eu_portal unset (None) → native OLA garage path, not the portal.
        client = _seatcupra("cupra")
        client._user_id = "uid-123"
        client._get = AsyncMock(return_value={"vehicles": [{"vin": "NATIVE0001"}]})
        vins = asyncio.run(client.get_vehicles())
        assert "NATIVE0001" in vins


class TestSkodaPortalRouting:
    def test_get_vehicles_routes_through_portal(self):
        client = _skoda()
        portal = _portal(vins=["VINPORTAL03"])
        client._eu_portal = portal
        vins = asyncio.run(client.get_vehicles())
        assert vins == ["VINPORTAL03"]
        portal.list_vehicle_vins.assert_awaited_once()

    def test_get_status_routes_through_portal(self):
        client = _skoda()
        portal = _portal(vin="VINPORTAL04")
        client._eu_portal = portal
        data = asyncio.run(client.get_status("VINPORTAL04"))
        assert data.vin == "VINPORTAL04"
        portal.get_vehicle_data.assert_awaited_once_with("VINPORTAL04")
