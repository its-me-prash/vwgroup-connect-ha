# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
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
# ``targetTemperature*`` MUST BE OMITTED (upstream PR #644 + #677).
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
# v2.8.0 (Action #5) — preferred auth strategy pin. Set via the
# Repair-flow guided action when a DAG-eligible brand (Audi/Skoda/SEAT/
# CUPRA) silently degrades to hybrid_full. Recording the preference in
# entry.options lets future polls honour the user's choice instead of
# repeatedly retrying DAG. Values: "data_act_portal" (forces read-only
# Data Act portal mode), "" / absent (default — resolver picks).
CONF_PREFERRED_AUTH_STRATEGY  = "preferred_auth_strategy"
# v2.8.0 Action #3 - EU Data Act portal scraper headless-browser
# fallback. Off by default because the playwright dependency is heavy
# (around 100 MB Chromium download) and most users will get usable
# data from the JSON probe in Route A once a credentialed tester
# completes v2.8.1 endpoint discovery. When True AND the active auth
# strategy is data_act_portal AND playwright is installed, the
# coordinator drives a headless browser to click the portal's "Get
# customised data" button. If True but playwright is missing, the
# coordinator surfaces a Repair issue telling the user how to
# install the package inside their HA container.
CONF_ENABLE_DATA_ACT_BROWSER  = "enable_data_act_browser"

# v2.10.0 - Active vehicle wake-up before status poll. Pattern ported
# from the audi_connect_ha v2.1.0 modernization round, observed on
# their commit history but implemented independently here. When True,
# the coordinator POSTs to the brand's wake-vehicle endpoint for any
# VIN that was OFFLINE on the previous poll cycle, sleeps
# CONF_WAKE_DELAY_SECONDS, then runs the regular status fetch. Closes
# the offline-car null-cascade reports (#306 DanielBie SEAT/CUPRA,
# #322 roberttco VW NA) for users who accept the extra API call per
# poll. Off by default because every wake costs one budget unit and
# users with already-online cars get no benefit.
CONF_WAKE_BEFORE_POLL         = "wake_before_poll"
# Seconds to wait between the wake POST and the status fetch. 15 s is
# the empirical default observed across the ecosystem; too low and the
# backend serves stale data because the wake-induced push has not
# arrived yet, too high and the user's poll cycle stretches unhelpfully.
CONF_WAKE_DELAY_SECONDS       = "wake_delay_seconds"
DEFAULT_WAKE_DELAY_SECONDS    = 15

# v2.10.4 - User-supplied OAuth client_id override. Lets a user paste
# a freshly extracted client_id (e.g. from a new APK the community
# captured before our daily atlas builder picked it up, or a beta
# build) without waiting for a release. When set, the AuthConfigResolver
# prepends this value to the top of the oauth_client_id_chain so it
# is tried FIRST. The existing chain (APK-discovered + hardcoded
# alternates + hardcoded canonical) stays in place as fallback. Empty
# string / unset = no override, resolver behaves as before. Format
# must match the canonical "UUID@apps_vw-dilab_com" shape; resolver
# validates and silently drops anything malformed.
CONF_CLIENT_ID_OVERRIDE       = "client_id_override"

# v2.10.5 - EU Data Act portal Custom Data Request auto-kickoff.
# When ON and the integration is operating in read-only data_act_portal
# mode, the coordinator checks for an active 15-min Custom Data Request
# at startup and kicks one off when none exists. The portal accepts
# exactly one custom request per VIN at a time and the kickoff implies
# a 1-month subscription on the user's account, so this stays OFF by
# default; the user has to flip it explicitly. Persisted Identifier
# per VIN lives under CONF_DATA_ACT_IDENTIFIERS in entry.options.
CONF_EU_DATA_ACT_AUTO_KICKOFF = "eu_data_act_auto_kickoff"
CONF_DATA_ACT_IDENTIFIERS     = "data_act_identifiers"

# v2.14.0 — OPT-IN, BETA. When set on a Volkswagen entry, the integration
# authenticates + reads via the volkswagen.de website authproxy (a confidential
# server-side OAuth client on www.volkswagen.de that avoids the Play-Integrity
# wall) instead of the token-based CARIAD BFF. STRICTLY additive: only honoured
# when present + truthy AND brand == "volkswagen"; absent / False = every
# existing path (BFF, EU Data Act portal, native CARIAD) behaves identically.
# The channel is read-only (no remote commands). Chosen explicitly by the user
# via the dedicated "Volkswagen.de website (beta)" config-flow option.
CONF_WEBSITE_AUTHPROXY        = "website_authproxy"

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

# v2.8.0 quick-win B — native-app deeplink schemes per brand. Used by
# the vag_connect.open_app service to emit an event that dashboards can
# subscribe to in order to open the brand's mobile app on iOS/Android.
# Values sourced from each brand's published intent-filter scheme
# (Android AndroidManifest.xml + iOS Info.plist CFBundleURLSchemes).
# Map of brand -> base URL; the action is appended as a path segment
# if the app supports it (the dashboard card decides whether to keep
# or strip the action based on platform behaviour).
#
# v2.10.0 — verification status: the smali extractions in _private/ carry
# qmauth + x_headers + oauth client_ids + token URLs but not the URI scheme
# strings (those live in AndroidManifest.xml + iOS Info.plist, not in the
# decompiled bytecode). Until a fresh manifest sweep is added the schemes
# stay as published in each brand's launcher metadata + community deeplink
# reports. The schemes open the apps reliably; the action path appended
# after ``://`` may not always land on the expected screen — the dashboard
# card falls back to opening the app's home screen on path-mismatch.
DEEPLINK_SCHEMES: dict[str, str] = {
    "audi":          "myaudi://",          # launcher metadata: My Audi
    "volkswagen":    "wecharge://",        # WeConnect ID Charge component (VW)
    "skoda":         "myskoda://",         # launcher metadata: MySkoda
    "seat":          "myseat://",          # launcher metadata: MySEAT
    "cupra":         "mycupra://",         # launcher metadata: My Cupra
    "porsche":       "myporsche://",       # My Porsche app
    "volkswagen_na": "vwapp://",           # VW US Car-Net
}

# Polling interval limits
# v1.17.0 — defaults raised after community research (pycupra
# README + upstream/homeassistant-pycupra release notes): the
# MyCupra/MySeat portal has a per-day API call limit of ~1,500 across
# the official mobile app + integrations. Default 5 min = 288 polls/day
# already eats ~20% of the daily budget BEFORE the official app even
# logs in. Pycupra recommends ≥ 600 s (10 min) by default, ≥ 900 s
# (15 min) when push is enabled. Min raised from 3 min → 5 min.
# Existing entries with explicit lower values are not coerced upward
# at upgrade — only the default for fresh installs changes.
DEFAULT_SCAN_INTERVAL = 10   # minutes (was 5 — see v1.17.0 reasoning)
MIN_SCAN_INTERVAL     = 5    # minutes (was 3 — quota protection)
