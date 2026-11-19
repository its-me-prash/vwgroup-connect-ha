# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Audi market-config fetch asks like the app and watches the sign-in keys.

Grounded in myAudi 5.10.1 (Google Play, 2026-11-18): the app appends
``v=<versionName>`` to the market-config URL
(``MarketResourceDownloadAction.l()`` → ``VersionInformation.e()``), and the
CDN answers per version — measured that day, DE gave 68 keys for
``v=4.23.1`` and 122 for ``v=5.10.1``. The app picks Auth0 or IdentityKit for
new sign-ins from ``marketSupportsAuth0``; this fetch now carries that and
three neighbouring keys so a market switch becomes visible.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth import _audi_market_config as mc
from custom_components.vag_connect.cariad.models import (
    MYAUDI_APP_VERSION,
    MYAUDI_USER_AGENT,
)


class _Resp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self.status = status
        self._payload = payload

    async def json(self) -> Any:
        return self._payload

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Session:
    """Records the one GET the fetch makes and answers with ``payload``."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, *, timeout: Any, headers: dict[str, str]) -> _Resp:
        self.calls.append((url, headers))
        return _Resp(self.payload)


@pytest.fixture(autouse=True)
def _clean_module_state() -> Any:
    mc._AUDI_MARKET_CACHE.clear()
    mc._AUTH0_MARKETS_NOTED.clear()
    yield
    mc._AUDI_MARKET_CACHE.clear()
    mc._AUTH0_MARKETS_NOTED.clear()


_DISCOVERY = (
    "https://emea.bff.cariad.digital/auth/v1/idk/oidc/openid-configuration"
)


async def test_fetch_sends_the_app_version_and_the_app_user_agent() -> None:
    session = _Session({"idkLoginServiceConfigurationURLProduction": _DISCOVERY})

    await mc.fetch_audi_market_config(session, country="ch", language="DE")

    (url, headers), = session.calls
    assert url == (
        "https://content.app.my.audi.com/service/mobileapp/configurations/"
        f"market/CH/de?v={MYAUDI_APP_VERSION}"
    )
    assert headers["User-Agent"] == MYAUDI_USER_AGENT


async def test_watch_keys_are_read_as_strings_next_to_the_discovery_url() -> None:
    session = _Session({
        "idkLoginServiceConfigurationURLProduction": _DISCOVERY,
        "marketSupportsAuth0": False,
        "marketSupportsAndroidClientValidation": True,
        "auth0MigrationNotice": "Inform",
        "webViewAuthenticationProvider": "idk",
        "marketSupportsMQTTPushes": True,  # not a watch key: ignored
    })

    cfg = await mc.fetch_audi_market_config(session)

    assert cfg == {
        "idkLoginServiceConfigurationURLProduction": _DISCOVERY,
        "marketSupportsAuth0": "false",
        "marketSupportsAndroidClientValidation": "true",
        "auth0MigrationNotice": "Inform",
        "webViewAuthenticationProvider": "idk",
    }
    # The token-URL derivation reads the same dict and must not be disturbed.
    assert mc.derive_token_url_from_market_config(cfg) is not None


async def test_auth0_market_is_reported_once(caplog: pytest.LogCaptureFixture) -> None:
    session = _Session({"marketSupportsAuth0": True})
    caplog.set_level(logging.INFO, logger=mc.__name__)

    await mc.fetch_audi_market_config(session, force_refresh=True)
    await mc.fetch_audi_market_config(session, force_refresh=True)

    hits = [r for r in caplog.records if "marketSupportsAuth0 is set" in r.getMessage()]
    assert len(hits) == 1
    assert hits[0].levelno == logging.INFO


async def test_no_auth0_line_while_the_market_stays_on_identitykit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=mc.__name__)

    # Absent (DE and CH on 2026-11-18) and explicitly false.
    await mc.fetch_audi_market_config(_Session({}), force_refresh=True)
    await mc.fetch_audi_market_config(
        _Session({"marketSupportsAuth0": False}), force_refresh=True,
    )

    assert not [r for r in caplog.records if "marketSupportsAuth0 is set" in r.getMessage()]


async def test_a_flip_of_a_watch_key_is_logged_as_a_change(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=mc.__name__)
    await mc.fetch_audi_market_config(
        _Session({"auth0MigrationNotice": "None"}), force_refresh=True,
    )

    await mc.fetch_audi_market_config(
        _Session({"auth0MigrationNotice": "ForcedLogout"}), force_refresh=True,
    )

    changed = [r.getMessage() for r in caplog.records if "CHANGED" in r.getMessage()]
    assert changed == [
        "Audi market-config (DE/de): auth0MigrationNotice CHANGED — None → ForcedLogout"
    ]
