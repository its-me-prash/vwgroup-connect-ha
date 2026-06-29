# Copyright 2026 Prash Balan (@its-me-prash) - GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.4 (#527) — EU Data Act portal login outcome classification.

Multiple users with VALID VW-EU credentials were told "check email and
password" because ``EUDataActConnector.login()`` classified any non-redirect
landing purely from a URL substring, never consulting the page's
``templateModel`` error/errorCode or known interstitial markers. Both callers
then flattened EVERY ``AuthenticationError`` to ``invalid_credentials``.

These tests drive ``login()``'s failure classification with synthetic landing
pages and assert:
  (a) a genuine bad-credential re-render → AuthenticationError (NOT a typed
      interstitial subclass) → caller maps to ``invalid_credentials``;
  (b) a templateModel carrying a consent / T&C errorCode → the TYPED
      interstitial exception (NOT invalid_credentials);
  (c) a 2FA page → the 2FA typed exception;
  (d) an onboarding / unknown-but-non-credential portal error →
      PortalInteractionRequiredError;
  (e) the caller mapping (config_flow._oportal_test_login) for each case.

The HTTP layer is mocked exactly like the existing portal tests
(``test_v2120_eu_data_act_connector``): a fake session routes the
prime → authorize → identifier → credential POST steps.
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
    EmailTwoFactorRequiredError,
    MarketingConsentError,
    PortalInteractionRequiredError,
    TermsAndConditionsError,
    TwoFactorRequiredError,
)


# ── canned login-flow pages (reused from the v2.12.0 connector tests) ───────
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

# Failure landing pages (what step 3's credential POST lands on).
_BAD_CRED_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"hmac":"again","relayState":"rs1",'
    '"error":{"errorCode":"login.error.password_invalid",'
    '"text":"Incorrect login data"}}, csrf_token: "x"};</script>'
)
_TC_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"template":"terms-and-conditions",'
    '"error":{"errorCode":"terms.not.accepted"}}};</script>'
)
_CONSENT_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"errorCode":"consent/marketing required"}};</script>'
)
_2FA_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"template":"mfa-challenge","errorCode":"two-factor"}};</script>'
)
_EMAIL_2FA_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"template":"email-otp"}};</script>'
)
_ONBOARDING_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"template":"onboarding","errorCode":"region-select"}};</script>'
)
_UNKNOWN_ERR_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"error":{"errorCode":"backend.temporarily.unavailable"}}};</script>'
)


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
    """Routes the login steps; the credential POST lands on a configurable
    (url, status, html) failure page so we can drive the classifier."""

    def __init__(
        self, *, landing_url: str, landing_status: int, landing_html: str
    ) -> None:
        self._landing_url = landing_url
        self._landing_status = landing_status
        self._landing_html = landing_html

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
            return _FakeResp(
                self._landing_url,
                status=self._landing_status,
                text=self._landing_html,
            )
        raise AssertionError(f"unmatched POST {url}")


_SIGNIN_LANDING = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/authenticate"
    "?relayState=rs1"
)


async def _run_login(landing_html: str, *, status: int = 200) -> BaseException:
    """Drive login() to its failure landing and return the raised exception."""
    session = _LoginSession(
        landing_url=_SIGNIN_LANDING,
        landing_status=status,
        landing_html=landing_html,
    )
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError) as ei:
        await conn.login("user@example.com", "secret")
    return ei.value


# ── direct classifier unit tests ────────────────────────────────────────────

def test_classify_bad_cred_returns_none() -> None:
    exc, ctx = classify_portal_login_failure(_SIGNIN_LANDING, _BAD_CRED_HTML)
    assert exc is None
    assert ctx["classified"] == "invalid_credentials"
    # secret-free: no email/password/relayState/code keys.
    assert "relayState" not in ctx and "code" not in ctx


def test_classify_tc() -> None:
    exc, ctx = classify_portal_login_failure(_SIGNIN_LANDING, _TC_HTML)
    assert isinstance(exc, TermsAndConditionsError)
    assert ctx["classified"] == "terms_and_conditions"


def test_classify_consent() -> None:
    exc, _ = classify_portal_login_failure(_SIGNIN_LANDING, _CONSENT_HTML)
    assert isinstance(exc, MarketingConsentError)


def test_classify_2fa() -> None:
    exc, _ = classify_portal_login_failure(_SIGNIN_LANDING, _2FA_HTML)
    assert isinstance(exc, TwoFactorRequiredError)
    assert not isinstance(exc, EmailTwoFactorRequiredError)


def test_classify_email_2fa_is_subclass() -> None:
    exc, _ = classify_portal_login_failure(_SIGNIN_LANDING, _EMAIL_2FA_HTML)
    assert isinstance(exc, EmailTwoFactorRequiredError)


