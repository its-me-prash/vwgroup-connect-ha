# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Data models for the CARIAD API client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BrandConfig:
    """Per-brand constants for IDK authentication and API access."""

    name: str
    client_id: str
    redirect_uri: str
    user_agent: str
    api_base: str
    client_secret: str = ""
    scope: str = (
        "openid profile badge birthdate birthplace nationalIdentifier "
        "nationality profession email vin phone nickname name picture mbb "
        "gallery cars dealers"
    )
    # v2.5.11 (#brand-impersonation-fix) — Android package name sent in
    # the ``x-android-package-name`` header on CARIAD-BFF token requests.
    # Pre-v2.5.11 this was hardcoded to ``de.myaudi.mobile.assistant``
    # in idk.py for ALL brands — a latent brand-impersonation bug that
    # would have broken VW EU instantly if Azure WAF flipped on the
    # brand-consistency anomaly check. Documented in our own atlas
    # profile (vw_group_auth_profile.json) as the correct per-brand
    # value all along, but the code didn't match. v2.5.11 wires the
    # atlas truth through to the wire.
    #
    # Used by: ``_cariad_token_headers()`` in idk.py for the CARIAD-BFF
    # token endpoint (Audi + VW EU). Other brands hit different IDPs
    # that don't enforce this header — value provided defensively for
    # future-proofing but not currently transmitted on their flows.
    android_package_name: str = ""

    @property
    def app_prefix(self) -> str:
        """Scheme prefix used to detect auth redirect (e.g. 'myaudi')."""
        return self.redirect_uri.split("://")[0]


# All client IDs sourced from MIT/Apache-2.0 open-source projects.
# See docs/research/VAG_GROUP_ECOSYSTEM.md for full attribution.

BRAND_VW_EU = BrandConfig(
    name="volkswagen",
    client_id="a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com",
    redirect_uri="weconnect://authenticated",
    user_agent="Volkswagen/3.51.1-android/14",
    api_base="https://emea.bff.cariad.digital",
    # scope from volkswagencarnet (upstream/volkswagencarnet, MIT) — confirmed working
    scope="openid profile badge cars dealers vin",
    # v2.5.11 — matches atlas profile vw_group_auth_profile.json#brands.vw.package_name.
    # Source: VW WeConnect 3.61.0 APK xapk archive name + ioBroker commit 884269b1.
    # Pre-v2.5.11 this was silently impersonating the Audi package via the
    # hardcoded ``de.myaudi.mobile.assistant`` default in idk.py.
    android_package_name="de.volkswagen.weconnect",
)

BRAND_AUDI = BrandConfig(
    name="audi",
    # client_id from upstream (arjenvrh/upstream, MIT) — confirmed working
    client_id="09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
    redirect_uri="myaudi:///",
    user_agent="Android/4.31.0 (Build 800341641.root project 'myaudi_android'.ext.buildTime) Android/13",
    api_base="https://emea.bff.cariad.digital",
    # scope exactly matching upstream — no extra "cars"/"dealers" scopes
    scope=(
        "address profile badge birthdate birthplace nationalIdentifier nationality "
        "profession email vin phone nickname name picture mbb gallery openid"
    ),
    # v2.5.11 — matches atlas profile vw_group_auth_profile.json#brands.audi.package_name.
    # Source: myAudi 5.4.1 APK archive name + upstream source.
    android_package_name="de.myaudi.mobile.assistant",
)

BRAND_SKODA = BrandConfig(
    name="skoda",
    client_id="7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com",
    redirect_uri="myskoda://redirect/login/",
    user_agent="MySkoda/1.0 Android",
    api_base="https://mysmob.api.connect.skoda-auto.cz",
    scope=(
        "address badge birthdate cars driversLicense dealers email mileage mbb "
        "nationalIdentifier openid phone profession profile vin"
    ),
    # v2.5.11 — Skoda IDP not on CARIAD-BFF (uses mysmob.api.connect.skoda-auto.cz),
    # so x-android-package-name is not currently transmitted. Value
    # provided defensively for future-proofing / atlas consistency.
    android_package_name="cz.skodaauto.myskoda",
)

BRAND_SEAT = BrandConfig(
    name="seat",
    client_id="99a5b77d-bd88-4d53-b4e5-a539c60694a3@apps_vw-dilab_com",
    redirect_uri="seat://oauth-callback",
    user_agent="OLASeat/2.13.3 (Android 12; sdk_gphone64_x86_64; Google) Mobile",
    api_base="https://ola.prod.code.seat.cloud.vwgroup.com",
    # `address` + `email` mirror the official My SEAT app — defense in depth so
    # OLA endpoints that conditionally require either claim never get tripped.
    scope="openid profile address phone email birthdate nickname",
    # v2.5.11 — SEAT/CUPRA hit OLA backend (different from CARIAD-BFF), so
    # x-android-package-name not currently used in their flows. The OLA
    # backend uses ``app-brand`` (see _ola_headers.py) which we already set.
    android_package_name="com.seat.myseat.ola",
)

BRAND_CUPRA = BrandConfig(
    name="cupra",
    client_id="3c756d46-f1ba-4d78-9f9a-cff0d5292d51@apps_vw-dilab_com",
    redirect_uri="cupra://oauth-callback",
    user_agent="OLACupra/2.15.0 (Android 12; sdk_gphone64_x86_64; Google) Mobile",
    api_base="https://ola.prod.code.seat.cloud.vwgroup.com",
    client_secret="eb8814e641c81a2640ad62eeccec11c98effc9bccd4269ab7af338b50a94b3a2",
    # See BRAND_SEAT above — same OLA backend, same scope set.
    scope="openid profile address phone email birthdate nickname",
    android_package_name="com.cupra.mycupra",
)

BRAND_VW_NA_MODEL = BrandConfig(
    name="volkswagen_na",
    client_id="59992128-69a9-42c3-8621-7942041ba824_MYVW_ANDROID",
    redirect_uri="kombi:///login",
    user_agent="MyVW/1.0 Android",
    api_base="https://b-h-s.spr.us00.p.con-veh.net",
    # v2.3.0 (#269) — single ``openid`` scope per matpoulin's working
    # NA flow. Wider EU-style scope chain was the trigger for HTTP 400.
    scope="openid",
)

BRAND_PORSCHE = BrandConfig(
    name="porsche",
    client_id="XhygisuebbrqQ80byOuU5VncxLIm8E6H",
    redirect_uri="my-porsche-app://auth0/callback",
    user_agent="My Porsche/2.1.0 (iPhone; iOS 17.0; Scale/3.00)",
    api_base="https://api.ppa.porsche.com",
    scope="openid profile email offline_access mbb vin cars charging",
)

