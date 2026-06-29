# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.21.0 — Audi/VW MBB legacy-path migration (Phase 1).

Closes 8+ user-reported 404s for Audi A4 B9 / Q5 2021 / VW Golf 7
(2026-05-07 user-report). Older MIB3 cars don't speak Cariad-BFF —
they answer on the legacy MBB stack at
``mal-1a.prd.ece.vwg-connect.com`` + per-VIN ``msg.volkswagen.de``
or similar regional read-base.

Phase 1 (this release):
- HomeRegion-Helper wired in (was scaffolding since v1.17.6)
- MBBBackendCache: per-VIN backend flag with 7-day TTL
- is_cariad_wrapper_404(body) detection helper
- VWEUClient.command_wake auto-falls-back to MBB on wrapper-404
- Sticky cache: subsequent wake calls for same VIN go straight to MBB

Phase 2+ (future): lock/unlock SPIN flow, climate, charger, etc.
"""

from __future__ import annotations


import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) is_cariad_wrapper_404 detection
# ─────────────────────────────────────────────────────────────────────────────


class TestIsCariadWrapper404:
    def test_full_user_report_body_detected(self):
        """Verbatim body from 2026-05-07 user-report log."""
        from custom_components.vag_connect.cariad._mbb import (
            is_cariad_wrapper_404,
        )
        body = (
            'API error 404 for https://emea.bff.cariad.digital/...: '
            '{"error":{"message":"Not Found",'
            '"info":"Upstream service responded with an unexpected status. '
            'If the problem persists, please contact our support.",'
            '"code":4112,"group":2,"retry":true}}'
        )
        assert is_cariad_wrapper_404(body) is True

    def test_retry_true_alone_detected(self):
        """Truncated bodies may only have retry:true marker."""
        from custom_components.vag_connect.cariad._mbb import (
            is_cariad_wrapper_404,
        )
        assert is_cariad_wrapper_404('{"error":{"retry":true}}') is True
        assert is_cariad_wrapper_404("{'error':{'retry': true}}") is True

    def test_upstream_marker_alone_detected(self):
        from custom_components.vag_connect.cariad._mbb import (
            is_cariad_wrapper_404,
        )
        body = '{"error":{"info":"Upstream service responded"}}'
        assert is_cariad_wrapper_404(body) is True

    def test_genuine_404_without_markers_not_detected(self):
        """Plain 404 without Cariad's wrapper markers — could be a
        real integration bug. NOT detected as MBB-backed."""
        from custom_components.vag_connect.cariad._mbb import (
            is_cariad_wrapper_404,
        )
        assert is_cariad_wrapper_404('{"error":{"message":"Not Found"}}') is False

    def test_empty_body_not_detected(self):
        from custom_components.vag_connect.cariad._mbb import (
            is_cariad_wrapper_404,
        )
        assert is_cariad_wrapper_404("") is False
        assert is_cariad_wrapper_404(None) is False

    def test_case_insensitive_marker(self):
        """Defensive: backend may change casing in future."""
        from custom_components.vag_connect.cariad._mbb import (
            is_cariad_wrapper_404,
        )
        assert is_cariad_wrapper_404("UPSTREAM SERVICE RESPONDED") is True


# ─────────────────────────────────────────────────────────────────────────────
# B) MBBBackendCache
# ─────────────────────────────────────────────────────────────────────────────


class TestMBBBackendCache:
    def test_initial_get_returns_none(self):
        from custom_components.vag_connect.cariad._mbb import MBBBackendCache
        cache = MBBBackendCache()
        assert cache.get("VIN1") is None

    def test_set_then_get_returns_backend(self):
        from custom_components.vag_connect.cariad._mbb import MBBBackendCache
        cache = MBBBackendCache()
        cache.set("VIN1", "mbb")
        assert cache.get("VIN1") == "mbb"
        cache.set("VIN2", "cariad")
        assert cache.get("VIN2") == "cariad"

    def test_invalid_backend_raises(self):
        from custom_components.vag_connect.cariad._mbb import MBBBackendCache
        cache = MBBBackendCache()
        with pytest.raises(ValueError, match="must be 'cariad' or 'mbb'"):
            cache.set("VIN1", "unknown_backend")

    def test_per_vin_isolation(self):
        from custom_components.vag_connect.cariad._mbb import MBBBackendCache
        cache = MBBBackendCache()
        cache.set("VIN_AUDI_A4", "mbb")
        cache.set("VIN_AUDI_E_TRON", "cariad")
        assert cache.get("VIN_AUDI_A4") == "mbb"
        assert cache.get("VIN_AUDI_E_TRON") == "cariad"

    def test_clear_wipes_everything(self):
        from custom_components.vag_connect.cariad._mbb import MBBBackendCache
        cache = MBBBackendCache()
        cache.set("VIN1", "mbb")
        cache.set("VIN2", "cariad")
        cache.clear()
        assert cache.get("VIN1") is None
        assert cache.get("VIN2") is None


# ─────────────────────────────────────────────────────────────────────────────
# C) MBB URL builders
# ─────────────────────────────────────────────────────────────────────────────


class TestMBBURLBuilders:
    def test_audi_brand_segment(self):
        from custom_components.vag_connect.cariad._mbb import mbb_brand_segment
        assert mbb_brand_segment("audi") == "Audi"
        assert mbb_brand_segment("AUDI") == "Audi"

    def test_volkswagen_brand_segment(self):
        from custom_components.vag_connect.cariad._mbb import mbb_brand_segment
        assert mbb_brand_segment("volkswagen") == "VW"
        assert mbb_brand_segment("vw_eu") == "VW"

    def test_unknown_brand_defaults_to_vw(self):
        from custom_components.vag_connect.cariad._mbb import mbb_brand_segment
        assert mbb_brand_segment("unknown") == "VW"

    def test_build_mbb_wake_url_audi_de(self):
        """Verbatim URL pattern from upstream audi_services.py:478"""
        from custom_components.vag_connect.cariad._mbb import build_mbb_wake_url
        url = build_mbb_wake_url(
            read_base="https://msg.volkswagen.de",
            brand="audi",
            country="DE",
            vin="WAUZZZF43JA027519",
        )
        assert url == (
            "https://msg.volkswagen.de/fs-car/bs/vsr/v1/Audi/DE/"
            "vehicles/WAUZZZF43JA027519/requests"
        )

    def test_build_mbb_wake_url_vw_de(self):
        from custom_components.vag_connect.cariad._mbb import build_mbb_wake_url
        url = build_mbb_wake_url(
            read_base="https://msg.volkswagen.de",
            brand="volkswagen",
            country="DE",
            vin="WVWZZZAUZFW805377",
        )
        assert url == (
            "https://msg.volkswagen.de/fs-car/bs/vsr/v1/VW/DE/"
            "vehicles/WVWZZZAUZFW805377/requests"
        )

    def test_build_mbb_wake_url_other_country(self):
        from custom_components.vag_connect.cariad._mbb import build_mbb_wake_url
        url = build_mbb_wake_url(
            read_base="https://msg.volkswagen.de",
            brand="audi",
            country="AT",
            vin="WAUZZZ123456789",
        )
        assert "/Audi/AT/vehicles/" in url


# ─────────────────────────────────────────────────────────────────────────────
# D) Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestMBBConstants:
    def test_setter_base_is_mal_1a(self):
        from custom_components.vag_connect.cariad._mbb import MBB_SETTER_BASE
        assert MBB_SETTER_BASE == "https://mal-1a.prd.ece.vwg-connect.com"

    def test_default_read_base_is_msg_vw(self):
        from custom_components.vag_connect.cariad._mbb import MBB_DEFAULT_READ_BASE
        assert MBB_DEFAULT_READ_BASE == "https://msg.volkswagen.de"
