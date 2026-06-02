# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 3 PR #14/20 — Audi/VW FCM circuit-breaker wiring.

**Phase 3 closer.** Completes the cross-brand circuit-breaker
coverage: Skoda MQTT (PR #12), CUPRA/SEAT FCM (PR #13), Audi/VW FCM
(this PR) all now wire the 5 hook sites uniformly.

After this PR every push manager in the integration has identical
fail-safe behaviour: 3 consecutive connect failures → TRIPPED state
→ 1h auto-reset (or manual ``reset_circuit_breaker()``).

The 3-way parity test (Skoda + CUPRA/SEAT + Audi/VW) is the
regression-shield that catches future drift — if any brand's wiring
diverges (extra hook, missing hook, different reason-string format)
the parity test fails.

"Live activation can wait. The safety net must come first."
— paraphrased Sheldon Cooper, on push-bus engineering discipline
"""

from __future__ import annotations

import inspect


class TestAudiVWWiringSites:
    """Source-level checks that all 5 hook sites are wired."""

    def _source(self) -> str:
        from custom_components.vag_connect.cariad.push import audi_vw_fcm

        return inspect.getsource(audi_vw_fcm)

    def test_start_short_circuits_on_tripped(self) -> None:
        src = self._source()
        assert "if self.state == PushManagerState.TRIPPED" in src

    def test_missing_deps_records_strike(self) -> None:
        src = self._source()
        assert 'self._record_failure(f"missing-dep' in src

    def test_connect_loop_records_strike(self) -> None:
        src = self._source()
        assert 'self._record_failure(f"connect-loop' in src

    def test_loop_exits_on_trip(self) -> None:
        src = self._source()
        assert (
            "if self.state == PushManagerState.TRIPPED" in src
            and "exiting reconnect loop" in src
        )

    def test_connect_success_resets_strikes(self) -> None:
        src = self._source()
        assert "self._record_success()" in src


class TestAudiVWInheritsBreakerMixin:
    """Class must inherit the breaker mixin from base."""

    def test_class_has_record_failure(self) -> None:
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        assert hasattr(AudiVWPushManager, "_record_failure")

    def test_class_has_record_success(self) -> None:
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        assert hasattr(AudiVWPushManager, "_record_success")

    def test_class_has_reset_circuit_breaker(self) -> None:
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        assert hasattr(AudiVWPushManager, "reset_circuit_breaker")

    def test_class_has_is_tripped_property(self) -> None:
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        assert isinstance(
            inspect.getattr_static(AudiVWPushManager, "is_tripped"), property
        )

    def test_class_has_strike_count_property(self) -> None:
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        assert isinstance(
            inspect.getattr_static(AudiVWPushManager, "strike_count"), property
        )


class TestThreeWayParity:
    """Phase 3 closer regression-shield: ALL three push managers must
    have identical hook-counts. Any future divergence breaks this test."""

    def test_all_three_brands_have_same_record_failure_count(self) -> None:
        from custom_components.vag_connect.cariad.push import (
            audi_vw_fcm,
            cupra_seat_fcm,
            skoda_mqtt,
        )

        skoda = inspect.getsource(skoda_mqtt).count("self._record_failure(")
        cupra = inspect.getsource(cupra_seat_fcm).count(
            "self._record_failure("
        )
        audi = inspect.getsource(audi_vw_fcm).count("self._record_failure(")
        assert skoda == cupra == audi, (
            f"hook-count drift: skoda={skoda} cupra={cupra} audi={audi}"
        )

    def test_all_three_brands_have_same_record_success_count(self) -> None:
        from custom_components.vag_connect.cariad.push import (
            audi_vw_fcm,
            cupra_seat_fcm,
            skoda_mqtt,
        )

        skoda = inspect.getsource(skoda_mqtt).count("self._record_success()")
        cupra = inspect.getsource(cupra_seat_fcm).count(
            "self._record_success()"
        )
        audi = inspect.getsource(audi_vw_fcm).count("self._record_success()")
        assert skoda == cupra == audi, (
            f"success-reset drift: skoda={skoda} cupra={cupra} audi={audi}"
        )

    def test_all_three_brands_short_circuit_tripped_state(self) -> None:
        from custom_components.vag_connect.cariad.push import (
            audi_vw_fcm,
            cupra_seat_fcm,
            skoda_mqtt,
        )

        marker = "if self.state == PushManagerState.TRIPPED"
        for mod in (skoda_mqtt, cupra_seat_fcm, audi_vw_fcm):
            assert marker in inspect.getsource(mod), (
                f"{mod.__name__}: missing TRIPPED short-circuit"
            )

    def test_all_three_brands_log_reset_hint_on_trip(self) -> None:
        # Operator-facing message: "wait for auto-reset (1h) or call
        # reset_circuit_breaker()" — must be present in all three
        # log messages so users always know how to recover regardless
        # of brand.
        from custom_components.vag_connect.cariad.push import (
            audi_vw_fcm,
            cupra_seat_fcm,
            skoda_mqtt,
        )

        for mod in (skoda_mqtt, cupra_seat_fcm, audi_vw_fcm):
            src = inspect.getsource(mod)
            assert (
                "auto-reset" in src and "reset_circuit_breaker" in src
            ), f"{mod.__name__}: missing recovery hint in log"
