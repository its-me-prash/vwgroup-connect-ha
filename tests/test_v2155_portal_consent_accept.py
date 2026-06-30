# Copyright 2026 Prash Balan (@its-me-prash) - GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.5 (#527 follow-on) — EU Data Act portal generic-consent handling.

Root cause (confirmed on v2.15.4 diagnostics, sarahlesage): after CORRECT
credentials the IDP can interject a generic OAuth consent grant page
(``identity.vwgroup.io/signin-service/v1/consent/users/{uid}/{client}``,
templateModel pageType='consent', status 200). The v2.15.4 classifier only
knew the MARKETING-consent markers, so this generic grant page matched nothing
and fell through to the credential catch-all → users with a valid password were
told "check email and password".

This suite covers the v2.15.5 fix:
  (a) REAL fix — login() auto-ACCEPTS the consent grant page (scrape form +
      POST) and login then COMPLETES (no exception, logged_in=True);
  (b) FALLBACK — when auto-accept can't complete (form has no fields, or the
      accept still lands on the consent page), the classifier flags it as
      PortalInteractionRequiredError("consent / terms acceptance"), NOT
      invalid_credentials and NOT MarketingConsentError;
  (c) a genuine bad-password landing still → plain AuthenticationError
      ("check email and password") — unchanged;
  (d) a marketing-consent landing still → MarketingConsentError (never
      auto-accepted as a generic grant).

HTTP is mocked exactly like test_v2154_portal_login_classify.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    classify_portal_login_failure,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    MarketingConsentError,
    PortalInteractionRequiredError,
)

# ── canned login-flow pages ─────────────────────────────────────────────────
_SIGNIN_HTML = (
    '<form action="/signin-service/v1/CLIENT/login/identifier">'
    '<input type="hidden" name="hmac" value="email_hmac">'
    '<input type="hidden" name="_csrf" value="csrf1">'
    '<input type="hidden" name="relayState" value="rs1">'
    '</form>'
)
_PASSWORD_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"hmac":"fresh_pw_hmac","relayState":"rs1",'
    '"postAction":"/signin-service/v1/CLIENT/login/authenticate"}, '
    'csrf_token: "csrf2"};</script>'
)

# A scrapeable generic-consent grant page: server-rendered <form> with the
# accept action + hidden anti-CSRF fields + the consentedScopes the grant
# endpoint validates (v2.15.7 — the gate keys on _csrf OR consentedScopes).
# This fixture keeps an explicit action so this file's session routing (which
# matches "/consent/" in the POST URL) stays intact; the EMPTY-action real
# form is covered separately in test_v2157_portal_consent_action.py.
_CONSENT_FORM_HTML = (
    '<script>window._IDK = {templateModel: {"template":"consent",'
    '"hmac":"consent_hmac","relayState":"rs1"}, csrf_token: "csrf3"};</script>'
    '<form action="/signin-service/v1/consent/users/UID/CLIENT">'
    '<input type="hidden" name="_csrf" value="csrf3">'
    '<input type="hidden" name="relayState" value="rs1">'
    '<input type="hidden" name="consentedScopes" value="profile">'
    '<input type="hidden" name="consentedScopes" value="cars">'
    '<button type="submit">Allow</button>'
    '<button type="submit" name="cancel" value="true">Cancel</button>'
    '</form>'
)
# A consent page with NO usable form fields → auto-accept must bail out.
_CONSENT_NOFORM_HTML = (
    '<script>window._IDK = {templateModel: {"template":"consent"}};</script>'
)
_BAD_CRED_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"hmac":"again","relayState":"rs1",'
    '"error":{"errorCode":"login.errors.password_invalid",'
    '"text":"Incorrect login data"}}, csrf_token: "x"};</script>'
)
_MARKETING_CONSENT_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"errorCode":"consent/marketing required"}};</script>'
)

_CONSENT_LANDING = (
    "https://identity.vwgroup.io/signin-service/v1/consent/users/UID/CLIENT"
)
_SIGNIN_LANDING = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/authenticate"
    "?relayState=rs1"
)
_PORTAL_OK_LANDING = "https://eu-data-act.drivesomethinggreater.com/dashboard"
_PORTAL_OK_HTML = "<html>logged in</html>"


class _FakeResp:
    def __init__(self, url: str, *, status: int = 200, text: str = "") -> None:
        self.url = url
        self.status = status
        self._text = text

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text


class _LoginSession:
    """Routes prime → authorize → identifier → credential POST → (consent).

    The credential POST lands on ``cred_landing`` (url/status/html). If that's
    the consent page, the subsequent accept POST (to the consent action URL)
    lands on ``accept_landing``.
    """

    def __init__(
        self,
        *,
        cred_landing: tuple[str, int, str],
        accept_landing: tuple[str, int, str] | None = None,
    ) -> None:
        self._cred = cred_landing
        self._accept = accept_landing

    def get(self, url: str, **kw: Any) -> _FakeResp:
        if url.endswith("/") and "drivesomethinggreater" in url:
            return _FakeResp(url, text="<html>portal</html>")
        if "authorize" in url:
            return _FakeResp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "identifier",
                text=_SIGNIN_HTML,
            )
        raise AssertionError(f"unmatched GET {url}")

    def post(self, url: str, **kw: Any) -> _FakeResp:
        if url.endswith("/login/identifier"):
            return _FakeResp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "authenticate?relayState=rs1",
                text=_PASSWORD_HTML,
            )
        if "/login/authenticate" in url:
            u, s, h = self._cred
            return _FakeResp(u, status=s, text=h)
        if "/consent/" in url:
            assert self._accept is not None, "unexpected consent accept POST"
            u, s, h = self._accept
            return _FakeResp(u, status=s, text=h)
        raise AssertionError(f"unmatched POST {url}")


