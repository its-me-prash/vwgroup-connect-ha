# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ╔════════════════════════════════════════════════════════════════════╗
# ║ BETA — opt-in, live-test-gated (v2.15.10)                         ║
# ║ Real FCM register + subscribe + receive is wired. Firebase creds  ║
# ║ are verified per-brand (audi + volkswagen are SEPARATE Firebase   ║
# ║ projects). The notification-SUBSCRIPTION endpoint host/path/body  ║
# ║ for the Audi/VW app-BFF is UNVERIFIED off-device (no upstream lib  ║
# ║ exposes it) — we ship the pycupra ``/v2/subscriptions`` body shape ║
# ║ against the OLA-style host as a GATED placeholder + log a one-time ║
# ║ warning. A live mitmproxy capture of myAudi/WeConnect must confirm ║
# ║ the real host+path before this is anything but experimental.      ║
# ╚════════════════════════════════════════════════════════════════════╝
"""Audi/VW Cariad-BFF Firebase Cloud Messaging push manager (BETA).

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

2. **Notification subscription** — POST the FCM token to the app-BFF
   subscription endpoint. GATED/UNVERIFIED for Audi/VW: no upstream lib
   exposes their push-subscription endpoint, so we reuse the pycupra
   ``/v2/subscriptions`` body shape as a best-effort and emit a one-time
   runtime warning. (An earlier ``mal-1a.prd.ece.vwg-connect.com`` guess
   was fabricated — it has no notification path in any source.) A live
   mitmproxy capture must confirm the real host/path/body before this
   leaves BETA.

3. **Coordinator callback** — each push event decoded into
   ``PushUpdateEvent`` and forwarded via ``on_event`` callback. The
   coordinator decides what to refresh (typically a single
   ``get_status`` for the affected VIN) AND optionally surfaces a
   ``persistent_notification`` for command-result events ("Audi A4
   wurde verriegelt") so user gets HA-side confirmation analog to
   what the official myAudi app shows.

### Brand scope

Both `audi` and `volkswagen` brands — but they are on **SEPARATE
Firebase projects** (myAudi = ``onetouch-169db``; VW We Connect ID =
``gcp-project-we-connect-id``), NOT a shared Cariad project. The
credential resolver therefore branches on ``self._brand``. One
``AudiVWPushManager`` instance still handles a single-brand entry.
Per-VIN routing is supplied from subscription context (the FCM
``data`` dict does not always carry a ``vin`` — see ``_decode``).

### BETA status (v2.15.10)

Real FCM register (``firebase-messaging``) + notification subscribe
+ receive loop are wired. Verified per-brand Firebase creds are
baked in (independently confirmed against the raw APKs). What is
NOT verified off-device:

- The Audi/VW app-BFF notification-subscription **host + path**.
  No upstream library exposes a VW/Audi push-subscription endpoint
  (checked WeConnect-python, CarConnectivity-volkswagen, ioBroker —
  ioBroker implements it only for Skoda). We ship the pycupra
  ``/v2/subscriptions`` body shape as a GATED placeholder and log a
  one-time warning; a live mitmproxy capture must confirm the real
  host/path/body before this is trustworthy.
- The exact Audi/VW ``type`` string vocabulary (CUPRA's kebab-case
  ``vehicle-access-*`` / ``charging-*`` values are the template).

Live activation confirmation requires an Audi/VW owner with an
active Connect+ subscription running a capture.

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

@dataclass(frozen=True)
class _FcmCreds:
    """Resolved per-brand FCM credentials (verified against the APKs)."""

    project_id: str
    sender_id: str
    api_key: str
    app_id: str


# Per-brand Firebase creds — VERIFIED against the raw APKs. myAudi and
# VW We Connect ID are SEPARATE Firebase projects (NOT a shared Cariad
# project, NOT the legacy com.vw.carnet.release project). Public
# Android google-services.json values — no secrets.
_BRAND_FCM: dict[str, _FcmCreds] = {
    "audi": _FcmCreds(
        project_id="onetouch-169db",
        sender_id="254788998682",
        api_key="AIzaSyBVo1tiqGH1g2BOaOEvPS3XcWvoQrvMkBY",
        app_id="1:254788998682:android:fec5c470993c39fe",
    ),
    "volkswagen": _FcmCreds(
        project_id="gcp-project-we-connect-id",
        sender_id="992914193347",
        api_key="AIzaSyDC9d-LOI0LLK-9p0zhDNT2tJPYTjk5c2E",
        app_id="1:992914193347:android:c08d27281d231559bddb76",
    ),
}

# Notification-subscription endpoint.
#
# GATED / UNVERIFIED — there is NO VW/Audi push-subscription endpoint in
# any upstream library (WeConnect-python, CarConnectivity-volkswagen,
# ioBroker all lack it; ioBroker implements notification-subscribe only
# for Skoda). The legacy ``mal-1a.prd.ece.vwg-connect.com/api/
# notification/...`` literal that earlier scaffolding asserted as
# "verified" is fabricated — it carries only vehicle-data / auth paths,
# never a notification path. Until a live mitmproxy capture of the
# myAudi / WeConnect app confirms the real host + path, we borrow the
# pycupra OLA subscription host/path shape as a best-effort placeholder
# and emit a one-time GATED warning before POSTing.
_SUBSCRIPTION_BASE = "https://ola.prod.code.seat.cloud.vwgroup.com"
_SUBSCRIPTION_PATH = "/v2/subscriptions"

# v2.8.0 legacy state-key shape. Kept ONLY as a tolerant fallback for
# older captures / synthetic payloads. The GROUNDED discriminator is
# the single kebab-case string ``data["type"]`` (pycupra
# ``vehicle.py::onNotification``) handled first in ``_decode_fcm_payload``.
_KNOWN_EVENT_KEYS: tuple[str, ...] = (
    "lockState",
    "chargingState",
    "climateState",
    "alarmType",
)

# v2.2.0 Phase 5a PR #18/20: backoff constants moved to ``base.py``
# (``PUSH_INITIAL_BACKOFF_S`` etc.). Shared across all push managers.


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

    Brand-scope: ``audi`` and ``volkswagen`` are on SEPARATE Firebase
    projects (resolver branches on ``self._brand``). Per-VIN routing is
    supplied from subscription context, not the FCM payload.
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
        # Live FCM client handle (firebase_messaging.FcmPushClient),
        # created inside ``_connect_and_listen`` once creds resolve.
        self._fcm_client: Any = None
        # Event loop captured at connect time so the SYNC firebase
        # callback can schedule the async handler safely.
        self._loop: asyncio.AbstractEventLoop | None = None
        # Persisted FCM credential dict (checkin/registration state),
        # so a restart re-uses the same FCM token instead of churning
        # a new device registration. In HA this would be backed by the
        # ``Store`` helper; kept in-memory here + refreshed via the
        # credentials-updated callback.
        self._fcm_credentials: dict[str, Any] | None = None
        # One-time GATED-endpoint warning latch.
        self._subscription_warned = False
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
                self._record_failure(
                    f"connect-loop: {type(err).__name__}: {str(err)[:160]}"
                )
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
        """One FCM register + subscribe + receive cycle.

        Steps (all grounded in pycupra ``firebase.py`` + the upstream
        ``firebase-messaging`` API):

        1. Refresh the OAuth token (bearer for the subscription POST).
        2. Resolve verified per-brand Firebase creds.
        3. ``FcmPushClient(callback, FcmRegisterConfig(...), creds, ...)``
           then ``await checkin_or_register()`` -> FCM token.
        4. POST the token to the (GATED) notification-subscription
           endpoint per-VIN via ``_post_cariad_subscription``.
        5. ``await client.start()`` — the lib delivers pushes to
           ``self._handle_fcm_message`` via the callback bridge.
        6. Park on ``_stop_event``; on stop, ``await client.stop()``.

        On any failure the outer ``_run_loop`` records the strike,
        advances backoff, refreshes the token, and retries.
        """
        self._loop = asyncio.get_running_loop()
        token = await self._access_token_provider()
        if not token:
            raise RuntimeError(
                "Audi/VW push: access_token_provider returned empty"
            )
        creds = self._resolve_fcm_credentials()

        # Lazy import — kept out of module import so non-opted-in users
        # never pay the cost and HACS install can't fail on the wheel.
        from firebase_messaging import (  # noqa: PLC0415
            FcmPushClient,
            FcmRegisterConfig,
        )

        fcm_config = FcmRegisterConfig(
            creds.project_id,
            creds.app_id,
            creds.api_key,
            creds.sender_id,
        )
        client = FcmPushClient(
            self._on_fcm_notification,
            fcm_config,
            self._fcm_credentials,
            self._on_fcm_credentials_updated,
        )
        self._fcm_client = client
        fcm_token = await client.checkin_or_register()

        # Register the FCM token for push delivery, once per VIN.
        for vin in self._vins:
            await self._post_cariad_subscription(vin, fcm_token, token, creds)

        await client.start()

        # Connected: reset breaker + backoff, publish CONNECTED before
        # parking so observers don't see a STARTING-stuck status.
        self._state = PushManagerState.CONNECTED
        self._record_success()
        self._reset_backoff()
        _LOGGER.info(
            "Audi/VW push (brand=%s): live FCM receive loop up for "
            "%d VIN(s) (project=%s)",
            self._brand,
            len(self._vins),
            creds.project_id,
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

    def _resolve_fcm_credentials(self) -> _FcmCreds:
        """Resolve the verified per-brand Firebase credentials.

        Audi and VW-EU are SEPARATE Firebase projects — this branches
        on ``self._brand``. Values are verified against the raw APKs.
        """
        creds = _BRAND_FCM.get(self._brand)
        if creds is None:  # pragma: no cover — brand validated in __init__
            raise RuntimeError(
                f"Audi/VW push: no FCM creds for brand {self._brand!r}"
            )
        return creds

    async def _post_cariad_subscription(
        self,
        vin: str,
        fcm_token: str,
        access_token: str,
        creds: _FcmCreds,
    ) -> None:
        """POST the FCM token to the notification-subscription endpoint.

        GATED / UNVERIFIED — see the module banner. No upstream library
        exposes the Audi/VW app-BFF push-subscription endpoint, so we
        borrow the pycupra OLA ``/v2/subscriptions`` body shape as a
        best-effort placeholder and warn once. The body is the pycupra
        GROUNDED shape: ``deviceId`` (GCM app_id), ``locale``,
        ``services`` (charging + climatisation booleans), ``token``
        (the FCM push token), ``userId``, ``vin`` — per-VIN, not bulk.

        A live mitmproxy capture must confirm the real host + path +
        body before this can be trusted. Failures fail-soft: they
        propagate to ``_run_loop`` which trips the breaker after 3
        strikes rather than spamming.
        """
        if not self._subscription_warned:
            self._subscription_warned = True
            _LOGGER.warning(
                "Audi/VW push (brand=%s): the notification-subscription "
                "endpoint is UNVERIFIED off-device — using the pycupra "
                "/v2/subscriptions body shape as a GATED placeholder. "
                "Push may not activate until a live capture confirms the "
                "real Audi/VW host+path. This is experimental BETA.",
                self._brand,
            )
        url = f"{_SUBSCRIPTION_BASE}{_SUBSCRIPTION_PATH}"
        body = {
            "deviceId": creds.app_id,
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
        """Issue the bearer-authenticated subscription POST.

        Split out so tests can patch a single seam without a live
        aiohttp session. Uses HA's shared client session when running
        inside HA; here we lazy-import aiohttp so the module has no
        hard import-time dependency on it.
        """
        import aiohttp  # noqa: PLC0415

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status >= 400:
                    raise RuntimeError(
                        f"Audi/VW push: subscription POST returned "
                        f"HTTP {resp.status}"
                    )

    def _on_fcm_notification(
        self, notification: Any, persistent_id: Any = None, obj: Any = None
    ) -> None:
        """firebase-messaging callback bridge (SYNC).

        The upstream ``firebase-messaging`` lib calls the callback
        SYNCHRONOUSLY with ``(notification_dict, persistent_id, obj)``
        — it does NOT await coroutine callbacks. So this is a plain
        function that schedules the async ``_handle_fcm_message`` on
        the loop captured at connect time. ``persistent_id`` is
        available for dedup if a future revision needs it.
        """
        loop = self._loop
        if loop is None or loop.is_closed():  # pragma: no cover - defensive
            return
        loop.call_soon_threadsafe(
            lambda: loop.create_task(self._handle_fcm_message(notification))
        )

    def _on_fcm_credentials_updated(self, creds: dict[str, Any]) -> None:
        """firebase-messaging credentials-rotation callback.

        Called when the lib re-registers / rotates the FCM token. We
        cache it in-memory so the next reconnect re-uses it. In HA this
        is where a ``Store.async_save`` would persist across restarts.
        """
        self._fcm_credentials = creds

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
        event = self._decode_fcm_payload(raw, default_vin=self._default_vin())
        if event is None:
            return
        await self.emit(event)

    def _default_vin(self) -> str | None:
        """VIN to attribute a payload to when the FCM data carries none.

        GROUND-A: the Cariad/CUPRA FCM ``data`` dict does NOT carry a
        ``vin`` — routing comes from subscription context. When exactly
        one VIN is subscribed we can attribute unambiguously; with
        several we can't and fall back to None (the decode then drops
        VIN-less payloads). A future revision can key the FCM client
        per-VIN to make this exact.
        """
        return self._vins[0] if len(self._vins) == 1 else None

    @staticmethod
    def _decode_fcm_payload(
        raw: Any, default_vin: str | None = None
    ) -> PushUpdateEvent | None:
        """Decode a Cariad/CUPRA FCM ``data`` dict into a ``PushUpdateEvent``.

        The GROUNDED shape (pycupra ``vehicle.py::onNotification``) is a
        single kebab-case string discriminator ``data["type"]`` (e.g.
        ``vehicle-access-locked-successful``, ``charging-status-changed``)
        with no ``vin`` in the data dict — VIN comes from subscription
        context (``default_vin``). That path is tried first.

        As a tolerant fallback we also accept the legacy state-key shape
        (``lockState`` / ``chargingState`` / ``climateState`` /
        ``alarmType``) with an in-payload ``vin`` — used for older
        captures + synthetic tests.

        Anything else returns ``None`` so the caller skips it.
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

        # GROUNDED primary: single kebab-case ``type`` string.
        ev_type = data.get("type")
        if isinstance(ev_type, str) and ev_type:
            vin = data.get("vin") or raw.get("vin") or default_vin
            if not isinstance(vin, str) or not vin:
                _LOGGER.debug(
                    "Audi/VW push: 'type'=%s but no vin (payload or "
                    "subscription context); discarding",
                    ev_type,
                )
                return None
            topic = (
                data.get("topic") or raw.get("topic") or f"cariad/{ev_type}"
            )
            timestamp = data.get("timestamp") or raw.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp:
                timestamp = datetime.now(tz=timezone.utc).isoformat()
            return PushUpdateEvent(
                vin=vin,
                event_type=ev_type,
                topic=str(topic),
                timestamp=timestamp,
                raw_payload=dict(data),
            )

        # Legacy fallback: state-key shape with in-payload vin.
        vin = data.get("vin") or raw.get("vin") or default_vin
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
