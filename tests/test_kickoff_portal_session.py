# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exercise both coordinator scraper sites with explicit session identities."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.coordinator import VagConnectCoordinator

_SCRAPER = "custom_components.vag_connect.cariad.auth._data_act_scraper.DataActScraper"
_SESSION = "homeassistant.helpers.aiohttp_client.async_get_clientsession"
_VIN = "WVWZZZAUZFW000000"


def _coordinator(portal: object | None, *, strategy: str = "data_act_portal",
                 supplementary: bool = False) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = SimpleNamespace(
        data={"brand": "volkswagen", "supplementary_eu_portal": supplementary},
        options={"data_act_identifiers": {_VIN: "existing"}},
    )
    coord._cariad_client = SimpleNamespace(
        _portal_session=portal,
        _tokens=SimpleNamespace(strategy=strategy, access_token="test-portal-bearer"),
    )
    coord.vehicles = {_VIN: {}}
    coord._active_vins = lambda vins: vins
    coord.historical_export_state = lambda vin: "idle"
    coord._record_historical_pending = MagicMock()
    coord._raise_data_act_session_expired_repair = MagicMock()
    return coord


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["kickoff", "export"])
@pytest.mark.parametrize("isolated", [True, False])
@pytest.mark.parametrize("strategy,supplementary", [
    ("data_act_portal", False), ("mbb", True),
])
async def test_coordinator_passes_authenticated_session(
    method: str, isolated: bool, strategy: str, supplementary: bool,
) -> None:
    shared, portal = object(), object() if isolated else None
    coord = _coordinator(portal, strategy=strategy, supplementary=supplementary)
    scraper = SimpleNamespace(
        get_active_custom_request_identifier=AsyncMock(return_value="existing"),
        kickoff_historical_export=AsyncMock(return_value=True),
    )
    with patch(_SESSION, return_value=shared), patch(_SCRAPER, return_value=scraper) as constructor:
        if method == "kickoff":
            await coord._ensure_data_act_custom_request_kickoff()
            scraper.get_active_custom_request_identifier.assert_awaited_once_with(_VIN)
        else:
            with patch("custom_components.vag_connect.const.ONETIME_EXPORT_DISABLED", False):
                assert await coord.async_request_historical_export(_VIN) is True
            coord._record_historical_pending.assert_called_once_with(_VIN)
    assert constructor.call_args.args[0] is (portal if isolated else shared)
    coord._raise_data_act_session_expired_repair.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("close_at", ["before", "csrf", "post"])
async def test_export_unload_returns_false_without_reauth_or_pending(close_at: str) -> None:
    from custom_components.vag_connect.cariad.auth._data_act_scraper import DataActScraper

    session = SimpleNamespace(closed=close_at == "before", post=MagicMock())
    session.post.side_effect = RuntimeError("Session is closed")
    coord = _coordinator(session)

    async def csrf() -> None:
        if close_at == "csrf":
            session.closed = True

    csrf_mock = AsyncMock(side_effect=csrf)
    with (
        patch(_SESSION, return_value=object()),
        patch("custom_components.vag_connect.const.ONETIME_EXPORT_DISABLED", False),
        patch.object(DataActScraper, "_fetch_csrf_token", csrf_mock),
    ):
        assert await coord.async_request_historical_export(_VIN) is False
    if close_at == "before":
        csrf_mock.assert_not_awaited()
    else:
        csrf_mock.assert_awaited_once()
    assert session.post.call_count == (1 if close_at == "post" else 0)
    coord._record_historical_pending.assert_not_called()
    coord._raise_data_act_session_expired_repair.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("supplementary", [False, True])