# v2.2.0 Phase 4 PR #15/20 — Lamborghini brand-adapter scaffold.
#
# **BETA — TESTER VALIDATION PENDING.** This brand-config is NOT wired
# into the ``BRANDS`` registry / config-flow / factory yet — it ships
# as scaffolding only so a tester can import the class directly and
# manually exercise the IDK flow against the Lamborghini Unica app
# to validate the client_id + redirect_uri.
#
# Inheritance rationale: Lamborghini Unica is a VAG luxury brand
# fronted by the same Cariad-BFF backend as VW EU + Audi (verified
# via API-Evangelist OpenAPI catalog metadata 2026-05-03 — same
# ``emea.bff.cariad.digital`` host). So the data-fetch path inherits
# unchanged from ``VWEUClient`` — only the brand-token + UA differ.
#
# Placeholder values below MUST be replaced by a tester with a
# Lamborghini Unica app install (Android/iOS) inspecting the
# OAuth flow with mitmproxy / Charles. Until then, attempting to
# use this brand WILL fail at the IDK login step with HTTP 400.
#
# Activation in v2.2.x or v2.3.x once tester returns confirmed
# values. The wiring into ``BRANDS`` + factory + config-flow is
# a separate (one-liner) PR once values are known.
BRAND_LAMBO = BrandConfig(
    name="lambo",
    client_id="PLACEHOLDER-lambo-tester-please-confirm@apps_vw-dilab_com",
    redirect_uri="unica://oauth-callback",
    user_agent="Unica/1.0.0 Android",
    api_base="https://emea.bff.cariad.digital",
    # Scope inherited from VW EU + Audi pattern; tester may need to
    # adjust if the Lamborghini app uses a tighter or wider claim set.
    scope="openid profile badge cars vin",
)

# v2.2.0 Phase 4 PR #16/20 — Bentley brand-adapter scaffold.
#
# **BETA — TESTER VALIDATION PENDING.** Same pattern as ``BRAND_LAMBO``
# (PR #15) — scaffolding-only, NOT wired into the ``BRANDS`` registry
# / config-flow / factory yet.
#
# Inheritance rationale: Bentley "My Bentley" app is a VAG luxury
# brand fronted by the same Cariad-BFF backend as VW EU + Audi +
# Lamborghini (verified via API-Evangelist OpenAPI catalog metadata
# 2026-05-03 — same ``emea.bff.cariad.digital`` host). So the data-
# fetch path inherits unchanged from ``VWEUClient`` — only the
# brand-token + UA differ.
#
# Placeholder values below MUST be replaced by a tester with a My
# Bentley app install (Android/iOS) inspecting the OAuth flow with
# mitmproxy / Charles. Until then, attempting to use this brand
# WILL fail at the IDK login step with HTTP 400.
#
# Activation in v2.2.x or v2.3.x once tester returns confirmed
# values — one-liner factory + BRANDS registry addition.
BRAND_BENTLEY = BrandConfig(
    name="bentley",
    client_id="PLACEHOLDER-bentley-tester-please-confirm@apps_vw-dilab_com",
    redirect_uri="mybentley://oauth-callback",
    user_agent="MyBentley/1.0.0 Android",
    api_base="https://emea.bff.cariad.digital",
    # Scope inherited from VW EU + Audi pattern; tester may need to
    # adjust if the Bentley app uses a tighter or wider claim set.
    scope="openid profile badge cars vin",
)

# v2.2.0 Phase 4 PR #17/20 — CUPRA-standalone brand-adapter scaffold.
#
# **BETA — TESTER VALIDATION PENDING.** Pattern matches BRAND_LAMBO
# (#15) + BRAND_BENTLEY (#16): scaffolding-only, NOT wired into the
# ``BRANDS`` registry / config-flow / factory yet.
#
# **What's distinct from existing BRAND_CUPRA**: the current CUPRA
# integration goes through the shared SEAT/CUPRA OLA backend
# (``ola.prod.code.seat.cloud.vwgroup.com``). Per pycupra commit
# 0f3b1c7 + multiple 2026-Q1/Q2 community reports, SEAT and CUPRA
# Connect are progressively migrating to brand-isolated backends —
# pycupra tracks a ``cupra-api.vwgroup.io`` host for the CUPRA-only
# rollout that's expected to fully cut over by 2026-H2.
#
# This scaffold reserves the brand-id ``"cupra_standalone"`` and the
# placeholder host so tester can:
#   1. confirm the actual host once their account flips
#   2. exercise the parser against the cut-over response shapes
#   3. report back which endpoints stayed identical vs. drifted
#
# Once tester confirms host + any endpoint shape deltas, activation
# is a 1-line factory PR PLUS any necessary parser-divergence
# fixes (most fields expected to be identical — OLA-flavoured JSON
# rather than CARIAD-BFF-flavoured).
#
# Until then: factory rejects "cupra_standalone", UI hides it,
# existing "cupra" users see zero behaviour change.
BRAND_CUPRA_STANDALONE = BrandConfig(
    name="cupra_standalone",
    # Same OAuth client as legacy CUPRA — the IDK login flow is
    # unchanged; only the post-auth API base differs.
    client_id="3c756d46-f1ba-4d78-9f9a-cff0d5292d51@apps_vw-dilab_com",
    redirect_uri="cupra://oauth-callback",
    user_agent="OLACupra/2.15.0 (Android 12; sdk_gphone64_x86_64; Google) Mobile",
    # PLACEHOLDER — tester must confirm the actual host once the
    # backend cut-over reaches their account. Until then, attempts
    # to fetch data WILL fail with DNS error.
    api_base="https://PLACEHOLDER-cupra-api.vwgroup.io",
    client_secret="eb8814e641c81a2640ad62eeccec11c98effc9bccd4269ab7af338b50a94b3a2",
    scope="openid profile address phone email birthdate nickname",
)

BRANDS: dict[str, BrandConfig] = {
    "volkswagen":    BRAND_VW_EU,
    "audi":          BRAND_AUDI,
    "skoda":         BRAND_SKODA,
    "seat":          BRAND_SEAT,
    "cupra":         BRAND_CUPRA,
    "volkswagen_na": BRAND_VW_NA_MODEL,
    "porsche":       BRAND_PORSCHE,
}


@dataclass
class TokenSet:
    """OAuth2 token bundle from IDK."""

    access_token: str
    refresh_token: str
    id_token: str
    expires_at: float = 0.0  # Unix timestamp — 0 = unknown, refresh proactively 60s before
    # v2.6.0 — auth strategy that produced this token set. Coordinator
    # uses this to decide refresh behaviour: hybrid_full / data_act_portal
    # have no refresh_token, so refresh = full re-login. classic flows
    # can use refresh_token. Strategy values: "classic" | "hybrid_full"
    # | "data_act_portal" | "device_grant" | "" (legacy/unknown).
    strategy: str = ""

    # v2.8.0 — persisted Auth0 / IDP session cookies (vwgroup.io domain
    # only). The IDP issues a "device-bound" cookie after a successful
    # email-OTP challenge that suppresses the OTP prompt for ~30 days
    # on the same device fingerprint. Without persistence, every fresh
    # session (HA restart, integration reload) re-prompts the user for
    # the OTP, which combined with the hybrid_full 2h-relogin cycle
    # turns into a hostile UX. Each entry is a small dict with the
    # subset of fields aiohttp needs to round-trip a Morsel:
    #   {"name": ..., "value": ..., "domain": ..., "path": ...,
    #    "expires": ..., "secure": ..., "httponly": ...}
    auth_cookies: list[dict[str, Any]] = field(default_factory=list)

    def is_valid(self) -> bool:
        """Return True if the access_token + id_token are populated.

        v2.6.0 — refresh_token is intentionally optional. Hybrid flow
        and Data Act portal both produce token sets WITHOUT a refresh
        token; the coordinator handles those via full re-login when
        the access_token expires.
        """
        return bool(self.access_token and self.id_token)

    def needs_refresh(self) -> bool:
        """True if token expires within 60 seconds or expiry is unknown."""
        if not self.expires_at:
            return False  # unknown → let the API tell us via 401
        import time
        return time.time() >= self.expires_at - 60


