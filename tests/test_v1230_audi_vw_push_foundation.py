# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.23.0 — Audi/VW Cariad FCM push foundation.

Mirrors v1.18.0 (Skoda MQTT) + v1.19.0 (CUPRA/SEAT FCM) test layout —
AudiVWPushManager shares the abstract PushManager base + identical
lifecycle/state-machine semantics.

User-suggested 2026-05-07: "weil ich auf der app push nachrichten
bekomme, könnte man das doch auch auf der integration als feedback
nehmen?" — myAudi App push notifications surface as HA-side feedback
once Phase 2 wires the receive loop.

Foundation phase: class structure, state machine, lifecycle, opt-in
toggle. Live FCM activation requires a community Audi/VW tester for
Cariad Firebase project + sender_id + notification-subscription
endpoint validation.
"""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_token_provider():
    return AsyncMock(return_value="fake-oauth-token-789")


@pytest.fixture
def mock_callback():
    return AsyncMock()


# ─────────────────────────────────────────────────────────────────────────────
# A) Brand validation
# ─────────────────────────────────────────────────────────────────────────────


class TestBrandValidation:
    def test_audi_or_volkswagen_only(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        for brand in ("audi", "volkswagen"):
            m = AudiVWPushManager(
                mock_callback,
                user_id="u",
                access_token_provider=mock_token_provider,
                vins=["V"],
                brand=brand,
            )
            assert m._brand == brand
        for bad in ("skoda", "cupra", "seat", "porsche", "vw_eu", ""):
            with pytest.raises(ValueError, match="brand must be"):
                AudiVWPushManager(
                    mock_callback,
                    user_id="u",
                    access_token_provider=mock_token_provider,
                    vins=["V"],
                    brand=bad,
                )

    def test_initial_state_is_stopped(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = AudiVWPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="audi",
        )
        assert m.state == PushManagerState.STOPPED


# ─────────────────────────────────────────────────────────────────────────────
# B) Lifecycle
# ─────────────────────────────────────────────────────────────────────────────


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_no_vins_stays_stopped(self, mock_callback, mock_token_provider):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = AudiVWPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=[],
            brand="audi",
        )
        await m.start()
        assert m.state == PushManagerState.STOPPED

    @pytest.mark.asyncio
    async def test_missing_firebase_messaging_yields_unavailable(
        self, mock_callback, mock_token_provider, monkeypatch,
    ):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        original = importlib.import_module
        def fake(name, *a, **k):
            if name == "firebase_messaging":
                raise ImportError("not installed")
            return original(name, *a, **k)
        monkeypatch.setattr(importlib, "import_module", fake)
        m = AudiVWPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="volkswagen",
        )
        await m.start()
        assert m.state == PushManagerState.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_start_then_stop_cleanup(
        self, mock_callback, mock_token_provider, monkeypatch,
    ):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            _FcmCreds,
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManagerState
        m = AudiVWPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="audi",
        )
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        # v2.8.0 Action #4: ``_resolve_fcm_credentials`` raises
        # NotImplementedError until the live APK extraction lands;
        # patch it here so the lifecycle test reaches CONNECTED.
        monkeypatch.setattr(
            m,
            "_resolve_fcm_credentials",
            lambda: _FcmCreds(
                project_id="test-project",
                sender_id="000000",
                api_key="test-api-key",
                app_id="1:000000:android:test",
            ),
        )
        await m.start()
        await asyncio.sleep(0.05)
        assert m.state == PushManagerState.CONNECTED
        await m.stop()
        assert m.state == PushManagerState.STOPPED
        assert m._loop_task is None


# ─────────────────────────────────────────────────────────────────────────────
# C) Backoff
# ─────────────────────────────────────────────────────────────────────────────


class TestBackoff:
    def _new_manager(self, brand="audi"):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        return AudiVWPushManager(
            AsyncMock(),
            user_id="u",
            access_token_provider=AsyncMock(return_value="t"),
            vins=["V"],
            brand=brand,
        )

    def test_backoff_constants_match_other_managers(self):
        """Same backoff bounds as v1.18.0 Skoda + v1.19.0 CUPRA/SEAT
        for behavioural consistency across all 3 push managers."""
        from custom_components.vag_connect.cariad.push.base import (
            PUSH_INITIAL_BACKOFF_S as _INITIAL_BACKOFF_S,
            PUSH_MAX_BACKOFF_S as _MAX_BACKOFF_S,
        )
        assert _INITIAL_BACKOFF_S == 5.0
        assert _MAX_BACKOFF_S == 600.0

    def test_advance_grows_backoff(self):
        m = self._new_manager()
        initial = m._backoff_seconds
        m._advance_backoff()
        assert m._backoff_seconds > initial

    def test_advance_capped(self):
        from custom_components.vag_connect.cariad.push.base import PUSH_MAX_BACKOFF_S as _MAX_BACKOFF_S
        m = self._new_manager()
        for _ in range(50):
            m._advance_backoff()
        assert m._backoff_seconds <= _MAX_BACKOFF_S * 1.15

    def test_reset_to_initial(self):
        from custom_components.vag_connect.cariad.push.base import PUSH_INITIAL_BACKOFF_S as _INITIAL_BACKOFF_S
        m = self._new_manager()
        m._advance_backoff()
        m._reset_backoff()
        assert m._backoff_seconds == _INITIAL_BACKOFF_S
        assert m._consecutive_fast_retries == 0


# ─────────────────────────────────────────────────────────────────────────────
# D) Const + Config-Flow option exposure
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigFlowOption:
    def test_const_defines_option_key(self):
        from custom_components.vag_connect.const import CONF_ENABLE_PUSH_AUDI_VW
        assert CONF_ENABLE_PUSH_AUDI_VW == "enable_push_audi_vw"

    def test_three_push_toggles_coexist(self):
        """All 3 brand-tracks have independent toggles — Skoda MQTT
        (v1.18), CUPRA/SEAT FCM (v1.19), Audi/VW FCM (v1.23). User
        with mixed fleet can opt-in to any combination."""
        from custom_components.vag_connect import config_flow
        for attr in (
            "CONF_ENABLE_PUSH_MQTT",
            "CONF_ENABLE_PUSH_FCM",
            "CONF_ENABLE_PUSH_AUDI_VW",
        ):
            assert hasattr(config_flow, attr), f"missing {attr}"

    def test_three_distinct_option_names(self):
        from custom_components.vag_connect import config_flow
        keys = {
            config_flow.CONF_ENABLE_PUSH_MQTT,
            config_flow.CONF_ENABLE_PUSH_FCM,
            config_flow.CONF_ENABLE_PUSH_AUDI_VW,
        }
        assert len(keys) == 3


# ─────────────────────────────────────────────────────────────────────────────
# E) Inheritance + module exports
# ─────────────────────────────────────────────────────────────────────────────


class TestInheritance:
    def test_extends_pushmanager_base(self):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManager
        assert issubclass(AudiVWPushManager, PushManager)

    def test_all_three_managers_share_base(self):
        """All 3 brand-track managers inherit from PushManager —
        coordinator can hold any of them via type hint
        ``self._push_manager: PushManager | None``."""
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushManager
        for cls in (AudiVWPushManager, CupraSeatPushManager, SkodaPushManager):
            assert issubclass(cls, PushManager)


# ─────────────────────────────────────────────────────────────────────────────
# F) v2.8.0 Action #4: Live activation paths
# ─────────────────────────────────────────────────────────────────────────────


def _make_live_manager(callback, token_provider, monkeypatch):
    """Build a manager with the resolver patched to return live creds."""
    from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
        _FcmCreds,
        AudiVWPushManager,
    )
    m = AudiVWPushManager(
        callback,
        user_id="u",
        access_token_provider=token_provider,
        vins=["WAUTEST123456VIN1"],
        brand="audi",
    )
    monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
    monkeypatch.setattr(
        m,
        "_resolve_fcm_credentials",
        lambda: _FcmCreds(
            project_id="cariad-fcm-test",
            sender_id="000000",
            api_key="test-api-key",
            app_id="1:000000:android:test",
        ),
    )
    return m


class TestLiveSubscriptionSuccess:
    """Subscription success path reaches CONNECTED and resets backoff."""

    @pytest.mark.asyncio
    async def test_resolver_success_reaches_connected(
        self, mock_callback, mock_token_provider, monkeypatch,
    ):
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
            PUSH_INITIAL_BACKOFF_S,
        )
        m = _make_live_manager(
            mock_callback, mock_token_provider, monkeypatch,
        )
        # Pre-dirty the backoff so we can prove ``_reset_backoff`` ran
        # along the success path.
        m._advance_backoff()
        assert m._consecutive_fast_retries == 1
        await m.start()
        await asyncio.sleep(0.05)
        assert m.state == PushManagerState.CONNECTED
        assert m._backoff_seconds == PUSH_INITIAL_BACKOFF_S
        assert m._consecutive_fast_retries == 0
        # Token provider was hit at least once on the success path.
        assert mock_token_provider.await_count >= 1
        await m.stop()


class TestLiveSubscriptionFailureRetry:
    """Empty access token raises; reconnect-loop refreshes token + retries."""

    @pytest.mark.asyncio
    async def test_empty_token_then_refresh_recovers(
        self, mock_callback, monkeypatch,
    ):
        from unittest.mock import AsyncMock

        from custom_components.vag_connect.cariad.push.base import PushManagerState

        # First call returns "" (token refresh just failed), second
        # call returns a real token (refresh succeeded). The outer
        # _run_loop catches the RuntimeError, sleeps the backoff,
        # and re-enters _connect_and_listen.
        token_provider = AsyncMock(side_effect=["", "fresh-token-xyz"])
        m = _make_live_manager(mock_callback, token_provider, monkeypatch)
        # Make the backoff sleep effectively instant so the retry
        # happens inside the test window.
        m._backoff_seconds = 0.01

        await m.start()
        # Give the loop enough wall-clock to run failure -> backoff
        # sleep -> retry -> CONNECTED.
        for _ in range(50):
            await asyncio.sleep(0.02)
            if m.state == PushManagerState.CONNECTED:
                break
        assert m.state == PushManagerState.CONNECTED
        assert token_provider.await_count >= 2
        await m.stop()


class TestEventDecode:
    """``_decode_fcm_payload`` happy path on a synthetic lockState."""

    def test_decodes_lockstate_payload(self):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import PushUpdateEvent

        payload = {
            "data": {
                "vin": "WAUTEST123456VIN1",
                "lockState": "LOCKED",
                "topic": "cariad/lockState/WAUTEST123456VIN1",
                "timestamp": "2026-05-31T12:34:56Z",
            },
        }
        event = AudiVWPushManager._decode_fcm_payload(payload)
        assert isinstance(event, PushUpdateEvent)
        assert event.vin == "WAUTEST123456VIN1"
        assert event.event_type == "lockState"
        assert event.topic == "cariad/lockState/WAUTEST123456VIN1"
        assert event.timestamp == "2026-05-31T12:34:56Z"
        assert event.raw_payload is not None
        assert event.raw_payload["lockState"] == "LOCKED"

    def test_decodes_alarm_payload_with_collapsed_event_type(self):
        """``alarmType`` payload-key collapses to ``alarm`` event_type."""
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        payload = {
            "vin": "WAUTEST123456VIN1",
            "alarmType": "MOTION",
            "timestamp": "2026-05-31T13:00:00Z",
        }
        event = AudiVWPushManager._decode_fcm_payload(payload)
        assert event is not None
        assert event.event_type == "alarm"
        assert event.raw_payload is not None
        assert event.raw_payload["alarmType"] == "MOTION"


class TestEventDecodeMalformed:
    """Malformed payloads return None and never raise."""

    def test_non_dict_returns_none(self, caplog):
        import logging as _logging

        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        caplog.set_level(_logging.DEBUG, logger="custom_components.vag_connect.cariad.push.audi_vw_fcm")
        assert AudiVWPushManager._decode_fcm_payload("not-a-dict") is None
        assert AudiVWPushManager._decode_fcm_payload(None) is None
        assert AudiVWPushManager._decode_fcm_payload(42) is None
        # No exceptions propagated; debug log entries exist for the
        # operator but never warn/error.
        for rec in caplog.records:
            assert rec.levelno <= _logging.DEBUG

    def test_missing_vin_returns_none(self):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        assert (
            AudiVWPushManager._decode_fcm_payload(
                {"lockState": "LOCKED", "timestamp": "2026-05-31T12:00:00Z"},
            )
            is None
        )

    def test_unknown_event_keys_returns_none(self):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        assert (
            AudiVWPushManager._decode_fcm_payload(
                {
                    "vin": "WAUTEST123456VIN1",
                    "somethingElse": "value",
                    "timestamp": "2026-05-31T12:00:00Z",
                },
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_handle_fcm_message_swallows_malformed(self):
        """End-to-end: malformed payload reaches the handler but
        never raises and never calls ``self.emit``."""
        from unittest.mock import AsyncMock

        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        cb = AsyncMock()
        m = AudiVWPushManager(
            cb,
            user_id="u",
            access_token_provider=AsyncMock(return_value="t"),
            vins=["V"],
            brand="volkswagen",
        )
        # Should NOT raise.
        await m._handle_fcm_message("bogus")
        await m._handle_fcm_message({"no": "vin"})
        await m._handle_fcm_message({"vin": "X", "unknownKey": "val"})
        # Callback never fired for any of the malformed messages.
        cb.assert_not_called()
