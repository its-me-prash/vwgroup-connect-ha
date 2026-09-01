# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Constants for VW Group Connect."""

import math
from datetime import datetime, timezone

DOMAIN = "vag_connect"

# Bus event fired by coordinator._on_push_event for each manufacturer push
# notification; consumed by the event platform (per-vehicle EventEntity).
EVENT_PUSH = "vag_connect_push_event"

# Config entry keys
CONF_BRAND                    = "brand"
CONF_USERNAME                 = "username"
CONF_PASSWORD                 = "password"
CONF_SPIN                     = "spin"
# v3.0.0-alpha — companion (ADB) channel. A config entry whose CONF_STRATEGY is
# "companion_adb" is served by the CompanionClient over network ADB instead of
# a CARIAD network client. Host/port point at the spare phone; VIN is the car
# the phone's app shows. EXPERIMENTAL, opt-in from the hub menu.
CONF_STRATEGY                 = "strategy"
STRATEGY_COMPANION_ADB        = "companion_adb"
CONF_ADB_HOST                 = "adb_host"
CONF_ADB_PORT                 = "adb_port"
CONF_VIN                      = "vin"
DEFAULT_ADB_PORT              = 5555
# v2.26.0 (ckomma #21) — wall-clock unix time until which the companion channel
# is rate-limited. Persisted so an account lockout survives an HA restart (an
# in-memory backoff clearing on restart is fine for a TCP blip, dangerous for a
# real lockout). Written by the coordinator after a poll; restored at setup.
CONF_COMPANION_RATE_LIMIT_UNTIL = "companion_rate_limit_until"
# v2.26.0 (C9) — opt-in: also read the charge-target/power/time that live behind
# the charge-detail screen. OFF by default because it TAPS the app to navigate
# there (a forward tap, unlike a plain screen dump); only a user who has
# confirmed the flow on their device should turn it on.
CONF_COMPANION_READ_CHARGE_DETAIL = "companion_read_charge_detail"
# v2.26.0 (#974) — opt-in: wake the phone display before a poll and put it back
# to sleep afterwards, so a locked/asleep phone shows the app (not the keyguard)
# without needing "Stay awake" on permanently. OFF by default.
CONF_COMPANION_WAKE_SLEEP        = "companion_wake_sleep"
# v2.27.0 (#968) — route the companion channel through the ADB Bridge add-on
# instead of talking ADB to the phone directly. Android 11+ wireless debugging
# needs TLS + pairing, which the pure-python transport cannot do, so a modern
# phone can only be driven via the add-on (it bundles the real adb binary).
# When set, CONF_ADB_HOST/PORT address the ADD-ON, not the phone.
CONF_COMPANION_USE_ADDON         = "companion_use_addon"
CONF_COMPANION_ADDON_TOKEN       = "companion_addon_token"
DEFAULT_COMPANION_ADDON_PORT     = 8129
# v4.4.0 (#968) — companion agent relay. Instead of Home Assistant reaching into
# the phone (ADB directly, or the add-on doing it), a small agent app on the
# phone makes an outbound long-poll to HA and takes its commands from the
# response. That removes wireless-debugging pairing, a fixed phone IP and
# client-isolated Wi-Fi from the requirements in one go. When set, no host/port
# is used at all; the random agent token is the entire binding, and it must be
# at least COMPANION_MIN_TOKEN_LEN characters.
CONF_COMPANION_USE_RELAY         = "companion_use_relay"
CONF_COMPANION_AGENT_TOKEN       = "companion_agent_token"
COMPANION_MIN_TOKEN_LEN          = 32
# v4.4.0 (#968) — the deeper companion nav-read opt-ins. Each one TAPS its way
# through the app to reach values the overview does not carry, so each is off by
# default and separately enabled: the odometer + service countdown on the
# Vehicle Health screen (4.3.2 dropped the odometer from the overview), the
# target/outside temperature on the climate detail, and the parking position,
# which is read from the coordinates in the app's own share link.
CONF_COMPANION_READ_VEHICLE_HEALTH   = "companion_read_vehicle_health"
CONF_COMPANION_READ_CLIMATE_DETAIL   = "companion_read_climate_detail"
CONF_COMPANION_READ_PARKING_POSITION = "companion_read_parking_position"
# v2.17.5 (#759) — optional per-VIN S-PIN overrides: {vin: spin}. When a
# vehicle has no entry here the shared CONF_SPIN is used, so existing
# single-S-PIN setups are unchanged. Set via the Options flow.
CONF_SPIN_BY_VIN              = "spin_by_vin"
# v2.15.1 (#503) — Volkswagen US/Canada region selector. VWNorthAmericaClient
# picks the right MYVW client_id + b-h-s.spr.{us|ca}00 host from this value.
# Only consumed by the volkswagen_na brand; every other brand ignores it.
# Backward-compatible default "us" for entries created before this field.
CONF_COUNTRY                  = "country"
# v2.15.0 — durable MBB strategy: optional manual VIN(s). The MBB
# fal-scoped bearer cannot call the account-level usermanagement garage
# endpoint (403 RS.security.9007 XID_APP_VW), so the user supplies the VIN
# directly. Comma/space-separated for multiple cars. Vehicle-level reads +
# commands (VSR / rlu) work fine with the fal token.
CONF_MBB_VINS                 = "mbb_vins"
# b12 — MBB COMMAND CHANNEL layered on a read-only primary (e.g. EU Data Act
# portal for reads). The portal can't command; this arms a durable-MBB
# connector ALONGSIDE it so lock/climate/charge route through MBB while reads
# stay on the portal. Stored separately from the primary's dag_initial_tokens
# so the portal primary is untouched.
CONF_MBB_COMMAND_CHANNEL      = "mbb_command_channel"      # bool: armed?
CONF_MBB_COMMAND_TOKENS       = "mbb_command_tokens"       # dag-shaped dict (strategy=mbb)
CONF_MBB_COMMAND_CLIENT_ID    = "mbb_command_client_id"    # registered X-Client-Id
CONF_MEB_COMMANDS_UNAVAILABLE = "meb_commands_unavailable"  # bool: MEB/ID car, commands requested but impossible
# b15 — MBB COMMAND FALLBACK for a TWO-WAY device-grant primary (e.g. Audi
# Car-Net on the CARIAD BFF). Unlike CONF_MBB_COMMAND_CHANNEL (portal primary →
# MBB *is* the command channel), here the BFF stays the command primary and the
# MBB connector is armed ONLY as a fallback: a command runs on the BFF first and
# re-routes to MBB *only* when the BFF refuses it (401/403 auth refusal), and
# only for MBB-eligible (pre-MEB Car-Net) cars. Škoda pulled its device-grant in
# 2026-08 — this keeps a two-way Audi commandable if VW ever does the same. Reuses
# the CONF_MBB_COMMAND_TOKENS / _CLIENT_ID / _VINS storage (same durable bearer).
CONF_MBB_COMMAND_FALLBACK     = "mbb_command_fallback"     # bool: MBB armed as BFF-refusal fallback?
# 2026-08 — VW EU Two-Way (modern CARIAD BFF) via device-grant client 650d46ca.
# Its 1h Bearer is BFF-whitelisted for reads+commands (the surface vw_eu.py
# drives), unlike the DAG-dead app client / read-only portal client. Because the
# token is NON-refreshable (public client), the runtime RE-MINTS on expiry via a
# cookie-cached silent device-grant confirm (passwordless default) or an opt-in
# stored password. MBB (CONF_MBB_COMMAND_*) stays the Car-Net fallback.
CONF_VWEU_DEVICE_GRANT        = "vweu_device_grant"        # bool: 650d46ca BFF two-way armed?
CONF_VWEU_TWOWAY_TOKENS       = "vweu_twoway_tokens"       # dag-shaped dict (strategy=device_grant)
CONF_VWEU_TWOWAY_COOKIES      = "vweu_twoway_cookies"      # cached 24h/1yr re-auth cookies for silent re-mint
CONF_VWEU_TWOWAY_STORE_PASSWORD = "vweu_twoway_store_password"  # bool: opt-in stored-password auto-confirm fallback
CONF_VWEU_TWOWAY_EMAIL        = "vweu_twoway_email"        # login email for the headless re-mint
CONF_VWEU_TWOWAY_PASSWORD     = "vweu_twoway_password"     # login password (opt-in, stored only if user consents)
CONF_VWEU_TWOWAY_ADDED_EU_PORTAL = "vweu_twoway_added_eu_portal"  # bool: EU-DA supplementary was auto-carried when two-way was enabled (so removal cleans it up)
CONF_SCAN_INTERVAL            = "scan_interval"
CONF_ENABLE_REVERSE_GEOCODING = "enable_reverse_geocoding"
# Optional nameplate NET battery capacity (kWh). VW never reports it and even the
# official app does not derive State of Health, so we cannot guess it (a single
# model name maps to several battery options). When the user supplies it we
# publish battery_soh_pct = current max capacity / nominal. 0 / unset = no SoH.
CONF_BATTERY_NOMINAL_KWH      = "battery_nominal_kwh"
# Optional fuel-tank capacity (litres) — lets a litres-only source (acpp
# plug&play) derive a fuel-level percentage. 0 = off (litres only).
CONF_FUEL_TANK_CAPACITY       = "fuel_tank_capacity"
# P1-5 — opt-in diagnostic archive of raw EU Data Act dataset ZIPs. Default
# off: a raw dataset carries GPS + VIN + telemetry, so keeping the last few on
# disk is a privacy cost the user opts into knowingly. When on, the coordinator
# keeps a small, byte-capped, VIN-hashed per-vehicle ring buffer under
# ``.storage/vag_connect_datasets`` so a wrong/missing-field report can be
# reproduced from the exact bytes the car sent. Snapshot restore-on-restart is
# already handled by the vehicle cache; this is purely a troubleshooting trail.
CONF_KEEP_RAW_DATASETS        = "keep_raw_datasets"
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
# exactly one custom request per VIN at a time.
# v2.17.1 — defaults to ON: portal mode delivers no data at all without a
# request, so opting in by hand was a trap. The kickoff registers a 1-month
# subscription on the user's account, which is free.
# The resolved per-VIN Identifier is persisted under CONF_DATA_ACT_IDENTIFIERS.
CONF_EU_DATA_ACT_AUTO_KICKOFF = "eu_data_act_auto_kickoff"

