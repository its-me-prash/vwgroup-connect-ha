# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.17.1 — Bruno Quick-Wins Bundle.

Six feature groups (all SEAT/CUPRA OLA additions from
``Timwun/Cupra-WeConnect-Bruno-Collection`` deep-dive):

A) ``_post_with_ab_fallback`` generic helper — primary URL on 404
   falls back to legacy URL with body action.
B) Window heating endpoint A/B fix — Bruno path first
   ``/vehicles/{vin}/windowheating/requests/{action}``, fallback to
   legacy ``/v2/vehicles/{vin}/climatisation`` body action.
C) Ventilation start/stop — new endpoint, no body, no fallback.
D) Aux heating start/stop with SecToken (start) — A/B URL fallback
   between Bruno-path and pycupra-path.
E) Battery Care GET endpoints + coordinator refresh + brand-restriction.
F) Capabilities path A/B fallback — try plural first, fall back to
   Bruno's singular path with userId.
G) Charging actions A/B fallback — try newer non-/v1 path first,
   fall back to legacy /v1/.../actions.
H) #36 Navigation — PUT /v1/users/vehicles/{vin}/destination with
   verbatim Bruno body shape (single-element JSON array).
I) Capability-Map entries for new commands.
J) _COMMAND_CLASS registrations.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) _post_with_ab_fallback generic helper
# ─────────────────────────────────────────────────────────────────────────────


def _client():
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
    client = SeatCupraClient.__new__(SeatCupraClient)
    client._post = AsyncMock(return_value=None)
    return client


