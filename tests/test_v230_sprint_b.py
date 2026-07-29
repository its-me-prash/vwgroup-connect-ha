# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.3.0 — Sprint B: VW NA auth-fix (#269) + Audi nav-aware charging (#264).

This single test-file pins the two user-facing changes that ship in
v2.3.0 MINOR:

1. **#269 (roberttco VW NA, 2026-05-21) — VW NA login fix**.
   Robert reported that login fails with HTTP 400 because the
   integration was using the EU IDP (``identity.vwgroup.io``) for VW
   NA's ``MYVW_ANDROID`` client_id, which is only registered against
   the NA-specific ``b-h-s.spr.{country}00.p.con-veh.net`` host.
   Confirmed via the matpoulin/CarConnectivity-connector-volkswagen-na
   reference implementation (Apache-2.0, cited in vw_na.py:4-6).

   Fix: generalized IDKAuth to accept four optional URL overrides
   (``authorize_url_override``, ``token_url_override``,
   ``idk_base_override``, ``signin_client_id_override``) so the VW NA
   client can route through the correct NA endpoints. EU brands (Audi,
   VW EU, Skoda, SEAT, CUPRA, Bentley, Lambo, Porsche) are unaffected
   — defaults preserved.

   These tests are source-level: they verify IDKAuth accepts the new
   kwargs without breaking existing callers, that vw_na.py constructs
   IDKAuth with the matpoulin-correct values, and that the brand-
   config scope was narrowed to ``"openid"`` per matpoulin.

2. **#264 (moltke69 Audi 2026-05-19) — Route-aware smart charging**.
   New backend fields surface a "navigation-aware" SoC target plus
   companion ETA — i.e. "charge only enough for your next planned
   navigation route". Distinct semantics from the existing static
   target_soc / remaining_charge_time, so they get separate sensor
   entities (``sensor.{prefix}_nav_target_soc_pct`` +
   ``sensor.{prefix}_remaining_charge_time_nav_min``).

   Plus a fallback in the existing ``climate_timer_enabled_count``
   parser: newer firmware nests timers under a unified
   ``departureTimers.climatisationTimersStatus.value.timers`` path
   instead of the legacy ``climatisationTimers.*`` path — both now
   resolve.

   Plus 7 silencer-adds covering the moltke69 scout paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_IDK_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "auth" / "idk.py"
_VW_NA_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "api" / "vw_na.py"
_VW_EU_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "api" / "vw_eu.py"
_MODELS_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "models.py"
_SENSOR_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "sensor.py"
_STRINGS_JSON = _REPO_ROOT / "custom_components" / "vag_connect" / "strings.json"
_UNEXPECTED_KEYS_PY = (
    _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "_unexpected_keys.py"
)


# ──────────────────────────────────────────────────────────────────────
# 1. #269 — VW NA IDKAuth overrides + vw_na.py wiring
# ──────────────────────────────────────────────────────────────────────


