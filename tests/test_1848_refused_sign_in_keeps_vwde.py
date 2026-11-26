# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1848 — a refused main sign-in no longer takes a healthy volkswagen.de
channel down with it.

Setup ran the main sign-in before arming the supplementary channels, with no
handler in between, so a portal that refused the sign-in ended setup before
volkswagen.de was ever armed: no data at all until the user signed in again,
although volkswagen.de could have served the car.

What changed, and what deliberately did not:

- A refusal that needs the user anyway (today it ends in a reauth prompt) lets
  setup go on, but only when volkswagen.de is configured, arms, and lists at
  least one car from the stored snapshot. The cars come from the snapshot and
  nothing is pruned. The refusal is still reported the way a failed setup
  reported it: the same repair and a reauth flow, after setup, because
  ``clear_auth_issues`` at the end of a successful setup would remove the
  repair again.
- An expired portal session and an expired device login keep their own paths.
- A 5xx on the portal's login landing is now ``UpstreamUnavailableError``
  instead of ``PortalInteractionRequiredError``: a server error is not a step
  the user can take, and only the 5xx class is retried by Home Assistant. A
  setup that went on after it would leave the portal off until the next
  restart, because nothing repeats the sign-in later.
- The reason for each refusal comes from one mapping now; the old except
  chain's results are pinned below.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad import exceptions as exc

_VIN = "WVWZZZE1ZTP000001"


# ---------------------------------------------------------------------------
# One mapping from refusal to setup reason, results as before.
# ---------------------------------------------------------------------------

# What the except chain in async_setup raised before #1848, class by class.
_OLD_CHAIN = [
    (exc.TermsAndConditionsError(), "terms_and_conditions"),
    (exc.MarketingConsentError(), "marketing_consent"),
    (exc.EmailTwoFactorRequiredError(), "email_two_factor_required"),
    (exc.TwoFactorRequiredError(), "two_factor_required"),
    (exc.PortalInteractionRequiredError("x"), "portal_interaction_required"),
    (exc.DeviceLoginExpiredError("x"), "device_login_expired"),
    (exc.EuropeAttestationError("x"), "eu_signin_attestation"),
    (exc.AuthenticationError("x"), "invalid_credentials"),
    (exc.InvalidCredentialsError("x"), "invalid_credentials"),
    (exc.WebsiteConsentRequiredError("x"), "invalid_credentials"),
    (exc.NorthAmericaAttestationError("x"), "invalid_credentials"),
]


@pytest.mark.parametrize(("err", "reason"), _OLD_CHAIN,
                         ids=[type(e).__name__ for e, _ in _OLD_CHAIN])
def test_refusal_reason_matches_the_old_except_chain(err, reason):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    assert VagConnectCoordinator._auth_refusal_reason(err) == reason


# ---------------------------------------------------------------------------
# Setup: goes on via volkswagen.de, or fails exactly as before.
# ---------------------------------------------------------------------------


def _coord(*, vwde: bool = True, snapshot: bool = True):
    from custom_components.vag_connect.const import CONF_SUPPLEMENTARY_AUTHPROXY
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
    if vwde:
        coord.entry.data[CONF_SUPPLEMENTARY_AUTHPROXY] = True
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = None
    coord._started = False
    coord._was_available = True
    coord.vehicles = {_VIN: {"vin": _VIN, "battery_soc": 61}} if snapshot else {}
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    # Arming is not under test here; the connector is set on the client.
    coord._arm_supplementary_channels = AsyncMock()
    return coord


def _portal_tokens():
    from custom_components.vag_connect.cariad.models import TokenSet
    return TokenSet(
        access_token="eu-data-act-portal-cookie-session", refresh_token="",
        id_token="", expires_at=4102444800.0, strategy="data_act_portal",
    )


def _client(refusal: BaseException | None, *, listed: Any = (_VIN,),
            list_raises: bool = False, armed: bool = True):
    client = MagicMock()
    client.authenticate = AsyncMock(side_effect=refusal)
    client.set_persisted_tokens = MagicMock()
    client.get_vehicles = AsyncMock(return_value=[_VIN])
    # The real client raises this for every read while it holds no token.
    client.get_status = AsyncMock(
        side_effect=exc.AuthenticationError("Not authenticated")
    )
    client._supplementary_eu_portal = None
    client._eu_portal = None
    if armed:
        web = MagicMock()
        if list_raises:
            web.list_vehicle_vins = AsyncMock(side_effect=RuntimeError("boom"))
        else:
            web.list_vehicle_vins = AsyncMock(return_value=list(listed))
        client._supplementary_authproxy = web
    else:
        client._supplementary_authproxy = None
    return client


