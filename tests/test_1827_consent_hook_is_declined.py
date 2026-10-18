# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1827 — VW put an optional advertising opt-in in the way of the login.

On 2026-10-13/14 the sign-in chain started ending on a page VW serves from
``consent.vwgroup.io/hooks/<name>``: "Personalised advertising tailored to your
requirements". It is not the marketing-consent page the identity provider
already served — different host, different path — and it is optional. The page
offers a plain "Not now" link, and following that finishes the login on the
portal exactly as before.

Two people reported the failure within the same hours, and one attached a log
whose landing was ``consent.vwgroup.io/hooks/data-clean-room``. That string is
in no source file here, so our own code printed what it saw: ``refresh()`` ends
on a host that is not volkswagen.de and raises "refresh did not land on the
portal" (``_website_authproxy.py``, the final raise). An integration riding the
same authproxy channel reported and fixed the identical thing independently.

**We decline, and we never accept.** The opt-in is advertising consent, which is
not ours to give on an owner's behalf, and declining is what the page's own "Not
now" does. Only a skip link the page itself offers is followed — never one we
construct — so if VW stops offering it we stop skipping instead of guessing at a
URL. The link is matched by shape (``/hooks/<anything>/skip``) so a second hook
of the same kind needs no code change, and the host is pinned so the shape
cannot match somewhere it was never meant to.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

PORTAL_OK = "https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html"
HOOK = "https://consent.vwgroup.io/hooks/data-clean-room?session=S1&state=ST"

# The real shape: a root-relative link on the page, carrying the session.
_SKIP_HREF = "/hooks/data-clean-room/skip?session=S1&state=ST"
HOOK_PAGE = (
    '<html><body><h1>Personalised advertising</h1>'
    '<form method="post" action="/hooks/data-clean-room/accept">'
    '<button>Yes please</button></form>'
    f'<a href="{_SKIP_HREF}">Not now</a>'
    '</body></html>'
)
# Same page with the decline link removed — nothing for us to follow.
HOOK_PAGE_NO_SKIP = HOOK_PAGE.replace(f'<a href="{_SKIP_HREF}">Not now</a>', "")


class _Resp:
    def __init__(self, url: str, status: int, text: str) -> None:
        self.url, self.status, self._text = url, status, text
        self.history: tuple[Any, ...] = ()

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:  # noqa: ARG002
        return self._text


class _Session:
    """Answers successive GETs from a script, and records what was asked for."""

    def __init__(self, *steps: tuple[str, int, str]) -> None:
        self._steps = list(steps)
        self.requested: list[str] = []

    def get(self, url: str, **_kw: Any) -> _Resp:
        self.requested.append(url)
        landed, status, body = self._steps.pop(0) if self._steps else (
            PORTAL_OK, 200, "",
        )
        return _Resp(landed, status, body)


def _client(session: _Session) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c._session = session
    c._resume_dead_this_cycle = False
    c.logged_in = False
    c._headers = MagicMock(return_value={})

    async def _no_relogin() -> bool:
        return False

    c.relogin_if_allowed = _no_relogin
    return c


class TestTheHookIsDeclinedAndTheResumeSurvives:
    def test_the_reporters_case_resumes_instead_of_raising(self) -> None:
        """Land on the hook, follow its decline link, end on the portal."""
        sess = _Session(
            (HOOK, 200, HOOK_PAGE),      # the refresh GET lands on the hook
            (PORTAL_OK, 200, ""),        # declining lands back on the portal
        )
        c = _client(sess)
        asyncio.run(c.refresh())
        assert c.logged_in is True
        assert len(sess.requested) == 2, "the decline link was never followed"

    def test_it_follows_the_decline_link_and_not_the_accept_form(self) -> None:
        """The page offers both. Taking the wrong one would agree to advertising
        on the owner's behalf, which is the one outcome that must be impossible."""
        sess = _Session((HOOK, 200, HOOK_PAGE), (PORTAL_OK, 200, ""))
        asyncio.run(_client(sess).refresh())
        followed = sess.requested[1]
        assert "/skip" in followed
        assert "accept" not in followed
        assert followed.startswith("https://consent.vwgroup.io/")
        assert "session=S1" in followed, "the page's own link carries the session"


