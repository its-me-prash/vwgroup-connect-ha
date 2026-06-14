# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.14.3 - website-authproxy login-cookie persistence.

The OPT-IN volkswagen.de website-authproxy channel (v2.14.0) logged in once
in the config flow (incl. email-OTP) but the coordinator later built a FRESH
connector with an empty cookie jar, so every setup/restart re-prompted the
email-OTP and raised ``EmailTwoFactorRequiredError``. v2.14.3 persists the
login cookies from the config flow and hydrates them at runtime so the session
resumes WITHOUT a fresh OTP.

The pieces pinned here are the ones verifiable without a live VW account:

  1. ``set_website_authproxy_mode(True, cookies=[...])`` stores the cookies on
     the client (and the param defaults to None → no behaviour change).
  2. ``_arm_website_proxy`` imports the persisted cookies into the connector
     BEFORE ``begin_login()``, so a valid session short-circuits to "ok" and
     NO OTP is requested.
  3. Stale cookies still surface the OTP requirement (normal reauth path).
  4. ``get_website_proxy_cookies`` exports the live jar for refresh-back, and
     ``export_cookies``/``import_cookies`` round-trip the two VW domains.

The live login + reverse-proxy reads require the maintainer's VW account and
are validated post-release; they cannot be unit-tested here.

NOTE: VINs in this file deliberately avoid I/O/Q (the VIN regex rejects them).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    EmailTwoFactorRequiredError,
)


_PERSISTED_COOKIES: list[dict[str, Any]] = [
    {"name": "sess", "value": "abc", "domain": "www.volkswagen.de", "path": "/"},
    {"name": "idp", "value": "xyz", "domain": "identity.vwgroup.io", "path": "/"},
]


def _base_client() -> CariadBaseClient:
    """Build a CariadBaseClient skipping the HA setup chain (test idiom).

    Mirrors the ``__new__`` pattern used across the suite (see
    test_v290_account_lock.py) — we set only the attributes the
    website-authproxy code paths touch.
    """
    c = CariadBaseClient.__new__(CariadBaseClient)
    c._brand = type("B", (), {"name": "volkswagen"})()
    c._session = object()
    c._email = "user@example.com"
    c._password = "secret"
    c._tokens = None
    c._use_website_proxy = False
    c._website_proxy = None
    c._website_proxy_otp = None
    c._website_cookies = None
    c.on_tokens_changed = None
    return c


# ── set_website_authproxy_mode stores cookies (and defaults to None) ──────────

def test_set_mode_stores_cookies() -> None:
    """set_website_authproxy_mode(True, cookies=[...]) stashes them."""
    c = _base_client()
    c.set_website_authproxy_mode(True, cookies=_PERSISTED_COOKIES)
    assert c._use_website_proxy is True
    assert c._website_cookies == _PERSISTED_COOKIES


def test_set_mode_cookies_default_none() -> None:
    """The cookies param defaults to None — no behaviour change for callers
    that don't pass it (strictly additive guarantee)."""
    c = _base_client()
    c.set_website_authproxy_mode(True)
    assert c._use_website_proxy is True
    assert c._website_cookies is None


def test_set_mode_disabled_is_inert() -> None:
    """enabled=False leaves the client in the default (no-proxy) state."""
    c = _base_client()
    c.set_website_authproxy_mode(False)
    assert c._use_website_proxy is False


# ── _arm_website_proxy hydrates cookies and skips OTP ─────────────────────────

@pytest.mark.asyncio
async def test_arm_imports_cookies_and_skips_otp(monkeypatch: Any) -> None:
    """With persisted cookies, the connector's session is already valid:
    begin_login() returns "ok" and NO OTP is requested."""
    connector = MagicMock()
    connector.import_cookies = MagicMock()
    # A valid session short-circuits straight to "ok" (the authproxy redirects
    # an already-authenticated session back to volkswagen.de).
    connector.begin_login = AsyncMock(return_value="ok")
    connector.submit_otp = AsyncMock(return_value=True)
    connector.export_cookies = MagicMock(return_value=_PERSISTED_COOKIES)

    factory = MagicMock(return_value=connector)
    monkeypatch.setattr(
        "custom_components.vag_connect.cariad.auth."
        "_website_authproxy.WebsiteAuthProxyConnector",
        factory,
    )

    c = _base_client()
    c.set_website_authproxy_mode(True, cookies=_PERSISTED_COOKIES)
    await c._arm_website_proxy()

    # Cookies were imported BEFORE begin_login() short-circuited.
    connector.import_cookies.assert_called_once_with(_PERSISTED_COOKIES)
    connector.begin_login.assert_awaited_once()
    connector.submit_otp.assert_not_awaited()
    # Connector retained + sentinel token marks the client authenticated.
    assert c._website_proxy is connector
    assert c._tokens is not None
    assert c._tokens.strategy == "website_authproxy"