async def _run_login_expect_error(session: _LoginSession) -> BaseException:
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError) as ei:
        await conn.login("user@example.com", "secret")
    return ei.value


# ── (a) REAL fix: auto-accept the consent grant → login completes ───────────

@pytest.mark.asyncio
async def test_consent_page_auto_accepted_login_completes() -> None:
    session = _LoginSession(
        cred_landing=(_CONSENT_LANDING, 200, _CONSENT_FORM_HTML),
        accept_landing=(_PORTAL_OK_LANDING, 200, _PORTAL_OK_HTML),
    )
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")  # must NOT raise
    assert conn.logged_in is True


@pytest.mark.asyncio
async def test_consent_page_pagetype_only_url_is_signin() -> None:
    """pageType=='consent' (URL not in the consent family) is still accepted."""
    cred_html = _CONSENT_FORM_HTML  # carries template=consent + form
    session = _LoginSession(
        cred_landing=(_SIGNIN_LANDING, 200, cred_html),
        accept_landing=(_PORTAL_OK_LANDING, 200, _PORTAL_OK_HTML),
    )
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")
    assert conn.logged_in is True


# ── (b) FALLBACK: auto-accept can't complete → PortalInteractionRequired ────

@pytest.mark.asyncio
async def test_consent_page_no_form_falls_back_to_portal_interaction() -> None:
    """Consent page with no scrapeable form → not auto-acceptable → typed
    non-credential exception (NOT invalid_credentials)."""
    session = _LoginSession(
        cred_landing=(_CONSENT_LANDING, 200, _CONSENT_NOFORM_HTML),
    )
    exc = await _run_login_expect_error(session)
    assert isinstance(exc, PortalInteractionRequiredError)
    assert "consent" in str(exc).lower()


@pytest.mark.asyncio
async def test_consent_accept_still_on_consent_falls_back() -> None:
    """Accept POST that still lands on the consent page (accept didn't take)
    → classifier flags it PortalInteractionRequired, never bad-password."""
    session = _LoginSession(
        cred_landing=(_CONSENT_LANDING, 200, _CONSENT_FORM_HTML),
        accept_landing=(_CONSENT_LANDING, 200, _CONSENT_FORM_HTML),
    )
    exc = await _run_login_expect_error(session)
    assert isinstance(exc, PortalInteractionRequiredError)
    assert type(exc) is not AuthenticationError or isinstance(
        exc, PortalInteractionRequiredError
    )


# ── (c) genuine bad password unchanged ──────────────────────────────────────

@pytest.mark.asyncio
async def test_bad_password_still_invalid_credentials() -> None:
    session = _LoginSession(
        cred_landing=(_SIGNIN_LANDING, 200, _BAD_CRED_HTML),
    )
    exc = await _run_login_expect_error(session)
    assert type(exc) is AuthenticationError
    assert not isinstance(exc, PortalInteractionRequiredError)
    assert "check email and password" in str(exc)


# ── (d) marketing consent still its own typed exception ─────────────────────

@pytest.mark.asyncio
async def test_marketing_consent_not_auto_accepted() -> None:
    """A marketing opt-in must NOT be auto-accepted as a generic grant — it
    stays on the MarketingConsentError path (user choice, not silent)."""
    session = _LoginSession(
        cred_landing=(_SIGNIN_LANDING, 200, _MARKETING_CONSENT_HTML),
    )
    exc = await _run_login_expect_error(session)
    assert isinstance(exc, MarketingConsentError)


# ── direct classifier unit tests ────────────────────────────────────────────

def test_classify_generic_consent_url() -> None:
    exc, ctx = classify_portal_login_failure(_CONSENT_LANDING, "<html></html>")
    assert isinstance(exc, PortalInteractionRequiredError)
    assert not isinstance(exc, MarketingConsentError)
    assert ctx["classified"] == "portal_interaction_required"


def test_classify_generic_consent_pagetype() -> None:
    exc, _ = classify_portal_login_failure(_SIGNIN_LANDING, _CONSENT_NOFORM_HTML)
    assert isinstance(exc, PortalInteractionRequiredError)


def test_classify_marketing_consent_still_marketing() -> None:
    """Marketing markers win over the generic-consent rule."""
    exc, _ = classify_portal_login_failure(
        _SIGNIN_LANDING, _MARKETING_CONSENT_HTML
    )
    assert isinstance(exc, MarketingConsentError)


def test_classify_bad_cred_still_none() -> None:
    exc, ctx = classify_portal_login_failure(_SIGNIN_LANDING, _BAD_CRED_HTML)
    assert exc is None
    assert ctx["classified"] == "invalid_credentials"