# Stage-1 one-time historical-export lifecycle. The portal accepts AT MOST ONE
# custom request per VIN at a time, so a one-time export would BLOCK the
# The portal gives the one-time request no terminal state (it can silently
# vanish after submit), so we impose our own client-side deadline; the wedge-guard
# refuses only while OUR OWN one-time export is pending (#923). Persisted per VIN
# as {state, submitted_at}.
CONF_HISTORICAL_EXPORT_STATE = "historical_export_state"
# Past this many seconds a still-pending export is declared timed-out. #923
# (@naked-head) observed a request legitimately still "Gathering your data" on
# the portal past 39h, so the earlier 26h floor timed out real in-flight requests
# and (once the wedge-guard was fixed to key off our own pending state) would let
# a resubmit through that the portal then rejects. 72h leaves a wide margin.
HISTORICAL_EXPORT_DEADLINE_S = 72 * 3600
# Kill-switch — set True to disable the whole one-time lifecycle (button hidden,
# service + kickoff abort). The machinery stays intact; nothing else changes.
ONETIME_EXPORT_DISABLED = False
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

# v2.14.3 — persisted login cookies for the website-authproxy channel. The
# config flow logs in once (incl. email-OTP) and stashes the resulting
# volkswagen.de / vwgroup.io session cookies here in entry.data. At runtime the
# coordinator hands them to the brand client so ``_arm_website_proxy`` hydrates
# the cookie jar BEFORE ``begin_login()`` — an already-authenticated session
# redirects straight back to volkswagen.de WITHOUT re-prompting the email-OTP,
# which was previously raised on every setup/restart. The jar rotates on each
# successful login/refresh, so the coordinator writes the fresh cookies back to
# the entry. STRICTLY additive: only ever read/written for website-authproxy
# entries; absent for every other mode/brand. Value: a list of cookie dicts as
# produced by ``WebsiteAuthProxyConnector.export_cookies``.
CONF_WEBSITE_COOKIES          = "website_cookies"

