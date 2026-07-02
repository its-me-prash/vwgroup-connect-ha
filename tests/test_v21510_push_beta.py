# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.10 — real push BETA activation, fully mocked (no network).

The v1.18.0 / v1.19.0 / v1.23.0 foundation tests cover the state
machine + lifecycle with ``_connect_and_listen`` patched out. This
file exercises the REAL connect path now that it's wired, with the
network deps mocked so nothing touches a broker or Firebase:

  * ``firebase_messaging.FcmPushClient`` / ``FcmRegisterConfig`` are
    replaced with fakes whose ``checkin_or_register`` returns a canned
    token and whose ``start`` / ``stop`` are no-ops.
  * ``aiomqtt.Client`` (Skoda) is replaced with a fake async-context
    client exposing ``subscribe`` + an empty ``messages`` async iterator.
  * the subscription-POST seam ``_http_post_subscription`` /
    ``_post_cariad_subscription`` is captured so we can assert the
    EXACT body shipped per brand without an aiohttp session.

Coverage per the v2.15.10 task:
  (a) ``_resolve_fcm_credentials`` returns the correct per-brand creds
  (b) the connect path builds the right subscription body per brand
  (c) ``_decode_*`` maps a sample payload to a ``PushUpdateEvent``
  (d) the circuit-breaker trips after 3 consecutive connect failures

No live car / broker / Firebase project is contacted.
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_token_provider():
    return AsyncMock(return_value="fake-oauth-token-789")


@pytest.fixture
def mock_callback():
    return AsyncMock()


# ─────────────────────────────────────────────────────────────────────────────
# Fake network deps injected via sys.modules so the lazy imports inside
# ``_connect_and_listen`` resolve to no-network doubles.
# ─────────────────────────────────────────────────────────────────────────────


class _FakeFcmClient:
    """Stand-in for ``firebase_messaging.FcmPushClient``.

    Records the positional ctor args so a test can assert the config the
    manager built, exposes the async register/start/stop the manager
    awaits, and lets a test push a notification through the stored
    callback to exercise the decode path.
    """

    instances: list["_FakeFcmClient"] = []

    def __init__(self, callback, config, creds, creds_cb):  # noqa: ANN001
        self.callback = callback
        self.config = config
        self.creds = creds
        self.creds_cb = creds_cb
        self.started = False
        self.stopped = False
        _FakeFcmClient.instances.append(self)

    async def checkin_or_register(self):  # noqa: ANN201
        return "FAKE-FCM-TOKEN-abc123"

    async def start(self):  # noqa: ANN201
        self.started = True

    async def stop(self):  # noqa: ANN201
        self.stopped = True


class _FakeFcmRegisterConfig:
    """Stand-in for ``firebase_messaging.FcmRegisterConfig`` — captures
    the exact positional args (project_id, app_id, api_key, sender_id)."""

    def __init__(self, project_id, app_id, api_key, sender_id):  # noqa: ANN001
        self.project_id = project_id
        self.app_id = app_id
        self.api_key = api_key
        self.sender_id = sender_id


@pytest.fixture
def fake_firebase(monkeypatch):
    """Inject a fake ``firebase_messaging`` module + reset instances."""
    _FakeFcmClient.instances = []
    mod = types.ModuleType("firebase_messaging")
    mod.FcmPushClient = _FakeFcmClient
    mod.FcmRegisterConfig = _FakeFcmRegisterConfig
    monkeypatch.setitem(sys.modules, "firebase_messaging", mod)
    return mod


# ═════════════════════════════════════════════════════════════════════════════
# (a) Per-brand credential resolution
# ═════════════════════════════════════════════════════════════════════════════