def _run(coord, client, tokens: Any = "portal"):
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
    loaded = _portal_tokens() if tokens == "portal" else tokens
    with patch.object(CariadClientFactory, "create", return_value=client), \
         patch("homeassistant.helpers.aiohttp_client.async_get_clientsession",
               return_value=MagicMock()), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.load", new=AsyncMock(return_value=loaded)), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.save", new=AsyncMock()):
        return asyncio.run(coord.async_setup())


def test_a_refused_portal_sign_in_goes_on_via_volkswagen_de():
    coord = _coord()
    client = _client(exc.AuthenticationError("login failed"))
    assert _run(coord, client) is True
    assert coord.primary_refusal_reason == "invalid_credentials"
    assert _VIN in coord.vehicles
    assert coord.vehicles[_VIN]["battery_soc"] == 61
    client.get_vehicles.assert_not_awaited()
    client._supplementary_authproxy.list_vehicle_vins.assert_awaited_once()


def test_an_entry_without_stored_tokens_goes_on_the_same_way():
    coord = _coord()
    client = _client(exc.AuthenticationError("login failed"))
    assert _run(coord, client, tokens=None) is True
    assert coord.primary_refusal_reason == "invalid_credentials"


def test_a_portal_interaction_refusal_keeps_its_own_reason():
    coord = _coord()
    client = _client(exc.PortalInteractionRequiredError("onboarding / region step"))
    assert _run(coord, client) is True
    assert coord.primary_refusal_reason == "portal_interaction_required"


def test_vin_comparison_ignores_case():
    coord = _coord()
    client = _client(exc.AuthenticationError("x"), listed=(_VIN.lower(),))
    assert _run(coord, client) is True


@pytest.mark.parametrize(
    "case",
    ["no_vwde_configured", "vwde_not_armed", "vwde_lists_other_car",
     "vwde_lists_nothing", "vwde_list_raises", "no_snapshot"],
)
def test_without_a_working_volkswagen_de_the_refusal_fails_setup_as_before(case):
    coord = _coord(vwde=case != "no_vwde_configured",
                   snapshot=case != "no_snapshot")
    client = _client(
        exc.AuthenticationError("login failed"),
        listed={"vwde_lists_other_car": ("WVWZZZE1ZTP999999",),
                "vwde_lists_nothing": ()}.get(case, (_VIN,)),
        list_raises=case == "vwde_list_raises",
        armed=case != "vwde_not_armed",
    )
    with pytest.raises(ValueError, match="^invalid_credentials$"):
        _run(coord, client)
    assert getattr(coord, "primary_refusal_reason", None) is None


def test_an_expired_portal_session_keeps_its_retry_path():
    from homeassistant.exceptions import ConfigEntryNotReady
    coord = _coord()
    coord._raise_data_act_session_expired_repair = MagicMock()
    client = _client(exc.PortalSessionExpiredError("401 on the vehicle list"))
    with pytest.raises(ConfigEntryNotReady):
        _run(coord, client)
    client._supplementary_authproxy.list_vehicle_vins.assert_not_awaited()
    assert getattr(coord, "primary_refusal_reason", None) is None


def test_an_expired_device_login_keeps_its_own_notice():
    coord = _coord()
    client = _client(exc.DeviceLoginExpiredError("strategy=auth0"))
    with pytest.raises(ValueError, match="^device_login_expired$"):
        _run(coord, client)
    client._supplementary_authproxy.list_vehicle_vins.assert_not_awaited()


def test_a_server_error_is_not_turned_into_a_running_entry():
    """The 5xx class is not a refusal: setup still fails and is retried."""
    coord = _coord()
    client = _client(exc.UpstreamUnavailableError(503, brand="volkswagen"))
    assert _run(coord, client) is False
    client._supplementary_authproxy.list_vehicle_vins.assert_not_awaited()
    assert getattr(coord, "primary_refusal_reason", None) is None


def test_a_working_sign_in_sets_no_refusal():
    coord = _coord()
    client = _client(None)
    assert _run(coord, client) is True
    assert getattr(coord, "primary_refusal_reason", None) is None
    client.get_vehicles.assert_awaited()


