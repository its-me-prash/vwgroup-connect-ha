# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v2.10.0 rich climate-control payload.

Coverage:

A) ``VWEUClient.command_start_climate_control`` builds the correct
   CARIAD-BFF body for each individual field.
B) An all-None call posts an empty body (omitted fields = brand
   defaults preserved by the backend).
C) Seat heating is treated as a group: any non-None seat triggers all
   four zone keys, with unspecified seats defaulting to False.
D) ``AudiClient`` inherits the rich command from ``VWEUClient``.
E) Coordinator ``async_start_climate_control`` routes Audi + VW EU
   to the rich payload via ``_cariad_cmd_optimistic``.
F) Other brands (skoda / seat / cupra / vw_na / porsche) fall through
   to the basic ``async_start_climatisation`` flow.
G) The base ``CariadBaseClient.command_start_climate_control`` stub
   raises ``NotImplementedError`` so non-CARIAD subclasses inherit a
   safe failure mode.
H) ``_COMMAND_CLASS`` maps the new method into the existing climate
   serialisation class.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# A) Body building per field
# ---------------------------------------------------------------------------


def _vw_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    client = VWEUClient.__new__(VWEUClient)
    # _base_for_vin reads this; empty dict -> default _BASE.
    client._vehicle_bases = {}
    return client


class TestRichClimateBody:
    def _run(self, **kwargs):
        client = _vw_client()
        client._post = AsyncMock(return_value=None)
        asyncio.run(
            client.command_start_climate_control("VINX", **kwargs)
        )
        call = client._post.await_args
        assert call is not None, "expected _post to be awaited"
        return call

    def test_temp_c_only(self):
        call = self._run(temp_c=21.5)
        url = call.args[0]
        body = call.kwargs["json"]
        assert url.endswith("/vehicle/v1/vehicles/VINX/climatisation/start")
        assert body == {"targetTemperatureInCelsius": 21.5}

    def test_glass_heating_only(self):
        call = self._run(glass_heating=True)
        assert call.kwargs["json"] == {"windowHeatingEnabled": True}

    def test_climatisation_at_unlock_only(self):
        call = self._run(climatisation_at_unlock=True)
        assert call.kwargs["json"] == {"climatisationAtUnlock": True}

    def test_climatisation_mode_only(self):
        call = self._run(climatisation_mode="economy")
        assert call.kwargs["json"] == {"climatisationMode": "economy"}

    def test_full_payload(self):
        call = self._run(
            temp_c=22.0,
            glass_heating=True,
            seat_fl=True,
            seat_fr=True,
            seat_rl=False,
            seat_rr=False,
            climatisation_at_unlock=False,
            climatisation_mode="comfort",
        )
        body = call.kwargs["json"]
        assert body == {
            "targetTemperatureInCelsius": 22.0,
            "windowHeatingEnabled": True,
            "zoneFrontLeftEnabled": True,
            "zoneFrontRightEnabled": True,
            "zoneRearLeftEnabled": False,
            "zoneRearRightEnabled": False,
            "climatisationAtUnlock": False,
            "climatisationMode": "comfort",
        }


# ---------------------------------------------------------------------------
# B) Empty body when nothing supplied
# ---------------------------------------------------------------------------


class TestEmptyBody:
    def test_no_kwargs_emits_empty_dict(self):
        client = _vw_client()
        client._post = AsyncMock(return_value=None)
        asyncio.run(
            client.command_start_climate_control("VINX")
        )
        call = client._post.await_args
        assert call.kwargs["json"] == {}


# ---------------------------------------------------------------------------
# C) Seat heating as a group
# ---------------------------------------------------------------------------


class TestSeatGrouping:
    def test_single_seat_triggers_all_four_zones(self):
        client = _vw_client()
        client._post = AsyncMock(return_value=None)
        asyncio.run(
            client.command_start_climate_control("VINX", seat_fl=True)
        )
        body = client._post.await_args.kwargs["json"]
        assert body == {
            "zoneFrontLeftEnabled": True,
            "zoneFrontRightEnabled": False,
            "zoneRearLeftEnabled": False,
            "zoneRearRightEnabled": False,
        }

    def test_all_seats_explicit_false(self):
        client = _vw_client()
        client._post = AsyncMock(return_value=None)
        asyncio.run(
            client.command_start_climate_control(
                "VINX",
                seat_fl=False,
                seat_fr=False,
                seat_rl=False,
                seat_rr=False,
            )
        )
        body = client._post.await_args.kwargs["json"]
        # ``False`` is non-None, so the group fires with all-False zones.
        assert body == {
            "zoneFrontLeftEnabled": False,
            "zoneFrontRightEnabled": False,
            "zoneRearLeftEnabled": False,
            "zoneRearRightEnabled": False,
        }

    def test_no_seat_args_emits_no_zone_keys(self):
        client = _vw_client()
        client._post = AsyncMock(return_value=None)
        asyncio.run(
            client.command_start_climate_control("VINX", temp_c=20.0)
        )
        body = client._post.await_args.kwargs["json"]
        assert "zoneFrontLeftEnabled" not in body
        assert "zoneFrontRightEnabled" not in body
        assert "zoneRearLeftEnabled" not in body
        assert "zoneRearRightEnabled" not in body
        assert body == {"targetTemperatureInCelsius": 20.0}


