# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.19.0 — CUPRA/SEAT OLA FCM push foundation.

Mirrors the v1.18.0 Skoda MQTT test layout (test_v1180_skoda_push_foundation.py)
since CupraSeatPushManager and SkodaPushManager share the abstract
PushManager base + identical lifecycle/state-machine semantics.

Foundation phase: class structure, state machine, lifecycle, opt-in
toggle. Live FCM activation requires a community tester (CUPRA/SEAT
owner with active subscription) for FCM project + sender_id +
OLA subscription endpoint validation.
"""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_token_provider():
    return AsyncMock(return_value="fake-oauth-token-456")


@pytest.fixture
def mock_callback():
    return AsyncMock()


# ─────────────────────────────────────────────────────────────────────────────
# A) CupraSeatPushManager — basic structure + brand validation
# ─────────────────────────────────────────────────────────────────────────────


class TestCupraSeatPushManagerConstruction:
    def test_brand_must_be_cupra_or_seat(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        # Valid brands
        for brand in ("cupra", "seat"):
            m = CupraSeatPushManager(
                mock_callback,
                user_id="u",
                access_token_provider=mock_token_provider,
                vins=["V"],
                brand=brand,
            )
            assert m._brand == brand
        # Invalid brand → ValueError
        for bad in ("skoda", "audi", "volkswagen", "porsche", ""):
            with pytest.raises(ValueError, match="brand must be"):
                CupraSeatPushManager(
                    mock_callback,
                    user_id="u",
                    access_token_provider=mock_token_provider,
                    vins=["V"],
                    brand=bad,
                )

    def test_initial_state_is_stopped(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="cupra",
        )
        assert m.state == PushManagerState.STOPPED


# ─────────────────────────────────────────────────────────────────────────────
# B) Lifecycle: start / stop / idempotency
# ─────────────────────────────────────────────────────────────────────────────


class TestCupraSeatPushManagerLifecycle:
    @pytest.mark.asyncio
    async def test_no_vins_stays_stopped(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=[],
            brand="cupra",
        )
        await m.start()
        assert m.state == PushManagerState.STOPPED

    @pytest.mark.asyncio
    async def test_missing_firebase_messaging_yields_unavailable(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState

        original_import = importlib.import_module

        def fake_import(name, *args, **kwargs):
            if name == "firebase_messaging":
                raise ImportError("No module named 'firebase_messaging'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fake_import)

        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="cupra",
        )
        await m.start()
        assert m.state == PushManagerState.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_start_then_stop_cleanup(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="seat",
        )
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        await m.start()
        await asyncio.sleep(0.05)
        assert m.state == PushManagerState.CONNECTED
        await m.stop()
        assert m.state == PushManagerState.STOPPED
        assert m._loop_task is None

    @pytest.mark.asyncio
    async def test_idempotent_start(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="cupra",
        )
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        await m.start()
        first_task = m._loop_task
        await m.start()
        assert m._loop_task is first_task
        await m.stop()

    @pytest.mark.asyncio
    async def test_idempotent_stop(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="cupra",
        )
        await m.stop()
        await m.stop()


# ─────────────────────────────────────────────────────────────────────────────
# C) Backoff state machine (mirrors Skoda MQTT)
# ─────────────────────────────────────────────────────────────────────────────


class TestCupraSeatBackoffStateMachine:
    def _new_manager(self, brand="cupra"):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        return CupraSeatPushManager(
            AsyncMock(),
            user_id="u",
            access_token_provider=AsyncMock(return_value="t"),
            vins=["V"],
            brand=brand,
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
        for _ in range(50):
            m._advance_backoff()
        assert m._backoff_seconds <= _MAX_BACKOFF_S * 1.15

    def test_reset_backoff_returns_to_initial(self):
        from custom_components.vag_connect.cariad.push.base import PUSH_INITIAL_BACKOFF_S as _INITIAL_BACKOFF_S
        m = self._new_manager()
        m._advance_backoff()
        m._advance_backoff()
        m._reset_backoff()
        assert m._backoff_seconds == _INITIAL_BACKOFF_S
        assert m._consecutive_fast_retries == 0


# ─────────────────────────────────────────────────────────────────────────────
# D) Event emit + exception isolation (inherited from base PushManager)
# ─────────────────────────────────────────────────────────────────────────────


class TestEventEmitInheritance:
    @pytest.mark.asyncio
    async def test_emit_calls_callback(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushUpdateEvent
        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="cupra",
        )
        e = PushUpdateEvent(
            vin="VINSEATTEST123456",
            event_type="charging-completed",
            topic="ola-fcm",
            timestamp="2026-05-04T15:00:00Z",
        )
        await m.emit(e)
        mock_callback.assert_awaited_once_with(e)

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_propagate(self, mock_token_provider):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushUpdateEvent
        cb = AsyncMock(side_effect=ValueError("ola boom"))
        m = CupraSeatPushManager(
            cb,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="seat",
        )
        await m.emit(PushUpdateEvent(
            vin="V", event_type="x", topic="t", timestamp="ts",
        ))
        cb.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# E) Const + Config-Flow option exposure
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigFlowOption:
    def test_const_defines_option_key(self):
        from custom_components.vag_connect.const import CONF_ENABLE_PUSH_FCM
        assert CONF_ENABLE_PUSH_FCM == "enable_push_fcm"

    def test_options_flow_includes_fcm_toggle(self):
        from custom_components.vag_connect import config_flow
        from custom_components.vag_connect.const import CONF_ENABLE_PUSH_FCM
        assert hasattr(config_flow, "CONF_ENABLE_PUSH_FCM")
        assert config_flow.CONF_ENABLE_PUSH_FCM == CONF_ENABLE_PUSH_FCM

    def test_two_push_toggles_coexist(self):
        """Both v1.18.0 MQTT toggle and v1.19.0 FCM toggle should
        exist independently in OptionsFlow — user can opt into one,
        the other, both, or neither depending on their fleet."""
        from custom_components.vag_connect import config_flow
        assert hasattr(config_flow, "CONF_ENABLE_PUSH_MQTT")
        assert hasattr(config_flow, "CONF_ENABLE_PUSH_FCM")
        # Two distinct option names
        assert config_flow.CONF_ENABLE_PUSH_MQTT != config_flow.CONF_ENABLE_PUSH_FCM


# ─────────────────────────────────────────────────────────────────────────────
# F) Module exports
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleExports:
    def test_cupra_seat_fcm_exports_manager(self):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        assert CupraSeatPushManager is not None

    def test_both_managers_share_pushmanager_base(self):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManager
        assert issubclass(CupraSeatPushManager, PushManager)
        assert issubclass(SkodaPushManager, PushManager)
