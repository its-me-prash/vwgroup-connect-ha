# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1947 follow-up — a refusal classified as transient must still reach the
portal fallback at SETUP, where there is no last-known-good to stay alive on.

The ladder in ``async_setup`` (#875, then #1222) exists for exactly this shape:
persisted non-portal tokens skip the fresh login, so the supplementary channel
is never armed, ``get_vehicles`` hits the dead primary path, and the entry would
die on a sign-in that actually works. It catches ``AuthenticationError``.

Thirteen days after that ladder was built, #1318 reclassified every
non-``invalid_grant`` refresh rejection as ``TokenRefreshRetryError`` — a
deliberate SIBLING of ``AuthenticationError``, so a blip would stop bouncing
users to a reauth prompt. Correct for the poll loop, which keeps the entry live
on its last snapshot. Wrong here: setup has no snapshot, so "transient" means
"retry the same dead token every 160 s forever", and the ladder built for this
exact failure is never entered.

Field evidence, all on v5.1.2 with ``expires_at=0`` and an EMPTY strategy field
(the log prints ``strategy=(legacy)`` for a falsy value, which is why the entry
is not treated as a portal one): @mortenmoulder, @RichardPitt and @hausamsee.
The portal login succeeds and arms in every one of their logs, and one cached
vehicle is restored — the data was there, the route to it was not. @hausamsee
asked for precisely this: continue on the channel that authenticated.

The user-visible message is the second half of the defect. The catch-all does
not raise, it returns False, and the entry point renders that as "No vehicles
found for this account. The login itself worked" — which is why @mortenmoulder
called it "very strange" while his car sat visible in the portal.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch


def _coord(brand: str = "cupra"):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.data = {
        "brand": brand, "username": "u@t.de",
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


def _reported_tokens():
    """The exact shape in all three field reports: no expiry, no strategy."""
    from custom_components.vag_connect.cariad.models import TokenSet
    return TokenSet(
        access_token="dead", refresh_token="dead", id_token="",
        expires_at=0.0, strategy="",   # falsy → logged as "(legacy)", not portal
    )


def _client(get_vehicles, portal=None):
    from custom_components.vag_connect.cariad.models import VehicleData
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.set_persisted_tokens = MagicMock()
    client.get_vehicles = get_vehicles
    client.get_status = AsyncMock(return_value=VehicleData(vin="VIN123", battery_soc=80))
    # explicit: a bare MagicMock would auto-create a truthy portal whose
    # list_vehicle_vins returns a Mock, and the no-channel case would then pass
    # for the wrong reason.
    client._supplementary_eu_portal = portal
    client._eu_portal = None
    return client


def _run(coord, client):
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
    with patch.object(CariadClientFactory, "create", return_value=client), \
         patch("homeassistant.helpers.aiohttp_client.async_get_clientsession",
               return_value=MagicMock()), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.load", new=AsyncMock(return_value=_reported_tokens())), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.save", new=AsyncMock()):
        return asyncio.run(coord.async_setup())


def test_the_skipped_fresh_login_is_still_done_after_a_transient_refusal():
    from custom_components.vag_connect.cariad.exceptions import TokenRefreshRetryError
    gv = AsyncMock(side_effect=[TokenRefreshRetryError("refresh refused"),
                                ["VIN123"]])
    coord = _coord()
    client = _client(gv)
    assert _run(coord, client) is True
    assert "VIN123" in coord.vehicles
    client.authenticate.assert_awaited()
    assert gv.await_count == 2


def test_a_parked_entry_survives_on_the_channel_that_authenticated():
    """@hausamsee's case: both attempts refused, the portal serves the VIN."""
    from custom_components.vag_connect.cariad.exceptions import TokenRefreshRetryError
    portal = MagicMock()
    portal.list_vehicle_vins = AsyncMock(return_value=["WVWZZZE1ZTP000001"])
    gv = AsyncMock(side_effect=TokenRefreshRetryError("refresh refused"))
    coord = _coord()
    client = _client(gv, portal=portal)
    assert _run(coord, client) is True
    assert "WVWZZZE1ZTP000001" in coord.vehicles


def test_without_a_portal_channel_the_entry_still_reports_not_ready():
    """Strict no-op: no channel to fall back to, so the outcome is unchanged."""
    from custom_components.vag_connect.cariad.exceptions import TokenRefreshRetryError
    gv = AsyncMock(side_effect=TokenRefreshRetryError("refresh refused"))
    coord = _coord()
    client = _client(gv)
    assert _run(coord, client) is False


def test_porsche_is_never_asked_to_submit_its_credentials_twice():
    """#1337 — a second identical login per restart is what locks Porsche
    accounts. The widened catch must not reopen that door."""
    from custom_components.vag_connect.cariad.exceptions import TokenRefreshRetryError
    portal = MagicMock()
    portal.list_vehicle_vins = AsyncMock(return_value=["WVWZZZE1ZTP000001"])
    gv = AsyncMock(side_effect=TokenRefreshRetryError("refresh refused"))
    coord = _coord(brand="porsche")
    client = _client(gv, portal=portal)
    _run(coord, client)
    # the skipped-login retry must not have run: exactly one enumeration
    assert gv.await_count == 1
    client.authenticate.assert_not_awaited()


def test_the_transient_classification_itself_is_not_quietly_undone():
    """The lazy fix is to make it a subclass. That would bounce every blip to a
    reauth prompt, which is the whole point of #1318. Blocked here as well as in
    tests/test_refresh_retry_classification.py."""
    from custom_components.vag_connect.cariad.exceptions import (
        AuthenticationError,
        TokenRefreshRetryError,
    )
    assert not issubclass(TokenRefreshRetryError, AuthenticationError)


def test_the_poll_loop_still_treats_it_as_self_healing():
    """The other lazy fix: drop it from the transient set so it reaches the
    AuthenticationError ladder. That would make every poll-time blip tear the
    entry down."""
    from custom_components.vag_connect.coordinator import _is_selfhealing_poll_error
    from custom_components.vag_connect.cariad.exceptions import TokenRefreshRetryError
    assert _is_selfhealing_poll_error(TokenRefreshRetryError("blip")) is True
