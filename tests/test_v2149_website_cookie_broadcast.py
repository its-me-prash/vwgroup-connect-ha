# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.14.9 — website-authproxy cookie persistence: capture + broadcast the
host-only ``auth0`` SSO cookie across both hosts.

Root cause of the restart redirect-loop / re-OTP on the vw.de beta channel:
the ``auth0`` SSO cookie lives host-only on ``identity.vwgroup.io`` (aiohttp
exposes an EMPTY domain for host-only cookies). The old ``export_cookies``
scanned the raw jar and filtered by a domain string → it silently DROPPED that
cookie, and ``import_cookies`` only injected each cookie to its own domain.
Without the SSO cookie reaching ``identity.vwgroup.io``, the silent resume can
never re-establish the session, so the authproxy bounces the resumed session
to the login page (redirect loop) and the user gets re-prompted for an OTP.

v2.14.9 (mirroring the independently-validated rafaelhutter approach):
- ``export_cookies`` collects via ``cookie_jar.filter_cookies(URL(host))`` for
  BOTH hosts → captures host-only cookies (incl. ``auth0``) while staying
  scoped to our two domains.
- ``import_cookies`` broadcasts every persisted cookie host-only to BOTH
  ``www.volkswagen.de`` AND ``identity.vwgroup.io``.
- A stale session's ``412``/``428`` now counts as auth-failure (re-login),
  not just ``401``/``403``.
"""
from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

import pytest
from yarl import URL

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    _MAX_SSO_REDIRECTS,
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError


class _FilterJar:
    """Stand-in for aiohttp's CookieJar: per-host filter + update recorder."""

    def __init__(self, per_host: dict[str, SimpleCookie]) -> None:
        self._per_host = dict(per_host)
        self.updates: list[tuple[str | None, str]] = []

    def filter_cookies(self, url: URL) -> SimpleCookie:
        return self._per_host.get(url.host or "", SimpleCookie())

    def update_cookies(self, cookies: Any, response_url: Any = None) -> None:
        host = response_url.host if response_url is not None else None
        for name in cookies:
            self.updates.append((host, name))


class _Sess:
    def __init__(self, jar: _FilterJar) -> None:
        self.cookie_jar = jar


def _conn(session: Any) -> WebsiteAuthProxyConnector:
    return WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]


# ── export captures the host-only SSO cookie ───────────────────────────────

def test_export_captures_host_only_sso_cookie() -> None:
    """The host-only ``auth0`` cookie (empty domain) on identity.vwgroup.io is
    captured via filter_cookies, where the old domain-string scan dropped it."""
    vw = SimpleCookie()
    vw["sess"] = "abc"
    vw["sess"]["path"] = "/"
    idp = SimpleCookie()
    idp["auth0"] = "ssotoken"  # host-only: no domain attribute set

    jar = _FilterJar({
        "www.volkswagen.de": vw,
        "identity.vwgroup.io": idp,
    })
    out = _conn(_Sess(jar)).export_cookies()
    names = {c["name"] for c in out}
    assert "sess" in names
    assert "auth0" in names  # the previously-dropped SSO cookie
    auth0 = next(c for c in out if c["name"] == "auth0")
    # Empty domain falls back to the host we filtered for.
    assert auth0["domain"] == "identity.vwgroup.io"
    assert auth0["value"] == "ssotoken"


def test_export_dedupes_only_a_truly_identical_cookie() -> None:
    """#632 — de-dup is keyed by (domain, name, path), not (name, value). A cookie
    that is genuinely the same (same explicit domain) collapses to one entry."""
    same = SimpleCookie()
    same["shared"] = "v"
    same["shared"]["domain"] = ".vwgroup.io"
    same["shared"]["path"] = "/"
    jar = _FilterJar({
        "www.volkswagen.de": same,
        "identity.vwgroup.io": same,
    })
    out = _conn(_Sess(jar)).export_cookies()
    assert [c["name"] for c in out].count("shared") == 1


def test_export_keeps_a_cross_host_name_reuse_per_host() -> None:
    """#632 (the fix) — VW reuses cookie names (auth0/did/idkit_p/…) across
    identity.vwgroup.io AND www.volkswagen.de with DIFFERENT values. The old
    (name,value) de-dup collapsed one, and on the restore round-trip the identity
    SSO cookie was lost -> silent resume landed on /u/login. Both are now kept,
    each stamped with its own host, so neither is dropped."""
    www = SimpleCookie()
    www["auth0"] = "www-value"
    idp = SimpleCookie()
    idp["auth0"] = "idp-value"
    jar = _FilterJar({
        "www.volkswagen.de": www,
        "identity.vwgroup.io": idp,
    })
    out = [c for c in _conn(_Sess(jar)).export_cookies() if c["name"] == "auth0"]
    assert len(out) == 2  # not collapsed
    assert {c["domain"] for c in out} == {"www.volkswagen.de", "identity.vwgroup.io"}
    assert {c["value"] for c in out} == {"www-value", "idp-value"}


