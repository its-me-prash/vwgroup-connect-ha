# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche departure timers, climate state, AC charging limit, charging reason,
hibernation mode and plain status reads.

Shapes from My Porsche 21.26.46:

- ``DEPARTURES.value`` is ``{lastModified?, list?}`` with entries
  ``{id, isEnabled, triggerDateTimeWithOffset, repeatOn?, chargingOption,
  preferredChargingTimes?, circle?, isClimatizationEnabled}``;
  ``triggerDateTimeWithOffset`` is an ISO 8601 string with an offset.
- ``DEPARTURES_EDIT`` takes ``{spin?, list?}`` with the same entries.
  ``TIMERS_DISABLE`` takes a list of a different model (``TIMERS``), so it is
  not the way to switch a departure off.
- ``HVAC_SUMMARY.value`` is ``{type, status, targetTemperature? (Kelvin), ...}``
  with ``status`` one of OFF, ON, HEATING, COOLING, VENTILATING, HOLDING,
  HEATING_HOLD, COOLING_HOLD, VENTILATING_HOLD, ERROR.
- ``CHARGING_SETTINGS.value.acChargingCurrentLimitA`` is the AC limit;
  ``CHARGING_SETTINGS_AC_CURRENT_LIMIT_EDIT`` takes
  ``{spin?, acChargingCurrentLimitA}``.
- ``CHARGING_SUMMARY.value.reason`` is ``{error?, warning?, pause?}``.
- ``HIBERNATION_MODE.value`` is ``{lastModified?, isEnabled}``.
- The app's plain status read sends no ``wakeUpJob``; only its refresh does.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api import porsche as porsche_mod
from custom_components.vag_connect.cariad.api.porsche import PorscheClient
from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

_VIN = "WP0ZZZ99ZTS300001"


def _client() -> PorscheClient:
    return PorscheClient.__new__(PorscheClient)


async def _status(measurements: list[dict]) -> object:
    c = _client()
    c._get = AsyncMock(return_value={"measurements": measurements})
    return await c.get_status(_VIN)


def _m(key: str, value: dict | None, enabled: bool = True) -> dict:
    item: dict = {"key": key, "status": {"isEnabled": enabled}}
    if value is not None:
        item["value"] = value
    return item


def _departure(dep_id: int, enabled: bool, when: str) -> dict:
    return {
        "id": dep_id,
        "isEnabled": enabled,
        "triggerDateTimeWithOffset": when,
        "repeatOn": ["MONDAY", "FRIDAY"],
        "chargingOption": {"type": "ENABLED"},
        "isClimatizationEnabled": True,
    }


def _departures_client(entries: list[dict]) -> PorscheClient:
    c = _client()
    c._get = AsyncMock(return_value={"measurements": [
        _m("DEPARTURES", {"list": entries}),
    ]})
    c._command = AsyncMock()
    return c


