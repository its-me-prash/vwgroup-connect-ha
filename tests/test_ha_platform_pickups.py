# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HA feature-coverage pickups — update / event / calendar / device diagnostics."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.cariad._util import mask_vin
from custom_components.vag_connect.const import DOMAIN
from custom_components.vag_connect.update import VagUpdateEntity
from custom_components.vag_connect.event import (
    EVENT_TYPE_OTHER,
    VagConnectPushEventEntity,
)
from custom_components.vag_connect.calendar import (
    VagChargingScheduleCalendar,
    VagServiceCalendar,
    _parse_date,
    _parse_dt,
)

VIN = "WVWZZZAUZ1234567"


def _entity(cls, vehicle: dict, *args):
    e = cls.__new__(cls)
    e._vin = VIN
    e.coordinator = MagicMock(data={VIN: vehicle})
    for a in args:
        pass
    return e


# ── update ─────────────────────────────────────────────────────────────────────

def _upd(vehicle: dict) -> VagUpdateEntity:
    return _entity(VagUpdateEntity, vehicle)


def test_update_available_renders_on() -> None:
    e = _upd({"software_version": "1.2", "ota_update_available": True})
    assert e.installed_version == "1.2"
    assert e.latest_version != e.installed_version  # → HA state ON


def test_update_confirmed_up_to_date_renders_off() -> None:
    e = _upd({"software_version": "1.2", "ota_update_available": False})
    assert e.latest_version == "1.2"  # == installed → OFF


def test_update_unknown_is_info_only() -> None:
    e = _upd({"software_version": "1.2"})  # ota_update_available absent → None
    assert e.latest_version is None


def test_update_in_progress_mapping() -> None:
    assert _upd({"software_update_status": "INSTALLING"}).in_progress is True
    assert _upd({"software_update_status": "readyToInstall"}).in_progress is True
    assert _upd({"software_update_status": "NO_UPDATE_AVAILABLE"}).in_progress is False
    assert _upd({}).in_progress is False


def test_update_release_url_passthrough() -> None:
    e = _upd({"ota_release_notes_url": "https://x/notes"})
    assert e.release_url == "https://x/notes"


# ── event ──────────────────────────────────────────────────────────────────────

def _evt(event_types: list[str]) -> VagConnectPushEventEntity:
    e = VagConnectPushEventEntity.__new__(VagConnectPushEventEntity)
    e._vin = VIN
    e._attr_event_types = event_types
    e._trigger_event = MagicMock()
    e.async_write_ha_state = MagicMock()
    return e


def _bus_event(data: dict):
    return SimpleNamespace(data=data)


def test_event_known_type_passes_through() -> None:
    e = _evt(["chargingState", EVENT_TYPE_OTHER])
    e._handle_push_event(_bus_event({"vin": VIN, "event_type": "chargingState"}))
    assert e._trigger_event.call_args.args[0] == "chargingState"


def test_event_unknown_type_coerced_to_other_with_raw_preserved() -> None:
    e = _evt(["chargingState", EVENT_TYPE_OTHER])
    e._handle_push_event(_bus_event({"vin": VIN, "event_type": "some-backend-kebab"}))
    typ, attrs = e._trigger_event.call_args.args
    assert typ == EVENT_TYPE_OTHER
    assert attrs["event_type_raw"] == "some-backend-kebab"


def test_event_filter_matches_only_its_vin() -> None:
    e = _evt([EVENT_TYPE_OTHER])
    assert e._match_vin(_bus_event({"vin": VIN})) is True
    assert e._match_vin(_bus_event({"vin": "OTHERVIN0000000AA"})) is False


# ── calendar ────────────────────────────────────────────────────────────────────

def test_calendar_parse_helpers() -> None:
    assert _parse_dt("2026-08-14T10:00:00Z").tzinfo is not None
    assert _parse_dt("HH:MM") is None
    assert _parse_dt(None) is None
    assert _parse_date("2026-09-01") == date(2026, 9, 1)
    assert _parse_date("2026-09-01T00:00:00Z") == date(2026, 9, 1)
    assert _parse_date("bad") is None


def test_service_calendar_builds_all_day_events() -> None:
    e = _entity(VagServiceCalendar, {
        "service_due_at": "2026-12-01",
        "oil_service_at": "2026-11-15T00:00:00Z",
    })
    evs = e._all_events()
    summaries = {ev.summary for ev in evs}
    assert "Service due" in summaries and "Oil service due" in summaries
    svc = next(ev for ev in evs if ev.summary == "Service due")
    assert svc.start == date(2026, 12, 1)
    assert svc.end == date(2026, 12, 2)  # all-day: end exclusive


def test_charging_calendar_projects_departure_timer() -> None:
    e = _entity(VagChargingScheduleCalendar, {
        "departure_timer_1_enabled": True,
        "departure_timer_1_time": "07:30",
    })
    start = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    evs = e._events_between(start, end)
    dep = [ev for ev in evs if ev.summary == "Departure timer 1"]
    assert len(dep) >= 2  # projected onto each day in the 2-day range
    assert all(ev.end > ev.start for ev in dep)  # non-zero blocks


def test_charging_calendar_ignores_disabled_timer() -> None:
    e = _entity(VagChargingScheduleCalendar, {
        "departure_timer_1_enabled": False,
        "departure_timer_1_time": "07:30",
    })
    start = datetime(2026, 8, 14, tzinfo=timezone.utc)
    evs = e._events_between(start, start + timedelta(days=2))
    assert not [ev for ev in evs if ev.summary == "Departure timer 1"]


# ── device diagnostics ──────────────────────────────────────────────────────────

def test_device_diagnostics_slices_to_one_vin() -> None:
    from custom_components.vag_connect import diagnostics as diag_mod

    masked = mask_vin(VIN)
    other = mask_vin("WVWZZZOTHER99999X")
    full = {
        "config": {"brand": "skoda"},
        "options": {},
        "vehicles": {masked: {"soc": 50}, other: {"soc": 90}},
        "unexpected_findings": {masked: [{"path": "x"}]},
        "mbb_no_legacy": [masked, other],
        "last_update_success": True,
        "cloud_push_active": False,
        "push_states": {},
        "polling_active": True,
        "raw_responses": {"selectivestatus": {"a": 1}},  # account-scoped → dropped
    }
    device = SimpleNamespace(identifiers={(DOMAIN, VIN)})
    with patch.object(
        diag_mod, "async_get_config_entry_diagnostics",
        MagicMock(return_value=_afut(full)),
    ):
        out = asyncio.run(
            diag_mod.async_get_device_diagnostics(MagicMock(), MagicMock(), device)
        )
    assert out["device_vin_masked"] == masked
    assert out["vehicles"] == {masked: {"soc": 50}}      # other VIN not included
    assert out["vehicle_count"] == 1
    assert out["unexpected_findings"] == {masked: [{"path": "x"}]}
    assert out["mbb_no_legacy"] == [masked]
    assert "raw_responses" not in out                     # account-scoped, dropped


def test_device_diagnostics_settings_device_gets_no_slice() -> None:
    from custom_components.vag_connect import diagnostics as diag_mod

    device = SimpleNamespace(identifiers={(DOMAIN, "entryid_settings")})
    with patch.object(
        diag_mod, "async_get_config_entry_diagnostics",
        MagicMock(return_value=_afut({"config": {}, "options": {}})),
    ):
        out = asyncio.run(
            diag_mod.async_get_device_diagnostics(MagicMock(), MagicMock(), device)
        )
    assert "device_note" in out
    assert "vehicles" not in out


def _afut(value):
    async def _coro():
        return value
    return _coro()