class TestResolverPerBrand:
    def test_audi_vs_volkswagen_are_separate_projects(
        self, mock_callback, mock_token_provider
    ):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        audi = AudiVWPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="audi",
        )._resolve_fcm_credentials()
        vw = AudiVWPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
            brand="volkswagen",
        )._resolve_fcm_credentials()

        # Verified against the raw APKs — SEPARATE Firebase projects.
        assert audi.project_id == "onetouch-169db"
        assert audi.sender_id == "254788998682"
        assert audi.api_key == "AIzaSyBVo1tiqGH1g2BOaOEvPS3XcWvoQrvMkBY"
        assert audi.app_id == "1:254788998682:android:fec5c470993c39fe"

        assert vw.project_id == "gcp-project-we-connect-id"
        assert vw.sender_id == "992914193347"
        assert vw.api_key == "AIzaSyDC9d-LOI0LLK-9p0zhDNT2tJPYTjk5c2E"
        assert vw.app_id == "1:992914193347:android:c08d27281d231559bddb76"

        # Must NOT be the same project (regression guard against a
        # single-shared-project resolver).
        assert audi.project_id != vw.project_id
        assert audi.sender_id != vw.sender_id

    def test_cupra_vs_seat_shared_project_per_brand_app_id(self):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            _FCM_API_KEY,
            _FCM_APP_ID,
            _FCM_PROJECT_ID,
            _FCM_SENDER_ID,
        )

        # SHARED Firebase project, per-brand app_id.
        assert _FCM_PROJECT_ID == "ola-apps-prod"
        assert _FCM_SENDER_ID == "530284123617"
        assert _FCM_API_KEY == "AIzaSyCoSp1zitklb1EDj5yQumN0VNhDizJQHLk"
        assert _FCM_APP_ID["cupra"] == "1:530284123617:android:9b9ba5a87c7ffd37fbeea0"
        assert _FCM_APP_ID["seat"] == "1:530284123617:android:d6187613ac3d7b08fbeea0"
        assert _FCM_APP_ID["cupra"] != _FCM_APP_ID["seat"]

    def test_skoda_creds(self):
        from custom_components.vag_connect.cariad.push import skoda_mqtt as sk

        assert sk._FCM_PROJECT_ID == "678067506455"
        assert sk._FCM_SENDER_ID == "678067506455"
        assert sk._FCM_API_KEY == "AIzaSyBlJdDfVR6ltRhKpA87F3SmCe2hHqhyEd8"
        assert sk._FCM_APP_ID == "1:678067506455:android:4afca86c91d6d4c235bb52"


# ═════════════════════════════════════════════════════════════════════════════
# (b) Connect path builds the correct per-brand subscription body
# ═════════════════════════════════════════════════════════════════════════════


class TestSubscriptionBodyCupraSeat:
    @pytest.mark.asyncio
    async def test_ola_body_shape_per_vin(
        self, fake_firebase, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
            _FCM_APP_ID,
            _OLA_BASE,
            _SUBSCRIPTIONS_PATH,
        )
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        posts: list[tuple[str, dict, str]] = []

        async def fake_post(url, body, access_token):  # noqa: ANN001
            posts.append((url, body, access_token))

        m = CupraSeatPushManager(
            mock_callback,
            user_id="ola-user-uuid",
            access_token_provider=mock_token_provider,
            vins=["VINCUPRA0000001", "VINCUPRA0000002"],
            brand="cupra",
        )
        monkeypatch.setattr(m, "_http_post_subscription", fake_post)
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)

        await m.start()
        # Let the loop reach CONNECTED (register + subscribe + start()).
        for _ in range(50):
            if m.state == PushManagerState.CONNECTED:
                break
            await asyncio.sleep(0.01)
        assert m.state == PushManagerState.CONNECTED

        # One POST per VIN (per-VIN, not bulk — GROUNDED pycupra).
        assert len(posts) == 2
        url, body, token = posts[0]
        assert url == f"{_OLA_BASE}{_SUBSCRIPTIONS_PATH}"
        assert token == "fake-oauth-token-789"
        # GROUNDED body shape (pycupra connection.py::subscribe).
        assert body == {
            "deviceId": _FCM_APP_ID["cupra"],
            "locale": "en_GB",
            "services": {"charging": True, "climatisation": True},
            "token": "FAKE-FCM-TOKEN-abc123",
            "userId": "ola-user-uuid",
            "vin": "VINCUPRA0000001",
        }
        # deviceId is the GCM app_id, NOT the FCM token — distinct values.
        assert body["deviceId"] != body["token"]
        # No windowHeating flag (drop-per-GROUND-B).
        assert "windowHeating" not in body["services"]

        # Config the manager built for the FCM register.
        cfg = fake_firebase.FcmRegisterConfig
        inst = _FakeFcmClient.instances[-1]
        assert isinstance(inst.config, cfg)
        assert inst.config.project_id == "ola-apps-prod"
        assert inst.config.app_id == _FCM_APP_ID["cupra"]

        await m.stop()
        assert m.state == PushManagerState.STOPPED

    @pytest.mark.asyncio
    async def test_seat_uses_seat_app_id(
        self, fake_firebase, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
            _FCM_APP_ID,
        )
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        posts: list[dict] = []

        async def fake_post(url, body, access_token):  # noqa: ANN001
            posts.append(body)

        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["VINSEAT00000001"],
            brand="seat",
        )
        monkeypatch.setattr(m, "_http_post_subscription", fake_post)
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        await m.start()
        for _ in range(50):
            if m.state == PushManagerState.CONNECTED:
                break
            await asyncio.sleep(0.01)
        assert m.state == PushManagerState.CONNECTED
        assert posts[0]["deviceId"] == _FCM_APP_ID["seat"]
        await m.stop()


