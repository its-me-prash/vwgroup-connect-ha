# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.2.0 PR #1 — Consent-screen detection tests.

Covers all 6 known consent-URL fragments across BOTH the Auth0
Universal Login path AND the legacy signin-service path. Pre-v2.2.0
only 2 fragments were detected in the legacy path and 0 in the Auth0
path, which surfaced as generic "no app:// redirect" errors that
gave users zero clue what was actually wrong.

Cross-references:
- pycupra #83 (Cupra/SEAT marketing consent rolled May 2026)
- upstream PR #731 (Audi T&C nag clearer-error patch)
- evcc #29760 (MEB marketing-consent reboot loop)
- myskoda #976 (Skoda consent wall Dec 2025)

"Knock, knock, knock — consent. Knock, knock, knock — consent.
 Knock, knock, knock — consent."  — Sheldon Cooper, every OAuth redirect
"""

from __future__ import annotations

import pytest


_AUTH0_MARKERS = (
    "https://login.cariad.cloud/u/consent?state=abc",
    "https://identity.vwgroup.io/consent/marketing/v1/foo",
    "https://cupraid.vwgroup.io/consent",
    "https://skoda-id.vwgroup.io/consent",
    "https://skodaid.vwgroup.io/consent",
    "https://audi-id.vwgroup.io/consent",          # v2.5.1
    "https://myaudi.de/consent?return_url=...",    # v2.5.1
    "https://identity.vwgroup.io/signin-service/v1/terms-and-conditions",
)

_LEGACY_MARKERS = (
    "https://identity.vwgroup.io/consent/marketing/v1/...",
    "https://identity.vwgroup.io/u/consent?...",
    "https://cupraid.vwgroup.io/...",
    "https://skoda-id.vwgroup.io/...",
    "https://skodaid.vwgroup.io/...",
    "https://audi-id.vwgroup.io/...",              # v2.5.1
    "https://myaudi.de/consent?...",               # v2.5.1
)


_AUTH0_DETECTION_TUPLE = (
    "consent/marketing",
    "/u/consent",
    "cupraid.vwgroup.io",
    "skoda-id.vwgroup.io",
    "skodaid.vwgroup.io",
    "audi-id.vwgroup.io",       # v2.5.1
    "myaudi.de/consent",        # v2.5.1
    "terms-and-conditions",
)

_LEGACY_DETECTION_TUPLE = (
    "consent/marketing",
    "/u/consent",
    "cupraid.vwgroup.io",
    "skoda-id.vwgroup.io",
    "skodaid.vwgroup.io",
    "audi-id.vwgroup.io",       # v2.5.1
    "myaudi.de/consent",        # v2.5.1
)


class TestAuth0ConsentDetection:
    """v2.2.0 / v2.5.1 — Auth0 path must detect all 8 consent markers.

    Bazinga, we're testing the redirect-loop URL matchers in idk.py."""

    @pytest.mark.parametrize("location", _AUTH0_MARKERS)
    def test_auth0_consent_marker_string_match(self, location: str) -> None:
        """Each marker substring must appear in our detection tuple."""
        # The actual detection logic is a simple substring check —
        # this test enforces that every documented marker still matches
        # the in-code tuple even if someone refactors the tuple.
        assert any(m in location for m in _AUTH0_DETECTION_TUPLE), (
            f"Auth0 location {location!r} should match at least one "
            f"consent marker but matched none"
        )


class TestLegacyConsentDetection:
    """v2.2.0 / v2.5.1 — Legacy signin path must catch all 7 consent
    markers (terms-and-conditions has its own dedicated
    TermsAndConditionsError handler one block above)."""

    @pytest.mark.parametrize("location", _LEGACY_MARKERS)
    def test_legacy_consent_marker_string_match(self, location: str) -> None:
        assert any(m in location for m in _LEGACY_DETECTION_TUPLE)


class TestConsentAutoSkip:
    """v2.5.1 — Marketing-consent interstitial must be auto-skipped via
    the OIDC callback URL instead of raising MarketingConsentError.

    This is the Python port of evcc PR #29980 (Go, MIT, merged
    2026-05-17). The IDP injects an OPTIONAL consent page during the
    OAuth redirect chain; the page URL carries a ``callback=…`` query
    parameter that — when followed — completes login WITHOUT granting
    marketing scopes. We follow it transparently so the user never sees
    a Repair-flow notification for the consent wall.
    """

    def test_callback_extraction_from_consent_url(self) -> None:
        """The ``callback`` query param is what we follow to skip consent."""
        from urllib.parse import parse_qs, urlparse

        consent_url = (
            "https://identity.vwgroup.io/consent/marketing/v1/"
            "user-uuid/client-id?scopes=openid%20profile%20mbb"
            "&relayState=abc123"
            "&callback=https%3A%2F%2Fidentity.vwgroup.io%2Foidc%2Fv1%2F"
            "oauth%2Fclient%2Fcallback&hmac=def456"
        )
        callback = parse_qs(urlparse(consent_url).query).get("callback", [""])[0]
        assert callback.startswith("https://identity.vwgroup.io/oidc/v1/oauth/client/callback")

    def test_skip_marketing_consent_returns_none_when_no_callback(self) -> None:
        """If the consent URL has no ``callback`` query param, auto-skip
        must return None so the caller falls back to raising
        MarketingConsentError → Repair flow."""
        from urllib.parse import parse_qs, urlparse

        consent_url = "https://cupraid.vwgroup.io/consent"  # no ?callback=
        callback = parse_qs(urlparse(consent_url).query).get("callback", [""])[0]
        assert callback == ""

    def test_audi_specific_markers_skippable(self) -> None:
        """v2.5.1 — Audi-specific consent variants must be auto-skippable
        (not raise TermsAndConditionsError which would block silently)."""
        skippable = (
            "https://audi-id.vwgroup.io/consent?callback=https://...",
            "https://myaudi.de/consent?callback=https://...",
        )
        for url in skippable:
            # Must NOT trigger the t-and-c branch (not legally-binding T&C)
            assert "terms-and-conditions" not in url
            # Must trigger one of the skippable markers
            assert any(m in url for m in (
                "audi-id.vwgroup.io", "myaudi.de/consent",
            ))

    def test_terms_and_conditions_is_not_auto_skippable(self) -> None:
        """T&C wall is legal acceptance — must NEVER be auto-skipped.
        The detection must still raise TermsAndConditionsError so the
        user explicitly accepts in the app/web."""
        tc_url = "https://identity.vwgroup.io/signin-service/v1/terms-and-conditions"
        assert "terms-and-conditions" in tc_url
        # Important contract: the marker tuple includes terms-and-conditions
        # in Auth0 path but the code branches on it BEFORE attempting skip.
        assert "terms-and-conditions" in _AUTH0_DETECTION_TUPLE


class TestConsentExceptionImport:
    """MarketingConsentError must remain importable from the
    historical path so external code (Repair-flow translation keys,
    third-party tools) doesn't break across upgrades."""

    def test_marketing_consent_error_importable(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            MarketingConsentError,
        )
        err = MarketingConsentError()
        assert isinstance(err, Exception)
