# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1337 G5 — a captcha that appears AFTER the password step (in the Auth0
redirect chain) is now solvable, not a dead end.

CJNE never sees this case (their login completes), so there is no reference to
copy. The robust design replays the solved captcha back to the exact ACUL screen
that presented it (``_acul_captcha_resume`` builds the descriptor from the
screen's own ``transaction.state`` + ``submittedFormData``; ``_resume_acul_
captcha`` POSTs the answer there and continues to the code). NOT LIVE-VERIFIED —
no account here produces a post-password captcha; these exercise the machinery
against mocked hops, and the in-flow report link captures any real misfire.
"""
from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.auth.porsche import PorscheAuth
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    PorscheCaptchaRequiredError,
    PorscheLoginWallError,
)

_CB = "my-porsche-app://auth0/callback"
_IMG = "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="


def _acul_captcha_html(state: str = "s1", submitted: dict | None = None) -> str:
    ctx: dict = {
        "transaction": {"state": state},
        "screen": {"name": "login-id", "captcha": {"image": _IMG}},
    }
    if submitted is not None:
        ctx["untrustedData"] = {"submittedFormData": submitted}
    payload = base64.b64encode(json.dumps(ctx).encode()).decode()
    return f'<script>JSON.parse(atob("{payload}"))</script>'


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


def _session(post_responses=None, get_responses=None) -> MagicMock:
    pit = iter(post_responses or [])
    git = iter(get_responses or [])
    s = MagicMock()
    s.post = MagicMock(side_effect=lambda *a, **kw: next(pit))
    s.get = MagicMock(side_effect=lambda *a, **kw: next(git))
    return s


# ── _acul_captcha_resume: descriptor parsing ───────────────────────────────────
def test_resume_descriptor_carries_url_state_and_seeded_form() -> None:
    auth = PorscheAuth(MagicMock())
    r = auth._acul_captcha_resume(
        "https://identity.porsche.com/u/login/identifier?state=s1",
        _acul_captcha_html(state="s1", submitted={"username": "a@b.com"}),
    )
    assert r is not None
    assert r["url"].endswith("/u/login/identifier?state=s1")
    assert r["form"]["state"] == "s1"
    assert r["form"]["username"] == "a@b.com"  # submittedFormData seeded


def test_resume_descriptor_is_none_without_context_or_state() -> None:
    auth = PorscheAuth(MagicMock())
    assert auth._acul_captcha_resume("https://identity.porsche.com/x", "<html>no ctx</html>") is None
    payload = base64.b64encode(json.dumps({"screen": {"name": "login-id"}}).encode()).decode()
    assert auth._acul_captcha_resume("https://identity.porsche.com/x", f'<script>atob("{payload}")</script>') is None


# ── _resume_acul_captcha: replay + continue ────────────────────────────────────
def test_replay_posts_captcha_to_the_screen_and_exchanges() -> None:
    session = _session(post_responses=[_Resp(302, location=f"{_CB}?code=RESUMED&state=x")])
    auth = PorscheAuth(session)
    with patch.object(PorscheAuth, "_exchange_code", new=AsyncMock(return_value="TOKENSET")) as ex:
        out = asyncio.run(auth._resume_acul_captcha(
            "SOLVED", {"url": "https://identity.porsche.com/u/login/identifier?state=s1",
                       "form": {"state": "s1"}}, "ver"))
    assert out == "TOKENSET"
    _, kw = session.post.call_args
    assert kw["data"]["captcha"] == "SOLVED"   # the solved answer goes back
    assert kw["data"]["state"] == "s1"         # to THIS screen's state
    assert kw["data"]["action"] == "default"
    ex.assert_awaited_once_with("RESUMED", "ver")  # original verifier reused


def test_replay_chains_a_second_captcha() -> None:
    session = _session(post_responses=[_Resp(200, text=_acul_captcha_html(state="s2"))])
    auth = PorscheAuth(session)
    with pytest.raises(PorscheCaptchaRequiredError) as ei:
        asyncio.run(auth._resume_acul_captcha(
            "SOLVED", {"url": "https://identity.porsche.com/s?state=s1",
                       "form": {"state": "s1"}}, "ver"))
    assert ei.value.resume is not None
    assert ei.value.resume["form"]["state"] == "s2"  # fresh screen surfaced


def test_replay_200_without_captcha_is_honest_wall() -> None:
    session = _session(post_responses=[_Resp(200, text="<html>consent wall</html>")])
    auth = PorscheAuth(session)
    with pytest.raises(PorscheLoginWallError):
        asyncio.run(auth._resume_acul_captcha(
            "SOLVED", {"url": "https://identity.porsche.com/x", "form": {"state": "s1"}}, "ver"))


def test_replay_unexpected_status_raises_auth_error_not_wall() -> None:
    session = _session(post_responses=[_Resp(403, text="")])
    auth = PorscheAuth(session)
    with pytest.raises(AuthenticationError) as ei:
        asyncio.run(auth._resume_acul_captcha(
            "SOLVED", {"url": "https://identity.porsche.com/x", "form": {"state": "s1"}}, "ver"))
    assert not isinstance(ei.value, (PorscheLoginWallError, PorscheCaptchaRequiredError))


def test_replay_redirect_to_dead_end_is_wall() -> None:
    session = _session(
        post_responses=[_Resp(302, location="/authorize/resume?state=s1")],
        get_responses=[_Resp(200, text="")],  # a hop with no code and no captcha
    )
    auth = PorscheAuth(session)
    with pytest.raises(PorscheLoginWallError):
        asyncio.run(auth._resume_acul_captcha(
            "SOLVED", {"url": "https://identity.porsche.com/x", "form": {"state": "s1"}}, "ver"))


# ── host allowlist (privacy defense-in-depth) ──────────────────────────────────
def test_is_porsche_host_allowlist() -> None:
    ok = PorscheAuth._is_porsche_host
    assert ok("https://identity.porsche.com/u/login/identifier?state=s")
    assert ok("https://my.porsche.com/anything")
    assert not ok("http://identity.porsche.com/x")            # not https
    assert not ok("https://identity.porsche.com.evil.tld/x")  # look-alike suffix
    assert not ok("https://notporsche.com/x")                 # no dot boundary
    assert not ok("https://evil.example/x")
    assert not ok("")


def test_off_domain_captcha_is_not_replayable() -> None:
    auth = PorscheAuth(MagicMock())
    # a perfectly valid captcha context, but on a non-Porsche host → no descriptor
    assert auth._acul_captcha_resume(
        "https://evil.example/screen", _acul_captcha_html(state="s1")) is None


def test_replay_refuses_off_domain_url_without_posting() -> None:
    session = _session(post_responses=[_Resp(302, location="whatever")])
    auth = PorscheAuth(session)
    with pytest.raises(PorscheLoginWallError):
        asyncio.run(auth._resume_acul_captcha(
            "SOLVED", {"url": "https://evil.example/x", "form": {"state": "s1"}}, "ver"))
    session.post.assert_not_called()  # never POSTs the seeded form off-domain


# ── direct-body captcha at the password step (not only in the chain) ───────────
def test_direct_body_captcha_at_password_step_is_surfaced() -> None:
    session = _session(
        get_responses=[_Resp(302, location="https://identity.porsche.com/u/login/identifier?state=STATE1")],
        post_responses=[
            _Resp(200),  # identifier POST — no captcha at this step
            _Resp(200, text=_acul_captcha_html(state="pw-state")),  # password → captcha body, no redirect
        ],
    )
    auth = PorscheAuth(session)
    with pytest.raises(PorscheCaptchaRequiredError) as ei:
        asyncio.run(auth.authenticate("e@x.com", "pw"))
    assert ei.value.resume is not None
    assert ei.value.resume["form"]["state"] == "pw-state"


# ── identifier POST shape (CJNE parity, #1337) ────────────────────────────────
def test_identifier_post_declares_no_webauthn_matching_cjne() -> None:
    # Declaring WebAuthn support routed enrolled accounts into passkey-enrollment
    # and on to the unclearable my.porsche.com wall (#1337). Match CJNE: no
    # WebAuthn, so a captcha surfaces at the identifier step (solvable) instead.
    session = _session(
        get_responses=[_Resp(302, location="https://identity.porsche.com/u/login/identifier?state=S1")],
        post_responses=[_Resp(401)],  # identifier rejected → flow stops after the POST
    )
    auth = PorscheAuth(session)
    with pytest.raises(AuthenticationError):
        asyncio.run(auth.authenticate("e@x.com", "pw"))
    _, kw = session.post.call_args
    data = kw["data"]
    assert data["webauthn-available"] == "false"
    assert data["webauthn-platform-available"] == "false"
    assert "webauthn-platform-authenticator-available" not in data


# ── authenticate routing ───────────────────────────────────────────────────────
def test_authenticate_routes_captcha_resume_to_replay() -> None:
    auth = PorscheAuth(MagicMock())
    with patch.object(PorscheAuth, "_resume_acul_captcha", new=AsyncMock(return_value="TS")) as m:
        out = asyncio.run(auth.authenticate(
            "e", "p", captcha_code="C", resume_verifier="ver",
            captcha_resume={"url": "u", "form": {"state": "s"}}))
    assert out == "TS"
    args = m.call_args.args
    assert args[0] == "C"
    assert args[1] == {"url": "u", "form": {"state": "s"}}
    assert args[2] == "ver"