# ---------------------------------------------------------------------------
# async_setup_entry reports the refusal after its clean-up.
# ---------------------------------------------------------------------------


def _hass():
    hass = MagicMock()
    hass.loop = MagicMock()
    hass.data = {}
    hass.services.has_service = MagicMock(return_value=True)
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    return hass


def _entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {
        "brand": "volkswagen", "username": "u@t.de",
        "password": "pw", "spin": "", "scan_interval": 5,
    }
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    entry.async_on_unload = MagicMock()
    entry.async_start_reauth = MagicMock()
    return entry


def _setup_entry(refusal):
    from custom_components.vag_connect import async_setup_entry
    hass, entry = _hass(), _entry()
    coord = MagicMock()
    coord.async_setup = AsyncMock(return_value=True)
    coord.vehicles = {_VIN: {}}
    coord.primary_refusal_reason = refusal
    coord.async_start_push_managers = AsyncMock()
    calls: list[tuple[str, Any]] = []
    with patch("custom_components.vag_connect.VagConnectCoordinator",
               return_value=coord), \
         patch("custom_components.vag_connect.repairs.clear_auth_issues",
               side_effect=lambda h, e: calls.append(("clear", e))), \
         patch("custom_components.vag_connect.repairs.raise_issue_auth_required",
               side_effect=lambda h, e, r, brand=None: calls.append(("raise", r))):
        assert asyncio.run(async_setup_entry(hass, entry)) is True
    return entry, calls


def test_the_refusal_is_reported_after_the_clean_up():
    entry, calls = _setup_entry("invalid_credentials")
    assert calls == [("clear", "test_entry"), ("raise", "invalid_credentials")]
    entry.async_start_reauth.assert_called_once()


def test_no_refusal_no_notice():
    entry, calls = _setup_entry(None)
    assert calls == [("clear", "test_entry")]
    entry.async_start_reauth.assert_not_called()


# ---------------------------------------------------------------------------
# Portal login: a 5xx landing is the 5xx class, a 4xx stays an interaction.
# ---------------------------------------------------------------------------

_SIGNIN_HTML = (
    '<form action="/signin-service/v1/CLIENT/login/identifier">'
    '<input type="hidden" name="hmac" value="email_hmac">'
    '<input type="hidden" name="_csrf" value="csrf1">'
    '<input type="hidden" name="relayState" value="rs1">'
    '</form>'
)
_PASSWORD_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"hmac":"fresh_pw_hmac","relayState":"rs1",'
    '"postAction":"/signin-service/v1/CLIENT/login/authenticate"}, '
    'csrf_token: "csrf2"};</script>'
)


class _Resp:
    def __init__(self, url: str, *, status: int = 200, text: str = "") -> None:
        self.url = url
        self.status = status
        self.headers: dict[str, str] = {}
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text


class _Session:
    """Drives the login to a landing page off the sign-in service."""

    def __init__(self, status: int) -> None:
        self._status = status

    def get(self, url: str, **kw: Any) -> _Resp:
        if url.endswith("/") and "vwgroup-datahub" in url:
            return _Resp(url, text="<html>portal</html>")
        if "authorize" in url:
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "identifier", text=_SIGNIN_HTML)
        raise AssertionError(f"unmatched GET {url}")

    def post(self, url: str, **kw: Any) -> _Resp:
        if url.endswith("/login/identifier"):
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "authenticate?relayState=rs1", text=_PASSWORD_HTML)
        if "/login/authenticate" in url:
            return _Resp("https://gateway.example.invalid/landing",
                         status=self._status,
                         text="<html><body>Service Unavailable</body></html>")
        raise AssertionError(f"unmatched POST {url}")


async def _login(status: int) -> BaseException:
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )
    conn = EUDataActConnector(_Session(status))  # type: ignore[arg-type]
    with pytest.raises(exc.CariadError) as ei:
        await conn.login("user@example.com", "secret")
    return ei.value


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_a_5xx_login_landing_is_a_server_error(status):
    err = await _login(status)
    assert type(err) is exc.UpstreamUnavailableError
    assert err.status == status


@pytest.mark.parametrize("status", [400, 403, 429])
async def test_a_4xx_login_landing_stays_an_interaction(status):
    err = await _login(status)
    assert type(err) is exc.PortalInteractionRequiredError
    assert f"HTTP {status}" in str(err)
