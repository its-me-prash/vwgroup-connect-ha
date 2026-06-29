# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b1/C1 wiring — client supplementary-channel readers + coordinator merge glue.
Single-channel (no supplementary armed) stays byte-for-byte unchanged; commands
and get_status are never touched."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _client() -> VWEUClient:
    return VWEUClient(MagicMock(), "u@t.de", "pw")


class TestSupplementaryReaders:
    def test_empty_when_not_armed(self) -> None:
        assert _client().supplementary_readers("VIN") == []

    def test_lists_armed_authproxy(self) -> None:
        c = _client()
        conn = MagicMock()
        conn.get_vehicle_data = AsyncMock(
            return_value=VehicleData(vin="VIN", odometer_km=5)
        )
        c._supplementary_authproxy = conn
        readers = c.supplementary_readers("VIN")
        assert len(readers) == 1
        assert readers[0][0] == "website_authproxy"
        assert asyncio.run(readers[0][1]).odometer_km == 5

    def test_read_authproxy_reauth_retry(self) -> None:
        c = _client()
        conn = MagicMock()
        conn.get_vehicle_data = AsyncMock(
            side_effect=[AuthenticationError("stale"), VehicleData(vin="VIN", odometer_km=7)]
        )
        conn.refresh = AsyncMock()
        res = asyncio.run(c._read_authproxy(conn, "VIN"))
        assert res is not None and res.odometer_km == 7
        conn.refresh.assert_awaited_once()

    def test_read_authproxy_error_is_none(self) -> None:
        c = _client()
        conn = MagicMock()
        conn.get_vehicle_data = AsyncMock(side_effect=RuntimeError("boom"))
        assert asyncio.run(c._read_authproxy(conn, "VIN")) is None


_COOKIE = [{"name": "auth0", "value": "x", "domain": "identity.vwgroup.io"}]
_CONN_PATH = (
    "custom_components.vag_connect.cariad.auth._website_authproxy"
    ".WebsiteAuthProxyConnector"
)


