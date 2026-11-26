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
    client.close_supplementary = AsyncMock()
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


@pytest.mark.parametrize("strategy", [None, "website_authproxy"])
def test_only_a_stored_portal_session_goes_on(strategy):
    """Without the stored portal session the client is not read-only, and a
    run on volkswagen.de would offer command entities that fail and are left
    behind once the reauth reloads the entry. Such an entry fails as before."""
    from custom_components.vag_connect.cariad.models import TokenSet
    tokens = None if strategy is None else TokenSet(
        access_token="x", refresh_token="", id_token="",
        expires_at=4102444800.0, strategy=strategy)
    coord = _coord()
    client = _client(exc.AuthenticationError("login failed"))
    with pytest.raises(ValueError, match="^invalid_credentials$"):
        _run(coord, client, tokens=tokens)
    coord._arm_supplementary_channels.assert_not_awaited()
    assert getattr(coord, "primary_refusal_reason", None) is None


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
    if case in ("no_vwde_configured", "no_snapshot"):
        # decided before arming: no volkswagen.de session for a failing setup
        coord._arm_supplementary_channels.assert_not_awaited()
        client.close_supplementary.assert_not_awaited()
    else:
        # armed for the check, and closed again because setup fails
        coord._arm_supplementary_channels.assert_awaited_once()
        client.close_supplementary.assert_awaited_once()


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
    assert isinstance(getattr(coord, "setup_failure", None),
                      exc.UpstreamUnavailableError)


# ---------------------------------------------------------------------------
# VW and Audi EU: the attestation answer must not hide a portal outage.
# ---------------------------------------------------------------------------


def _strategy_client(portal_error: BaseException, brand: str = "volkswagen"):
    """The real strategy loop; both sign-in steps hit the EU attestation wall
    (as with a correct password on VW and Audi EU), then the portal fails."""
    from types import SimpleNamespace

    from custom_components.vag_connect.cariad.api.base import CariadBaseClient

    me = CariadBaseClient.__new__(CariadBaseClient)
    me._brand = SimpleNamespace(name=brand)
    me._email = "owner@example.com"
    me._password = "right-password"
    me._spin = ""
    me._use_website_proxy = False
    me._tokens = None
    me._auth = SimpleNamespace(authenticate=AsyncMock(
        side_effect=exc.EuropeAttestationError("Sign-in blocked by VW device attestation")
    ))

    async def _portal() -> None:
        raise portal_error

    me._arm_eu_portal = _portal
    return me


@pytest.mark.parametrize("brand", ["volkswagen", "audi"])
@pytest.mark.parametrize("portal_error", [
    exc.UpstreamUnavailableError(503, brand="volkswagen"),
    exc.UpstreamUnavailableError(504, brand="volkswagen"),
    exc.RateLimitError(),
], ids=["5xx", "timeout", "rate_limit"])
async def test_a_portal_outage_is_not_handed_on_as_the_attestation_refusal(
    portal_error, brand,
):
    me = _strategy_client(portal_error, brand)
    with pytest.raises(type(portal_error)):
        await me.authenticate()


async def test_a_generic_portal_failure_still_hands_on_the_attestation_answer():
    """GUARD for #1712: a failure that says nothing is still reported as the
    attestation wall, not as a wrong password."""
    me = _strategy_client(RuntimeError("boom"))
    with pytest.raises(exc.EuropeAttestationError):
        await me.authenticate()


def test_setup_retries_a_portal_outage_behind_the_attestation_wall():
    """End to end: the real loop's result reaches setup as a server outage,
    which fails and is retried, and never as a refusal to run on."""
    coord = _coord()
    client = _client(None)
    client.authenticate = _strategy_client(
        exc.UpstreamUnavailableError(503, brand="volkswagen")).authenticate
    assert _run(coord, client) is False
    assert getattr(coord, "primary_refusal_reason", None) is None
    client._supplementary_authproxy.list_vehicle_vins.assert_not_awaited()


# ---------------------------------------------------------------------------
# No portal kickoff while the portal refuses the sign-in.
# ---------------------------------------------------------------------------


def _kickoff_coord(refusal):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.options = MagicMock()
    coord.entry.options.get = MagicMock(return_value=False)  # auto kickoff off
    coord.entry.data = MagicMock()
    coord.entry.data.get = MagicMock(return_value=None)
    coord._cariad_client = MagicMock()
    coord.primary_refusal_reason = refusal
    return coord


