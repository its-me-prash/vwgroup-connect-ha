# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ╔════════════════════════════════════════════════════════════════════╗
# ║ BETA — opt-in, live-test-gated (v2.15.10)                         ║
# ║ Real FCM register + OLA /v2/subscriptions + receive is wired,     ║
# ║ grounded verbatim in the pycupra lib. CUPRA + SEAT share one      ║
# ║ Firebase project (ola-apps-prod) with per-brand app_id. Live-test ║
# ║ gate: needs a MyCupra/MySeat owner to confirm the creds + body    ║
# ║ against the production backend. Fail-soft via the circuit-breaker.║
# ╚════════════════════════════════════════════════════════════════════╝
"""CUPRA/SEAT OLA FCM push manager (BETA).

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

### BETA status (v2.15.10)

Real path is wired, grounded verbatim in the ``pycupra`` lib
(``firebase.py``, ``connection.py::subscribe`` L2073-2086,
``const.py`` L231-236, ``vehicle.py::onNotification``):

- ``FcmRegisterConfig(project_id, app_id, api_key, sender_id)`` then
  ``FcmPushClient(callback, config, creds, creds_cb)`` then
  ``await checkin_or_register()`` then ``await start()``.
- CUPRA + SEAT share Firebase project ``ola-apps-prod`` (same api_key
  + sender number ``530284123617``); the app_id is per-brand.
- Subscribe POST is PER-VIN to ``{OLA}/v2/subscriptions`` with body
  ``deviceId`` (GCM app_id), ``locale``, ``services`` (charging +
  climatisation booleans — NO windowHeating flag), ``token`` (FCM
  push token), ``userId``, ``vin``.
- Decode via ``obj["data"]["type"|"requestId"|"payload"]``; VIN comes
  from subscription context (not the FCM data dict).

Reuses the same ``firebase-messaging`` lib as Skoda + Audi/VW push.
Live-test gate: a MyCupra/MySeat owner confirms creds + body against
production, and VIN attribution with a multi-VIN single client.

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
import json
import logging
from datetime import datetime, timezone
from typing import Any

from .base import (
    PushManager,
    PushManagerState,
    PushEventCallback,
    PushUpdateEvent,
)

_LOGGER = logging.getLogger(__name__)

# Firebase project the CUPRA/SEAT mobile apps register against —
# VERIFIED against the raw APKs + pycupra const.py. CUPRA + SEAT SHARE
# one project (ola-apps-prod, api_key, sender number 530284123617);
# only the app_id differs per-brand. Public google-services.json
# values (no secrets).
_FCM_PROJECT_ID = "ola-apps-prod"
_FCM_SENDER_ID = "530284123617"
_FCM_API_KEY = "AIzaSyCoSp1zitklb1EDj5yQumN0VNhDizJQHLk"
_FCM_APP_ID: dict[str, str] = {
    "cupra": "1:530284123617:android:9b9ba5a87c7ffd37fbeea0",
    "seat": "1:530284123617:android:d6187613ac3d7b08fbeea0",
}

# OLA subscription endpoint — GROUNDED in pycupra ``connection.py``
# (``APP_URI`` + ``subscribe`` L2073-2086). POST per-VIN.
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
        self._fcm_client: Any = None
        self._fcm_credentials: dict[str, Any] | None = None
        # Event loop captured at connect time so the SYNC firebase
        # callback can schedule the async handler safely.
        self._loop: asyncio.AbstractEventLoop | None = None
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

        Grounded verbatim in pycupra ``firebase.py`` + ``connection.py``:

        1. ``FcmRegisterConfig(project_id, app_id, api_key, sender_id)``
           then ``FcmPushClient(callback, config, creds, creds_cb)``.
        2. ``await checkin_or_register()`` -> FCM token.
        3. POST per-VIN to ``{OLA}/v2/subscriptions`` (bearer OAuth).
        4. ``await client.start()`` — pushes delivered to the SYNC
           callback which schedules ``_handle_fcm_message``.
        5. Park on ``_stop_event``; on stop, ``await client.stop()``.
        """
        self._loop = asyncio.get_running_loop()
        access_token = await self._access_token_provider()
        if not access_token:
            raise RuntimeError(
                "CUPRA/SEAT push: access_token_provider returned empty"
            )

        from firebase_messaging import (  # noqa: PLC0415
            FcmPushClient,
            FcmRegisterConfig,
        )

        app_id = _FCM_APP_ID[self._brand]
        fcm_config = FcmRegisterConfig(
            _FCM_PROJECT_ID,
            app_id,
            _FCM_API_KEY,
            _FCM_SENDER_ID,
        )
        client = FcmPushClient(
            self._on_fcm_notification,
            fcm_config,
            self._fcm_credentials,
            self._on_fcm_credentials_updated,
        )
        self._fcm_client = client
        fcm_token = await client.checkin_or_register()

        # (3) per-VIN OLA subscription.
        for vin in self._vins:
            await self._post_ola_subscription(
                vin, fcm_token, app_id, access_token
            )

        # (4) start receiving.
        await client.start()

        self._state = PushManagerState.CONNECTED
        self._record_success()
        self._reset_backoff()
        _LOGGER.info(
            "CUPRA/SEAT push (brand=%s): live FCM receive loop up for "
            "%d VIN(s)",
            self._brand,
            len(self._vins),
        )
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            raise
        finally:
            try:
                await client.stop()
            except Exception:  # noqa: BLE001
                pass
            self._fcm_client = None
        self._state = PushManagerState.STOPPED

    async def _post_ola_subscription(
        self, vin: str, fcm_token: str, app_id: str, access_token: str
    ) -> None:
        """POST the FCM token to OLA ``/v2/subscriptions`` — per VIN.

        Body GROUNDED verbatim in pycupra ``connection.py::subscribe``
        (L2078-2085): ``deviceId`` = the GCM/checkin app_id (NOT the
        FCM token), ``locale`` = ``en_GB``, ``services`` =
        ``{charging, climatisation}`` booleans (no windowHeating flag),
        ``token`` = the FCM push token, ``userId``, ``vin``.
        """
        url = f"{_OLA_BASE}{_SUBSCRIPTIONS_PATH}"
        body = {
            "deviceId": app_id,
            "locale": "en_GB",
            "services": {"charging": True, "climatisation": True},
            "token": fcm_token,
            "userId": self._user_id,
            "vin": vin,
        }
        await self._http_post_subscription(url, body, access_token)

    async def _http_post_subscription(
        self, url: str, body: dict[str, Any], access_token: str
    ) -> None:
        """Bearer-authenticated subscription POST (test seam)."""
        import aiohttp  # noqa: PLC0415

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status >= 400:
                    raise RuntimeError(
                        f"CUPRA/SEAT push: subscription POST returned "
                        f"HTTP {resp.status}"
                    )

    def _on_fcm_notification(
        self, notification: Any, persistent_id: Any = None, obj: Any = None
    ) -> None:
        """firebase-messaging callback bridge (SYNC).

        The upstream lib invokes callbacks synchronously, so this
        schedules the async decode/emit on the captured loop.
        """
        loop = self._loop
        if loop is None or loop.is_closed():  # pragma: no cover - defensive
            return
        loop.call_soon_threadsafe(
            lambda: loop.create_task(self._handle_fcm_message(notification))
        )

    def _on_fcm_credentials_updated(self, creds: dict[str, Any]) -> None:
        """firebase-messaging credentials-rotation callback."""
        self._fcm_credentials = creds

    async def _handle_fcm_message(self, raw: Any) -> None:
        """Decode a CUPRA/SEAT FCM message + emit. Never raises."""
        event = self._decode_fcm_payload(raw, default_vin=self._default_vin())
        if event is None:
            return
        await self.emit(event)

    def _default_vin(self) -> str | None:
        """VIN for a payload when the FCM data carries none.

        GROUND-B: the CUPRA/SEAT FCM ``data`` dict has no ``vin`` —
        routing is subscription context. Unambiguous only with a
        single subscribed VIN.
        """
        return self._vins[0] if len(self._vins) == 1 else None

    @staticmethod
    def _decode_fcm_payload(
        raw: Any, default_vin: str | None = None
    ) -> PushUpdateEvent | None:
        """Decode a CUPRA/SEAT FCM message into a ``PushUpdateEvent``.

        GROUNDED in pycupra ``vehicle.py::onNotification`` (L5662-5664):
        the discriminator is ``obj["data"]["type"]`` (kebab-case string,
        e.g. ``charging-status-changed``, ``vehicle-access-locked-
        successful``); ``requestId`` correlates to a command we sent;
        ``payload`` is a JSON string (``json.loads`` when present).
        There is NO ``vin`` in the data dict — it comes from
        subscription context (``default_vin``).

        Malformed input returns ``None`` (never raises).
        """
        if not isinstance(raw, dict):
            _LOGGER.debug(
                "CUPRA/SEAT push: discarding non-dict FCM payload (type=%s)",
                type(raw).__name__,
            )
            return None
        data = raw["data"] if isinstance(raw.get("data"), dict) else raw
        ev_type = data.get("type")
        if not isinstance(ev_type, str) or not ev_type:
            _LOGGER.debug(
                "CUPRA/SEAT push: no 'type' discriminator; discarding",
            )
            return None
        vin = data.get("vin") or raw.get("vin") or default_vin
        if not isinstance(vin, str) or not vin:
            _LOGGER.debug(
                "CUPRA/SEAT push: 'type'=%s but no vin (payload or "
                "subscription context); discarding",
                ev_type,
            )
            return None
        # ``payload`` is a JSON string when present; parse best-effort.
        parsed_payload: Any = data.get("payload")
        if isinstance(parsed_payload, str) and parsed_payload:
            try:
                parsed_payload = json.loads(parsed_payload)
            except (ValueError, TypeError):
                pass  # keep the raw string
        timestamp = data.get("timestamp") or raw.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            timestamp = datetime.now(tz=timezone.utc).isoformat()
        request_id = data.get("requestId")
        raw_payload = dict(data)
        if request_id is not None:
            raw_payload.setdefault("requestId", request_id)
        if parsed_payload is not None:
            raw_payload["payload"] = parsed_payload
        topic = data.get("topic") or raw.get("topic") or f"ola/{ev_type}"
        return PushUpdateEvent(
            vin=vin,
            event_type=ev_type,
            topic=str(topic),
            timestamp=timestamp,
            raw_payload=raw_payload,
        )

    # v2.2.0 Phase 5a PR #18/20: ``_advance_backoff`` + ``_reset_backoff``
    # moved to ``PushManager`` base class. Inherited via ``super``.
