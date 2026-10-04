# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One guarded OAuth error-code reader, shared by every auth module.

Two copies of ``_oauth_error_code`` existed, with different safety properties:

* The Porsche one (added as a redaction helper) read only ``error`` and returned
  ``str(parsed["error"])`` — **no length or shape bound at all** — and three call
  sites interpolate that straight into an ``AuthenticationError`` message, which
  Home Assistant shows and testers paste into public issues. Its own docstring
  promises the raw body never reaches such a message; nothing enforced that for
  the field's own value.
* The IDK one reads ``error`` **and** ``errorCode`` and validates the shape.

Which key matters was counted across the archived captures rather than taken
from RFC 6749: ``errorCode`` carries the code 90 times (INVALID_REQUEST 50,
USER_NOT_AUTHORIZED 20, METHOD_NOT_ALLOWED 15, RS.security.9007, …) against 18
for the spec's own ``error``. The captures also show the field is not reliably a
short enum — one body carries ``invalid assertion headers``, a sentence — which
is exactly why a bound is needed rather than assumed.

So: one implementation, guarded, in the module that already owns the masking
helpers. ``oauth_error_code`` returns the code or ``""``; ``oauth_error_label``
always returns something printable, keeping the Porsche messages' useful
distinction between "the endpoint did not answer JSON" (a gateway page) and
"JSON without a usable code".
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad._util import (
    oauth_error_code,
    oauth_error_label,
)

# Every distinct value shape seen in the archived captures.
OBSERVED = [
    "INVALID_REQUEST",            # 50 — uppercase, not the spec's lowercase
    "USER_NOT_AUTHORIZED",        # 20
    "METHOD_NOT_ALLOWED",         # 15
    "RS.security.9007",           # dotted
    "RLU.security.9007",
    "REQUEST_DATA_INVALID",
    "IllegalStateException",
    "invalid assertion headers",  # the one spaced value
    "invalid_grant",              # and the spec shape
    "unauthorized_client",        # ditto
]


@pytest.mark.parametrize("value", OBSERVED)
def test_every_observed_shape_is_read_under_both_keys(value: str) -> None:
    assert oauth_error_code('{"error":"%s"}' % value) == value
    assert oauth_error_code('{"errorCode":"%s"}' % value) == value


def test_errorcode_is_read_at_all() -> None:
    """The majority key in real captures, and the one the Porsche copy missed."""
    body = '{"errorCode":"USER_NOT_AUTHORIZED","origin":"CarnetSPAuthorizationServer"}'
    assert oauth_error_code(body) == "USER_NOT_AUTHORIZED"


def test_error_wins_over_errorcode_deterministically() -> None:
    assert oauth_error_code('{"error":"invalid_client","errorCode":"X_Y"}') \
        == "invalid_client"


def test_the_description_is_never_read() -> None:
    """``error_description`` is free text and echoes request content back."""
    body = ('{"error":"invalid_request","error_description":'
            '"redirect_uri=myaudi://cb?state=SECRETSTATE is not registered"}')
    out = oauth_error_code(body)
    assert out == "invalid_request"
    assert "SECRETSTATE" not in out and "redirect_uri" not in out


@pytest.mark.parametrize("body", [
    # A JWT, which the unguarded copy would have passed through verbatim.
    '{"error":"eyJhbGciOiJSUzI1NiJ9.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.sig"}',
    # Request content echoed back around a secret.
    '{"error":"the access token 0123456789abcdef is not valid for this user"}',
    '{"error":"user 0123456789abcdef0123456789 denied"}',
    # Markup.
    '{"error":"<script>alert(1)</script>"}',
    # Nothing usable.
    '{"error":""}',
    '{"error":12345}',
    '{"errorCode":"0"}',
    '{"errorCode":"1"}',
    '{"errorCode":"9007"}',
    '{"nested":{"error":"invalid_grant"}}',
    '{}',
    '[]',
    '"just a string"',
])
def test_nothing_unbounded_or_useless_gets_through(body: str) -> None:
    assert oauth_error_code(body) == "", body


def test_a_long_token_is_refused_even_though_spaces_are_allowed() -> None:
    """Spaces are permitted so "invalid assertion headers" survives; the
    per-token bound is what stops a secret riding along in free text."""
    assert oauth_error_code('{"error":"invalid assertion headers"}') \
        == "invalid assertion headers"
    assert oauth_error_code('{"error":"bad eyJhbGciOiJSUzI1NiJ9aaaaaaaaaa hdr"}') == ""


def test_non_json_bodies_do_not_raise() -> None:
    for body in ("", "not json", "<html>502 Bad Gateway</html>", "\x00\x01"):
        assert oauth_error_code(body) == ""


# ── The printable label, which the Porsche messages interpolate ──────────────

def test_the_label_keeps_the_gateway_vs_json_distinction() -> None:
    """A gateway returning HTML and a backend returning JSON without a code are
    different diagnoses, and the Porsche messages were already distinguishing
    them. That must survive unification."""
    assert oauth_error_label('{"error":"invalid_grant"}') == "invalid_grant"
    assert oauth_error_label("<html>502 Bad Gateway</html>") == "non-JSON body"
    assert oauth_error_label("") == "non-JSON body"
    assert oauth_error_label('{"foo":"bar"}') == "no usable error code"


def test_the_label_never_carries_an_unbounded_value() -> None:
    """The whole point: what reaches a pasted message is bounded."""
    label = oauth_error_label(
        '{"error":"eyJhbGciOiJSUzI1NiJ9.aaaaaaaaaaaaaaaaaaaaaaaa.sig"}'
    )
    assert label == "no usable error code"
    assert "eyJ" not in label


def test_the_label_is_short_enough_for_a_log_line() -> None:
    for body in ('{"error":"%s"}' % ("x" * 500), '{"errorCode":"%s"}' % ("A_" * 300)):
        assert len(oauth_error_label(body)) <= 40


# ── Behavioural dependency: Porsche branches on the returned value ───────────

def test_the_porsche_refresh_expiry_branch_still_sees_invalid_grant() -> None:
    """Porsche turns a 400 + ``invalid_grant`` into "refresh token expired"
    rather than a generic auth failure. The guard must not break that compare."""
    assert oauth_error_code('{"error":"invalid_grant"}') == "invalid_grant"
    assert oauth_error_code(
        '{"error":"invalid_grant","error_description":"Unknown or invalid refresh token."}'
    ) == "invalid_grant"


def test_both_auth_modules_use_the_shared_helper_and_keep_no_copy() -> None:
    """Guard against the duplicate coming back: neither module may define its
    own extractor again."""
    import inspect

    from custom_components.vag_connect.cariad._util import (
        oauth_error_code as shared,
    )
    from custom_components.vag_connect.cariad.auth import idk, porsche

    for mod in (idk, porsche):
        src = inspect.getsource(mod)
        assert "def _oauth_error_code" not in src, (
            f"{mod.__name__} defines its own extractor again"
        )
        assert mod.oauth_error_code is shared, f"{mod.__name__} is not using the shared one"
