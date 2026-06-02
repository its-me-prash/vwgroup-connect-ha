# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 3 PR #13/20 — CUPRA/SEAT FCM circuit-breaker wiring.

Companion to PR #12 (foundation). Wires the breaker hooks into the
CUPRA/SEAT FCM push manager at three sites:

  1. ``start()``: short-circuits when state == TRIPPED
  2. ``start()`` deps-check failure: records strike
  3. ``_run_loop()`` connect-exception path: records strike
  4. ``_run_loop()`` post-backoff trip check: breaks outer loop
  5. ``_connect_and_listen()`` success path: records success (resets)

CUPRA + SEAT share the same OLA FCM backend (different brand
project_ids) — both go through the same manager class with the
``brand`` constructor arg discriminating the project.

"That, my dear Penny, is what we call defensive programming."
— Sheldon Cooper, on why a 3-strike circuit-breaker is the right
abstraction
"""

from __future__ import annotations

import inspect


class TestCupraSeatWiringSites:
    """Source-level checks that all 5 hook sites are wired.

    We verify via source inspection rather than runtime because the
    push manager is a stub (real FCM connection still pending tester
    validation), so triggering live behaviour isn't practical yet.
    Source inspection is the right level here — confirms the wiring
    contract without requiring a live broker.
    """

    def _source(self) -> str:
        from custom_components.vag_connect.cariad.push import cupra_seat_fcm

        return inspect.getsource(cupra_seat_fcm)

    def test_start_short_circuits_on_tripped(self) -> None:
        src = self._source()
        # The start() function must check ``self.state == PushManagerState.TRIPPED``
        # BEFORE reading self._vins (the existing early-return)
        assert "if self.state == PushManagerState.TRIPPED" in src

    def test_missing_deps_records_strike(self) -> None:
        src = self._source()
        # The except-ImportError branch must call _record_failure
        # with a reason mentioning missing-dep
        assert 'self._record_failure(f"missing-dep' in src

    def test_connect_loop_records_strike(self) -> None:
        src = self._source()
        # The except-Exception branch in _run_loop must record a
        # connect-loop strike
        assert 'self._record_failure(f"connect-loop' in src

    def test_loop_exits_on_trip(self) -> None:
        src = self._source()
        # After the backoff sleep + _advance_backoff, the loop must
        # check is-tripped and break the outer while
        assert (
            "if self.state == PushManagerState.TRIPPED" in src
            and "exiting reconnect loop" in src
        )

    def test_connect_success_resets_strikes(self) -> None:
        src = self._source()
        # The _connect_and_listen path that transitions to CONNECTED
        # must call _record_success() to clear any prior strike count
        assert "self._record_success()" in src


class TestCupraSeatInheritsBreakerMixin:
    """The manager class must inherit the breaker mixin from base."""

    def test_class_has_record_failure(self) -> None:
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        assert hasattr(CupraSeatPushManager, "_record_failure")
        assert callable(CupraSeatPushManager._record_failure)

    def test_class_has_record_success(self) -> None:
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        assert hasattr(CupraSeatPushManager, "_record_success")
        assert callable(CupraSeatPushManager._record_success)

    def test_class_has_reset_circuit_breaker(self) -> None:
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        assert hasattr(CupraSeatPushManager, "reset_circuit_breaker")
        assert callable(CupraSeatPushManager.reset_circuit_breaker)

    def test_class_has_is_tripped_property(self) -> None:
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        assert hasattr(CupraSeatPushManager, "is_tripped")
        # Verify it's a property, not a regular method
        assert isinstance(
            inspect.getattr_static(CupraSeatPushManager, "is_tripped"), property
        )

    def test_class_has_strike_count_property(self) -> None:
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        assert hasattr(CupraSeatPushManager, "strike_count")
        assert isinstance(
            inspect.getattr_static(CupraSeatPushManager, "strike_count"),
            property,
        )


class TestParityWithSkodaWiring:
    """The CUPRA/SEAT wiring shape MUST match the Skoda wiring shape
    so behaviour is identical across brands. Source-level comparison."""

    def test_both_brands_have_same_hook_count(self) -> None:
        from custom_components.vag_connect.cariad.push import (
            cupra_seat_fcm,
            skoda_mqtt,
        )

        skoda_src = inspect.getsource(skoda_mqtt)
        cupra_src = inspect.getsource(cupra_seat_fcm)

        # 3 _record_failure call sites (start-deps + connect-loop +
        # maybe future-third), 1 _record_success call site
        assert skoda_src.count("self._record_failure(") == cupra_src.count(
            "self._record_failure("
        )
        assert skoda_src.count("self._record_success()") == cupra_src.count(
            "self._record_success()"
        )

    def test_both_brands_short_circuit_tripped_state(self) -> None:
        from custom_components.vag_connect.cariad.push import (
            cupra_seat_fcm,
            skoda_mqtt,
        )

        # Both must have the same TRIPPED short-circuit pattern in start()
        marker = "if self.state == PushManagerState.TRIPPED"
        assert marker in inspect.getsource(skoda_mqtt)
        assert marker in inspect.getsource(cupra_seat_fcm)
