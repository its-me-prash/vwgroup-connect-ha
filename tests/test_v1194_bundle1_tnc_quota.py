# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.19.4 — Bundle 1 (T&C deeplinks polish + Quota Repair-Issue).

Two extensions of existing repair-flow infrastructure:

1. **T&C polish**: brand-aware learn-more deeplinks instead of
   generic README link. When IDK backend signals "terms-and-conditions"
   body marker, the Repair-Issue's "Learn more" button now jumps
   directly to the right account portal (skodaid.vwgroup.io,
   vwid.vwgroup.io, my.audi.com, seat-cupra.cloud, my.porsche.com).
   Pattern adopted from skodaconnect/myskoda issues.py.

2. **Quota Repair-Issue**: extension of v1.19.1 X-RateLimit-Remaining
   sensor. New `raise_issue_quota_low()` + `clear_quota_issue()`
   surface a UI warning when the daily quota is approaching exhaustion
   (warn at <100 remaining, critical at <25). Coordinator's `_enrich`
   triggers based on observed header values; auto-clears when remaining
   recovers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch



# ─────────────────────────────────────────────────────────────────────────────
# A) Brand-aware T&C deeplinks
# ─────────────────────────────────────────────────────────────────────────────


class TestBrandAwareTnCDeeplinks:
    def test_skoda_uses_skodaid_url(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("skoda", "terms_and_conditions")
        assert "skodaid.vwgroup.io" in url

    def test_volkswagen_uses_vwid_url(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("volkswagen", "terms_and_conditions")
        assert "vwid.vwgroup.io" in url

    def test_audi_uses_my_audi_url(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("audi", "terms_and_conditions")
        assert "my.audi.com" in url

    def test_seat_uses_seat_cupra_cloud_url(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("seat", "terms_and_conditions")
        assert "seat-cupra.cloud" in url

    def test_cupra_uses_seat_cupra_cloud_url(self):
        """SEAT and CUPRA share OLA backend → same portal URL."""
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("cupra", "terms_and_conditions")
        assert "seat-cupra.cloud" in url

    def test_porsche_uses_my_porsche_url(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("porsche", "terms_and_conditions")
        assert "my.porsche.com" in url

    def test_volkswagen_na_uses_myvw_url(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("volkswagen_na", "terms_and_conditions")
        assert "vw.com/myvw" in url

    def test_unknown_brand_falls_back_to_readme(self):
        """Defensive — legacy entries or brand-less calls must still
        return a usable URL, not crash."""
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("unknown_brand", "terms_and_conditions")
        assert "github.com/its-me-prash/vag-connect-ha" in url

    def test_no_brand_falls_back_to_readme(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason(None, "terms_and_conditions")
        assert "github.com/its-me-prash/vag-connect-ha" in url

    def test_marketing_consent_also_uses_brand_url(self):
        """Same brand-aware deeplink applies to marketing-consent
        repair issues."""
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("skoda", "marketing_consent")
        assert "skodaid.vwgroup.io" in url

    def test_other_reasons_fall_back_to_readme(self):
        """Brand-aware URLs only apply to T&C / consent. Other reasons
        (invalid_credentials, two_factor_required) get the generic
        README — they're not portal-fixable."""
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url = _learn_url_for_reason("skoda", "invalid_credentials")
        assert "github.com/its-me-prash/vag-connect-ha" in url
        url = _learn_url_for_reason("skoda", "two_factor_required")
        assert "github.com/its-me-prash/vag-connect-ha" in url

    def test_case_insensitive_brand_lookup(self):
        from custom_components.vag_connect.repairs import _learn_url_for_reason
        url1 = _learn_url_for_reason("SKODA", "terms_and_conditions")
        url2 = _learn_url_for_reason("skoda", "terms_and_conditions")
        assert url1 == url2


# ─────────────────────────────────────────────────────────────────────────────
# B) raise_issue_auth_required: brand parameter forwarded to deeplink
# ─────────────────────────────────────────────────────────────────────────────


class TestRaiseIssueAuthBrandAware:
    def test_terms_call_uses_brand_url(self):
        from custom_components.vag_connect import repairs
        with patch(
            "custom_components.vag_connect.repairs.ir.async_create_issue"
        ) as mock_create:
            repairs.raise_issue_auth_required(
                MagicMock(),
                entry_id="abc",
                reason="terms_and_conditions",
                brand="skoda",
            )
            args, kwargs = mock_create.call_args
            assert "skodaid.vwgroup.io" in kwargs["learn_more_url"]

    def test_no_brand_uses_default(self):
        """Backwards-compat: callers without brand= still work."""
        from custom_components.vag_connect import repairs
        with patch(
            "custom_components.vag_connect.repairs.ir.async_create_issue"
        ) as mock_create:
            repairs.raise_issue_auth_required(
                MagicMock(),
                entry_id="abc",
                reason="terms_and_conditions",
            )
            args, kwargs = mock_create.call_args
            assert "github.com/its-me-prash/vag-connect-ha" in kwargs["learn_more_url"]


# ─────────────────────────────────────────────────────────────────────────────
# C) Quota Repair-Issue thresholds
# ─────────────────────────────────────────────────────────────────────────────


class TestQuotaRepairIssue:
    def test_thresholds_constants(self):
        from custom_components.vag_connect.repairs import (
            QUOTA_WARN_THRESHOLD, QUOTA_CRITICAL_THRESHOLD,
        )
        # Pycupra-style: warn at 100, critical at 25 — sane defaults
        # for ~1500/day MyCupra/MySeat quota
        assert QUOTA_WARN_THRESHOLD == 100
        assert QUOTA_CRITICAL_THRESHOLD == 25
        assert QUOTA_CRITICAL_THRESHOLD < QUOTA_WARN_THRESHOLD

    def test_raise_quota_low_warning_severity(self):
        from custom_components.vag_connect import repairs
        with patch(
            "custom_components.vag_connect.repairs.ir.async_create_issue"
        ) as mock_create:
            repairs.raise_issue_quota_low(
                MagicMock(), entry_id="abc",
                remaining=80, limit=1500, critical=False,
            )
            args, kwargs = mock_create.call_args
            assert kwargs["severity"] == repairs.ir.IssueSeverity.WARNING
            assert kwargs["translation_key"] == "quota_low"
            assert kwargs["translation_placeholders"]["remaining"] == "80"
            assert kwargs["translation_placeholders"]["limit"] == "1500"
            # 80/1500 = 5.3%
            assert "5.3" in kwargs["translation_placeholders"]["pct"]

    def test_raise_quota_critical_severity(self):
        from custom_components.vag_connect import repairs
        with patch(
            "custom_components.vag_connect.repairs.ir.async_create_issue"
        ) as mock_create:
            repairs.raise_issue_quota_low(
                MagicMock(), entry_id="abc",
                remaining=15, limit=1500, critical=True,
            )
            args, kwargs = mock_create.call_args
            assert kwargs["severity"] == repairs.ir.IssueSeverity.ERROR
            assert kwargs["translation_key"] == "quota_critical"

    def test_quota_issue_id_per_entry(self):
        """Issue ID must be unique per config-entry so multi-account
        users get separate warnings."""
        from custom_components.vag_connect import repairs
        with patch(
            "custom_components.vag_connect.repairs.ir.async_create_issue"
        ) as mock_create:
            repairs.raise_issue_quota_low(
                MagicMock(), entry_id="entry_A",
                remaining=80, limit=1500,
            )
            assert mock_create.call_args[0][2] == "entry_A_quota_low"
            mock_create.reset_mock()
            repairs.raise_issue_quota_low(
                MagicMock(), entry_id="entry_B",
                remaining=80, limit=1500,
            )
            assert mock_create.call_args[0][2] == "entry_B_quota_low"

    def test_clear_quota_issue(self):
        from custom_components.vag_connect import repairs
        with patch(
            "custom_components.vag_connect.repairs.ir.async_delete_issue"
        ) as mock_delete:
            repairs.clear_quota_issue(MagicMock(), entry_id="abc")
            mock_delete.assert_called_once()
            args = mock_delete.call_args[0]
            assert args[2] == "abc_quota_low"

    def test_quota_low_no_limit_pct_unknown(self):
        """Some endpoints may send X-RateLimit-Remaining without
        X-RateLimit-Limit — pct goes to '?', no division by zero."""
        from custom_components.vag_connect import repairs
        with patch(
            "custom_components.vag_connect.repairs.ir.async_create_issue"
        ) as mock_create:
            repairs.raise_issue_quota_low(
                MagicMock(), entry_id="abc",
                remaining=50, limit=None,
            )
            kwargs = mock_create.call_args[1]
            placeholders = kwargs["translation_placeholders"]
            assert placeholders["remaining"] == "50"
            assert "limit" not in placeholders
            assert "pct" not in placeholders
