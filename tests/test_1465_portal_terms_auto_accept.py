# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""EU Data Act portal — auto-accept the legal terms-and-conditions interstitial.

Adopted from TommiG1/HA_VAG-EU-Data-Act (verified byte-exact): consent and T&C are
the SAME Auth0 signin-service form-POST (hidden ``_csrf`` / ``relayState`` /
``hmac``); they differ only in the landing marker. We already auto-accept the OAuth
consent grant (#527); this mirrors that for the T&C wall — the user has already
authenticated and asked the integration to read their OWN car's data (Art. 4), so
accepting an updated-terms interstitial completes exactly the flow they requested.

Bounded to ONE attempt: if the T&C form cannot be parsed (or the accept re-lands on
a T&C page), login falls through to the typed ``TermsAndConditionsError`` Repair —
no silent loop. The wrong-CLIENT T&C artefact (#1340) is already gone at the source
via the per-brand portal client_ids, so this only clears a genuine account-level
T&C update.

HTTP is mocked exactly like test_v2155_portal_consent_accept.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
from custom_components.vag_connect.cariad.exceptions import TermsAndConditionsError

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
# A scrapeable T&C page: hidden _csrf/relayState/hmac + an explicit accept action.
_TERMS_FORM_HTML = (
    '<script>window._IDK = {templateModel: {"template":"termsAndConditions",'
    '"hmac":"terms_hmac","relayState":"rs1"}, csrf_token: "csrf_t"};</script>'
    '<form action="/signin-service/v1/CLIENT/terms-and-conditions">'
    '<input type="hidden" name="_csrf" value="csrf_t">'
    '<input type="hidden" name="relayState" value="rs1">'
    '<input type="hidden" name="hmac" value="terms_hmac">'
    '<button type="submit">Accept</button>'
    '</form>'
)
# A T&C page with NO usable form fields → auto-accept must bail → typed Repair.
_TERMS_NOFORM_HTML = (
    '<script>window._IDK = {templateModel: {"template":"termsAndConditions"}};</script>'
)

_TERMS_LANDING = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/terms-and-conditions"
)
_PORTAL_OK_LANDING = "https://eu-data-act.drivesomethinggreater.com/dashboard"
_PORTAL_OK_HTML = "<html>logged in</html>"


class _FakeResp:
    def __init__(self, url: str, *, status: int = 200, text: str = "") -> None:
        self.url = url
        self.status = status
        # A real aiohttp response always has headers; the login reads
        # "Location" off them now that it follows redirects itself.
        self.headers: dict[str, str] = {}
        self._text = text

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text


class _TermsLoginSession:
    """prime → authorize → identifier → credential POST (→ T&C page) → T&C accept."""

    def __init__(
        self,
        *,
        cred_landing: tuple[str, int, str],
        accept_landing: tuple[str, int, str] | None = None,
    ) -> None:
        self._cred = cred_landing
        self._accept = accept_landing
        self.accept_posts = 0

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
        if "terms-and-conditions" in url:
            self.accept_posts += 1
            assert self._accept is not None, "unexpected T&C accept POST"
            u, s, h = self._accept
            return _FakeResp(u, status=s, text=h)
        raise AssertionError(f"unmatched POST {url}")


# ── (a) REAL adoption: auto-accept the T&C page → login completes ────────────

@pytest.mark.asyncio
async def test_terms_page_auto_accepted_login_completes() -> None:
    session = _TermsLoginSession(
        cred_landing=(_TERMS_LANDING, 200, _TERMS_FORM_HTML),
        accept_landing=(_PORTAL_OK_LANDING, 200, _PORTAL_OK_HTML),
    )
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")  # must NOT raise
    assert conn.logged_in is True
    assert session.accept_posts == 1  # accepted exactly once


# ── (b) FALLBACK: unparseable T&C form → typed Repair, no silent loop ────────

@pytest.mark.asyncio
async def test_terms_page_without_form_falls_through_to_repair() -> None:
    session = _TermsLoginSession(
        cred_landing=(_TERMS_LANDING, 200, _TERMS_NOFORM_HTML),
        accept_landing=None,  # accept must never be POSTed (no fields to send)
    )
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    with pytest.raises(TermsAndConditionsError):
        await conn.login("user@example.com", "secret")
    assert session.accept_posts == 0


# ── (c) FALLBACK: accept re-lands on a T&C page → typed Repair (no loop) ──────

@pytest.mark.asyncio
async def test_terms_accept_that_reloops_raises_repair() -> None:
    session = _TermsLoginSession(
        cred_landing=(_TERMS_LANDING, 200, _TERMS_FORM_HTML),
        # the accept POST lands on ANOTHER T&C page → we accept once, then classify
        accept_landing=(_TERMS_LANDING, 200, _TERMS_FORM_HTML),
    )
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    with pytest.raises(TermsAndConditionsError):
        await conn.login("user@example.com", "secret")
    assert session.accept_posts == 1  # exactly once, then fell through


# ── (d) unit: the T&C landing detector ───────────────────────────────────────

def test_is_terms_landing_detects_only_terms() -> None:
    conn = EUDataActConnector(object())  # type: ignore[arg-type]
    assert conn._is_terms_landing(_TERMS_LANDING, _TERMS_FORM_HTML) is True
    assert conn._is_terms_landing(_PORTAL_OK_LANDING, _PORTAL_OK_HTML) is False
    # a plain signin/authenticate landing is not a T&C wall
    assert conn._is_terms_landing(
        "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/authenticate",
        _PASSWORD_HTML,
    ) is False


# ── (e) #1417 — the accept POST shape (empty action → full URL + query) ───────
# The T&C interstitial is the SAME empty-action form as the consent grant. The
# accept must POST back to the FULL terms URL with the query (hmac/relayState/
# callback) intact — the old code routed through _resolve_action which stripped
# the query → HTTP 400 generalErrorBranded (mps222 in #1337). It must also send
# ORDERED (name, value) pairs (not a dict) and must NOT inject a templateModel
# hmac BODY field the signin-service form never carries.

# EMPTY <form action> + hidden _csrf/relayState; templateModel carries hmac as a
# QUERY-only value (never a body input) — mirrors the real consent fixture.
_TERMS_EMPTY_ACTION_HTML = (
    '<script>window._IDK = {templateModel: {"template":"termsAndConditions",'
    '"hmac":"QUERY_HMAC_NOT_A_BODY_FIELD","relayState":"rs1"}, '
    'csrf_token: "csrf_js"};</script>'
    '<form action="">'
    '<input type="hidden" name="_csrf" value="csrf_form">'
    '<input type="hidden" name="relayState" value="rs1">'
    '<button type="submit">Accept</button>'
    '<button type="submit" name="cancel" value="true">Cancel</button>'
    '</form>'
)
_TERMS_URL_WITH_QUERY = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/terms-and-conditions"
    "?hmac=QUERY_HMAC_NOT_A_BODY_FIELD&relayState=rs1&callback=https%3A%2F%2Fcb"
)


