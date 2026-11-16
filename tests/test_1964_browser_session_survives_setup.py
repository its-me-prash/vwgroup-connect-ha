# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1964: a browser sign-in stored on an entry must survive a failed start.

An entry that was set up with e-mail and password keeps that password when the
browser sign-in is attached to it (``_finish_auth0``): the token store then
holds a session with strategy ``auth0``, the entry data still holds the
password.

At setup such a stored session skips the fresh sign-in. If the first vehicle
list request then failed ONCE, refused or only transiently, the setup ladder
(#875, #1947) did the fresh sign-in it had skipped. For this brand that is the
password chain, which ends in the read-only portal sign-in, and
``authenticate()`` hands its result to the token store. From then on the store
held ``data_act_portal``; every later start signed in with the password again
and nothing ever tried the browser session or said that it was gone.

Two locks, each pinned here:

* the ladder never answers a failed browser session with the password chain.
  A transient refusal leaves setup as it came (the start is retried with the
  same session); a refused session asks for a new sign-in;
* ``authenticate()`` refuses the password chain while the client holds a
  browser session, with or without a stored password, so no other caller can
  replace the session either.

Everything here is synthetic. Why the reporter's first request failed is not
known.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    DeviceLoginExpiredError,
    TokenRefreshRetryError,
)
from custom_components.vag_connect.cariad.models import TokenSet, VehicleData

_TRANSIENT = TokenRefreshRetryError("the refresh answered 503")
_REFUSED = AuthenticationError("the vehicle list answered 401")


# ─────────────────────────────────────────────────────────────────────────────
# The setup ladder
# ─────────────────────────────────────────────────────────────────────────────


def _session(strategy: str) -> TokenSet:
    return TokenSet(
        access_token="a", refresh_token="r", id_token="i",
        expires_at=9_999_999_999.0, strategy=strategy,
    )


def _coord(password: str, brand: str = "audi") -> Any:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.data = {
        "brand": brand, "username": "u@t.de",
        "password": password, "spin": "", "scan_interval": 5,
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


def _setup(
    answers: list[Any],
    *,
    stored: str = "auth0",
    password: str = "pw",
    portal: Any = None,
) -> SimpleNamespace:
    """Run the real ``async_setup`` against a stand-in client.

    The stand-in's ``authenticate()`` does what the real one does on such an
    entry: with no password and a browser session it refuses (the lock that
    exists since #1813); otherwise the password chain ends in the portal
    sign-in and the result goes to ``on_tokens_changed``, the callback
    ``_notify_tokens_changed`` calls after every sign-in.
    """
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory

    saved: list[str] = []

    async def _save(self: Any, tokens: Any) -> None:  # TokenStorage.save
        saved.append(getattr(tokens, "strategy", "?"))

    client = MagicMock()
    client.set_persisted_tokens = MagicMock()
    client.get_status = AsyncMock(return_value=VehicleData(vin="VIN123", battery_soc=80))
    client.get_vehicles = AsyncMock(side_effect=answers)
    # explicit: a bare MagicMock would grow a truthy portal on first access
    client._supplementary_eu_portal = portal
    client._eu_portal = None

    async def _sign_in(*_a: Any, **_k: Any) -> None:
        if not password and stored == "auth0":
            raise DeviceLoginExpiredError("strategy=auth0")
        await client.on_tokens_changed(_session("data_act_portal"))

    client.authenticate = AsyncMock(side_effect=_sign_in)
    coord = _coord(password)
    out = SimpleNamespace(result=None, error=None, saved=saved, client=client, coord=coord)
    with patch.object(CariadClientFactory, "create", return_value=client), \
         patch("homeassistant.helpers.aiohttp_client.async_get_clientsession",
               return_value=MagicMock()), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.load", new=AsyncMock(return_value=_session(stored))), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.save", new=_save):
        try:
            out.result = asyncio.run(coord.async_setup())
        except Exception as exc:  # noqa: BLE001
            out.error = exc
    return out


def test_a_blip_does_not_cost_the_browser_session() -> None:
    """One transient refusal: nothing is signed in, nothing is written, and the
    start is left to be retried with the session it has."""
    out = _setup([_TRANSIENT, ["VIN123"]])
    out.client.authenticate.assert_not_awaited()
    assert out.saved == [], "the token store must still hold the browser session"
    assert out.error is None
    assert out.result is False, "not ready, so the start is retried"
    assert out.client.get_vehicles.await_count == 1


def test_a_refused_browser_session_asks_for_a_new_sign_in() -> None:
    """Refused, not transient: the password chain cannot bring the browser
    session back, so the user is asked to sign in again and the store is left
    alone."""
    out = _setup([_REFUSED, ["VIN123"]])
    out.client.authenticate.assert_not_awaited()
    assert out.saved == []
    assert isinstance(out.error, ValueError)
    assert str(out.error) == "device_login_expired"


def test_a_failure_that_names_its_own_cause_keeps_its_reason() -> None:
    """Only the plain refusal is turned into "sign in again". An error class
    that names what the user has to do (here: accept the terms) leaves as it
    came, so its own notice is shown. The password chain is not run for it
    either."""
    from custom_components.vag_connect.cariad.exceptions import TermsAndConditionsError

    out = _setup([TermsAndConditionsError(), ["VIN123"]])
    out.client.authenticate.assert_not_awaited()
    assert out.saved == []
    assert isinstance(out.error, ValueError)
    assert str(out.error) == "terms_and_conditions"


