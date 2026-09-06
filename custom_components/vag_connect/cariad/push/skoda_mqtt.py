# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ╔════════════════════════════════════════════════════════════════════╗
# ║ BETA — opt-in, live-test-gated (v2.15.10)                         ║
# ║ Real aiomqtt MQTTv5 connect + FCM-derived TOTP auth + subscribe + ║
# ║ decode is wired (grounded in skodaconnect/myskoda). Live-test gate:║
# ║ needs a Skoda Connect owner to confirm the broker still accepts   ║
# ║ the totp_v1 scheme + FCM project 678067506455 at deploy time      ║
# ║ (Cariad rotates). Fail-soft: wrong creds/timeout trip the breaker.║
# ╚════════════════════════════════════════════════════════════════════╝
"""Skoda mysmob MQTT push manager (BETA).

Subscribes to ``mqtt.messagehub.de:8883`` (TLS, MQTTv5) for the user's
``{user_id}/{vin}/+/+`` topic pattern. Each backend event triggers a
coordinator-side ``get_status`` refresh so HA gets near-real-time
state changes without 12V wake-cycle polling.

### Architecture

Three coupled pieces:

1. **MQTT client** (``aiomqtt``) — async MQTTv5 connection with
   TLS, exponential reconnect backoff, and TOTP-derived auth.

2. **TOTP credential** — Skoda's MQTT broker requires a TOTP HOTP
   value derived from a Firebase Cloud Messaging token registered
   against ``cz.skodaauto.myskoda``. The FCM token is obtained via
   ``firebase-messaging`` at startup and held in memory only — there
   is NO persistence, so every restart registers a fresh token.
   (An earlier version of this docstring claimed the token was
   "persisted across restarts via HA's ``Store`` helper". There is no
   Store anywhere in this package; the claim was false.)

   v3.2.2 — a Škoda tester's log finally pinned the real failure: the
   registration was hitting Firebase with the wrong ``project_id`` (the
   sender/project *number* ``678067506455`` instead of the project SLUG
   ``myskoda-ng``), so ``firebase-messaging`` built
   ``.../projects/678067506455/installations`` and every attempt died with
   "Unable to register with fcm". ``firebase-messaging`` 0.4.x already uses
   the ``c2dm/register3`` endpoint (so the earlier "myskoda abandoned this
   path in #584, tokens can't be minted" note was a misdiagnosis — the four
   google-services values match the live 8.15.0 APK verbatim; only our
   project_id was the number, not the slug). Fixed by using the slug.
   STILL LIVE-GATED: pending a tester confirming the broker accepts the
   resulting token end-to-end. Intermittent GCM check-in failures
   ("Unable to establish subscription with Google Cloud Messaging") can
   still occur under Google's registration rate-limit when the breaker
   retries fast; once one registration succeeds the token is cached for the
   session, so that pressure clears itself.

3. **Coordinator callback** — each MQTT message is decoded into a
   ``PushUpdateEvent`` and forwarded to the coordinator via the
   ``on_event`` callback. The coordinator decides what to refresh
   (typically a single ``get_status`` for the affected VIN).

### BETA status (v2.15.10)

Real connect path is wired, grounded verbatim in
``skodaconnect/myskoda`` ``mqtt.py`` + ``const.py`` +
``models/event/base.py``:

- ``aiomqtt.Client`` MQTTv5, TLS, ``identifier`` = two UUIDs joined
  by ``#``, ``keepalive=60``.
- Auth: paho ``username_pw_set(user_id, oauth_access_token)`` +
  MQTTv5 CONNECT ``UserProperty`` = ``auth_method=totp_v1`` +
  ``auth_credentials=<TOTP>`` where TOTP is HOTP-SHA256 keyed by the
  SHA-256 of the FCM token (``_generate_totp`` verbatim). We pass a
  fresh ``Properties(PacketTypes.CONNECT)`` via the aiomqtt
  ``properties=`` constructor kwarg (public API, ``aiomqtt>=2.0``) —
  built fresh per connect so the TOTP is current.
- Catch-all subscribe ``{user_id}/{vin}/#`` per VIN (covers the
  two-level ``service-event/vehicle-status/odometer`` topics that a
  ``+/+`` filter would miss).
- Decode: ``topic.split("/", maxsplit=3)`` -> vin + category,
  ``json.loads(payload)`` -> ``PushUpdateEvent`` (any event triggers
  a coordinator refresh).

Live-test gate (needs a Skoda Connect owner): confirm the broker
still accepts the ``totp_v1`` scheme + FCM project ``678067506455``
at deploy time (Cariad rotates), and that FCM registration via
``firebase-messaging`` yields a broker-accepted token.

### References

- skodaconnect/myskoda PR #566 (TOTP auth flow)
- skodaconnect/myskoda const.py (broker URL, topic patterns)
- evcc-io/evcc — does NOT implement push (cross-checked, validates
  this is a real differentiator)

### Privacy

- VINs masked to last 6 chars in logs
- user_id masked the same way
- OAuth tokens, FCM tokens, TOTP credentials: NEVER logged
- TLS verifies broker cert — no plaintext leak
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import struct
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .base import (
    PushManager,
    PushManagerState,
    PushEventCallback,
    PushUpdateEvent,
)

_LOGGER = logging.getLogger(__name__)

# Skoda mysmob MQTT broker (verified from myskoda const.py).
_BROKER_HOST = "mqtt.messagehub.de"
_BROKER_PORT = 8883
_MQTT_KEEPALIVE = 60

# Firebase project for the Skoda app's FCM registration — the four
# ``google-services`` values, verified verbatim against the raw MySkoda
# 8.15.0 APK (res/values/strings.xml). Public config, no secrets.
#
# v3.2.2 FIX: ``project_id`` is the Firebase project SLUG ``myskoda-ng``,
# NOT the sender/project *number* 678067506455. ``firebase-messaging`` keys
# the FCM installation + registration URLs on it
# (``.../projects/{project_id}/installations``), so the old numeric value
# made every FCM registration 404 → "Unable to register with fcm", which is
# exactly what a Škoda tester's log showed. The number is the sender id; the
# slug is the project id — they are different fields and were conflated here.
_FCM_PROJECT_ID = "myskoda-ng"
_FCM_SENDER_ID = "678067506455"
_FCM_API_KEY = "AIzaSyBlJdDfVR6ltRhKpA87F3SmCe2hHqhyEd8"
_FCM_APP_ID = "1:678067506455:android:4afca86c91d6d4c235bb52"
_FCM_PACKAGE = "cz.skodaauto.myskoda"

# v2.2.0 Phase 5a PR #18/20: backoff constants moved to ``base.py``
# (``PUSH_INITIAL_BACKOFF_S`` etc.). Shared across all push managers
# so a single tuning change propagates to all brands.


class SkodaPushManager(PushManager):
    """Skoda mysmob MQTT push manager.

    Lifecycle:

    1. ``start()`` — lazy-imports aiomqtt + firebase-messaging,
       registers FCM if not yet done, derives TOTP, opens MQTT
       connection, subscribes to topic, spawns receive loop
    2. Background loop reads messages, parses into PushUpdateEvent,
       calls ``self.emit()`` (coordinator callback)
    3. On disconnect: backoff + reconnect (refreshes OAuth token first)
    4. ``stop()`` — cancels loop, closes MQTT, releases resources

    Idempotent ``start()`` and ``stop()`` calls. The receive loop is
    a single asyncio task stored at ``self._loop_task``.
    """

    def __init__(
        self,
        on_event: PushEventCallback,
        *,
        user_id: str,
        access_token_provider: Any,
        vins: list[str],
    ) -> None:
        """Initialise.

        Args:
            on_event: Coordinator callback that receives each event.
            user_id: The OAuth user-id (used as MQTT username + topic
                prefix). UUID format.
            access_token_provider: A coroutine function that returns
                a fresh OAuth access token. Called before every
                connect/reconnect to ensure the broker auth is valid.
                Signature: ``async def () -> str``.
            vins: List of VINs to subscribe to. Each gets its own
                ``{user_id}/{vin}/+/+`` topic subscription.
        """
        super().__init__(on_event)
        self._user_id = user_id
        self._access_token_provider = access_token_provider
        self._vins = list(vins)
        self._loop_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        # FCM client + in-memory creds (the FCM token is the TOTP secret
        # material — NEVER logged). Registered lazily on connect; not
        # persisted, so a restart re-registers.
        self._fcm_client: Any = None
        self._fcm_credentials: dict[str, Any] | None = None
        self._fcm_token: str | None = None
        # v2.2.0 Phase 5a PR #18/20: backoff state moved to PushManager
        # base ``__init__`` (set by ``super().__init__(on_event)`` above).

    async def start(self) -> None:
        """Spawn the MQTT receive loop. Idempotent.

        v2.2.0 PR #12/20: respects the circuit-breaker. If the breaker
        is tripped (3 consecutive start failures), returns immediately
        without retrying. Caller can poll ``state`` for the TRIPPED
        signal and surface it via Repair-Issue.
        """
        if self._state in (PushManagerState.CONNECTED, PushManagerState.STARTING):
            return
        # v2.2.0 PR #12/20 — short-circuit if breaker tripped.
        # Reading ``self.state`` (not ``self._state``) honours the
        # auto-reset transition baked into the property getter.
        if self.state == PushManagerState.TRIPPED:
            _LOGGER.warning(
                "Skoda push: circuit-breaker TRIPPED — declining start. "
                "Wait for auto-reset (1h) or call reset_circuit_breaker().",
            )
            return
        if not self._vins:
            _LOGGER.info(
                "Skoda push: no VINs to subscribe to — staying STOPPED",
            )
            return
        self._state = PushManagerState.STARTING
        self._stop_event.clear()
        # Lazy import — only attempted when user opts in. If the deps
        # aren't installed, surface UNAVAILABLE so coordinator can
        # decide on user notification.
        try:
            self._lazy_check_dependencies()
        except ImportError as err:
            _LOGGER.warning(
                "Skoda push: required dependency missing — %s. "
                "Run `pip install aiomqtt firebase-messaging` in your "
                "HA env or disable the push option. Falling back to "
                "polling.",
                err,
            )
            self._state = PushManagerState.UNAVAILABLE
            # v2.2.0 PR #12/20: missing deps count as a strike. After
            # 3 attempts to start without the deps being installed, the
            # breaker trips and we stop spamming the log on each
            # coordinator-start retry.
            self._record_failure(f"missing-dep: {err}")
            return
        self._loop_task = asyncio.create_task(
            self._run_loop(),
            name=f"vag_connect-skoda-push-{self._user_id[-6:]}",
        )

    async def stop(self) -> None:
        """Cancel the loop + clean up. Idempotent."""
        if self._state == PushManagerState.STOPPED:
            return
        self._stop_event.set()
        task = self._loop_task
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=10.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._loop_task = None
        self._state = PushManagerState.STOPPED

    def _lazy_check_dependencies(self) -> None:
        """Verify aiomqtt + firebase-messaging are importable.

        Doesn't actually use them yet — just verifies the install
        succeeded. The real imports happen inside ``_run_loop``.
        """
        # Per-import to give a clear ImportError message identifying
        # which dep is missing.
        import importlib  # noqa: PLC0415
        for mod_name in ("aiomqtt", "firebase_messaging"):
            try:
                importlib.import_module(mod_name)
            except ImportError as err:
                raise ImportError(f"{mod_name}: {err}") from err

    async def _run_loop(self) -> None:
        """Reconnect-with-backoff outer loop.

        Wraps a single inner ``_connect_and_listen`` invocation in the
        backoff state machine. Exits when ``_stop_event`` is set.
        """
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Skoda push: connection lost (vin count=%d): %s — "
                    "reconnecting in %.1fs",
                    len(self._vins),
                    type(err).__name__,
                    self._backoff_seconds,
                )
                self._state = PushManagerState.RECONNECTING
                # v2.2.0 PR #12/20 — record this strike. If we hit 3
                # consecutive failures the breaker trips and the next
                # iteration of the outer loop will exit (we check
                # is_tripped after the backoff sleep below).
                # class only — str(err)[:160] is truncation, not redaction: an
                # aiohttp/mqtt connect error's str() carries the broker URL/host.
                self._record_failure(f"connect-loop: {type(err).__name__}")
                # Sleep with cancellation support
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._backoff_seconds,
                    )
                    # Stop was set during sleep — exit loop
                    break
                except asyncio.TimeoutError:
                    pass
                self._advance_backoff()
                # v2.2.0 PR #12/20 — if the breaker tripped during
                # the failure-counting above, exit the outer loop.
                # Reading ``self.state`` honours the auto-reset
                # property-getter transition.
                if self.state == PushManagerState.TRIPPED:
                    _LOGGER.error(
                        "Skoda push: circuit-breaker tripped — exiting "
                        "reconnect loop. Next start() call will short-"
                        "circuit until auto-reset (1h) or manual "
                        "reset_circuit_breaker().",
                    )
                    break

    async def _connect_and_listen(self) -> None:
        """One connect + receive cycle. Raises on disconnect.

        Grounded verbatim in ``skodaconnect/myskoda`` ``mqtt.py``:

        1. Register (or restore) an FCM token — it is the TOTP secret.
        2. Refresh the OAuth access token (MQTT password).
        3. Build a fresh ``Properties(PacketTypes.CONNECT)`` carrying
           the ``totp_v1`` UserProperties, keyed on the current FCM
           token (TOTP rotates every 30s).
        4. Open ``aiomqtt.Client(..., properties=props)`` MQTTv5/TLS.
        5. Subscribe ``{user_id}/{vin}/#`` per VIN.
        6. ``async for message in client.messages`` -> decode -> emit.

        Any broker/connection error propagates to ``_run_loop`` which
        records the strike, advances backoff, and retries (refreshing
        both OAuth + FCM tokens on the next attempt).
        """
        import aiomqtt  # noqa: PLC0415
        from paho.mqtt.packettypes import PacketTypes  # noqa: PLC0415
        from paho.mqtt.properties import Properties  # noqa: PLC0415

        # (1) FCM token = TOTP secret material.
        fcm_token = await self._register_fcm_token()
        # (2) OAuth token = MQTT password. Fresh every connect.
        password = await self._access_token_provider()
        if not password:
            raise RuntimeError("Skoda push: access_token_provider returned empty")

        # (3) MQTTv5 CONNECT properties with the TOTP UserProperties.
        props = Properties(PacketTypes.CONNECT)
        props.UserProperty = [
            ("auth_method", "totp_v1"),
            ("auth_credentials", self._generate_totp(fcm_token)),
        ]

        ssl_context = self._build_ssl_context()

        # (4) Fresh client per connect so ``properties=`` carries the
        # current TOTP (public aiomqtt constructor API, >=2.0).
        client = aiomqtt.Client(
            hostname=_BROKER_HOST,
            port=_BROKER_PORT,
            identifier=f"{uuid.uuid4()}#{uuid.uuid4()}",
            logger=_LOGGER,
            tls_context=ssl_context,
            keepalive=_MQTT_KEEPALIVE,
            protocol=aiomqtt.ProtocolVersion.V5,
            username=self._user_id or "android-app",
            password=password,
            properties=props,
        )

        async with client:
            self._fcm_client = client
            # (5) Catch-all subscribe per VIN. ``#`` (not ``+/+``) so we
            # don't miss two-level service topics like
            # ``service-event/vehicle-status/odometer``.
            for vin in self._vins:
                await client.subscribe(f"{self._user_id}/{vin}/#")
            self._state = PushManagerState.CONNECTED
            self._record_success()
            self._reset_backoff()
            _LOGGER.info(
                "Skoda push: connected + subscribed for %d VIN(s) "
                "(user ***%s)",
                len(self._vins),
                self._user_id[-6:],
            )
            # (6) Receive loop.
            async for message in client.messages:
                event = self._decode_mqtt_message(
                    str(message.topic), message.payload
                )
                if event is not None:
                    await self.emit(event)

        # Clean exit (context manager closed) — treated as a disconnect
        # by the outer loop unless we were told to stop.
        self._fcm_client = None
        self._state = PushManagerState.STOPPED

    def _build_ssl_context(self) -> Any:
        """Pre-built TLS context (avoids paho's blocking ``tls_set``).

        Matches myskoda ``_create_ssl_context``.
        """
        import ssl  # noqa: PLC0415

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_default_certs()
        return context

    async def _register_fcm_token(self) -> str:
        """Register the FCM token used as the TOTP secret.

        The creds are copied from myskoda's pre-#584 values (NOT
        independently verified), and this ``checkin_or_register`` path is
        the one myskoda abandoned in #584 — see the module docstring. The
        token is cached in memory only and refreshed via the
        credentials-updated callback; it is NOT persisted, so a restart
        re-registers. (An earlier docstring said "in HA this maps to a
        ``Store``" — there is no Store.)
        """
        if self._fcm_token:
            return self._fcm_token
        from firebase_messaging import (  # noqa: PLC0415
            FcmPushClient,
            FcmRegisterConfig,
        )

        fcm_config = FcmRegisterConfig(
            _FCM_PROJECT_ID,
            _FCM_APP_ID,
            _FCM_API_KEY,
            _FCM_SENDER_ID,
        )
        # Skoda push arrives over MQTT, not FCM — so we register only
        # to obtain the token (the TOTP secret) and don't start the
        # FCM receive loop. A no-op callback satisfies the ctor.
        client = FcmPushClient(
            lambda *_a, **_k: None,
            fcm_config,
            self._fcm_credentials,
            self._on_fcm_credentials_updated,
        )
        token = str(await client.checkin_or_register())
        self._fcm_token = token
        return token

    def _on_fcm_credentials_updated(self, creds: dict[str, Any]) -> None:
        """firebase-messaging credentials-rotation callback."""
        self._fcm_credentials = creds

    @staticmethod
    def _generate_totp(fcm_token: str) -> str:
        """Generate the broker TOTP — VERBATIM from myskoda ``mqtt.py``.

        RFC-4226 HOTP over a 30s time-step, but keyed by the SHA-256 of
        the FCM token (NOT a standard shared secret), HMAC-SHA256,
        6-digit zero-padded.
        """
        key = hashlib.sha256(fcm_token.encode("utf-8")).digest()
        time_step = struct.pack(">Q", int(time.time()) // 30)
        mac = hmac.new(key, time_step, hashlib.sha256).digest()
        offset = mac[-1] & 0x0F
        code = (
            ((mac[offset] & 0x7F) << 24)
            | ((mac[offset + 1] & 0xFF) << 16)
            | ((mac[offset + 2] & 0xFF) << 8)
            | (mac[offset + 3] & 0xFF)
        )
        return str(code % (10**6)).zfill(6)

    @staticmethod
    def _decode_mqtt_message(
        topic: str, payload: Any
    ) -> PushUpdateEvent | None:
        """Decode an MQTT message into a ``PushUpdateEvent``.

        Grounded in myskoda ``BaseEvent.from_mqtt_message``:
        ``topic.split("/", maxsplit=3)`` -> user_id, vin, category, tail
        (the tail absorbs one- or two-level service topics).
        ``json.loads(payload)`` for the body. Empty payloads dropped.
        Any decode error returns ``None`` (never crashes the loop).
        """
        try:
            if payload is None:
                return None
            if isinstance(payload, (bytes, bytearray)):
                if len(payload) == 0:
                    return None
                payload_str = payload.decode("utf-8", errors="replace")
            else:
                payload_str = str(payload)
            if not payload_str:
                return None
            parts = topic.split("/", maxsplit=3)
            if len(parts) < 4:
                return None
            _user_id, vin, category, tail = parts
            body: dict[str, Any] = {}
            try:
                parsed = json.loads(payload_str)
                if isinstance(parsed, dict):
                    body = parsed
            except (ValueError, TypeError):
                body = {}
            # Prefer the vin from the payload data when present, else
            # the topic segment.
            data = body.get("data") if isinstance(body.get("data"), dict) else {}
            vin = (data.get("vin") if isinstance(data, dict) else None) or vin
            timestamp = body.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp:
                timestamp = datetime.now(tz=timezone.utc).isoformat()
            return PushUpdateEvent(
                vin=vin,
                event_type=category,
                topic=f"{category}/{tail}",
                timestamp=timestamp,
                raw_payload=body or None,
            )
        except Exception as exc:  # noqa: BLE001 - decode must never crash the loop
            # Class only, not exc_info — a malformed-field conversion error can put
            # a payload value (e.g. the VIN) into its message/traceback.
            _LOGGER.debug(
                "Skoda push: undecodable MQTT message (%s)", type(exc).__name__
            )
            return None

    # v2.2.0 Phase 5a PR #18/20: ``_advance_backoff`` + ``_reset_backoff``
    # moved to ``PushManager`` base class. Inherited via ``super``.
