# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Holder for DrivePulse readings: the last trip reading of a linked dongle.

DrivePulse only speaks when a trip starts or ends, so between two events there
is nothing to poll. This module keeps the most recent reading per linked
device, in memory and in a small store of its own, so a poll can merge it as
the lowest-trust source and so it survives a restart.

Only the bus events are listened to. The sensors of the foreign integration
are deliberately not read: after a restart their state timestamp is the time
Home Assistant came up, which would make a weeks-old value look fresh. The
event carries (or is stamped with) the time the reading was actually made.

Readings are held per FIELD, each with its own time. One event rarely carries
every field (a value the dongle could not read arrives as nothing), so taking
an event as a whole would wipe a still-good fuel level because the next event
only had a voltage. A field is replaced when a newer event carries it and
otherwise stays until its own hold time is over.

The store here is the only holder. Nothing is written into the vehicle cache
or the entry data, so removing the link or the entry leaves nothing behind:
``DrivePulseHold.async_discard`` deletes the file when the link is removed and
``async_remove_held_store`` when the entry is. The file is keyed by the
foreign device id only: no VIN and no vehicle name is stored.

A reading belongs to the CAR it was taken in, not to the dongle. Each device's
readings are therefore stored with a tag derived from the linked car, and
readings whose tag does not match the current link are dropped on load.
Without that, a dongle moved from one car to another would hand the second
car the first car's reading until its own first trip.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .cariad._drivepulse_source import (
    EVENT_TRIP_END,
    EVENT_TRIP_START,
    build_vehicle_data,
    parse_event,
)
from .cariad.models import VehicleData
from .const import DOMAIN, DRIVEPULSE_HOLD_S

_LOGGER = logging.getLogger(__name__)

_STORE_VERSION = 1
_SAVE_DELAY_S = 5
_KEY = "drivepulse"
# A stored stamp may run a little ahead of the clock (a correction after the
# reading was taken), but not by more: a stamp far in the future would never
# expire and would outrank every other reading by age.
_FUTURE_TOLERANCE_S = 300.0


def held_store_key(entry_id: str) -> str:
    """Storage key of the hold for one config entry."""
    return f"{DOMAIN}.held_push.{entry_id}"


