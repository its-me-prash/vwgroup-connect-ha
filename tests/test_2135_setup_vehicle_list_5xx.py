# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2135 — an entry that already knows its cars starts when the list answers 5xx.

The EU Data Act portal moved on 2026-11-16 and, on the new host, its vehicle
list answered 503 while the rest of the portal was alive. ``async_setup`` has no
snapshot to fall back on for a NEW entry, but an entry restored from the last
successful start does: it starts with those cars and prunes nothing, because a
failed list proves nothing about the account. A new setup still fails and
retries, and an authentication failure on the list stays on its own ladder.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_VIN_A = "WVWZZZE1ZTP000001"
_VIN_B = "WVWZZZE1ZTP000002"


def _coord(restored: bool):
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
    coord.vehicles = (
        {_VIN_A: {"vin": _VIN_A, "odometer_km": 1000},
         _VIN_B: {"vin": _VIN_B, "odometer_km": 2000},
         "_meta": {}} if restored else {}
    )
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    coord._prune_absent_vehicles = MagicMock()
    return coord


def _tokens():
    from custom_components.vag_connect.cariad.models import TokenSet
    return TokenSet(
        access_token="dead", refresh_token="dead", id_token="",
        expires_at=0.0, strategy="",
    )


def _client(get_vehicles):
    from custom_components.vag_connect.cariad.models import VehicleData
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.set_persisted_tokens = MagicMock()
    client.get_vehicles = get_vehicles
    client.get_status = AsyncMock(return_value=VehicleData(vin=_VIN_A, battery_soc=80))
    client._supplementary_eu_portal = None
    client._eu_portal = None
    return client


def _run(coord, client):
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
    with patch.object(CariadClientFactory, "create", return_value=client), \
         patch("homeassistant.helpers.aiohttp_client.async_get_clientsession",
               return_value=MagicMock()), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.load", new=AsyncMock(return_value=_tokens())), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.save", new=AsyncMock()):
        return asyncio.run(coord.async_setup())


def test_a_restored_entry_starts_with_its_cars_when_the_list_answers_503(caplog):
    from custom_components.vag_connect.cariad.exceptions import UpstreamUnavailableError
    gv = AsyncMock(side_effect=UpstreamUnavailableError(503))
    coord = _coord(restored=True)
    client = _client(gv)
    with caplog.at_level(logging.WARNING):
        assert _run(coord, client) is True
    assert {_VIN_A, _VIN_B} <= set(coord.vehicles)
    assert gv.await_count == 1, "a 5xx is not retried through the auth ladder"
    client.authenticate.assert_not_awaited()
    # a failed list proves nothing about the account: nothing may be pruned
    coord._prune_absent_vehicles.assert_not_called()
    # exactly one warning, naming the status and what is being used instead
    hits = [r for r in caplog.records
            if r.levelno == logging.WARNING and "vehicle list" in r.getMessage()]
    assert len(hits) == 1
    msg = hits[0].getMessage()
    assert "503" in msg and "last successful start" in msg


def _status_named_in_the_failure(caplog, status: int) -> bool:
    """The re-raise reaches async_setup's catch-all, which logs the error class
    with its HTTP status. Without the re-raise the code falls through to the
    'no vehicles' path, which names no status, so this tells the two apart."""
    return any(
        r.levelno == logging.ERROR and f"HTTP {status}" in r.getMessage()
        for r in caplog.records
    )


def test_a_new_setup_without_restored_cars_still_fails_on_a_503(caplog):
    from custom_components.vag_connect.cariad.exceptions import UpstreamUnavailableError
    gv = AsyncMock(side_effect=UpstreamUnavailableError(503))
    coord = _coord(restored=False)
    client = _client(gv)
    with caplog.at_level(logging.WARNING):
        try:
            outcome = _run(coord, client)
        except UpstreamUnavailableError:
            return  # re-raised unchanged: setup fails and is retried
    assert outcome is False, "setup must not succeed with no cars at all"
    assert not [v for v in coord.vehicles if not str(v).startswith("_")]
    assert _status_named_in_the_failure(caplog, 503), (
        "the 503 must be re-raised and named, not turned into 'no vehicles'"
    )
    assert not [r for r in caplog.records
                if r.levelno == logging.WARNING and "vehicle list" in r.getMessage()]


def test_bookkeeping_keys_alone_do_not_count_as_restored_cars(caplog):
    from custom_components.vag_connect.cariad.exceptions import UpstreamUnavailableError
    gv = AsyncMock(side_effect=UpstreamUnavailableError(502))
    coord = _coord(restored=False)
    coord.vehicles = {"_meta": {}}
    with caplog.at_level(logging.WARNING):
        try:
            outcome = _run(coord, _client(gv))
        except UpstreamUnavailableError:
            return
    assert outcome is False
    assert _status_named_in_the_failure(caplog, 502)


def test_an_authentication_failure_on_the_list_stays_on_its_ladder():
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError
    gv = AsyncMock(side_effect=AuthenticationError("401 on the list"))
    coord = _coord(restored=True)
    client = _client(gv)
    # the ladder's existing end: the entry reports invalid credentials
    with pytest.raises(ValueError, match="invalid_credentials"):
        _run(coord, client)
    # the ladder re-logged in and asked a second time, as before this change
    client.authenticate.assert_awaited()
    assert gv.await_count == 2
    coord._prune_absent_vehicles.assert_not_called()


def test_a_successful_list_still_prunes_what_left_the_account():
    """Control: the fallback must not have switched pruning off for good."""
    gv = AsyncMock(return_value=[_VIN_A])
    coord = _coord(restored=True)
    assert _run(coord, _client(gv)) is True
    coord._prune_absent_vehicles.assert_called_once()
    assert coord._prune_absent_vehicles.call_args.args[0] == {_VIN_A}
