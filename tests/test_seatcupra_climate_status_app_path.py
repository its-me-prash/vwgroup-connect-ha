# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SEAT/CUPRA climate state: fall back to the app 3.0.2 path on a legacy 404.

The 3.0.2 app reads ``GET v1/vehicles/{vin}/climate/status``; the legacy
``.../climatisation/status`` is gone from the app, and whether the server still
serves it is unmeasured. The legacy path stays first. Only its 404 makes
``get_status`` read the app path, and only a payload with a readable state is
used. Read-only: SEAT/CUPRA commands stay switched off.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.exceptions import APIError

_BASE = "https://ola.prod.code.seat.cloud.vwgroup.com"
_VIN = "TESTVIN00CLIM001"
_LEGACY = f"{_BASE}/v1/vehicles/{_VIN}/climatisation/status"
_APP = f"{_BASE}/v1/vehicles/{_VIN}/climate/status"

_ON = {"climatisationStatus": {"climatisationState": "heating"}}


def _client(routes):
    """get_status client; ``routes`` maps a URL to a payload or an exception."""
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    client = SeatCupraClient(MagicMock(), "cupra", "u@t.de", "pw")
    client._user_id = "uid-123"
    client._get_capabilities_count = AsyncMock(return_value=None)
    client._get_from_charging_host = AsyncMock(return_value={})
    calls: list[str] = []

    async def _get(url, **kwargs):
        calls.append(url)
        out = routes.get(url, {})
        if isinstance(out, BaseException):
            raise out
        return out

    client._get = AsyncMock(side_effect=_get)
    client.calls = calls
    return client


def _404(url):
    return APIError(404, url, "No static resource")


class TestClimateStatusAppPathFallback:
    def test_legacy_answers_app_path_not_called(self):
        client = _client({_LEGACY: _ON, _APP: {"climatisationStatus": {"climatisationState": "off"}}})
        data = asyncio.run(client.get_status(_VIN))
        assert _APP not in client.calls
        assert data.climatisation_state == "heating"
        assert data.climatisation_active is True

    def test_legacy_404_reads_and_maps_app_path(self):
        client = _client({_LEGACY: _404(_LEGACY), _APP: _ON})
        data = asyncio.run(client.get_status(_VIN))
        assert client.calls.count(_APP) == 1
        assert data.climatisation_state == "heating"
        assert data.climatisation_active is True
        assert client.last_raw_responses["climatisation"] == _ON
        assert client.parser_stats["climatisation"]["success"] == 1

    def test_both_404_is_today_state_without_error(self):
        client = _client({_LEGACY: _404(_LEGACY), _APP: _404(_APP)})
        data = asyncio.run(client.get_status(_VIN))
        assert client.calls.count(_APP) == 1
        assert data.climatisation_state is None
        assert data.climatisation_active is None
        assert "climatisation" not in client.last_raw_responses
        assert client.parser_stats["climatisation"]["fail"] == 1

    def test_non_404_legacy_error_does_not_try_app_path(self):
        client = _client({_LEGACY: APIError(500, _LEGACY, "boom")})
        asyncio.run(client.get_status(_VIN))
        assert _APP not in client.calls

    def test_app_payload_without_known_state_is_ignored(self):
        # unknown shape: not guessed, and not reported as "climate off"
        client = _client({_LEGACY: _404(_LEGACY), _APP: {"somethingNew": {"x": 1}}})
        data = asyncio.run(client.get_status(_VIN))
        assert data.climatisation_active is None
        assert "climatisation" not in client.last_raw_responses

    def test_app_payload_with_generic_state_field_is_ignored(self):
        # a bare ``state`` is not a climatisation state: it must not read as "on"
        for payload in ({"state": "ok"}, {"status": {"state": "idle"}}):
            client = _client({_LEGACY: _404(_LEGACY), _APP: payload})
            data = asyncio.run(client.get_status(_VIN))
            assert data.climatisation_active is None
            assert "climatisation" not in client.last_raw_responses

    def test_app_payload_wrapper_forms_are_read(self):
        for payload in (
            {"status": {"climatisationState": "heating"}},
            {"climatisationState": "heating"},
        ):
            client = _client({_LEGACY: _404(_LEGACY), _APP: payload})
            data = asyncio.run(client.get_status(_VIN))
            assert data.climatisation_active is True

    def test_app_payload_not_a_dict_is_ignored(self):
        for payload in (["x"], "text"):
            client = _client({_LEGACY: _404(_LEGACY), _APP: payload})
            data = asyncio.run(client.get_status(_VIN))
            assert data.climatisation_active is None

    def test_app_path_server_error_keeps_today_state(self):
        client = _client({_LEGACY: _404(_LEGACY), _APP: APIError(500, _APP, "boom")})
        data = asyncio.run(client.get_status(_VIN))
        assert data.climatisation_active is None
        assert "climatisation" not in client.last_raw_responses
        assert client.parser_stats["climatisation"]["fail"] == 1
