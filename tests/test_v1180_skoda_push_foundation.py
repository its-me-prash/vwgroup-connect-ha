# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Tests for v1.18.0 — Skoda mysmob MQTT push foundation.

Foundation phase: class structure, state machine, lifecycle, and
opt-in toggle. Live MQTT activation requires a community tester
(Skoda owner with active Connect subscription) to validate the
TOTP/FCM credential dance against the production broker.

Tests cover:
- PushManagerState enum + transitions (STOPPED → STARTING → CONNECTED → STOPPED)
- Lazy dependency check (graceful UNAVAILABLE if aiomqtt missing)
- Idempotent start() / stop()
- Empty VINs list → no-op
- Backoff state machine (initial / advance / reset / cap / jitter range)
- Coordinator callback wiring + exception isolation
- Const + config_flow option exposure
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) PushManagerState + PushUpdateEvent + abstract PushManager
# ─────────────────────────────────────────────────────────────────────────────


class TestPushBaseTypes:
    def test_push_manager_state_enum_values(self):
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        # Six lifecycle phases
        assert PushManagerState.STOPPED.value == "stopped"
        assert PushManagerState.STARTING.value == "starting"
        assert PushManagerState.CONNECTED.value == "connected"
        assert PushManagerState.RECONNECTING.value == "reconnecting"
        assert PushManagerState.DISABLED.value == "disabled"
        assert PushManagerState.UNAVAILABLE.value == "unavailable"

    def test_push_update_event_is_frozen_dataclass(self):
        from custom_components.vag_connect.cariad.push.base import PushUpdateEvent
        e = PushUpdateEvent(
            vin="TMBJR8NX2RY179915",
            event_type="vehicle-event",
            topic="user/vin/event/topic",
            timestamp="2026-05-04T15:00:00Z",
        )
        assert e.vin == "TMBJR8NX2RY179915"
        assert e.event_type == "vehicle-event"
        assert e.raw_payload is None
        # Frozen → can't mutate
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            e.vin = "X"  # type: ignore[misc]

    def test_push_update_event_with_payload(self):
        from custom_components.vag_connect.cariad.push.base import PushUpdateEvent
        e = PushUpdateEvent(
            vin="V",
            event_type="service-event",
            topic="t",
            timestamp="ts",
            raw_payload={"name": "charging-completed"},
        )
        assert e.raw_payload == {"name": "charging-completed"}


# ─────────────────────────────────────────────────────────────────────────────
# B) SkodaPushManager — state machine + lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_token_provider():
    """Async token provider returning a fixed test token."""
    return AsyncMock(return_value="fake-oauth-token-123")


@pytest.fixture
def mock_callback():
    """Async coordinator callback collecting all events."""
    return AsyncMock()


