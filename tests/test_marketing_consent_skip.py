# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""EU Data Act portal — auto-skip the OPTIONAL marketing-consent interstitial.

VW randomly injects a marketing-consent page after an otherwise valid login. Its
URL carries an OIDC ``callback=`` that, when followed, completes the login WITHOUT
granting marketing scopes (the "not now" path). Ported from
``idk._skip_marketing_consent`` (evcc PR #29980) to the portal channel.

Contract:
  (a) marketing-consent landing WITH a callback → auto-skipped, login completes;
  (b) marketing-consent landing WITHOUT a callback → still MarketingConsentError
      (safe fallback, no regression);
  (c) a legal terms-and-conditions landing is NEVER skipped — it has no "not now"
      path and auto-accepting it would assert legal consent on the user's behalf.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
from custom_components.vag_connect.cariad.exceptions import (
    MarketingConsentError,
    TermsAndConditionsError,
)

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
_MARKETING_HTML = (
    '<script>window._IDK = {templateModel: {"template":"marketing-consent"}};</script>'
)
_TC_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"template":"terms-and-conditions",'
    '"error":{"errorCode":"terms.not.accepted"}}};</script>'
)
_PORTAL_OK_LANDING = "https://eu-data-act.drivesomethinggreater.com/dashboard"

# A marketing-consent landing whose URL carries the OIDC callback (the skippable
# case) vs one without it (the fallback case).
_MARKETING_WITH_CB = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/consent/marketing"
    "?callback=https://identity.vwgroup.io/oidc/v1/callback/success"
)
_MARKETING_NO_CB = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/consent/marketing"
)
_TC_LANDING = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/terms-and-conditions"
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


class _Session:
    """prime → authorize → identifier → credential POST → (marketing) → callback."""

    def __init__(
        self,
        *,
        cred_landing: tuple[str, int, str],
        callback_landing: tuple[str, int, str] | None = None,
    ) -> None:
        self._cred = cred_landing
        self._cb = callback_landing

    def get(self, url: str, **kw: Any) -> _FakeResp:
        if url.endswith("/") and "drivesomethinggreater" in url:
            return _FakeResp(url, text="<html>portal</html>")
        if "authorize" in url:
            return _FakeResp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "identifier",
                text=_SIGNIN_HTML,
            )
        if "/callback/" in url:  # the marketing-skip callback follow
            assert self._cb is not None, "unexpected callback GET"
            u, s, h = self._cb
            return _FakeResp(u, status=s, text=h)
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
        raise AssertionError(f"unmatched POST {url}")


@pytest.mark.asyncio
async def test_marketing_consent_with_callback_is_skipped_login_completes() -> None:
    session = _Session(
        cred_landing=(_MARKETING_WITH_CB, 200, _MARKETING_HTML),
        callback_landing=(_PORTAL_OK_LANDING, 200, "<html>logged in</html>"),
    )
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")  # must NOT raise
    assert conn.logged_in is True


@pytest.mark.asyncio
async def test_marketing_consent_without_callback_still_errors() -> None:
    session = _Session(cred_landing=(_MARKETING_NO_CB, 200, _MARKETING_HTML))
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    with pytest.raises(MarketingConsentError):
        await conn.login("user@example.com", "secret")


@pytest.mark.asyncio
async def test_terms_and_conditions_never_skipped() -> None:
    # Legal T&C has no "not now" path — it must still raise, never auto-continue.
    session = _Session(cred_landing=(_TC_LANDING, 200, _TC_HTML))
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    with pytest.raises(TermsAndConditionsError):
        await conn.login("user@example.com", "secret")
