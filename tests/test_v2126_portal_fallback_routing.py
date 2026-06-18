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
import pytest

from custom_components.vag_connect.cariad.exceptions import APIError
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


class TestSeatCupraRuntimeArming:
    """v2.12.7 — when the OLA login SUCCEEDS but the data backend is blocked
    (403, VW's device-attestation wall), the login-time portal fallback never
    fires (only login failures trigger it). get_vehicles must arm the portal
    on the native 403 so the entry recovers via the read-only portal instead
    of going dark with "no vehicles"."""

    def test_get_vehicles_arms_portal_on_ola_403(self):
        client = _seatcupra("cupra")
        client._user_id = "uid-123"
        client._get = AsyncMock(
            side_effect=APIError(403, "https://ola.prod.code.seat.cloud.vwgroup.com/garage")
        )
        portal = _portal(vins=["VINPORTAL09"])

        async def _arm():
            client._eu_portal = portal

        client._arm_eu_portal = AsyncMock(side_effect=_arm)
        vins = asyncio.run(client.get_vehicles())
        assert vins == ["VINPORTAL09"]
        client._arm_eu_portal.assert_awaited_once()

    def test_get_vehicles_non_403_does_not_arm(self):
        client = _seatcupra("seat")
        client._user_id = "uid-123"
        client._get = AsyncMock(
            side_effect=APIError(500, "https://ola.prod.code.seat.cloud.vwgroup.com/garage")
        )
        client._arm_eu_portal = AsyncMock()
        with pytest.raises(APIError):
            asyncio.run(client.get_vehicles())
        client._arm_eu_portal.assert_not_awaited()


class TestCapabilitiesPortalSkip:
    """v2.12.7 — refresh_capabilities skips the BFF capabilities call in EU
    Data Act portal mode (the sentinel token always 400s there), gated on the
    portal STRATEGY specifically so a user-toggled read-only native session
    (which still has a real token) keeps fetching."""

    def _coord(self, strategy):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord._cariad_client = MagicMock()
        coord._cariad_client._tokens = MagicMock(strategy=strategy)
        coord._cariad_client.get_capabilities = AsyncMock(return_value={"x": 1})
        coord.vehicle_capabilities = {}
        coord._capabilities_fetched_at = {}
        return coord

    def test_data_act_portal_skips_capabilities(self):
        coord = self._coord("data_act_portal")
        asyncio.run(coord.refresh_capabilities("VIN1", force=True))
        coord._cariad_client.get_capabilities.assert_not_awaited()

    def test_device_grant_portal_skips_capabilities(self):
        coord = self._coord("device_grant_portal")
        asyncio.run(coord.refresh_capabilities("VIN1", force=True))
        coord._cariad_client.get_capabilities.assert_not_awaited()

    def test_native_strategy_still_fetches_capabilities(self):
        coord = self._coord("classic")
        asyncio.run(coord.refresh_capabilities("VIN1", force=True))
        coord._cariad_client.get_capabilities.assert_awaited_once_with("VIN1")