class TestDepartureTimer:
    @pytest.mark.asyncio
    async def test_enable_sends_the_whole_list_with_one_entry_changed(self) -> None:
        entries = [
            _departure(1, False, "2026-11-19T07:30:00+01:00"),
            _departure(2, True, "2026-11-20T06:00:00+01:00"),
        ]
        c = _departures_client(entries)
        await c.command_set_departure_timer(_VIN, 1, True, None)
        c._command.assert_awaited_once()
        vin, key, payload = c._command.await_args.args
        assert (vin, key) == (_VIN, "DEPARTURES_EDIT")
        assert payload["spin"] is None
        sent = payload["list"]
        assert [e["id"] for e in sent] == [1, 2]
        assert sent[0]["isEnabled"] is True
        assert sent[0]["triggerDateTimeWithOffset"] == "2026-11-19T07:30:00+01:00"
        assert sent[1] == _departure(2, True, "2026-11-20T06:00:00+01:00")
        assert sent[0]["repeatOn"] == ["MONDAY", "FRIDAY"]

    @pytest.mark.asyncio
    async def test_disable_goes_through_departures_edit(self) -> None:
        c = _departures_client([_departure(1, True, "2026-11-19T07:30:00+01:00")])
        await c.command_set_departure_timer(_VIN, 1, False, None)
        _vin, key, payload = c._command.await_args.args
        assert key == "DEPARTURES_EDIT"
        assert payload["list"][0]["isEnabled"] is False

    @pytest.mark.asyncio
    async def test_hh_mm_keeps_date_and_offset(self) -> None:
        c = _departures_client([_departure(3, True, "2026-11-19T07:30:00+01:00")])
        await c.command_set_departure_timer(_VIN, 3, True, "08:15")
        sent = c._command.await_args.args[2]["list"][0]
        assert sent["triggerDateTimeWithOffset"] == "2026-11-19T08:15:00+01:00"

    @pytest.mark.asyncio
    async def test_iso_time_is_taken_as_given(self) -> None:
        c = _departures_client([_departure(1, True, "2026-11-19T07:30:00+01:00")])
        await c.command_set_departure_timer(
            _VIN, 1, True, "2026-11-21T09:00:00+01:00",
        )
        sent = c._command.await_args.args[2]["list"][0]
        assert sent["triggerDateTimeWithOffset"] == "2026-11-21T09:00:00+01:00"

    @pytest.mark.asyncio
    async def test_unknown_id_sends_nothing_and_names_the_ids(self) -> None:
        c = _departures_client([
            _departure(4, True, "2026-11-19T07:30:00+01:00"),
            _departure(5, False, "2026-11-19T07:30:00+01:00"),
        ])
        with pytest.raises(VehicleCommandError) as err:
            await c.command_set_departure_timer(_VIN, 1, True, None)
        assert "4, 5" in str(err.value)
        c._command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_departure_list_sends_nothing(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": [
            _m("DEPARTURES", None, enabled=False),
        ]})
        c._command = AsyncMock()
        with pytest.raises(VehicleCommandError):
            await c.command_set_departure_timer(_VIN, 1, True, None)
        c._command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bad_time_sends_nothing(self) -> None:
        c = _departures_client([_departure(1, True, "2026-11-19T07:30:00+01:00")])
        with pytest.raises(VehicleCommandError):
            await c.command_set_departure_timer(_VIN, 1, True, "7.30 am")
        c._command.assert_not_awaited()


class TestClimateFromHvacSummary:
    @pytest.mark.asyncio
    async def test_hvac_summary_heating_is_active(self) -> None:
        d = await _status([
            _m("HVAC_SUMMARY", {"type": "CLIMATIZER", "status": "HEATING",
                                "targetTemperature": 294.15}),
        ])
        assert d.climatisation_active is True
        assert d.climatisation_state == "ON"
        assert d.target_temperature == 21.0

    @pytest.mark.asyncio
    async def test_hvac_summary_off_wins_over_legacy_on(self) -> None:
        d = await _status([
            _m("HVAC_SUMMARY", {"type": "CLIMATIZER", "status": "OFF"}),
            _m("CLIMATIZER_STATE", {"isOn": True, "targetTemperature": 293.15}),
        ])
        assert d.climatisation_active is False
        assert d.climatisation_state == "OFF"
        assert d.target_temperature == 20.0

    @pytest.mark.asyncio
    async def test_hvac_error_is_not_active(self) -> None:
        d = await _status([
            _m("HVAC_SUMMARY", {"type": "CLIMATIZER", "status": "ERROR",
                                "errorReason": "LOW_BATTERY"}),
        ])
        assert d.climatisation_active is False

    @pytest.mark.asyncio
    async def test_without_hvac_summary_the_legacy_state_still_counts(self) -> None:
        d = await _status([
            _m("HVAC_SUMMARY", None, enabled=False),
            _m("CLIMATIZER_STATE", {"isOn": True, "targetTemperature": 293.15}),
        ])
        assert d.climatisation_active is True
        assert d.climatisation_state == "ON"
        assert d.target_temperature == 20.0

    @pytest.mark.asyncio
    async def test_unknown_hvac_status_falls_back(self) -> None:
        d = await _status([
            _m("HVAC_SUMMARY", {"type": "CLIMATIZER", "status": "SOMETHING_NEW"}),
            _m("CLIMATIZER_STATE", {"isOn": False}),
        ])
        assert d.climatisation_active is False


