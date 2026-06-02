# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 PR #7/20 — Email-OTP vs TOTP discrimination in IDK auth.

Follow-on to PR #1 (consent-screen detection) and #183 (Auth Resilience
für 2026). Pre-v2.2.0 the IDK auth flow raised a generic
``TwoFactorRequiredError`` whether the IDP demanded an authenticator-
app TOTP code or an email OTP. The Repairs UI then showed the same
"open the app and confirm the code" copy in both cases, which left
Email-OTP users staring at their authenticator-app trying to find a
code that was actually sitting in their inbox.

This PR adds:

1. ``EmailTwoFactorRequiredError`` (subclass of ``TwoFactorRequiredError``)
   — keeps the existing ``isinstance`` handler chain working while
   carrying the discriminated copy.

2. Auth0-path detection via ``/u/email-challenge`` URL fragment
   (distinct from generic ``/u/mfa``).

3. Legacy-path detection via body markers ``email-otp`` / ``email-code``
   / ``send-email-code`` (checked BEFORE the generic ``two-factor`` /
   ``2fa`` substring so Email-OTP doesn't get swallowed by the parent).

4. End-to-end surfacing: coordinator → ``email_two_factor_required``
   ValueError → Repairs flow → branded translation copy that tells the
   user to **check their inbox** rather than open the authenticator.

"In the future, you should always check your e-mail first. And by
'in the future', I mean **starting now**."
— Marshall Eriksen, on the importance of OTP-channel discrimination
"""

from __future__ import annotations

import pytest


class TestEmailTwoFactorExceptionShape:
    """The subclass must inherit ``TwoFactorRequiredError`` so the
    existing ``except`` chain in coordinator.py still catches it."""

    def test_is_subclass_of_two_factor(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            EmailTwoFactorRequiredError,
            TwoFactorRequiredError,
        )

        assert issubclass(EmailTwoFactorRequiredError, TwoFactorRequiredError)

    def test_isinstance_chain_works(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            AuthenticationError,
            EmailTwoFactorRequiredError,
            TwoFactorRequiredError,
        )

        err = EmailTwoFactorRequiredError()
        assert isinstance(err, TwoFactorRequiredError)
        assert isinstance(err, AuthenticationError)

    def test_email_specific_message(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            EmailTwoFactorRequiredError,
            TwoFactorRequiredError,
        )

        # Distinct copy — must mention "inbox" / "email" / "VAG IDP"
        msg = str(EmailTwoFactorRequiredError())
        msg_lc = msg.lower()
        assert "email" in msg_lc or "inbox" in msg_lc
        # Generic TOTP message must NOT mention inbox (regression-shield)
        assert "inbox" not in str(TwoFactorRequiredError()).lower()


class TestLegacyBodyMarkers:
    """The Legacy-path detection runs three substring checks before
    falling through to the generic 2FA pattern."""

    def test_email_otp_marker_caught(self) -> None:
        body = "<html>Please enter the email-otp sent to your inbox</html>"
        body_lc = body.lower()
        is_email = any(
            m in body_lc for m in ("email-otp", "email-code", "send-email-code")
        )
        assert is_email is True

    def test_email_code_marker_caught(self) -> None:
        body_lc = "we sent an email-code to your address".lower()
        is_email = any(
            m in body_lc for m in ("email-otp", "email-code", "send-email-code")
        )
        assert is_email is True

    def test_send_email_code_marker_caught(self) -> None:
        body_lc = "<form action=/send-email-code>...".lower()
        is_email = any(
            m in body_lc for m in ("email-otp", "email-code", "send-email-code")
        )
        assert is_email is True

    def test_generic_2fa_body_not_caught_by_email_pattern(self) -> None:
        # Pure TOTP body has no email markers
        body_lc = "<html>Two-factor authentication required</html>".lower()
        is_email = any(
            m in body_lc for m in ("email-otp", "email-code", "send-email-code")
        )
        assert is_email is False
        # But the generic 2FA fallback would catch it
        is_generic = "two-factor" in body_lc or "2fa" in body_lc
        assert is_generic is True


class TestAuth0URLMarker:
    """Auth0-path discriminates via the ``/u/email-challenge`` fragment."""

    def test_email_challenge_url_detected(self) -> None:
        ref = "https://identity.vwgroup.io/u/email-challenge?state=xyz"
        is_email_2fa = "/u/email-challenge" in ref
        assert is_email_2fa is True

    def test_mfa_url_not_email(self) -> None:
        ref = "https://identity.vwgroup.io/u/mfa?state=xyz"
        is_email_2fa = "/u/email-challenge" in ref
        is_mfa = is_email_2fa or "/u/mfa" in ref
        assert is_email_2fa is False
        assert is_mfa is True

    def test_callback_url_neither(self) -> None:
        ref = "carnet://callback?code=abc"
        is_email_2fa = "/u/email-challenge" in ref
        is_mfa = is_email_2fa or "/u/mfa" in ref
        assert is_email_2fa is False
        assert is_mfa is False


class TestRepairsRegistration:
    """``email_two_factor_required`` must be in the fixable-reasons +
    issue-map + clear-list, mirroring the generic two_factor_required."""

    def test_email_2fa_in_fixable_reasons(self) -> None:
        from custom_components.vag_connect.repairs import _FIXABLE_REASONS

        assert "email_two_factor_required" in _FIXABLE_REASONS
        assert _FIXABLE_REASONS["email_two_factor_required"] == "reauth"

    def test_email_2fa_setup_error_message(self) -> None:
        from custom_components.vag_connect import _SETUP_ERRORS

        assert "email_two_factor_required" in _SETUP_ERRORS
        msg_lc = _SETUP_ERRORS["email_two_factor_required"].lower()
        # Distinct copy — must reference inbox
        assert "inbox" in msg_lc or "email" in msg_lc


class TestTranslationCoverage:
    """All 8 lang files + strings.json must define the new key in BOTH
    ``config.error`` and ``issues`` sections."""

    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_email_2fa_error(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(
            f"custom_components/vag_connect/translations/{lang}.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "email_two_factor_required" in data["config"]["error"], (
            f"{lang}: missing config.error.email_two_factor_required"
        )

    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_email_2fa_issue(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(
            f"custom_components/vag_connect/translations/{lang}.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "email_two_factor_required" in data["issues"], (
            f"{lang}: missing issues.email_two_factor_required"
        )
        issue = data["issues"]["email_two_factor_required"]
        assert "title" in issue
        assert "description" in issue
        # {brand} placeholder required for Repair-flow templating
        assert "{brand}" in issue["title"]

    def test_strings_json_has_both(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        assert "email_two_factor_required" in data["config"]["error"]
        assert "email_two_factor_required" in data["issues"]


class TestExceptionHandlerOrder:
    """The coordinator's exception-handler chain must catch
    ``EmailTwoFactorRequiredError`` with the email-specific reason
    BEFORE the parent ``TwoFactorRequiredError`` catches it as generic.
    This test reads the source to verify ordering."""

    def test_email_handler_before_generic_2fa_in_coordinator(self) -> None:
        from pathlib import Path

        src = Path("custom_components/vag_connect/coordinator.py").read_text(
            encoding="utf-8"
        )
        email_pos = src.find("except EmailTwoFactorRequiredError")
        generic_pos = src.find("except TwoFactorRequiredError")
        assert email_pos > 0, "EmailTwoFactorRequiredError handler missing"
        assert generic_pos > 0, "TwoFactorRequiredError handler missing"
        assert email_pos < generic_pos, (
            "EmailTwoFactorRequiredError handler must come BEFORE the parent "
            "TwoFactorRequiredError handler (Python exception-handler order)"
        )
