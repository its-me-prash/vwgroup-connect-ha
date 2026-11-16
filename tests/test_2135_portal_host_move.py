# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2135 — the EU Data Act portal moved to ``eu-data-act.vwgroup-datahub.com``.

Pins the parts of the host move that the older tests do not state outright:
the new host is the portal, the old host is kept only as an exact entry, the
callback host check in ``_data_act_portal`` is an exact-host comparison (not a
substring or suffix test), and a login that lands on the new host is a success.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth import (
    _data_act_portal,
    _data_act_scraper,
    _eu_data_act,
)
from custom_components.vag_connect.cariad.auth._data_act_portal import (
    _is_portal_url,
)
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    _is_login_host,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from tests.test_v2120_eu_data_act_connector import _FakeResp, _FakeSession

_NEW = "eu-data-act.vwgroup-datahub.com"
_OLD = "eu-data-act.drivesomethinggreater.com"


def test_all_three_modules_point_at_the_new_host() -> None:
    for mod in (_eu_data_act, _data_act_portal, _data_act_scraper):
        assert mod._PORTAL_BASE == f"https://{_NEW}", mod.__name__
    assert _eu_data_act._PORTAL_REDIRECT_URI == f"https://{_NEW}/login"
    assert _data_act_portal._PORTAL_OIDC_REDIRECT_URI == f"https://{_NEW}/login"


@pytest.mark.parametrize("netloc", [_NEW, _OLD, _NEW.upper(), _OLD.title()])
def test_new_and_legacy_host_are_both_login_hosts(netloc: str) -> None:
    assert _is_login_host(netloc) is True


@pytest.mark.parametrize("netloc", [
    f"other.{_NEW.split('.', 1)[1]}",
    "vwgroup-datahub.com",
    f"{_NEW}.evil.tld",
    f"{_NEW}:443",
    f"evil{_NEW}",
    f"{_OLD}.evil.tld",
    f"{_OLD}:443",
])
def test_lookalikes_of_the_portal_hosts_are_refused(netloc: str) -> None:
    assert _is_login_host(netloc) is False


# ── _data_act_portal: one exact-host helper instead of substring tests ──────
@pytest.mark.parametrize("url", [
    f"https://{_NEW}/login?code=abc&state=x",
    f"https://{_NEW.upper()}/login",
    f"https://{_NEW}:443/login",
    f"https://{_OLD}/login?code=abc",
])
def test_portal_helper_accepts_the_exact_hosts(url: str) -> None:
    assert _is_portal_url(url) is True


@pytest.mark.parametrize("url", [
    # the host name only inside the query string / path / fragment
    f"https://evil.example.org/cb?next=https://{_NEW}/login",
    f"https://evil.example.org/{_NEW}/login",
    f"https://evil.example.org/cb#{_NEW}",
    f"https://identity.vwgroup.io/signin-service/v1/x?redirect={_NEW}",
    f"https://{_NEW}@evil.example.org/login",
    # lookalike hosts
    f"https://evil{_NEW.replace('eu-data-act.', '')}/login",
    f"https://{_NEW}.example/login",
    f"https://evil{_NEW}/login",
    f"https://other.{_NEW.split('.', 1)[1]}/login",
    "https://vwgroup-datahub.com/login",
    f"https://{_OLD}.example/login",
    "",
    "not a url",
    "https://[::1/login",
])
def test_portal_helper_refuses_everything_else(url: str) -> None:
    assert _is_portal_url(url) is False


# ── a login that lands on the new host is a success ─────────────────────────
class _LandingSession(_FakeSession):
    def __init__(self, landing: str) -> None:
        super().__init__()
        self._landing = landing

    def post(self, url: str, **kw: Any) -> _FakeResp:
        if "/login/authenticate" in url and "?" not in url:
            self.posts.append({"url": url, "data": kw.get("data")})
            return _FakeResp(self._landing, status=200, text="<html>ok</html>")
        return super().post(url, **kw)


@pytest.mark.parametrize("path", ["/dashboard", "/de/de/user.html"])
async def test_a_login_landing_on_the_new_host_is_not_a_failure(path: str) -> None:
    conn = EUDataActConnector(_LandingSession(f"https://{_NEW}{path}"))  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")
    assert conn.logged_in is True


async def test_a_login_landing_on_a_foreign_host_is_still_a_failure() -> None:
    """Control: the landing check was loosened by nothing but the host move."""
    conn = EUDataActConnector(  # type: ignore[arg-type]
        _LandingSession("https://evil.example.org/dashboard")
    )
    with pytest.raises(AuthenticationError):
        await conn.login("user@example.com", "secret")
    assert conn.logged_in is not True