# v2.15.0b1 (C1) — SUPPLEMENTARY vw.de read channel armed ALONGSIDE a primary
# channel (e.g. an EU-Data-Act-portal entry that also pulls VIN/odometer/service
# from volkswagen.de and merges them). Distinct from CONF_WEBSITE_AUTHPROXY,
# which makes vw.de the SOLE/primary channel: this flag adds vw.de as an extra
# read-only source that the coordinator unions onto the primary snapshot via
# merge_channels. Absent / False = single-channel behaviour, unchanged.
CONF_SUPPLEMENTARY_AUTHPROXY         = "supplementary_authproxy"
# Opt-in test cohort. When a user ticks this, the integration may run EXPERIMENTAL
# reads/probes on their car (e.g. the vw.de parkingposition GPS lever, #923) and
# surface a dismissible Repair asking them to share aggressively-redacted
# diagnostics so a new capability can be confirmed for their model. Default off;
# read ONLY via entry.data (the options listener folds options → data, and
# entry.options is always {} at read time — see [[vag-connect-entry-options-trap]]).
CONF_TEST_COHORT                     = "test_cohort"
# v2.15.0b8 (C1) — supplementary EU Data Act PORTAL read channel (email/pw,
# no OTP) merged onto a command-capable primary like MBB to fill the reads MBB
# can't. Creds stored separately from the primary's (an MBB-QR entry has none).
CONF_SUPPLEMENTARY_EU_PORTAL          = "supplementary_eu_portal"
CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME = "supplementary_eu_portal_username"
CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD = "supplementary_eu_portal_password"
# Persisted vw.de session cookies for the supplementary channel (same shape +
# lifecycle as CONF_WEBSITE_COOKIES, but for the supplementary slot). Written by
# the OptionsFlow "add vw.de read channel" step; read by the coordinator to arm
# the client's _supplementary_authproxy connector at setup.
CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES = "supplementary_authproxy_cookies"
# v2.19.0 (C1) — supplementary TIBBER read channel (OAuth2 auth-code+PKCE against
# the Tibber Data API). A licensed, brand-agnostic EV telemetry source (SoC /
# target SoC / range / plug + charging status) merged onto the primary as the
# LOWEST-trust gap-fill: it only fills fields the first-party channels left empty
# and never overwrites fresher data. Read-only — Tibber exposes no vehicle
# commands. The token bundle {access_token, refresh_token, client_id,
# client_secret} is one dict; the refresh token rotates in place and is persisted
# back here. SECURITY: the token bundle is never logged.
CONF_SUPPLEMENTARY_TIBBER        = "supplementary_tibber"
CONF_SUPPLEMENTARY_TIBBER_TOKENS = "supplementary_tibber_tokens"
# Škoda OFFICIAL public API key (opt-in) — a FAILOVER-ONLY source: read only
# when the primary (unofficial mysmob) channel hard-fails, never polled
# continuously, because the official API is rate-limited to 20 requests/hour/key.
CONF_SKODA_OFFICIAL_API_KEY      = "skoda_official_api_key"

