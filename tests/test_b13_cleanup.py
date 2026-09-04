# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b13 — HA-near clean-up: PARALLEL_UPDATES, device-lookup deprecation guard,
and the redacted 401 auth-state debug capture (#1340).
"""
from __future__ import annotations

import importlib
import logging

from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.const import DOMAIN


# ── platinum parallel-updates rule is declared at MODULE level on every platform

_PLATFORMS = [
    "binary_sensor", "button", "calendar", "climate", "device_tracker", "event",
    "image", "lock", "number", "select", "sensor", "switch", "time", "update",
]


@pytest.mark.parametrize("platform", _PLATFORMS)
def test_platform_declares_module_level_parallel_updates(platform: str) -> None:
    # HA reads PARALLEL_UPDATES as a MODULE attribute; an entity attr is a no-op.
    # Guards the platinum quality-scale rule being actually in effect.
    mod = importlib.import_module(f"custom_components.vag_connect.{platform}")
    assert getattr(mod, "PARALLEL_UPDATES", None) == 0


# ── device lookup uses the non-deprecated entry-scoped API when available ─────

class _Coord:
    """Bind the real coordinator method onto a tiny stub carrying self.entry."""

    def __init__(self) -> None:
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        self._lookup = VagConnectCoordinator._lookup_own_device.__get__(self)
        self.entry = MagicMock()
        self.entry.entry_id = "e1"


def test_lookup_uses_by_identifier_when_present() -> None:
    coord = _Coord()
    registry = MagicMock(spec=["async_get_device_by_identifier"])
    registry.async_get_device_by_identifier.return_value = "DEV"
    out = coord._lookup(registry, "WVWZZZ1KZAM000001")
    # entry-scoped call: single TUPLE identifier + the config entry id
    registry.async_get_device_by_identifier.assert_called_once_with(
        (DOMAIN, "WVWZZZ1KZAM000001"), "e1"
    )
    assert out == "DEV"


def test_lookup_falls_back_on_old_core() -> None:
    coord = _Coord()
    # a pre-2026.8 core has no async_get_device_by_identifier
    registry = MagicMock(spec=["async_get_device"])
    registry.async_get_device.return_value = "OLD"
    out = coord._lookup(registry, "WVWZZZ1KZAM000001")
    registry.async_get_device.assert_called_once_with(
        identifiers={(DOMAIN, "WVWZZZ1KZAM000001")}
    )
    assert out == "OLD"


# ── the 401 auth-state debug capture is safe + redacted ───────────────────────

class _Cookie:
    def __init__(self, key: str, domain: str, value: str) -> None:
        self.key = key
        self.value = value
        self._d = {"domain": domain}

    def get(self, k: str, default=None):
        return self._d.get(k, default)


def _connector(cookies, bearer):
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )
    c = EUDataActConnector.__new__(EUDataActConnector)
    c._bearer = bearer  # type: ignore[attr-defined]
    sess = MagicMock()
    sess.cookie_jar = cookies
    c._session = sess  # type: ignore[attr-defined]
    return c


def test_401_dump_noop_when_debug_off(monkeypatch) -> None:
    from custom_components.vag_connect.cariad.auth import _eu_data_act
    # debug off → no-op. monkeypatch (auto-restored) instead of mutating the
    # module logger's level globally, which would pollute other tests' caplog.
    monkeypatch.setattr(_eu_data_act._LOGGER, "isEnabledFor", lambda _lvl: False)
    # a cookie jar that WOULD raise if touched — proves the guard returns early
    sess = MagicMock()
    type(sess).cookie_jar = property(
        lambda self: (_ for _ in ()).throw(AssertionError("touched jar"))
    )
    c = _eu_data_act.EUDataActConnector.__new__(_eu_data_act.EUDataActConnector)
    c._bearer = "tok"  # type: ignore[attr-defined]
    c._session = sess  # type: ignore[attr-defined]
    resp = MagicMock()
    resp.headers = {"WWW-Authenticate": "Bearer"}
    # must not raise (and must not read the cookie jar)
    c._debug_dump_auth_state_on_401("https://p/proxy_api/x?y=1", {"Authorization": "x"}, resp)


def test_401_dump_logs_redacted_at_debug(caplog) -> None:
    from custom_components.vag_connect.cariad.auth import _eu_data_act
    c = _connector([_Cookie("SESSID", "portal.example", "SUPERSECRET")], bearer="tok")
    resp = MagicMock()
    resp.headers = {"WWW-Authenticate": "Bearer realm=x", "Set-Cookie": "a=b"}
    with caplog.at_level(logging.DEBUG, logger=_eu_data_act._LOGGER.name):
        c._debug_dump_auth_state_on_401(
            "https://p/proxy_api/consent/me/vehicles?viewPosition=FRONT_LEFT",
            {"Authorization": "Bearer tok"},
            resp,
        )
    blob = caplog.text
    assert "mode=bearer" in blob
    assert "sent_authorization=True" in blob
    assert "SESSID@portal.example" in blob     # cookie NAME + domain surfaced
    assert "SUPERSECRET" not in blob           # cookie VALUE never leaked
    assert "resp_set_cookie=True" in blob
    # the query string is stripped from the logged URL
    assert "viewPosition" not in blob
