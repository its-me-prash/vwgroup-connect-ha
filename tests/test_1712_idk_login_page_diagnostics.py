# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1712 — "no form fields found" did not say which page it had landed on.

The legacy signin-service parser raises when ``_csrf``, ``hmac`` *and*
``relayState`` are all missing, i.e. when the served page is not the classic
form at all. The old message named none of that: not the path, not the form
action, not the field names it did see. The one line that identifies the page
existed only at DEBUG level, so every report needed a second round of "please
turn on debug logging first" before anyone could tell which login variant VW had
served.

That matters right now because the dispatch treats a page as the Auth0 universal
login **only** when the landing URL contains ``/u/login``, while
``/v2/login/ui/*`` is demonstrably live (a reporter's wall at
``/v2/login/ui/terms-and-conditions``). A universal login served under that path
lands in the legacy parser and produces exactly this error.

**Redaction matters here more than usual.** These URLs carry ``code`` (the
authorization JWT), ``user_id`` (an account UUID), ``relayState`` and sometimes
``access_token`` in the query or fragment, and the hidden fields carry CSRF and
hmac *values*. The diagnostic must name the page and the field NAMES, and must
never carry a query string, a fragment or a single field value.
"""
from __future__ import annotations

import asyncio

import pytest


class _Resp:
    def __init__(self, status: int = 200, text: str = "") -> None:
        self.status = status
        self._text = text
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None


class _Session:
    """Never reached: every case here fails while parsing the first page."""

    def __init__(self) -> None:
        self.cookie_jar = type("_J", (), {"filter_cookies": lambda *_a: {}})()

    def get(self, *_a: object, **_k: object) -> _Resp:
        raise AssertionError("the parser should have raised before any request")

    post = get


def _idk():
    from custom_components.vag_connect.cariad.api.vw_na import BRAND_VW_NA
    from custom_components.vag_connect.cariad.auth.idk import IDKAuth

    return IDKAuth(_Session(), BRAND_VW_NA)


def _raise_for(html: str, login_url: str | None = None) -> str:
    """Return the message of the AuthenticationError the parser raises."""
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    kwargs = {} if login_url is None else {"login_url": login_url}
    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(
            _idk()._authenticate_legacy(
                html, "u@t.de", "pw", "verifier-123", **kwargs,  # type: ignore[arg-type]
            )
        )
    return str(excinfo.value)


# The page a reporter actually hits: a universal login / interstitial served
# outside /u/login, so the legacy parser gets it and finds no classic fields.
_UI_PAGE = '<html><body><div id="root">loading</div></body></html>'
_UI_URL = (
    "https://identity.vwgroup.io/v2/login/ui/terms-and-conditions"
    "?code=eyJhbGciOiJSUzI1NiJ9.SECRETJWT.sig"
    "&user_id=3f7b1a24-5c6d-4e8f-9a0b-1c2d3e4f5a6b"
    "&relayState=abcdef0123456789"
)


def test_the_landing_path_is_named_in_the_error() -> None:
    """The whole point: the next report says which page it was, without anyone
    having to enable debug logging first."""
    msg = _raise_for(_UI_PAGE, _UI_URL)
    assert "/v2/login/ui/terms-and-conditions" in msg, msg
    assert "identity.vwgroup.io" in msg, msg


def test_the_query_string_never_reaches_the_error() -> None:
    """These URLs carry the authorization JWT, the account UUID and relayState.
    The message is pasted into public issues verbatim."""
    msg = _raise_for(_UI_PAGE, _UI_URL)
    for secret in ("SECRETJWT", "eyJhbGciOiJSUzI1NiJ9", "abcdef0123456789", "code="):
        assert secret not in msg, f"{secret!r} leaked into: {msg}"
    assert "?" not in msg, msg


def test_a_uuid_in_the_path_is_masked() -> None:
    """The consent page carries the account UUID as a path segment, where
    stripping the query does not help."""
    msg = _raise_for(
        _UI_PAGE,
        "https://identity.vwgroup.io/signin-service/v1/consent/users/"
        "3f7b1a24-5c6d-4e8f-9a0b-1c2d3e4f5a6b/details",
    )
    assert "3f7b1a24" not in msg, msg
    assert "/consent/users/" in msg, msg


def test_hidden_field_names_are_reported_but_never_their_values() -> None:
    """Names identify the page variant; values are secrets."""
    html = (
        "<html><body><form action='/v2/login/ui/next'>"
        '<input type="hidden" name="sessionDataKey" value="SECRET-SESSION-VALUE">'
        '<input type="hidden" name="tenantDomain" value="SECRET-TENANT-VALUE">'
        "</form></body></html>"
    )
    msg = _raise_for(html, _UI_URL)
    assert "sessionDataKey" in msg, msg
    assert "tenantDomain" in msg, msg
    assert "SECRET-SESSION-VALUE" not in msg, msg
    assert "SECRET-TENANT-VALUE" not in msg, msg


def test_the_form_action_is_reported() -> None:
    """Distinguishes "a form, but a different one" from "no form at all"."""
    html = (
        "<html><body><form action='/v2/login/ui/next'>"
        '<input type="hidden" name="sessionDataKey" value="x">'
        "</form></body></html>"
    )
    msg = _raise_for(html, _UI_URL)
    assert "/v2/login/ui/next" in msg, msg


def test_a_page_without_any_form_says_so() -> None:
    """A JS-rendered shell or an error page has no <form> at all — that is a
    different diagnosis from "a form we could not read", and it is the one that
    tells us the page never belonged to the legacy flow."""
    msg = _raise_for(_UI_PAGE, _UI_URL)
    assert "<form> present: no" in msg, msg
    # Counter-check, so this cannot pass on the old wording's "no form fields":
    html = (
        "<html><body><form action='/x'>"
        '<input type="hidden" name="sessionDataKey" value="v">'
        "</form></body></html>"
    )
    assert "<form> present: yes" in _raise_for(html, _UI_URL)


def test_an_unknown_landing_url_still_raises_cleanly() -> None:
    """Call sites that do not know the URL must keep working — the diagnostic is
    additive, never a new failure mode."""
    msg = _raise_for(_UI_PAGE)
    assert "unknown" in msg.lower(), msg
    assert "Could not parse IDK login page" in msg, msg


def test_the_field_name_list_stays_bounded() -> None:
    """A hostile or JS-heavy page can carry hundreds of inputs with long names;
    the message ends up in a log line and in a pasted report."""
    inputs = "".join(
        f'<input type="hidden" name="field_{i}_{"x" * 80}" value="v">'
        for i in range(60)
    )
    msg = _raise_for(f"<html><body><form>{inputs}</form></body></html>", _UI_URL)
    assert len(msg) < 600, f"message is {len(msg)} chars: {msg}"


def test_the_original_sentence_is_kept() -> None:
    """Reporters and search both key on the existing wording; the diagnostic is
    appended, not a rewrite."""
    msg = _raise_for(_UI_PAGE, _UI_URL)
    assert msg.startswith("Could not parse IDK login page (legacy flow)"), msg


def test_a_parseable_legacy_page_does_not_raise_here() -> None:
    """Guard the happy path: a classic page with the expected fields must get
    past this check and fail later (at the network call), not at the parser."""
    html = (
        "<html><body><form action='/signin-service/v1/CLIENT/login/identifier'>"
        '<input type="hidden" name="_csrf" value="t">'
        '<input type="hidden" name="relayState" value="r">'
        '<input type="hidden" name="hmac" value="h">'
        "</form></body></html>"
    )
    with pytest.raises(AssertionError, match="should have raised before any request"):
        asyncio.run(
            _idk()._authenticate_legacy(
                html, "u@t.de", "pw", "verifier-123", login_url=_UI_URL,
            )
        )


# ---------------------------------------------------------------------------
# The same reporter's SECOND failure: strategy #1 dies at the token exchange
# with a bare "HTTP 400 (body N chars)". RFC 6749 §5.2 puts a short machine
# token in that body ("invalid_grant", "invalid_client", "unauthorized_client"),
# which separates a wrong client id from a spent code from a redirect mismatch.
# It is a code, not a secret — but the body around it is NOT trusted, so only a
# value shaped like an OAuth error code is ever emitted.
# ---------------------------------------------------------------------------

def _err_code(body: str) -> str:
    from custom_components.vag_connect.cariad.auth.idk import _oauth_error_code

    return _oauth_error_code(body)


def test_the_oauth_error_code_is_extracted() -> None:
    assert _err_code('{"error":"invalid_grant","error_description":"code used"}') \
        == "invalid_grant"
    assert _err_code('{"error": "unauthorized_client"}') == "unauthorized_client"


def test_the_error_description_is_never_extracted() -> None:
    """``error_description`` echoes request content back and is free text."""
    body = '{"error":"invalid_request","error_description":"redirect_uri=myaudi://x?t=SECRET"}'
    out = _err_code(body)
    assert out == "invalid_request"
    assert "SECRET" not in out
    assert "redirect_uri" not in out


def test_anything_not_shaped_like_an_error_code_is_dropped() -> None:
    """A JWT, a sentence, HTML or a long opaque value must never pass through,
    whatever the upstream decides to put in that field."""
    for hostile in (
        '{"error":"eyJhbGciOiJSUzI1NiJ9.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.sig"}',
        '{"error":"the access token 12345 is not valid for this user account"}',
        '{"error":"<script>alert(1)</script>"}',
        '{"error":""}',
        '{"error":12345}',
        "<html>502 Bad Gateway</html>",
        "",
        "not json at all",
        '{"nested":{"error":"invalid_grant"}}',
    ):
        assert _err_code(hostile) == "", f"leaked for {hostile[:40]!r}"


def test_the_token_exchange_message_carries_the_code_when_present() -> None:
    from custom_components.vag_connect.cariad.auth.idk import _token_exchange_detail

    msg = _token_exchange_detail(400, '{"error":"invalid_client"}')
    assert "400" in msg and "invalid_client" in msg
    # And stays exactly as before when the body says nothing usable:
    body = "<html>oops</html>"
    assert _token_exchange_detail(400, body) == \
        f"Token exchange failed HTTP 400 (body {len(body)} chars)"


# ---------------------------------------------------------------------------
# Grounded against the archived captures rather than against the spec. Counted
# there: ``errorCode`` carries the diagnosis 90 times (INVALID_REQUEST 50,
# USER_NOT_AUTHORIZED 20, METHOD_NOT_ALLOWED 15, RS.security.9007, …) against 18
# for RFC 6749's own ``error`` — so reading only ``error``, as the first version
# of this did, returns nothing on most real bodies. The observed values are also
# SCREAMING_SNAKE, dotted and in one case spaced, none of which the spec's
# lowercase-token assumption covers.
# ---------------------------------------------------------------------------

def test_the_errorcode_key_is_read_not_just_error() -> None:
    """The majority case in real captures."""
    assert _err_code('{"errorCode":"USER_NOT_AUTHORIZED"}') == "USER_NOT_AUTHORIZED"
    assert _err_code('{"errorCode":"METHOD_NOT_ALLOWED"}') == "METHOD_NOT_ALLOWED"


def test_the_observed_value_shapes_all_pass() -> None:
    """Every distinct shape actually seen in the captures."""
    for observed in (
        "INVALID_REQUEST",          # 50 — uppercase, not the spec's lowercase
        "USER_NOT_AUTHORIZED",      # 20
        "METHOD_NOT_ALLOWED",       # 15
        "RS.security.9007",         # dotted
        "RLU.security.9007",
        "REQUEST_DATA_INVALID",
        "IllegalStateException",
        "invalid assertion headers",  # the one spaced value
        "invalid_grant",            # and the spec shape still works
    ):
        assert _err_code('{"error":"%s"}' % observed) == observed, observed
        assert _err_code('{"errorCode":"%s"}' % observed) == observed, observed


def test_a_numeric_code_is_treated_as_noise() -> None:
    """Seen as "0" and "1" — a number is not a diagnosis."""
    assert _err_code('{"errorCode":"0"}') == ""
    assert _err_code('{"errorCode":"1"}') == ""
    assert _err_code('{"errorCode":"9007"}') == ""


def test_a_long_token_is_still_dropped_even_though_spaces_are_allowed() -> None:
    """Allowing spaces must not open a door for a secret: the per-token cap is
    what closes it, so a sentence containing an opaque value is refused while
    "invalid assertion headers" is not."""
    assert _err_code('{"error":"token eyJhbGciOiJSUzI1NiJ9aaaaaaaaaaaaaaaa bad"}') == ""
    assert _err_code('{"error":"user 0123456789abcdef0123456789 denied"}') == ""
    assert _err_code('{"error":"invalid assertion headers"}') == "invalid assertion headers"


def test_error_wins_over_errorcode_when_both_are_present() -> None:
    """Deterministic order, so the message does not depend on dict ordering."""
    assert _err_code('{"error":"invalid_client","errorCode":"INVALID_REQUEST"}') \
        == "invalid_client"