class TestSubscriptionBodyAudiVW:
    @pytest.mark.asyncio
    async def test_gated_body_shape_and_warning(
        self, fake_firebase, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
            _SUBSCRIPTION_BASE,
            _SUBSCRIPTION_PATH,
            _BRAND_FCM,
        )
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        posts: list[tuple[str, dict, str]] = []

        async def fake_post(url, body, access_token):  # noqa: ANN001
            posts.append((url, body, access_token))

        m = AudiVWPushManager(
            mock_callback,
            user_id="cariad-user-uuid",
            access_token_provider=mock_token_provider,
            vins=["WAUZZZAUDI00001"],
            brand="audi",
        )
        # Patch the low-level HTTP seam so the GATED warning + body-build
        # in _post_cariad_subscription still run (that's what we assert).
        monkeypatch.setattr(m, "_http_post_subscription", fake_post)
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        await m.start()
        for _ in range(50):
            if m.state == PushManagerState.CONNECTED:
                break
            await asyncio.sleep(0.01)
        assert m.state == PushManagerState.CONNECTED

        assert len(posts) == 1
        url, body, token = posts[0]
        # GATED placeholder host/path (pycupra OLA shape — UNVERIFIED).
        assert url == f"{_SUBSCRIPTION_BASE}{_SUBSCRIPTION_PATH}"
        assert body == {
            "deviceId": _BRAND_FCM["audi"].app_id,
            "locale": "en_GB",
            "services": {"charging": True, "climatisation": True},
            "token": "FAKE-FCM-TOKEN-abc123",
            "userId": "cariad-user-uuid",
            "vin": "WAUZZZAUDI00001",
        }
        # One-time GATED warning latch was set.
        assert m._subscription_warned is True
        await m.stop()