@pytest.mark.parametrize("force", [False, True])
async def test_bearer_entry_never_uses_cookie_only_kickoff(
    supplementary: bool, force: bool,
) -> None:
    from homeassistant.exceptions import ServiceValidationError

    coord = _coordinator(object(), strategy="device_grant_portal", supplementary=supplementary)
    with patch(_SESSION) as shared, patch(_SCRAPER) as constructor:
        if force:
            with pytest.raises(ServiceValidationError) as exc:
                await coord._ensure_data_act_custom_request_kickoff(force=True)
            assert exc.value.translation_key == "portal_request_requires_cookie_login"
        else:
            await coord._ensure_data_act_custom_request_kickoff()
    constructor.assert_not_called()
    shared.assert_not_called()
    coord._raise_data_act_session_expired_repair.assert_not_called()


@pytest.mark.asyncio
async def test_bearer_export_explains_cookie_login_requirement() -> None:
    from homeassistant.exceptions import ServiceValidationError

    coord = _coordinator(object(), strategy="device_grant_portal")
    with (
        patch("custom_components.vag_connect.const.ONETIME_EXPORT_DISABLED", False),
        patch(_SESSION) as shared,
        patch(_SCRAPER) as constructor,
        pytest.raises(ServiceValidationError) as exc,
    ):
        await coord.async_request_historical_export(_VIN)
    assert exc.value.translation_key == "portal_request_requires_cookie_login"
    constructor.assert_not_called()
    shared.assert_not_called()
    coord._raise_data_act_session_expired_repair.assert_not_called()
    coord._record_historical_pending.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("close_at", ["before", "probe", "post"])
async def test_kickoff_unload_does_not_save_a_retry_timestamp(close_at: str) -> None:
    session = SimpleNamespace(closed=close_at == "before")
    coord = _coordinator(session)
    coord.entry.options = {}
    coord._data_act_kickoff_error = {}

    async def probe(vin: str) -> None:
        if close_at == "probe":
            session.closed = True

    async def post(vin: str) -> None:
        session.closed = True

    scraper = SimpleNamespace(
        get_active_custom_request_identifier=AsyncMock(side_effect=probe),
        kickoff_custom_data_request=AsyncMock(side_effect=post),
    )
    with (
        patch(_SESSION, return_value=object()),
        patch(_SCRAPER, return_value=scraper),
        patch("custom_components.vag_connect.coordinator._self_update_entry") as persist,
    ):
        await coord._ensure_data_act_custom_request_kickoff()
    persist.assert_not_called()
    assert scraper.get_active_custom_request_identifier.await_count == (close_at != "before")
    assert scraper.kickoff_custom_data_request.await_count == (close_at == "post")
    coord._raise_data_act_session_expired_repair.assert_not_called()


@pytest.mark.asyncio
async def test_setup_hands_its_isolated_session_to_the_kickoff() -> None:
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    coord = _coordinator(None)
    coord.entry.entry_id = "portal-test"
    client = coord._cariad_client
    # Stop setup at the first authentication call: the session handover has
    # happened, and no vehicle/background polling is needed for this contract.
    client.authenticate = AsyncMock(side_effect=AuthenticationError("test stop"))
    own, shared = SimpleNamespace(closed=False), object()
    store = SimpleNamespace(async_load=AsyncMock(return_value=None))
    scraper = SimpleNamespace(
        get_active_custom_request_identifier=AsyncMock(return_value="existing"),
    )
    with (
        patch(_SESSION, return_value=shared),
        patch("homeassistant.helpers.aiohttp_client.async_create_clientsession", return_value=own),
        patch("custom_components.vag_connect.cariad.CariadClientFactory.create", return_value=client),
        patch("custom_components.vag_connect.cariad.auth._token_storage.TokenStorage.load",
              AsyncMock(return_value=None)),
        patch("homeassistant.helpers.storage.Store", return_value=store),
        patch(_SCRAPER, return_value=scraper) as constructor,
    ):
        with pytest.raises(ValueError, match="invalid_credentials"):
            await coord.async_setup()
        assert client._portal_session is own
        await coord._ensure_data_act_custom_request_kickoff()
    assert constructor.call_args.args[0] is own
    scraper.get_active_custom_request_identifier.assert_awaited_once_with(_VIN)
