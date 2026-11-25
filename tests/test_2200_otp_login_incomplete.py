# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2200 — a sign-in that stops short AFTER the e-mail code is not a refused code.

``submit_otp`` reads only two outcomes as a refused code: an HTTP error, or a
return to the ``email-challenge`` page. Anything else goes to
``_finalise_login``, which raises when the chain did not end on volkswagen.de
or ended on a page with an ``error`` parameter. Both dialogs mapped that raise
to ``invalid_otp`` ("That e-mail code was not accepted"), and the options
dialog logged only "rejected the code" at debug level without the message, so
the reporter's log could not say where the sign-in had stopped.

Pinned here, through the REAL ``submit_otp`` with a scripted POST:
- the post-code stop raises ``WebsiteLoginIncompleteError``, still an
  ``AuthenticationError``, naming host and path but never the query;
- the setup, options and repair dialogs show ``website_login_failed`` for it
  and log the landing point at WARNING;
- a return to the challenge page stays ``invalid_otp`` in all three.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect._vwde_reauth import VwDeReauthMixin
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    WebsiteLoginIncompleteError,
)

CHALLENGE = "https://identity.vwgroup.io/u/email-challenge?state=ST"
CHALLENGE_FORM = (
    '<html><body><form method="post" action="/u/email-challenge?state=ST">'
    '<input type="hidden" name="_csrf" value="C1">'
    '<input type="text" name="code" value="">'
    "</form></body></html>"
)
# Where the reporter's sign-in plausibly stopped: an identity page that is not
# the code challenge. The query carries state and must never reach the log.
STOPPED = "https://identity.vwgroup.io/u/login/identifier?state=SECRETSTATE"
ERROR_PAGE = "https://www.volkswagen.de/de/besitzer.html?error=login_failed"
PORTAL_OK = "https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html"


class _Resp:
    def __init__(self, url: str, status: int, text: str = "") -> None:
        self.url, self.status, self._text = url, status, text
        self.history: tuple[Any, ...] = ()

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:  # noqa: ARG002
        return self._text


class _Session:
    """The code POST lands on ``landed``; nothing else is requested."""

    def __init__(self, landed: str, status: int = 200) -> None:
        self._landed, self._status = landed, status
        self.closed = False

    def post(self, _url: str, **_kw: Any) -> _Resp:
        return _Resp(self._landed, self._status)

    def get(self, url: str, **_kw: Any) -> _Resp:
        raise AssertionError(f"unexpected GET {url}")


def _connector(landed: str) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c._session = _Session(landed)
    c._resume_dead_this_cycle = False
    c.logged_in = False
    c._headers = MagicMock(return_value={})
    c._otp_url = CHALLENGE
    c._otp_html = CHALLENGE_FORM
    c._otp_state = "ST"
    return c


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


# ── the connector ─────────────────────────────────────────────────────────────


def test_a_stop_on_another_page_is_its_own_error() -> None:
    with pytest.raises(WebsiteLoginIncompleteError) as excinfo:
        _run(_connector(STOPPED).submit_otp("123456"))
    msg = str(excinfo.value)
    assert "identity.vwgroup.io/u/login/identifier" in msg
    assert "SECRETSTATE" not in msg, "the query must not travel in the message"
    assert isinstance(excinfo.value, AuthenticationError), (
        "callers that handle the parent must keep working"
    )


def test_an_error_page_on_volkswagen_de_is_the_same_error() -> None:
    with pytest.raises(WebsiteLoginIncompleteError, match="error=login_failed"):
        _run(_connector(ERROR_PAGE).submit_otp("123456"))


def test_back_on_the_challenge_page_is_still_a_refused_code() -> None:
    with pytest.raises(AuthenticationError) as excinfo:
        _run(_connector(CHALLENGE).submit_otp("123456"))
    assert not isinstance(excinfo.value, WebsiteLoginIncompleteError)


def test_a_completed_sign_in_is_untouched() -> None:
    c = _connector(PORTAL_OK)
    assert _run(c.submit_otp("123456")) is True
    assert c.logged_in is True


# ── the options dialog (and the repair, which reuses its method) ─────────────


class _Options(VwDeReauthMixin):
    def __init__(self, connector: WebsiteAuthProxyConnector) -> None:
        self.hass = MagicMock()
        self.ovw_reset()
        self._ovw_connector = connector


def _options_submit(landed: str) -> Exception | bool:
    flow = _Options(_connector(landed))
    try:
        return bool(_run(flow._ovw_submit_otp("123456")))
    except ValueError as raised:
        return raised


def test_options_dialog_says_the_sign_in_failed_and_logs_where(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    got = _options_submit(STOPPED)
    assert isinstance(got, ValueError)
    assert str(got) == "website_login_failed"
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "identity.vwgroup.io/u/login/identifier" in r.getMessage() for r in warned
    ), "the landing point is not in the log at WARNING"
    assert "SECRETSTATE" not in caplog.text


def test_options_dialog_keeps_invalid_otp_for_a_refused_code() -> None:
    got = _options_submit(CHALLENGE)
    assert isinstance(got, ValueError)
    assert str(got) == "invalid_otp"


# ── the setup dialog ─────────────────────────────────────────────────────────


def _setup_submit(landed: str) -> Exception | bool:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow

    stub = MagicMock()
    stub._wap_connector = _connector(landed)
    stub._wap_capture_cookies = MagicMock(return_value=[{"name": "sso"}])
    stub._wap_close_session = AsyncMock()
    bound = VagConnectConfigFlow._wap_submit_otp.__get__(stub)
    try:
        return bool(_run(bound("123456")))
    except ValueError as raised:
        return raised


def test_setup_dialog_says_the_sign_in_failed_and_logs_where(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    got = _setup_submit(STOPPED)
    assert isinstance(got, ValueError)
    assert str(got) == "website_login_failed"
    assert any(
        r.levelno == logging.WARNING
        and "identity.vwgroup.io/u/login/identifier" in r.getMessage()
        for r in caplog.records
    )


def test_setup_dialog_keeps_invalid_otp_for_a_refused_code() -> None:
    got = _setup_submit(CHALLENGE)
    assert isinstance(got, ValueError)
    assert str(got) == "invalid_otp"


def test_the_error_key_passes_the_setup_mapping() -> None:
    from custom_components.vag_connect.config_flow import _map_error

    assert _map_error("website_login_failed") == "website_login_failed"


# ── the repair notice's code step ────────────────────────────────────────────


def test_repair_code_step_shows_the_sign_in_failure() -> None:
    from custom_components.vag_connect.repairs import (
        _SupplementaryReauthRepairFlow,
    )

    flow = _SupplementaryReauthRepairFlow("entry-2200")
    flow.hass = MagicMock()
    flow._ovw_connector = _connector(STOPPED)
    flow._ovw_username = "user@example.com"

    res = _run(flow.async_step_otp({"mfa_code": "123456"}))

    assert res["type"] == "form" and res["step_id"] == "otp"
    assert res["errors"]["base"] == "website_login_failed"