# ── import broadcasts to BOTH hosts ────────────────────────────────────────

def test_import_broadcasts_sso_cookie_to_both_hosts() -> None:
    """Each persisted cookie is injected against BOTH authproxy hosts so the
    SSO cookie reliably reaches identity.vwgroup.io."""
    jar = _FilterJar({})
    # Domain stamped by export() (here identity.vwgroup.io) — import broadcasts
    # it host-only to BOTH hosts regardless of the stored domain.
    _conn(_Sess(jar)).import_cookies(
        [{"name": "auth0", "value": "ssotoken",
          "domain": "identity.vwgroup.io", "path": "/"}]
    )
    hosts = {host for host, name in jar.updates if name == "auth0"}
    assert hosts == {"www.volkswagen.de", "identity.vwgroup.io"}


def test_import_skips_malformed_entries() -> None:
    """Malformed entries (and foreign-domain ones) are ignored without raising."""
    jar = _FilterJar({})
    _conn(_Sess(jar)).import_cookies(
        [
            {"value": "noname"},  # no name
            "notadict",  # not a dict
            {"name": "foreign", "value": "v", "domain": "example.com"},  # off-domain
            {"name": "ok", "value": "v", "domain": "www.volkswagen.de"},
        ]  # type: ignore[list-item]
    )
    names = {name for _h, name in jar.updates}
    assert names == {"ok"}


def test_import_rejects_a_lookalike_domain_632() -> None:
    """#632 — the scope guard is an exact host/suffix check now, so a foreign
    look-alike that merely CONTAINS our domain as a substring is rejected, while
    our real hosts and their `.vwgroup.io` domain cookies still pass."""
    jar = _FilterJar({})
    _conn(_Sess(jar)).import_cookies(
        [
            {"name": "evil", "value": "v", "domain": "vwgroup.io.attacker.com"},
            {"name": "evil2", "value": "v", "domain": "notvolkswagen.de.evil"},
            {"name": "ok_idp", "value": "v", "domain": "identity.vwgroup.io"},
            {"name": "ok_dot", "value": "v", "domain": ".vwgroup.io"},
            {"name": "ok_www", "value": "v", "domain": "www.volkswagen.de"},
        ]
    )
    names = {name for _h, name in jar.updates}
    assert names == {"ok_idp", "ok_dot", "ok_www"}
    assert "evil" not in names and "evil2" not in names


def test_redirect_budget_accommodates_the_auth0_federation_632() -> None:
    """#632 — VW's silent SSO chains two Auth0 federation dances; the redirect cap
    must exceed aiohttp's default 10 and our old 20 so a good resume in a region
    with extra federation hops isn't aborted as a loop."""
    assert _MAX_SSO_REDIRECTS >= 30


# ── round-trip: SSO cookie survives export → import ────────────────────────

def test_round_trip_sso_cookie_reaches_idp() -> None:
    """End-to-end: a host-only SSO cookie is exported then re-broadcast to the
    IDP host on import — the exact path that was broken before v2.14.9."""
    idp = SimpleCookie()
    idp["auth0"] = "ssotoken"
    src = _FilterJar({"identity.vwgroup.io": idp})
    exported = _conn(_Sess(src)).export_cookies()

    dst = _FilterJar({})
    _conn(_Sess(dst)).import_cookies(exported)
    idp_cookies = {name for host, name in dst.updates
                   if host == "identity.vwgroup.io"}
    assert "auth0" in idp_cookies


# ── 412/428 stale-session signal ───────────────────────────────────────────

class _StatusResp:
    def __init__(self, status: int) -> None:
        self.status = status
        self.url = "https://www.volkswagen.de/app/authproxy/x"

    async def __aenter__(self) -> "_StatusResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def json(self, content_type: Any = None) -> Any:
        return {}


@pytest.mark.asyncio
async def test_get_json_428_raises_auth_error() -> None:
    """A stale authproxy session answers 428 Precondition Required → re-login."""
    class _S:
        def get(self, *_a: Any, **_k: Any) -> _StatusResp:
            return _StatusResp(428)

    with pytest.raises(AuthenticationError):
        await _conn(_S())._get_json("https://www.volkswagen.de/app/authproxy/x")


@pytest.mark.asyncio
async def test_get_json_412_degrades_to_none_not_relogin() -> None:
    """412 is a per-VEHICLE precondition (e.g. the wrong-platform gdc on an MBB
    car), NOT a dead session — verified live 2026-07-12 (relations 200 while
    every read 412'd). It now degrades to None instead of raising, so it can't
    force a re-login / email-OTP loop while the session is still valid. This
    holds even in the non-soft path (412 is never a session signal).
    """
    class _S:
        def get(self, *_a: Any, **_k: Any) -> _StatusResp:
            return _StatusResp(412)

    result = await _conn(_S())._get_json("https://www.volkswagen.de/app/authproxy/x")
    assert result is None