class TestSkodaConnectPath:
    @pytest.mark.asyncio
    async def test_mqtt_connect_subscribes_per_vin_with_totp_properties(
        self, fake_firebase, mock_callback, mock_token_provider, monkeypatch
    ):
        """Skoda: fake aiomqtt.Client + paho Properties; assert the
        MQTTv5 CONNECT UserProperties carry totp_v1 and per-VIN ``#``
        subscribe topics are issued."""
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        subscribed: list[str] = []

        class _FakeMessages:
            def __aiter__(self):
                return self

            async def __anext__(self):
                # Block until cancelled — no messages in this test.
                await asyncio.sleep(3600)
                raise StopAsyncIteration

        class _FakeMqttClient:
            last: "_FakeMqttClient | None" = None

            def __init__(self, **kwargs):  # noqa: ANN003
                self.kwargs = kwargs
                self.messages = _FakeMessages()
                _FakeMqttClient.last = self

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):  # noqa: ANN002
                return False

            async def subscribe(self, topic):  # noqa: ANN001
                subscribed.append(topic)

        class _ProtoVer:
            V5 = "V5"

        aiomqtt_mod = types.ModuleType("aiomqtt")
        aiomqtt_mod.Client = _FakeMqttClient
        aiomqtt_mod.ProtocolVersion = _ProtoVer
        monkeypatch.setitem(sys.modules, "aiomqtt", aiomqtt_mod)

        # Fake paho packettypes + properties.
        paho = types.ModuleType("paho")
        paho_mqtt = types.ModuleType("paho.mqtt")
        pkt = types.ModuleType("paho.mqtt.packettypes")

        class _PacketTypes:
            CONNECT = 1

        pkt.PacketTypes = _PacketTypes
        props_mod = types.ModuleType("paho.mqtt.properties")

        class _Properties:
            def __init__(self, ptype):  # noqa: ANN001
                self.ptype = ptype
                self.UserProperty = None

        props_mod.Properties = _Properties
        monkeypatch.setitem(sys.modules, "paho", paho)
        monkeypatch.setitem(sys.modules, "paho.mqtt", paho_mqtt)
        monkeypatch.setitem(sys.modules, "paho.mqtt.packettypes", pkt)
        monkeypatch.setitem(sys.modules, "paho.mqtt.properties", props_mod)

        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )

        m = SkodaPushManager(
            mock_callback,
            user_id="skoda-user",
            access_token_provider=mock_token_provider,
            vins=["TMBSKODA0000001", "TMBSKODA0000002"],
        )
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        # Avoid real TLS context construction in the sandbox.
        monkeypatch.setattr(m, "_build_ssl_context", lambda: object())

        await m.start()
        for _ in range(50):
            if m.state == PushManagerState.CONNECTED:
                break
            await asyncio.sleep(0.01)
        assert m.state == PushManagerState.CONNECTED

        # Catch-all ``#`` subscribe per VIN.
        assert subscribed == [
            "skoda-user/TMBSKODA0000001/#",
            "skoda-user/TMBSKODA0000002/#",
        ]
        # MQTTv5 + TOTP UserProperties present on the CONNECT properties.
        cli = _FakeMqttClient.last
        assert cli is not None
        assert cli.kwargs["protocol"] == "V5"
        assert cli.kwargs["username"] == "skoda-user"
        assert cli.kwargs["password"] == "fake-oauth-token-789"
        props = cli.kwargs["properties"]
        assert ("auth_method", "totp_v1") in props.UserProperty
        # The TOTP value is a 6-digit string keyed on the FCM token.
        auth_cred = dict(props.UserProperty)["auth_credentials"]
        assert auth_cred.isdigit() and len(auth_cred) == 6

        await m.stop()
        assert m.state == PushManagerState.STOPPED

    def test_generate_totp_verbatim_myskoda(self):
        """``_generate_totp`` matches the myskoda reference algorithm
        (HMAC-SHA256 keyed by SHA-256 of the FCM token, 6-digit HOTP)."""
        import hashlib
        import hmac
        import struct
        import time

        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )

        token = "some-fcm-token"
        got = SkodaPushManager._generate_totp(token)

        key = hashlib.sha256(token.encode("utf-8")).digest()
        time_step = struct.pack(">Q", int(time.time()) // 30)
        mac = hmac.new(key, time_step, hashlib.sha256).digest()
        offset = mac[-1] & 0x0F
        code = (
            ((mac[offset] & 0x7F) << 24)
            | ((mac[offset + 1] & 0xFF) << 16)
            | ((mac[offset + 2] & 0xFF) << 8)
            | (mac[offset + 3] & 0xFF)
        )
        expected = str(code % (10**6)).zfill(6)
        assert got == expected
        assert got.isdigit() and len(got) == 6


# ═════════════════════════════════════════════════════════════════════════════
# (c) Decode maps a sample payload to a PushUpdateEvent
# ═════════════════════════════════════════════════════════════════════════════


class TestDecode:
    def test_cupra_seat_decode_type_discriminator(self):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        # GROUNDED shape (pycupra vehicle.py::onNotification): nested
        # under ``data`` with a kebab-case ``type`` + optional requestId
        # + JSON-string ``payload``. No vin in data → subscription vin.
        raw = {
            "data": {
                "type": "charging-status-changed",
                "requestId": "req-42",
                "payload": '{"description":{"values":["zoneA"]}}',
            }
        }
        ev = CupraSeatPushManager._decode_fcm_payload(
            raw, default_vin="VINCUPRA0000001"
        )
        assert ev is not None
        assert ev.vin == "VINCUPRA0000001"
        assert ev.event_type == "charging-status-changed"
        assert ev.raw_payload["requestId"] == "req-42"
        # payload JSON-string parsed to a dict.
        assert ev.raw_payload["payload"] == {
            "description": {"values": ["zoneA"]}
        }

    def test_cupra_seat_decode_no_type_dropped(self):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        assert (
            CupraSeatPushManager._decode_fcm_payload(
                {"data": {"foo": "bar"}}, default_vin="V"
            )
            is None
        )

    def test_cupra_seat_decode_no_vin_dropped(self):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        # type present but no subscription vin and none in payload → drop.
        assert (
            CupraSeatPushManager._decode_fcm_payload(
                {"data": {"type": "charging-status-changed"}},
                default_vin=None,
            )
            is None
        )

    def test_audi_vw_decode_type_discriminator(self):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        raw = {"data": {"type": "vehicle-access-locked-successful"}}
        ev = AudiVWPushManager._decode_fcm_payload(
            raw, default_vin="WAUZZZAUDI00001"
        )
        assert ev is not None
        assert ev.vin == "WAUZZZAUDI00001"
        assert ev.event_type == "vehicle-access-locked-successful"

    def test_audi_vw_decode_legacy_statekey_fallback(self):
        from custom_components.vag_connect.cariad.push.audi_vw_fcm import (
            AudiVWPushManager,
        )

        # Legacy state-key shape still tolerated with in-payload vin.
        raw = {"lockState": "locked", "vin": "WAUZZZAUDI00001"}
        ev = AudiVWPushManager._decode_fcm_payload(raw)
        assert ev is not None
        assert ev.event_type == "lockState"
        assert ev.vin == "WAUZZZAUDI00001"

    def test_skoda_decode_topic_split(self):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )

        # GROUNDED: topic.split("/", maxsplit=3); tail absorbs the
        # two-level ``vehicle-status/odometer`` service topic.
        topic = "user-uuid/TMBSKODA0000001/service-event/vehicle-status/odometer"
        payload = (
            b'{"name":"charging-status-changed","timestamp":'
            b'"2024-11-09T13:30:34Z","data":{"vin":"TMBSKODA0000001"}}'
        )
        ev = SkodaPushManager._decode_mqtt_message(topic, payload)
        assert ev is not None
        assert ev.vin == "TMBSKODA0000001"
        assert ev.event_type == "service-event"
        assert ev.topic == "service-event/vehicle-status/odometer"

    def test_skoda_decode_empty_payload_dropped(self):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )

        assert (
            SkodaPushManager._decode_mqtt_message(
                "u/V/service-event/charging", b""
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_fcm_notification_bridge_emits(
        self, mock_callback, mock_token_provider
    ):
        """The SYNC firebase callback bridge schedules the async decode
        + emit on the captured loop, producing a coordinator event."""
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )

        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["VINCUPRA0000001"],
            brand="cupra",
        )
        m._loop = asyncio.get_running_loop()
        m._on_fcm_notification(
            {"data": {"type": "charging-status-changed"}}
        )
        # Let the scheduled task run.
        await asyncio.sleep(0.05)
        assert mock_callback.await_count == 1
        event = mock_callback.await_args.args[0]
        assert event.event_type == "charging-status-changed"
        assert event.vin == "VINCUPRA0000001"


