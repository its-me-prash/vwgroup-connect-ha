# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abstract base + value types for push managers.

All brand-specific push managers (Skoda MQTT, CUPRA/SEAT FCM, ...)
implement the same lifecycle so the coordinator can hold them
uniformly via ``self._push_manager: PushManager | None``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import logging
import random
from typing import Any, Awaitable, Callable

_LOGGER = logging.getLogger(__name__)

# v2.2.0 Phase 5a PR #18/20 — extracted from per-brand duplication.
#
# Reconnect-backoff bounds shared across all push managers. evcc +
# myskoda + pycupra all agree on these constants empirically — they
# match the behaviour of the official VAG apps which retry every
# 5s for the first 10 attempts then back off exponentially to 10min
# cap. Centralised here so a single tuning change propagates to all
# brand managers without per-file edits.
#
# Subclasses MAY override by setting class-level overrides BEFORE
# ``super().__init__()``. The defaults are sane for production VAG
# brokers; only override for unit tests that need accelerated retries.
PUSH_INITIAL_BACKOFF_S: float = 5.0
PUSH_MAX_BACKOFF_S: float = 600.0
PUSH_BACKOFF_MULTIPLIER: float = 2.0
PUSH_FAST_RETRY_THRESHOLD: int = 10  # First N retries skip cap

# v2.2.0 Phase 3 PR #12/20 — circuit-breaker tuning.
#
# After ``CIRCUIT_BREAKER_MAX_STRIKES`` consecutive failed-start
# attempts the manager trips into the ``TRIPPED`` state, where:
# - subsequent ``start()`` calls return immediately without retrying
# - state-property surfaces the trip for diagnostics + Repair-Issue
# - operator can manually reset via ``reset_circuit_breaker()``
# - auto-recovery happens after ``CIRCUIT_BREAKER_AUTO_RESET_SEC``
#
# Three strikes chosen empirically: a single transient failure is
# common (DNS hiccup, broker rolling restart) and shouldn't trip;
# three in a row almost always means a structural issue (creds rotated,
# deps removed, IDP migrated) that won't self-heal in the retry loop.
#
# Auto-reset at 1h matches the typical token-rotation window — by
# the time we auto-retry, refresh-token state should have moved on
# from whatever was failing.
CIRCUIT_BREAKER_MAX_STRIKES: int = 3
CIRCUIT_BREAKER_AUTO_RESET_SEC: int = 3600  # 1 hour


class PushManagerState(StrEnum):
    """Lifecycle phases of a push manager."""

    STOPPED = "stopped"
    STARTING = "starting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISABLED = "disabled"      # opt-out via option, no work attempted
    UNAVAILABLE = "unavailable"  # deps missing or broker unreachable
    # v2.2.0 Phase 3 PR #12/20 — Circuit-breaker trip state.
    # Reached after CIRCUIT_BREAKER_MAX_STRIKES consecutive failed
    # start attempts. Distinct from UNAVAILABLE (transient) and
    # DISABLED (user opt-out) — TRIPPED means "we tried hard and
    # the failure mode looks structural, so stop spinning the loop
    # until either auto-reset (1h) or manual reset_circuit_breaker()".
    TRIPPED = "tripped"


@dataclass(frozen=True)
class PushUpdateEvent:
    """A single push event from the manufacturer backend.

    Carries enough context for the coordinator to decide what to
    refresh — never the full state itself, since most VAG push events
    are change-notifications, not state-payloads.

    Attributes:
        vin: The 17-char VIN the event is for.
        event_type: Backend-defined string. For Skoda mysmob this is
            one of ``operation-request``, ``service-event``,
            ``account-event``, ``vehicle-event``. For CUPRA/SEAT FCM
            it's the FCM message type.
        topic: Full backend topic / channel string. Useful for
            debugging + coordinator-side filtering.
        timestamp: ISO-8601 UTC string of when the backend produced
            the event (NOT when we received it).
        raw_payload: Decoded JSON payload, if any. Some events carry
            full state slices; most are pure notifications.
    """

    vin: str
    event_type: str
    topic: str
    timestamp: str
    raw_payload: dict[str, Any] | None = None