def test_no_kickoff_while_the_portal_refuses_the_sign_in():
    coord = _kickoff_coord("invalid_credentials")
    asyncio.run(coord._ensure_data_act_custom_request_kickoff())
    coord.entry.options.get.assert_not_called()
    coord.entry.data.get.assert_not_called()


def test_the_manual_button_still_runs_the_kickoff_while_refused():
    """force=True is the user pressing the button; the guard lets it run."""
    coord = _kickoff_coord("invalid_credentials")
    coord._cariad_client._tokens = None
    asyncio.run(coord._ensure_data_act_custom_request_kickoff(force=True))
    # the supplementary-portal read comes only after the guard
    coord.entry.data.get.assert_called()


def test_the_kickoff_check_runs_as_before_without_a_refusal():
    """Contrast: without a refusal the function reaches its option check."""
    coord = _kickoff_coord(None)
    asyncio.run(coord._ensure_data_act_custom_request_kickoff())
    coord.entry.options.get.assert_called()


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



def _failed_setup_entry(failure):
    from custom_components.vag_connect import async_setup_entry
    coord = MagicMock()
    coord.async_setup = AsyncMock(return_value=False)
    coord.vehicles = {}
    coord.setup_failure = failure
    with patch("custom_components.vag_connect.VagConnectCoordinator",
               return_value=coord):
        asyncio.run(async_setup_entry(_hass(), _entry()))


def test_a_server_outage_at_setup_does_not_claim_the_login_worked():
    from homeassistant.exceptions import ConfigEntryNotReady
    with pytest.raises(ConfigEntryNotReady) as ei:
        _failed_setup_entry(exc.UpstreamUnavailableError(503, brand="volkswagen"))
    assert "HTTP 503" in str(ei.value)
    assert "login itself worked" not in str(ei.value)


def test_no_vehicles_keeps_its_message():
    from homeassistant.exceptions import ConfigEntryNotReady
    with pytest.raises(ConfigEntryNotReady, match="No vehicles found"):
        _failed_setup_entry(None)


def test_a_missing_vehicle_list_is_not_called_an_outage():
    """The same class stands for a 404 or 410 on the portal's vehicle list
    (#1964); that keeps the no-vehicles text."""
    from homeassistant.exceptions import ConfigEntryNotReady
    with pytest.raises(ConfigEntryNotReady, match="No vehicles found"):
        _failed_setup_entry(exc.UpstreamUnavailableError(404, brand="volkswagen"))


def test_a_foreign_failure_text_never_reaches_the_message():
    from homeassistant.exceptions import ConfigEntryNotReady
    with pytest.raises(ConfigEntryNotReady, match="No vehicles found") as ei:
        _failed_setup_entry(RuntimeError("https://x.invalid/?token=abc"))
    assert "token=abc" not in str(ei.value)


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


_DOWN = "<html><body>Service Unavailable</body></html>"
_SIGNIN_LANDING = (
    "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/authenticate"
    "?relayState=rs1"
)


class _Session:
    """Drives the login; each step can answer a server error."""

    def __init__(self, status: int = 200, *, signin_status: int = 200,
                 identifier_status: int = 200,
                 landing_url: str = "https://gateway.example.invalid/landing",
                 ) -> None:
        self._status = status
        self._signin_status = signin_status
        self._identifier_status = identifier_status
        self._landing_url = landing_url

    def get(self, url: str, **kw: Any) -> _Resp:
        if url.endswith("/") and "vwgroup-datahub" in url:
            return _Resp(url, text="<html>portal</html>")
        if "authorize" in url:
            if self._signin_status >= 500:
                return _Resp(url, status=self._signin_status, text=_DOWN)
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "identifier", text=_SIGNIN_HTML)
        raise AssertionError(f"unmatched GET {url}")

    def post(self, url: str, **kw: Any) -> _Resp:
        if url.endswith("/login/identifier"):
            if self._identifier_status >= 500:
                return _Resp(url, status=self._identifier_status, text=_DOWN)
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "authenticate?relayState=rs1", text=_PASSWORD_HTML)
        if "/login/authenticate" in url:
            return _Resp(self._landing_url, status=self._status, text=_DOWN)
        raise AssertionError(f"unmatched POST {url}")