class TestSkodaPushManagerLifecycle:
    @pytest.mark.asyncio
    async def test_initial_state_is_stopped(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = SkodaPushManager(
            mock_callback,
            user_id="user-uuid-123",
            access_token_provider=mock_token_provider,
            vins=["VIN1234567890ABCDE"],
        )
        assert m.state == PushManagerState.STOPPED

    @pytest.mark.asyncio
    async def test_no_vins_stays_stopped(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = SkodaPushManager(
            mock_callback,
            user_id="user-uuid-123",
            access_token_provider=mock_token_provider,
            vins=[],  # Empty — start should no-op
        )
        await m.start()
        assert m.state == PushManagerState.STOPPED

    @pytest.mark.asyncio
    async def test_missing_aiomqtt_dep_yields_unavailable(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        """If aiomqtt is not installed, start() should set UNAVAILABLE
        and NOT spawn a background task."""
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        from custom_components.vag_connect.cariad.push.base import PushManagerState

        # Force ImportError on aiomqtt by patching importlib
        import importlib
        original_import = importlib.import_module

        def fake_import(name, *args, **kwargs):
            if name in ("aiomqtt", "firebase_messaging"):
                raise ImportError(f"No module named {name!r}")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fake_import)

        m = SkodaPushManager(
            mock_callback,
            user_id="user-uuid-123",
            access_token_provider=mock_token_provider,
            vins=["VIN1234567890ABCDE"],
        )
        await m.start()
        assert m.state == PushManagerState.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_start_then_stop_cleanup(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        """Foundation stub: start() spawns the receive loop; stop()
        cancels cleanly. No real network I/O."""
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        from custom_components.vag_connect.cariad.push.base import PushManagerState

        # Stub the dependency check so foundation stub runs
        m = SkodaPushManager(
            mock_callback,
            user_id="user-uuid-123",
            access_token_provider=mock_token_provider,
            vins=["VIN1234567890ABCDE"],
        )
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)

        await m.start()
        # Give event loop a tick to enter _connect_and_listen
        await asyncio.sleep(0.05)
        assert m.state == PushManagerState.CONNECTED

        await m.stop()
        assert m.state == PushManagerState.STOPPED
        assert m._loop_task is None

    @pytest.mark.asyncio
    async def test_idempotent_start(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        """Calling start() twice should not spawn two tasks."""
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        m = SkodaPushManager(
            mock_callback,
            user_id="user-uuid-123",
            access_token_provider=mock_token_provider,
            vins=["VIN1234567890ABCDE"],
        )
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        await m.start()
        first_task = m._loop_task
        await m.start()  # Second call — should be no-op
        assert m._loop_task is first_task
        await m.stop()

    @pytest.mark.asyncio
    async def test_idempotent_stop(self, mock_callback, mock_token_provider):
        """Calling stop() when already stopped should not raise."""
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        m = SkodaPushManager(
            mock_callback,
            user_id="user-uuid-123",
            access_token_provider=mock_token_provider,
            vins=["VIN1234567890ABCDE"],
        )
        await m.stop()  # Never started
        await m.stop()  # Stop again — still safe


# ─────────────────────────────────────────────────────────────────────────────
# C) Backoff state machine
# ─────────────────────────────────────────────────────────────────────────────


class TestBackoffStateMachine:
    def _new_manager(self):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        from unittest.mock import AsyncMock
        return SkodaPushManager(
            AsyncMock(),
            user_id="x",
            access_token_provider=AsyncMock(return_value="t"),
            vins=["V"],
        )

    def test_initial_backoff_is_5s(self):
        from custom_components.vag_connect.cariad.push.base import PUSH_INITIAL_BACKOFF_S as _INITIAL_BACKOFF_S
        m = self._new_manager()
        assert m._backoff_seconds == _INITIAL_BACKOFF_S
        assert _INITIAL_BACKOFF_S == 5.0

    def test_advance_backoff_grows(self):
        m = self._new_manager()
        initial = m._backoff_seconds
        m._advance_backoff()
        assert m._backoff_seconds > initial

    def test_advance_backoff_capped_at_max(self):
        from custom_components.vag_connect.cariad.push.base import PUSH_MAX_BACKOFF_S as _MAX_BACKOFF_S
        m = self._new_manager()
        # Advance many times
        for _ in range(50):
            m._advance_backoff()
        # Should be at-or-near the cap (jitter ±10% allowed)
        assert m._backoff_seconds <= _MAX_BACKOFF_S * 1.15

    def test_reset_backoff_returns_to_initial(self):
        from custom_components.vag_connect.cariad.push.base import PUSH_INITIAL_BACKOFF_S as _INITIAL_BACKOFF_S
        m = self._new_manager()
        m._advance_backoff()
        m._advance_backoff()
        m._reset_backoff()
        assert m._backoff_seconds == _INITIAL_BACKOFF_S
        assert m._consecutive_fast_retries == 0

    def test_jitter_keeps_backoff_above_initial(self):
        from custom_components.vag_connect.cariad.push.base import PUSH_INITIAL_BACKOFF_S as _INITIAL_BACKOFF_S
        m = self._new_manager()
        # Even with negative jitter, backoff should never drop below initial
        for _ in range(100):
            m._advance_backoff()
            assert m._backoff_seconds >= _INITIAL_BACKOFF_S


# ─────────────────────────────────────────────────────────────────────────────
# D) Event emit + exception isolation
# ─────────────────────────────────────────────────────────────────────────────


class TestEventEmit:
    @pytest.mark.asyncio
    async def test_emit_calls_callback(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        from custom_components.vag_connect.cariad.push.base import PushUpdateEvent
        m = SkodaPushManager(
            mock_callback,
            user_id="x",
            access_token_provider=mock_token_provider,
            vins=["V"],
        )
        e = PushUpdateEvent(
            vin="VIN1234567890ABCDE",
            event_type="service-event",
            topic="t",
            timestamp="ts",
        )
        await m.emit(e)
        mock_callback.assert_awaited_once_with(e)

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_propagate(self, mock_token_provider):
        """A failing coordinator callback must not crash the push loop."""
        from custom_components.vag_connect.cariad.push.skoda_mqtt import SkodaPushManager
        from custom_components.vag_connect.cariad.push.base import PushUpdateEvent
        cb = AsyncMock(side_effect=ValueError("coordinator boom"))
        m = SkodaPushManager(
            cb,
            user_id="x",
            access_token_provider=mock_token_provider,
            vins=["V"],
        )
        # Should not raise
        await m.emit(PushUpdateEvent(
            vin="VIN1234567890ABCDE", event_type="x", topic="t", timestamp="ts",
        ))
        cb.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# E) Const + Config-Flow option exposure
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigFlowOption:
    def test_const_defines_option_key(self):
        from custom_components.vag_connect.const import CONF_ENABLE_PUSH_MQTT
        assert CONF_ENABLE_PUSH_MQTT == "enable_push_mqtt"

    def test_options_flow_includes_push_toggle(self):
        """OptionsFlow schema should include the push-mqtt toggle so
        users can enable it from HA UI."""
        # Smoke test — config_flow.py imports CONF_ENABLE_PUSH_MQTT
        # and uses it in the schema. We verify the import works
        # and the option name is referenced.
        from custom_components.vag_connect import config_flow
        from custom_components.vag_connect.const import CONF_ENABLE_PUSH_MQTT
        # Check the option is exported in the config_flow module's
        # imports (proxy for being used in the schema)
        assert hasattr(config_flow, "CONF_ENABLE_PUSH_MQTT")
        assert config_flow.CONF_ENABLE_PUSH_MQTT == CONF_ENABLE_PUSH_MQTT


# ─────────────────────────────────────────────────────────────────────────────
# F) Package exports
# ─────────────────────────────────────────────────────────────────────────────


class TestPackageExports:
    def test_push_package_exports_base(self):
        from custom_components.vag_connect.cariad.push import (
            PushManager, PushUpdateEvent,
        )
        # Smoke test — both names importable from package root
        assert PushManager is not None
        assert PushUpdateEvent is not None

    def test_skoda_mqtt_module_exports_manager(self):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )
        assert SkodaPushManager is not None