# ---------------------------------------------------------------------------
# D) Audi inheritance
# ---------------------------------------------------------------------------


class TestAudiInheritance:
    def test_audi_inherits_method(self):
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        assert hasattr(AudiClient, "command_start_climate_control")

    def test_audi_inherits_from_vweu(self):
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        assert issubclass(AudiClient, VWEUClient)
        # Inherited identity: same function object.
        assert (
            AudiClient.command_start_climate_control
            is VWEUClient.command_start_climate_control
        )


# ---------------------------------------------------------------------------
# G) Base stub raises NotImplementedError
# ---------------------------------------------------------------------------


class TestBaseStub:
    def test_base_raises(self):
        from custom_components.vag_connect.cariad.api.base import (
            CariadBaseClient,
        )
        client = CariadBaseClient.__new__(CariadBaseClient)
        with pytest.raises(NotImplementedError):
            asyncio.run(
                client.command_start_climate_control("VINX")
            )


# ---------------------------------------------------------------------------
# E+F) Coordinator routing per brand
# ---------------------------------------------------------------------------


def _coord(brand: str):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": brand}
    coord.entry.options = {}
    coord._cariad_client = MagicMock()
    # Used by the rich path (Audi + VW).
    coord._cariad_cmd_optimistic = AsyncMock(return_value=None)
    coord._vehicles_lock = threading.Lock()
    coord.vehicles = {"VINX": {}}
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock(return_value=None)
    # Used by the fallback (other brands) - the rich call should route
    # through ``async_start_climatisation`` which we mock out here so the
    # test never reaches the live optimistic helper a second time.
    coord.async_start_climatisation = AsyncMock(return_value=None)
    return coord


class TestCoordinatorBrandRouting:
    @pytest.mark.parametrize("brand", ["audi", "volkswagen"])
    def test_cariad_brands_use_rich_path(self, brand):
        coord = _coord(brand)
        asyncio.run(
            coord.async_start_climate_control(
                "VINX",
                temp_c=21.0,
                seat_fl=True,
                climatisation_mode="comfort",
            )
        )
        coord._cariad_cmd_optimistic.assert_awaited_once()
        # async_start_climatisation must NOT be invoked on the rich
        # path - the coordinator goes straight to the rich command.
        coord.async_start_climatisation.assert_not_called()
        call = coord._cariad_cmd_optimistic.await_args
        assert call.args[0] == "VINX"
        assert call.args[1] == "command_start_climate_control"
        # Optimistic state hits the climatisation sensors immediately
        # (mirrors the basic-start optimistic shape).
        assert call.kwargs["optimistic"] == {
            "climatisation_state": "VENTILATION",
            "climatisation_active": True,
        }
        # Forwarded payload kwargs land on the client call.
        assert call.kwargs["temp_c"] == 21.0
        assert call.kwargs["seat_fl"] is True
        assert call.kwargs["climatisation_mode"] == "comfort"
        # Unspecified kwargs are forwarded as None.
        assert call.kwargs["glass_heating"] is None
        assert call.kwargs["seat_fr"] is None
        assert call.kwargs["seat_rl"] is None
        assert call.kwargs["seat_rr"] is None
        assert call.kwargs["climatisation_at_unlock"] is None

    @pytest.mark.parametrize(
        "brand", ["skoda", "seat", "cupra", "volkswagen_na", "porsche"]
    )
    def test_other_brands_fall_through_to_basic_start(self, brand):
        coord = _coord(brand)
        asyncio.run(
            coord.async_start_climate_control(
                "VINX",
                temp_c=21.0,
                seat_fl=True,
                climatisation_mode="economy",
            )
        )
        # Rich payload silently dropped: coordinator routes to the
        # basic start_climatisation handler which the OLA / mysmob / PPA
        # backends actually understand.
        coord.async_start_climatisation.assert_awaited_once_with("VINX")
        coord._cariad_cmd_optimistic.assert_not_called()

    def test_no_cariad_client_is_noop(self):
        coord = _coord("audi")
        coord._cariad_client = None
        asyncio.run(
            coord.async_start_climate_control("VINX", temp_c=21.0)
        )
        coord._cariad_cmd_optimistic.assert_not_called()
        coord.async_start_climatisation.assert_not_called()


# ---------------------------------------------------------------------------
# H) Command-class serialisation registration
# ---------------------------------------------------------------------------


class TestCommandClassMap:
    def test_rich_climate_in_climate_class(self):
        from custom_components.vag_connect.coordinator import (
            VagConnectCoordinator,
        )
        assert (
            VagConnectCoordinator._COMMAND_CLASS.get(
                "command_start_climate_control"
            )
            == "climate"
        )
