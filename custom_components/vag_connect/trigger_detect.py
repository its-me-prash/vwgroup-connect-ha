# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b14 (experimental) — vehicle state-transition detection for the named-trigger
platform (``trigger.py``).

Kept OUT of the 8000-line coordinator so the edge logic is unit-testable in
isolation and HA-version-independent. The coordinator feeds each REAL (push /
poll) data snapshot into :meth:`VehicleTransitionDetector.feed`; the detector
compares it against the previous snapshot and fires edge callbacks that the
trigger platform subscribes to.

Two hard rules the caller must honour (both grounded in the coordinator's own
documented traps):
  * feed() ONLY on a real data update — NEVER on the optimistic-echo
    ``async_set_updated_data(dict(self.vehicles))`` calls, or every button press
    would fire a phantom "started charging".
  * the first snapshot of a VIN, and any ``None`` (unknown) → value edge, never
    fire — otherwise every restart spams events.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Boolean field → (event on False→True, event on True→False).
_BOOL_EDGES: dict[str, tuple[str, str]] = {
    "is_charging": ("started_charging", "stopped_charging"),
    "plug_connected": ("plugged_in", "unplugged"),
    "climatisation_active": ("started_preconditioning", "stopped_preconditioning"),
}
# doors_locked reads inverted: True→False is "unlocked", False→True is "locked".
_LOCK_FIELD = "doors_locked"

# Every event key the detector can emit — the trigger platform registers these.
EVENT_KEYS: frozenset[str] = frozenset(
    {ev for pair in _BOOL_EDGES.values() for ev in pair}
    | {"locked", "unlocked", "charge_target_reached"}
)

# The vehicle-dict fields we snapshot each cycle (keep the baseline tiny).
_TRACKED_FIELDS: tuple[str, ...] = (
    "is_charging", "plug_connected", "climatisation_active", "doors_locked",
    "battery_soc", "target_soc",
)

_Listener = Callable[[dict[str, Any]], None]


class VehicleTransitionDetector:
    """Detects per-vehicle state edges across successive data snapshots."""

    def __init__(self) -> None:
        self._prev: dict[str, dict[str, Any]] = {}
        # event_key → list of (vin_or_None, callback)
        self._listeners: dict[str, list[tuple[str | None, _Listener]]] = {}

    def register(
        self, event_key: str, vin: str | None, callback: _Listener
    ) -> Callable[[], None]:
        """Subscribe to an event (optionally scoped to one VIN). Returns unsub."""
        entry = (vin, callback)
        self._listeners.setdefault(event_key, []).append(entry)

        def _unsub() -> None:
            lst = self._listeners.get(event_key)
            if lst is not None and entry in lst:
                lst.remove(entry)

        return _unsub

    def feed(self, data: dict[str, dict[str, Any]]) -> None:
        """Compare *data* against the last snapshot and fire edge listeners."""
        for vin, veh in data.items():
            if str(vin).startswith("_") or not isinstance(veh, dict):
                continue
            prev = self._prev.get(vin)
            if prev is not None:
                for event_key in self._detect(prev, veh):
                    self._fire(event_key, vin)
            self._prev[vin] = {k: veh.get(k) for k in _TRACKED_FIELDS}

    def _detect(self, prev: dict[str, Any], cur: dict[str, Any]) -> list[str]:
        events: list[str] = []
        for field, (on_true, on_false) in _BOOL_EDGES.items():
            old, new = prev.get(field), cur.get(field)
            if isinstance(old, bool) and isinstance(new, bool) and old != new:
                events.append(on_true if new else on_false)
        old, new = prev.get(_LOCK_FIELD), cur.get(_LOCK_FIELD)
        if isinstance(old, bool) and isinstance(new, bool) and old != new:
            events.append("locked" if new else "unlocked")
        # charge_target_reached — SoC crosses UP to >= target (once, not every
        # poll while parked at/above target).
        po, pn, tgt = (
            prev.get("battery_soc"), cur.get("battery_soc"), cur.get("target_soc")
        )
        if (
            isinstance(po, int) and isinstance(pn, int) and isinstance(tgt, int)
            and not isinstance(po, bool) and not isinstance(pn, bool)
            and po < tgt <= pn
        ):
            events.append("charge_target_reached")
        return events

    def _fire(self, event_key: str, vin: str) -> None:
        payload = {"vin": vin, "event": event_key}
        for lvin, cb in list(self._listeners.get(event_key, [])):
            if lvin is None or lvin == vin:
                try:
                    cb(payload)
                except Exception:  # noqa: BLE001 — a listener must never break polling
                    _LOGGER.debug(
                        "vehicle transition listener for %s raised", event_key,
                        exc_info=True,
                    )
