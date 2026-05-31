# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
"""Tests for v2.8.0 Auxiliary Heating (Standheizung) entities.

Audi + VW EU CARIAD-BFF parking-pre-heater wiring. SEAT/CUPRA OLA
support (v1.17.1, Bruno seq 29/30) stays unchanged - its tests live in
``test_v1171_bruno_quick_wins.py``.

Coverage:

A) ``VWEUClient._parse_status`` reads the ``auxiliaryHeating`` job.
B) ``command_start_aux_heating`` builds the right URL + Kelvin payload.
C) ``command_stop_aux_heating`` posts the stop payload.
D) Coordinator ``async_start_aux_heating`` reads duration + target_c
   from entry.options when the caller does not pass them, and falls
   back to defaults (30 min, 21 C) when the options key is missing.
E) Coordinator does NOT require S-PIN on the Audi + VW EU path.
F) Number-entity range validation matches the spec (5-60 min duration,
   16-30 C target temp).
G) Switch ``is_on`` honours both the derived ``aux_heating_active``
   bool and the raw ``auxiliary_heating_status`` string fallback.
H) Capability map exposes the cap-id for volkswagen + audi but not
   for skoda / vw_na / porsche.
I) Brand does-not-match path: a Skoda VIN never gets the new VW/Audi
   number sliders, and the SEAT/CUPRA S-PIN gate still fires.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# A) Parser: ``auxiliaryHeating`` job populates VehicleData fields
# ---------------------------------------------------------------------------


def _vw_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    client = VWEUClient.__new__(VWEUClient)
    # _parse_status accesses _vehicle_metadata.
    client._vehicle_metadata = {}
    return client


class TestParseAuxHeating:
    def test_heating_on_sets_active_true(self):
        client = _vw_client()
        raw = {
            "auxiliaryHeating": {
                "auxiliaryHeatingStatus": {
                    "value": {
                        "operationMode": "heating",
                        "remainingTime_min": 18,
                    },
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.auxiliary_heating_status == "heating"
        assert data.aux_heating_active is True
        assert data.auxiliary_heating_remaining_min == 18

    def test_off_sets_active_false(self):
        client = _vw_client()
        raw = {
            "auxiliaryHeating": {
                "auxiliaryHeatingStatus": {
                    "value": {"operationMode": "off"},
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.auxiliary_heating_status == "off"
        assert data.aux_heating_active is False
        assert data.auxiliary_heating_remaining_min is None

    def test_climatisation_state_fallback(self):
        """Older Audi firmware ships ``climatisationState`` instead of
        ``operationMode`` - parser falls through cleanly."""
        client = _vw_client()
        raw = {
            "auxiliaryHeating": {
                "auxiliaryHeatingStatus": {
                    "value": {"climatisationState": "heatingOn"},
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.auxiliary_heating_status == "heatingOn"
        assert data.aux_heating_active is True

    def test_missing_branch_leaves_fields_none(self):
        client = _vw_client()
        data = client._parse_status("VINX", raw={}, parking={})
        assert data.auxiliary_heating_status is None
        assert data.aux_heating_active is None
        assert data.auxiliary_heating_remaining_min is None


# ---------------------------------------------------------------------------
# B+C) Cariad client start / stop commands
# ---------------------------------------------------------------------------


class TestCariadCommands:
    def test_start_default_payload(self):
        client = _vw_client()
        client._post_command = AsyncMock(return_value=None)
        asyncio.new_event_loop().run_until_complete(
            client.command_start_aux_heating("VINX")
        )
        client._post_command.assert_awaited_once()
        call = client._post_command.await_args
        assert call.args[0] == "VINX"
        assert call.args[1] == "auxiliary-heating/start"
        body = call.kwargs["json"]
        assert body["command"] == "start"
        # Defaults: 30 minutes, 21 C -> 294.15 K.
        assert body["duration_in_min"] == 30
        assert abs(body["target_temperature_in_kelvin"] - 294.15) < 0.001

    def test_start_custom_duration_and_temp(self):
        client = _vw_client()
        client._post_command = AsyncMock(return_value=None)
        asyncio.new_event_loop().run_until_complete(
            client.command_start_aux_heating(
                "VINX", duration_min=45, target_c=22.5,
            )
        )
        body = client._post_command.await_args.kwargs["json"]
        assert body["duration_in_min"] == 45
        # 22.5 C -> 295.65 K
        assert abs(body["target_temperature_in_kelvin"] - 295.65) < 0.001

    def test_stop_payload(self):
        client = _vw_client()
        client._post_command = AsyncMock(return_value=None)
        asyncio.new_event_loop().run_until_complete(
            client.command_stop_aux_heating("VINX")
        )
        call = client._post_command.await_args
        assert call.args[0] == "VINX"
        assert call.args[1] == "auxiliary-heating/stop"
        assert call.kwargs["json"] == {"command": "stop"}

    def test_audi_inherits_via_subclass(self):
        """``AudiClient`` inherits from ``VWEUClient`` so the new
        commands are available on Audi without a separate override."""
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        assert hasattr(AudiClient, "command_start_aux_heating")
        assert hasattr(AudiClient, "command_stop_aux_heating")


# ---------------------------------------------------------------------------
# D+E) Coordinator wiring: options lookup, no S-PIN gate for VW/Audi
# ---------------------------------------------------------------------------


def _coord(brand: str = "volkswagen", options: dict | None = None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": brand}
    coord.entry.options = options or {}
    coord._vehicles_lock = threading.Lock()
    coord.vehicles = {"VINX": {}}
    coord._cariad_cmd = AsyncMock(return_value=None)
    coord._spin_from_entry = MagicMock(return_value="")
    return coord


class TestCoordinatorAuxHeatingStart:
    def test_volkswagen_default_options(self):
        coord = _coord("volkswagen")
        asyncio.new_event_loop().run_until_complete(
            coord.async_start_aux_heating("VINX")
        )
        coord._cariad_cmd.assert_awaited_once_with(
            "VINX",
            "command_start_aux_heating",
            duration_min=30,
            target_c=21.0,
        )

    def test_audi_reads_options(self):
        coord = _coord(
            "audi",
            options={"auxheat_duration": 45, "auxheat_target_temp": 22.5},
        )
        asyncio.new_event_loop().run_until_complete(
            coord.async_start_aux_heating("VINX")
        )
        coord._cariad_cmd.assert_awaited_once_with(
            "VINX",
            "command_start_aux_heating",
            duration_min=45,
            target_c=22.5,
        )

    def test_caller_kwargs_win_over_options(self):
        coord = _coord(
            "volkswagen",
            options={"auxheat_duration": 5, "auxheat_target_temp": 17.0},
        )
        asyncio.new_event_loop().run_until_complete(
            coord.async_start_aux_heating(
                "VINX", duration_min=20, target_c=24.0,
            )
        )
        coord._cariad_cmd.assert_awaited_once_with(
            "VINX",
            "command_start_aux_heating",
            duration_min=20,
            target_c=24.0,
        )

    def test_volkswagen_does_not_require_spin(self):
        """Audi + VW EU surface does not gate on S-PIN. The S-PIN
        ServiceValidationError still fires on SEAT/CUPRA - see
        ``test_seat_requires_spin`` below.
        """
        from homeassistant.exceptions import ServiceValidationError  # noqa: PLC0415
        coord = _coord("volkswagen")
        coord._spin_from_entry = MagicMock(return_value="")
        # Must not raise.
        asyncio.new_event_loop().run_until_complete(
            coord.async_start_aux_heating("VINX")
        )
        coord._cariad_cmd.assert_awaited_once()
        # Sanity: switching the brand back to seat with no S-PIN raises.
        coord.entry.data = {"brand": "seat"}
        with pytest.raises(ServiceValidationError):
            asyncio.new_event_loop().run_until_complete(
                coord.async_start_aux_heating("VINX")
            )

    def test_seat_requires_spin(self):
        from homeassistant.exceptions import ServiceValidationError  # noqa: PLC0415
        coord = _coord("cupra")
        with pytest.raises(ServiceValidationError):
            asyncio.new_event_loop().run_until_complete(
                coord.async_start_aux_heating("VINX")
            )


# ---------------------------------------------------------------------------
# F) Number entity range validation
# ---------------------------------------------------------------------------


class TestNumberEntityRanges:
    def test_auxheat_duration_range(self):
        from custom_components.vag_connect.number import NUMBER_DESCRIPTIONS
        desc = next(d for d in NUMBER_DESCRIPTIONS if d.key == "auxheat_duration")
        assert desc.native_min_value == 5
        assert desc.native_max_value == 60
        assert desc.native_step == 5
        assert desc.condition == "auxheat"

    def test_auxheat_target_temp_range(self):
        from custom_components.vag_connect.number import NUMBER_DESCRIPTIONS
        desc = next(d for d in NUMBER_DESCRIPTIONS if d.key == "auxheat_target_temp")
        assert desc.native_min_value == 16
        assert desc.native_max_value == 30
        assert desc.native_step == 0.5
        assert desc.condition == "auxheat"


# ---------------------------------------------------------------------------
# G) Switch ``is_on`` semantics
# ---------------------------------------------------------------------------


def _switch(vehicle: dict):
    from custom_components.vag_connect.switch import VagAuxHeatingSwitch
    sw = VagAuxHeatingSwitch.__new__(VagAuxHeatingSwitch)
    sw._vin = "VINX"
    sw._key = "aux_heating_switch"
    sw.coordinator = MagicMock()
    sw.coordinator.data = {"VINX": vehicle}
    return sw


class TestSwitchIsOn:
    def test_active_true_when_bool_true(self):
        sw = _switch({"aux_heating_active": True})
        assert sw.is_on is True

    def test_active_false_when_bool_false(self):
        sw = _switch({"aux_heating_active": False})
        assert sw.is_on is False

    def test_falls_back_to_status_string(self):
        sw = _switch({"auxiliary_heating_status": "heating"})
        assert sw.is_on is True

    def test_off_status_string_is_false(self):
        sw = _switch({"auxiliary_heating_status": "off"})
        assert sw.is_on is False

    def test_unknown_when_no_data(self):
        sw = _switch({})
        assert sw.is_on is None


# ---------------------------------------------------------------------------
# H) Capability map
# ---------------------------------------------------------------------------


class TestCapabilityMap:
    @pytest.mark.parametrize("brand", ["volkswagen", "audi"])
    def test_supported_brands(self, brand):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for(brand, "command_start_aux_heating") == "auxiliaryHeating"
        assert cap_id_for(brand, "command_stop_aux_heating") == "auxiliaryHeating"

    @pytest.mark.parametrize("brand", ["skoda", "volkswagen_na", "porsche"])
    def test_unsupported_brands(self, brand):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for(brand, "command_start_aux_heating") is None


# ---------------------------------------------------------------------------
# I) Graceful brand-mismatch fallback for the SEAT/CUPRA kwargs path
# ---------------------------------------------------------------------------


class TestSeatCupraIgnoresKwargs:
    def test_seat_cupra_drops_kwargs(self):
        """The SEAT/CUPRA OLA endpoint takes no body, so the v2.8.0
        ``duration_min`` / ``target_c`` kwargs must be silently dropped
        instead of breaking the existing flow."""
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        client = SeatCupraClient.__new__(SeatCupraClient)
        client._spin = "1234"
        client._get_sec_token = AsyncMock(return_value="SECTOK")
        client._post_with_ab_fallback = AsyncMock(return_value=None)
        # Should not raise even with kwargs the coordinator might send
        # in a mixed-brand multi-account install.
        asyncio.new_event_loop().run_until_complete(
            client.command_start_aux_heating(
                "VINX", duration_min=45, target_c=22.5,
            )
        )
        client._post_with_ab_fallback.assert_awaited_once()
