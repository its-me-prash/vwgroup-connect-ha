# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#966 / #632 — the supplementary vw.de channel now persists its rotated cookies.

The sole-mode website-authproxy has persisted its rotated cookies since v2.14.3
(_persist_website_cookies + get_website_proxy_cookies). The SUPPLEMENTARY slot
never did: get_website_proxy_cookies reads _website_proxy, _persist_website_cookies
is gated on the sole-mode CONF_WEBSITE_AUTHPROXY key, and
CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES was only ever written once at OTP setup.

So the arm ran refresh() (which rotates the jar) every poll, but the entry kept
the original OTP cookies forever. On the next restart the arm replayed those
stale cookies, refresh() bounced to the login page, and the channel reported
"SSO session expired — full re-login required" even though a live session had
existed moments earlier. This is exactly the loop the reporter of #966 (and
shaarkys in #632, since 2026-07-09) was stuck in.

The fix is the twin of the sole-mode path, scoped to its own storage key so the
two never clobber each other.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.const import (
    CONF_SUPPLEMENTARY_AUTHPROXY,
    CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
)


# ── the export side (base client) ───────────────────────────────────────────

class _FakeConnector:
    def __init__(self, cookies):
        self._cookies = cookies

    def export_cookies(self):
        return self._cookies


class TestSupplementaryCookieExport:
    def _client(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

        c = VWEUClient.__new__(VWEUClient)
        c._website_proxy = None
        c._supplementary_authproxy = None
        return c

    def test_exports_the_supplementary_connector_not_the_sole_mode_one(self) -> None:
        c = self._client()
        # sole-mode connector present, supplementary present with DIFFERENT cookies
        c._website_proxy = _FakeConnector([{"name": "sole", "value": "x"}])
        c._supplementary_authproxy = _FakeConnector([{"name": "supp", "value": "y"}])
        got = c.get_supplementary_proxy_cookies()
        assert got == [{"name": "supp", "value": "y"}], (
            "must read _supplementary_authproxy, not _website_proxy"
        )

    def test_unarmed_returns_empty(self) -> None:
        c = self._client()
        assert c.get_supplementary_proxy_cookies() == []

    def test_export_failure_is_soft(self) -> None:
        class _Boom:
            def export_cookies(self):
                raise RuntimeError("jar gone")

        c = self._client()
        c._supplementary_authproxy = _Boom()
        assert c.get_supplementary_proxy_cookies() == []


# ── the persist side (coordinator) ──────────────────────────────────────────

class TestSupplementaryCookiePersist:
    def _coord(self, *, entry_data, exported):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        c = VagConnectCoordinator.__new__(VagConnectCoordinator)
        c.entry = MagicMock()
        c.entry.data = dict(entry_data)
        c.hass = MagicMock()
        c.hass.config_entries = MagicMock()
        client = MagicMock()
        client.get_supplementary_proxy_cookies = MagicMock(return_value=exported)
        c._cariad_client = client
        return c

    def _updated_data(self, c):
        call = c.hass.config_entries.async_update_entry.call_args
        return call.kwargs["data"] if call else None

    def test_writes_rotated_cookies_back(self) -> None:
        c = self._coord(
            entry_data={
                CONF_SUPPLEMENTARY_AUTHPROXY: True,
                CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: [{"name": "old", "value": "1"}],
            },
            exported=[{"name": "new", "value": "2"}],
        )
        c._persist_supplementary_cookies()
        data = self._updated_data(c)
        assert data is not None
        assert data[CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES] == [{"name": "new", "value": "2"}]

    def test_noop_when_unchanged(self) -> None:
        same = [{"name": "same", "value": "1"}]
        c = self._coord(
            entry_data={
                CONF_SUPPLEMENTARY_AUTHPROXY: True,
                CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: same,
            },
            exported=list(same),
        )
        c._persist_supplementary_cookies()
        c.hass.config_entries.async_update_entry.assert_not_called()

    def test_noop_when_not_a_supplementary_entry(self) -> None:
        c = self._coord(
            entry_data={CONF_SUPPLEMENTARY_AUTHPROXY: False},
            exported=[{"name": "new", "value": "2"}],
        )
        c._persist_supplementary_cookies()
        c.hass.config_entries.async_update_entry.assert_not_called()

    def test_noop_on_empty_export(self) -> None:
        c = self._coord(
            entry_data={
                CONF_SUPPLEMENTARY_AUTHPROXY: True,
                CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: [{"name": "old", "value": "1"}],
            },
            exported=[],
        )
        c._persist_supplementary_cookies()
        c.hass.config_entries.async_update_entry.assert_not_called()

    def test_does_not_touch_the_sole_mode_key(self) -> None:
        from custom_components.vag_connect.const import CONF_WEBSITE_COOKIES

        c = self._coord(
            entry_data={
                CONF_SUPPLEMENTARY_AUTHPROXY: True,
                CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES: [{"name": "old", "value": "1"}],
                CONF_WEBSITE_COOKIES: [{"name": "sole", "value": "keep"}],
            },
            exported=[{"name": "new", "value": "2"}],
        )
        c._persist_supplementary_cookies()
        data = self._updated_data(c)
        # sole-mode cookies untouched
        assert data[CONF_WEBSITE_COOKIES] == [{"name": "sole", "value": "keep"}]