class TestAcChargingLimit:
    @pytest.mark.asyncio
    async def test_limit_is_read(self) -> None:
        d = await _status([
            _m("CHARGING_SETTINGS", {"targetSoc": 80, "automaticPlugState": "OFF",
                                     "acChargingCurrentLimitA": 16}),
        ])
        assert d.max_charge_current == 16

    @pytest.mark.asyncio
    async def test_no_limit_leaves_the_field_empty(self) -> None:
        d = await _status([_m("CHARGING_SETTINGS", {"targetSoc": 80})])
        assert d.max_charge_current is None

    @pytest.mark.asyncio
    async def test_set_limit_sends_the_app_payload(self) -> None:
        c = _client()
        c._command = AsyncMock()
        await c.command_set_max_charge_current(_VIN, 10)
        c._command.assert_awaited_once_with(
            _VIN, "CHARGING_SETTINGS_AC_CURRENT_LIMIT_EDIT",
            {"spin": None, "acChargingCurrentLimitA": 10},
        )


def _number_keys(brand: str, vehicle: dict) -> set[str]:
    """Run the number platform's per-VIN builder and return the keys it makes."""
    from unittest.mock import MagicMock, patch

    from custom_components.vag_connect import number as number_mod

    coord = MagicMock()
    coord.is_read_only.return_value = False
    coord.is_companion.return_value = False
    coord.read_capability_hidden.return_value = False
    coord.command_capability_supported.return_value = None
    coord.command_method_available.return_value = True
    entry = MagicMock()
    entry.runtime_data = coord
    entry.data = {"brand": brand}
    captured: dict = {}

    def _capture(_entry, _coord, _add, build):
        captured["build"] = build

    with patch.object(number_mod, "register_dynamic_spawner", _capture), \
            patch.object(number_mod, "drop_retired_climate", lambda *a: None), \
            patch.object(number_mod, "drop_unsendable_controls", lambda *a: None), \
            patch.object(number_mod, "_companion_can_sync", lambda *a: False):
        import asyncio
        asyncio.run(number_mod.async_setup_entry(MagicMock(), entry, lambda *a: None))
        built = captured["build"](_VIN, vehicle)
    return {e.entity_description.key for e in built if hasattr(e, "entity_description")}


class TestAcLimitSlider:
    def test_porsche_without_the_value_gets_no_slider(self) -> None:
        keys = _number_keys("porsche", {"has_battery": True})
        assert "max_charge_current" not in keys

    def test_porsche_with_the_value_gets_the_slider(self) -> None:
        keys = _number_keys("porsche", {"has_battery": True, "max_charge_current": 16})
        assert "max_charge_current" in keys

    def test_other_brands_are_unchanged(self) -> None:
        keys = _number_keys("volkswagen", {"has_battery": True})
        assert "max_charge_current" in keys


class TestChargingReason:
    @pytest.mark.asyncio
    async def test_error_comes_first(self) -> None:
        d = await _status([
            _m("CHARGING_SUMMARY", {"status": "CHARGING_ERROR", "reason": {
                "error": "PLUG_NOT_LOCKED", "pause": "INFRASTRUCTURE"}}),
        ])
        assert d.charging_reason == "PLUG_NOT_LOCKED"

    @pytest.mark.asyncio
    async def test_pause_alone(self) -> None:
        d = await _status([
            _m("CHARGING_SUMMARY", {"status": "CHARGING_PAUSED",
                                    "reason": {"pause": "INFRASTRUCTURE"}}),
        ])
        assert d.charging_reason == "INFRASTRUCTURE"

    @pytest.mark.asyncio
    async def test_no_reason(self) -> None:
        d = await _status([_m("CHARGING_SUMMARY", {"status": "CHARGING"})])
        assert d.charging_reason is None


class TestHibernationMode:
    def test_requested(self) -> None:
        assert "HIBERNATION_MODE" in porsche_mod._MEASUREMENTS

    @pytest.mark.asyncio
    async def test_read(self) -> None:
        d = await _status([_m("HIBERNATION_MODE", {"isEnabled": True})])
        assert d.hibernation_mode is True

    @pytest.mark.asyncio
    async def test_unavailable_stays_unknown(self) -> None:
        d = await _status([_m("HIBERNATION_MODE", None, enabled=False)])
        assert d.hibernation_mode is None


class TestPlainStatusRead:
    @pytest.mark.asyncio
    async def test_poll_sends_no_wake_up_job(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": []})
        await c.get_status(_VIN)
        params = c._get.await_args.kwargs["params"]
        assert all(name != "wakeUpJob" for name, _ in params)
        assert ("mf", "MILEAGE") in params