class _CaptureSession:
    """Records the URL + data of the T&C accept POST."""

    def __init__(self) -> None:
        self.post_url: str | None = None
        self.post_data: Any = None

    def post(self, url: str, **kw: Any) -> _FakeResp:
        self.post_url = url
        self.post_data = kw.get("data")
        return _FakeResp(_PORTAL_OK_LANDING, status=200, text=_PORTAL_OK_HTML)


@pytest.mark.asyncio
async def test_accept_terms_posts_full_url_with_query_and_ordered_pairs() -> None:
    session = _CaptureSession()
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    result = await conn._accept_terms_page(
        _TERMS_URL_WITH_QUERY, _TERMS_EMPTY_ACTION_HTML
    )

    assert result is not None
    landing, _html, status = result
    assert landing == _PORTAL_OK_LANDING
    assert status == 200

    # Empty action → POST to the FULL terms URL WITH its query string intact.
    assert session.post_url == _TERMS_URL_WITH_QUERY
    assert "hmac=QUERY_HMAC_NOT_A_BODY_FIELD" in str(session.post_url)
    assert "relayState=rs1" in str(session.post_url)

    # Body is a LIST of ordered (name, value) pairs (not a dict).
    body = session.post_data
    assert isinstance(body, list)
    body_names = {n for n, _ in body}
    # No templateModel hmac injected into the BODY (hmac is the query param).
    assert "hmac" not in body_names
    # Buttons excluded — no 'cancel' leaks into the body.
    assert "cancel" not in body_names
    # The form's own anti-CSRF / continuation fields carried through.
    assert ("_csrf", "csrf_form") in body
    assert ("relayState", "rs1") in body