# v2.15.0b3 — "hide entities without data" (default ON). When enabled, data
# sensors / binary sensors whose value hasn't arrived are not created, so a
# device isn't flooded with dozens of "unknown" entities. The per-id dynamic
# spawner re-evaluates each poll, so an entity still appears the moment its
# value first arrives. Controls (lock/climate/button/number/switch) are never
# gated. Set False to show every entity regardless of data.
CONF_HIDE_EMPTY_ENTITIES = "hide_empty_entities"

# v2.15.5 — OPTIONAL ABRP (A Better Routeplanner) live-telemetry push.
# Three opt-in option fields grouped with the other CONF_ENABLE_PUSH_*
# flags. ALL default-dormant: with the enable flag off (or no api_key /
# token) the ABRP sender makes ZERO outbound calls, exactly like the
# other opt-in push features.
#
# CONF_ABRP_ENABLE      — master switch. Default False. When False the
#                         abrp_data_changed binary sensor is not created
#                         and the abrp_send service is a no-op unless
#                         given inline credentials.
# CONF_ABRP_API_KEY     — developer/partner key issued by iternio (per
#                         integration, NOT per user). The user pastes one
#                         they registered with iternio — we deliberately do
#                         NOT ship/hardcode a key (hardcoding one we don't
#                         own would be impersonation + bakes a non-owned
#                         secret into an AGPL public repo). Empty = required
#                         from the service call instead.
# CONF_ABRP_USER_TOKEN  — per-VIN user token from the ABRP app
#                         (Settings → car → Live Data → Generic). Stored as
#                         a {vin: token} dict so multi-VIN accounts each
#                         carry their own token. A bare string is also
#                         accepted (single-VIN convenience) and applied to
#                         every VIN.
# SECURITY: neither value is ever logged — see abrp.redact().
CONF_ABRP_ENABLE              = "abrp_enable"
CONF_ABRP_API_KEY            = "abrp_api_key"
CONF_ABRP_USER_TOKEN         = "abrp_user_token"

