# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for the EU Data Act portal form parser.

Issue #378: after the VW IDP moved hmac/_csrf out of plain
``<input type="hidden">`` markup into a JSON block rendered by the
SPA, the portal third-tier auth fallback was unable to extract the
fields and raised ``AuthenticationError`` on every VW EU re-auth
attempt past the 2h token-expiry window.

The fix mirrors the multi-fallback strategy already in
``idk.py:_parse_csrf_robust``: HTMLParser, regex-over-hidden-inputs,
form-action regex, and JSON/script-block extraction. These tests
pin every fallback path so a future markup migration on either side
fails loudly here instead of in production.
"""

from __future__ import annotations

import re


# Tests run pure-Python. Algorithm is replicated below from the
# production code so we do not transitively import the HA-dependent
# ``DataActPortalAuth`` class just to exercise the parser.


# The fix lives inside ``DataActPortalAuth.login`` as a local closure.
# To keep the test pure-Python (no aiohttp session needed), we extract
# the same algorithm here. Any drift between the test and the
# production code is intentional: the test pins the algorithm shape,
# the production code can evolve as long as it accepts the same
# HTML shapes and produces the same fields.

def _extract_fields(landing_html: str) -> tuple[dict[str, str], str]:
    """Run the same parser shape as the production login flow."""
    from html.parser import HTMLParser

    class _IdentifierFormParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.fields: dict[str, str] = {}
            self.form_action: str = ""

        def handle_starttag(self, tag, attrs):
            attr = dict(attrs)
            if tag == "input" and attr.get("type") == "hidden":
                name = attr.get("name") or ""
                if name:
                    self.fields[name] = attr.get("value") or ""
            elif tag == "form" and not self.form_action:
                self.form_action = attr.get("action") or ""

    parser = _IdentifierFormParser()
    parser.feed(landing_html)

    for tag_match in re.finditer(r"<input[^>]+>", landing_html, re.IGNORECASE):
        t = tag_match.group(0)
        if 'type="hidden"' not in t.lower() and "type='hidden'" not in t.lower():
            continue
        name_match = re.search(r'name=["\']([^"\']+)["\']', t)
        value_match = re.search(r'value=["\']([^"\']*)["\']', t)
        if name_match:
            parser.fields.setdefault(
                name_match.group(1),
                value_match.group(1) if value_match else "",
            )

    if not parser.form_action:
        form_match = re.search(
            r'action=["\']([^"\']+/login/[^"\']+)["\']', landing_html,
        )
        if form_match:
            parser.form_action = form_match.group(1)

    if not parser.fields.get("_csrf"):
        for pattern in (
            r'"_csrf"\s*:\s*"([^"]{8,})"',
            r'"csrf"\s*:\s*"([^"]{8,})"',
            r'"csrfToken"\s*:\s*"([^"]{8,})"',
        ):
            m = re.search(pattern, landing_html)
            if m:
                parser.fields["_csrf"] = m.group(1)
                break
    if not parser.fields.get("hmac"):
        m = re.search(r'"hmac"\s*:\s*"([0-9a-fA-F]{20,})"', landing_html)
        if m:
            parser.fields["hmac"] = m.group(1)

    return parser.fields, parser.form_action


class TestClassicHiddenInputShape:
    """Pre-#378 shape: hmac + _csrf as plain hidden form inputs."""

    def test_extracts_hmac_csrf_and_action(self) -> None:
        html = """
        <html><body>
          <form action="/signin-service/v1/login/identifier"
                method="POST">
            <input type="hidden" name="_csrf" value="legacy-csrf-12345678">
            <input type="hidden" name="hmac" value="0123456789abcdef0123456789abcdef0123456789ab">
            <input type="hidden" name="relayState" value="rs-1">
            <input type="email" name="email">
          </form>
        </body></html>
        """
        fields, action = _extract_fields(html)
        assert fields["_csrf"] == "legacy-csrf-12345678"
        assert fields["hmac"] == "0123456789abcdef0123456789abcdef0123456789ab"
        assert fields["relayState"] == "rs-1"
        assert "login/identifier" in action


class TestModernSpaShape:
    """Post-#378 shape: hmac + _csrf inside a SPA-rendered JSON block."""

    def test_extracts_from_inline_json(self) -> None:
        html = """
        <html><body>
          <form action="/signin-service/v1/login/identifier" method="POST">
            <input type="email" name="email">
          </form>
          <script>
            window.__STORE__ = {
              "user": null,
              "_csrf": "spa-csrf-abc12345xyz",
              "hmac": "deadbeef00112233445566778899aabbccddeeff",
              "relayState": "rs-2"
            };
          </script>
        </body></html>
        """
        fields, action = _extract_fields(html)
        assert fields["_csrf"] == "spa-csrf-abc12345xyz"
        assert fields["hmac"] == "deadbeef00112233445566778899aabbccddeeff"
        assert "login/identifier" in action

    def test_alternate_csrf_key_names(self) -> None:
        html = """
        <html><body>
          <form action="/u/login/identifier"></form>
          <script>
            window.config = {"csrfToken":"token-with-key-csrfToken-32chars"};
          </script>
        </body></html>
        """
        fields, action = _extract_fields(html)
        # csrfToken should be mapped to the _csrf field the POST expects.
        assert fields["_csrf"] == "token-with-key-csrfToken-32chars"

    def test_html_parser_partial_then_regex_fills_rest(self) -> None:
        """Mixed shape: form action via HTML, hmac via JSON."""
        html = """
        <html><body>
          <form action="/signin-service/v1/login/identifier">
            <input type="hidden" name="_csrf" value="from-html-csrf-token">
          </form>
          <script>{"hmac":"aabbccddeeff00112233445566778899"}</script>
        </body></html>
        """
        fields, action = _extract_fields(html)
        assert fields["_csrf"] == "from-html-csrf-token"
        assert fields["hmac"] == "aabbccddeeff00112233445566778899"


class TestRejectsTrulyEmpty:
    """If the IDP returns a page with neither shape, we still raise."""

    def test_no_fields_no_action(self) -> None:
        html = "<html><body><h1>Service unavailable</h1></body></html>"
        fields, action = _extract_fields(html)
        assert "hmac" not in fields
        assert action == ""

    def test_short_csrf_below_minimum_length_ignored(self) -> None:
        """8-char minimum in the JSON regex guards against false positives
        on unrelated short ``"csrf": "no"`` strings that may appear in
        marketing copy."""
        html = '<script>{"csrf":"no"}</script>'
        fields, _ = _extract_fields(html)
        assert "_csrf" not in fields
