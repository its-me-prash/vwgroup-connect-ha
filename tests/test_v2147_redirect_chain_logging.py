# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.14.7 — sanitized redirect-chain helper for the website-authproxy beta.

When the volkswagen.de website login loops, the surfaced error is redacted
(it can carry tokens), so the root cause is invisible from a normal log.
v2.14.7 adds a DEBUG-level, **hostname-only** trace of the redirect chain so a
stuck session-resume can be diagnosed (a repeating ``A → B → A → B`` is the
loop signature).

The single safety-critical property pinned here: the helper emits **only
hostnames** — never paths or query strings, because the OAuth ``state`` and any
tokens live in the query. A regression that leaked the full URL into a DEBUG
log would be a token-disclosure bug, so this test is the guard.
"""

from __future__ import annotations

from typing import Any

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)

_rh = WebsiteAuthProxyConnector._redirect_hosts


class _Hop:
    """Minimal stand-in for an aiohttp history entry (carries a ``.url``)."""

    def __init__(self, url: str) -> None:
        self.url = url


def test_chain_emits_hostnames_only_no_query() -> None:
    """A chain whose URLs carry sensitive query strings logs ONLY hostnames."""
    history = [
        _Hop("https://www.volkswagen.de/app/authproxy/login?fag=vw-de"),
        _Hop("https://identity.vwgroup.io/u/login?state=SECRET_TOKEN_abc123"),
    ]
    final = "https://www.volkswagen.de/de/besitzer.html?code=SENSITIVE"
    out = _rh(history, final)

    assert out == "www.volkswagen.de → identity.vwgroup.io → www.volkswagen.de"
    # Hard guard: nothing token-ish from any query string leaked through.
    for leaked in ("state=", "SECRET_TOKEN", "code=", "SENSITIVE", "?", "/u/login"):
        assert leaked not in out


def test_loop_signature_is_visible() -> None:
    """A bouncing A→B→A→B chain renders as the repeating loop signature."""
    history = [
        _Hop("https://www.volkswagen.de/app/authproxy/login"),
        _Hop("https://identity.vwgroup.io/oidc/v1/authorize"),
        _Hop("https://www.volkswagen.de/app/authproxy/callback"),
        _Hop("https://identity.vwgroup.io/oidc/v1/authorize"),
    ]
    out = _rh(history)
    assert out == (
        "www.volkswagen.de → identity.vwgroup.io → "
        "www.volkswagen.de → identity.vwgroup.io"
    )


def test_empty_and_malformed_history_never_raise() -> None:
    """No redirects / None / junk entries degrade gracefully, never raise."""
    assert _rh([]) == "(no redirects)"
    assert _rh(None) == "(no redirects)"
    assert _rh(None, "https://www.volkswagen.de/x?y=z") == "www.volkswagen.de"
    # A junk entry without a usable url becomes "?" rather than crashing.
    junk: Any = [object()]
    assert _rh(junk) == "?"
