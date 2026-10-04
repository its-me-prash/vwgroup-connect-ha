# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A volkswagen.de login that lands on an error page is not a login.

Found by comparing against a competing integration that shipped this fix on
2026-10-03 after the same HTTP/2 outage we fixed in 4.10.0b4. Their description
of the symptom: during the outage "Reconfigure looked fine but stored nothing,
and the integration quietly ran without the volkswagen.de side."

We have the same asymmetry. ``_finalise_login`` marks the session logged in
"iff we ended back on the volkswagen.de host" — host only. The silent-resume
path seventy lines above it already refuses to do that when the landing URL
carries an ``error`` query parameter, and additionally when it ended back on the
login page. So an error page served from volkswagen.de with HTTP 200 passes the
interactive path (the status guard upstream only rejects ``>= 400``) while the
resume path would have caught it.

Second thing fixed here, same leak class as the Porsche error code: the existing
resume check interpolates that query value into the exception **unbounded**.
Error parameters are attacker- and upstream-controlled free text in a message
testers paste into public issues, so both sites now go through one bounded
helper.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad._util import safe_error_token


# ── The bounded token helper ────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "login_failed", "access_denied", "SESSION_EXPIRED", "RS.security.9007",
    "invalid assertion headers",
])
def test_a_real_error_token_survives(value: str) -> None:
    assert safe_error_token(value) == value


@pytest.mark.parametrize("value", [
    "eyJhbGciOiJSUzI1NiJ9.aaaaaaaaaaaaaaaaaaaaaaaa.sig",   # a JWT
    "token 0123456789abcdef0123456789 rejected",            # a secret in prose
    "<script>alert(1)</script>",
    "x" * 41,
    "",
])
def test_anything_unbounded_or_unshaped_is_dropped(value: str) -> None:
    assert safe_error_token(value) == ""


def test_non_string_input_does_not_raise() -> None:
    assert safe_error_token(None) == ""      # type: ignore[arg-type]
    assert safe_error_token(12345) == ""     # type: ignore[arg-type]


# ── _finalise_login ─────────────────────────────────────────────────────────

def _proxy():
    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        WebsiteAuthProxyConnector,
    )

    class _Session:
        cookie_jar = type(
            "_J", (), {"filter_cookies": lambda *_a: {},
                       "update_cookies": lambda *_a: None}
        )()

    return WebsiteAuthProxyConnector(_Session(), "u@t.de", "pw")  # type: ignore[arg-type]


def test_an_error_page_on_the_right_host_is_not_a_login() -> None:
    """The reported failure: the host matches, so it used to count as success."""
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    p = _proxy()
    with pytest.raises(AuthenticationError) as excinfo:
        p._finalise_login("https://www.volkswagen.de/de/besitzer.html?error=login_failed")
    assert p.logged_in is False
    assert "login_failed" in str(excinfo.value)


def test_the_error_value_is_bounded_in_the_message() -> None:
    """An upstream-controlled parameter must not ride into a pasted report."""
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    p = _proxy()
    with pytest.raises(AuthenticationError) as excinfo:
        p._finalise_login(
            "https://www.volkswagen.de/x?error=eyJhbGciOiJSUzI1NiJ9.SECRETPAYLOAD.sig"
        )
    msg = str(excinfo.value)
    assert "SECRETPAYLOAD" not in msg
    assert "eyJ" not in msg


def test_a_clean_landing_still_logs_in() -> None:
    """Happy path unchanged."""
    p = _proxy()
    p._finalise_login("https://www.volkswagen.de/de/besitzer.html")
    assert p.logged_in is True


def test_a_clean_landing_with_other_query_params_still_logs_in() -> None:
    """Only ``error`` disqualifies — an ordinary query must not."""
    p = _proxy()
    p._finalise_login("https://www.volkswagen.de/de/besitzer.html?lang=de&tab=1")
    assert p.logged_in is True


def test_a_foreign_host_still_fails() -> None:
    """Unchanged: ending somewhere else was already a failure."""
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    p = _proxy()
    with pytest.raises(AuthenticationError):
        p._finalise_login("https://identity.vwgroup.io/v2/login/ui/error")
    assert p.logged_in is False


def test_the_two_paths_now_agree() -> None:
    """The point of the change: the interactive finaliser and the silent-resume
    path apply the same rule, instead of only the latter checking."""
    import inspect

    from custom_components.vag_connect.cariad.auth import _website_authproxy

    src = inspect.getsource(_website_authproxy.WebsiteAuthProxyConnector._finalise_login)
    assert "error" in src, "the finaliser does not look at the error parameter"
    whole = inspect.getsource(_website_authproxy)
    assert whole.count("safe_error_token") >= 2, (
        "both sites should share the bounded helper"
    )
