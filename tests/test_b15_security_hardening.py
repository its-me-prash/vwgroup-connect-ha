# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b15 — two #1340 (@cyrano330) follow-ups:

1. The legacy IDK OIDC redirect hops logged the redirect URL truncated (not
   redacted) at debug level, so ``code`` (auth JWT) and ``user_id`` (account
   UUID) in the query survived a tester's copy-paste. Now host+path only.
2. Login-success hardening: a portal login that lands on the portal host but
   leaves only the load-balancer cookie is anonymous — surfaced as a portal
   repair instead of a confusing 401 one call later.
"""
from __future__ import annotations

from unittest.mock import MagicMock


# ── 1. IDK redirect-hop URLs are redacted to host+path ────────────────────────

def test_idk_safe_url_strips_secret_query() -> None:
    from custom_components.vag_connect.cariad.auth.idk import _safe_url
    leaky = (
        "https://identity.vwgroup.io/oidc/v1/callback"
        "?code=eyJHVGE_REAL_AUTH_JWT_LEADING_CHARS&user_id=3fa85f64-real-uuid"
        "&relayState=abc"
    )
    out = _safe_url(leaky)
    assert out == "identity.vwgroup.io/oidc/v1/callback"
    assert "code=" not in out
    assert "user_id=" not in out
    assert "REAL_AUTH_JWT" not in out
    assert "real-uuid" not in out


def test_idk_safe_url_handles_junk() -> None:
    from custom_components.vag_connect.cariad.auth.idk import _safe_url
    assert _safe_url("") == "<empty-url>"
    # never raises, even on nonsense
    assert isinstance(_safe_url("::not a url::"), str)


# ── 2. Login-success hardening — anonymous portal session detection ───────────

class _Cookie:
    def __init__(self, key: str, domain: str) -> None:
        self.key = key
        self._d = {"domain": domain}

    def get(self, k: str, default=None):
        return self._d.get(k, default)


def _connector(cookies):
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )
    c = EUDataActConnector.__new__(EUDataActConnector)
    sess = MagicMock()
    sess.cookie_jar = cookies
    c._session = sess  # type: ignore[attr-defined]
    return c


_PORTAL = "eu-data-act.drivesomethinggreater.com"
_IDP = "identity.vwgroup.io"


def test_anonymous_when_only_lb_cookie_on_portal_domain() -> None:
    # the exact #1340 signature: everything auth-y is on the IDP, only the LB's
    # affinity cookie is on the portal domain
    c = _connector([
        _Cookie("SESSION", _IDP),
        _Cookie("JSESSIONID", _IDP),
        _Cookie("affinity", _PORTAL),
    ])
    assert c._portal_session_is_anonymous() is True


def test_not_anonymous_when_a_real_session_cookie_is_present() -> None:
    c = _connector([
        _Cookie("affinity", _PORTAL),
        _Cookie("access_token", _PORTAL),   # a real authenticated session cookie
    ])
    assert c._portal_session_is_anonymous() is False


def test_not_anonymous_when_no_portal_domain_cookie() -> None:
    # no cookie on the portal domain at all → ambiguous, do NOT flag (never raise
    # on an empty set — only on the confirmed affinity-only signature)
    c = _connector([_Cookie("SESSION", _IDP)])
    assert c._portal_session_is_anonymous() is False


def test_not_anonymous_when_empty_jar() -> None:
    c = _connector([])
    assert c._portal_session_is_anonymous() is False