class TestIDKAuthOverrides:
    """IDKAuth must accept 4 optional kwargs without breaking EU callers."""

    def test_init_accepts_authorize_url_override(self) -> None:
        src = _IDK_PY.read_text(encoding="utf-8")
        assert "authorize_url_override:" in src
        assert "self._authorize_url = authorize_url_override or _AUTHORIZE_URL" in src

    def test_init_accepts_token_url_override(self) -> None:
        src = _IDK_PY.read_text(encoding="utf-8")
        assert "token_url_override:" in src
        assert "self._token_url_override = token_url_override" in src

    def test_init_accepts_idk_base_override(self) -> None:
        src = _IDK_PY.read_text(encoding="utf-8")
        assert "idk_base_override:" in src
        assert "self._idk_base = idk_base_override or _IDK_BASE" in src

    def test_init_accepts_signin_client_id_override(self) -> None:
        src = _IDK_PY.read_text(encoding="utf-8")
        assert "signin_client_id_override:" in src
        assert "self._signin_client_id = signin_client_id_override" in src

    def test_authorize_url_uses_instance_attribute(self) -> None:
        """The GET-authorize call must use self._authorize_url, not the constant."""
        src = _IDK_PY.read_text(encoding="utf-8")
        # The actual aiohttp request site:
        assert "self._session.get(\n            self._authorize_url," in src

    def test_token_endpoint_honors_override(self) -> None:
        """_get_token_endpoint must short-circuit to override when set."""
        src = _IDK_PY.read_text(encoding="utf-8")
        assert "if self._token_url_override:" in src
        assert "return self._token_url_override" in src

    def test_idk_base_threaded_through_origin_header(self) -> None:
        """Auth0 form POSTs must use self._idk_base for Origin header."""
        src = _IDK_PY.read_text(encoding="utf-8")
        assert '"Origin": self._idk_base,' in src

    def test_signin_fallback_uses_override(self) -> None:
        """Fallback signin URL must use self._signin_client_id, not _brand.client_id."""
        src = _IDK_PY.read_text(encoding="utf-8")
        # Two fallback sites (identifier + authenticate) — both must use override.
        assert "{self._signin_base}/{self._signin_client_id}/login/identifier" in src
        assert "{self._signin_base}/{self._signin_client_id}/login/authenticate" in src


