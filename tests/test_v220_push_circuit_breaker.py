# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 3 PR #12/20 — Push-Bus 3-strike circuit-breaker.

Foundation for live activation of MQTT (Skoda) + FCM (CUPRA/SEAT +
Audi/VW). After 3 consecutive connect failures the manager trips
into the new ``TRIPPED`` state, stops retrying, and either:
  - waits 1h for auto-reset (lazy property-getter transition)
  - or operator calls ``reset_circuit_breaker()`` to re-enable now

The 3-strike threshold is deliberate: single transient failures
(DNS hiccup, broker rolling restart) are common and shouldn't trip;
three in a row almost always indicates a structural problem (creds
rotated, deps removed, IDP migrated) that won't self-heal in a tight
retry loop.

"What is the optimal number of strikes before you give up on a
faulty appliance? Three. The answer is always three."
— Sheldon Cooper, on circuit-breaker tuning
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone



def _make_manager():
    """Minimal PushManager subclass for testing the breaker mixin."""
    from custom_components.vag_connect.cariad.push.base import PushManager

    class _Stub(PushManager):
        async def start(self) -> None:  # pragma: no cover (not exercised)
            pass

        async def stop(self) -> None:  # pragma: no cover
            pass

    async def _noop(_event):  # pragma: no cover
        pass

    return _Stub(on_event=_noop)


class TestStrikeCounting:
    """Three consecutive strikes trip; success resets."""

    def test_initial_strike_count_is_zero(self) -> None:
        mgr = _make_manager()
        assert mgr.strike_count == 0
        assert mgr.is_tripped is False

    def test_first_strike_increments_count(self) -> None:
        mgr = _make_manager()
        mgr._record_failure("test")
        assert mgr.strike_count == 1
        assert mgr.is_tripped is False

    def test_two_strikes_no_trip(self) -> None:
        mgr = _make_manager()
        mgr._record_failure("a")
        mgr._record_failure("b")
        assert mgr.strike_count == 2
        assert mgr.is_tripped is False

    def test_third_strike_trips(self) -> None:
        mgr = _make_manager()
        mgr._record_failure("a")
        mgr._record_failure("b")
        mgr._record_failure("c")
        assert mgr.strike_count == 3
        assert mgr.is_tripped is True

    def test_success_resets_count(self) -> None:
        mgr = _make_manager()
        mgr._record_failure("a")
        mgr._record_failure("b")
        mgr._record_success()
        assert mgr.strike_count == 0
        assert mgr.is_tripped is False

    def test_success_after_trip_doesnt_clear_state_without_record_success(
        self,
    ) -> None:
        # Test the contract: only explicit _record_success() or
        # reset_circuit_breaker() can clear TRIPPED. The breaker
        # doesn't recover just because no failures arrive.
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        mgr = _make_manager()
        for _ in range(3):
            mgr._record_failure("x")
        assert mgr.is_tripped is True
        # Stays tripped — no auto-recovery without success or reset
        assert mgr.state == PushManagerState.TRIPPED


class TestManualReset:
    """``reset_circuit_breaker()`` clears trip state."""

    def test_reset_after_trip_returns_to_stopped(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        mgr = _make_manager()
        for _ in range(3):
            mgr._record_failure("x")
        assert mgr.state == PushManagerState.TRIPPED

        mgr.reset_circuit_breaker()

        assert mgr.is_tripped is False
        assert mgr.strike_count == 0
        assert mgr.state == PushManagerState.STOPPED

    def test_reset_when_not_tripped_is_noop(self) -> None:
        mgr = _make_manager()
        # No strikes — reset should be a clean no-op
        mgr.reset_circuit_breaker()
        assert mgr.strike_count == 0
        assert mgr.is_tripped is False

    def test_reset_clears_partial_strikes(self) -> None:
        mgr = _make_manager()
        mgr._record_failure("a")
        mgr._record_failure("b")
        # 2/3 strikes — not yet tripped
        assert mgr.is_tripped is False
        mgr.reset_circuit_breaker()
        assert mgr.strike_count == 0


class TestAutoReset:
    """Lazy property-getter transition after the cooldown window."""

    def test_state_getter_resets_after_cooldown(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            CIRCUIT_BREAKER_AUTO_RESET_SEC,
            PushManagerState,
        )

        mgr = _make_manager()
        for _ in range(3):
            mgr._record_failure("x")
        assert mgr._state == PushManagerState.TRIPPED  # raw access

        # Simulate cooldown elapsed by backdating the trip timestamp
        mgr._tripped_at = datetime.now(tz=timezone.utc) - timedelta(
            seconds=CIRCUIT_BREAKER_AUTO_RESET_SEC + 60
        )
        # Reading ``state`` triggers the lazy transition
        assert mgr.state == PushManagerState.STOPPED
        assert mgr.strike_count == 0
        assert mgr._tripped_at is None

    def test_state_getter_doesnt_reset_before_cooldown(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        mgr = _make_manager()
        for _ in range(3):
            mgr._record_failure("x")
        # Just tripped — within cooldown window
        assert mgr.state == PushManagerState.TRIPPED
        # Still tripped on subsequent read
        assert mgr.state == PushManagerState.TRIPPED


class TestTuningConstants:
    """The constants are part of the public contract — locked at 3 & 3600s."""

    def test_max_strikes_is_three(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            CIRCUIT_BREAKER_MAX_STRIKES,
        )

        # 3 chosen empirically: single failure is transient, 3 is
        # structural. Changing this changes the user-facing UX.
        assert CIRCUIT_BREAKER_MAX_STRIKES == 3

    def test_auto_reset_is_one_hour(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            CIRCUIT_BREAKER_AUTO_RESET_SEC,
        )

        # 1h matches the typical token-rotation window.
        assert CIRCUIT_BREAKER_AUTO_RESET_SEC == 3600


class TestNewEnumValue:
    """``TRIPPED`` must be in the enum + retain str-value contract."""

    def test_tripped_state_exists(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        assert PushManagerState.TRIPPED.value == "tripped"

    def test_tripped_distinct_from_disabled_unavailable(self) -> None:
        # Subtle but important: TRIPPED has different recovery semantics
        # from UNAVAILABLE (auto-retry indefinitely) and DISABLED (user
        # opt-out, requires user action). Don't conflate.
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        assert PushManagerState.TRIPPED != PushManagerState.DISABLED
        assert PushManagerState.TRIPPED != PushManagerState.UNAVAILABLE
