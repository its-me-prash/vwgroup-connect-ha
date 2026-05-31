# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.5.11 — Field-tested Auth Hardening tests.

Three patches under test:

1. **PATCH 1** — Per-brand ``x-android-package-name``. Pre-v2.5.11 the
   ``_cariad_token_headers()`` helper hardcoded the Audi package name
   for ALL brands. Tests verify the parameter now flows through.

2. **PATCH 2** — Audi market-config dynamic discovery module. Tests
   verify the URL-derivation logic and the graceful-fallback paths.

3. **PATCH 3** — evcc Audi client_id alternate. Tests verify
   ``f4d0934f-...`` is now in the Audi fallback chain.

All tests are pure-data (no HA dep) — they import from
``custom_components.vag_connect.cariad.*`` but never instantiate a HA
runtime. Run via standard pytest.
"""

from __future__ import annotations

import pytest


# ── PATCH 1 — Per-brand x-android-package-name ─────────────────────────────


class TestBrandConfigAndroidPackageName:
    """BrandConfig now carries an android_package_name per brand."""

    def test_brand_config_has_field(self) -> None:
        from custom_components.vag_connect.cariad.models import BrandConfig
        # Field exists, defaults to empty string for back-compat
        bc = BrandConfig(
            name="x", client_id="y", redirect_uri="z://", user_agent="ua",
            api_base="https://example.invalid",
        )
        assert hasattr(bc, "android_package_name")
        assert bc.android_package_name == ""

    def test_audi_package_name(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_AUDI
        assert BRAND_AUDI.android_package_name == "de.myaudi.mobile.assistant"

    def test_vw_package_name(self) -> None:
        """Critical: VW MUST NOT impersonate Audi any more."""
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU
        assert BRAND_VW_EU.android_package_name == "de.volkswagen.weconnect"

    def test_seat_cupra_skoda_have_distinct_package_names(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_SEAT, BRAND_CUPRA, BRAND_SKODA,
        )
        names = {
            BRAND_SEAT.android_package_name,
            BRAND_CUPRA.android_package_name,
            BRAND_SKODA.android_package_name,
        }
        # All three must be distinct
        assert len(names) == 3
        # And none of them should be Audi (the pre-v2.5.11 bug value)
        assert "de.myaudi.mobile.assistant" not in names


class TestCariadTokenHeaders:
    """``_cariad_token_headers()`` accepts ``android_package_name``."""

    def test_header_uses_param(self) -> None:
        """v2.7.0b2: android_package_name only transmitted when
        include_assertion=True. Default 5-header set omits the assertion
        trio entirely."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _cariad_token_headers,
        )
        headers = _cariad_token_headers(
            "test-ua",
            android_package_name="com.example.testbrand",
            include_assertion=True,
        )
        assert headers["x-android-package-name"] == "com.example.testbrand"

    def test_default_remains_audi_for_back_compat(self) -> None:
        """v2.7.0b2 — default flipped to 5-header set (audi_connect_ha
        parity). x-android-package-name is no longer in the default
        output. Opt-in via include_assertion=True."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _cariad_token_headers,
        )
        headers = _cariad_token_headers("test-ua")
        assert "x-android-package-name" not in headers
        # When opted-in, the Audi-default value still applies
        headers_opt = _cariad_token_headers("test-ua", include_assertion=True)
        assert headers_opt["x-android-package-name"] == "de.myaudi.mobile.assistant"


# ── PATCH 2 — Audi market-config dynamic discovery ─────────────────────────


class TestAudiMarketConfigDerivation:
    """``derive_token_url_from_market_config()`` covers the URL-shape variants."""

    def test_oidc_suffix_derivation(self) -> None:
        from custom_components.vag_connect.cariad.auth._audi_market_config import (
            derive_token_url_from_market_config,
        )
        cfg = {
            "idkLoginServiceConfigurationURLProduction": (
                "https://emea.bff.cariad.digital/auth/v1/idk/oidc/openid-configuration"
            ),
        }
        url = derive_token_url_from_market_config(cfg)
        assert url == "https://emea.bff.cariad.digital/auth/v1/idk/oidc/token"

    def test_well_known_suffix_derivation(self) -> None:
        from custom_components.vag_connect.cariad.auth._audi_market_config import (
            derive_token_url_from_market_config,
        )
        cfg = {
            "idkLoginServiceConfigurationURLProduction": (
                "https://identity.vwgroup.io/.well-known/openid-configuration"
            ),
        }
        url = derive_token_url_from_market_config(cfg)
        assert url == "https://identity.vwgroup.io/token"

    def test_missing_key_returns_none(self) -> None:
        from custom_components.vag_connect.cariad.auth._audi_market_config import (
            derive_token_url_from_market_config,
        )
        assert derive_token_url_from_market_config({}) is None

    def test_non_string_value_returns_none(self) -> None:
        from custom_components.vag_connect.cariad.auth._audi_market_config import (
            derive_token_url_from_market_config,
        )
        cfg = {"idkLoginServiceConfigurationURLProduction": 12345}
        assert derive_token_url_from_market_config(cfg) is None  # type: ignore[dict-item]

    def test_unknown_suffix_returns_none(self) -> None:
        from custom_components.vag_connect.cariad.auth._audi_market_config import (
            derive_token_url_from_market_config,
        )
        cfg = {"idkLoginServiceConfigurationURLProduction": "https://example.invalid/foo"}
        # Doesn't end with /openid-configuration → derivation can't fire
        assert derive_token_url_from_market_config(cfg) is None


class TestAudiMarketConfigCacheAccess:
    """``cached_audi_market_config()`` returns ``{}`` until something is fetched."""

    def test_empty_when_no_fetch_yet(self) -> None:
        from custom_components.vag_connect.cariad.auth._audi_market_config import (
            cached_audi_market_config, _AUDI_MARKET_CACHE,
        )
        # Force-clear the cache so this test is order-independent.
        _AUDI_MARKET_CACHE.clear()
        assert cached_audi_market_config() == {}
        assert cached_audi_market_config("US", "en") == {}


# ── PATCH 3 — evcc Audi client_id alternate + c95f4fd2 deprecation ─────────


class TestAlternateClientIds:
    """``_ALTERNATE_CLIENT_IDS["audi"]`` now includes evcc's f4d0934f-..."""

    def test_audi_has_evcc_alternate(self) -> None:
        from custom_components.vag_connect.cariad.auth._auth_config_resolver import (
            _ALTERNATE_CLIENT_IDS,
        )
        audi_alts = _ALTERNATE_CLIENT_IDS["audi"]
        assert any(
            cid.startswith("f4d0934f-32bf-4ce4-b3c4-699a7049ad26")
            for cid in audi_alts
        ), (
            "evcc-derived Audi client_id alternate missing from "
            f"_ALTERNATE_CLIENT_IDS['audi']: {audi_alts}"
        )

    def test_audi_retains_apk_alternate(self) -> None:
        """The retro-mining APK alternate must still be present."""
        from custom_components.vag_connect.cariad.auth._auth_config_resolver import (
            _ALTERNATE_CLIENT_IDS,
        )
        audi_alts = _ALTERNATE_CLIENT_IDS["audi"]
        assert any(
            cid.startswith("16dd7960-431d-4b88-b3a5-35724b2fce01")
            for cid in audi_alts
        )