class TestWhatItDeliberatelyDoesNotDo:
    def test_a_hook_page_without_a_decline_link_keeps_the_old_verdict(self) -> None:
        """The helper may only ever REMOVE a blocker. With nothing to follow,
        the refresh fails exactly as it did before this change."""
        sess = _Session((HOOK, 200, HOOK_PAGE_NO_SKIP))
        with pytest.raises(AuthenticationError, match="did not land on the portal"):
            asyncio.run(_client(sess).refresh())
        assert len(sess.requested) == 1, "nothing may be fetched with no link"

    def test_a_skip_link_on_another_host_is_not_followed(self) -> None:
        """The host is pinned. A page elsewhere that happens to carry a
        skip-shaped link is not an optional VW consent hook."""
        elsewhere = "https://example.invalid/hooks/whatever"
        sess = _Session((elsewhere, 200, HOOK_PAGE))
        with pytest.raises(AuthenticationError, match="did not land on the portal"):
            asyncio.run(_client(sess).refresh())
        assert len(sess.requested) == 1

    def test_a_good_resume_never_reads_the_body(self) -> None:
        """The body is fetched only for that one host. A healthy resume happens
        on every poll, and it must not pull a page down to throw it away."""
        read: list[str] = []

        class _Watching(_Resp):
            async def text(self, errors: str | None = None) -> str:  # noqa: ARG002
                read.append("text")
                return self._text

        class _WatchingSession(_Session):
            def get(self, url: str, **_kw: Any) -> _Resp:
                self.requested.append(url)
                return _Watching(PORTAL_OK, 200, "")

        sess = _WatchingSession()
        c = _client(sess)
        asyncio.run(c.refresh())
        assert c.logged_in is True
        assert read == [], "the body was read on a healthy resume"


class TestTheInteractivePathToo:
    def test_begin_login_declines_the_hook_before_judging_the_landing(self) -> None:
        """The credential POST lands on the same page. Without the decline,
        ``_finalise_login``'s host check reads it as "login did not complete"."""
        c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
        c.logged_in = False
        c._headers = MagicMock(return_value={})
        c._session = _Session((PORTAL_OK, 200, ""))

        declined = asyncio.run(c._decline_action_hook(HOOK, HOOK_PAGE))
        assert declined is not None, "the hook was not recognised"
        landed, status = declined
        assert landed == PORTAL_OK
        assert status == 200

        # And the same call is a no-op on an ordinary landing, which is what
        # makes it safe to put in front of every landing check.
        assert asyncio.run(c._decline_action_hook(PORTAL_OK, "")) is None

# -- the e-mail-code path, which the first fix never reached ------------------
CHALLENGE = "https://identity.vwgroup.io/u/email-challenge?state=ST"
CHALLENGE_FORM = (
    '<html><body><form method="post" action="/u/email-challenge?state=ST">'
    '<input type="hidden" name="_csrf" value="C1">'
    '<input type="text" name="code" value="">'
    "</form></body></html>"
)


class _PostSession(_Session):
    """Adds POST, so submit_otp can be driven rather than approximated.

    The POST answers from its own script; GETs keep coming from _Session's,
    which is what the decline link uses.
    """

    def __init__(
        self,
        post_steps: list[tuple[str, int, str]],
        *get_steps: tuple[str, int, str],
    ) -> None:
        super().__init__(*get_steps)
        self._post_steps = list(post_steps)
        self.posted: list[str] = []

    def post(self, url: str, **_kw: Any) -> _Resp:
        self.posted.append(url)
        landed, status, body = self._post_steps.pop(0) if self._post_steps else (
            PORTAL_OK, 200, "",
        )
        return _Resp(landed, status, body)


def _otp_client(sess: _PostSession) -> WebsiteAuthProxyConnector:
    c = _client(sess)
    c._otp_url = CHALLENGE
    c._otp_html = CHALLENGE_FORM
    c._otp_state = "ST"
    return c