# Supported brands — must match CariadClientFactory.create() keys
BRANDS = {
    "audi":           "Audi (myAudi)",
    "volkswagen":     "Volkswagen EU (WeConnect ID)",
    "skoda":          "Škoda (MyŠkoda)",
    "seat":           "SEAT",
    "cupra":          "CUPRA",
    "volkswagen_na":  "Volkswagen US/CA",
    "audi_na":        "Audi US/CA",
    "porsche":        "Porsche (My Porsche)",
    "audi_acpp":      "Audi plug&play (OBD dongle)",
    "skoda_official": "Škoda (official API)",
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
# v2.17.1 (#666 fresh APK sweep) — schemes corrected from the shipping DEX.
# The old values (wecharge/myseat/mycupra/myporsche/vwapp) were launcher
# guesses that don't match each app's registered deep-link scheme.
DEEPLINK_SCHEMES: dict[str, str] = {
    "audi":          "myaudi://",          # DEX: myAudi 5.5.1
    "volkswagen":    "weconnect://",       # DEX: We Connect 4.0.3 (was wecharge://)
    "skoda":         "myskoda://",         # DEX: MySkoda 8.14.0
    "seat":          "seat://",            # DEX: My SEAT 2.19.1 (was myseat://)
    "cupra":         "cupra://",           # DEX: My CUPRA 2.18.1 (was mycupra://)
    "porsche":       "porsche-app://",     # DEX: Porsche One 12.24.27 (was myporsche://)
    "volkswagen_na": "myvw://",            # DEX: myVW 2026.5.27 (was vwapp://)
    "audi_na":       "myaudi://",          # US Audi = same global myAudi app
    "audi_acpp":     "acpp://",            # Audi connect plug&play (de.audi.connectplugandplay)
    "skoda_official": "myskoda://",        # official API keys are managed in the MyŠkoda app
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
MAX_SCAN_INTERVAL     = 60   # minutes — the config-flow selectable ceiling (#1115)

# #1078 — some brands hand out short-lived access tokens, so at the default
# 10-min poll almost every cycle triggers a token refresh. The refresh-storm
# guard (base.py, capped at 3 refreshes/hour to avoid an account lock) then
# trips and the account goes quiet. Škoda is the known case: myskoda's own
# README recommends a 30-min interval, which keeps refreshes at ~2/hour, under
# the storm budget. New setups for these brands start at the recommended value;
# every other brand keeps the 10-min default.
RECOMMENDED_SCAN_INTERVAL: dict[str, int] = {
    "skoda": 30,
    # acpp (Audi plug&play OBD dongle) uploads a snapshot only when the dongle
    # syncs after a drive — polling faster than the car is driven returns
    # identical data and just churns the ~1h rotating token. Hourly reliably
    # catches the post-drive snapshot.
    "audi_acpp": 60,
}


def recommended_scan_interval(brand: str | None) -> int:
    """The suggested default poll interval (minutes) for *brand*.

    Falls back to ``DEFAULT_SCAN_INTERVAL`` for brands with no short-token
    caveat. Case-insensitive; tolerates ``None``.
    """
    return RECOMMENDED_SCAN_INTERVAL.get((brand or "").lower(), DEFAULT_SCAN_INTERVAL)


# How much to step the advice up by when the user already meets our
# recommendation but the storm guard still trips (#1115).
_INTERVAL_STEP_UP_MIN = 15


def advised_scan_interval(brand: str | None, current: int) -> int:
    """The interval to ADVISE in the refresh-storm repair, given *current*.

    #1115 (starwarsfan / Reluca / christianmhz) — the flat per-brand
    recommendation told a user already running 31 minutes to "raise it to 30",
    which reads as nonsense and leaves them nothing to act on. The advice has to
    beat what they already run: once the configured interval meets or exceeds the
    brand recommendation, step up from THEIR value instead of repeating ours.

    ALWAYS clamped to ``MAX_SCAN_INTERVAL`` — the config-flow selectable ceiling.
    The first pass stepped up unclamped and advised 61/75 minutes when the picker
    caps at 60, i.e. an interval the user physically cannot select. When the
    result equals ``current`` the caller sees there is no headroom left to advise
    and suppresses the "raise it" repair instead of asking the impossible.
    """
    base = min(recommended_scan_interval(brand), MAX_SCAN_INTERVAL)
    if not isinstance(current, int) or current < base:
        return base
    return min(current + _INTERVAL_STEP_UP_MIN, MAX_SCAN_INTERVAL)


# An X-RateLimit-Reset at/above this looks like an absolute epoch second (year
# 2001+); a smaller numeric is treated as delta-seconds-until-reset.
_RESET_EPOCH_THRESHOLD = 1_000_000_000


def _seconds_until_reset(
    reset_at: str | int | float | None, now: float
) -> float | None:
    """Normalise an opaque ``X-RateLimit-Reset`` value to seconds from *now*.

    Accepts what the clients actually store: epoch seconds (int/float, or a
    numeric string — base.py stores ``str``, porsche.py an ``int``), an ISO-8601
    timestamp, or a small delta-seconds value. Returns ``None`` when unusable.
    Pure: *now* (epoch seconds) is injected so it is clock-free and testable.
    """
    if reset_at is None:
        return None
    num: float | None
    if isinstance(reset_at, (int, float)):
        num = float(reset_at)
    else:
        try:
            num = float(str(reset_at).strip())
        except (TypeError, ValueError):
            num = None
    if num is not None:
        return (num - now) if num >= _RESET_EPOCH_THRESHOLD else num
    text = str(reset_at).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() - now


def advised_scan_interval_from_budget(
    remaining: int | None,
    reset_at: str | int | float | None,
    now: float,
    current: int,
    *,
    brand: str | None = None,
) -> int:
    """Budget-aware interval advice: spread the REAL remaining calls over the
    time left until the rate-limit window resets.

    Falls back to :func:`advised_scan_interval` (unchanged) whenever the live
    signal is missing — ``remaining is None`` (the ``X-RateLimit-Remaining``
    header was never seen, the default for most installs), or ``reset_at`` gives
    no positive horizon. The budget may only ever *tighten* the advice, never
    drop it below the storm guard (``max(guard, budget_advice)``), so the
    refresh-storm Repair fires in exactly the same cases as before. Clamped to
    ``[MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL]``.

    NOTE: the model assumes ~1 API call per poll cycle; a fan-out poll spends
    more, so this advice is a *lower bound* on the safe interval — safe because
    it can never advise below the guard, but a future ``calls_per_poll`` factor
    could tighten it further.
    """
    guard = advised_scan_interval(brand, current)
    if remaining is None:
        return guard
    seconds = _seconds_until_reset(reset_at, now)
    if seconds is None or seconds <= 0:
        return guard
    if remaining <= 0:
        return MAX_SCAN_INTERVAL
    spread = math.ceil((seconds / 60.0) / remaining)
    budget_advice = max(MIN_SCAN_INTERVAL, min(spread, MAX_SCAN_INTERVAL))
    return max(guard, budget_advice)