class TestC95F4FD2DeprecationFlag:
    """The one-shot deprecation flag exists and starts False."""

    def test_flag_class_exists(self) -> None:
        from custom_components.vag_connect.cariad.auth._auth_config_resolver import (
            _PriorPairDeprecation,
        )
        # The class exists with a `warned` attribute
        assert hasattr(_PriorPairDeprecation, "warned")
        # Don't assert specific bool — order-independent test, the flag
        # may have been flipped by another test. Just verify the type.
        assert isinstance(_PriorPairDeprecation.warned, bool)


class TestResolverChain:
    """End-to-end chain verification — pure-data, no network."""

    def test_audi_chain_contains_all_known_candidates(self) -> None:
        from custom_components.vag_connect.cariad.auth._auth_config_resolver import (
            AuthConfigResolver,
        )
        r = AuthConfigResolver(
            "audi",
            hardcoded_client_id="09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
            hardcoded_qmauth_secret=(
                "1ab69925ac179aaa4e83abe671a9476d176418b85bd706f1436ca15be647989c"
            ),
            hardcoded_qmauth_client_id="01da27b0",
            hardcoded_token_url=(
                "https://emea.bff.cariad.digital/auth/v1/idk/oidc/token"
            ),
        )
        chain = r.oauth_client_id_chain()
        # All four expected candidates present (no APK cache available in
        # test context — so chain is alternates + hardcoded only).
        assert "16dd7960-431d-4b88-b3a5-35724b2fce01@apps_vw-dilab_com" in chain
        assert "f4d0934f-32bf-4ce4-b3c4-699a7049ad26@apps_vw-dilab_com" in chain
        assert "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com" in chain
        # Hardcoded canonical is LAST per the resolver contract
        assert chain[-1] == "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com"

    def test_chain_dedupes_preserving_order(self) -> None:
        from custom_components.vag_connect.cariad.auth._auth_config_resolver import (
            AuthConfigResolver,
        )
        r = AuthConfigResolver(
            "audi",
            # Pass the f4d0934f alternate as the hardcoded canonical too —
            # the resolver must dedupe (not double-list).
            hardcoded_client_id="f4d0934f-32bf-4ce4-b3c4-699a7049ad26@apps_vw-dilab_com",
            hardcoded_qmauth_secret="00" * 32,
            hardcoded_qmauth_client_id="deadbeef",
            hardcoded_token_url="https://example.invalid/token",
        )
        chain = r.oauth_client_id_chain()
        assert chain.count(
            "f4d0934f-32bf-4ce4-b3c4-699a7049ad26@apps_vw-dilab_com"
        ) == 1, f"f4d0934f-... duplicated in chain: {chain}"
