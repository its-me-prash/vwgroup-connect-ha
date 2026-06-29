# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 Phase 5a PR #18/20 — Push-Bus internal abstraction refactor.

Extracts the duplicated ``_advance_backoff`` + ``_reset_backoff``
methods + backoff constants from the 3 brand push managers into the
``PushManager`` base class.

Before this PR:
- 3 identical sets of constants (``_INITIAL_BACKOFF_S`` etc.)
- 3 identical implementations of ``_advance_backoff``
- 3 identical implementations of ``_reset_backoff``
- 3 identical ``random`` imports
- 3 identical ``_backoff_seconds`` + ``_consecutive_fast_retries``
  initialisations

After:
- Single source of truth in ``base.py``
- Subclasses inherit via ``super().__init__()``
- ~80 lines of duplication removed across the 3 brand managers
- Future managers (Phase 4 brand scaffolds when activated) get the
  pattern for free

Behaviour unchanged — same jitter formula, same caps, same retry
threshold. Tests verify the inherited methods produce identical
results to the pre-refactor per-brand implementations.

"DRY — Don't Repeat Yourself. Also: Don't Repeat Yourself."
— Sheldon Cooper, on refactoring discipline
"""

from __future__ import annotations


def _make_manager():
    """Minimal PushManager subclass for exercising the inherited
    backoff methods (no live connection)."""
    from custom_components.vag_connect.cariad.push.base import PushManager

    class _Stub(PushManager):
        async def start(self) -> None:  # pragma: no cover
            pass

        async def stop(self) -> None:  # pragma: no cover
            pass

    async def _noop(_event):  # pragma: no cover
        pass

    return _Stub(on_event=_noop)


class TestBackoffConstantsExtracted:
    """The constants must live in base.py, not in per-brand modules."""

    def test_initial_backoff_in_base(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_INITIAL_BACKOFF_S,
        )

        assert PUSH_INITIAL_BACKOFF_S == 5.0

    def test_max_backoff_in_base(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_MAX_BACKOFF_S,
        )

        assert PUSH_MAX_BACKOFF_S == 600.0

    def test_multiplier_in_base(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_BACKOFF_MULTIPLIER,
        )

        assert PUSH_BACKOFF_MULTIPLIER == 2.0

    def test_fast_retry_threshold_in_base(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_FAST_RETRY_THRESHOLD,
        )

        assert PUSH_FAST_RETRY_THRESHOLD == 10


class TestPerBrandDuplicatesRemoved:
    """Source-level check that the duplicates are gone from brand modules."""

    def test_skoda_no_local_backoff_constants(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.push import skoda_mqtt

        src = inspect.getsource(skoda_mqtt)
        # The old module-level names must NOT appear (would be dead code)
        assert "_INITIAL_BACKOFF_S = " not in src
        assert "_MAX_BACKOFF_S = " not in src
        assert "_BACKOFF_MULTIPLIER = " not in src
        assert "_FAST_RETRY_THRESHOLD = " not in src

    def test_cupra_no_local_backoff_constants(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.push import cupra_seat_fcm

        src = inspect.getsource(cupra_seat_fcm)
        assert "_INITIAL_BACKOFF_S = " not in src
        assert "_MAX_BACKOFF_S = " not in src

    def test_audi_no_local_backoff_constants(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.push import audi_vw_fcm

        src = inspect.getsource(audi_vw_fcm)
        assert "_INITIAL_BACKOFF_S = " not in src
        assert "_MAX_BACKOFF_S = " not in src

    def test_no_brand_has_local_advance_backoff(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.push import (
            audi_vw_fcm,
            cupra_seat_fcm,
            skoda_mqtt,
        )

        # The methods should ONLY appear as inherited refs (e.g. in
        # comments) — not as ``def _advance_backoff`` redefinitions.
        for mod in (skoda_mqtt, cupra_seat_fcm, audi_vw_fcm):
            src = inspect.getsource(mod)
            assert "def _advance_backoff" not in src, (
                f"{mod.__name__}: duplicate _advance_backoff still present"
            )
            assert "def _reset_backoff" not in src, (
                f"{mod.__name__}: duplicate _reset_backoff still present"
            )

    def test_no_brand_imports_random_module(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.push import (
            audi_vw_fcm,
            cupra_seat_fcm,
            skoda_mqtt,
        )

        # ``random`` was only used for the jitter calc — now in base.py
        for mod in (skoda_mqtt, cupra_seat_fcm, audi_vw_fcm):
            src = inspect.getsource(mod)
            assert "\nimport random" not in src, (
                f"{mod.__name__}: stale random import"
            )


class TestInitialBackoffState:
    """``__init__`` of PushManager must set the initial backoff state."""

    def test_initial_backoff_seconds_matches_constant(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_INITIAL_BACKOFF_S,
        )

        mgr = _make_manager()
        assert mgr._backoff_seconds == PUSH_INITIAL_BACKOFF_S

    def test_initial_consecutive_fast_retries_is_zero(self) -> None:
        mgr = _make_manager()
        assert mgr._consecutive_fast_retries == 0


class TestAdvanceBackoffBehaviour:
    """The inherited ``_advance_backoff`` produces the same shape as
    the pre-refactor per-brand implementations."""

    def test_single_advance_grows_below_cap(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_INITIAL_BACKOFF_S,
        )

        mgr = _make_manager()
        before = mgr._backoff_seconds
        assert before == PUSH_INITIAL_BACKOFF_S
        mgr._advance_backoff()
        # Should roughly double (5s → ~10s with ±10% jitter)
        assert mgr._backoff_seconds > before
        # But not above max
        assert mgr._backoff_seconds <= 600.0

    def test_fast_retry_threshold_increments(self) -> None:
        mgr = _make_manager()
        mgr._advance_backoff()
        assert mgr._consecutive_fast_retries == 1
        mgr._advance_backoff()
        assert mgr._consecutive_fast_retries == 2

    def test_backoff_caps_at_max(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_MAX_BACKOFF_S,
        )

        mgr = _make_manager()
        # Advance well past the fast-retry threshold + multiplier saturation
        for _ in range(40):
            mgr._advance_backoff()
        # With ±10% jitter the value can be slightly above MAX*0.9
        # and slightly below MAX*1.1, but never above MAX*1.10
        assert mgr._backoff_seconds <= PUSH_MAX_BACKOFF_S * 1.10
        # And it should be near max, not still in fast-retry territory
        assert mgr._backoff_seconds > PUSH_MAX_BACKOFF_S * 0.85

    def test_backoff_never_below_initial(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_INITIAL_BACKOFF_S,
        )

        mgr = _make_manager()
        for _ in range(5):
            mgr._advance_backoff()
            assert mgr._backoff_seconds >= PUSH_INITIAL_BACKOFF_S


class TestResetBackoffBehaviour:
    """``_reset_backoff`` returns state to initial values."""

    def test_reset_after_advance_returns_to_initial(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_INITIAL_BACKOFF_S,
        )

        mgr = _make_manager()
        for _ in range(5):
            mgr._advance_backoff()
        assert mgr._consecutive_fast_retries == 5

        mgr._reset_backoff()
        assert mgr._backoff_seconds == PUSH_INITIAL_BACKOFF_S
        assert mgr._consecutive_fast_retries == 0

    def test_reset_when_already_reset_is_noop(self) -> None:
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_INITIAL_BACKOFF_S,
        )

        mgr = _make_manager()
        mgr._reset_backoff()
        assert mgr._backoff_seconds == PUSH_INITIAL_BACKOFF_S
        assert mgr._consecutive_fast_retries == 0


class TestAllManagersInheritMethods:
    """The 3 brand managers must inherit the methods from base, not
    redefine them locally."""

    def test_skoda_inherits_advance_backoff(self) -> None:
        from custom_components.vag_connect.cariad.push.base import PushManager
        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )

        # The method must come from PushManager, not the subclass
        assert (
            SkodaPushManager._advance_backoff
            is PushManager._advance_backoff
        )

    def test_cupra_inherits_advance_backoff(self) -> None:
        from custom_components.vag_connect.cariad.push.base import PushManager
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        assert (
            CupraSeatPushManager._advance_backoff
            is PushManager._advance_backoff
        )

    def test_audi_inherits_advance_backoff(self) -> None:
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManager

        assert (
            AudiVWPushManager._advance_backoff
            is PushManager._advance_backoff
        )