class TestArmSupplementary:
    """The dedicated-session fix: arming must use an ISOLATED session (never the
    shared brand session) so vw.de cookies can't clobber a cookie-based primary
    (EU Data Act portal) on the identity.vwgroup.io IDP host."""

    def test_no_cookies_returns_false(self) -> None:
        c = _client()
        assert asyncio.run(c.arm_supplementary_authproxy(None)) is False
        assert asyncio.run(c.arm_supplementary_authproxy([])) is False

    def test_silent_refresh_arms_with_dedicated_session(self) -> None:
        # b9: resume via the prompt=none silent refresh (re-mints the portal
        # session from the SSO cookie), NOT a /relations probe. OTP-free.
        c = _client()
        sess = MagicMock()
        sess.close = AsyncMock()
        conn = MagicMock()
        conn.import_cookies = MagicMock()
        conn.refresh = AsyncMock()  # prompt=none silent resume succeeds
        conn.begin_login = AsyncMock()
        with patch("aiohttp.ClientSession", return_value=sess), \
             patch(_CONN_PATH, return_value=conn) as ctor:
            ok = asyncio.run(c.arm_supplementary_authproxy(_COOKIE))
        assert ok is True
        assert c._supplementary_authproxy is conn
        assert c._supplementary_session is sess
        # connector built on the DEDICATED session, not the shared one
        assert ctor.call_args.args[0] is sess
        assert ctor.call_args.args[0] is not c._session
        conn.refresh.assert_awaited_once()
        sess.close.assert_not_awaited()
        conn.begin_login.assert_not_awaited()  # no OTP path on resume

    def test_dead_sso_repairs_without_otp(self) -> None:
        # b9: refresh() raises on a dead SSO (prompt=none bounced to /u/login).
        # It NEVER calls begin_login, so no OTP-email storm — just flag re-add.
        c = _client()
        sess = MagicMock()
        sess.close = AsyncMock()
        conn = MagicMock()
        conn.import_cookies = MagicMock()
        conn.refresh = AsyncMock(side_effect=AuthenticationError("SSO expired"))
        conn.begin_login = AsyncMock()
        with patch("aiohttp.ClientSession", return_value=sess), \
             patch(_CONN_PATH, return_value=conn):
            ok = asyncio.run(c.arm_supplementary_authproxy(_COOKIE))
        assert ok is False
        assert c._supplementary_authproxy is None
        assert c._supplementary_needs_reauth is True
        conn.begin_login.assert_not_awaited()  # no OTP-email storm
        sess.close.assert_awaited()  # isolated session closed, no leak

    def test_scan_feeds_raw_unmapped_into_scout(self) -> None:
        # b6: the portal's unmapped raw fields are surfaced in the SAME Scout
        # findings buffer (merge raw-discovery with the Scout notification).
        stub = type("S", (), {})()
        stub._cariad_client = MagicMock()
        stub._cariad_client.last_raw_responses = {}
        stub.entry = MagicMock()
        stub.entry.data = {"brand": "volkswagen"}
        stub.unexpected_findings = {}
        VagConnectCoordinator._scan_for_unexpected_keys(
            stub, "X", {"raw_unmapped_fields": {"foo_bar": "42", "baz": "x"}}
        )
        findings = stub.unexpected_findings["X"]
        assert "eu_data_act.foo_bar" in findings
        assert "eu_data_act.baz" in findings
        assert findings["eu_data_act.foo_bar"].endpoint == "eu_data_act"

    def test_portal_readers_include_portal(self) -> None:
        c = _client()
        conn = MagicMock()
        conn.get_vehicle_data = AsyncMock(return_value=VehicleData(vin="X", battery_soc=80))
        c._supplementary_eu_portal = conn
        readers = c.supplementary_readers("X")
        names = [r[0] for r in readers]
        assert "eu_data_act" in names
        for _name, coro in readers:  # consume coroutines (no un-awaited warning)
            asyncio.run(coro)

    def test_arm_portal_success_stores_creds(self) -> None:
        c = _client()
        conn = MagicMock()
        conn.login = AsyncMock()
        with patch(
            "custom_components.vag_connect.cariad.auth._eu_data_act.EUDataActConnector",
            return_value=conn,
        ):
            ok = asyncio.run(c.arm_supplementary_eu_portal("u@t.de", "pw"))
        assert ok is True
        assert c._supplementary_eu_portal is conn
        assert c._supplementary_eu_portal_creds == ("u@t.de", "pw")

    def test_arm_portal_skipped_when_portal_is_primary(self) -> None:
        c = _client()
        c._eu_portal = object()  # portal already the primary → don't self-collide
        ok = asyncio.run(c.arm_supplementary_eu_portal("u@t.de", "pw"))
        assert ok is False
        assert c._supplementary_eu_portal is None

    def test_arm_portal_login_failure_is_failsoft(self) -> None:
        c = _client()
        conn = MagicMock()
        conn.login = AsyncMock(side_effect=RuntimeError("boom"))
        with patch(
            "custom_components.vag_connect.cariad.auth._eu_data_act.EUDataActConnector",
            return_value=conn,
        ):
            ok = asyncio.run(c.arm_supplementary_eu_portal("u@t.de", "pw"))
        assert ok is False
        assert c._supplementary_eu_portal is None

    def test_read_portal_relogins_on_auth_error(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        c = _client()
        c._supplementary_eu_portal_creds = ("u@t.de", "pw")
        conn = MagicMock()
        conn.get_vehicle_data = AsyncMock(
            side_effect=[AuthenticationError("stale"), VehicleData(vin="X", battery_soc=55)]
        )
        conn.login = AsyncMock()
        res = asyncio.run(c._read_eu_portal(conn, "X"))
        assert res is not None and res.battery_soc == 55
        conn.login.assert_awaited_once()

    def test_close_supplementary(self) -> None:
        c = _client()
        sess = MagicMock()
        sess.close = AsyncMock()
        c._supplementary_session = sess
        c._supplementary_authproxy = MagicMock()
        asyncio.run(c.close_supplementary())
        assert c._supplementary_session is None
        assert c._supplementary_authproxy is None
        sess.close.assert_awaited()


def _coord_stub(client: Any, entry_data: dict[str, Any]) -> Any:
    stub = type("S", (), {})()
    stub._cariad_client = client
    stub.entry = MagicMock()
    stub.entry.data = entry_data
    stub._primary_channel_name = VagConnectCoordinator._primary_channel_name.__get__(stub)
    return stub


class TestPrimaryChannelName:
    def test_eu_portal(self) -> None:
        client = MagicMock()
        client._eu_portal = object()
        assert _coord_stub(client, {})._primary_channel_name() == "eu_data_act"

    def test_website(self) -> None:
        from custom_components.vag_connect.const import CONF_WEBSITE_AUTHPROXY
        stub = _coord_stub(MagicMock(), {CONF_WEBSITE_AUTHPROXY: True})
        assert stub._primary_channel_name() == "website_authproxy"

    def test_mbb(self) -> None:
        client = MagicMock()
        client._eu_portal = None
        stub = _coord_stub(client, {"dag_initial_tokens": {"strategy": "mbb"}})
        assert stub._primary_channel_name() == "mbb"


class TestMergeSupplementary:
    def test_no_readers_attr_returns_primary(self) -> None:
        stub = _coord_stub(MagicMock(spec=[]), {})
        primary = VehicleData(vin="X", battery_soc=80)
        out = asyncio.run(VagConnectCoordinator._merge_supplementary(stub, "X", primary))
        assert out is primary

    def test_empty_readers_returns_primary(self) -> None:
        client = MagicMock()
        client.supplementary_readers = MagicMock(return_value=[])
        primary = VehicleData(vin="X", battery_soc=80)
        out = asyncio.run(
            VagConnectCoordinator._merge_supplementary(_coord_stub(client, {}), "X", primary)
        )
        assert out is primary

    def test_merges_supplementary_onto_primary(self) -> None:
        client = MagicMock()
        client._eu_portal = object()  # primary name → eu_data_act

        async def _supp() -> VehicleData:
            return VehicleData(vin="X", odometer_km=12345)

        client.supplementary_readers = MagicMock(
            return_value=[("website_authproxy", _supp())]
        )
        primary = VehicleData(vin="X", battery_soc=80)
        out = asyncio.run(
            VagConnectCoordinator._merge_supplementary(_coord_stub(client, {}), "X", primary)
        )
        assert out.battery_soc == 80          # primary kept
        assert out.odometer_km == 12345       # supplementary filled the gap
        assert out.source_channel == "eu_data_act+website_authproxy"
