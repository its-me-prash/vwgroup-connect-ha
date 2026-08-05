# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche login must follow the Auth0 resume hop to the authorization code.

In Auth0's Identifier-First flow the password POST does not redirect straight
to the app callback. Its Location is a resume path (``/authorize/resume?...``),
and the code only appears after following that hop, sometimes two. The old code
required the callback immediately and so always fell through to "wrong
credentials or captcha", even with correct credentials — a self-inflicted
failure that had nothing to do with the Porsche One migration.

NOT LIVE-VERIFIED: there is no Porsche account here, so these exercise the
redirect-walking logic against mocked hops. The shape of the flow is grounded
in a maintained third-party client; a Porsche owner still has to confirm the
end to end login (#13, #666) before this ships.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.auth.porsche import PorscheAuth

_CB = "my-porsche-app://auth0/callback"
_PW_URL = "https://identity.porsche.com/u/login/password?state=xyz"


def _session_returning(locations: list[tuple[int, str]]) -> MagicMock:
    """A session whose successive GETs return the given (status, Location) hops."""
    calls = iter(locations)

    def _get(url, **kwargs):
        status, loc = next(calls)
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.status = status
        resp.headers = {"Location": loc}
        return resp

    session = MagicMock()
    session.get = MagicMock(side_effect=_get)
    return session


def _follow(session, first_location: str) -> str | None:
    auth = PorscheAuth(session)
    return asyncio.run(auth._follow_to_code(first_location, _PW_URL))


class TestResumeHop:
    def test_direct_callback_still_works(self) -> None:
        """The old happy path: password POST redirects straight to the callback."""
        # No GET needed; the first location already carries the code.
        code = _follow(MagicMock(), f"{_CB}?code=DIRECT123&state=x")
        assert code == "DIRECT123"

    def test_single_resume_hop(self) -> None:
        session = _session_returning([(302, f"{_CB}?code=AFTER_RESUME&state=x")])
        code = _follow(session, "/authorize/resume?state=xyz")
        assert code == "AFTER_RESUME"

    def test_two_hops(self) -> None:
        session = _session_returning([
            (302, "/authorize/resume2?state=xyz"),
            (302, f"{_CB}?code=AFTER_TWO&state=x"),
        ])
        code = _follow(session, "/authorize/resume?state=xyz")
        assert code == "AFTER_TWO"

    def test_absolute_location_is_resolved(self) -> None:
        """Auth0 sometimes bounces to an absolute URL; it must be followed, not
        string-formatted onto the base."""
        session = _session_returning([
            (302, "https://my.porsche.com/?iss=https%3A%2F%2Fidentity.porsche.com"),
            (302, f"{_CB}?code=ABS_OK&state=x"),
        ])
        code = _follow(session, "/authorize/resume?state=xyz")
        assert code == "ABS_OK"

    def test_captcha_page_yields_no_code(self) -> None:
        """A 200 (a rendered captcha/consent page, not a redirect) means there is
        no code; the caller turns this into the honest captcha error."""
        session = _session_returning([(200, "")])
        assert _follow(session, "/authorize/resume?state=xyz") is None

    def test_redirect_loop_is_bounded(self) -> None:
        """A cycle must terminate rather than hang the login."""
        session = _session_returning([(302, "/authorize/resume?state=xyz")] * 50)
        assert _follow(session, "/authorize/resume?state=xyz") is None

    def test_callback_without_code_is_not_a_code(self) -> None:
        code = _follow(MagicMock(), f"{_CB}?error=access_denied")
        assert code is None
