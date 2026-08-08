# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
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
    user_agent="Volkswagen/4.2.1-android/14",
    api_base="https://emea.bff.cariad.digital",
    # scope from volkswagencarnet (upstream/volkswagencarnet, MIT) — confirmed working
    scope="openid profile badge cars dealers vin",
    # v2.5.11 — matches atlas profile vw_group_auth_profile.json#brands.vw.package_name.
    # Source: VW WeConnect 3.61.0 APK xapk archive name + ioBroker commit 884269b1.
    # v2.15.3 — user_agent bumped 3.61.0 → 3.63.2 to match the live We Connect
    # build (DEX-verified; _mbb_app_identity() in vw_eu.py already ships 3.63.2).
    # Unreleased (App Atlas refresh 2026-07) — bumped 3.63.2 → 4.2.1 from the
    # fresh com.volkswagen.weconnect DEX. This literal had drifted two whole
    # generations behind the app while _mbb_app_identity() had already moved on,
    # so the two channels were announcing different builds of the same app.
    # Nothing else changed between 4.1.1 and 4.2.1 (no new clients/endpoints).
    # Pre-v2.5.11 this was silently impersonating the Audi package via the
    # hardcoded ``de.myaudi.mobile.assistant`` default in idk.py.
    android_package_name="de.volkswagen.weconnect",
)

# b13 (RE dismantle 2026-06) — known-good FALLBACK OAuth client_ids harvested
# from the current brand APKs. Each app ships more dilab clients than we model;
# if VW ever blocklists a primary client_id, a user can set one of these via the
# ``CONF_CLIENT_ID_OVERRIDE`` option to recover. These are NOT active by default
# (documentation only); all primary client_ids above are APK-verified-current.
#   audi : 16dd7960-431d-4b88-b3a5-35724b2fce01@apps_vw-dilab_com
#   vw_eu: 4edc53db-4b79-4e37-b614-19a95dea20dc@apps_vw-dilab_com
#   skoda: 4fffed6b-815a-4b6f-af4a-b0ccccb4ff6d@apps_vw-dilab_com
#   ola  : 3f16b970-38ab-49c6-a1bf-af38460fd388 / f1cd60b6-e40f-4bf2-822d-0201eabc09b5
#   vw_na: 59992128-69a9-42c3-8621-7942041ba824_MYVW_ANDROID (US prod, primary)

