# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#632 parity (vs the reference vw.de website-portal project) — two remaining
gaps closed: (1) a terms-and-conditions wall in the silent-resume path is
surfaced as an actionable error instead of a generic session-expired loop; (2)
the cookie persist never overwrites a good set with one captured from a DEAD
session.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.const import (
    CONF_WEBSITE_AUTHPROXY,
    CONF_WEBSITE_COOKIES,
)
from custom_components.vag_connect.coordinator import VagConnectCoordinator


class _Resp:
    def __init__(self, url: str, status: int = 200, text: str = "") -> None:
        self.url = url
        self.status = status
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text


# ── gap 1: T&C wall in the resume path → actionable, not a generic loop ──────

@pytest.mark.asyncio
async def test_tc_wall_in_begin_login_raises_actionable() -> None:
    class _S:
        def get(self, url: str, **_kw: object) -> _Resp:
            return _Resp(
                "https://identity.vwgroup.io/u/terms?state=ST", 200,
                "<html>please accept the terms</html>",
            )

    conn = WebsiteAuthProxyConnector(_S(), "u@x.z", "pw")  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError, match="terms-and-conditions"):
        await conn.begin_login()
    assert conn.logged_in is False


# ── gap 2: never persist a dead session over a good cookie set ───────────────

def _coord(*, logged_in: bool, fresh: list):
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = SimpleNamespace(
        entry_id="e1",
        data={
            CONF_WEBSITE_AUTHPROXY: True,
            CONF_WEBSITE_COOKIES: [
                {"name": "good", "value": "v",
                 "domain": "identity.vwgroup.io", "path": "/"}
            ],
        },
    )
    web = SimpleNamespace(logged_in=logged_in)
    coord._cariad_client = SimpleNamespace(
        _website_proxy=web,
        get_website_proxy_cookies=lambda: fresh,
    )
    return coord


def test_persist_skipped_when_session_not_logged_in() -> None:
    """A dead session (logged_in False) must NOT overwrite the good persisted
    set — otherwise the next restart is guaranteed to fail too."""
    coord = _coord(logged_in=False, fresh=[{"name": "dead", "value": "x"}])
    coord._persist_website_cookies()
    coord.hass.config_entries.async_update_entry.assert_not_called()


def test_persist_proceeds_when_logged_in_and_changed() -> None:
    """A live session with a genuinely fresh set still persists."""
    coord = _coord(
        logged_in=True,
        fresh=[{"name": "good", "value": "ROLLED",
                "domain": "identity.vwgroup.io", "path": "/"}],
    )
    coord._persist_website_cookies()
    coord.hass.config_entries.async_update_entry.assert_called_once()
