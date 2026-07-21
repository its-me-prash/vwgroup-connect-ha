# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.21.1 (#875) — a dead persisted IDK/legacy token must not kill the entry.

Repro: an entry with persisted non-portal tokens skips the fresh login, so
``_eu_portal`` is never armed; ``get_vehicles`` then hits the dead CARIAD-BFF
path, its token refresh 403s (VW's device-attestation wall), and the coordinator
used to turn that into ``invalid_credentials`` — killing a config entry whose
EU Data Act portal login actually works fine. The fix retries once with the
fresh login that was skipped; a genuine credential failure still surfaces.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _coord():
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.data = {
        "brand": "volkswagen", "username": "u@t.de",
        "password": "pw", "spin": "", "scan_interval": 5,
    }
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = None
    coord._started = False
    coord._was_available = True
    coord.vehicles = {}
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    return coord


def _non_portal_tokens():
    from custom_components.vag_connect.cariad.models import TokenSet
    return TokenSet(
        access_token="dead", refresh_token="dead", id_token="",
        expires_at=0.0, strategy="idk",  # NON-portal → fresh login is skipped
    )


def _client(get_vehicles):
    from custom_components.vag_connect.cariad.models import VehicleData
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.set_persisted_tokens = MagicMock()
    client.get_vehicles = get_vehicles
    client.get_status = AsyncMock(return_value=VehicleData(vin="VIN123", battery_soc=80))
    return client


def _run(coord, client):
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
    with patch.object(CariadClientFactory, "create", return_value=client), \
         patch("homeassistant.helpers.aiohttp_client.async_get_clientsession",
               return_value=MagicMock()), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.load", new=AsyncMock(return_value=_non_portal_tokens())), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.save", new=AsyncMock()):
        return asyncio.run(coord.async_setup())


def test_dead_persisted_token_recovers_via_fresh_login():
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError
    # get_vehicles fails once (dead refresh) then succeeds after the fresh login.
    gv = AsyncMock(side_effect=[AuthenticationError("Token refresh HTTP 403"),
                                ["VIN123"]])
    coord = _coord()
    client = _client(gv)
    result = _run(coord, client)
    assert result is True                     # entry survived, not invalid_credentials
    assert "VIN123" in coord.vehicles
    client.authenticate.assert_awaited()      # the skipped fresh login was done
    assert gv.await_count == 2                 # failed once, retried once


def test_genuine_auth_failure_still_surfaces():
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError
    # Even after the fresh login, get_vehicles keeps failing → real bad creds.
    gv = AsyncMock(side_effect=AuthenticationError("still dead"))
    coord = _coord()
    client = _client(gv)
    with pytest.raises(ValueError, match="invalid_credentials"):
        _run(coord, client)
