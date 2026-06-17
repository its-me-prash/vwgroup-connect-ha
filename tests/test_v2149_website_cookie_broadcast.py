# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
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


def test_export_dedupes_cookie_present_on_both_hosts() -> None:
    """A cookie returned for both hosts is emitted once."""
    shared = SimpleCookie()
    shared["common"] = "v"
    jar = _FilterJar({
        "www.volkswagen.de": shared,
        "identity.vwgroup.io": shared,
    })
    out = _conn(_Sess(jar)).export_cookies()
    assert [c["name"] for c in out].count("common") == 1


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
@pytest.mark.parametrize("status", [412, 428])
async def test_get_json_412_428_raise_auth_error(status: int) -> None:
    """A stale authproxy session answers 412/428 (not 401) — treat as re-login."""
    class _S:
        def get(self, *_a: Any, **_k: Any) -> _StatusResp:
            return _StatusResp(status)

    with pytest.raises(AuthenticationError):
        await _conn(_S())._get_json("https://www.volkswagen.de/app/authproxy/x")
