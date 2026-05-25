# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Constants for VAG Connect."""

DOMAIN = "vag_connect"

# Config entry keys
CONF_BRAND                    = "brand"
CONF_USERNAME                 = "username"
CONF_PASSWORD                 = "password"
CONF_SPIN                     = "spin"
CONF_SCAN_INTERVAL            = "scan_interval"
CONF_FORCE_ACCESS             = "force_enable_access"
CONF_ENABLE_REVERSE_GEOCODING = "enable_reverse_geocoding"
# v1.12.0 (#63) — Read-only mode. When True, the integration creates
# only status sensors + binary sensors (read-only), no switches/buttons/
# locks/numbers/climate that would send commands. Useful for users who
# want vehicle telemetry but no risk of accidental actuation or
# subscription-counting commands.
CONF_READ_ONLY                = "read_only_mode"
# v1.14.0 (#29 + #51 Facelift) — PPE/PPC Climate body conditional.
# Audi-only option (default False). When True, ``command_start_climate``
# uses the PPE body shape — ``climatisationMode: "comfort"`` mandatory,
# ``targetTemperature*`` MUST BE OMITTED (audi_connect_ha PR #644 + #677).
# Auto-detection from VIN/model/year is unreliable (no public PPE list);
# user-overridable until we have a proper detection mechanism.
CONF_FORCE_PPE_CLIMATE        = "force_ppe_climate"
# v1.18.0 (#57 Push Bundle, foundation phase) — opt-in toggle for
# Skoda mysmob MQTT push updates. Default False because:
# (1) requires aiomqtt + firebase-messaging deps (not yet in
#     manifest, lazy-imported in cariad/push/skoda_mqtt.py)
# (2) live activation pending community tester validation
# (3) only meaningful for brand=skoda (other brands ignore)
# When True + brand=skoda + deps installed: SkodaPushManager spawns
# at coordinator setup and forwards backend events to
# coordinator.async_handle_push_event for near-real-time refresh.
CONF_ENABLE_PUSH_MQTT         = "enable_push_mqtt"
# v1.19.0 (#57 Push Bundle, foundation phase) — opt-in toggle for
# CUPRA/SEAT OLA Firebase Cloud Messaging push updates. Default
# False because:
# (1) requires firebase-messaging dep (lazy-imported in
#     cariad/push/cupra_seat_fcm.py — same dep that v1.18.0 lazy-
#     imports for Skoda MQTT TOTP, so opting into either backend
#     triggers the same install requirement)
# (2) live activation pending community tester (CUPRA/SEAT owner
#     with active subscription) for FCM project + sender_id
#     verification
# (3) only meaningful for brand in {cupra, seat} — others ignore
# When True + brand matches + dep installed: CupraSeatPushManager
# spawns at coordinator setup, registers FCM, POSTs OLA
# subscription, forwards events to coordinator.
CONF_ENABLE_PUSH_FCM          = "enable_push_fcm"
# v1.23.0 (#57 Push Bundle, foundation phase) — opt-in toggle for
# Audi/VW Cariad-BFF Firebase Cloud Messaging push updates. Default
# False because:
# (1) requires firebase-messaging dep (lazy-imported in
#     cariad/push/audi_vw_fcm.py — same dep as Skoda v1.18.0 +
#     CUPRA/SEAT v1.19.0)
# (2) live activation pending community tester (Audi/VW owner with
#     active Connect+ subscription) for FCM project + sender_id +
#     notification-subscription endpoint verification
# (3) only meaningful for brand in {audi, volkswagen} — others ignore
# When True + brand matches + dep installed: AudiVWPushManager
# spawns at coordinator setup. User-suggested feature 2026-05-07
# (myAudi App push notifications → HA-side feedback channel).
CONF_ENABLE_PUSH_AUDI_VW      = "enable_push_audi_vw"
# v2.4.1 (#281+#282) — OLA app-identifying header overrides for power-
# users (SEAT/CUPRA only). VW Group's OLA backend enforces specific
# values for ``app-version`` + ``User-Agent`` on every request. We
# default to the latest-known-good values from
# ``cariad/_ola_headers.py`` (mirrored from CarConnectivity-connector-
# seatcupra). If the backend changes faster than we release, users can
# override here without waiting for an integration update.
# Empty string = use the built-in default. Format: plain version
# string ("2.17.0") or full User-Agent string per RFC 7231.
CONF_OLA_APP_VERSION_OVERRIDE = "ola_app_version_override"
CONF_OLA_USER_AGENT_OVERRIDE  = "ola_user_agent_override"

# Supported brands — must match CariadClientFactory.create() keys
BRANDS = {
    "audi":           "Audi (myAudi)",
    "volkswagen":     "Volkswagen EU (WeConnect ID)",
    "skoda":          "Škoda (MyŠkoda)",
    "seat":           "SEAT",
    "cupra":          "CUPRA",
    "volkswagen_na":  "Volkswagen US/CA",
    "porsche":        "Porsche (My Porsche)",
}

# Polling interval limits
# v1.17.0 — defaults raised after community research (pycupra
# README + WulfgarW/homeassistant-pycupra release notes): the
# MyCupra/MySeat portal has a per-day API call limit of ~1,500 across
# the official mobile app + integrations. Default 5 min = 288 polls/day
# already eats ~20% of the daily budget BEFORE the official app even
# logs in. Pycupra recommends ≥ 600 s (10 min) by default, ≥ 900 s
# (15 min) when push is enabled. Min raised from 3 min → 5 min.
# Existing entries with explicit lower values are not coerced upward
# at upgrade — only the default for fresh installs changes.
DEFAULT_SCAN_INTERVAL = 10   # minutes (was 5 — see v1.17.0 reasoning)
MIN_SCAN_INTERVAL     = 5    # minutes (was 3 — quota protection)
