# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche `mf` measurement wiring — b23 (competitor-triage ADOPT #1).

``porsche.py`` already REQUESTS the full mf set (windows, spoiler, charge
flaps, service flap, parking brake/light, oil level, service-time intervals)
but the parser mapped NONE of them onto VehicleData. These tests pin the new
wiring against the REAL inner-value shapes.

Shapes are grounded on a real Taycan mf capture (a public CJNE
ha-porscheconnect issue paste, corroborated across every measurement and
matching CJNE's own parsing): the open-state family is ``{"isOpen": bool}``
(an earlier revision guessed an ``openState`` STRING from the androguard enum
NAMES — the enum dump gives the keys, not the value field names), parking
brake/light are ``{"isOn": bool}``, and service-time is ``{"days": int}``.
Only OIL_LEVEL_CURRENT was disabled on that capture, so its inner shape stays
unverified behind a defensive numeric reader — exercised here for both the
plausible shapes and the garbage-in → None path.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.porsche import PorscheClient

_VIN = "WP0ZZZ99ZTS300001"


def _client() -> PorscheClient:
    return PorscheClient.__new__(PorscheClient)


async def _status(measurements: list[dict]) -> object:
    c = _client()
    c._get = AsyncMock(return_value={"measurements": measurements})
    return await c.get_status(_VIN)


# ── OPEN_STATE_* family — real shape {"isOpen": bool} ─────────────────────────
class TestWindows:
    @pytest.mark.asyncio
    async def test_individual_and_aggregate(self) -> None:
        d = await _status([
            {"key": "OPEN_STATE_WINDOW_FRONT_LEFT", "value": {"isOpen": True}},
            {"key": "OPEN_STATE_WINDOW_FRONT_RIGHT", "value": {"isOpen": False}},
            {"key": "OPEN_STATE_WINDOW_REAR_LEFT", "value": {"isOpen": False}},
            {"key": "OPEN_STATE_WINDOW_REAR_RIGHT", "value": {"isOpen": False}},
        ])
        # Stored convention (mirrors doors_individual): True == closed.
        assert d.windows_individual == {
            "frontLeft": False,
            "frontRight": True,
            "rearLeft": True,
            "rearRight": True,
        }
        assert d.windows_open is True

    @pytest.mark.asyncio
    async def test_all_closed_aggregate_false(self) -> None:
        d = await _status([
            {"key": f"OPEN_STATE_WINDOW_{p}", "value": {"isOpen": False}}
            for p in ("FRONT_LEFT", "FRONT_RIGHT", "REAR_LEFT", "REAR_RIGHT")
        ])
        assert d.windows_open is False
        assert all(v is True for v in d.windows_individual.values())

    @pytest.mark.asyncio
    async def test_partial_only_present_keys_stored(self) -> None:
        d = await _status([
            {"key": "OPEN_STATE_WINDOW_FRONT_LEFT", "value": {"isOpen": True}},
        ])
        assert d.windows_individual == {"frontLeft": False}
        assert d.windows_open is True

    @pytest.mark.asyncio
    async def test_missing_leaves_default_empty(self) -> None:
        d = await _status([])
        assert d.windows_individual == {}
        assert d.windows_open is None


class TestSpoilerAndServiceHatch:
    @pytest.mark.asyncio
    async def test_spoiler_open(self) -> None:
        d = await _status([{"key": "OPEN_STATE_SPOILER", "value": {"isOpen": True}}])
        assert d.spoiler_open is True

    @pytest.mark.asyncio
    async def test_spoiler_closed(self) -> None:
        d = await _status([{"key": "OPEN_STATE_SPOILER", "value": {"isOpen": False}}])
        assert d.spoiler_open is False

    @pytest.mark.asyncio
    async def test_service_hatch_open(self) -> None:
        d = await _status([{"key": "OPEN_STATE_SERVICE_FLAP", "value": {"isOpen": True}}])
        assert d.service_hatch_open is True

    @pytest.mark.asyncio
    async def test_missing_stay_none(self) -> None:
        d = await _status([])
        assert d.spoiler_open is None
        assert d.service_hatch_open is None


class TestChargeFlaps:
    @pytest.mark.asyncio
    async def test_left_maps_plug1_right_maps_plug2(self) -> None:
        d = await _status([
            {"key": "OPEN_STATE_CHARGE_FLAP_LEFT", "value": {"isOpen": True}},
            {"key": "OPEN_STATE_CHARGE_FLAP_RIGHT", "value": {"isOpen": False}},
        ])
        assert d.charging_plug1_flap_state == "OPEN"
        assert d.charging_plug2_flap_state == "CLOSED"

    @pytest.mark.asyncio
    async def test_single_port_leaves_plug2_none(self) -> None:
        d = await _status([
            {"key": "OPEN_STATE_CHARGE_FLAP_LEFT", "value": {"isOpen": False}},
        ])
        assert d.charging_plug1_flap_state == "CLOSED"
        assert d.charging_plug2_flap_state is None


# ── Parking brake / light — real shape {"isOn": bool} ─────────────────────────
class TestParkingBrake:
    @pytest.mark.asyncio
    async def test_engaged(self) -> None:
        d = await _status([{"key": "PARKING_BRAKE", "value": {"isOn": True}}])
        assert d.parking_brake_engaged is True

    @pytest.mark.asyncio
    async def test_released(self) -> None:
        d = await _status([{"key": "PARKING_BRAKE", "value": {"isOn": False}}])
        assert d.parking_brake_engaged is False

    @pytest.mark.asyncio
    async def test_unknown_shape_fails_soft(self) -> None:
        d = await _status([{"key": "PARKING_BRAKE", "value": {"state": "WHO_KNOWS"}}])
        assert d.parking_brake_engaged is None


class TestParkingLight:
    @pytest.mark.asyncio
    async def test_on(self) -> None:
        d = await _status([{"key": "PARKING_LIGHT", "value": {"isOn": True}}])
        assert d.parking_light is True

    @pytest.mark.asyncio
    async def test_off(self) -> None:
        d = await _status([{"key": "PARKING_LIGHT", "value": {"isOn": False}}])
        assert d.parking_light is False


# ── Oil level (inner shape NOT live-verified — defensive reader) ──────────────
class TestOilLevel:
    @pytest.mark.asyncio
    async def test_direct_percent(self) -> None:
        d = await _status([{"key": "OIL_LEVEL_CURRENT", "value": {"percent": 80}}])
        assert d.oil_level_pct == 80

    @pytest.mark.asyncio
    async def test_ratio_0_1_scaled(self) -> None:
        d = await _status([{"key": "OIL_LEVEL_CURRENT", "value": {"value": 0.8}}])
        assert d.oil_level_pct == 80

    @pytest.mark.asyncio
    async def test_absolute_normalised_against_max(self) -> None:
        d = await _status([
            {"key": "OIL_LEVEL_CURRENT", "value": {"currentValue": 6.0}},
            {"key": "OIL_LEVEL_MAX", "value": {"currentValue": 8.0}},
        ])
        assert d.oil_level_pct == 75

    @pytest.mark.asyncio
    async def test_out_of_range_fails_soft(self) -> None:
        d = await _status([{"key": "OIL_LEVEL_CURRENT", "value": {"percent": 150}}])
        assert d.oil_level_pct is None

    @pytest.mark.asyncio
    async def test_garbage_fails_soft(self) -> None:
        d = await _status([{"key": "OIL_LEVEL_CURRENT", "value": {"percent": "n/a"}}])
        assert d.oil_level_pct is None


# ── Service-time intervals — real shape {"days": int} ─────────────────────────
class TestServiceTime:
    @pytest.mark.asyncio
    async def test_main_service_days(self) -> None:
        # 726 is the exact value from the grounding capture.
        d = await _status([{"key": "MAIN_SERVICE_TIME", "value": {"days": 726}}])
        assert d.service_due_in_days == 726

    @pytest.mark.asyncio
    async def test_oil_service_days(self) -> None:
        d = await _status([{"key": "OIL_SERVICE_TIME", "value": {"days": 300}}])
        assert d.oil_service_due_in_days == 300

    @pytest.mark.asyncio
    async def test_overdue_negative_allowed(self) -> None:
        d = await _status([{"key": "MAIN_SERVICE_TIME", "value": {"days": -14}}])
        assert d.service_due_in_days == -14

    @pytest.mark.asyncio
    async def test_implausible_value_rejected(self) -> None:
        # A Unix timestamp slipping into a day field — reject, don't ship nonsense.
        d = await _status([{"key": "MAIN_SERVICE_TIME", "value": {"days": 1_700_000_000}}])
        assert d.service_due_in_days is None


# ── Global fail-soft: garbage shapes never crash a poll ───────────────────────
class TestFailSoft:
    @pytest.mark.asyncio
    async def test_non_dict_values_do_not_crash(self) -> None:
        d = await _status([
            {"key": "OPEN_STATE_WINDOW_FRONT_LEFT", "value": "isOpen"},
            {"key": "OPEN_STATE_SPOILER", "value": []},
            {"key": "PARKING_BRAKE", "value": None},
            {"key": "OIL_LEVEL_CURRENT", "value": 42},
            {"key": "MAIN_SERVICE_TIME", "value": "soon"},
        ])
        assert d.windows_individual == {}
        assert d.spoiler_open is None
        assert d.parking_brake_engaged is None
        # bare-number oil value is still tolerated (0..100 → percent)
        assert d.oil_level_pct == 42
        assert d.service_due_in_days is None

    @pytest.mark.asyncio
    async def test_all_new_fields_default_none_when_absent(self) -> None:
        d = await _status([])
        assert d.spoiler_open is None
        assert d.service_hatch_open is None
        assert d.charging_plug1_flap_state is None
        assert d.charging_plug2_flap_state is None
        assert d.parking_brake_engaged is None
        assert d.parking_light is None
        assert d.oil_level_pct is None
        assert d.service_due_in_days is None
        assert d.oil_service_due_in_days is None