@pytest.mark.asyncio
async def test_arm_no_cookies_does_not_import(monkeypatch: Any) -> None:
    """Without persisted cookies, import_cookies is never called and a logged-in
    session still arms cleanly (baseline / no behaviour change)."""
    connector = MagicMock()
    connector.import_cookies = MagicMock()
    connector.begin_login = AsyncMock(return_value="ok")
    factory = MagicMock(return_value=connector)
    monkeypatch.setattr(
        "custom_components.vag_connect.cariad.auth."
        "_website_authproxy.WebsiteAuthProxyConnector",
        factory,
    )

    c = _base_client()
    c.set_website_authproxy_mode(True)  # no cookies
    await c._arm_website_proxy()

    connector.import_cookies.assert_not_called()
    assert c._website_proxy is connector


@pytest.mark.asyncio
async def test_arm_stale_cookies_surface_otp(monkeypatch: Any) -> None:
    """Stale cookies → the IDP still re-prompts; with no OTP code on hand the
    arm raises EmailTwoFactorRequiredError (routes to the normal reauth path)."""
    connector = MagicMock()
    connector.import_cookies = MagicMock()
    connector.begin_login = AsyncMock(return_value="otp_required")
    connector.submit_otp = AsyncMock(return_value=True)
    factory = MagicMock(return_value=connector)
    monkeypatch.setattr(
        "custom_components.vag_connect.cariad.auth."
        "_website_authproxy.WebsiteAuthProxyConnector",
        factory,
    )

    c = _base_client()
    # Cookies supplied but stale; no OTP code available at runtime.
    c.set_website_authproxy_mode(True, cookies=_PERSISTED_COOKIES)
    with pytest.raises(EmailTwoFactorRequiredError):
        await c._arm_website_proxy()
    connector.import_cookies.assert_called_once_with(_PERSISTED_COOKIES)
    connector.submit_otp.assert_not_awaited()


# ── get_website_proxy_cookies exports the live jar (refresh-back) ─────────────

def test_get_website_proxy_cookies_exports() -> None:
    """After arming, get_website_proxy_cookies returns the connector's jar."""
    c = _base_client()
    connector = MagicMock()
    connector.export_cookies = MagicMock(return_value=_PERSISTED_COOKIES)
    c._website_proxy = connector
    assert c.get_website_proxy_cookies() == _PERSISTED_COOKIES


def test_get_website_proxy_cookies_unarmed_is_empty() -> None:
    """With no connector armed, the export is an empty list (never raises)."""
    c = _base_client()
    c._website_proxy = None
    assert c.get_website_proxy_cookies() == []


def test_get_website_proxy_cookies_swallows_export_error() -> None:
    """An export hiccup yields [] rather than breaking the poll."""
    c = _base_client()
    connector = MagicMock()
    connector.export_cookies = MagicMock(side_effect=RuntimeError("boom"))
    c._website_proxy = connector
    assert c.get_website_proxy_cookies() == []


# ── export/import round-trip on the real connector ────────────────────────────

class _FakeCookie(dict):
    """Minimal stand-in for an aiohttp Morsel-like cookie."""

    def __init__(self, key: str, value: str, domain: str) -> None:
        super().__init__()
        self.key = key
        self.value = value
        self["domain"] = domain
        self["path"] = "/"


class _FakeJarSession:
    """Session whose cookie_jar yields a fixed set of cookies."""

    def __init__(self, cookies: list[_FakeCookie]) -> None:
        self._cookies = cookies
        self.updated: list[tuple[str, Any]] = []

    @property
    def cookie_jar(self) -> "_FakeJarSession":
        return self

    def __iter__(self) -> Any:
        return iter(self._cookies)

    def update_cookies(
        self, cookies: dict[str, Any], response_url: Any = None
    ) -> None:
        self.updated.append((next(iter(cookies)), response_url))


def test_export_then_import_round_trip() -> None:
    """A connector exports its VW-domain cookies; a second connector imports
    exactly those (and drops anything off-domain)."""
    src = _FakeJarSession([
        _FakeCookie("sess", "abc", "www.volkswagen.de"),
        _FakeCookie("idp", "xyz", "identity.vwgroup.io"),
        _FakeCookie("other", "nope", "example.com"),
    ])
    exporter = WebsiteAuthProxyConnector(src, "u@x.z", "pw")  # type: ignore[arg-type]
    exported = exporter.export_cookies()
    assert {c["name"] for c in exported} == {"sess", "idp"}

    dst = _FakeJarSession([])
    importer = WebsiteAuthProxyConnector(dst, "u@x.z", "pw")  # type: ignore[arg-type]
    importer.import_cookies(exported)
    injected = {name for name, _url in dst.updated}
    assert injected == {"sess", "idp"}
