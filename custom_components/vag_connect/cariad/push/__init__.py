# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Push-update infrastructure for VAG Connect.

Today VAG Connect polls each backend every N minutes (default 10 min).
Push updates would let the integration receive change events in
seconds rather than minutes — eliminating the 12V wake-cycle for
real-time status changes.

This package houses the push-client implementations:

- ``skoda_mqtt`` (v1.18.0 foundation, v1.18.x+ live activation) —
  Skoda mysmob MQTT broker at mqtt.messagehub.de:8883. MQTTv5 with
  TOTP auth credentials derived from a Firebase Cloud Messaging
  token. Topic pattern: ``{user_id}/{vin}/+/+`` for change events.

- ``cupra_seat_fcm`` (v1.19.0+) — CUPRA/SEAT push via Firebase
  Cloud Messaging. POST a registered FCM token to
  ``/v2/subscriptions`` on OLA, listen for push notifications
  through firebase-messaging library.

Both backends use the same ``firebase-messaging`` Python lib (Skoda
needs it for the MQTT TOTP auth credential, CUPRA/SEAT needs it for
the actual push transport).

### Foundation status (v1.18.0)

The classes below define the **interface and lifecycle** for push
managers. The actual MQTT/FCM client code is **lazy-imported on
demand** — the integration runs without the deps installed unless
the user opts in via the OptionsFlow toggle. This avoids:

1. Bloating non-Skoda installs with MQTT + FCM Python packages
2. Risking HACS install failures on environments where the wheels
   aren't available
3. Shipping untested production code paths to users who don't need
   push

### Wire-up plan (post-foundation)

1. User enables ``enable_push_mqtt`` option (default OFF) for Skoda
2. ``__init__.async_setup_entry`` spawns ``SkodaPushManager.start()``
3. Manager imports ``aiomqtt`` lazily; if missing, surfaces a clear
   error via persistent_notification ("pip install aiomqtt") and
   falls back to polling
4. Manager calls back into ``coordinator.async_handle_push_event``
   on each MQTT message; coordinator triggers a fresh ``get_status``
   pull and ``async_set_updated_data``
5. On unload / option-disabled / token-rotation: clean shutdown via
   ``stop()``

### Privacy

Tokens (OAuth, FCM, TOTP) are NEVER logged. VINs are masked to last
6 chars in all log lines. MQTT user_id is masked the same way.

References:

- Skoda MQTT: skodaconnect/myskoda PR #566 (TOTP auth) + const.py
  (broker URL, topic pattern)
- CUPRA/SEAT FCM: upstream/homeassistant-pycupra firebase.py +
  connection.py
- evcc cross-reference: vehicle/vw/api.go (no push, polling-only —
  validates that push is a real differentiator vs evcc)
"""

from .base import PushManager, PushUpdateEvent

__all__ = ["PushManager", "PushUpdateEvent"]