class TestVWNAUsesNAOverrides:
    """vw_na.py must construct IDKAuth with the 4 matpoulin-correct overrides."""

    def test_na_idp_base_constant(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert '_NA_IDP_BASE = "https://identity.na.vwgroup.io"' in src

    def test_na_signin_guid_is_dormant_not_wired(self) -> None:
        """b14 (#503): matpoulin's old browser-client GUID is DORMANT — kept
        documented but NOT passed to IDKAuth. With it, NA login dead-ended at
        ``signin-service/v1/b680e751… → "no code"`` even after the b13 scope
        revert; the current flow uses the MYVW_ANDROID client throughout."""
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "_NA_SIGNIN_CLIENT_GUID_DORMANT" in src       # kept for the record
        assert "signin_client_id_override" not in src        # but NOT wired in

    def test_idkauth_constructed_with_authorize_override(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        # v2.26.1 (#990) — the authorize URL points at the fixed us00 OIDC proxy
        # (_NA_OIDC_PROXY_BASE), NOT the per-country data host. ca00 has no
        # working /oidc/v1/authorize (it 400s); the us00 proxy 302s to
        # identity.na for every NA country, and vrouleau confirmed CA signs in
        # there (v2.25 authenticated this way). Only api_base is per-country.
        assert 'authorize_url_override=f"{_NA_OIDC_PROXY_BASE}/oidc/v1/authorize"' in src

    def test_idkauth_constructed_with_token_override(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert 'token_url_override=f"{_NA_OIDC_PROXY_BASE}/oidc/v1/token"' in src

    def test_idkauth_constructed_with_idk_base_override(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "idk_base_override=_NA_IDP_BASE" in src

    def test_idkauth_NOT_constructed_with_signin_guid_override(self) -> None:
        """b14 (#503): the signin client_id override is removed, so IDKAuth
        falls back to ``brand.client_id`` (the per-country MYVW_ANDROID client)
        for the signin-service URL — matching the live MyVW app + a working US
        implementation. Re-adding the override regresses NA login to "no code"."""
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "signin_client_id_override" not in src

    def test_scope_stays_bare_openid(self) -> None:
        """REGRESSION PIN (#269 / #503): BRAND_VW_NA.scope MUST be bare
        "openid". NA tester roberttco hit a live HTTP 400 (#269) when the
        EU-style "openid profile cars vin" chain was requested against the
        NA IDP. v2.11.0 re-widened it from a source-read (never live-tested
        against NA) and silently regressed NA login to "no code" (#503).

        Do NOT re-widen this from another project's source without a live
        NA login test — that is exactly how it regressed. Two scopes are
        live-verified: bare "openid" works; the full EU chain 400s.
        """
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert 'scope="openid"' in src
        assert 'scope="openid profile cars vin"' not in src
        # The wider EU-style scope chain must also stay absent.
        assert 'scope="openid profile email offline_access mbb vin cars dealers"' not in src

    def test_models_brand_scope_matches_bare_openid(self) -> None:
        """models.BRAND_VW_NA_MODEL.scope must stay in sync with
        BRAND_VW_NA.scope at bare "openid" (see #269/#503 above)."""
        src = _MODELS_PY.read_text(encoding="utf-8")
        idx = src.find("BRAND_VW_NA_MODEL = BrandConfig(")
        assert idx > 0
        block = src[idx : idx + 600]
        assert 'scope="openid"' in block
        assert 'scope="openid profile cars vin"' not in block


# ──────────────────────────────────────────────────────────────────────
# 2. #264 — Audi nav-aware smart charging fields
# ──────────────────────────────────────────────────────────────────────


class TestScout264NavAwareCharging:
    """7 new fields from moltke69's scout — 2 parsed + 5 silenced (timers)."""

    def test_nav_target_soc_dataclass_field(self) -> None:
        src = _MODELS_PY.read_text(encoding="utf-8")
        assert "nav_target_soc_pct: int | None" in src

    def test_nav_eta_dataclass_field(self) -> None:
        src = _MODELS_PY.read_text(encoding="utf-8")
        assert "remaining_charge_time_nav_min: int | None" in src

    def test_nav_target_soc_parser(self) -> None:
        src = _VW_EU_PY.read_text(encoding="utf-8")
        assert "d.nav_target_soc_pct = int(nav_target)" in src
        assert '"navigationTargetSOC_pct"' in src

    def test_nav_eta_parser(self) -> None:
        src = _VW_EU_PY.read_text(encoding="utf-8")
        assert "d.remaining_charge_time_nav_min = int(nav_eta)" in src
        assert '"remainingChargingTimeNavigation_min"' in src

    def test_nav_target_soc_sensor(self) -> None:
        src = _SENSOR_PY.read_text(encoding="utf-8")
        assert 'key="nav_target_soc_pct"' in src
        # Disabled by default — power-user opt-in (only useful if user
        # actually uses the car's nav routing).
        assert "entity_registry_enabled_default=False" in src

    def test_nav_eta_sensor(self) -> None:
        src = _SENSOR_PY.read_text(encoding="utf-8")
        assert 'key="remaining_charge_time_nav_min"' in src

    def test_nav_strings_translations(self) -> None:
        src = _STRINGS_JSON.read_text(encoding="utf-8")
        assert '"nav_target_soc_pct"' in src
        assert '"remaining_charge_time_nav_min"' in src

    def test_silencer_navigation_paths_registered(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"charging.batteryStatus.value.navigationTargetSOC_pct"' in src
        assert '"charging.chargingStatus.value.remainingChargingTimeNavigation_min"' in src

    def test_silencer_departure_timers_subblocks(self) -> None:
        """5 paths from moltke69 under the new departureTimers parent shape."""
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"departureTimers.chargingTimersStatus"' in src
        assert '"departureTimers.chargingTimersStatus.value"' in src
        assert '"departureTimers.chargingTimersStatus.value.*"' in src
        assert '"departureTimers.climatisationTimersStatus"' in src
        assert '"departureTimers.climatisationTimersStatus.value"' in src
        assert '"departureTimers.climatisationTimersStatus.value.*"' in src

    def test_climate_timer_parser_has_departure_fallback(self) -> None:
        """Newer firmware nests timers under departureTimers — must be reached."""
        src = _VW_EU_PY.read_text(encoding="utf-8")
        # The fallback walk: when the legacy climatisationTimers.* path
        # is empty, try the new departureTimers.climatisationTimersStatus
        # path. Both populate d.climate_timer_enabled_count identically.
        assert 'v(\n                raw, "departureTimers", "climatisationTimersStatus"' in src

    def test_audi_inherits_via_brand_alias(self) -> None:
        """All silencer-adds in volkswagen catalog → Audi inherits."""
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert 'EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]' in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