async def async_remove_held_store(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the hold's store file. Never raises (a missing file is fine)."""
    try:
        await Store(hass, _STORE_VERSION, held_store_key(entry_id)).async_remove()
    except Exception as err:  # noqa: BLE001 - cleanup must not block entry removal
        _LOGGER.debug("Could not remove held store: %s", type(err).__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ts_key(ts: Any) -> datetime | None:
    """ISO ``ts`` as an aware datetime (naive counts as UTC), else ``None``."""
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age_s(ts: Any, now: datetime) -> float | None:
    """Seconds since ISO ``ts``, or ``None`` if it cannot be read."""
    dt = _ts_key(ts)
    if dt is None:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds()


class DrivePulseHold:
    """Keeps the latest DrivePulse reading per linked device, field by field."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        links: Mapping[str, str] | None,
        hold_s: float = DRIVEPULSE_HOLD_S,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._hold_s = hold_s
        self._now = now
        # VIN (upper case) -> device id; invalid entries silently dropped.
        self._links: dict[str, str] = {}
        if isinstance(links, Mapping):
            for vin, dev in links.items():
                if isinstance(vin, str) and isinstance(dev, str):
                    v, d = vin.strip().upper(), dev.strip()
                    if v and d:
                        self._links[v] = d
        self._devices = set(self._links.values())
        # device id -> tag of the car it is linked to (see the module docstring).
        self._car_tags: dict[str, str] = {
            dev: self._car_tag(vin) for vin, dev in self._links.items()
        }
        # device id -> {"car": tag, "values": {field: value},
        #               "stamps": {field: iso}}
        self._held: dict[str, dict[str, Any]] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORE_VERSION, held_store_key(entry_id)
        )
        self._unsubs: list[Callable[[], None]] = []
        # True while a change is waiting for the delayed save.
        self._dirty = False

    def _car_tag(self, vin: str) -> str:
        """A short tag that says "this car" without storing the VIN."""
        raw = f"{self._entry_id}:{vin}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def _usable_age(self, ts: Any) -> float | None:
        """Age of a stamp when it is inside the hold, else ``None``."""
        age = _age_s(ts, self._now())
        if age is None or age > self._hold_s or age < -_FUTURE_TOLERANCE_S:
            return None
        return age

    def _usable_fields(self, snap: Any) -> tuple[dict[str, Any], dict[str, str]]:
        """The fields of *snap* whose own stamp is still inside the hold."""
        values: dict[str, Any] = {}
        stamps: dict[str, str] = {}
        if not isinstance(snap, dict):
            return values, stamps
        raw_values, raw_stamps = snap.get("values"), snap.get("stamps")
        if not isinstance(raw_values, dict) or not isinstance(raw_stamps, dict):
            return values, stamps
        for name, value in raw_values.items():
            stamp = raw_stamps.get(name)
            if (
                isinstance(name, str)
                and isinstance(stamp, str)
                and self._usable_age(stamp) is not None
            ):
                values[name] = value
                stamps[name] = stamp
        return values, stamps

    async def async_load(self) -> None:
        """Restore the readings of linked devices that are still within the hold."""
        try:
            data = await self._store.async_load()
            raw = data.get(_KEY) if isinstance(data, dict) else None
            if not isinstance(raw, dict):
                return
            dropped = False
            for dev, snap in raw.items():
                tag = self._car_tags.get(dev)
                # Not linked any more, or taken in another car (the dongle was
                # moved or re-linked).
                if tag is None or not isinstance(snap, dict) or snap.get("car") != tag:
                    dropped = True
                    continue
                values, stamps = self._usable_fields(snap)
                stored = snap.get("values")
                if not isinstance(stored, dict) or len(values) != len(stored):
                    dropped = True
                if values:
                    self._held[dev] = {"car": tag, "values": values, "stamps": stamps}
            if dropped:
                # What was left out must not sit in the file until the next
                # event happens to rewrite it.
                self._dirty = True
                self._store.async_delay_save(self._data_to_save, _SAVE_DELAY_S)
        except Exception as err:  # noqa: BLE001 - broken storage must not block setup
            self._held = {}
            _LOGGER.debug("Could not load held DrivePulse data: %s", type(err).__name__)

    @callback
    def async_start(self) -> Callable[[], None]:
        """Listen for trip events; return the function that stops listening."""
        if not self._devices:
            return lambda: None
        self._unsubs = [
            self._hass.bus.async_listen(EVENT_TRIP_START, self._handle),
            self._hass.bus.async_listen(EVENT_TRIP_END, self._handle),
        ]
        return self._unsubscribe

    @callback
    def _unsubscribe(self) -> None:
        unsubs, self._unsubs = self._unsubs, []
        for unsub in unsubs:
            unsub()

    async def async_stop(self) -> None:
        """Stop listening and write a change that is still waiting.

        The save is delayed by a few seconds. A reload or an unload inside that
        window would otherwise lose the last event for the next instance, and a
        timer firing after the entry was removed would bring the file back.
        Never raises: teardown must not fail on storage.
        """
        try:
            self._unsubscribe()
            if self._dirty:
                self._dirty = False
                await self._store.async_save(self._data_to_save())
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not flush held DrivePulse data: %s", type(err).__name__)

    async def async_discard(self) -> None:
        """Stop listening, forget every reading and delete the file.

        For the moment the link is removed: nothing of the foreign device may
        stay behind, on disk or in memory. Never raises.
        """
        try:
            self._unsubscribe()
            self._held = {}
            self._dirty = False
            await self._store.async_remove()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not discard held DrivePulse data: %s", type(err).__name__)

    @callback
    def _handle(self, event: Event) -> None:
        """Take one trip event. Runs in the event loop, hence ``@callback``.

        Without the decorator Home Assistant would run the listener in a worker
        thread, and neither the dict below nor the store's delayed save may be
        touched from there.
        """
        try:
            snap = parse_event(event.data, event.time_fired)
            if snap is None:
                return
            dev = snap["device_id"]
            if dev not in self._devices:
                return
            new_ts = _ts_key(snap["ts"])
            if new_ts is None:
                return
            tag = self._car_tags.get(dev)
            # Fields past their hold time are dropped here, so the file never
            # keeps a value longer than it would be served.
            old = self._held.get(dev)
            values, stamps = self._usable_fields(
                old if old is not None and old.get("car") == tag else None
            )
            changed = False
            for name, value in snap["values"].items():
                # An older event must not replace a newer reading of the same
                # field. Only a usable stamp protects its value: one that is
                # ahead of the clock was already left out above, so it cannot
                # shut out every later event until the clock catches up.
                held_ts = _ts_key(stamps.get(name))
                if held_ts is not None and new_ts < held_ts:
                    continue
                values[name] = value
                stamps[name] = snap["ts"]
                changed = True
            if not changed:
                return
            self._held[dev] = {"car": tag, "values": values, "stamps": stamps}
            self._dirty = True
            self._store.async_delay_save(self._data_to_save, _SAVE_DELAY_S)
        except Exception as err:  # noqa: BLE001 - foreign input must not disturb the bus
            _LOGGER.debug("Ignored a DrivePulse event: %s", type(err).__name__)

    def _data_to_save(self) -> dict[str, Any]:
        self._dirty = False
        return {
            _KEY: {
                dev: {
                    "car": snap.get("car"),
                    "values": dict(snap.get("values") or {}),
                    "stamps": dict(snap.get("stamps") or {}),
                }
                for dev, snap in self._held.items()
            }
        }

    def _snapshot_for(self, vin: str) -> dict[str, Any] | None:
        if not isinstance(vin, str):
            return None
        dev = self._links.get(vin.strip().upper())
        return self._held.get(dev) if dev else None

    def has_fresh(self, vin: str) -> bool:
        """True when at least one field for the linked device is within the hold."""
        values, _stamps = self._usable_fields(self._snapshot_for(vin))
        return bool(values)

    def vehicle_data(
        self, vin: str, *, has_battery: bool, has_combustion: bool
    ) -> VehicleData | None:
        """Thin ``VehicleData`` from the held readings, or ``None``."""
        snap = self._snapshot_for(vin)
        if snap is None:
            return None
        return build_vehicle_data(
            vin,
            snap,
            has_battery=has_battery,
            has_combustion=has_combustion,
            now=self._now(),
            max_age_s=self._hold_s,
        )