@dataclass
class VehicleData:
    """Unified vehicle data model — brand-agnostic.

    All fields are Optional so partial data never raises KeyError.
    Coordinator maps this to its vehicles dict.
    """

    vin: str
    model: str | None = None
    model_year: int | None = None
    manufacturer: str | None = None
    firmware_version: str | None = None
    license_plate: str | None = None

    # Render images — dict of mediaType → public URL (fetched via GraphQL, no auth needed to GET)
    # e.g. {"MYAPN8NB": "https://mediaservice.audi.com/media/fast/v3_...", ...}
    image_urls: dict = None  # type: ignore[assignment]
    # Vehicle media names from GraphQL (vehicle.media.shortName/longName)
    # Warning lights — v2.0.1 (#131 follow-up): switched from
    # ``bool = False`` to ``bool | None = None`` so that a parser miss
    # (Backend-Hiccup, .error envelope, missing field, unknown firmware
    # value) leaves the entity ``unknown`` rather than falsely "no
    # warning". The previous default-False masked real warnings during
    # the Cariad-BFF nightly maintenance windows (see #190 for an
    # example backend-hiccup that flipped 17 fields to .error envelope).
    warning_active: bool | None = None
    warning_count: int = 0
    warning_oil: bool | None = None
    warning_engine: bool | None = None
    warning_tyre: bool | None = None
    warning_brakes: bool | None = None
    # v2.7.0b11 — comma-joined string of every warning the backend
    # reports (type plus text when present). Surfaces brand-specific
    # warning types (Audi STO/towing-bracket, etc) that the hardcoded
    # warning_oil/engine/brake/tyre family above misses. Empty string
    # when no warnings active, None when the warning endpoint failed.
    warning_messages: str | None = None

    media_short_name: str | None = None  # e.g. "Q4 e-tron"
    media_long_name: str | None = None   # e.g. "Audi Q4 50 e-tron quattro"
    media_exterior_color: str | None = None

    def __post_init__(self) -> None:
        """Initialise mutable defaults."""
        if self.image_urls is None:
            self.image_urls = {}

    # Drivetrain
    is_electric: bool = False
    has_battery: bool = False
    has_combustion: bool = False
    is_hybrid: bool = False

    # Range & energy
    battery_soc: int | None = None
    battery_available_kwh: float | None = None
    battery_cap_kwh: float | None = None
    battery_temp: float | None = None
    fuel_level: int | None = None
    range_km: int | None = None
    # v1.10.0 (#94 — PHEV range triple).
    # ``range_km`` stays as the headline number (back-compat — existing
    # automations and dashboards keep working). Three new explicit fields
    # let PHEVs and EVs surface what the API actually distinguishes:
    #   electric_range_km — battery-only remaining range
    #   combustion_range_km — petrol/diesel/CNG/LPG remaining range
    #   total_range_km — combined range (only meaningful for hybrids)
    # Brand clients populate these from per-engine blocks
    # (``fuelStatus.rangeStatus.value.{primaryEngine,secondaryEngine}``
    # plus ``measurements.rangeStatus.value.{dieselRange,gasolineRange}``
    # for older Audi models). Conditional sensor creation in sensor.py
    # uses ``is not None`` so pure EVs never get a phantom combustion
    # entity and pure ICE never get an electric one.
    electric_range_km: int | None = None
    combustion_range_km: int | None = None
    total_range_km: int | None = None
    range_estimated_full_km: int | None = None
    range_wltp_km: int | None = None
    odometer_km: int | None = None

    # Charging
    charging_state: str | None = None
    # v2.0.1 (#131 follow-up) — switched ``is_charging`` /
    # ``plug_connected`` / ``auto_unlock_charge`` / ``connector_locked``
    # from ``bool = False`` to ``bool | None = None``. Same false-
    # negative reasoning as ``doors_locked`` above: parser-miss on a
    # backend-hiccup must NOT default to "not charging" / "plug
    # disconnected" / "connector unlocked" — that hides real state.
    # ``connector_locked`` is the most safety-relevant of these (LOCK
    # device class) — user can't pull a still-locked plug, so a
    # wrong-False masks a real "you can't unplug yet" state.
    is_charging: bool | None = None
    plug_state: str | None = None
    plug_connected: bool | None = None
    charging_power_kw: float | None = None
    charging_rate_kmh: float | None = None
    charge_complete_eta: Any | None = None
    charging_type: str | None = None
    target_soc: int | None = None
    max_charge_current: float | None = None
    min_soc: int | None = None  # Minimum SoC for departure timer (PHEV)
    auto_unlock_charge: bool | None = None
    connector_locked: bool | None = None
    charging_station_name: str | None = None
    charging_station_address: str | None = None
    charging_station_kw: float | None = None
    charging_station_operator: str | None = None
    charge_mode: str | None = None  # MANUAL | TIMER | PREFERRED_CHARGING_TIMES | IMMEDIATE_DISCHARGING
    # v1.27.2 — Cariad scout #181 (Audi): pending charging-settings change
    # requests count. Useful diagnostic for "did my putChargingSettings POST
    # actually queue?" Plus visual feedback signals from plugStatus.
    charging_settings_pending: int | None = None
    # v2.2.3 — Cariad scout #268 (VW EU arvcer): mirror of the
    # ``chargingSettings.requests`` queue but for chargingStatus side
    # (i.e. queued ``start_charging`` / ``stop_charging`` commands).
    # Same int-count diagnostic, same None semantics.
    charging_status_pending: int | None = None
    # v2.2.3 — Cariad scout #272 (VW EU arvcer 2026-05-23): third
    # member of the *.requests family — counts queued
    # ``start_climatisation`` / ``stop_climatisation`` commands at the
    # gateway. Same shape as ``charging_*_pending`` siblings.
    climatisation_status_pending: int | None = None
    # v2.4.1 — Cariad scout #283 (VW EU Brinki99 2026-05-24): fourth
    # *_pending family member — counts queued
    # ``set_climatisation_temperature`` / ``set_window_heating`` /
    # related climate-settings commands at the gateway.
    climatisation_settings_pending: int | None = None
    # v2.4.1 — Scout Policy Compliance Audit (see docs/SCOUT_POLICY.md).
    # T1 entities: previously silenced-only paths that have been
    # promoted to first-class parsed fields per the new "always parse"
    # policy. All disabled-by-default in sensor.py (opt-in for users
    # who actually need them).
    #
    # CARIAD-BFF: HV battery cell temperature (Celsius). Useful for
    # users with home battery-thermal management (e.g. wallbox curtail).
    battery_temp_c: float | None = None
    # CARIAD-BFF climatisation: per-zone enable + battery-only mode.
    climate_without_external_power: bool | None = None
    climate_zone_front_left: bool | None = None
    climate_zone_front_right: bool | None = None
    # CARIAD-BFF climatisation: remaining-time-to-target.
    climate_remaining_time_min: int | None = None
    # CARIAD-BFF readiness: connection diagnostics. Already partly
    # surfaced via legacy fields; these are the deeper sub-keys.
    connection_battery_power_level: str | None = None  # e.g. "OK", "LOW"
    connection_active: bool | None = None
    daily_power_budget_warning: bool | None = None
    insufficient_battery_level_warning: bool | None = None
    # OLA (SEAT/CUPRA): per-vehicle metadata from /v2/users/.../garage.
    # NOTE: ``license_plate`` already defined at the top of the dataclass
    # (line ~264) — populated by other parsers historically. v2.4.1 T1
    # adds the SEAT/CUPRA parser path; the field declaration stays
    # singular to avoid mypy [no-redef] error.
    vehicle_nickname: str | None = None
    # OLA: parking position map renders (Google Maps URLs from /v1/vehicles/{vin}/parkingposition).
    parking_map_url_dark: str | None = None
    parking_map_url_light: str | None = None
    # v2.3.0 — Cariad scout #264 (Audi moltke69 2026-05-19) — route-aware
    # smart-charging fields. Backend nun publishes a "navigation-aware"
    # SoC target — z.B. "lade nur soviel wie du für deine nächste
    # Navigation brauchst" — und die companion remaining-time bis dieses
    # nav-target erreicht ist. Distinct semantics von static target_soc
    # + remaining_charge_time, deshalb separate fields.
    # From ``charging.batteryStatus.value.navigationTargetSOC_pct``.
    nav_target_soc_pct: int | None = None
    # From ``charging.chargingStatus.value.remainingChargingTimeNavigation_min``.
    remaining_charge_time_nav_min: int | None = None
    plug_led_color: str | None = None  # none / red / green / blue
    external_power_available: bool | None = None  # plugStatus.externalPower

    # Climate
    climatisation_state: str | None = None
    # v2.0.1 (#131 follow-up) — same false-negative reasoning as the
    # Access block: parser-miss must NOT default to "climate off".
    climatisation_active: bool | None = None
    target_temperature: float | None = None
    outside_temp: float | None = None
    # v2.1.0 — Skoda climate-ready-at (closes Scout #186 + #188).
    # ISO-8601 timestamp when the cabin is expected to reach
    # ``target_temperature``. Only populated during active climate
    # run; remains None when climatisation is OFF. Skoda-only field
    # today — other brands' status endpoints don't expose it.
    # Brand-restricted via _DATA_PRESENT_REQUIRED in sensor.py.
    climate_ready_at: Any | None = None

    # Access
    # v2.0.1 (#131 user-reported follow-up): switched from
    # ``bool = False`` to ``bool | None = None`` to fix a critical
    # safety false-negative: when the parser couldn't extract the lock
    # state from the response (Backend-Hiccup .error envelope, missing
    # field, unknown firmware value) the dataclass default was False,
    # so the binary_sensor + lock entity displayed "Unlocked" for an
    # actually-locked car. Cars now correctly show "Unknown" instead.
    # The lock entity (lock.py:is_locked) and the binary_sensor (with
    # LOCK device_class invert) both already handle ``None`` as
    # "unknown" — no entity-side change needed.
    doors_locked: bool | None = None
    doors_open: bool | None = None
    windows_open: bool | None = None
    doors_individual: dict[str, bool] = field(default_factory=dict)
    # v1.8.9 (Session 3C) — per-window state, mirrors ``doors_individual``.
    # Keys: frontLeft / frontRight / rearLeft / rearRight. Value True ==
    # window closed, False == open. Populated by SEAT/CUPRA OLA paths
    # (status.windows.{position}); other brands leave it empty for now.
    windows_individual: dict[str, bool] = field(default_factory=dict)

    # Location
    latitude: float | None = None
    longitude: float | None = None
    parking_address: str | None = None
    parking_city: str | None = None
    heading: int | None = None

    # Status
    vehicle_state: str | None = None
    connection_state: str | None = None
    # v2.0.1 (#131 follow-up) — same false-negative reasoning. Parser
    # miss must NOT default to "vehicle parked + offline". Conditional
    # automations like "wake car when leaving driveway" relied on
    # ``is_online`` being honest about its uncertainty.
    is_driving: bool | None = None
    is_online: bool | None = None
    last_updated_at: Any | None = None
    # v1.8.11 (Session 3S) — when the *vehicle* last reported data to the
    # backend, derived from ``carCapturedTimestamp`` on the status response
    # sub-objects. ``last_updated_at`` above tracks when we last *polled*
    # the backend; this tracks when the backend last actually heard from
    # the car. The two diverge during weekend backend outages, when the
    # car is asleep, or when 12V drops too low to send heartbeats.
    # Currently populated by SkodaClient; other brands keep it None until
    # they grow analogous parsing.
    last_seen_at: Any | None = None

    # Service
    service_km: int | None = None
    service_due_at: Any | None = None
    oil_service_km: int | None = None
    oil_service_at: Any | None = None
    # v1.11.0 (#91 closure) — explicit "raw int days" sensors complementing
    # the existing DATE sensors. The DATE conversion (sensor.py) loses the
    # exact day count; users who want "5 days remaining" instead of
    # "May 5, 2026" can read these directly. Populated by brand parsers
    # from the same backend integers. Keep both fields populated so the
    # DATE-class sensor and the int sensor both work.
    service_due_in_days: int | None = None
    oil_service_due_in_days: int | None = None
    # v1.17.7 (#130 Chr1sDub + #133 christianmhz — two converging Skoda
    # Scout-Reports 2026-05-04). Skoda mysmob now exposes the user's
    # registered preferred-workshop info on the maintenance endpoint.
    # Surfaced as extra_state_attributes on the ``service_due_in_days``
    # sensor (see sensor.py) so users see workshop name + contact
    # alongside the "next service in X days" number. Dict shape is
    # whatever the backend ships — typical keys: name, brand,
    # partnerNumber, id, contact{phone, email}, address{street, city,
    # postalCode, country}, location{lat, lon}, openingHours[].
    # Currently populated by SkodaClient; other brands leave it None.
    preferred_workshop: dict[str, Any] | None = None

    # v2.8.0 — Brake service due-dates + preferred workshop normalised
    # singletons. The composite ``preferred_workshop`` dict above stays
    # as the attribute payload for the existing service-due sensor; the
    # three normalised string fields below back dedicated sensors so a
    # user can build a "call my workshop" automation against
    # ``sensor.preferred_workshop_phone`` without templating into a dict.
    #
    # Brake fields are TIMESTAMP-class (parser converts an int day-
    # offset or EU dd.mm.yyyy date into an ISO 8601 UTC string at
    # midnight). Stays None when the backend either omits the field or
    # ships an empty error envelope. Phantom-protected in sensor.py via
    # ``_DATA_PRESENT_REQUIRED``.
    brake_fluid_change_due_at: str | None = None
    brake_pads_front_inspection_due_at: str | None = None
    brake_pads_rear_inspection_due_at: str | None = None
    preferred_workshop_name: str | None = None
    preferred_workshop_address: str | None = None
    preferred_workshop_phone: str | None = None

    # v2.8.1 — 13 P1 sensor gaps observed during the goncal + DanielBie
    # bug-report cycle on issue #306. The OLA backend ships these fields
    # on /v5/mycar, /climater, /charging, /airConditioning, /maintenance
    # and /status, but the seat_cupra parser never pulled them. The
    # CARIAD-BFF equivalents exist for some (target temp, battery care,
    # external power, primary range) so the audi.py / vw_eu.py parsers
    # opt in where the field maps cleanly. Every field is None-default
    # and phantom-protected in sensor.py via _DATA_PRESENT_REQUIRED.

    # 1. Diesel AdBlue tank level (separate from adblue_range_km which
    # estimates how far the existing AdBlue lasts). Some vehicles report
    # level but not range and vice versa.
    adblue_level_pct: int | None = None

    # 2. CNG tank level (Polo TGI, Skoda Scala G-Tec, Seat Mii Ecofuel).
    cng_level_pct: int | None = None

    # 3. CNG remaining range in km — derived from the CNG-engine block
    # on OLA mycar.engines.{primary,secondary} when type == "cng".
    cng_range_km: int | None = None

    # (4 + 5: dropped from this group during the v2.8.1 audit — the
    # climate target temperature is already exposed via the existing
    # ``target_temperature`` field; the rear-window heating element is
    # already exposed via ``window_heating_back`` and surfaced as a
    # binary sensor since v1.7.0. Numbering kept to match the pycupra
    # gap-analysis dump on issue #306.)

    # 6. Seat heating overall on/off — aggregate over all seats that
    # report a seatHeatingSupport entry. Per-seat granular state stays
    # in the diagnostics dump only.
    seat_heating: bool | None = None

    # 7. Parking lights status. Top-level ``status.lights`` flag on OLA;
    # ``vehicleLights.parkingLightStatus.value.parkingLightState`` on
    # CARIAD-BFF where the value carries more granularity than we
    # currently expose.
    parking_light: bool | None = None

    # 8. EV: external power available (plugged into a station vs
    # plugged but station not providing power). Distinct from
    # ``plug_connected`` which is the physical cable presence.
    external_power: bool | None = None

    # 9. Battery-care mode on/off. When True the brand backend limits
    # the battery to a preservation window (typically 80% top-end).
    battery_care: bool | None = None

    # 10. Energy-flow direction. True when current is actively flowing
    # to or from the HV battery; useful as a fast "is the car drawing
    # power right now" signal that survives across the charging /
    # climatisation / V2L cases without needing three different
    # underlying sensors.
    energy_flow: bool | None = None

    # 11. Primary-engine residual range in km. We had
    # ``secondary_engine_range_km`` since v1.26.0 but no primary.
    # Mirror so PHEV / dual-fuel vehicles have both halves of the
    # range pair.
    primary_engine_range_km: int | None = None

    # 12. User-selected preferred charging mode ("manual",
    # "preferredChargingTimes", "automaticUnlocked", ...). Read-only
    # surface of the brand-app setting; useful as a context attribute
    # for charge-target automations.
    charging_preferred_mode: str | None = None

    # 13. Area alarm event flag. The OLA backend ships a top-level
    # ``areaAlarm`` block when the vehicle leaves a configured
    # geofence. Coordinator decays the flag after 15 minutes so a
    # one-shot alarm does not stick forever. Useful as an event
    # trigger for "where is my car" automations.
    area_alarm: bool | None = None

    # v1.19.1 — Pycupra-style API quota visibility. Populated from
    # X-RateLimit-Remaining response header captured by base.py
    # ``_capture_rate_limit_headers``. Brand-shared (the same auth
    # cookie / token has the same daily budget regardless of which
    # vehicle's endpoint we hit), so the coordinator copies it onto
    # every VIN's data dict for HA sensor mapping. ``None`` means the
    # backend has never sent the header for this brand — sensor stays
    # ``unknown`` instead of showing a stale 0.
    requests_remaining_today: int | None = None
    requests_limit_today: int | None = None
    requests_reset_at: Any | None = None

    # v2.7.0b11 — wake_count_today on the dataclass so it always
    # serialises as 0 instead of being absent. The coordinator's
    # wake-counter logic writes the real count into the vehicle dict
    # when a wake is triggered (overrides this 0). Without the field
    # here, a user who never uses the wake button sees "Unbekannt"
    # for the wake_count_today sensor because the key is missing.
    wake_count_today: int = 0

    # v1.20.0 (Bundle 2 Phase A — Skoda widget + vehicle-info + equipment).
    # Three new static-ish enrichment fields populated from myskoda PR
    # #557 widget endpoint + /vehicle-information/{vin} + /equipment.
    # Currently Skoda-only; other brands leave them None.
    # NOTE: ``license_plate`` already exists above (line 156) — do not
    # re-declare. Skoda widget parser populates the existing field.
    render_url: str | None = None          # widget.vehicle.renderUrl (image)
    equipment: list[dict[str, Any]] | None = None  # equipment.equipment[]
    equipment_count: int | None = None     # derived: len(equipment)
    # v1.22.x foundation (myskoda PR #571 confirmed live 2026-05-02) —
    # multi-angle composite renders from
    # ``GET /api/v1/vehicle-information/{vin}/renders``.
    # Keyed by lowercased ``viewPoint`` (e.g. ``exterior_side``,
    # ``interior_boot``); value is the highest-order ``REAL`` layer URL
    # found in that ``compositeRenders[]`` entry.
    # v1.24.0 wired image-platform entity expansion (~6 new ImageEntity
    # per Skoda VIN) via the cross-brand Branch-2 leftover-keys path in
    # ``image.py:_add_entities_for_vin``. Coordinator merges this dict
    # into ``image_urls`` in ``_enrich`` so the unified path picks it up.
    composite_render_urls: dict[str, str] | None = None

    # v1.26.0 — Welle 6 Feature Backlog (Issue #173).
    # All these fields were silently shipped in scout reports
    # (#129/#130/#132/#133/#143/#144/#145/#146/#147/#165/#167) but
    # only EXPECTED_KEYS-silenced in v1.19.3. v1.26.0 finally exposes
    # them as user-visible entities. Each field is brand-restricted
    # via ``_DATA_PRESENT_REQUIRED`` so non-supporting vehicles don't
    # see phantom "unknown" entities.

    # Battery-Care wiring for VW EU/Audi: existing fields
    # ``battery_care_enabled`` + ``battery_care_target_soc_pct`` (defined
    # below for Skoda/CUPRA/SEAT since v1.17.5) are now ALSO populated by
    # vw_eu.py from ``charging.chargingCareSettings.value.batteryCareMode``
    # + ``batteryChargingCare.chargingCareSettings.value.batteryCareTargetSoc``.
    # No new model fields needed — the binary_sensor + sensor entities
    # auto-spawn via existing ``_DATA_PRESENT_REQUIRED`` gating once the
    # Cariad-BFF parser fills the values.

    # Auto-Unlock plug when charged: VW EU/Audi from
    # ``charging.chargingSettings.value.autoUnlockPlugWhenCharged`` ("permanent"/"OFF").
    # Skoda from ``settings.autoUnlockPlugWhenCharged`` ("ON"/"OFF").
    auto_unlock_when_charged: bool | None = None

    # Climatization-at-Unlock: VW EU/Audi from
    # ``climatisation.climatisationSettings.value.climatizationAtUnlock``.
    # Skoda from ``airConditioningAtUnlock``. CUPRA/SEAT from
    # ``mycar.climatisation.airConditioningAtUnlock``.
    climate_at_unlock: bool | None = None

    # Window-heating-enabled: VW EU/Audi from
    # ``climatisation.climatisationSettings.value.windowHeatingEnabled``.
    # Distinct from the existing v1.7.0 ``window_heating_front/back`` switches
    # (those are STATES "on/off"); this is the SETTING ("auto-activate during
    # climate?"). Boolean.
    window_heating_enabled: bool | None = None

    # v2.8.0 - Auxiliary heating (engine pre-heater / Standheizung) for
    # Audi + VW EU. Cariad-BFF parses from
    # ``auxiliaryHeating.auxiliaryHeatingStatus.value.{operationMode,
    # climatisationState, remainingTime_min}``. SEAT/CUPRA OLA aux-heating
    # support stays unchanged (v1.17.1 Bruno seq 29/30), but its parser
    # does not populate these fields yet, so non-supporting brands leave
    # them as None (no phantom entities).
    # ``aux_heating_active`` is a derived bool used by the switch
    # entity's ``is_on`` property; populated from operationMode /
    # climatisationState being one of {heating, on, heatingOn, active}.
    auxiliary_heating_status: str | None = None
    aux_heating_active: bool | None = None
    auxiliary_heating_remaining_min: int | None = None

    # Next-Charging-Timer info (read-side complement to v1.16.0
    # write-side service ``set_departure_timer``): VW EU/Audi from
    # ``automation.chargingProfiles.value.nextChargingTimer.{id, targetSOCreachable}``.
    # ``id`` = which timer (1/2/3) is queued next.
    # ``target_soc_reachable`` = "calculating" or a percent value.
    next_charging_timer_id: int | None = None
    next_charging_timer_target_soc_reachable: str | None = None

    # Skoda PHEV secondary engine range (Kodiaq iV, Octavia iV, Superb iV).
    # From ``driving-range.secondaryEngineRange.{distanceInKm, ...}``.
    # Distinct from ``combustion_range_km`` because Skoda PHEVs report
    # both via separate API blocks since 2024 firmware.
    secondary_engine_range_km: int | None = None

    # v2.2.0 (Skoda Scout #220 — Daniel Walter 2026-05-16) — Skoda mysmob
    # ``driving-range.secondaryEngineRange`` expanded from 1-key (distanceInKm)
    # to 4-key shape mid-May 2026. The extra keys document WHICH engine
    # backs the secondary range (PETROL / DIESEL on PHEV variants) and the
    # CURRENT FUEL LEVEL %. Both surface as separate sensors so power-users
    # can build automations on engine-type-aware logic.
    # From ``driving-range.secondaryEngineRange.engineType`` (string enum).
    secondary_engine_type: str | None = None
    # From ``driving-range.secondaryEngineRange.currentFuelLevelInPercent``
    # (int 0-100) — companion to ``current_fuel_level_pct`` for the primary
    # engine but scoped to the secondary (PHEV ICE) tank.
    secondary_engine_fuel_level_pct: int | None = None

    # v2.2.0 (Skoda Scout #220 — Daniel Walter 2026-05-16) — Skoda mysmob
    # ``air-conditioning.airConditioningWithoutExternalPower`` boolean.
    # True when climatisation can run from the HV battery alone (without
    # being plugged into a charger). Critical for PHEV/BEV pre-conditioning
    # automations where the user wants to "warm up only if not plugged in".
    air_conditioning_without_external_power: bool | None = None

    # v2.5.9 (#315/#316/#321/#327/#328/#329/#330/#333 — EIGHT Skoda
    # Scout-Reports converging 2026-05-28/29). New Enyaq/iV "Camping Mode"
    # feature: climatisation runs continuously when parked, windows lock,
    # roof-rack power-out. Sample showed `{1 keys}` so the API returns
    # an object — defensive parsing handles both bool and object-with-
    # ``enabled`` sub-key. Skoda-only today; mirror across brands when
    # CUPRA/SEAT firmware ships equivalent.
    camping_mode: bool | None = None

    # v2.2.0 Phase 7 PR #1 — quick-wins batch from the silenced-but-
    # unwired scout-audit. Four fields silenced in `_unexpected_keys.py`
    # but never exposed as entities. All defensive: brand-restricted
    # parser hooks, phantom-protected via `_DATA_PRESENT_REQUIRED`.

    # Skoda mysmob `readiness.ignitionOn` (bool). Cariad+CUPRA/SEAT
    # don't expose an equivalent — Skoda-only today. Useful for
    # "lock car when ignition turns off" automations without an
    # extra sensor query.
    ignition_on: bool | None = None

    # Skoda mysmob `driving-range.primaryEngineRange.currentSoCInPercent`
    # (int 0-100). On a gasoline car this is the 12V SoC — early-
    # warning sensor for "modem can't keep itself awake". Distinct
    # from `battery_voltage_v` (CARIAD-BFF only).
    primary_engine_soc_pct: int | None = None

    # Skoda mysmob `air-conditioning.steeringWheelPosition` (string
    # enum LEFT/RIGHT). LHD/RHD-aware automations + diagnostic for
    # markets where the same car ships both (UK, AU, JP).
    steering_wheel_position: str | None = None

    # VW EU + Audi CARIAD-BFF `measurements.temperatureBatteryStatus.
    # value.temperatureHvBatteryMax_K`. Companion to existing
    # `battery_temp` (HvBatteryMin_K). Both Celsius after K→C
    # conversion. Power-users monitoring thermal balance during
    # charging want both extremes.
    battery_temp_max: float | None = None

    # v2.2.0 Phase 7 PR #2 — tier-B diagnostics from scout-audit.
    # Two VW EU + Audi fields that we already PARSE (timers list,
    # readiness block) but never expose as aggregate / diagnostic.

    # Count of currently-enabled departure timers (0-3). Aggregate of
    # the per-timer `departure_timer_N_enabled` fields. Saves users
    # the templating effort of summing 3 binary states. Read from
    # `departureTimers.departureTimersStatus.value.timers[*].enabled`.
    departure_timer_enabled_count: int | None = None

    # Telematics modem daily power budget remaining (boolean). When
    # False, the modem is rationing wake-ups to preserve 12V — long
    # poll intervals are the user-visible symptom. From
    # `readiness.readinessStatus.value.connectionState.
    # dailyPowerBudgetAvailable`.
    daily_power_budget_available: bool | None = None

    # v2.2.0 Phase 7 PR #3 — SEAT/CUPRA `engines.primary` block.
    # Silenced via wildcard `engines.primary.*` since v1.16.1 (#122
    # r1150gs SEAT scout 2026-05-02 — "3 keys observed") but never
    # parsed. Companion to PR #6/#18 `secondary_engine_*` fields
    # which were wired for the PHEV secondary-engine block.
    #
    # `primary_engine_type`: enum string PETROL / DIESEL / ELECTRIC /
    # HYBRID. Useful for type-aware automations and cross-brand
    # diagnostics. Distinct from the existing `is_electric`/
    # `is_hybrid`/`has_combustion` derived booleans — this is the
    # backend's authoritative classification of the *primary* engine.
    primary_engine_type: str | None = None

    # `fuel_tank_capacity_liters`: absolute tank size in liters. With
    # the existing `fuel_level` (percent), users can derive
    # remaining-litres via simple template. Saves them looking up
    # the vehicle spec PDF.
    fuel_tank_capacity_liters: int | None = None

    # v2.2.0 Phase 7 PR #4 — Skoda tier-B trio from scout-audit.
    # Three Skoda mysmob fields that have been silenced since
    # v1.12.2 (#107 tritanium73 2026-05-01) but never parsed.

    # Skoda mysmob `air-conditioning.timers` (list). Count of
    # currently-enabled climate timers (0-3) — Skoda parity to the
    # VW EU/Audi `departure_timer_enabled_count` from PR #2. Saves
    # users templating-effort. Field stays None when timers block
    # is absent (so phantom gate fires on non-Skoda brands).
    climate_timer_enabled_count: int | None = None

    # Skoda mysmob `air-conditioning.runningRequests` (list). Count
    # of in-flight climatisation requests waiting on the modem to
    # acknowledge. >0 means a command is still pending — useful
    # diagnostic when start_climatisation appears to do nothing.
    climate_running_requests_count: int | None = None

    # Skoda mysmob `charging.isVehicleInSavedLocation` (bool). Whether
    # the car's current GPS matches one of the user's saved "home"
    # / "work" locations. Enables "auto-charge only at home"
    # automations without needing a zone helper.
    vehicle_at_saved_location: bool | None = None

    # v2.2.1 Phase 8 PR #1 — "alles parsen statt silencen" Strategy-shift.
    # User-Direktive (2026-05-17): Statt fields zu silencen wenn der
    # scout sie reportet, parse them ALL ins data model. Wenn ein
    # field es wert ist silenced zu werden, ist es wert geparsed zu
    # werden. Diese batch: 5 Skoda fields die seit v1.x silenced sind
    # ohne parser hook.

    # Skoda mysmob `readiness.batteryProtectionLimitOn` (bool). 12V
    # starter battery protection threshold reached — modem rationiert
    # wake-ups um die batterie zu schonen. Distinct vom existing
    # `daily_power_budget_available` (VW EU/Audi PR #2 Phase 7) —
    # das ist die Skoda-side äquivalent. Useful für "warn 12V check"
    # automations.
    battery_protection_limit_on: bool | None = None

    # Skoda mysmob `driving-range.carType` (string enum: diesel /
    # gasoline / electric / hybrid). Authoritative backend
    # classification der primary engine. Cross-brand companion zu
    # `primary_engine_type` (CUPRA/SEAT) und distinct von den
    # derived booleans (`is_electric`, `is_hybrid`).
    car_type: str | None = None

    # Skoda mysmob `driving-range.primaryEngineRange.engineType`
    # (string PETROL/DIESEL/...). Cross-brand reuse: maps in den
    # existing `primary_engine_type` field aus PR #3 Phase 7 (CUPRA/
    # SEAT) — zero new entity, just expanded brand coverage.

    # Skoda mysmob `driving-range.primaryEngineRange.
    # currentFuelLevelInPercent` (int 0-100). Cross-brand companion
    # zu `secondary_engine_fuel_level_pct`. Primary fuel tank level
    # für combustion vehicles. Distinct vom existing `fuel_level`
    # (% from measurements.fuelLevelStatus) — Skoda mysmob ships
    # both paths on PHEVs; user can compare for diagnostic.
    primary_engine_fuel_level_pct: int | None = None

    # Skoda mysmob `maintenance.maintenanceReport.capturedAt` (ISO
    # 8601 string). Timestamp when the maintenance report was last
    # refreshed by the backend. Diagnostic — useful for "is my
    # service-due data stale?" questions.
    maintenance_report_captured_at: str | None = None

    # v2.2.0 Phase 2 PR #8/20 — Connect-subscription expiry timestamp.
    # SEAT/CUPRA OLA ``mycar.services`` block exposes a per-service
    # entitlement map. Each entry typically carries either an
    # ``expirationDate`` / ``validUntil`` / ``expiresAt`` (ISO 8601) when
    # the subscription has a fixed end date. We aggregate by picking the
    # EARLIEST end-date across all services that have one (most-restrictive
    # / first-to-expire). Field is None when:
    #   - no services block present (brand without OLA mycar endpoint)
    #   - services block present but no expiry fields (e.g. perpetual)
    #   - all services are perpetual or trial-extending
    # ISO 8601 string → ``device_class=timestamp`` sensor that HA renders
    # as a calendar date + "X days remaining". Closes long-standing user
    # request "When does my Connect subscription run out?".
    subscription_expiry_at: str | None = None

    # v2.2.0 Phase 2 PR #9/20 — Companion bool to ``subscription_expiry_at``.
    # Computed at parse-time from the same SEAT/CUPRA ``mycar.services``
    # aggregation but normalised to a simple True/False:
    #   - True  → at least one service has expiry in the future
    #   - False → earliest expiry is now-or-past (subscription LAPSED)
    #   - None  → no expiry info at all (perpetual OR brand without block)
    # Surfaces as ``binary_sensor.subscription_active``. Use case:
    # ``automation: if binary_sensor.subscription_active == off → notify``.
    # Tri-state semantics preserved on purpose — None ≠ False so users
    # with perpetual entitlements don't get false "expired" alarms.
    subscription_active: bool | None = None

    # v2.2.0 Phase 2 PR #11/20 — Derived integer days until expiry.
    # Closes the subscription-feature triangle (expiry timestamp +
    # active bool + days-remaining int). Computed from
    # ``subscription_expiry_at`` minus current UTC, rounded DOWN to
    # whole days. Negative values when expired (e.g. -3 means "expired
    # 3 days ago"). Stays None when ``subscription_expiry_at`` is None
    # (perpetual entitlement or brand without subscription block).
    # Use case: threshold-based renewal reminders like
    # ``automation: if sensor.subscription_days_remaining < 30 → notify``.
    # Much easier to template against than parsing the timestamp.
    subscription_days_remaining: int | None = None

    # Audi/VW EU charging rate in km/h (parity with Skoda + CUPRA/SEAT
    # which have ``charging_rate_kmh`` since v1.10.0). From
    # ``charging.chargingStatus.value.chargeRate_kmph``. Reused field
    # ``charging_rate_kmh`` already exists for the other brands — we
    # don't add a new field, just populate it for VW EU/Audi too.

    # Diagnostic: count of capabilities array (already used internally
    # for capability gating since v1.13.0, now exposed for power users
    # who want to see "this VIN reports N capabilities").
    capabilities_count: int | None = None

    # Departure timers
    departure_timer_1_enabled: bool = False
    departure_timer_1_time: str | None = None
    departure_timer_2_enabled: bool = False
    departure_timer_2_time: str | None = None
    departure_timer_3_enabled: bool = False
    departure_timer_3_time: str | None = None

    # Window heating
    window_heating_front: bool | None = None
    window_heating_back: bool | None = None

    # AdBlue (diesel)
    adblue_range_km: int | None = None

    # v1.12.0 (#23) — 12V starter battery status. Critical for older
    # vehicles with degrading 12V batteries — symptom is "API stops
    # responding for hours/days" and many users blame the integration
    # before realising their 12V is at 10.8V and the car can't keep
    # the modem awake. Threshold for ``warning_12v_low`` is documented
    # in the binary_sensor description; volkswagencarnet PR #940 used
    # 11.5 V (12.6 V is healthy, 11.5 V is "needs attention", 10.5 V
    # is "battery dead").
    voltage_12v: float | None = None
    warning_12v_low: bool | None = None

    # v1.11.0 (#91 closure) — Vehicle lights status.
    # ``lights_on`` is the safe aggregate ("any light on?"); created
    # whenever the ``vehicleLights.lightsStatus.value.lights[]`` array
    # is present (regardless of element shape).
    # ``lights_count`` mirrors the on-count for users who want a numeric
    # value in dashboards.
    # ``lights_individual`` is best-effort per-light state. We probe
    # several known shapes (``{name, status}``, ``{id, status}``,
    # ``{location.position, status}``) but if none match we leave it
    # empty rather than guess. Per-light binary_sensors are only
    # registered at setup time when this dict is populated.
    lights_on: bool | None = None
    lights_count: int | None = None
    lights_individual: dict[str, bool] = field(default_factory=dict)

    # Hood / trunk / sunroof
    hood_open: bool | None = None
    trunk_open: bool | None = None
    trunk_locked: bool | None = None
    sunroof_open: bool | None = None

    # v1.17.1 (Bruno seq 10/11) — SEAT/CUPRA Battery Care.
    # Two read-only fields populated from the new OLA endpoints:
    # - GET /v1/vehicles/{vin}/charging/battery-care → {enabled: bool}
    # - GET /v1/vehicles/{vin}/charging/battery-care/target → {targetSocPercentage: int}
    # Skoda also has battery-care under different paths (covered in
    # v1.15.0 cap-id work); this is the SEAT/CUPRA-specific surface.
    battery_care_enabled: bool | None = None
    battery_care_target_soc_pct: int | None = None

    # v1.16.0 (#25, #31) — Skoda Charging Profiles (mysmob endpoint
    # ``/v1/charging/{vin}/profiles``). Read-only sensors expose:
    # - which profile is active at the car's CURRENT GPS position
    #   (``active_charging_profile_name`` from
    #   ``currentVehiclePositionProfile.name``) — solves #25 location-
    #   based target SoC by surfacing the backend's own decision
    # - next upcoming charging time
    # - target SoC for the active profile
    # - count of registered profiles
    # ``charging_profiles`` (full list) lives in attributes for the
    # active-profile sensor — vermeidet 255-char state limit. Write-side
    # for editing profiles is deferred (myskoda has POST/PUT but those
    # endpoints need their own bundle).
    active_charging_profile_name: str | None = None
    active_charging_profile_target_soc_pct: int | None = None
    next_charging_time: str | None = None
    charging_profiles_count: int | None = None
    charging_profiles: list[dict[str, Any]] = field(default_factory=list)

    # v1.15.0 (#35) — Skoda Charging History (mysmob endpoint
    # ``/v1/charging/{vin}/history``). Drives HA Energy Dashboard via
    # ``total_charged_energy_kwh`` with state_class=TOTAL_INCREASING.
    # Skoda-only initially — CARIAD-BFF + OLA don't expose an equivalent
    # endpoint with chargedEnergy_kWh per session (verified 2026-05-02).
    # ``recent_sessions`` (last 5) lives in attributes to avoid the HA
    # 255-char state limit.
    total_charged_energy_kwh: float | None = None
    last_charging_session_kwh: float | None = None
    last_charging_session_duration_min: int | None = None
    last_charging_session_current_type: str | None = None
    last_charging_session_start: str | None = None
    recent_charging_sessions: list[dict[str, Any]] = field(default_factory=list)

    # v1.15.0 — Software-version + OTA update status (Skoda mysmob).
    # Endpoint ``GET /v1/vehicle-information/{vin}/software-version/update-status``
    # shipped in Skoda app v8.10.0+ (myskoda PR #541). Cross-brand support
    # deferred — CARIAD-BFF + OLA don't expose an equivalent endpoint yet
    # (Research 2026-05-02). Fields stay ``None`` for non-Skoda vehicles.
    # ``software_update_status`` is the raw enum string (NO_UPDATE_AVAILABLE
    # / UPDATE_SUCCESSFUL / future values) — defensive: we don't gate on
    # the enum, the bool ``ota_update_available`` is what entities consume.
    software_version: str | None = None
    software_update_status: str | None = None
    ota_update_available: bool | None = None
    ota_release_notes_url: str | None = None

    # v2.0.0 (Big-Bang) — Skoda driving-score (efficiency metric 0-100).
    # Endpoint ``GET /api/v2/vehicle-status/{vin}/driving-score`` on mysmob
    # (MY24+). ``driving_score`` is the integer 0-100; ``driving_score_class``
    # is the human-readable bucket (e.g. ``EXCELLENT``, ``GOOD``, ``AVERAGE``).
    # Other brands leave both as ``None`` — sensor.py uses _DATA_PRESENT_REQUIRED
    # so non-Skoda vehicles never see a phantom ``unknown`` entity.
    driving_score: int | None = None
    driving_score_class: str | None = None

    # v2.0.0 (Big-Bang) — Porsche TPMS (Tire Pressure Monitoring System).
    # Populated by PorscheClient from
    # ``GET /app/connect/v1/vehicles/{vin}/measurements?fields=TIRE_PRESSURE``
    # (PPA endpoint, requires ConnectPlus subscription on most models).
    # Per-tire pressure in bar (kPa/100). Warning flag derived from
    # the per-tire ``warning`` boolean union. Other brands' status
    # endpoints don't expose per-tire data — fields stay None and
    # _DATA_PRESENT_REQUIRED prevents phantom entities.
    tire_pressure_front_left_bar: float | None = None
    tire_pressure_front_right_bar: float | None = None
    tire_pressure_rear_left_bar: float | None = None
    tire_pressure_rear_right_bar: float | None = None
    tire_pressure_warning: bool | None = None

    # v2.7.0b10 — Engine oil level. Cariad BFF ``oilLevel`` job ships
    # a discrete value (e.g. "normal", "minimumWarning", "service") and
    # often a numeric percentage. We surface three fields:
    #   - oil_level_status: raw string for diagnostic surface
    #   - oil_level_warning: True when the backend reports anything
    #     other than "normal"/"ok"/"sufficient". PROBLEM device class
    #     friendly (True = red icon, False = green icon).
    #   - oil_level_pct: numeric gauge when the backend provides one.
    oil_level_status: str | None = None
    oil_level_warning: bool | None = None
    oil_level_pct: int | None = None

    # v2.0.0 (Big-Bang) — Vehicle alarm (issue #33).
    # Cariad-BFF ``access.accessStatus.value`` may carry vehicleAlarm /
    # siren fields when the car's anti-theft system has triggered. Surfaced
    # as two binary_sensors (PROBLEM device class) plus a TIMESTAMP
    # sensor for the most recent alarm event. Brand-restricted via
    # _DATA_PRESENT_REQUIRED so cars without this telemetry don't see
    # phantom entities.
    alarm_active: bool | None = None       # vehicleAlarm == "ALARM"
    siren_active: bool | None = None       # siren == "ACTIVE"
    last_alarm_at: Any | None = None       # ISO timestamp of last alarm

    # v2.0.0 (Big-Bang) — Heat-source mode (issue #163, best-effort).
    # ID.x heat-pump models surface ``climatisationSettings.value.heaterSource``
    # ("electric" / "fuel") indicating which heat source the car will use
    # for pre-conditioning. Issue #163 wanted a tester to confirm whether
    # the field is read-only (surface as sensor) or writable (surface as
    # select). Without a confirmed tester we ship the safe READ-ONLY shape;
    # if a tester later confirms write support a follow-up PR can promote
    # to a select. Field stays None for non-heat-pump cars.
    heater_source: str | None = None

    # v1.14.0 (#24) — Trip Statistics from CARIAD-BFF
    # ``GET /vehicle/v1/vehicles/{vin}/tripstatistics?type={shortTerm|longTerm}``.
    # Both endpoints return ``{tripDataList: {tripData: [...]}}``; we sort
    # by ``overallMileage`` desc and take ``[0]`` as the most recent
    # trip (the audi #113 "aggregate-in-state" convention — keeps each
    # field a separate sensor state rather than building a list entity).
    # Consumption fields come back from the API as integers ×10
    # (averageFuelConsumption: 68 ⇒ 6.8 l/100 km); the parser divides
    # by 10 so the value stored here is already the human number.
    # ``recent_trips`` holds the last 5 short-term trips for the
    # ``last_trip_distance_km`` sensor's ``extra_state_attributes`` —
    # avoids state-string-too-long (255 char limit).
    last_trip_distance_km: float | None = None
    last_trip_duration_min: int | None = None
    last_trip_avg_speed_kmh: float | None = None
    last_trip_avg_fuel_consumption_l_100km: float | None = None
    last_trip_avg_electric_consumption_kwh_100km: float | None = None
    last_trip_timestamp: str | None = None
    lifetime_distance_km: float | None = None
    lifetime_avg_fuel_consumption_l_100km: float | None = None
    lifetime_avg_electric_consumption_kwh_100km: float | None = None
    recent_trips: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict for coordinator.vehicles storage."""
        from dataclasses import asdict  # noqa: PLC0415
        return asdict(self)
