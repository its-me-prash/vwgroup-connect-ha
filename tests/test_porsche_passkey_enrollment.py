# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche login must decline the Auth0 passkey-enrollment screen, not treat it
as an unhandled captcha/consent wall.

LIVE-VERIFIED (#1337, 2026-09-07): a full password-flow run on a real Porsche
account returned a genuine access_token with no captcha and no attestation
error, so the flow is not structurally blocked. What IS live-confirmed is that
the rendered-200-instead-of-redirect step this module already detects is, at
least sometimes, the ACUL passkey-enrollment nudge (``/u/passkey-enrollment``)
rather than a captcha — declining it yields a real authorization code. These
tests exercise that decline against mocked hops; a genuine captcha (any other
rendered page) must still fall through to the existing honest "no code" result.
"""
from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.auth.porsche import PorscheAuth
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    PorscheLoginWallError,
)

_CB = "my-porsche-app://auth0/callback"
_PW_URL = "https://identity.porsche.com/u/login/password?state=xyz"
_ENROLL_URL = "https://identity.porsche.com/u/passkey-enrollment?state=xyz"


def _passkey_html(state: str = "enroll-state-1") -> str:
    """A minimal page shaped like Auth0's ACUL passkey-enrollment screen."""
    payload = base64.b64encode(
        json.dumps({"transaction": {"state": state}}).encode()
    ).decode()
    return f'<script>var ctx = JSON.parse(atob("{payload}"));</script>'


class _Resp:
    def __init__(self, status: int, location: str = "", text: str = "") -> None:
        self.status = status
        self.headers = {"Location": location} if location else {}
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def text(self) -> str:
        return self._text


def _session(get_responses: list[_Resp], post_responses: list[_Resp] | None = None) -> MagicMock:
    get_iter = iter(get_responses)
    post_iter = iter(post_responses or [])
    session = MagicMock()
    session.get = MagicMock(side_effect=lambda *a, **kw: next(get_iter))
    session.post = MagicMock(side_effect=lambda *a, **kw: next(post_iter))
    return session


def _follow(session, first_location: str) -> str | None:
    auth = PorscheAuth(session)
    return asyncio.run(auth._follow_to_code(first_location, _PW_URL))


class TestPasskeyEnrollmentSkip:
    def test_declines_passkey_enrollment_and_gets_code(self) -> None:
        session = _session(
            get_responses=[_Resp(200, text=_passkey_html())],
            post_responses=[_Resp(302, f"{_CB}?code=AFTER_PASSKEY_DECLINE&state=x")],
        )
        code = _follow(session, "/u/passkey-enrollment?state=xyz")
        assert code == "AFTER_PASSKEY_DECLINE"

    def test_declines_passkey_enrollment_then_one_more_hop(self) -> None:
        """The decline can itself land on another resume hop before the code."""
        session = _session(
            get_responses=[
                _Resp(200, text=_passkey_html()),
                _Resp(302, f"{_CB}?code=AFTER_EXTRA_HOP&state=x"),
            ],
            post_responses=[_Resp(302, "/authorize/resume2?state=xyz")],
        )
        code = _follow(session, "/u/passkey-enrollment?state=xyz")
        assert code == "AFTER_EXTRA_HOP"

    def test_malformed_passkey_context_yields_no_code(self) -> None:
        """No parseable atob(...) blob — treated as the unhandled-wall case,
        not a crash."""
        session = _session(get_responses=[_Resp(200, text="<html>nothing here</html>")])
        assert _follow(session, "/u/passkey-enrollment?state=xyz") is None

    def test_decline_post_not_redirected_yields_no_code(self) -> None:
        """Auth0 rejects the decline itself (e.g. stale state) — still a clean
        None, never an exception."""
        session = _session(
            get_responses=[_Resp(200, text=_passkey_html())],
            post_responses=[_Resp(200, text="<html>still here</html>")],
        )
        assert _follow(session, "/u/passkey-enrollment?state=xyz") is None

    def test_genuine_captcha_page_is_unaffected(self) -> None:
        """A rendered 200 that is NOT the passkey-enrollment path (e.g. a real
        captcha) must still fall through to the existing honest "no code"
        result — this is the wall that stays genuinely unsolvable headless."""
        session = _session(get_responses=[_Resp(200, text="<html>captcha here</html>")])
        code = _follow(session, "/authorize/resume?state=xyz")
        assert code is None
        session.post.assert_not_called()

    def test_decline_merges_submitted_form_data(self) -> None:
        """b19 (CJNE-comparison #8) — CJNE seeds the decline POST body with
        whatever untrustedData.submittedFormData the ACUL context carried,
        before overwriting state/action/acul-sdk on top. Verify the merge,
        not just that SOME POST happens."""
        payload = base64.b64encode(json.dumps({
            "transaction": {"state": "enroll-state-1"},
            "untrustedData": {"submittedFormData": {"js-available": "true"}},
        }).encode()).decode()
        html = f'<script>var ctx = JSON.parse(atob("{payload}"));</script>'

        captured: dict = {}
        session = MagicMock()
        session.get = MagicMock(
            side_effect=[_Resp(200, text=html), _Resp(302, f"{_CB}?code=OK&state=x")]
        )

        def _post(url, **kwargs):
            captured.update(kwargs.get("data", {}))
            return _Resp(302, "/authorize/resume2?state=xyz")

        session.post = MagicMock(side_effect=_post)
        code = _follow(session, "/u/passkey-enrollment?state=xyz")
        assert code == "OK"
        assert captured.get("js-available") == "true"
        assert captured.get("state") == "enroll-state-1"
        assert captured.get("action") == "abort-passkey-enrollment"


def _acul_html(screen_name: str, state: str = "s1", captcha: bool = False) -> str:
    """A page shaped like an Auth0 ACUL screen with a named ``screen``."""
    ctx: dict = {"transaction": {"state": state}, "screen": {"name": screen_name}}
    if captcha:
        ctx["screen"]["captcha"] = {"image": "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="}
    payload = base64.b64encode(json.dumps(ctx).encode()).decode()
    return f'<script>var ctx = JSON.parse(atob("{payload}"));</script>'


class TestAculScreenGeneralisation:
    """b23 (#1337 follow-up) — the 200-branch now identifies the ACUL screen by
    its context ``screen.name`` (not just the URL path), declines the confirmed
    passkey-enrollment screen even when the resume URL is generic, and names any
    other screen it can't clear instead of guessing a decline for it."""

    def test_passkey_matched_by_screen_name_on_generic_resume_path(self) -> None:
        # No ``/u/passkey-enrollment`` in the path — identity comes from the
        # ACUL context. The confirmed decline must still fire.
        session = _session(
            get_responses=[_Resp(200, text=_acul_html("passkey-enrollment"))],
            post_responses=[_Resp(302, f"{_CB}?code=BY_NAME&state=x")],
        )
        assert _follow(session, "/authorize/resume?state=xyz") == "BY_NAME"

    def test_unknown_acul_screen_is_not_declined(self) -> None:
        # A screen we have no grounded decline action for must dead-end WITHOUT
        # inventing a POST against the confirmed login path.
        session = _session(get_responses=[_Resp(200, text=_acul_html("mfa-enroll"))])
        assert _follow(session, "/u/mfa-enroll?state=xyz") is None
        session.post.assert_not_called()

    def test_captcha_in_redirect_chain_dead_ends_without_post(self) -> None:
        # A captcha rendered mid-chain can't be solved here (the config-flow
        # captcha step only resumes the identifier POST) — stop cleanly, no POST.
        session = _session(
            get_responses=[_Resp(200, text=_acul_html("login-id", captcha=True))],
        )
        assert _follow(session, "/authorize/resume?state=xyz") is None
        session.post.assert_not_called()


class TestAculScreenName:
    def test_prefers_context_screen_name(self) -> None:
        name = PorscheAuth._acul_screen_name(
            "https://identity.porsche.com/authorize/resume?state=x",
            _acul_html("passkey-enrollment"),
        )
        assert name == "passkey-enrollment"

    def test_falls_back_to_path_segment(self) -> None:
        name = PorscheAuth._acul_screen_name(
            "https://identity.porsche.com/u/passkey-enrollment?state=x",
            "<html>no context blob</html>",
        )
        assert name == "passkey-enrollment"

    def test_none_when_neither_available(self) -> None:
        name = PorscheAuth._acul_screen_name(
            "https://identity.porsche.com/authorize/resume?state=x",
            "<html>nothing</html>",
        )
        assert name is None


class TestPageMarker:
    """b23 (#1337) — the real v4.7.2 wall is a rendered 200 at my.porsche.com,
    not an Auth0 ACUL screen. A secret-free page marker (title + keyword flags)
    is logged so the next capture reveals what that page actually is."""

    def test_extracts_title_and_keyword_markers(self) -> None:
        html = (
            "<html><head><title>  Porsche ID – Verify  </title></head>"
            "<body>please solve the captcha to continue</body></html>"
        )
        marker = PorscheAuth._page_marker(html)
        assert "Porsche ID" in marker
        assert "captcha" in marker
        assert "verify" in marker

    def test_no_title_or_markers(self) -> None:
        assert PorscheAuth._page_marker("<html><body>ok</body></html>") == "no title/markers"

    def test_empty_html_does_not_crash(self) -> None:
        assert PorscheAuth._page_marker("") == "no title/markers"

    def test_title_is_length_capped(self) -> None:
        long_title = "x" * 500
        marker = PorscheAuth._page_marker(f"<title>{long_title}</title>")
        # title value is capped at 80 chars (plus the "title=" wrapper/quotes)
        assert len(marker) < 120


def test_login_wall_error_is_authentication_error_subclass() -> None:
    """Ordering guard: config_flow catches PorscheLoginWallError BEFORE the
    generic AuthenticationError, so it must be a subclass (else the specific
    catch is dead code and the generic one wins → back to 'wrong password')."""
    assert issubclass(PorscheLoginWallError, AuthenticationError)