BRAND_AUDI = BrandConfig(
    name="audi",
    # client_id from upstream (arjenvrh/upstream, MIT) — confirmed working
    client_id="09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
    redirect_uri="myaudi:///",
    # v2.20.0 (APK audit) — current myAudi build 5.6.0 / versionCode 800344256.
    user_agent="Android/5.6.0 (Build 800344256.root project 'myaudi_android'.ext.buildTime) Android/13",
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

# v2.18.2 — Audi North America (myAudi US / CA). LIVE-VERIFIED from the US market
# config (content.app.my.audi.com/service/mobileapp/configurations/market/US/en)
# + the NA OIDC discovery doc, cross-checked against the DE control. Key finding:
# US Audi is the EU-Audi CARIAD-BFF architecture, NA REGION — NOT the VW-NA
# con-veh backend. One global app (de.myaudi.mobile.assistant), region-switched at
# runtime. Auth: authorize at identity.na.vwgroup.io, token at na.bff.cariad.digital.
#
# v2.30.3 (#13) — current market config and a live US account both confirm the
# US data plane is na.bff.cariad.digital. The same device-grant access token gets
# 401 "expected user token" on emea.bff but 200 on na.bff. CA remains on emea.bff
# and is selected dynamically by AudiNAClient.
BRAND_AUDI_NA = BrandConfig(
    name="audi_na",
    # LIVE (Android) client from the US market config — apps_vw-dilab_com family,
    # NOT a *_MYVW/_MYAUDI_ANDROID id. Sandbox variant:
    # d8ef5ed0-2fd5-4afe-9ffb-018da6b76724@apps_vw-dilab_com.
    client_id="7c6b4634-f0c5-488b-a78f-b1a65414fb90@apps_vw-dilab_com",
    redirect_uri="myaudi:///",
    user_agent="Android/5.6.0 (Build 800344256.root project 'myaudi_android'.ext.buildTime) Android/13",
    # US is the default market; AudiNAClient overrides reads to emea.bff for CA.
    api_base="https://na.bff.cariad.digital",
    scope=(
        "address profile badge birthdate birthplace nationalIdentifier nationality "
        "profession email vin phone nickname name picture mbb gallery openid"
    ),
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
    # b13 (#503) — reverted to bare "openid" (the field-verified v2.3.0/#269
    # value); the v2.11.0 widening to "openid profile cars vin" was never
    # live-tested against NA and regressed login. Kept in sync with
    # BRAND_VW_NA in api/vw_na.py via test_v230_sprint_b.
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

# Lamborghini Unica brand-config — NOT wired, NOT IDK-compatible.
#
# v2.14.11 — the 2026-06-18 app-atlas (lamborghini.connectedcar) DISPROVED
# the original "same Cariad-BFF as Audi/VW EU" assumption. Unica ships NO
# @apps_vw-dilab_com client_id at all; it logs in via MBB co-auth through
# Lamborghini's own SDP gateway (token endpoint sdp.lamborghini.com/
# unicav2/mbbcoauth, scope sc2:fal, client_id held SERVER-SIDE on the proxy).
# AWS Cognito is analytics-only. So this BrandConfig's api_base + dilab
# client_id are STRUCTURALLY WRONG for Unica — kept only as a documented
# placeholder. A real integration needs a dedicated SDP-proxy MBB-co-auth
# adapter (Tier-3; see api/lambo.py). Do NOT add to BRANDS/factory/config-flow.
BRAND_LAMBO = BrandConfig(
    name="lambo",
    # SERVER-SIDE: the real MBB client is held on the SDP proxy and is not in
    # the APK. This dilab placeholder is a non-functional marker only.
    client_id="SERVER-SIDE-sdp-proxy-not-in-apk@apps_vw-dilab_com",
    redirect_uri="unica://oauth-callback",
    user_agent="Unica/1.0.0 Android",
    # WRONG for Unica (real flow is sdp.lamborghini.com/unicav2/mbbcoauth);
    # left only so the scaffold imports. Do not rely on this.
    api_base="https://emea.bff.cariad.digital",
    scope="sc2:fal",
)

# Bentley brand-adapter — v2.2.0 scaffold, ACTIVATED v2.14.11 (login+read).
#
# Inheritance rationale: Bentley "My Bentley" is a VAG luxury brand on the
# same Cariad-BFF backend as Audi (atlas-confirmed: Bentley's IDK client_id
# is byte-identical to Audi's primary). Data-fetch path inherits unchanged
# from ``VWEUClient``; only the brand-token + UA differ. Wired into BRANDS +
# factory + config-flow. Ships read-only (two-way is a live-test-gated
# follow-up — see the BRAND_BENTLEY comment + idk.py audi/volkswagen gates).
BRAND_BENTLEY = BrandConfig(
    # v2.14.11 — scaffold values RESOLVED from the 2026-06-18 app-atlas
    # (uk.co.bentley.mybentley). ``assets/assets/url-configuration.json``
    # key ``idkClientIDLive`` = 09b6cbec…  — i.e. Bentley runs on the SAME
    # IDK client + tenant as Audi (Bentley = Audi platform). The two
    # Bentley-unique dilab ids (7cd71138 Approval, a9d0a852 Dev) are
    # non-production and are intentionally NOT used. redirect_uri taken
    # from the app DEX (``mybentleyapp:///``) — the old scaffold value
    # ``mybentley://oauth-callback`` was wrong and would fail server-side
    # redirect validation.
    #
    # WIRED read-only: the qmauth/CARIAD assertion headers are still gated
    # to audi/volkswagen (idk.py), so Bentley's classic token exchange will
    # degrade to the read-only data_act_portal until a tester with a real
    # My Bentley account confirms the Audi-qmauth secret is accepted for
    # client 09b6cbec under the bentleyid tenant (then we add "bentley" to
    # those gates for two-way). Ships login+read now; two-way is live-test
    # gated. api_base = emea.bff.cariad.digital (Audi-like BFF).
    name="bentley",
    client_id="09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
    redirect_uri="mybentleyapp:///",
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
    "audi_na":       BRAND_AUDI_NA,
    "porsche":       BRAND_PORSCHE,
    # v2.14.11 — Bentley wired (login+read; runs on the Audi IDK client/tenant).
    "bentley":       BRAND_BENTLEY,
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

    # #1012 — VW North America. Its con-veh token server binds the refresh
    # grant to the ORIGINAL login's PKCE code_verifier: refreshing without it
    # returns "400 Internal Service validation failure" (confirmed against two
    # maintained NA clients). So the verifier has to survive from the initial
    # exchange through to every later refresh, which means persisting it here
    # with the token set. Empty for every other brand, whose servers do not
    # want it on refresh.
    code_verifier: str = ""

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
    # Battery State of Health (%). Only computed when the user supplied the car's
    # nameplate net capacity (CONF_BATTERY_NOMINAL_KWH); = current max capacity /
    # nominal. Left None otherwise -- VW ships no SoH field, so we never guess it.
    battery_soh_pct: int | None = None
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
    # v2.17.5 — fourth *.requests sibling: ``batteryChargingCare
    # .chargingCareSettings.requests`` counts queued battery-care changes.
    # Same int-count diagnostic, same None semantics. sensor, diagnostic.
    charging_care_pending: int | None = None
    # v2.18.0 — Scout #799 (Audi): ``automation.chargingProfiles.requests``
    # counts queued charge-PROFILE changes. Same int-count diagnostic.
    charging_profiles_pending: int | None = None
    # v2.18.0 — Scout #801 (Audi): ``climatisationTimers
    # .climatisationTimersStatus.requests`` counts queued climate-TIMER
    # schedule changes (distinct from climatisation start/stop). Same diag.
    climatisation_timers_pending: int | None = None
    # v2.15.8 — Cariad scout #583 (Audi): third charging-side *.requests
    # sibling — ``charging.chargeMode.requests`` counts queued chargeMode
    # change requests (e.g. a putChargeMode POST switching preferred mode
    # manual <-> timer). Same ``[1 items]`` shape as the chargingSettings /
    # chargingStatus queues. Int-count diagnostic, None when leaf absent.
    charging_mode_pending: int | None = None
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
    # v2.15.9 (#597 audi Scout) — selectivestatus rear-zone enable flags.
    # ``climatisation.climatisationSettings.value.zoneRearLeftEnabled`` /
    # ``zoneRearRightEnabled`` (dict setting_zone_enabled_rear_left /
    # _rear_right, type=string on/off). Rear-zone-capable cars only →
    # phantom-protected. Distinct dialect from the EU-Data-Act
    # ``climate_zone_front_*_enabled`` fields further below.
    climate_zone_rear_left: bool | None = None
    climate_zone_rear_right: bool | None = None
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
    # v2.10.0 - real-time charge rate in kW (instant), distinct from
    # the averaged charging_rate_kmh. Only populated by CARIAD BFF on
    # firmware that exposes a separate instant rate.
    actual_charge_rate_kw: float | None = None
    external_power_available: bool | None = None  # plugStatus.externalPower

    # v2.10.0 Group A - VW EU field parity. Each field below was
    # identified as a competitor-library gap during the 2026-06-02
    # scan. All defensively parsed, phantom-protected via
    # _DATA_PRESENT_REQUIRED in sensor.py / binary_sensor.py so
    # brands without the underlying field stay clean.

    # HV battery temperature min / max in Celsius. CARIAD BFF ships
    # ``charging.batteryStatus.value.{minTemperature_K,maxTemperature_K}``
    # as Kelvin scalars on Born / ID.4 / Q4 e-tron PPE firmware. The
    # existing ``battery_temp`` collapses these into a single value;
    # power-users monitoring thermal balance want both extremes.
    hv_battery_min_temperature_c: float | None = None
    hv_battery_max_temperature_c: float | None = None

    # Max AC charging current SETTING (user-requested) vs ACTUAL
    # deliverable amperage. ``maxChargeCurrentAC_setting`` is the
    # value the user picked in the brand app; ``maxChargeCurrentAC``
    # is the live deliverable the wallbox + cable can support.
    # Distinct so dashboards show both. Existing ``max_charge_current``
    # stays untouched as legacy alias for setting.
    charge_max_ac_setting: int | None = None
    charge_max_ac_ampere: int | None = None

    # Born MY24+ AC connector auto-release. Bool flag plus enum
    # state string. Sourced from ``charging.chargingSettings.value.
    # autoReleaseAcConnector`` or ``charging.plugStatus.value.
    # autoUnlockPlugWhenCharged``; state from ``charging.plugStatus.
    # value.autoReleaseState`` (enum: e.g. ``IDLE``, ``RELEASING``).
    auto_release_ac_connector: bool | None = None
    auto_release_ac_connector_state: str | None = None

    # Battery-preservation flag distinct from ``battery_care``.
    # ``optimisedBatteryUse`` is a Born / ID.x setting that limits
    # charging dynamics (current ramp + thermal pre-conditioning)
    # to preserve cell longevity. Different feature from the
    # ``battery_care`` cap-target (which is a SoC limit).
    optimised_battery_use: bool | None = None

    # Active ventilation (cabin air-circulation without heating /
    # cooling). Separate from the climatisation block because the
    # CARIAD BFF surfaces it under a sibling status enum + remaining
    # time. ``ventilationState`` is one of ``off`` / ``running`` /
    # ``finished``.
    active_ventilation_state: str | None = None
    active_ventilation_remaining_time_min: int | None = None

    # v2.21.0 — MEB/PPE 12V-battery-support state (``enabled`` / ``disabled``).
    # The CARIAD BFF ships it as a selectivestatus job
    # ``batterySupport.batterySupportStatus.value.batterySupport``. Was
    # interim-silenced since v2.12.0 (the IOU: map once a real payload confirmed
    # the field); ~27 MEB reporters supplied ``enabled``/``disabled`` values, so
    # it is now mapped to this diagnostic state instead of suppressed.
    battery_support_state: str | None = None

    # #1020 — HV-battery calibration notifications. The car asks the owner to
    # run a calibration (a full charge, sometimes with a specified AC rate),
    # escalates if it is ignored, and reports whether the attempt failed. All
    # enums, all named and described in VW's own data dictionary, so the
    # meanings below are theirs and not inferred:
    #   calibration_need_detected  — "first hint for battery calibration"
    #   calibration_request_*      — UNDEFINED / NONE / ACTIVE / ACK / REJECT
    #   calibration_request_method — e.g. FULL_CHARGE_RELAX / _AC60 / _AC95
    #   calibration_failure(_reason) — whether an attempt failed, and why
    calibration_need_detected: str | None = None
    calibration_request_initial: str | None = None
    calibration_request_escalation_1: str | None = None
    calibration_request_escalation_2: str | None = None
    calibration_request_method: str | None = None
    calibration_failure: str | None = None
    calibration_failure_reason: str | None = None

    # Rear sunroof + Cabrio roof cover state. Both are window-array
    # entries; ``sunRoofRear`` covers panoramic rear glass roofs
    # (Touareg, Tiguan Allspace), ``roofCover`` covers convertible
    # tops (T-Roc Cabrio, Beetle Cabriolet). Booleans for the
    # window-class binary sensor. None when the car doesn't have
    # the option, so the phantom gate hides the entity.
    sunroof_rear_closed: bool | None = None
    roof_cover_closed: bool | None = None

    # 12V health bucket. ``connectionStatus.batteryPowerLevel`` or
    # ``vehicleHealthInspection.value.battery12VLevel``. Enum
    # values observed: ``low`` / ``normal`` / ``high``. Companion
    # to the existing ``connection_battery_power_level`` v2.4.1 T1
    # field; this surface comes from a different parent block on
    # some firmware shapes.
    connection_state_battery_power_level: str | None = None

    # Trip aggregator totals. Existing ``last_trip_avg_*`` fields
    # cover the per-100km averages; these fields are the absolute
    # totals per trip. The CARIAD BFF ships them directly under
    # ``tripstatistics.shortTerm[0].{totalFuelConsumption_l,
    # totalElectricConsumption_kwh}``; older firmware only ships
    # avg + distance, in which case we derive totals from
    # ``avg * distance / 100`` (NEVER overwrite a backend total).
    last_trip_total_fuel_consumption_l: float | None = None
    last_trip_total_electric_consumption_kwh: float | None = None

    # Climate
    climatisation_state: str | None = None
    # v2.0.1 (#131 follow-up) — same false-negative reasoning as the
    # Access block: parser-miss must NOT default to "climate off".
    climatisation_active: bool | None = None
    target_temperature: float | None = None
    # v2.18.0 (Phase C) — one-time historical export config flag
    # (RPC/RDT.climatisationWithoutHVPower). Official meaning: temperature
    # regulation is allowed without an external power source, i.e. pre-climate
    # may draw from the drive battery rather than requiring the car to be
    # plugged in. Config, not telemetry.
    climatisation_without_hv_power: bool | None = None
    outside_temp: float | None = None
    # v2.17.1 (Scout #701, VW ID.7) — EU-portal `in_cabin_temperature.
    # temperature`: current interior °C. No brand's status endpoint
    # exposed a cabin reading before; portal-only. Brand-restricted via
    # _DATA_PRESENT_REQUIRED in sensor.py so non-portal cars stay None.
    cabin_temp: float | None = None
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
    # b10 (EU Data Act portal long-tail) — extra signals mapped from the portal's
    # per-window position + trip + maintenance fields.
    windows_position: dict[str, int] = field(default_factory=dict)  # % open (0=closed)
    warning_inspection: bool | None = None        # service inspection due
    monthly_mileage_km: int | None = None         # avg distance driven per month
    remaining_charge_time_min: int | None = None  # charging time left
    lifetime_travel_time_min: int | None = None   # cumulative driving time (long-term)
    lifetime_avg_speed_kmh: float | None = None   # average speed (long-term)

    # Location
    latitude: float | None = None
    longitude: float | None = None
    parking_address: str | None = None
    parking_city: str | None = None
    heading: int | None = None
    # v2.24.1 — when the BACKEND says the position was captured, as opposed to
    # when we polled. Carrying a parked position forward through an outage is
    # right (the car has not moved), but doing it with no age attached made a
    # week-old position indistinguishable from a current one. This is what the
    # carry-forward TTL in ``vehicle_cache.reconcile`` measures against, and what
    # the device_tracker exposes so the age is visible rather than implied.
    position_captured_at: str | None = None

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

    # v2.10.0 (#389 scout 2026-06-02) — Audi pending-action surface.
    # The CARIAD BFF ships ``access.accessStatus.requests`` as a list
    # of dicts when a lock/unlock/climate command was recently dispatched
    # but the vehicle has not yet confirmed completion. We expose the
    # most-recent pending request as 3 sensors so HA automations can
    # wait for action acknowledgement instead of guessing with a
    # fixed sleep. Phantom-protected via _DATA_PRESENT_REQUIRED.
    pending_action_id: str | None = None
    pending_action_type: str | None = None
    pending_action_status: str | None = None

    # v2.10.0 - "since refuel" / "since recharge" trip aggregator.
    # Third trip category alongside last_trip_* (per individual trip)
    # and lifetime_* (vehicle total). Tracks consumption since the
    # last tank fill or charge session. Pattern observed in
    # volkswagencarnet's TRIP_REFUEL constant; CARIAD BFF exposes it
    # under tripstatistics?type=cyclic. Energy-Dashboard-friendly
    # since the total-consumption-per-tank/charge value lets users
    # build "miles per tank" / "kWh per charge" automations directly.
    refuel_trip_distance_km: float | None = None
    refuel_trip_duration_min: int | None = None
    refuel_trip_avg_speed_kmh: float | None = None
    refuel_trip_avg_fuel_consumption_l_100km: float | None = None
    refuel_trip_avg_electric_consumption_kwh_100km: float | None = None
    refuel_trip_total_fuel_consumption_l: float | None = None
    refuel_trip_total_electric_consumption_kwh: float | None = None
    refuel_trip_recuperation_kwh: float | None = None
    refuel_trip_timestamp: str | None = None

    # (battery_care_target_soc_pct is defined further down with the
    # original battery-care fields from the v2.0 EV cluster; the
    # v2.10.0 settable surface re-uses that field name.)

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
    # v2.31.0 (8.15.0 APK) — CampingModeDto.endsAt: when camping mode will
    # auto-stop. Surfaced as an attribute on the camping switch.
    camping_ends_at: Any | None = None

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

    # v2.17.1 (Scout #701, VW ID.7) — EU-portal battery/account extras.
    # `battery_state_report.charge_target_time`: ISO-8601 timestamp the
    # pack is expected to reach its charge target (charging analog of
    # ``climatisation_ready_at``). ``max_number_users``: seat/account
    # capacity of the vehicle profile (diagnostic). Both portal-only,
    # brand-restricted via _DATA_PRESENT_REQUIRED in sensor.py.
    charge_target_time: str | None = None
    max_number_users: int | None = None

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

    # v2.10.0 (charging_statistics endpoint) - per-session power-curve
    # sample points from CARIAD's charging.cariad.digital host. SEAT/CUPRA
    # only at first; other brands' hosts don't expose an equivalent.
    # Lives under the integrated last-session umbrella so an HA card can
    # graph the most recent DC fast-charge as kW over time / SoC.
    # The list itself goes into attributes (not state) because each
    # sample is a {timestamp, soc_pct, power_kw} dict and a typical
    # 30-min DC charge dumps ~30-60 samples. State is the COUNT of
    # samples so the entity stays HA-recorder friendly.
    last_charging_power_curve_points: list[dict[str, Any]] = field(default_factory=list)

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

    # v2.16.2 (#671 audi Q6 Scout) — climatisation mode readback
    # (``climatisationSettings.value.climatisationMode``, "comfort" in the
    # wild). Read-only diagnostic; None for cars that don't ship it.
    climate_mode: str | None = None

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
    # v2.10.0 - last-trip reset timestamp. audi_connect_ha v2.1.0 surfaces
    # this as `shortterm_reset`. Read-only: records WHEN the user last
    # reset the short-term trip data from the vehicle's head unit. Useful
    # for HA automations that want to know "trip data is fresh since X".
    last_trip_reset_at: str | None = None
    lifetime_distance_km: float | None = None
    lifetime_avg_fuel_consumption_l_100km: float | None = None
    lifetime_avg_electric_consumption_kwh_100km: float | None = None
    recent_trips: list[dict[str, Any]] = field(default_factory=list)
    # v2.12.0 (myskoda PR #575) — trip overall-cost breakdown. Currency
    # carried separately so the sensor can set native_unit_of_measurement
    # to the ISO code. None on accounts/firmwares that don't ship costs.
    trip_total_cost: float | None = None
    trip_fuel_cost: float | None = None
    trip_electricity_cost: float | None = None
    trip_cng_cost: float | None = None
    trip_cost_currency: str | None = None

    # v2.10.0 Group B - SEAT/CUPRA OLA endpoint parity.
    # New fields populated by 6 OLA endpoints added in v2.10.0:
    # /v1/vehicles/{vin}/notifications, /permissions,
    # /measurements/engines, /charging/profiles (reuses Skoda fields
    # above), /charging/modes. Public /v1/charging/points is wired as
    # a fallback inside find_charging_stations and does not need its
    # own VehicleData field.

    # Notifications endpoint. ``notifications_count`` is the total
    # number of unread in-vehicle notifications; the last_* fields
    # expose the most recent entry so a Lovelace card can render a
    # quick preview without iterating the list.
    notifications_count: int | None = None
    last_notification_subject: str | None = None
    last_notification_severity: str | None = None

    # Permissions endpoint. ``permission_is_owner`` is True when the
    # account holds the primary owner role; ``permission_can_command``
    # is True when the role allows remote commands (owner or
    # privileged co-driver).
    permission_is_owner: bool | None = None
    permission_can_command: bool | None = None

    # b1/B2 — "MBB two-way available" symbol: True when the durable Car-Net
    # (MBB) backend grants at least one remote command (climate/charge) on a
    # currently-licensed service for this car. Surfaced as a diagnostic
    # binary_sensor so users see at a glance whether two-way control is
    # possible. None = unknown (no operationList this poll / non-MBB car).
    mbb_two_way_available: bool | None = None

    # Engine measurements endpoint. Both temperatures are stored in
    # Celsius after the parser converts from Kelvin if needed
    # (values above 200 are treated as Kelvin and shifted).
    engine_oil_temperature_c: float | None = None
    engine_coolant_temperature_c: float | None = None

    # Charging modes endpoint. List of allowed mode strings exposed
    # on the existing ``charging_preferred_mode`` sensor via
    # ``extra_state_attributes``. Stored as a plain list so the
    # JSON-safe attribute helper passes it through unchanged.
    available_charge_modes: list[str] = field(default_factory=list)
    # v2.31.0 (8.15.0 APK) — ChargingSettingsDto.preferredChargeMode: the charge
    # mode the car is currently set to (MANUAL / TIMER / …). Diagnostic sensor.
    preferred_charge_mode: str | None = None

    # v2.15.0a10 — transient per-poll flag (NOT a sensor). Set True by a
    # connector when THIS poll produced no real data (e.g. EU Data Act portal
    # timeout/outage, or an ACL-blocked MBB read) and the object carries only
    # the VIN. The coordinator uses it to keep the previous good data visible
    # ("old but visible") instead of blanking entities — but only when prior
    # data exists, so a brand-new car still appears and fills in later.
    no_data: bool = False
    # v2.15.0b1 (B1) — provenance: which channel(s) produced this snapshot.
    # Set by the channel-merge layer to the "+"-joined contributing channels
    # (e.g. "eu_data_act+mbb"); None for a single-channel poll. Surfaced as a
    # diagnostic attribute so users/maintainers can see where data came from.
    source_channel: str | None = None
    # v3.0.0-alpha — companion (ADB) channel only. True when this snapshot came
    # from a phone whose app version matched a verified preset, so writes (tap
    # actions) are currently allowed. None for every network channel. Lets the
    # entity layer show whether the experimental two-way path is live.
    companion_writes_enabled: bool | None = None
    # v2.26.0 — companion (ADB) channel only. Age in seconds of the CAR's data
    # as the app itself reports it ("synchronised N ago"), distinct from how
    # fresh OUR read is. None for every network channel and when the app shows
    # no sync line. Surfaced as a diagnostic so a stale car (working connector,
    # old backend data) is visible.
    companion_source_age_s: float | None = None
    # v2.18.0 (A2) — per-FIELD provenance: {field_name: channel} for every
    # field that actually carries a value, recorded by the channel-merge layer.
    # ``source_channel`` answers "which channels fed this car"; this answers
    # "where did THIS reading come from", which is what an entity needs to
    # expose its own source. Never merged itself (see _channel_merge
    # ``_SKIP_FIELDS``) — each merge rebuilds it from the snapshots it saw.
    field_sources: dict[str, str] = field(default_factory=dict)
    # v2.15.0b1 (A6) — raw field discovery: portal fields the curated parser
    # did not map, kept as {field_name: value} so the user can see every value
    # the backend sent (surfaced as attributes on ONE disabled diagnostic
    # sensor — no per-field entity explosion). Same unmapped set that feeds the
    # Vehicle Data Scout report: one detection pass, both worlds.
    raw_unmapped_fields: dict[str, str] = field(default_factory=dict)
    # Fields the export delivered MORE THAN ONCE under one capture time with
    # different values. The append order is then the only thing separating
    # them, which is not evidence, so the parser records every candidate here
    # and a layer that knows the previous poll picks the plausible one. Keyed
    # by the raw portal field name; empty on the overwhelming majority of polls.
    contested_fields: dict[str, list[str]] = field(default_factory=dict)

    # ── v2.15.1 — EU Data Act + BFF wire-key mapping (2.15.0 plan) ──────────
    # New fields declared once on the shared model; each is written by the EU
    # Data Act portal parser (_eu_data_act.py) and/or the BFF selectivestatus
    # parser (vw_eu.py). All None/False-defaulted so a parser miss leaves the
    # entity "unknown" and never fabricates a value.

    # — EU Data Act dialect (portal) NEW fields —
    # Charging scenario enum (CHARGING_SCENARIO_*) — active/finished ×
    # departure-timer/immediate/optimised.
    charging_scenario: str | None = None
    # Immediate-charge action state (IMMEDIATE_ACTION_STATE_*). Diagnostic —
    # may be a constant INVALID on portal firmware.
    immediate_charge_action_state: str | None = None
    # Reason the car decided to charge (PROFILE_CHARGE_REASON_*).
    profile_charge_reason: str | None = None
    # Energy added this charge session (kWh). TOTAL_INCREASING.
    charge_session_energy_kwh: float | None = None
    # Remaining time to the bulk/80 % stage (minutes). Sentinel -1 dropped.
    remaining_charge_time_bulk_min: int | None = None
    # Odometer measurement quality flag (mileage.state enum). Diagnostic.
    odometer_state: str | None = None
    # In-vehicle instrument-cluster clock (timestamp). Diagnostic.
    instrument_cluster_time: str | None = None
    # HV-battery status flag (battery_level_HV.state enum). #604 Scout — dict
    # lists no value tokens → LOW confidence, disabled-by-default. Diagnostic.
    hv_battery_state: str | None = None
    # Joined non-empty data-error fields (error_code/number/description),
    # sentinels "#0"/"0" filtered. Diagnostic.
    data_error_detail: str | None = None
    # Portal report/message id (change detector). Diagnostic.
    last_report_id: str | None = None
    # Climatisation energy consumed (kWh). TOTAL_INCREASING.
    climate_energy_consumption_kwh: float | None = None
    # On-board electronics / residual consumption (kWh). TOTAL_INCREASING.
    residual_energy_consumption_kwh: float | None = None
    # Battery climatisation (thermal management) energy consumed (kWh).
    # TOTAL_INCREASING. Diagnostic, disabled-by-default.
    battery_climatization_energy_kwh: float | None = None
    # Recuperated energy per 100 km (last trip / lifetime). kWh/100 km.
    last_trip_avg_recuperation_kwh_100km: float | None = None
    lifetime_avg_recuperation_kwh_100km: float | None = None
    # Parking brake engaged (shared — EU parking_brake.is_set / BFF
    # parkingBrakeStatus both write THIS field). binary_sensor.
    parking_brake_engaged: bool | None = None
    # Parking lights left/right (aggregate feeds the existing parking_light).
    parking_light_left: bool | None = None
    parking_light_right: bool | None = None
    # Portal dataset key — LOW confidence, disabled-by-default. Diagnostic.
    dataset_key: str | None = None

    # ── v2.15.2 — EU Data Act portal "charger detail" fields (#513 Scout) ────
    # New EU-Data-Act-dialect-only fields surfaced by the per-poll charger
    # detail block. All written by _eu_data_act.py; all DIAGNOSTIC.
    # External power-supply state (enum, e.g. "available"). sensor.
    external_power_supply_state: str | None = None
    # Energy actively flowing to/from the HV battery right now (raw portal
    # "energy_flow" on/off). binary_sensor. Distinct from the cross-brand
    # OLA-sourced ``energy_flow`` bool above — this is the EU portal signal.
    energy_flow_active: bool | None = None
    # Reason the current charge was triggered (enum, e.g. "immediate"). sensor.
    charging_reason: str | None = None
    # Charging-state error code; "0"/"#0" sentinels (= no error) dropped → None.
    charging_error_code: str | None = None
    # Which SoC target the remaining charging time counts down to
    # (enum, e.g. "maxSOC"). sensor.
    remaining_time_target_soc: str | None = None
    # Charge-port LED colour (e.g. "green") — disabled-by-default. sensor.
    charge_led_color: str | None = None
    # Charge-port LED pattern (e.g. "pulse") — disabled-by-default. sensor.
    charge_led_pattern: str | None = None

    # ── v2.15.3 — EU Data Act portal new fields (#465/#514/#515/#516) ────────
    # All written by _eu_data_act.py only (EU-Data-Act dialect). DIAGNOSTIC
    # unless noted; LOW-confidence ones disabled-by-default at the entity layer.
    # A. Charging settings (settings.* block).
    # Currently-selected charge mode (CHARGE_MODE_SELECTION_* enum). sensor.
    charge_mode_selection: str | None = None
    # AC charge-current cap setting (MAX_CHARGE_CURRENT_AC_* enum). sensor.
    max_charge_current_ac: str | None = None
    # Auto-unlock charge port setting (AUTO_UNLOCK_AC_* enum). sensor.
    auto_unlock_charge_port: str | None = None
    # Battery-care mode on/off (setting.bcam_activation). binary_sensor.
    battery_care_mode_active: bool | None = None
    # Bulk→trickle threshold (% — charging slows after this). sensor.
    charge_bulk_threshold_pct: int | None = None
    # Companion unit for the charge rate (CHARGE_RATE_UNIT_* enum) — LOW,
    # disabled-by-default. sensor.
    charge_rate_unit: str | None = None
    # B. Door / closure SAFE-state (2=safe / 3=unsafe — INVERSE polarity).
    # Front bonnet lock (locked_state_front_engine_bonnet 2=locked). binary_sensor.
    bonnet_locked: bool | None = None
    # All present closures secured (safe_state_* rollup, all==2). binary_sensor.
    closures_secured: bool | None = None
    # Service hatch open (state_service_hatch 2=open) — LOW. binary_sensor.
    service_hatch_open: bool | None = None
    # Rear spoiler deployed (state_spoiler 2=open) — LOW. binary_sensor.
    spoiler_open: bool | None = None
    # C. Trip odometer endpoints (km).
    # Distance covered in the long-term trip window. sensor (TOTAL_INCREASING).
    lifetime_trip_distance_km: int | None = None
    # Odometer when the long-term window began — LOW. sensor, diagnostic.
    lifetime_trip_start_odometer_km: int | None = None
    # Odometer when the current/last trip began — LOW. sensor, diagnostic.
    last_trip_start_odometer_km: int | None = None
    # D. Fuel / fluids / SCR.
    # Engine oil amount (litres). sensor, diagnostic.
    oil_level_liters: float | None = None
    # Failure-overwrite additional oil level (%) — LOW. sensor, diagnostic.
    oil_level_additional_pct: float | None = None
    # Oil dipstick electronic-function active (0/1) — LOW. binary_sensor.
    oil_dipstick_active: bool | None = None
    # Fuel reading is calculated rather than measured (fuel_level__accuracy
    # 1=calculated) — LOW. binary_sensor, diagnostic.
    fuel_level_estimated: bool | None = None
    # E. Tyres — pressure DELTA vs target (unit-ambiguous; sentinels 0/1
    # dropped at the parser). LOW — disabled-by-default. sensor, diagnostic.
    tyre_pressure_diff_fl: int | None = None
    tyre_pressure_diff_fr: int | None = None
    tyre_pressure_diff_rl: int | None = None
    tyre_pressure_diff_rr: int | None = None
    tyre_pressure_diff_spare: int | None = None
    # Tyres — ACTUAL per-wheel pressure (dict unit "10kPA / Bar / PSI/ kPA" is
    # ambiguous → unitless diagnostic; sentinels 0=unsupported/1=invalid dropped
    # at the parser). #528 front pair, #538 rear+spare. LOW — disabled-by-
    # default. sensor, diagnostic.
    tyre_pressure_actual_fl: int | None = None
    tyre_pressure_actual_fr: int | None = None
    tyre_pressure_actual_rl: int | None = None
    tyre_pressure_actual_rr: int | None = None
    tyre_pressure_actual_spare: int | None = None
    # Tyres — REQUIRED/target per-wheel pressure (#538). Same ambiguous unit →
    # unitless diagnostic; sentinels 0/1 dropped at the parser. LOW — disabled-
    # by-default. sensor, diagnostic.
    tyre_pressure_required_fl: int | None = None
    tyre_pressure_required_fr: int | None = None
    tyre_pressure_required_rl: int | None = None
    tyre_pressure_required_rr: int | None = None
    tyre_pressure_required_spare: int | None = None
    # F. Lights / energy / misc.
    # Parking lights state (parking_lights enum → off/left/right/both). sensor.
    parking_lights_state: str | None = None
    # Auxiliary/12V battery energy-management level (%). sensor, diagnostic.
    aux_battery_energy_pct: int | None = None
    # Auxiliary/12V battery BEM level-2 pre-warning alert time (bem_alert_time).
    # Dict type=number ("delay after activation of the BEM2 pre-warning"), but the
    # observed portal value is an absolute ISO timestamp → passthrough via
    # _epoch_or_iso (tolerates epoch OR ISO). sensor (TIMESTAMP), diagnostic,
    # disabled-by-default. EU-Data-Act dialect only.
    aux_battery_bem_alert_at: Any | None = None
    # Instrument-cluster warning bitmask — RAW hex/interpreted value only, no
    # decode. LOW — disabled-by-default. sensor, diagnostic.
    dashboard_warnings_raw: str | None = None
    # #901 (Mezzo1973, volkswagen) — best-effort LOW-confidence driving-telemetry
    # from the EU-Data-Act feed. Types inferred from Scout samples; enums/units
    # unconfirmed beyond speed's documented km/h. All disabled-by-default.
    # Instantaneous vehicle speed (km/h; km/h grounded in the parser dictionary).
    current_speed_kmh: float | None = None
    # Ignition state — raw string (sample "keyContact"); enum domain unknown, so
    # no fixed options / device_class. sensor, diagnostic.
    ignition_state: str | None = None
    # Brake-pressure indication — raw numeric (sample "0"); unit unconfirmed, so
    # no unit / device_class. sensor, diagnostic.
    brake_pressure_indication: float | None = None
    # Driver-is-braking indication (sample "0" → off) — binary_sensor, no
    # device_class.
    driver_braking_active: bool | None = None
    # Climatisation error code; "0"/"#0" (no error) dropped → None. sensor.
    climate_error_code: str | None = None
    # Window-heating error code; "0"/"#0" (no error) dropped → None. sensor.
    window_heating_error_code: str | None = None
    # G. v2.15.3 (#517) — consumption / range aggregates (EU-Data-Act dialect).
    # Avg auxiliary-consumer consumption (dict kwH/1000km → kWh/100 km). sensor.
    last_trip_avg_aux_consumption_kwh_100km: float | None = None
    lifetime_avg_aux_consumption_kwh_100km: float | None = None
    # Avg gas (CNG) consumption, long-term (dict kg/1000km → kg/100 km). sensor.
    lifetime_avg_gas_consumption_kg_100km: float | None = None
    # Avg gas (CNG) consumption, last trip (dict kg/1000km → kg/100 km). sensor.
    last_trip_avg_gas_consumption_kg_100km: float | None = None
    # Gained range distance, long-term (dict 100m → km). sensor (TOTAL_INCREASING).
    lifetime_range_gain_km: float | None = None
    # Gained range distance, last trip (dict 100m → km). sensor.
    last_trip_range_gain_km: float | None = None
    # Distance driven without emission, long-term (dict 100m → km). sensor.
    lifetime_zero_emission_km: float | None = None
    # Distance driven without emission, last trip (dict 100m → km). sensor.
    last_trip_zero_emission_km: float | None = None
    # Trigger info about the last battery-charger update (string, e.g. "other").
    # LOW — disabled-by-default. sensor, diagnostic.
    charger_update_trigger: str | None = None
    # v2.16.2 (#636) — report-delivery trigger enum (ROA/ICL/USM/ICL_REMOTE/
    # ROA_REMOTE, "Trigger of the call service"). LOW — disabled-by-default.
    # sensor, diagnostic. Applies to all EU-Data-Act cars (not electric-only).
    report_trigger: str | None = None

    # v2.15.3 (#518) — EU-Data-Act charging-detail string family. All
    # dict-confirmed type=string (no enum list in the dict). LOW —
    # disabled-by-default diagnostic sensors. Junk sentinels (invalid/
    # unavailable/notAvailable) are dropped to None at the parser so single-
    # port cars don't get a dead entity; the fields stay defined so two-port
    # cars surface plug2 (NEVER suppress Scout fields).
    # active_target_soc: the CURRENTLY-active charge goal (distinct from the
    # target_soc SETTING above). No SoC token in the entity NAME ("Active
    # charge target").
    active_target_soc: str | None = None
    # Details of remaining charge time (free-form string; not the numeric ETA).
    charge_time_display: str | None = None
    # Charging plug1 (primary port) flap / lock / infrastructure states.
    charging_plug1_flap_lock_state: str | None = None
    charging_plug1_flap_state: str | None = None
    charging_plug1_infrastructure_state: str | None = None
    charging_plug1_lock_state: str | None = None
    # Charging plug2 (second port — dual-port cars) connection / flap / lock /
    # infrastructure states. Mirror of plug1 but a SECOND port; kept separate,
    # NOT folded into plug_connected/plug_state.
    charging_plug2_connectionstate: str | None = None
    charging_plug2_flap_lock_state: str | None = None
    charging_plug2_flap_state: str | None = None
    charging_plug2_infrastructure_state: str | None = None
    charging_plug2_lock_state: str | None = None

    # ── v2.15.4 — EU Data Act portal new fields (#521/#522 Scout) ────────────
    # All written by _eu_data_act.py only (EU-Data-Act dialect).
    # Next-charging-timer estimated start/finish (ISO timestamps). The car's
    # OWN estimate for when the next scheduled charge will begin/end — distinct
    # from next_charging_time (Skoda profile schedule). sensor (TIMESTAMP),
    # diagnostic.
    next_charge_timer_start_at: Any | None = None
    next_charge_timer_finish_at: Any | None = None
    # Whether the next-charge target is reachable in time
    # (TARGET_REACHABILITY_* enum → shortened). sensor, diagnostic.
    next_charge_target_reachability: str | None = None
    # Which timer slot (1-15) is the next charging timer — dict-confirmed
    # type=number, unit=null ("Profile1: 1,2,3 ... Profile5: 13,14,15"). A
    # plain slot index, low user value → disabled-by-default. sensor (NUMBER),
    # diagnostic. EU-Data-Act dialect only.
    next_charge_timer_number: int | None = None
    # Slope (gradient) energy consumption while ascending / descending — raw
    # physical_value, unit unconfirmed (dict unit=null), gated on value_type.
    # LOW — disabled-by-default. sensor, diagnostic.
    ascent_slope_consumption: float | None = None
    descent_slope_consumption: float | None = None
    # Which report this poll's payload represents (REPORT_TYPE_* enum →
    # shortened) — metadata, not telemetry. LOW — disabled-by-default.
    # sensor, diagnostic.
    report_type: str | None = None
    # Delivery/sync result status of the app- and master-data channel
    # (generic "result" enums, dict lists no values → raw value shortened
    # for display). Metadata, not telemetry. LOW — disabled-by-default.
    # sensor, diagnostic.
    result_app: str | None = None
    result_master: str | None = None
    # v2.15.5 — why the report was sent to the backend (UPDATE_REASON_* enum →
    # shortened). dict-confirmed values (CHARGING / CLAMP15_ON|OFF /
    # CLIMATISATION / OTHER / INVALID). Metadata, not telemetry. LOW —
    # disabled-by-default sensor, diagnostic.
    update_reason: str | None = None

    # ── v2.15.4 (#523) — EU Data Act portal new fields ───────────────────────
    # All written by _eu_data_act.py only (EU-Data-Act dialect). Climatisation
    # settings are on/off bools (dict type=string, Climatisation cluster).
    # Short conditioning when the car is unlocked (setting_climatisation_at_
    # unlock). binary_sensor, diagnostic.
    climatisation_at_unlock: bool | None = None
    # Glass-surface / mirror heating active (setting_mirror_heating_enabled).
    # binary_sensor, diagnostic.
    mirror_heating_enabled: bool | None = None
    # Extended conditioning per climate zone enabled (setting_zone_enabled_
    # front_left / _front_right). binary_sensor, diagnostic.
    climate_zone_front_left_enabled: bool | None = None
    climate_zone_front_right_enabled: bool | None = None
    # v2.17.5 — glass/mirror heating currently ACTIVE (state_mirror_heating_
    # active) — distinct from the *enabled* setting above. binary_sensor, diag.
    mirror_heating_active: bool | None = None
    # v2.17.5 — extended conditioning currently ACTIVE per zone (state_zone_
    # active_*) — the live status twin of the *_enabled settings. binary, diag.
    climate_zone_active_front_left: bool | None = None
    climate_zone_active_front_right: bool | None = None
    climate_zone_active_rear_left: bool | None = None
    climate_zone_active_rear_right: bool | None = None
    # Charging-related action (start_stop_action — dict type=string, no enum
    # list; _shorten_enum passes unprefixed values through). LOW —
    # disabled-by-default. sensor, diagnostic.
    start_stop_action: str | None = None
    # start_stop_modification — dict type=string, "Contains the detail related
    # to start stop modification". Distinct from start_stop_action. No enum list
    # → _shorten_enum passes unprefixed values through. LOW — disabled-by-
    # default. sensor, diagnostic.
    start_stop_modification: str | None = None

    # — BFF / selectivestatus dialect NEW fields —
    # Per-corner tire pressure STATE strings (shared — EU tires.[*].state and
    # BFF {corner}TireState both write these). Lowercased passthrough.
    tire_pressure_fl_state: str | None = None
    tire_pressure_fr_state: str | None = None
    tire_pressure_rl_state: str | None = None
    tire_pressure_rr_state: str | None = None
    # Per-corner tire error code (int). Sentinels 0/1 dropped → None.
    tire_pressure_fl_errorcode: int | None = None
    tire_pressure_fr_errorcode: int | None = None
    tire_pressure_rl_errorcode: int | None = None
    tire_pressure_rr_errorcode: int | None = None
    # LPG (autogas) remaining range (km).
    lpg_range_km: int | None = None
    # Engine running/idle status (enum/lowercased; bool→on/off). Diagnostic.
    engine_status: str | None = None
    # Avg auxiliary consumption — LOW, unit ambiguous, NOT rescaled.
    # Disabled-by-default. (kWh)
    trip_avg_aux_consumption_kwh: float | None = None
    # Energy charged at departure — LOW. Disabled-by-default. (kWh)
    departure_charge_kwh: float | None = None

    # ── v2.15.5 (#541) — V2G / bidirectional-charging charge-level limits ─────
    # Written by _eu_data_act.py only (EU-Data-Act dialect). dict-confirmed
    # type=number; "Additional SOC range for bidirectional charging" → percent.
    # Upper / lower charge-level limit the car may bidi-charge within. LOW —
    # disabled-by-default diagnostic sensors. NO 'SoC' token in entity NAMES.
    bidi_max_charge_level_pct: int | None = None
    bidi_min_charge_level_pct: int | None = None
    # v2.26.0 (#981) — the rest of the bidirectional_charging_mode.* family: the
    # V2G usage accounting (energy dispensed, cycles, operating hours, quota) and
    # each one's limit/threshold. dict type=number, unit=null → mapped UNITLESS
    # with no device_class (like the bcam pair), so a wrong-unit guess can never
    # ship. LOW — disabled-by-default diagnostic sensors.
    bidi_energy_used: float | None = None
    bidi_energy_used_threshold: float | None = None
    bidi_cycles: int | None = None
    bidi_cycles_threshold: int | None = None
    bidi_operating_hours: float | None = None
    bidi_operating_hours_threshold: float | None = None
    bidi_quota: float | None = None
    bidi_quota_threshold: float | None = None
    # ── v2.15.5 (#544) — sunroof motor hood 1 POSITION (distinct from the
    # open/closed STATE in sunroof_open). dict-confirmed type=number, unit "%"
    # (0 = closed). LOW — disabled-by-default diagnostic sensor.
    sunroof_position_pct: int | None = None
    # ── v2.15.11 (#614) — spoiler POSITION in % (distinct from the open/closed
    # STATE in spoiler_open). dict-confirmed type=number, unit "%" (0 = closed),
    # mirrors sunroof_position_pct. LOW — disabled-by-default diagnostic sensor.
    spoiler_position_pct: int | None = None
    # ── Unreleased (Scout #938/#947) — battery charging care mode (BCAM) score.
    # Written by _eu_data_act.py only (EU-Data-Act dialect). dict-confirmed
    # type=number, unit=null: bcam_score = "Score value indicates the use of the
    # battery charging care mode", bcam_score_threshold = "Threshold up to which
    # the battery charging care mode was used in an exemplary manner". Unit is
    # NOT given by the dictionary, so both stay unitless with no device_class.
    # LOW — disabled-by-default diagnostic sensors.
    battery_care_score: float | None = None
    battery_care_score_threshold: float | None = None

    # ── v2.16.0 — volkswagen.de authproxy live-status read-path (BETA) ────────
    # Written by auth/_website_authproxy.py only (opt-in, read-only channel).
    # All three back disabled-by-default sensors — the underlying endpoints are
    # unvalidated live (warninglights/last + transactionhistory), so users opt
    # in to test. Endpoint recipe cross-checked against rafaelhutter/
    # ha-volkswagen-connect (MIT); parsers are our own.
    #
    # Count of currently-active dashboard warning lights (0 = all OK). Distinct
    # from the aggregate ``warning_count`` other channels populate. sensor
    # (MEASUREMENT), diagnostic.
    active_warning_lights_count: int | None = None
    # Last CONFIRMED remote lock/unlock COMMAND (not a live lock state — that's
    # attestation-gated). "lock" / "unlock". sensor (enum), diagnostic.
    last_lock_action: str | None = None
    # ISO timestamp of that last lock/unlock command. sensor (TIMESTAMP),
    # diagnostic.
    last_lock_action_at: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict for coordinator.vehicles storage."""
        from dataclasses import asdict  # noqa: PLC0415
        return asdict(self)