# Coordinator callback signature — push manager fires this on each
# event so coordinator can refresh + async_set_updated_data.
PushEventCallback = Callable[[PushUpdateEvent], Awaitable[None]]


class PushManager(ABC):
    """Abstract base for brand-specific push managers.

    Subclasses MUST implement ``start()`` and ``stop()``. ``start``
    is fire-and-forget — it spawns its own background task so callers
    don't block. ``stop`` waits for clean shutdown.

    Subclasses SHOULD:
    - Lazy-import their network deps (aiomqtt, firebase-messaging)
      inside ``start()`` so non-opted-in users don't pay the install
      cost
    - Use exponential backoff on reconnect (5s → 600s with jitter)
    - Refresh OAuth tokens before each reconnect attempt
    - Log only masked VINs / user_ids — NEVER tokens
    """

    def __init__(self, on_event: PushEventCallback) -> None:
        self._on_event = on_event
        self._state: PushManagerState = PushManagerState.STOPPED
        # v2.2.0 Phase 3 PR #12/20 — circuit-breaker state.
        # Subclasses call ``_record_failure()`` / ``_record_success()``
        # around their connect attempts; this class handles the
        # strike-counting + trip + auto-reset arithmetic.
        self._strike_count: int = 0
        self._tripped_at: datetime | None = None
        # v2.2.0 Phase 5a PR #18/20 — backoff state extracted from
        # per-brand duplication. Identical bounds across all push
        # managers; centralised here so a single tuning change
        # propagates to all brands without per-file edits.
        self._backoff_seconds: float = PUSH_INITIAL_BACKOFF_S
        self._consecutive_fast_retries: int = 0

    @property
    def state(self) -> PushManagerState:
        """Current lifecycle state for diagnostics.

        v2.2.0 PR #12: this getter is now circuit-breaker-aware.
        When auto-reset elapses past the trip timestamp, transitions
        TRIPPED → STOPPED so the next ``start()`` call is permitted.
        Lazy transition (only on read) avoids needing a background
        timer just to flip a state value.
        """
        if (
            self._state == PushManagerState.TRIPPED
            and self._tripped_at is not None
        ):
            elapsed = datetime.now(tz=timezone.utc) - self._tripped_at
            if elapsed >= timedelta(seconds=CIRCUIT_BREAKER_AUTO_RESET_SEC):
                _LOGGER.info(
                    "Push manager %s: circuit-breaker auto-reset after "
                    "%ds — moving TRIPPED → STOPPED for retry eligibility",
                    self.__class__.__name__,
                    int(elapsed.total_seconds()),
                )
                self._strike_count = 0
                self._tripped_at = None
                self._state = PushManagerState.STOPPED
        return self._state

    @property
    def strike_count(self) -> int:
        """Current consecutive-failure count (0 if last attempt succeeded)."""
        return self._strike_count

    @property
    def is_tripped(self) -> bool:
        """Convenience property — True when circuit-breaker has tripped.

        Reads ``state`` (not ``_state``) so the auto-reset transition
        is honoured.
        """
        return self.state == PushManagerState.TRIPPED

    def _record_failure(self, reason: str = "") -> None:
        """Subclass hook: a connect / re-connect attempt failed.

        Increments the strike count. On the 3rd consecutive strike
        flips state to TRIPPED. Subclass is responsible for stopping
        its own retry loop when ``is_tripped`` returns True.

        ``reason`` is logged at warning level for diagnostics —
        keep it short and free of secrets.
        """
        self._strike_count += 1
        _LOGGER.warning(
            "Push manager %s: strike %d/%d (%s)",
            self.__class__.__name__,
            self._strike_count,
            CIRCUIT_BREAKER_MAX_STRIKES,
            reason or "no-reason-given",
        )
        if self._strike_count >= CIRCUIT_BREAKER_MAX_STRIKES:
            self._tripped_at = datetime.now(tz=timezone.utc)
            self._state = PushManagerState.TRIPPED
            _LOGGER.error(
                "Push manager %s: circuit-breaker TRIPPED after %d "
                "consecutive failures — pausing reconnect attempts for "
                "%ds (or until manual reset_circuit_breaker())",
                self.__class__.__name__,
                self._strike_count,
                CIRCUIT_BREAKER_AUTO_RESET_SEC,
            )

    def _record_success(self) -> None:
        """Subclass hook: a connect attempt succeeded.

        Resets the strike counter and clears any trip state. Safe to
        call from anywhere — idempotent when the breaker isn't tripped.
        """
        if self._strike_count > 0 or self._tripped_at is not None:
            _LOGGER.debug(
                "Push manager %s: resetting circuit-breaker after success "
                "(was strike %d, tripped_at=%s)",
                self.__class__.__name__,
                self._strike_count,
                self._tripped_at.isoformat() if self._tripped_at else None,
            )
        self._strike_count = 0
        self._tripped_at = None

    def reset_circuit_breaker(self) -> None:
        """Manual reset — re-enable the manager after a tripped breaker.

        Use case: operator fixed the root cause (rotated creds, restored
        broker, re-installed deps) and wants to retry NOW instead of
        waiting for the 1h auto-reset window. The next ``start()`` call
        will proceed normally.

        Doesn't re-start the manager — caller must invoke ``start()``
        explicitly after reset.
        """
        if self._tripped_at is None and self._strike_count == 0:
            return
        _LOGGER.info(
            "Push manager %s: manual circuit-breaker reset (was strike "
            "%d, tripped_at=%s)",
            self.__class__.__name__,
            self._strike_count,
            self._tripped_at.isoformat() if self._tripped_at else None,
        )
        self._strike_count = 0
        self._tripped_at = None
        if self._state == PushManagerState.TRIPPED:
            self._state = PushManagerState.STOPPED

    @abstractmethod
    async def start(self) -> None:
        """Spawn the background push connection.

        Idempotent — safe to call multiple times. If already connected
        or starting, returns immediately.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Cleanly disconnect + cancel the background task.

        Idempotent. Waits for the task to finish (with timeout) so
        the caller can rely on resource release upon return.
        """

    def _advance_backoff(self) -> None:
        """Bump reconnect-backoff with jitter, capped per myskoda PR #566.

        v2.2.0 Phase 5a PR #18/20: extracted from per-brand duplication.
        First ``PUSH_FAST_RETRY_THRESHOLD`` retries grow linearly without
        the hard cap; afterwards the exponential cap kicks in. Jitter
        prevents reconnect-storm thundering on broker outages.

        Called by subclasses from their ``_run_loop`` after a connection
        failure + a successful ``_record_failure()`` strike record.
        """
        self._consecutive_fast_retries += 1
        if self._consecutive_fast_retries <= PUSH_FAST_RETRY_THRESHOLD:
            self._backoff_seconds = min(
                self._backoff_seconds * PUSH_BACKOFF_MULTIPLIER,
                PUSH_MAX_BACKOFF_S,
            )
        else:
            self._backoff_seconds = PUSH_MAX_BACKOFF_S
        # Jitter: ±10% of current backoff
        jitter = self._backoff_seconds * 0.1 * (2 * random.random() - 1)
        self._backoff_seconds = max(
            PUSH_INITIAL_BACKOFF_S,
            self._backoff_seconds + jitter,
        )

    def _reset_backoff(self) -> None:
        """Reset backoff after a successful connection.

        v2.2.0 Phase 5a PR #18/20: extracted from per-brand duplication.
        Called from ``_connect_and_listen`` once the connection is
        established + first message received. Stub managers (pre-live-
        activation) don't call this yet — they'll start invoking it
        when the real network path lights up.
        """
        self._backoff_seconds = PUSH_INITIAL_BACKOFF_S
        self._consecutive_fast_retries = 0

    async def emit(self, event: PushUpdateEvent) -> None:
        """Forward an event to the coordinator callback.

        Subclasses call this from their message-handler. Wrapped in
        try/except so a failing coordinator handler doesn't crash
        the push loop.
        """
        try:
            await self._on_event(event)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Push event handler raised for vin ***%s (%s): %s — "
                "continuing push loop",
                event.vin[-6:] if event.vin else "??????",
                event.event_type,
                err,
            )
