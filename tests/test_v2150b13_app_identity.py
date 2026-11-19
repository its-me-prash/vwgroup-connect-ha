# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b13 (H5) — VW EU We Connect app-identity fidelity pin.

The fs-car / MBB command endpoints gate on the app-identification headers. The
hardcoded We Connect app version is bumped to the live build whenever an App
Atlas dismantle confirms it; this pins the current value so it can't silently
drift stale (the lesson from the #503 VW-NA scope regression).
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1] / "custom_components/vag_connect"
_VW_EU = _ROOT / "cariad/api/vw_eu.py"
_AUDI = _ROOT / "cariad/api/audi.py"
_MODELS = _ROOT / "cariad/models.py"
_GRAPHQL = _ROOT / "cariad/api/graphql.py"


def test_weconnect_app_version_is_current() -> None:
    """Verified against the dismantled com.volkswagen.weconnect APK
    (versionName 4.8.1 / versionCode 408010, 2026-11-18 dismantle). Do NOT lower
    this without a fresh dismantle — a fidelity check on the fs-car endpoints
    rejects stale versions, which is exactly how an unverified value regresses a
    channel."""
    src = _VW_EU.read_text(encoding="utf-8")
    assert '"Volkswagen", "4.8.1"' in src
    assert "3.51.1" not in src  # the stale value must not creep back


def test_weconnect_user_agent_matches_mbb_app_identity() -> None:
    """The BrandConfig User-Agent and the MBB X-App-Version must name the SAME
    build — they drifted two generations apart (3.63.2 vs 4.1.1) until the
    2026-07 Atlas refresh, so the two channels announced different apps."""
    models = _MODELS.read_text(encoding="utf-8")
    assert 'user_agent="Volkswagen/4.8.1-android/14"' in models
    # The real manifest package is com.volkswagen.weconnect (4.8.1 androguard +
    # the app's X-Android-Package-Name); it must not revert to the de.* legacy
    # family it was confused with before 2026-11-18.
    assert 'android_package_name="com.volkswagen.weconnect"' in models
    assert '"de.volkswagen.weconnect"' not in models


def test_myaudi_app_version_is_current() -> None:
    """Verified against the dismantled de.myaudi.mobile.assistant APK
    (versionName 5.10.1 / versionCode 800345183, signing cert 8eae072f…,
    Google Play 2026-11-18). The User-Agent shape is the app's own
    (``core/network/internal/UserAgentExtensionsKt.a``): the build suffix is
    the baked-in build time, not a build-script placeholder."""
    from custom_components.vag_connect.cariad import models

    assert models.MYAUDI_APP_VERSION == "5.10.1"
    assert models.MYAUDI_VERSION_CODE == 800345183
    assert models.MYAUDI_USER_AGENT == (
        "Android/5.10.1 (Build 800345183.2611170047) Android/13"
    )


def test_every_myaudi_identity_site_uses_the_one_source() -> None:
    """Six sites named the app in three versions (5.5.1, 5.6.0, 5.8.1) until
    2026-11-18. Each must now carry the values from ``models.py``, so a bump
    is one edit and the channels cannot announce different builds again."""
    from types import SimpleNamespace

    from custom_components.vag_connect.cariad import models
    from custom_components.vag_connect.cariad.api import audi, graphql
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    from custom_components.vag_connect.cariad.auth import _auth0

    ua, version = models.MYAUDI_USER_AGENT, models.MYAUDI_APP_VERSION
    assert models.BRAND_AUDI.user_agent == ua
    assert models.BRAND_AUDI_NA.user_agent == ua
    assert audi._USER_AGENT == ua
    assert audi._APP_VERSION == version
    assert graphql._BRAND_USER_AGENTS["audi"] == ua
    assert graphql._BRAND_APP_VERSIONS["audi"] == version
    assert _auth0._USER_AGENT == ua
    fake = SimpleNamespace(_brand=SimpleNamespace(name="audi"))
    assert VWEUClient._mbb_app_identity(fake) == ("myAudi", version)


def test_no_stale_myaudi_identity_literal_on_the_wire() -> None:
    """Stale builds and the old build-script placeholder must not come back as
    string literals (comments may still name old versions)."""
    _AUTH0 = _ROOT / "cariad/auth/_auth0.py"
    _MARKET = _ROOT / "cariad/auth/_audi_market_config.py"
    for f in (_AUDI, _MODELS, _GRAPHQL, _VW_EU, _AUTH0, _MARKET):
        src = f.read_text(encoding="utf-8")
        for stale in ('"4.31.0"', "Android/4.31.0", "myAudi/4.18.0", '"4.18.0"',
                      '"myAudi", "4.24.0"', "800341641", '"5.5.1"', '"5.6.0"',
                      "Android/5.5.1", "Android/5.6.0", "Android/5.8.1",
                      "myAudi/5.5.1", "ext.buildTime", "?v=4.23.1"):
            assert stale not in src, f"{f.name} still ships stale {stale}"