# ═════════════════════════════════════════════════════════════════════════════
# (d) Circuit-breaker trips on repeated connect failure
# ═════════════════════════════════════════════════════════════════════════════


class TestCircuitBreakerTripsOnConnectFailure:
    @pytest.mark.asyncio
    async def test_cupra_seat_breaker_trips_after_three_failures(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.cupra_seat_fcm import (
            CupraSeatPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        m = CupraSeatPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["VINCUPRA0000001"],
            brand="cupra",
        )
        monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
        # Accelerate backoff so 3 failures happen fast.
        m._backoff_seconds = 0.01
        monkeypatch.setattr(m, "_advance_backoff", lambda: None)

        async def boom():
            raise RuntimeError("simulated connect failure")

        monkeypatch.setattr(m, "_connect_and_listen", boom)

        await m.start()
        # Wait for the breaker to trip (3 strikes) or the loop to exit.
        for _ in range(200):
            if m.is_tripped or (
                m._loop_task is not None and m._loop_task.done()
            ):
                break
            await asyncio.sleep(0.01)
        assert m.strike_count >= 3
        assert m.state == PushManagerState.TRIPPED
        await m.stop()

    @pytest.mark.asyncio
    async def test_tripped_start_short_circuits(
        self, mock_callback, mock_token_provider, monkeypatch
    ):
        from custom_components.vag_connect.cariad.push.skoda_mqtt import (
            SkodaPushManager,
        )
        from custom_components.vag_connect.cariad.push.base import (
            PushManagerState,
        )

        m = SkodaPushManager(
            mock_callback,
            user_id="u",
            access_token_provider=mock_token_provider,
            vins=["V"],
        )
        # Force the tripped state directly.
        m._state = PushManagerState.TRIPPED
        from datetime import datetime, timezone

        m._tripped_at = datetime.now(tz=timezone.utc)
        await m.start()
        # start() must decline (no loop task spawned).
        assert m._loop_task is None