def test_classify_onboarding() -> None:
    exc, _ = classify_portal_login_failure(_SIGNIN_LANDING, _ONBOARDING_HTML)
    assert isinstance(exc, PortalInteractionRequiredError)


def test_classify_unknown_errorcode_is_non_credential() -> None:
    exc, _ = classify_portal_login_failure(_SIGNIN_LANDING, _UNKNOWN_ERR_HTML)
    assert isinstance(exc, PortalInteractionRequiredError)
    assert not isinstance(
        exc, (TermsAndConditionsError, TwoFactorRequiredError)
    )


def test_classify_logctx_has_no_secrets() -> None:
    """log_ctx must carry ONLY page-type/error/errorCode keys."""
    _, ctx = classify_portal_login_failure(_SIGNIN_LANDING, _TC_HTML)
    forbidden = {"email", "password", "relayState", "code", "token", "url"}
    assert forbidden.isdisjoint(ctx.keys())


# ── end-to-end login() outcome (mocked HTTP) ────────────────────────────────

@pytest.mark.asyncio
async def test_login_bad_cred_raises_plain_auth_error() -> None:
    exc = await _run_login(_BAD_CRED_HTML)
    # plain credential failure on a signin-service re-render: the credential
    # catch-all (AuthenticationError), NOT any typed interstitial subclass
    # and NOT the non-credential PortalInteractionRequiredError.
    assert type(exc) is AuthenticationError
    assert "check email and password" in str(exc)


@pytest.mark.asyncio
async def test_login_tc_raises_typed() -> None:
    exc = await _run_login(_TC_HTML)
    assert isinstance(exc, TermsAndConditionsError)


@pytest.mark.asyncio
async def test_login_2fa_raises_typed() -> None:
    exc = await _run_login(_2FA_HTML)
    assert isinstance(exc, TwoFactorRequiredError)


@pytest.mark.asyncio
async def test_login_onboarding_raises_portal_interaction() -> None:
    exc = await _run_login(_ONBOARDING_HTML)
    assert isinstance(exc, PortalInteractionRequiredError)


@pytest.mark.asyncio
async def test_login_http_400_with_consent_errorcode() -> None:
    """A 4xx landing with a consent errorCode is still classified typed."""
    exc = await _run_login(_CONSENT_HTML, status=400)
    assert isinstance(exc, MarketingConsentError)


# ── caller mapping (config_flow._oportal_test_login) ────────────────────────

class _OptionsFlowProbe:
    """Minimal stand-in exposing _oportal_test_login with a stubbed login()."""

    def __init__(self, exc: BaseException | None) -> None:
        self._config_entry = type(
            "E", (), {"data": {"brand": "volkswagen"}}
        )()
        self._exc = exc

    # bind the real method below


def _make_probe(exc: BaseException | None) -> Any:
    from custom_components.vag_connect import config_flow as cf

    probe = _OptionsFlowProbe(exc)
    probe._oportal_test_login = cf.VagConnectOptionsFlow._oportal_test_login.__get__(  # type: ignore[attr-defined]
        probe
    )
    return probe


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (AuthenticationError("bad pw"), "invalid_credentials"),
        (TermsAndConditionsError(), "terms_and_conditions"),
        (MarketingConsentError(), "marketing_consent"),
        (TwoFactorRequiredError(), "two_factor_required"),
        (EmailTwoFactorRequiredError(), "two_factor_required"),
        (PortalInteractionRequiredError("onboarding"), "portal_interaction_required"),
    ],
)
async def test_caller_maps_typed_exception(
    monkeypatch: pytest.MonkeyPatch,
    exc: BaseException,
    expected_code: str,
) -> None:
    """config_flow._oportal_test_login maps each typed exception to its
    distinct code (and only genuine bad creds → invalid_credentials)."""
    import custom_components.vag_connect.cariad.auth._eu_data_act as eda

    async def _fake_login(self: Any, email: str, password: str) -> None:
        raise exc

    monkeypatch.setattr(eda.EUDataActConnector, "login", _fake_login)

    probe = _make_probe(exc)
    with pytest.raises(ValueError) as ei:
        await probe._oportal_test_login("user@example.com", "secret")
    assert str(ei.value) == expected_code


def test_map_error_passes_portal_interaction_required() -> None:
    """_map_error keeps portal_interaction_required (non-credential) instead
    of collapsing it to cannot_connect."""
    from custom_components.vag_connect.config_flow import _map_error

    assert _map_error("portal_interaction_required") == "portal_interaction_required"
    assert _map_error("invalid_credentials") == "invalid_credentials"
