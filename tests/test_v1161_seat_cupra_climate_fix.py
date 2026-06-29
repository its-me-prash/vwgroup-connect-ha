# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.16.1 PATCH — SEAT/CUPRA climate endpoint fix (#53)
+ #122 SEAT scout-paths registration.

A) command_start_climate / stop_climate use ``/v2/.../climatisation/start``
   path-suffix variant first (pycupra-verified) with v1/v2 fallback to
   the legacy bare endpoint with body action on 404.
B) #122 — ``engines.primary`` + ``engines.primary.*`` wildcard
   registered in EXPECTED_KEYS["cupra"]["mycar"] (SEAT inherits via
   table alias).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) #53 — SEAT/CUPRA climate URL fix
# ─────────────────────────────────────────────────────────────────────────────


class TestClimateEndpointFix:
    """v1.16.1 (#53 Gerhard CUPRA Born) — climate start/stop use the
    pycupra-verified path-suffix URL with defensive 404 fallback."""

    def _client(self):
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        client = SeatCupraClient.__new__(SeatCupraClient)
        client._post = AsyncMock(return_value=None)
        return client

    def test_start_uses_path_suffix_first(self):
        client = self._client()
        asyncio.run(
            client.command_start_climate("VINX")
        )
        url = client._post.await_args.args[0]
        assert url.endswith("/v2/vehicles/VINX/climatisation/start"), url
        # Body should be empty {} since action is in the path
        kwargs = client._post.await_args.kwargs
        assert kwargs["json"] == {}

    def test_stop_uses_path_suffix_first(self):
        client = self._client()
        asyncio.run(
            client.command_stop_climate("VINX")
        )
        url = client._post.await_args.args[0]
        assert url.endswith("/v2/vehicles/VINX/climatisation/stop"), url

    def test_falls_back_to_legacy_on_404(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = self._client()
        # First call (path-suffix) raises 404, second call (legacy) succeeds
        client._post = AsyncMock(side_effect=[
            APIError(404, "primary-url", "No static resource"),
            None,
        ])
        asyncio.run(
            client.command_start_climate("VINX")
        )
        # Two calls made: primary 404, fallback to legacy
        assert client._post.await_count == 2
        legacy_url = client._post.await_args_list[1].args[0]
        assert legacy_url.endswith("/v2/vehicles/VINX/climatisation"), legacy_url
        assert legacy_url.endswith("climatisation"), "fallback URL should NOT have /start suffix"
        legacy_body = client._post.await_args_list[1].kwargs["json"]
        assert legacy_body == {"action": "start"}

    def test_non_404_error_propagates_no_fallback(self):
        """403 / 500 / etc. must propagate so Phase 2 records the failure
        properly. Only 404 triggers the legacy URL fallback."""
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = self._client()
        client._post = AsyncMock(side_effect=APIError(403, "primary-url", "forbidden"))
        with pytest.raises(APIError) as exc_info:
            asyncio.run(
                client.command_start_climate("VINX")
            )
        assert exc_info.value.status == 403
        # No second call — fallback only kicks in on 404
        assert client._post.await_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# B) #122 — SEAT scout-paths registration
# ─────────────────────────────────────────────────────────────────────────────


class TestScoutPathsSeat:
    """v1.16.1 (#122 r1150gs SEAT Scout-Report 2026-05-02) —
    ``engines.primary`` + wildcard registered in EXPECTED_KEYS["cupra"]["mycar"]
    (SEAT inherits via the table alias at the bottom of _unexpected_keys.py)."""

    def test_engines_primary_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import EXPECTED_KEYS
        cupra_mycar = EXPECTED_KEYS["cupra"]["mycar"]
        assert "engines.primary" in cupra_mycar
        assert "engines.primary.*" in cupra_mycar

    def test_seat_inherits_via_alias(self):
        from custom_components.vag_connect.cariad._unexpected_keys import EXPECTED_KEYS
        # SEAT should resolve the same paths through its alias to "cupra"
        seat_mycar = EXPECTED_KEYS["seat"]["mycar"]
        assert "engines.primary" in seat_mycar
        assert "engines.primary.*" in seat_mycar