class TestTheEmailCodePathDeclinesTheHookToo:
    def test_the_code_lands_on_the_hook_and_the_login_still_completes(self) -> None:
        """The reported shape. VW shows the opt-in AFTER the e-mail code, so
        begin_login - which returns "otp_required" at the challenge page - never
        reaches its own decline.

        Measured without the decline: this raises "login did not complete
        (ended at consent.vwgroup.io/hooks/data-clean-room)", which is the exact
        message #1827 was filed with, only from this method instead of from
        refresh(). The user holds a correct code and is told the login failed.
        """
        sess = _PostSession(
            [(HOOK, 200, HOOK_PAGE)],   # the code POST lands on the opt-in
            (PORTAL_OK, 200, ""),       # declining lands back on the portal
        )
        c = _otp_client(sess)

        assert asyncio.run(c.submit_otp("123456")) is True
        assert c.logged_in is True
        assert len(sess.requested) == 1, "the decline link was never followed"
        assert "/skip" in sess.requested[0]
        assert "accept" not in sess.requested[0]
        # The pending challenge is cleared, so a stale URL cannot be re-posted.
        assert c._otp_url is None
        assert c._otp_html is None

    def test_a_wrong_code_is_still_a_wrong_code(self) -> None:
        """The dangerous direction. The decline sits in front of the rejection
        check, so it must not turn a refused code into a session: a user with a
        typo has to be told to check the code, not handed a channel that stores
        nothing.
        """
        sess = _PostSession([(CHALLENGE, 200, CHALLENGE_FORM)])
        c = _otp_client(sess)
        with pytest.raises(AuthenticationError, match="OTP rejected"):
            asyncio.run(c.submit_otp("000000"))
        assert c.logged_in is False
        assert sess.requested == [], "nothing may be fetched for a refused code"

    def test_an_http_error_on_the_code_post_still_raises(self) -> None:
        sess = _PostSession([("https://identity.vwgroup.io/u/oops", 500, "")])
        c = _otp_client(sess)
        with pytest.raises(AuthenticationError):
            asyncio.run(c.submit_otp("123456"))
        assert c.logged_in is False

    def test_a_hook_served_with_an_error_status_is_still_declined(self) -> None:
        """The case that makes the ORDER load-bearing rather than tidy.

        VW serves these interstitials from its own infrastructure and nothing
        promises a 200 - the consent host has answered 4xx before. Behind the
        rejection check the decline would never run for such a page: the check
        sees >= 400 and raises "OTP rejected - check the code", which is both
        wrong and unactionable, because the code was right and no new code can
        get past an opt-in page.

        In front of it, the decline reassigns the landing and the status, so the
        check then sees the portal's 200 and the login completes.
        """
        sess = _PostSession(
            [(HOOK, 403, HOOK_PAGE)],   # the opt-in, served with an error status
            (PORTAL_OK, 200, ""),       # declining still lands on the portal
        )
        c = _otp_client(sess)
        assert asyncio.run(c.submit_otp("123456")) is True
        assert c.logged_in is True
        assert len(sess.requested) == 1
        assert "/skip" in sess.requested[0]

    def test_an_ordinary_success_is_untouched(self) -> None:
        """The decline is a no-op on any other host, so the normal path must not
        gain a request or lose its result."""
        sess = _PostSession([(PORTAL_OK, 200, "")])
        c = _otp_client(sess)
        assert asyncio.run(c.submit_otp("123456")) is True
        assert c.logged_in is True
        assert sess.requested == [], "a healthy code POST fetched something extra"

    def test_a_hook_with_no_skip_link_keeps_the_old_verdict(self) -> None:
        """Same contract as the resume path: the helper may only ever remove a
        blocker. With no link to follow the verdict is unchanged from before
        this fix - byte for byte the same raise, which is the point: if VW stops
        offering "Not now" we stop skipping instead of guessing at a URL."""
        sess = _PostSession([(HOOK, 200, HOOK_PAGE_NO_SKIP)])
        c = _otp_client(sess)
        with pytest.raises(AuthenticationError, match="login did not complete"):
            asyncio.run(c.submit_otp("123456"))
        assert c.logged_in is False
        assert sess.requested == [], "nothing may be fetched with no link"


class TestTheDeclineIsInEveryLandingPath:
    """A placement pin, and it says so.

    Every behavioural test above would still pass with the call removed from
    ONE of the three methods, because each test drives only one of them. That
    is exactly how #1827 shipped half-fixed: the decline went into begin_login
    and refresh, submit_otp was missed, and the whole suite stayed green while
    every account that uses an e-mail code remained broken.

    Checked on the methods' own source rather than on a search of the file, so
    a call sitting in some unrelated function cannot satisfy it.
    """

    def test_all_three_landing_methods_decline(self) -> None:
        import ast
        import inspect

        from custom_components.vag_connect.cariad.auth import _website_authproxy

        src = inspect.getsource(_website_authproxy)
        tree = ast.parse(src)
        bodies: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bodies[node.name] = ast.get_source_segment(src, node) or ""

        for method in ("begin_login", "submit_otp", "refresh"):
            assert method in bodies, f"{method} is gone - rename?"
            assert "_decline_action_hook" in bodies[method], (
                f"{method} does not decline the consent hook; an account whose "
                "login goes through it is blocked with no way out but a manual "
                "browser sign-in (#1827)"
            )

    def test_the_decline_runs_before_the_verdict_in_submit_otp(self) -> None:
        """Order, not just presence. Behind the rejection check the call is
        dead code for the reported case: the interstitial is a 200 that is not
        the challenge page, so the verdict is already wrong by the time the
        decline would run."""
        import ast
        import inspect

        from custom_components.vag_connect.cariad.auth import _website_authproxy

        src = inspect.getsource(_website_authproxy)
        tree = ast.parse(src)
        body = ""
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "submit_otp"
            ):
                body = ast.get_source_segment(src, node) or ""
        assert body, "submit_otp not found"
        decline_at = body.index("_decline_action_hook")
        verdict_at = body.index('if landed_status >= 400 or "email-challenge" in landed')
        assert decline_at < verdict_at, (
            "the decline sits behind the rejection check, where it cannot help"
        )
