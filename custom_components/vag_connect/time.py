# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Time platform for VAG Connect — Departure-Timer editing UI.

v1.16.0 (#26) — closes the long-standing UX gap that users had to call
the ``vag_connect.set_departure_timer`` service manually to change a
timer's time. Now there's a `time.{auto}_departure_timer_X` HA entity
per timer that the user can edit directly in the dashboard.

The entity reads from the existing ``departure_timer_X_time`` field in
the coordinator's vehicle dict (already populated by every brand parser
that supports departure timers). On set, it dispatches to the existing
``coordinator.async_set_departure_timer`` helper — same service path
that ``VagDepartureTimerSwitch`` already uses for the on/off toggle.

Cross-brand: works for any vehicle whose parser populates
``departure_timer_X_time`` as ``"HH:MM"`` string (currently VW EU /
Audi / Skoda / SEAT / CUPRA via their respective departureTimers /
departureProfiles / departure-timers endpoints).
"""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up departure timers. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.12.0 (#63) — Read-only Mode: time entities write commands, skip.
    if coordinator.is_read_only():
        return

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        if not vehicle.get("has_battery"):
            return []
        if (
            coordinator.command_capability_supported(vin, "command_set_departure_timer")
            is False
        ):
            return []
        return [VagDepartureTimerTime(coordinator, vin, tid) for tid in (1, 2, 3)]

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagDepartureTimerTime(VagConnectEntity, TimeEntity):
    """Departure timer time-of-day editing entity."""

    _attr_icon = "mdi:clock-edit-outline"
    _command_id = "command_set_departure_timer"  # for Phase 2 gating

    def __init__(
        self, coordinator: VagConnectCoordinator, vin: str, timer_id: int
    ) -> None:
        super().__init__(coordinator, vin, f"departure_timer_{timer_id}_time_set")
        self._timer_id = timer_id
        self._attr_translation_key = f"departure_timer_{timer_id}_time_set"

    @property
    def native_value(self) -> time | None:
        """Read the current departure time as ``datetime.time``.

        Reads from ``vehicle["departure_timer_X_time"]`` which the brand
        parsers populate as ``"HH:MM"`` string. Defensive against full
        ISO datetimes (some backends ship full timestamps when a date
        was set) — we only take the time-of-day part.
        """
        raw = self._vehicle.get(f"departure_timer_{self._timer_id}_time")
        if not isinstance(raw, str) or not raw:
            return None
        # Try strict HH:MM first, then HH:MM:SS, then ISO date
        for fmt_len in (5, 8):
            try:
                return time.fromisoformat(raw[:fmt_len])
            except ValueError:
                continue
        # ISO datetime fallback (e.g. "2026-05-02T07:30:00Z")
        if "T" in raw:
            try:
                return time.fromisoformat(raw.split("T", 1)[1][:8])
            except ValueError:
                pass
        return None

    async def async_set_value(self, value: time) -> None:
        """User edited the time in HA → dispatch to the backend.

        Reuses ``coordinator.async_set_departure_timer`` so the same
        per-VIN per-command-class lock + capability bookkeeping kicks
        in as the existing service path. Sends the time as ``HH:MM``
        — the brand clients normalise to whatever shape the backend
        expects (``string "HH:MM"`` for VW EU / Audi / Skoda; expanded
        to ISO datetime by the OLA path for SEAT/CUPRA).
        """
        hhmm = value.strftime("%H:%M")
        # ``enabled=True`` so editing the time also flips the timer on
        # if it was off — matches user expectation when they set a time.
        await self.coordinator.async_set_departure_timer(
            self._vin,
            self._timer_id,
            enabled=True,
            departure_time=hhmm,
        )
