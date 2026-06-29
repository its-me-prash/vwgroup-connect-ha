# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ╔════════════════════════════════════════════════════════════════════╗
# ║ SCAFFOLDING — NOT WIRED INTO PRODUCTION CALL PATHS                ║
# ║ Foundation built v1.19.0; OptionsFlow toggle exists but           ║
# ║ Coordinator does NOT instantiate CupraSeatPushManager.start().    ║
# ║ Live activation requires community MyCupra/MySeat tester for      ║
# ║ FCM project + sender_id + OLA /v2/subscriptions schema.           ║
# ║ See ROADMAP "Push Bundle Phase 2" + #57 Phase 2.                  ║
# ╚════════════════════════════════════════════════════════════════════╝
"""CUPRA/SEAT OLA FCM push manager (v1.19.0 foundation).

Subscribes to Firebase Cloud Messaging push notifications for
CUPRA/SEAT vehicles registered against the OLA backend at
``ola.prod.code.seat.cloud.vwgroup.com``.

### Architecture

Two pieces:

1. **FCM client** (``firebase-messaging`` Python lib) — registers
   a device with the Firebase project ``ola-apps-prod``, persists
   the resulting credentials via HA's ``Store`` helper, listens
   for push notifications via the lib's async start() loop.

2. **OLA subscription** — once we have the FCM token, POST it to
   ``/v2/subscriptions`` with the user's vehicles + service flags
   (charging, climatisation). OLA then routes change notifications
   to that FCM token. Subscription is sticky — re-POST only on
   token rotation.

### Foundation status (v1.19.0)

This module mirrors ``skoda_mqtt.py`` (v1.18.0) — class structure,
state machine, lifecycle hooks complete, but the actual FCM
client/OLA subscription code is **lazy-imported** + stubbed.
Live activation requires a CUPRA/SEAT owner (active MyCupra /
MySeat subscription) + verified Firebase credentials.

Reuses the same `firebase-messaging` lib that v1.18.0 lazy-imports
for Skoda MQTT TOTP auth — so opting into either Skoda push OR
CUPRA/SEAT push triggers the same dependency check.

### References

- upstream/homeassistant-pycupra ``firebase.py`` (FCM register flow)
- upstream/homeassistant-pycupra ``connection.py`` (OLA subscribe POST)

### Privacy

- VINs masked to last 6 chars in logs
- user_id masked to first 8 chars
- FCM tokens, OAuth tokens: NEVER logged
- TLS verifies OLA cert
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .base import PushManager, PushManagerState, PushEventCallback

_LOGGER = logging.getLogger(__name__)

# Firebase project the CUPRA/SEAT mobile apps register against.
# Public sender_id from the Android google-services.json — no
# secrets here. May rotate; live tester confirms at activation.
_FCM_PROJECT_ID = "ola-apps-prod"
_FCM_SENDER_ID = "<sender-id-pending-live-confirmation>"

# OLA subscription endpoint — verified via upstream/homeassistant-pycupra
# ``connection.py``. POST {token, deviceId, services} to register a
# given FCM token for push delivery.
_OLA_BASE = "https://ola.prod.code.seat.cloud.vwgroup.com"
_SUBSCRIPTIONS_PATH = "/v2/subscriptions"

# v2.2.0 Phase 5a PR #18/20: backoff constants moved to ``base.py``
# (``PUSH_INITIAL_BACKOFF_S`` etc.). Shared across all push managers.


class CupraSeatPushManager(PushManager):
    """CUPRA/SEAT OLA FCM push manager.

    Lifecycle mirrors ``SkodaPushManager``:

    1. ``start()`` — lazy-imports firebase-messaging, registers
       (or restores) FCM credentials, POSTs subscription to OLA
       for each VIN, spawns receive loop on the FCM client
    2. Background loop calls ``self.emit()`` on each push
    3. On disconnect: backoff + reconnect (refreshes OAuth token
       used in OLA subscription POST)
    4. ``stop()`` — cancels loop, closes FCM client

    Idempotent ``start()`` and ``stop()``.
    """

    def __init__(
        self,
        on_event: PushEventCallback,
        *,
        user_id: str,
        access_token_provider: Any,
        vins: list[str],
        brand: str,  # "cupra" or "seat"
    ) -> None:
        """Initialise.

        Args:
            on_event: Coordinator callback receiving each event.
            user_id: OLA user-id (UUID format).
            access_token_provider: Async coroutine returning fresh
                OAuth access token. Called before each OLA subscription
                POST to ensure auth is valid.
            vins: List of VINs to subscribe to. Each gets its own
                ``/v2/subscriptions`` POST with the brand's standard
                services flag set (charging, climatisation,
                windowHeating).
            brand: Either ``"cupra"`` or ``"seat"``. Affects the
                Firebase project / OLA endpoint variant when those
                differ.
        """
        super().__init__(on_event)
        if brand not in ("cupra", "seat"):
            raise ValueError(
                f"CupraSeatPushManager: brand must be 'cupra' or 'seat', "
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

        v2.2.0 PR #13/20: respects the circuit-breaker (PR #12 base).
        If the breaker is tripped (3 consecutive start failures), this
        returns immediately without retrying. Caller can poll ``state``
        for the TRIPPED signal and surface it via Repair-Issue.
        """
        if self._state in (PushManagerState.CONNECTED, PushManagerState.STARTING):
            return
        # v2.2.0 PR #13/20 — short-circuit if breaker tripped.
        # Reading ``self.state`` (not ``self._state``) honours the
        # auto-reset transition in the property-getter (1h cooldown).
        if self.state == PushManagerState.TRIPPED:
            _LOGGER.warning(
                "CUPRA/SEAT push (brand=%s): circuit-breaker TRIPPED — "
                "declining start. Wait for auto-reset (1h) or call "
                "reset_circuit_breaker().",
                self._brand,
            )
            return
        if not self._vins:
            _LOGGER.info(
                "CUPRA/SEAT push: no VINs to subscribe to — staying STOPPED",
            )
            return
        self._state = PushManagerState.STARTING
        self._stop_event.clear()
        try:
            self._lazy_check_dependencies()
        except ImportError as err:
            _LOGGER.warning(
                "CUPRA/SEAT push: required dependency missing — %s. "
                "Run `pip install firebase-messaging` in your HA env "
                "or disable the push option. Falling back to polling.",
                err,
            )
            self._state = PushManagerState.UNAVAILABLE
            # v2.2.0 PR #13/20: missing-deps strike. After 3 attempts
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

        CUPRA/SEAT only needs firebase-messaging (no MQTT — push
        is pure FCM). Skoda MQTT also uses firebase-messaging for
        TOTP auth, so the dep is already familiar from v1.18.0.
        """
        import importlib  # noqa: PLC0415
        try:
            importlib.import_module("firebase_messaging")
        except ImportError as err:
            raise ImportError(f"firebase_messaging: {err}") from err

    async def _run_loop(self) -> None:
        """Reconnect-with-backoff outer loop. Same shape as
        SkodaPushManager._run_loop for consistency."""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "CUPRA/SEAT push: connection lost (vin count=%d, "
                    "brand=%s): %s — reconnecting in %.1fs",
                    len(self._vins),
                    self._brand,
                    err,
                    self._backoff_seconds,
                )
                self._state = PushManagerState.RECONNECTING
                # v2.2.0 PR #13/20 — record this strike. After 3
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
                # v2.2.0 PR #13/20 — exit if breaker tripped during
                # the strike-counting above. Reading ``self.state``
                # honours the auto-reset transition.
                if self.state == PushManagerState.TRIPPED:
                    _LOGGER.error(
                        "CUPRA/SEAT push (brand=%s): circuit-breaker "
                        "tripped — exiting reconnect loop. Next start() "
                        "call will short-circuit until auto-reset (1h) "
                        "or manual reset_circuit_breaker().",
                        self._brand,
                    )
                    break

    async def _connect_and_listen(self) -> None:
        """One FCM register + OLA subscribe + receive cycle.

        v1.19.0 foundation: this is a STUB. The real implementation
        will:

        1. Lazy-import ``firebase_messaging.FcmClient``
        2. Build FcmRegisterConfig with project_id=ola-apps-prod +
           sender_id from app metadata
        3. ``await client.checkin_or_register()`` — returns FCM token
        4. POST token + vins to ``{_OLA_BASE}{_SUBSCRIPTIONS_PATH}``
           with bearer auth from ``self._access_token_provider``
        5. ``await client.start()`` with on_message callback that
           parses notification → PushUpdateEvent → ``self.emit()``

        For now: refresh OAuth token then sleep until stopped so
        the lifecycle state machine can be exercised without
        network I/O.
        """
        token = await self._access_token_provider()  # noqa: F841 — used in real impl
        self._state = PushManagerState.CONNECTED
        # v2.2.0 PR #13/20 — successful connect resets the breaker.
        # Idempotent: no-op when strike_count is already 0.
        self._record_success()
        _LOGGER.info(
            "CUPRA/SEAT push: foundation stub — live activation pending. "
            "Brand=%s, would POST subscription for VINs: %s",
            self._brand,
            [f"***{vin[-6:]}" for vin in self._vins],
        )
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            raise
        self._state = PushManagerState.STOPPED

    # v2.2.0 Phase 5a PR #18/20: ``_advance_backoff`` + ``_reset_backoff``
    # moved to ``PushManager`` base class. Inherited via ``super``.