async def _login(status: int = 200, **session_kw: Any) -> BaseException:
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )
    conn = EUDataActConnector(_Session(status, **session_kw))  # type: ignore[arg-type]
    with pytest.raises(exc.CariadError) as ei:
        await conn.login("user@example.com", "secret")
    return ei.value


@pytest.mark.parametrize("step", ["signin_page", "identifier", "signin_landing"])
async def test_a_5xx_at_any_sign_in_step_is_a_server_error(step):
    """A 503 before the credentials, after the e-mail step, or on the sign-in
    service's own landing used to read as a refusal ("could not parse the
    sign-in form", "no password form returned", "check email and password")."""
    kw: dict[str, Any] = {
        "signin_page": {"signin_status": 503},
        "identifier": {"identifier_status": 503},
        "signin_landing": {"status": 503, "landing_url": _SIGNIN_LANDING},
    }[step]
    err = await _login(**kw)
    assert type(err) is exc.UpstreamUnavailableError
    assert err.status == 503


async def test_the_server_error_names_the_brand_not_the_portal_state():
    err = await _login(503)
    assert "for brand volkswagen" in str(err)
    assert "__" not in str(err)


async def test_a_wrong_password_on_the_sign_in_service_is_still_a_refusal():
    """GUARD: the credential catch-all stays for a page without a 5xx."""
    err = await _login(200, landing_url=_SIGNIN_LANDING)
    assert type(err) is exc.AuthenticationError
    assert "check email and password" in str(err)


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


# ---------------------------------------------------------------------------
# Fourth review round: status first on the landing, 429, brand label,
# a failing close, and the int guard.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [None, "503", True, 503.0])
def test_only_an_int_status_counts_as_a_server_error(status):
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        _raise_if_server_error,
    )
    _raise_if_server_error(status, "volkswagen")  # must not raise
    _raise_if_server_error(MagicMock(), "volkswagen")
    with pytest.raises(exc.UpstreamUnavailableError):
        _raise_if_server_error(503, "volkswagen")


class _MarkerSession(_Session):
    """A 503 landing whose page and URL happen to contain classifier markers."""

    def post(self, url: str, **kw: Any) -> _Resp:
        if "/login/authenticate" in url:
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "authenticate?relayState=2fa0throttled",
                status=503,
                text="<html><body>2fa onboarding throttled - try later</body></html>",
            )
        return super().post(url, **kw)


async def test_a_5xx_landing_is_a_server_error_whatever_the_page_says():
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )
    conn = EUDataActConnector(_MarkerSession())  # type: ignore[arg-type]
    conn.last_login_interaction = "stale"
    with pytest.raises(exc.CariadError) as ei:
        await conn.login("user@example.com", "secret")
    assert type(ei.value) is exc.UpstreamUnavailableError
    assert conn.last_login_interaction == ""


def test_a_portal_429_at_setup_gets_the_outage_text():
    from homeassistant.exceptions import ConfigEntryNotReady
    with pytest.raises(ConfigEntryNotReady) as ei:
        _failed_setup_entry(exc.UpstreamUnavailableError(429, brand="volkswagen"))
    assert "HTTP 429" in str(ei.value)
    assert "login itself worked" not in str(ei.value)


class _DataSession:
    closed = False

    def __init__(self, status: int) -> None:
        self._status = status

    def get(self, url: str, **kw: Any) -> _Resp:
        return _Resp(url, status=self._status, text="{}")


async def test_the_portal_data_call_names_the_brand_too():
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )
    conn = EUDataActConnector(_DataSession(404))  # type: ignore[arg-type]
    with pytest.raises(exc.UpstreamUnavailableError) as ei:
        await conn._get_json("https://eu-data-act.vwgroup-datahub.com/x",
                             outage_statuses=(404,))
    assert "for brand volkswagen" in str(ei.value)
    assert "__" not in str(ei.value)


def test_a_failing_close_of_the_armed_channel_keeps_the_refusal():
    coord = _coord()
    client = _client(exc.AuthenticationError("login failed"), listed=())
    client.close_supplementary = AsyncMock(side_effect=RuntimeError("close failed"))
    with pytest.raises(ValueError, match="^invalid_credentials$"):
        _run(coord, client)
    client.close_supplementary.assert_awaited_once()