@pytest.mark.parametrize("failure", [_TRANSIENT, _REFUSED], ids=["transient", "refused"])
def test_a_separate_portal_channel_keeps_the_entry_up_and_the_session_stored(
    failure: Exception,
) -> None:
    """An entry that has the portal as its own channel stays up on it, as
    before. The browser session stays in the store for the next start."""
    portal = MagicMock()
    portal.list_vehicle_vins = AsyncMock(return_value=["VIN123"])
    out = _setup([failure], portal=portal)
    assert out.error is None
    assert out.result is True
    assert "VIN123" in out.coord.vehicles
    out.client.authenticate.assert_not_awaited()
    assert out.saved == []


def test_an_entry_without_a_password_is_retried_after_a_blip() -> None:
    """Before, the ladder called ``authenticate()`` here too, which refuses for
    an entry without a password, so a blip at start ended in a prompt to sign
    in again."""
    out = _setup([_TRANSIENT, ["VIN123"]], password="")
    out.client.authenticate.assert_not_awaited()
    assert out.error is None
    assert out.result is False


def test_an_entry_without_a_password_is_still_asked_to_sign_in_when_refused() -> None:
    """Control: the outcome for a refused session without a password is the
    one it always was."""
    out = _setup([_REFUSED, ["VIN123"]], password="")
    assert isinstance(out.error, ValueError)
    assert str(out.error) == "device_login_expired"
    assert out.saved == []


def test_a_start_that_gets_its_vehicle_list_writes_nothing() -> None:
    """Control: the normal start."""
    out = _setup([["VIN123"]])
    assert out.result is True
    out.client.authenticate.assert_not_awaited()
    assert out.saved == []


@pytest.mark.parametrize("failure", [_TRANSIENT, _REFUSED], ids=["transient", "refused"])
@pytest.mark.parametrize("stored", ["idk", ""], ids=["idk", "legacy"])
def test_an_older_password_session_still_gets_the_skipped_sign_in(
    failure: Exception, stored: str,
) -> None:
    """Control for #875 and #1947: a stored session of the password kind that
    no longer works is still answered with the fresh sign-in. Only the browser
    session is exempt."""
    out = _setup([failure, ["VIN123"]], stored=stored)
    assert out.result is True
    out.client.authenticate.assert_awaited_once()
    assert out.client.get_vehicles.await_count == 2
    assert out.saved == ["data_act_portal"]


def test_a_stored_portal_session_still_signs_in_at_every_start() -> None:
    """Control: an entry that is on the portal keeps working the way it does.
    This is also the state an entry is in after the loss; a new browser
    sign-in is what moves it back."""
    out = _setup([["VIN123"]], stored="data_act_portal")
    assert out.result is True
    out.client.authenticate.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# authenticate() itself
# ─────────────────────────────────────────────────────────────────────────────


def _client(password: str, strategy: str | None) -> tuple[Any, list[str]]:
    """A brand client shaped for ``authenticate``'s own preconditions, whose
    password sign-in is walled and whose portal sign-in works: the state of
    the brand the report is about."""
    from custom_components.vag_connect.cariad.api.base import CariadBaseClient

    me = CariadBaseClient.__new__(CariadBaseClient)
    me._brand = SimpleNamespace(name="audi")
    me._email = "u@t.de"
    me._password = password
    me._spin = ""
    me._use_website_proxy = False
    me._tokens = (
        None if strategy is None else SimpleNamespace(strategy=strategy, refresh_token="r")
    )
    sent: list[str] = []

    async def _password_sign_in(*_a: Any, **_k: Any) -> Any:
        sent.append("password")
        raise AuthenticationError("walled")

    async def _portal_sign_in() -> None:
        sent.append("portal")
        me._tokens = SimpleNamespace(strategy="data_act_portal", refresh_token="")

    me._auth = SimpleNamespace(authenticate=_password_sign_in)
    me._arm_eu_portal = _portal_sign_in
    me._notify_tokens_changed = AsyncMock()
    return me, sent


async def test_a_browser_session_is_not_replaced_by_the_password_chain() -> None:
    """The stored password is for the portal channel. It must not be used to
    put a portal session where the browser session is."""
    me, sent = _client(password="pw", strategy="auth0")
    with pytest.raises(DeviceLoginExpiredError, match="auth0"):
        await me.authenticate()
    assert sent == [], "no sign-in may leave the machine"
    me._notify_tokens_changed.assert_not_awaited()
    assert me._tokens.strategy == "auth0"


@pytest.mark.parametrize(
    "strategy",
    ["idk", "", "data_act_portal", "device_grant", "device_grant_portal", "mbb", None],
)
async def test_every_other_session_with_a_password_still_runs_its_strategies(
    strategy: str | None,
) -> None:
    """Control: the lock is for the browser session only. An entry with a
    password and any other session can retry as before."""
    me, sent = _client(password="pw", strategy=strategy)
    try:
        await me.authenticate()
    except DeviceLoginExpiredError:
        pytest.fail(f"a {strategy!r} session with a password must not be refused")
    assert sent[-1] == "portal"
    assert "password" in sent
    me._notify_tokens_changed.assert_awaited_once()


@pytest.mark.parametrize("strategy", ["device_grant", "device_grant_portal", "mbb", "auth0"])
async def test_an_entry_without_a_password_is_refused_as_before(strategy: str) -> None:
    """Control for #1813: unchanged."""
    me, sent = _client(password="", strategy=strategy)
    with pytest.raises(DeviceLoginExpiredError):
        await me.authenticate()
    assert sent == []
