# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Command dispatcher — per-VIN per-command-class lock + cooldown state.

v1.25.0 PR-D Foundation: extracts the lock-map + wake-cooldown state
out of `coordinator.py`'s lazy-init `if not hasattr(self, ...)` smell
into a properly-typed helper class. Coordinator now holds
``self._dispatcher: CommandDispatcher`` and forwards lock/cooldown
queries through it.

**This is Phase 1A** — the helper class is established; the 30+
``async_lock`` / ``async_unlock`` / ``async_start_climate`` / etc.
command-method bodies stay in ``coordinator.py`` for now (~750 LOC
that the original Sprint-C-Plan PR-C envisioned moving). Phase 2
of the coordinator refactor (= moving those methods into the
dispatcher proper, plus extracting CapabilityCache + EnrichmentService)
is deferred to **v1.26.0** — see ``docs/SPRINT_C_v1.25.0_PLAN.md``
"After-v1.25.0 Roadmap" + "Out-of-Scope for v1.25.0".

Pragmatic rationale:
- v1.25.0 already ships massive user-visible value (cross-brand
  parity wins, listener pattern, GPS hardening, write-side bundle,
  UX/UI mega-bundle, MBB Phase 2)
- A 1-2 day pure-architectural refactor with **zero user benefit**
  doesn't fit "MVP-haft fortschreiten" (Prash 2026-05-09)
- The dispatcher class established here makes the v1.26.0 Phase 2
  extraction mechanical: each method moves intact, just changes
  ``self.X`` → ``self._coordinator.X``

The Phase 1A work itself: removes a code smell (lazy-init via
hasattr) + creates the architectural marker. Coordinator size
delta is small but the new module signals intent.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import VagConnectCoordinator


class CommandDispatcher:
    """Owns per-VIN per-command-class lock + wake-cooldown state.

    Coordinator delegates lock acquisition + wake-cooldown checks
    through this helper. Phase 1A: state container only — actual
    command method bodies still live in ``coordinator.py``.
    """

    def __init__(self, coordinator: VagConnectCoordinator) -> None:
        self._coordinator = coordinator
        # v1.13.0 (#63 Phase 2) — per-VIN per-command-class asyncio.Lock
        # so a stuck command doesn't permanently freeze the entity.
        # ``command_class`` is the high-level grouping (e.g. ``"lock"``,
        # ``"climate"``, ``"charging"``) — finer than command_id (which
        # distinguishes start/stop) so the user can still do
        # ``start_climate`` while a previous ``stop_climate`` is in flight.
        self._command_locks: dict[tuple[str, str], asyncio.Lock] = {}
        # v1.13.0 (#63 Phase 3) — per-VIN wake cooldown timestamp.
        # 5-min anti-double-click cooldown catches "user pressed wake
        # button twice quickly" or automation-bug repeat triggers BEFORE
        # incrementing the daily budget.
        self._wake_last_at: dict[str, datetime] = {}

    def get_command_lock(self, vin: str, command_class: str) -> asyncio.Lock:
        """Lazily create a per-VIN per-command-class lock and return it."""
        key = (vin, command_class)
        lock = self._command_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._command_locks[key] = lock
        return lock

    def is_command_in_flight(self, vin: str, command_class: str) -> bool:
        """True if a command for this VIN+command-class is currently locked.

        Entity layer can use this to render a ``transitioning`` / ``busy``
        UI hint without taking the entity unavailable.
        """
        lock = self._command_locks.get((vin, command_class))
        return bool(lock and lock.locked())

    def record_wake(self, vin: str) -> None:
        """Stamp the last-wake timestamp for cooldown tracking."""
        self._wake_last_at[vin] = datetime.now(tz=timezone.utc)

    def seconds_since_last_wake(self, vin: str) -> float | None:
        """Return seconds since last wake for ``vin``, or None if never woken."""
        last = self._wake_last_at.get(vin)
        if last is None:
            return None
        delta = datetime.now(tz=timezone.utc) - last
        return delta.total_seconds()