class TestPostWithAbFallback:
    def test_primary_success_no_fallback(self):
        client = _client()
        asyncio.run(
            client._post_with_ab_fallback(
                primary_url="P", primary_json={"a": 1},
                fallback_url="F", fallback_json={"b": 2},
                label="test", vin="VINX",
            )
        )
        # Only one POST: the primary. No headers kwarg when no headers.
        assert client._post.await_count == 1
        client._post.assert_awaited_with("P", json={"a": 1})

    def test_404_falls_back_to_legacy(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = _client()
        client._post = AsyncMock(side_effect=[APIError(404, "P", ""), None])
        asyncio.run(
            client._post_with_ab_fallback(
                primary_url="P", primary_json=None,
                fallback_url="F", fallback_json={"action": "start"},
                label="test", vin="VINX",
            )
        )
        assert client._post.await_count == 2
        client._post.assert_any_await("P", json=None)
        client._post.assert_any_await("F", json={"action": "start"})

    def test_non_404_propagates(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = _client()
        client._post = AsyncMock(side_effect=APIError(403, "P", "spin_error"))
        with pytest.raises(APIError) as exc:
            asyncio.run(
                client._post_with_ab_fallback(
                    primary_url="P", primary_json={},
                    fallback_url="F", fallback_json={},
                    label="test", vin="VINX",
                )
            )
        assert exc.value.status == 403
        assert client._post.await_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# B) Window heating A/B fix
# ─────────────────────────────────────────────────────────────────────────────


class TestWindowHeatingAB:
    def test_start_uses_bruno_path_first(self):
        client = _client()
        asyncio.run(
            client.command_start_window_heating("VINX")
        )
        url = client._post.await_args.args[0]
        assert "/vehicles/VINX/windowheating/requests/start" in url

    def test_stop_uses_bruno_path_first(self):
        client = _client()
        asyncio.run(
            client.command_stop_window_heating("VINX")
        )
        url = client._post.await_args.args[0]
        assert "/vehicles/VINX/windowheating/requests/stop" in url


# ─────────────────────────────────────────────────────────────────────────────
# C) Ventilation
# ─────────────────────────────────────────────────────────────────────────────


class TestVentilation:
    def test_start_url(self):
        client = _client()
        asyncio.run(
            client.command_start_ventilation("VINX")
        )
        client._post.assert_awaited_once_with(
            "https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/VINX/ventilation/start",
            json={},
        )

    def test_stop_url(self):
        client = _client()
        asyncio.run(
            client.command_stop_ventilation("VINX")
        )
        client._post.assert_awaited_once_with(
            "https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/VINX/ventilation/stop",
            json={},
        )


# ─────────────────────────────────────────────────────────────────────────────
# D) Aux heating with SecToken + A/B fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestAuxHeating:
    def test_start_no_spin_raises(self):
        from custom_components.vag_connect.cariad.exceptions import SpinError
        client = _client()
        client._spin = ""
        with pytest.raises(SpinError):
            asyncio.run(
                client.command_start_aux_heating("VINX")
            )

    def test_start_uses_bruno_path_with_sectoken(self):
        client = _client()
        client._spin = "1234"
        client._get_sec_token = AsyncMock(return_value="SECTOK")
        asyncio.run(
            client.command_start_aux_heating("VINX")
        )
        # Primary call: Bruno URL with SecToken
        client._post.assert_awaited_once()
        call = client._post.await_args
        assert "/v1/vehicles/VINX/auxiliary-heating/start" in call.args[0]
        assert call.kwargs["headers"]["SecToken"] == "SECTOK"

    def test_start_404_falls_back_to_pycupra_path(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = _client()
        client._spin = "1234"
        client._get_sec_token = AsyncMock(return_value="SECTOK")
        client._post = AsyncMock(side_effect=[APIError(404, "P", ""), None])
        asyncio.run(
            client.command_start_aux_heating("VINX")
        )
        # Two calls: Bruno path, then pycupra path
        assert client._post.await_count == 2
        fallback_url = client._post.await_args_list[1].args[0]
        assert "/api/auxiliary-heating/v1/VINX/start" in fallback_url

    def test_stop_no_sectoken(self):
        client = _client()
        asyncio.run(
            client.command_stop_aux_heating("VINX")
        )
        # No SecToken header on stop (Bruno seq 30 confirmed)
        # Helper omits headers kwarg entirely when no headers needed.
        kwargs = client._post.await_args.kwargs
        assert "headers" not in kwargs


# ─────────────────────────────────────────────────────────────────────────────
# E) Battery Care GET + coordinator refresh
# ─────────────────────────────────────────────────────────────────────────────


class TestBatteryCare:
    def test_get_battery_care_404_returns_empty(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = _client()
        client._get = AsyncMock(side_effect=APIError(404, "U", ""))
        result = asyncio.run(
            client.get_battery_care("VINX")
        )
        assert result == {}

    def test_get_battery_care_returns_dict(self):
        client = _client()
        client._get = AsyncMock(return_value={"enabled": True})
        result = asyncio.run(
            client.get_battery_care("VINX")
        )
        assert result == {"enabled": True}

    def test_get_battery_care_target_returns_dict(self):
        client = _client()
        client._get = AsyncMock(return_value={"targetSocPercentage": 80})
        result = asyncio.run(
            client.get_battery_care_target("VINX")
        )
        assert result["targetSocPercentage"] == 80


class TestRefreshBatteryCareBrandRestriction:
    def _coord(self, brand="cupra"):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": brand}
        coord._vehicles_lock = threading.Lock()
        coord.vehicles = {"VINX": {"_dummy": True}}
        coord._cariad_client = MagicMock()
        coord._cariad_client.get_battery_care = AsyncMock(
            return_value={"enabled": True}
        )
        coord._cariad_client.get_battery_care_target = AsyncMock(
            return_value={"targetSocPercentage": 80}
        )
        coord.command_capability_supported = MagicMock(return_value=None)
        return coord

    def test_audi_brand_skips(self):
        coord = self._coord(brand="audi")
        asyncio.run(
            coord.refresh_battery_care("VINX")
        )
        coord._cariad_client.get_battery_care.assert_not_called()

    def test_cupra_brand_calls_and_merges(self):
        coord = self._coord(brand="cupra")
        asyncio.run(
            coord.refresh_battery_care("VINX")
        )
        v = coord.vehicles["VINX"]
        assert v["battery_care_enabled"] is True
        assert v["battery_care_target_soc_pct"] == 80


# ─────────────────────────────────────────────────────────────────────────────
# F) Capabilities path A/B fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestCapabilitiesAB:
    def test_plural_path_success_no_fallback(self):
        client = _client()
        client._get = AsyncMock(return_value={"capabilities": []})
        result = asyncio.run(
            client.get_capabilities("VINX")
        )
        assert result == {"capabilities": []}
        # Only one GET (plural primary)
        assert client._get.await_count == 1

    def test_plural_404_falls_back_to_singular(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = _client()
        client._user_id = "USER123"
        client._get = AsyncMock(side_effect=[
            APIError(404, "P", ""),  # plural fails
            {"capabilities": [{"id": "x"}]},  # singular succeeds
        ])
        result = asyncio.run(
            client.get_capabilities("VINX")
        )
        assert result == {"capabilities": [{"id": "x"}]}
        assert client._get.await_count == 2
        # Singular URL hit
        singular_call = client._get.await_args_list[1]
        assert "/v1/user/USER123/vehicle/VINX/capabilities" in singular_call.args[0]


# ─────────────────────────────────────────────────────────────────────────────
# G) Charging actions A/B fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestChargingActionsAB:
    def test_start_uses_newer_path_first(self):
        client = _client()
        asyncio.run(
            client.command_start_charging("VINX")
        )
        url = client._post.await_args.args[0]
        # Bruno's newer non-/v1 path
        assert url.endswith("/vehicles/VINX/charging/requests/start")
        assert "/v1/" not in url

    def test_stop_uses_newer_path_first(self):
        client = _client()
        asyncio.run(
            client.command_stop_charging("VINX")
        )
        url = client._post.await_args.args[0]
        assert url.endswith("/vehicles/VINX/charging/requests/stop")


# ─────────────────────────────────────────────────────────────────────────────
# H) #36 Navigation
# ─────────────────────────────────────────────────────────────────────────────


class TestSendDestination:
    def test_url_and_body_shape(self):
        client = _client()
        client._request = AsyncMock(return_value=None)
        asyncio.run(
            client.command_send_destination(
                "VINX",
                latitude=47.39,
                longitude=8.21,
                name="Office",
                city="Zurich",
                country="CH",
                state="ZH",
                street="Bahnhofstrasse",
                house_number="1",
                zip_code="8001",
            )
        )
        call = client._request.await_args
        # PUT method
        assert call.args[0] == "PUT"
        # URL pattern (Bruno-verified)
        assert "/v1/users/vehicles/VINX/destination" in call.args[1]
        # Body is a JSON ARRAY (single element)
        body = call.kwargs["json"]
        assert isinstance(body, list)
        assert len(body) == 1
        dest = body[0]
        assert dest["destinationName"] == "Office"
        assert dest["geoCoordinate"]["latitude"] == 47.39
        assert dest["geoCoordinate"]["longitude"] == 8.21
        assert dest["address"]["city"] == "Zurich"
        assert dest["address"]["zipCode"] == "8001"


# ─────────────────────────────────────────────────────────────────────────────
# I) Capability-Map entries for new commands
# ─────────────────────────────────────────────────────────────────────────────


class TestCapabilityMapV1171:
    @pytest.mark.parametrize("brand,command_id,expected", [
        ("cupra", "command_start_ventilation", "ventilation"),
        ("cupra", "command_stop_ventilation", "ventilation"),
        ("cupra", "command_start_aux_heating", "auxiliary-heating"),
        ("cupra", "command_stop_aux_heating", "auxiliary-heating"),
        ("cupra", "command_send_destination", "destination"),
        ("cupra", "command_battery_care_read", "charging"),
        # SEAT inherits via table alias
        ("seat", "command_start_aux_heating", "auxiliary-heating"),
        ("seat", "command_send_destination", "destination"),
    ])
    def test_cap_id_for(self, brand, command_id, expected):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for(brand, command_id) == expected

    def test_skoda_does_not_have_aux_heating(self):
        """Aux heating is not in skoda's capability table.

        v2.8.0 extended the integration to Audi + VW EU (Standheizung)
        so those brands now carry the ``auxiliaryHeating`` cap-id. Skoda
        still has no aux heating endpoint on mysmob, so the assertion
        for that brand stays None.
        """
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for("skoda", "command_start_aux_heating") is None
        # v2.8.0 - volkswagen + audi now carry the cap-id.
        assert cap_id_for("volkswagen", "command_start_aux_heating") == "auxiliaryHeating"
        assert cap_id_for("audi", "command_start_aux_heating") == "auxiliaryHeating"


# ─────────────────────────────────────────────────────────────────────────────
# J) _COMMAND_CLASS registrations
# ─────────────────────────────────────────────────────────────────────────────


class TestCommandClassRegistry:
    def test_ventilation_class(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        cmd = VagConnectCoordinator._COMMAND_CLASS
        assert cmd["command_start_ventilation"] == "ventilation"
        assert cmd["command_stop_ventilation"] == "ventilation"

    def test_aux_heating_class(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        cmd = VagConnectCoordinator._COMMAND_CLASS
        assert cmd["command_start_aux_heating"] == "aux_heating"
        assert cmd["command_stop_aux_heating"] == "aux_heating"

    def test_destination_class(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        cmd = VagConnectCoordinator._COMMAND_CLASS
        assert cmd["command_send_destination"] == "destination"
