# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.14.10 — website-authproxy: submit the OTP into the form's REAL code field.

Live symptom: entering the email code kept failing with a "credential issue",
and a NEW code was emailed after every attempt. Root cause: the Auth0
email-challenge form's code input is not always named ``code`` — it can be
``mfa-code`` / ``otp`` / ``token``. ``submit_otp`` hardcoded ``fields["code"]``,
so the real field stayed empty → the IDP treated it as "no code entered",
re-issued a fresh challenge (a new email) and the flow bounced on
"email-challenge" forever.

v2.14.10 sets the code into whichever recognised field the parsed form actually
carries (the form parser surfaces value-less inputs), falling back to ``code``
only if none is present. Mirrors the working rafaelhutter authproxy flow.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)

_LANDED_OK = "https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html"


class _Resp:
    def __init__(self, url: str, status: int = 200, text: str = "") -> None:
        self.url = url
        self.status = status
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text


class _CaptureSession:
    """Captures the POST body and lands the OTP submit back on volkswagen.de."""

    def __init__(self) -> None:
        self.posted: dict[str, Any] = {}

    def post(self, url: str, **kw: Any) -> _Resp:
        self.posted = dict(kw.get("data") or {})
        return _Resp(_LANDED_OK, status=200, text="<html>welcome</html>")


def _armed_conn(html: str) -> tuple[WebsiteAuthProxyConnector, _CaptureSession]:
    sess = _CaptureSession()
    conn = WebsiteAuthProxyConnector(sess, "u@x.z", "pw")  # type: ignore[arg-type]
    conn._otp_url = "https://identity.vwgroup.io/u/mfa-email-challenge?state=ST"
    conn._otp_html = html
    conn._otp_state = "ST"
    return conn, sess


@pytest.mark.asyncio
async def test_code_goes_into_mfa_code_field() -> None:
    """A form whose code input is named 'mfa-code' (value-less) gets the code —
    not left empty with the code misfiled under 'code'."""
    html = (
        '<form action="/u/mfa-email-challenge?state=ST">'
        '<input name="state" value="ST">'
        '<input name="mfa-code">'
        '<input name="hmac" value="h">'
        '</form>'
    )
    conn, sess = _armed_conn(html)
    ok = await conn.submit_otp("123456")
    assert ok is True
    assert sess.posted["mfa-code"] == "123456"


@pytest.mark.asyncio
async def test_code_goes_into_otp_field_and_remember_opt_in() -> None:
    """Field named 'otp' gets the code; a 'remember' checkbox is set true."""
    html = (
        '<form action="/u/mfa-email-challenge?state=ST">'
        '<input name="state" value="ST">'
        '<input name="otp">'
        '<input name="rememberBrowser">'
        '</form>'
    )
    conn, sess = _armed_conn(html)
    assert await conn.submit_otp("654321") is True
    assert sess.posted["otp"] == "654321"
    assert sess.posted["rememberBrowser"] == "true"


@pytest.mark.asyncio
async def test_standard_code_field_still_works() -> None:
    """Regression: a form that DOES name it 'code' still works."""
    html = (
        '<form action="/u/mfa-email-challenge?state=ST">'
        '<input name="state" value="ST">'
        '<input name="code">'
        '</form>'
    )
    conn, sess = _armed_conn(html)
    assert await conn.submit_otp("111222") is True
    assert sess.posted["code"] == "111222"


@pytest.mark.asyncio
async def test_no_recognisable_field_falls_back_to_code() -> None:
    """If the form exposes no recognisable code input, fall back to 'code'."""
    html = (
        '<form action="/u/mfa-email-challenge?state=ST">'
        '<input name="state" value="ST">'
        '</form>'
    )
    conn, sess = _armed_conn(html)
    assert await conn.submit_otp("999000") is True
    assert sess.posted["code"] == "999000"
