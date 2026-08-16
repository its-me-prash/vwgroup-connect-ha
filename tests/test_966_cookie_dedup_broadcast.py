# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#966 — the vw.de cookie set must not double every persist cycle.

import_cookies() broadcasts a host-only cookie to BOTH authproxy hosts. On the
next export_cookies(), filter_cookies() then returns that cookie for EACH host
and the empty-domain fallback stamps it with the filter-host, so the old
(domain,name,path) de-dup saw two different domains and kept both. Result: an
11-cookie login round-tripped to a 22-cookie restore whose superseded twin
clobbered the still-good identity.vwgroup.io SSO cookie -> 401 on the second
restart (Arno-MA-73's repro). The export now also folds on (name,path,value),
so a byte-identical broadcast twin collapses while #632's genuinely different
per-host values stay split.
"""
from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

from yarl import URL

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)


class _FilterJar:
    def __init__(self, per_host: dict[str, SimpleCookie]) -> None:
        self._per_host = dict(per_host)

    def filter_cookies(self, url: URL) -> SimpleCookie:
        return self._per_host.get(url.host or "", SimpleCookie())


class _Sess:
    def __init__(self, jar: _FilterJar) -> None:
        self.cookie_jar = jar


def _conn(session: Any) -> WebsiteAuthProxyConnector:
    return WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]


def _ck(name: str, value: str, **attrs: str) -> SimpleCookie:
    c: SimpleCookie = SimpleCookie()
    c[name] = value
    for k, v in attrs.items():
        c[name][k] = v
    return c


def test_broadcast_twin_collapses_to_one():
    # Same host-only SSO cookie present (broadcast) on BOTH hosts, same value.
    www = _ck("auth0", "ssotoken")
    idp = _ck("auth0", "ssotoken")
    jar = _FilterJar({"www.volkswagen.de": www, "identity.vwgroup.io": idp})
    out = _conn(_Sess(jar)).export_cookies()
    assert [c["name"] for c in out].count("auth0") == 1


def test_different_value_per_host_still_kept():
    # #632 guard — auth0 differs per host -> both kept (not folded by #966).
    www = _ck("auth0", "www-value")
    idp = _ck("auth0", "idp-value")
    jar = _FilterJar({"www.volkswagen.de": www, "identity.vwgroup.io": idp})
    out = [c for c in _conn(_Sess(jar)).export_cookies() if c["name"] == "auth0"]
    assert len(out) == 2
    assert {c["value"] for c in out} == {"www-value", "idp-value"}


def test_no_doubling_on_a_realistic_broadcast_state():
    # Post-broadcast jar: 3 host-only cookies live (same value) on BOTH hosts,
    # 1 www-only, 1 idp-only, and 1 genuinely-different-per-host pair.
    def merged(*cookies: SimpleCookie) -> SimpleCookie:
        m: SimpleCookie = SimpleCookie()
        for c in cookies:
            m.update(c)
        return m

    shared = [_ck(f"sso{i}", f"tok{i}") for i in range(3)]  # broadcast twins
    www_only = _ck("wsess", "w1")
    idp_only = _ck("isess", "i1")
    diff_www = _ck("did", "wd")
    diff_idp = _ck("did", "id")

    www = merged(*shared, www_only, diff_www)
    idp = merged(*shared, idp_only, diff_idp)
    jar = _FilterJar({"www.volkswagen.de": www, "identity.vwgroup.io": idp})
    out = _conn(_Sess(jar)).export_cookies()
    names = [c["name"] for c in out]
    # 3 collapsed SSO + wsess + isess + 2 did = 7 (NOT 3*2 + ... = doubled).
    assert len(out) == 7
    for i in range(3):
        assert names.count(f"sso{i}") == 1
    assert names.count("did") == 2  # #632 preserved
