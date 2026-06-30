# Copyright 2026 Prash Balan (@its-me-prash) - GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.7 (#527) — EU Data Act portal consent-grant POST shape.

RaimondB root-caused and verified end-to-end that the v2.15.5 auto-accept,
though it fired on the right page, POSTed the WRONG request and the grant
endpoint rejected it. Two defects:

  Defect 1 (FATAL): the consent <form> action is EMPTY → a browser POSTs back
    to the CURRENT consent URL **including its query string** (hmac /
    relayState / callback / scopes), which the grant endpoint validates. The
    old code routed through ``_resolve_action`` which ``split('?', 1)[0]`` and
    discarded the query → HTTP 400 generalErrorBranded.

  Defect 2: the form emits ``consentedScopes`` ONCE PER granted scope
    (profile, cars). The dict-based ``_login_fields`` kept only the last and
    dropped the mandatory ``profile``; it also injected a templateModel hmac
    BODY field the consent form never has.

This suite asserts the FIXED POST shape against a realistic consent fixture
(empty action, two consentedScopes, a _csrf, an Allow button with NO name, a
Cancel button name='cancel'):

  (a) the POST URL is the FULL consent_url WITH its query string intact;
  (b) the body preserves BOTH consentedScopes values (profile AND cars);
  (c) no button params (no 'cancel') leak into the body;
  (d) no spurious templateModel hmac is injected into the body.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    _consent_form_fields,
)

# ── realistic consent fixture (RaimondB's described page) ───────────────────
# EMPTY <form action> → POST to the current URL with query intact.
_REAL_CONSENT_HTML = (
    '<script>window._IDK = {templateModel: {"template":"consent",'
    '"hmac":"QUERY_HMAC_NOT_A_BODY_FIELD","relayState":"rs1"}, '
    'csrf_token: "csrf_js"};</script>'
    '<form action="">'
    '<input type="hidden" name="_csrf" value="csrf_form">'
    '<input type="hidden" name="consentedScopes" value="profile">'
    '<input type="hidden" name="consentedScopes" value="cars">'
    '<button type="submit">Allow</button>'
    '<button type="submit" name="cancel" value="true">Cancel</button>'
    '</form>'
)

# The full consent URL the credential POST landed on — query MUST survive.
_CONSENT_URL = (
    "https://identity.vwgroup.io/signin-service/v1/consent/users/UID/CLIENT"
    "?hmac=QUERY_HMAC_NOT_A_BODY_FIELD&relayState=rs1"
    "&callback=https%3A%2F%2Fcb&scopes=profile%20cars"
)
_PORTAL_OK_LANDING = "https://eu-data-act.drivesomethinggreater.com/dashboard"


# ── pure-parser unit tests ──────────────────────────────────────────────────

def test_consent_form_fields_preserves_repeated_scopes() -> None:
    pairs, action = _consent_form_fields(_REAL_CONSENT_HTML)
    assert action == ""  # empty form action
    # consentedScopes appears TWICE, both values preserved in order.
    scopes = [v for n, v in pairs if n == "consentedScopes"]
    assert scopes == ["profile", "cars"]
    # _csrf is captured.
    assert ("_csrf", "csrf_form") in pairs


def test_consent_form_fields_excludes_buttons() -> None:
    pairs, _ = _consent_form_fields(_REAL_CONSENT_HTML)
    names = {n for n, _ in pairs}
    # The Allow button has no name (nothing to add); Cancel must NOT appear.
    assert "cancel" not in names
    # No spurious hmac body field (hmac is the query param, not an input).
    assert "hmac" not in names


# ── end-to-end accept POST shape (captures the real request) ────────────────

class _CaptureResp:
    def __init__(self, url: str, *, status: int = 200, text: str = "") -> None:
        self.url = url
        self.status = status
        self._text = text

    async def __aenter__(self) -> "_CaptureResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text


class _CaptureSession:
    """Records the URL + data of the consent accept POST."""

    def __init__(self) -> None:
        self.post_url: str | None = None
        self.post_data: Any = None

    def post(self, url: str, **kw: Any) -> _CaptureResp:
        self.post_url = url
        self.post_data = kw.get("data")
        return _CaptureResp(_PORTAL_OK_LANDING, status=200, text="<html>ok</html>")


@pytest.mark.asyncio
async def test_accept_consent_posts_full_url_and_both_scopes() -> None:
    session = _CaptureSession()
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    result = await conn._accept_consent_page(_CONSENT_URL, _REAL_CONSENT_HTML)

    assert result is not None
    landing, _html, status = result
    assert landing == _PORTAL_OK_LANDING
    assert status == 200

    # (a) POST URL is the FULL consent_url WITH its query string intact.
    assert session.post_url == _CONSENT_URL
    assert "hmac=QUERY_HMAC_NOT_A_BODY_FIELD" in str(session.post_url)
    assert "relayState=rs1" in str(session.post_url)

    # The body is a LIST of (name, value) tuples (aiohttp preserves repeats).
    body = session.post_data
    assert isinstance(body, list)

    # (b) BOTH consentedScopes values are present.
    scopes = [v for n, v in body if n == "consentedScopes"]
    assert scopes == ["profile", "cars"]

    body_names = {n for n, _ in body}
    # (c) no button params leaked into the body.
    assert "cancel" not in body_names
    # (d) no spurious templateModel hmac injected into the body.
    assert "hmac" not in body_names
    # _csrf carried through.
    assert ("_csrf", "csrf_form") in body
