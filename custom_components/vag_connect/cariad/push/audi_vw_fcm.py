# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ╔════════════════════════════════════════════════════════════════════╗
# ║ LIVE (BETA) v2.8.0 Action #4                                      ║
# ║ Decode + HA-bus emission paths are wired into the coordinator.    ║
# ║ Live FCM subscription stays gated behind a NotImplementedError    ║
# ║ inside ``_resolve_fcm_credentials`` until the Cariad Firebase     ║
# ║ sender_id / api_key / app_id are recovered from a live APK        ║
# ║ (tracked as task #40 follow-up). When the credentials land, drop  ║
# ║ them into the resolver and the receive loop wakes up.             ║
# ╚════════════════════════════════════════════════════════════════════╝
"""Audi/VW Cariad-BFF Firebase Cloud Messaging push manager (v1.23.0 foundation).

User-suggested feature 2026-05-07: "weil ich auf der app push nachrichten
bekomme, könnte man das doch auch auf der integration als feedback nehmen?"

The myAudi + WeConnect mobile apps subscribe to Cariad's own FCM
channel for vehicle-event push notifications (lock/unlock results,
charging-state changes, climate-state changes, alarm/theft alerts).
We can do the same — registering an FCM token via the cariad-mbb
infrastructure and forwarding events to the coordinator for
near-real-time HA updates + command-result-push notifications.

### Architecture

Three pieces (analog to v1.18.0 Skoda MQTT + v1.19.0 CUPRA/SEAT FCM):

1. **FCM client** (``firebase-messaging`` Python lib, lazy-imported)
   — Same library v1.18.0/v1.19.0 already use. Registers a device
   with the Cariad Firebase project, persists credentials via HA
   ``Store`` helper, listens for push notifications.

2. **Cariad notification subscription** — POST FCM token to Cariad's
   notification-registration endpoint (TBD live-test, expected at
   ``mal-1a.prd.ece.vwg-connect.com/api/notification/...``). Reference:
   upstream for the endpoint pattern.

3. **Coordinator callback** — each push event decoded into
   ``PushUpdateEvent`` and forwarded via ``on_event`` callback. The
   coordinator decides what to refresh (typically a single
   ``get_status`` for the affected VIN) AND optionally surfaces a
   ``persistent_notification`` for command-result events ("Audi A4
   wurde verriegelt") so user gets HA-side confirmation analog to
   what the official myAudi app shows.

### Brand scope

Both `audi` and `volkswagen` brands. They share the Cariad-BFF
backend so the FCM channel is unified — single `AudiVWPushManager`
instance handles both. Per-VIN routing happens via the FCM message
payload's `vin` field.

### Foundation status (v1.23.0)

This module mirrors ``skoda_mqtt.py`` + ``cupra_seat_fcm.py`` —
class structure, state machine, lifecycle hooks complete. Live FCM
connection code is **lazy-imported** + stubbed.

Live activation requires:
- Audi/VW owner with active Connect+ subscription (live tester)
- Verified Cariad Firebase project ID + sender_id
- Confirmed notification-subscription endpoint URL (upstream
  reference, may have changed)
- Verified push-event payload schema

These can only be validated end-to-end against the live backend.
v1.23.x patches will activate the path once a community tester
confirms.

### References

- upstream/upstream: notification subscription patterns
- upstream/homeassistant-pycupra: FCM register flow (similar lib)
- skodaconnect/myskoda PR #566: TOTP auth pattern (for MBB-side FCM)
- User-report 2026-05-07: myAudi App push screenshots showing
  "Ver-/Entriegeln: Audi S6 Avant wurde verriegelt" — the kind of
  event we'd surface as HA persistent_notification

### Privacy

- VINs masked to last 6 chars in logs
- user_id masked to first 8 chars
- OAuth + FCM tokens NEVER logged
- TLS verifies Cariad cert
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .base import (
    PushManager,
    PushManagerState,
    PushEventCallback,
    PushUpdateEvent,
)

_LOGGER = logging.getLogger(__name__)

# Cariad FCM project — Firebase project ID used by myAudi/WeConnect
# mobile apps. Public sender_id from Android google-services.json
# (TBD live-test verification — placeholder pending tester).
_CARIAD_FCM_PROJECT_ID = "<pending-tester>"
_CARIAD_FCM_SENDER_ID = "<pending-tester>"
_CARIAD_FCM_API_KEY = "<pending-tester>"

# Notification-subscription endpoint base. Same MBB setter base
# we use elsewhere (verified mal-1a.prd.ece.vwg-connect.com pattern).
_CARIAD_NOTIFICATION_BASE = "https://mal-1a.prd.ece.vwg-connect.com"
_CARIAD_NOTIFICATION_PATH = "/api/notification/v1/subscriptions"

# v2.8.0 Action #4: top-level keys we treat as "this is the Cariad
# event shape". Used by ``_decode_fcm_payload`` to classify which
# subtype we're looking at without needing an explicit ``type``
# field (the live myAudi push payloads do not always carry one).
_KNOWN_EVENT_KEYS: tuple[str, ...] = (
    "lockState",
    "chargingState",
    "climateState",
    "alarmType",
)

# v2.2.0 Phase 5a PR #18/20: backoff constants moved to ``base.py``
# (``PUSH_INITIAL_BACKOFF_S`` etc.). Shared across all push managers.


@dataclass(frozen=True)
class _FcmCreds:
    """Resolved Cariad FCM credentials.

    Populated by ``AudiVWPushManager._resolve_fcm_credentials`` once
    the live APK extraction of the Cariad ``google-services.json``
    blob completes. Until then the resolver raises
    ``NotImplementedError`` and the receive loop surfaces UNAVAILABLE
    (same path as a missing pip dep).
    """

    project_id: str
    sender_id: str
    api_key: str
    app_id: str


class AudiVWPushManager(PushManager):
    """Audi/VW Cariad-BFF FCM push manager.

    Lifecycle mirrors ``SkodaPushManager`` + ``CupraSeatPushManager``:

    1. ``start()`` — lazy-imports firebase-messaging, registers (or
       restores) FCM credentials, POSTs subscription to Cariad
       notification endpoint for each VIN, spawns receive loop
    2. Background loop calls ``self.emit()`` on each push
    3. On disconnect: backoff + reconnect (refreshes OAuth token)
    4. ``stop()`` — cancels loop, closes FCM client

    Idempotent ``start()`` and ``stop()``.

    Brand-scope: both ``audi`` and ``volkswagen`` share the Cariad-BFF
    backend → single manager handles both. Per-VIN routing via FCM
    message payload's ``vin`` field.
    """

    def __init__(
        self,
        on_event: PushEventCallback,
        *,
        user_id: str,
        access_token_provider: Any,
        vins: list[str],
        brand: str,  # "audi" or "volkswagen"
    ) -> None:
        """Initialise.

        Args:
            on_event: Coordinator callback receiving each event.
            user_id: Cariad user-id (UUID format from IDK token).
            access_token_provider: Async coroutine returning fresh
                OAuth access token. Called before each subscription
                POST to ensure auth is valid.
            vins: List of VINs to subscribe to. The Cariad notification
                endpoint may take all VINs in one POST (TBD).
            brand: Either ``"audi"`` or ``"volkswagen"``. Both share
                Cariad-BFF — kept as parameter for log clarity.
        """
        super().__init__(on_event)
        if brand not in ("audi", "volkswagen"):
            raise ValueError(
                f"AudiVWPushManager: brand must be 'audi' or 'volkswagen', "
                f"got {brand!r}"
            )
        self._user_id = user_id
        self._access_token_provider = access_token_provider
        self._vins = list(vins)
        self._brand = brand
        self._loop_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        # v2.2.0 Phase 5a PR #18/20: backoff state moved to PushManager
        # base ``__init__`` (set by ``super().__init__(on_event)`` above).

    async def start(self) -> None:
        """Spawn the FCM receive loop. Idempotent.

        v2.2.0 PR #14/20: respects the circuit-breaker (PR #12 base).
        If the breaker is tripped (3 consecutive start failures), this
        returns immediately without retrying. Caller can poll ``state``
        for the TRIPPED signal and surface it via Repair-Issue.
        """
        if self._state in (PushManagerState.CONNECTED, PushManagerState.STARTING):
            return
        # v2.2.0 PR #14/20 — short-circuit if breaker tripped.
        # Reading ``self.state`` (not ``self._state``) honours the
        # auto-reset transition in the property-getter (1h cooldown).
        if self.state == PushManagerState.TRIPPED:
            _LOGGER.warning(
                "Audi/VW push (brand=%s): circuit-breaker TRIPPED — "
                "declining start. Wait for auto-reset (1h) or call "
                "reset_circuit_breaker().",
                self._brand,
            )
            return
        if not self._vins:
            _LOGGER.info(
                "Audi/VW push: no VINs to subscribe to — staying STOPPED",
            )
            return
        self._state = PushManagerState.STARTING
        self._stop_event.clear()
        try:
            self._lazy_check_dependencies()
        except ImportError as err:
            _LOGGER.warning(
                "Audi/VW push: required dependency missing — %s. "
                "Run `pip install firebase-messaging` in your HA env "
                "or disable the push option. Falling back to polling.",
                err,
            )
            self._state = PushManagerState.UNAVAILABLE
            # v2.2.0 PR #14/20: missing-deps strike. After 3 attempts
            # the breaker trips so we stop spamming the log every
            # coordinator-start cycle.
            self._record_failure(f"missing-dep: {err}")
            return
        self._loop_task = asyncio.create_task(
            self._run_loop(),
            name=f"vag_connect-{self._brand}-push-{self._user_id[-6:]}",
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
        """Verify firebase-messaging is importable.

        Cariad uses the same FCM library as v1.18.0 (TOTP for MBB) +
        v1.19.0 (CUPRA/SEAT FCM transport). Single shared dep.
        """
        import importlib  # noqa: PLC0415
        try:
            importlib.import_module("firebase_messaging")
        except ImportError as err:
            raise ImportError(f"firebase_messaging: {err}") from err

    async def _run_loop(self) -> None:
        """Reconnect-with-backoff outer loop. Mirrors v1.18.0/v1.19.0."""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Audi/VW push: connection lost (vin count=%d, "
                    "brand=%s): %s — reconnecting in %.1fs",
                    len(self._vins),
                    self._brand,
                    err,
                    self._backoff_seconds,
                )
                self._state = PushManagerState.RECONNECTING
                # v2.2.0 PR #14/20 — record this strike. After 3
                # consecutive failures the breaker trips and we
                # exit the outer loop (check below after backoff).
                self._record_failure(f"connect-loop: {type(err).__name__}")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._backoff_seconds,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
                self._advance_backoff()
                # v2.2.0 PR #14/20 — exit if breaker tripped during
                # the strike-counting above. Reading ``self.state``
                # honours the auto-reset transition.
                if self.state == PushManagerState.TRIPPED:
                    _LOGGER.error(
                        "Audi/VW push (brand=%s): circuit-breaker "
                        "tripped — exiting reconnect loop. Next start() "
                        "call will short-circuit until auto-reset (1h) "
                        "or manual reset_circuit_breaker().",
                        self._brand,
                    )
                    break

    async def _connect_and_listen(self) -> None:
        """One FCM register + Cariad subscribe + receive cycle.

        v2.8.0 Action #4: the receive-loop infrastructure is wired,
        but the live FCM register is gated behind a credential
        resolver. When ``_resolve_fcm_credentials`` raises
        ``NotImplementedError`` we surface UNAVAILABLE (same path as
        a missing pip dep). Once credentials land in the resolver,
        the lazy-import + register + subscribe path lights up.

        On a transient HTTP-401 from the subscription POST, the
        outer ``_run_loop`` catches the raised RuntimeError, refreshes
        the access token via the provider, and retries on the next
        backoff cycle.
        """
        token = await self._access_token_provider()
        if not token:
            raise RuntimeError(
                "Audi/VW push: access_token_provider returned empty"
            )
        try:
            creds = self._resolve_fcm_credentials()
        except NotImplementedError as err:
            _LOGGER.info(
                "Audi/VW push (brand=%s): credentials pending (%s). "
                "Staying UNAVAILABLE until task #40 follow-up lands.",
                self._brand,
                err,
            )
            # Surface UNAVAILABLE so observers (system_health) see the
            # right state before the outer loop catches the re-raise.
            self._state = PushManagerState.UNAVAILABLE
            # Re-raise so the outer ``_run_loop`` records the strike +
            # advances the backoff + checks the circuit-breaker through
            # the single shared failure path. The breaker eventually
            # trips and the outer loop exits, stopping log-spam.
            raise RuntimeError(
                "Audi/VW push: credentials not yet available"
            ) from err
        # Credentials available: proceed to the live subscription path.
        # CONNECTED state is set before the network call so observers
        # don't see a STARTING-stuck status if the subscription POST
        # itself blocks. Reset breaker + backoff on success.
        self._state = PushManagerState.CONNECTED
        self._record_success()
        self._reset_backoff()
        _LOGGER.info(
            "Audi/VW push (brand=%s): live subscription primed for "
            "%d VIN(s) (project=%s)",
            self._brand,
            len(self._vins),
            creds.project_id,
        )
        # The actual ``firebase_messaging`` register + ``await client.
        # start(callback=self._handle_fcm_message)`` calls land in the
        # same patch that drops the real credentials. The decode + emit
        # paths exercised by the unit tests are reachable today via
        # ``_handle_fcm_message``.
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            raise
        self._state = PushManagerState.STOPPED

    def _resolve_fcm_credentials(self) -> _FcmCreds:
        """Resolve Cariad FCM project credentials.

        v2.8.0 Action #4 status: the literal values live in the
        Audi 5.5.0 + Volkswagen 3.61.0 APK ``google-services.json``
        resource. They are NOT present in our existing smali
        extractions under ``_private/`` (those carry only X-headers +
        OAuth client IDs). A live APK pull is required to recover
        ``sender_id`` + ``api_key`` + ``app_id``. Tracked as task #40
        follow-up.

        When that extraction lands, replace the ``raise`` below with
        a populated ``_FcmCreds`` literal and the receive loop comes
        alive.
        """
        raise NotImplementedError(
            "Sender ID extraction requires live APK reverse "
            "engineering, see task #40 follow-up"
        )

    async def _handle_fcm_message(self, raw: Any) -> None:
        """FCM ``on_message`` entrypoint.

        v2.8.0 Action #4: called from the ``firebase_messaging``
        receive loop once credentials are available. Decodes the
        Cariad payload shape into a ``PushUpdateEvent`` and forwards
        it via ``self.emit``. The coordinator's callback fires it
        onto the HA event bus and requests a refresh.

        Wrapped: a malformed payload causes a debug log and no
        emission, never a crash of the receive loop.
        """
        event = self._decode_fcm_payload(raw)
        if event is None:
            return
        await self.emit(event)

    @staticmethod
    def _decode_fcm_payload(raw: Any) -> PushUpdateEvent | None:
        """Decode a Cariad FCM ``data`` dict into a ``PushUpdateEvent``.

        The receive loop sees one of two shapes depending on how the
        ``firebase_messaging`` lib hands the message off:

        - Plain ``dict`` with the Cariad payload as top-level keys
        - Wrapped dict with the payload nested under ``"data"``

        Both are accepted. Anything that doesn't look like a Cariad
        event (missing ``vin``, no known event-key, not a dict at
        all) returns ``None`` so the caller skips it without raising.
        """
        if not isinstance(raw, dict):
            _LOGGER.debug(
                "Audi/VW push: discarding non-dict FCM payload (type=%s)",
                type(raw).__name__,
            )
            return None
        # Some FCM clients hand off ``{"data": {...}}``; others hand
        # off the data dict directly. Normalise both shapes.
        if "data" in raw and isinstance(raw["data"], dict):
            data = raw["data"]
        else:
            data = raw
        vin = data.get("vin") or raw.get("vin")
        if not isinstance(vin, str) or not vin:
            _LOGGER.debug(
                "Audi/VW push: discarding FCM payload, no vin field",
            )
            return None
        event_type: str | None = None
        for key in _KNOWN_EVENT_KEYS:
            if key in data:
                # ``alarmType`` collapses to ``alarm`` so the event_type
                # matches the user-facing wording in the myAudi App
                # ("Alarm" rather than "alarmType").
                event_type = "alarm" if key == "alarmType" else key
                break
        if event_type is None:
            _LOGGER.debug(
                "Audi/VW push: FCM payload for vin ***%s has no known "
                "event-key (keys=%s); discarding",
                vin[-6:],
                sorted(data.keys()),
            )
            return None
        topic = data.get("topic") or raw.get("topic") or f"cariad/{event_type}"
        timestamp = data.get("timestamp") or raw.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            # No backend timestamp: fall back to "received now" so the
            # event always carries a usable ISO 8601 value for
            # downstream automations.
            timestamp = datetime.now(tz=timezone.utc).isoformat()
        return PushUpdateEvent(
            vin=vin,
            event_type=event_type,
            topic=str(topic),
            timestamp=timestamp,
            raw_payload=dict(data),
        )

    # v2.2.0 Phase 5a PR #18/20: ``_advance_backoff`` + ``_reset_backoff``
    # moved to ``PushManager`` base class. Inherited via ``super``.
