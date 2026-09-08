# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche auth hardening — b19 (#1337, CJNE-comparison, 2026-09-07).

Covers the auth-flow items from the CJNE-comparison pass that are NOT the
passkey-enrollment decline (already covered in test_porsche_passkey_enrollment.py):
X-Client-ID on every Auth0-flow request, an already-authenticated-session
short-circuit, distinguishing wrong-credentials from an unhandled wall,
captcha-image extraction, the full scope list, and treating both 401 and 403
as "refresh token invalid".
"""
from __future__ import annotations

import base64
import json as _json

import pytest

from custom_components.vag_connect.cariad.auth.porsche import (
    _SCOPE,
    _X_CLIENT,
    PorscheAuth,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    PorscheCaptchaRequiredError,
    TokenExpiredError,
)

_CB = "my-porsche-app://auth0/callback"


class _Resp:
    def __init__(self, status: int, headers: dict | None = None, text: str = "") -> None:
        self.status = status
        self.headers = headers or {}
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def text(self) -> str:
        return self._text

    async def json(self) -> dict:
        return _json.loads(self._text) if self._text else {}


class _Session:
    def __init__(self, get_responses=None, post_responses=None) -> None:
        self._get_q = list(get_responses or [])
        self._post_q = list(post_responses or [])
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self._get_q.pop(0)

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._post_q.pop(0)


def _atob_blob(payload: dict) -> str:
    return base64.b64encode(_json.dumps(payload).encode()).decode()


class TestXClientIdHeader:
    @pytest.mark.asyncio
    async def test_authorize_get_carries_x_client_id(self):
        session = _Session(
            get_responses=[_Resp(302, {"Location": "/u/login/identifier?state=ABC"})],
            post_responses=[_Resp(401)],  # identifier rejected — stop early
        )
        auth = PorscheAuth(session)
        with pytest.raises(AuthenticationError):
            await auth.authenticate("a@b.com", "pw")
        _, kwargs = session.get_calls[0]
        assert kwargs["headers"]["X-Client-ID"] == _X_CLIENT


class TestExistingSessionShortCircuit:
    @pytest.mark.asyncio
    async def test_authorize_already_has_code_skips_login_form(self, monkeypatch):
        session = _Session(
            get_responses=[_Resp(302, {"Location": f"{_CB}?code=EXISTING&state=x"})],
        )
        auth = PorscheAuth(session)
        exchanged = {}

        async def _fake_exchange(code, verifier):
            exchanged["code"] = code
            return "TOKEN_SET"

        monkeypatch.setattr(auth, "_exchange_code", _fake_exchange)
        result = await auth.authenticate("a@b.com", "pw")
        assert result == "TOKEN_SET"
        assert exchanged["code"] == "EXISTING"
        assert session.post_calls == []  # never touched identifier/password


class TestWrongCredentialsDistinction:
    @pytest.mark.asyncio
    async def test_identifier_401_is_wrong_credentials(self):
        session = _Session(
            get_responses=[_Resp(302, {"Location": "/u/login/identifier?state=ABC"})],
            post_responses=[_Resp(401)],
        )
        auth = PorscheAuth(session)
        with pytest.raises(AuthenticationError, match="wrong credentials"):
            await auth.authenticate("a@b.com", "pw")
        assert len(session.post_calls) == 1  # never reached the password step

    @pytest.mark.asyncio
    async def test_password_400_is_wrong_credentials(self):
        session = _Session(
            get_responses=[_Resp(302, {"Location": "/u/login/identifier?state=ABC"})],
            post_responses=[_Resp(302), _Resp(400)],
        )
        auth = PorscheAuth(session)
        with pytest.raises(AuthenticationError, match="wrong credentials"):
            await auth.authenticate("a@b.com", "pw")
        assert len(session.post_calls) == 2


class TestCaptchaExtraction:
    @pytest.mark.asyncio
    async def test_identifier_400_with_captcha_raises_typed_error(self):
        html = (
            '<script>var c = JSON.parse(atob("'
            + _atob_blob({"screen": {"captcha": {"image": "data:image/svg+xml;base64,ABC"}}})
            + '"));</script>'
        )
        session = _Session(
            get_responses=[_Resp(302, {"Location": "/u/login/identifier?state=ABC"})],
            post_responses=[_Resp(400, text=html)],
        )
        auth = PorscheAuth(session)
        with pytest.raises(PorscheCaptchaRequiredError) as excinfo:
            await auth.authenticate("a@b.com", "pw")
        assert excinfo.value.captcha_image == "data:image/svg+xml;base64,ABC"
        assert excinfo.value.state == "ABC"

    @pytest.mark.asyncio
    async def test_identifier_400_without_captcha_falls_through(self):
        """A 400 with no parseable captcha context shouldn't crash — it just
        falls through to the password step like before."""
        session = _Session(
            get_responses=[_Resp(302, {"Location": "/u/login/identifier?state=ABC"})],
            post_responses=[_Resp(400, text="<html>nothing here</html>"), _Resp(401)],
        )
        auth = PorscheAuth(session)
        with pytest.raises(AuthenticationError, match="wrong credentials"):
            await auth.authenticate("a@b.com", "pw")


class TestScopeList:
    def test_full_profile_scope_set_present(self):
        for scope in (
            "pid:user_profile.name:read",
            "pid:user_profile.dealers:read",
            "pid:user_profile.emails:read",
            "pid:user_profile.phones:read",
            "pid:user_profile.addresses:read",
            "pid:user_profile.birthdate:read",
            "pid:user_profile.locale:read",
            "pid:user_profile.legal:read",
        ):
            assert scope in _SCOPE


class TestCaptchaResume:
    """b19 (#1337, CJNE-comparison #12) — resuming a login after the config
    flow got the user to solve a captcha. The state/verifier from the
    ORIGINAL /authorize call must be reused, so this must skip straight to
    the identifier POST (with the solved captcha attached) rather than
    starting a fresh transaction."""

    @pytest.mark.asyncio
    async def test_resume_skips_authorize_and_reuses_state(self):
        session = _Session(
            # No GET queued at all — a resume must never call /authorize.
            post_responses=[
                _Resp(302),  # identifier step (captcha accepted, moves on)
                _Resp(302, {"Location": f"{_CB}?code=RESUMED&state=x"}),  # password step
            ],
        )
        auth = PorscheAuth(session)
        code_seen = {}

        async def _fake_exchange(code, verifier):
            code_seen["code"] = code
            code_seen["verifier"] = verifier
            return "TOKEN_SET"

        auth._exchange_code = _fake_exchange  # type: ignore[method-assign]
        result = await auth.authenticate(
            "a@b.com", "pw",
            captcha_code="ABCD",
            resume_state="prior-state",
            resume_verifier="prior-verifier",
        )
        assert result == "TOKEN_SET"
        assert session.get_calls == []  # never touched /authorize
        assert len(session.post_calls) == 2  # identifier (+captcha), password
        _, kwargs = session.post_calls[0]
        assert kwargs["data"]["captcha"] == "ABCD"
        assert kwargs["data"]["state"] == "prior-state"
        assert code_seen["verifier"] == "prior-verifier"

    @pytest.mark.asyncio
    async def test_chained_captcha_raises_again_with_same_verifier(self):
        """A second captcha comes back — the caller must get the SAME
        resume_verifier forwarded so a third attempt would still work."""
        html = (
            '<script>var c = JSON.parse(atob("'
            + _atob_blob({"screen": {"captcha": {"image": "data:image/svg+xml;base64,DEF"}}})
            + '"));</script>'
        )
        session = _Session(post_responses=[_Resp(400, text=html)])
        auth = PorscheAuth(session)
        with pytest.raises(PorscheCaptchaRequiredError) as excinfo:
            await auth.authenticate(
                "a@b.com", "pw",
                captcha_code="WRONG",
                resume_state="prior-state",
                resume_verifier="prior-verifier",
            )
        assert excinfo.value.state == "prior-state"
        assert excinfo.value.code_verifier == "prior-verifier"
        assert excinfo.value.captcha_image == "data:image/svg+xml;base64,DEF"


class TestRefreshExpiredCodes:
    @pytest.mark.asyncio
    async def test_401_is_token_expired(self):
        session = _Session(post_responses=[_Resp(401)])
        auth = PorscheAuth(session)
        with pytest.raises(TokenExpiredError):
            await auth.refresh("stale-refresh-token")

    @pytest.mark.asyncio
    async def test_403_is_also_token_expired(self):
        """b19 (CJNE-comparison #6) — CJNE's production experience treats 403
        as the refresh-invalid signal; previously only 401 was handled here,
        so a 403 body without access_token would raise a bare KeyError."""
        session = _Session(post_responses=[_Resp(403)])
        auth = PorscheAuth(session)
        with pytest.raises(TokenExpiredError):
            await auth.refresh("stale-refresh-token")

    @pytest.mark.asyncio
    async def test_successful_refresh_sets_expires_at(self):
        import time
        session = _Session(post_responses=[_Resp(
            200, text=_json.dumps({
                "access_token": "AT", "refresh_token": "RT", "expires_in": 3600,
            }),
        )])
        auth = PorscheAuth(session)
        before = time.time()
        tokens = await auth.refresh("old-refresh-token")
        assert tokens.expires_at >= before + 3600 - 5
