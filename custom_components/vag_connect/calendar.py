# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calendar platform for VW Group Connect — charging/departure schedule + service dates.

Two read-only calendars per vehicle:
- ``charging_schedule`` — departure timers, the next charge window, and charge /
  climate ETAs (timed events, hours-to-days horizon).
- ``service`` — service / oil / brake due dates (all-day events, months horizon).

Departure timers are stored as a bare ``HH:MM`` wall-clock time with no weekday
mask (the mask only exists on the write service, never read back), so an enabled
timer is projected onto every day in the requested range — honest over-generation
we document rather than guessing weekdays.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

_BLOCK = timedelta(minutes=15)  # non-zero duration for instant/timer events

_CHARGE_FIELDS = (
    "departure_timer_1_time", "departure_timer_2_time", "departure_timer_3_time",
    "charge_target_time", "next_charge_timer_start_at", "climate_ready_at",
)
_SERVICE_FIELDS = (
    "service_due_at", "oil_service_at", "brake_fluid_change_due_at",
    "brake_pads_front_inspection_due_at", "brake_pads_rear_inspection_due_at",
    # acpp plug&play — main inspection (HU/TÜV) + first registration + warranty.
    "main_inspection_due_at", "registration_date", "warranty_until",
)


def _parse_dt(val: Any) -> datetime | None:
    """Parse an ISO-8601 datetime string; assume UTC when naive. None on failure."""
    if not isinstance(val, str) or "T" not in val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=dt_util.UTC)


def _parse_date(val: Any) -> date | None:
    """Parse a date (or the date part of an ISO datetime). None on failure."""
    if not isinstance(val, str) or len(val) < 10:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the schedule + service calendars per vehicle.

    Deliberately NOT gated on read-only mode — calendars are pure read surfaces,
    and a portal/read-only car still has service dates + charge ETAs.
    """
    coordinator: VagConnectCoordinator = entry.runtime_data

    def _build_for_vin(vin: str, vehicle: dict) -> list[Any]:
        ents: list[Any] = []
        if vehicle.get("has_battery") or any(vehicle.get(k) for k in _CHARGE_FIELDS):
            ents.append(VagChargingScheduleCalendar(coordinator, vin))
        if any(vehicle.get(k) for k in _SERVICE_FIELDS):
            ents.append(VagServiceCalendar(coordinator, vin))
        return ents

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagChargingScheduleCalendar(VagConnectEntity, CalendarEntity):
    """Departure timers + charge/climate ETAs for one vehicle (read-only)."""

    _attr_translation_key = "charging_schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "charging_schedule")

    def _events_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        v = self._vehicle
        events: list[CalendarEvent] = []

        # Next charge window (real duration when both ends are present).
        cstart = _parse_dt(v.get("next_charge_timer_start_at"))
        cfin = _parse_dt(v.get("next_charge_timer_finish_at"))
        if cstart is not None:
            cend = cfin if (cfin and cfin > cstart) else cstart + _BLOCK
            if cstart < end and cend > start:
                events.append(CalendarEvent(
                    start=cstart, end=cend, summary="Charging (scheduled)",
                    uid=f"{self._vin}-chargewindow"))

        # Instant ETAs.
        for field, summary, uid in (
            ("charge_target_time", "Charge target reached", "chargetarget"),
            ("climate_ready_at", "Cabin ready", "climateready"),
        ):
            t = _parse_dt(v.get(field))
            if t is not None and t < end and t + _BLOCK > start:
                events.append(CalendarEvent(
                    start=t, end=t + _BLOCK, summary=summary,
                    uid=f"{self._vin}-{uid}"))

        # Departure timers — project the HH:MM wall-clock onto every day in range
        # (no weekday mask is read back, so daily projection is the honest choice).
        tz = dt_util.DEFAULT_TIME_ZONE
        for n in (1, 2, 3):
            if not v.get(f"departure_timer_{n}_enabled"):
                continue
            raw = v.get(f"departure_timer_{n}_time")
            if not isinstance(raw, str) or ":" not in raw:
                continue
            try:
                hh, mm = (int(x) for x in raw[:5].split(":"))
            except ValueError:
                continue
            day = start.astimezone(tz).date()
            last = end.astimezone(tz).date()
            while day <= last:
                s = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
                e = s + _BLOCK
                if s < end and e > start:
                    events.append(CalendarEvent(
                        start=s, end=e, summary=f"Departure timer {n}",
                        uid=f"{self._vin}-departure{n}-{day.isoformat()}"))
                day += timedelta(days=1)

        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        # A 3-day forward window is plenty to find the next timer/ETA cheaply.
        upcoming = [
            e for e in self._events_between(now - _BLOCK, now + timedelta(days=3))
            if e.end > now
        ]
        upcoming.sort(key=lambda e: e.start)
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime,  # noqa: ARG002
    ) -> list[CalendarEvent]:
        return self._events_between(start_date, end_date)


class VagServiceCalendar(VagConnectEntity, CalendarEntity):
    """Service / oil / brake due dates for one vehicle (read-only, all-day)."""

    _attr_translation_key = "service"
    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "service")

    def _all_events(self) -> list[CalendarEvent]:
        v = self._vehicle
        out: list[CalendarEvent] = []
        for field, summary in (
            ("service_due_at", "Service due"),
            ("oil_service_at", "Oil service due"),
            ("brake_fluid_change_due_at", "Brake fluid change"),
            ("brake_pads_front_inspection_due_at", "Front brake pads inspection"),
            ("brake_pads_rear_inspection_due_at", "Rear brake pads inspection"),
            ("main_inspection_due_at", "Main inspection (HU / TÜV)"),
            ("registration_date", "First registration"),
            ("warranty_until", "Warranty ends"),
        ):
            d = _parse_date(v.get(field))
            if d is not None:
                out.append(CalendarEvent(
                    start=d, end=d + timedelta(days=1),  # all-day: end exclusive
                    summary=summary, uid=f"{self._vin}-{field}"))
        return out

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        upcoming = sorted(
            (e for e in self._all_events() if e.end > today),
            key=lambda e: e.start,
        )
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime,  # noqa: ARG002
    ) -> list[CalendarEvent]:
        s, e = start_date.date(), end_date.date()
        return [ev for ev in self._all_events() if ev.start < e and ev.end > s]
