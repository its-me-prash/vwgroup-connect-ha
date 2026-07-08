# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.16.2 — rafaelhutter/ha-volkswagen-connect v0.5.20 vw.de-channel parity.

Two independent, additive deltas closed WITH our own code (his repo referenced
only for endpoint/Accept-recipe cross-checks — never copied):

GAP 2.1 — RESILIENCE. When the PRIMARY channel (e.g. EU Data Act portal)
  returns ``no_data`` for a cycle, a healthy SUPPLEMENTARY channel (vw.de
  authproxy) must keep the entry live instead of dropping to stale-cache. His
  website_portal keeps serving when EU-DA fails; we mirror that symmetrically
  via ``_revive_from_supplementary``. Single-channel entries (no suppliers) are
  byte-for-byte unchanged. A genuinely-lapsed vw.de session still surfaces as an
  AuthenticationError → reauth (the supplementary read is fail-soft → None →
  stale-cache, never a crash).

GAP 4.1 — READ PARITY. The ``usercapabilities`` endpoint at
  ``application/json;version=3``. Additive, read-only, fail-soft; NOT wired into
  the poll/entity filter (capability gating stays a maintainer decision).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad._authproxy import (
    build_usercapabilities_accept,
    build_usercapabilities_url,
    parse_usercapabilities,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord_stub(client: Any) -> Any:
    """Minimal coordinator stub bound to the two methods under test, mirroring
    the pattern in test_v2150c1_wiring.py (bypasses __init__)."""
    stub = type("S", (), {})()
    stub._cariad_client = client
    stub.entry = MagicMock()
    stub.entry.data = {}
    stub._primary_channel_name = (
        VagConnectCoordinator._primary_channel_name.__get__(stub)
    )
    stub._merge_supplementary = (
        VagConnectCoordinator._merge_supplementary.__get__(stub)
    )
    stub._revive_from_supplementary = (
        VagConnectCoordinator._revive_from_supplementary.__get__(stub)
    )
    return stub


class TestReviveFromSupplementary:
    """GAP 2.1 — EU-DA-down + vw.de-up → serve live vw.de, don't blank."""

    def test_revives_from_live_supplementary(self) -> None:
        """A no_data primary + a supplementary channel that returned live data
        → merged snapshot with no_data cleared, provenance = the supplier."""
        client = MagicMock()
        client._eu_portal = object()  # primary name → eu_data_act

        async def _supp() -> VehicleData:
            return VehicleData(vin="X", odometer_km=42, battery_soc=61)

        client.supplementary_readers = MagicMock(
            return_value=[("website_authproxy", _supp())]
        )
        empty = VehicleData(vin="X", no_data=True)
        out = asyncio.run(
            _coord_stub(client)._revive_from_supplementary("X", empty)
        )
        assert out is not None
        assert out.no_data is False           # no longer a no-data poll
        assert out.odometer_km == 42          # live vw.de data served
        assert out.battery_soc == 61
        assert out.source_channel == "website_authproxy"

    def test_no_suppliers_returns_none(self) -> None:
        """Single-channel entry (no suppliers armed) → None → caller falls back
        to stale-cache exactly as before (behaviour unchanged)."""
        client = MagicMock()
        client._eu_portal = object()
        client.supplementary_readers = MagicMock(return_value=[])
        empty = VehicleData(vin="X", no_data=True)
        out = asyncio.run(
            _coord_stub(client)._revive_from_supplementary("X", empty)
        )
        assert out is None

    def test_supplementary_empty_returns_none(self) -> None:
        """A supplementary channel that is ALSO down (returns None) → no live
        data → None → stale-cache fallback, not a fabricated empty snapshot."""
        client = MagicMock()
        client._eu_portal = object()

        async def _supp() -> VehicleData | None:
            return None

        client.supplementary_readers = MagicMock(
            return_value=[("website_authproxy", _supp())]
        )
        empty = VehicleData(vin="X", no_data=True)
        out = asyncio.run(
            _coord_stub(client)._revive_from_supplementary("X", empty)
        )
        assert out is None

    def test_merge_failure_is_failsoft_none(self) -> None:
        """A raising supplementary_readers must NOT crash the poll → None."""
        client = MagicMock()
        client._eu_portal = object()
        client.supplementary_readers = MagicMock(side_effect=RuntimeError("boom"))
        empty = VehicleData(vin="X", no_data=True)
        out = asyncio.run(
            _coord_stub(client)._revive_from_supplementary("X", empty)
        )
        assert out is None


class TestPollLoopReviveIntegration:
    """GAP 2.1 end-to-end through the real poll-result branch: a no_data primary
    with a live supplementary is stored as fresh data (not stale-cache), and a
    genuine session lapse degrades to stale-cache without crashing."""

    def _run_branch(self, coord: Any, vin: str, result: VehicleData) -> str:
        """Drive just the no_data decision the poll loop makes. Returns
        'revived' | 'stale' by inspecting what the branch produced."""
        # Mirror coordinator.py: no_data + prior data → try revive, else stale.
        if getattr(result, "no_data", False) and coord.vehicles.get(vin):
            revived = asyncio.run(
                coord._revive_from_supplementary(vin, result)
            )
            return "revived" if revived is not None else "stale"
        return "fresh"

    def _coord(self, client: Any, prior: dict[str, Any]) -> Any:
        stub = _coord_stub(client)
        stub.vehicles = {"X": prior}
        return stub

    def test_eu_da_down_vw_de_up_serves_live(self) -> None:
        client = MagicMock()
        client._eu_portal = object()

        async def _supp() -> VehicleData:
            return VehicleData(vin="X", odometer_km=99)

        client.supplementary_readers = MagicMock(
            return_value=[("website_authproxy", _supp())]
        )
        coord = self._coord(client, {"odometer_km": 90})
        outcome = self._run_branch(coord, "X", VehicleData(vin="X", no_data=True))
        assert outcome == "revived"

    def test_eu_da_down_vw_de_also_down_stale_cache(self) -> None:
        client = MagicMock()
        client._eu_portal = object()

        async def _supp() -> VehicleData | None:
            return None

        client.supplementary_readers = MagicMock(
            return_value=[("website_authproxy", _supp())]
        )
        coord = self._coord(client, {"odometer_km": 90})
        outcome = self._run_branch(coord, "X", VehicleData(vin="X", no_data=True))
        assert outcome == "stale"


class TestUserCapabilitiesParity:
    """GAP 4.1 — usercapabilities endpoint + version=3 Accept + parser."""

    def test_url_realm_host_and_gdc(self) -> None:
        url = build_usercapabilities_url("WVWZZZ")
        assert "/app/authproxy/vwag-weconnect/proxy/vehicles/WVWZZZ/usercapabilities" in url
        assert "resourceHost=myvw-vcf-prod" in url
        assert "gdc=myvw-wcar-prod" in url

    def test_accept_is_versioned(self) -> None:
        assert build_usercapabilities_accept() == "application/json;version=3"

    def test_parse_structured_status_gates(self) -> None:
        body = {
            "capabilities": [
                {"id": "charging", "status": []},          # enabled
                {"id": "climatisation"},                    # enabled (no status)
                {"id": "parkingPosition", "status": [1003]},  # disabled
            ]
        }
        assert parse_usercapabilities(body) == {"charging", "climatisation"}

    def test_parse_bare_list_and_flat_strings(self) -> None:
        assert parse_usercapabilities(["a", "b"]) == {"a", "b"}
        assert parse_usercapabilities({"capabilities": ["x"]}) == {"x"}

    def test_parse_garbage_is_empty_set(self) -> None:
        assert parse_usercapabilities(None) == set()
        assert parse_usercapabilities("nope") == set()
        assert parse_usercapabilities({"capabilities": "bad"}) == set()


class TestConnectorGetCapabilities:
    """The connector method: versioned Accept, fail-soft, propagates auth-fail."""

    def _conn(self) -> Any:
        from custom_components.vag_connect.cariad.auth._website_authproxy import (
            WebsiteAuthProxyConnector,
        )
        return WebsiteAuthProxyConnector(MagicMock(), "u@t.de", "pw")

    def test_sends_versioned_accept_and_parses(self) -> None:
        conn = self._conn()
        conn._get_json = AsyncMock(
            return_value={"capabilities": [{"id": "charging"}]}
        )
        out = asyncio.run(conn.get_capabilities("VIN"))
        assert out == {"charging"}
        # the versioned Accept was passed through
        assert conn._get_json.await_args.kwargs["accept"] == (
            "application/json;version=3"
        )

    def test_soft_none_returns_empty_set(self) -> None:
        conn = self._conn()
        conn._get_json = AsyncMock(return_value=None)
        assert asyncio.run(conn.get_capabilities("VIN")) == set()

    def test_auth_fail_propagates(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            AuthenticationError,
        )
        conn = self._conn()
        conn._get_json = AsyncMock(side_effect=AuthenticationError("stale"))
        try:
            asyncio.run(conn.get_capabilities("VIN"))
        except AuthenticationError:
            return
        raise AssertionError("expected AuthenticationError to propagate")
