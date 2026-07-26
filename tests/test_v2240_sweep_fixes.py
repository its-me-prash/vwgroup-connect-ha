# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.24.0 — triaged sweep fixes (each root-caused against a live report).

- #915 (VW Canada, vrouleau + amateurdeveloper): a 5xx from the NA
  signin-service is VW's outage, not a wrong password. It must NOT surface as
  AuthenticationError (which fires an unwinnable reauth prompt); a 401 still
  must.
- #912 (Audi A6 e-tron PPE, Mirjam9): the start_climate_control SERVICE now
  applies the same force_ppe_climate gate the basic start already had.
- #931 (Golf GTE, SparkyDan555): actual_charge_rate is a deci portal field, and
  a miles-per-hour rate is converted so the km/h sensor is truthful.
- #909 (Audi e-tron GT, Lagaff86): a gateway-denied MBB operationList is
  negative-cached instead of being re-requested every poll.
- #933 (same reporter): a 429 — including our own client-side cooldown — is a
  self-healing poll error, not a backend failure worth escalating.
- #923 (VW T-Roc, fight3): an empty parkingposition response keeps the last
  known position instead of blanking it.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── #915: signin-service 5xx is an outage, not bad credentials ───────────────

class _Resp:
    """Minimal aiohttp-response stand-in usable as an async context manager."""

    def __init__(self, status: int, text: str = "", location: str = "") -> None:
        self.status = status
        self._text = text
        self.headers = {"Location": location} if location else {}

    async def text(self, *_args, **_kwargs) -> str:
        return self._text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False


class _Session:
    """Hands out the queued responses in order and records the calls."""

    def __init__(self, *responses: _Resp) -> None:
        self._queue = list(responses)
        self.calls: list[str] = []

    def post(self, url: str, **_kwargs) -> _Resp:
        self.calls.append(url)
        return self._queue.pop(0)

    def get(self, url: str, **_kwargs) -> _Resp:
        self.calls.append(url)
        return self._queue.pop(0)


_LOGIN_HTML = (
    '<form action="/signin-service/v1/CLIENT/login/identifier" method="post">'
    '<input type="hidden" name="_csrf" value="csrf-1">'
    '<input type="hidden" name="relayState" value="relay-1">'
    '<input type="hidden" name="hmac" value="hmac-1">'
    "</form>"
)
# Step 3 pulls the fresh hmac out of the embedded JS, not out of a form.
_PASSWORD_PAGE_HTML = '<script>var cfg = {"hmac":"deadbeef"};</script>'


def _idk(session: _Session):
    from custom_components.vag_connect.cariad.api.vw_na import BRAND_VW_NA
    from custom_components.vag_connect.cariad.auth.idk import IDKAuth

    return IDKAuth(session, BRAND_VW_NA)


def _login(session: _Session):
    return asyncio.run(
        _idk(session)._authenticate_legacy(
            _LOGIN_HTML, "u@t.de", "pw", "verifier-123",
        )
    )


def test_915_password_post_500_is_upstream_not_auth() -> None:
    from custom_components.vag_connect.cariad.exceptions import (
        AuthenticationError,
        UpstreamUnavailableError,
    )

    session = _Session(_Resp(200, _PASSWORD_PAGE_HTML), _Resp(500, "<html>oops"))
    with pytest.raises(UpstreamUnavailableError) as excinfo:
        _login(session)
    # The whole point: it must not be catchable as a credentials problem.
    assert not isinstance(excinfo.value, AuthenticationError)
    assert excinfo.value.status == 500


def test_915_upstream_message_blames_the_manufacturer() -> None:
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    session = _Session(_Resp(200, _PASSWORD_PAGE_HTML), _Resp(503, ""))
    with pytest.raises(UpstreamUnavailableError) as excinfo:
        _login(session)
    msg = str(excinfo.value).lower()
    assert "not a credentials problem" in msg
    assert "503" in msg


def test_915_password_post_401_is_still_an_auth_error() -> None:
    from custom_components.vag_connect.cariad.exceptions import (
        AuthenticationError,
        UpstreamUnavailableError,
    )

    session = _Session(_Resp(200, _PASSWORD_PAGE_HTML), _Resp(401, ""))
    with pytest.raises(AuthenticationError) as excinfo:
        _login(session)
    assert not isinstance(excinfo.value, UpstreamUnavailableError)


def test_915_password_post_429_is_still_rate_limited() -> None:
    from custom_components.vag_connect.cariad.exceptions import RateLimitError

    session = _Session(_Resp(200, _PASSWORD_PAGE_HTML), _Resp(429, ""))
    with pytest.raises(RateLimitError):
        _login(session)


def test_915_email_post_500_is_upstream_too() -> None:
    """Same host, one step earlier — the identifier POST must classify alike."""
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    session = _Session(_Resp(502, ""))
    with pytest.raises(UpstreamUnavailableError):
        _login(session)


def test_915_config_flow_maps_upstream_to_retryable_key() -> None:
    """The config flow must offer a retryable message, never invalid_credentials."""
    from custom_components.vag_connect.config_flow import _map_error

    assert _map_error("upstream_unavailable") == "upstream_unavailable"
    assert _map_error("upstream_unavailable") != "invalid_credentials"


# ── #912: the climate SERVICE honours force_ppe_climate ─────────────────────

def _coordinator(brand: str = "audi", *, ppe: bool = False):
    from custom_components.vag_connect.const import CONF_BRAND, CONF_FORCE_PPE_CLIMATE
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = MagicMock()
    # Options are folded into data by the update listener and then blanked, so
    # the realistic shape for a saved option is data-side with empty options.
    coord.entry.options = {}
    coord.entry.data = {CONF_BRAND: brand, CONF_FORCE_PPE_CLIMATE: ppe}
    coord._cariad_client = MagicMock()
    coord._cariad_cmd_optimistic = AsyncMock()
    return coord


def test_912_climate_control_service_passes_ppe_mode() -> None:
    coord = _coordinator(ppe=True)
    asyncio.run(coord.async_start_climate_control("VIN1", temp_c=22.0))
    kwargs = coord._cariad_cmd_optimistic.call_args.kwargs
    assert kwargs["ppe_mode"] is True
    assert kwargs["temp_c"] == 22.0  # still forwarded; the client drops it


def test_912_climate_control_service_omits_ppe_when_option_off() -> None:
    coord = _coordinator(ppe=False)
    asyncio.run(coord.async_start_climate_control("VIN1", temp_c=22.0))
    assert "ppe_mode" not in coord._cariad_cmd_optimistic.call_args.kwargs


def test_912_ppe_option_read_from_options_side_too() -> None:
    from custom_components.vag_connect.const import CONF_FORCE_PPE_CLIMATE

    coord = _coordinator(ppe=False)
    coord.entry.options = {CONF_FORCE_PPE_CLIMATE: True}
    asyncio.run(coord.async_start_climate_control("VIN1"))
    assert coord._cariad_cmd_optimistic.call_args.kwargs["ppe_mode"] is True


def test_912_basic_start_still_passes_ppe_mode() -> None:
    coord = _coordinator(ppe=True)
    asyncio.run(coord.async_start_climatisation("VIN1"))
    assert coord._cariad_cmd_optimistic.call_args.kwargs["ppe_mode"] is True


def test_912_non_cariad_brand_never_gets_ppe_mode() -> None:
    coord = _coordinator(brand="skoda", ppe=True)
    asyncio.run(coord.async_start_climate_control("VIN1"))
    assert "ppe_mode" not in coord._cariad_cmd_optimistic.call_args.kwargs


def _vw_eu_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    from custom_components.vag_connect.cariad.models import TokenSet

    client = VWEUClient(MagicMock(), "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client


def test_912_ppe_body_drops_target_temperature() -> None:
    client = _vw_eu_client()
    client._post = AsyncMock()
    asyncio.run(
        client.command_start_climate_control("VIN1", temp_c=22.0, ppe_mode=True)
    )
    body = client._post.call_args.kwargs["json"]
    assert "targetTemperature" not in body
    assert "targetTemperatureUnit" not in body
    assert body["climatisationMode"] == "comfort"


def test_912_non_ppe_body_keeps_target_temperature() -> None:
    client = _vw_eu_client()
    client._post = AsyncMock()
    asyncio.run(client.command_start_climate_control("VIN1", temp_c=22.0))
    body = client._post.call_args.kwargs["json"]
    assert body["targetTemperature"] == 22.0
    assert body["targetTemperatureUnit"] == "celsius"


# ── #931: charge-rate scaling + unit honesty ────────────────────────────────

def _map(fields: dict[str, str]):
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        map_dataset_to_vehicle_data,
    )
    from custom_components.vag_connect.cariad.models import VehicleData

    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_931_canonical_deci_rate_scaled() -> None:
    # 800 at 0.1 resolution → 80 km/h.
    assert _map({"battery_state_report.charge_rate": "800"}).charging_rate_kmh == 80


def test_931_actual_charge_rate_is_deci_too() -> None:
    # Was published raw, which is where the reporter's 10x came from.
    assert _map({"actual_charge_rate": "800"}).charging_rate_kmh == 80


def test_931_miles_per_hour_converted_to_kmh() -> None:
    d = _map({
        "battery_state_report.charge_rate": "800",
        "battery_state_report.charge_rate_unit": "miles_per_h",
    })
    assert d.charging_rate_kmh == 128.7  # 80 mph → 128.75 km/h, rounded


def test_931_verbose_enum_spelling_also_converted() -> None:
    """The portal ships the dict spelling as well as the shortened one."""
    d = _map({
        "charge_rate": "100",
        "charge_rate_unit": "CHARGE_RATE_UNIT_MILES_PER_H",
    })
    assert d.charging_rate_kmh == 16.1  # 10 mph


def test_931_km_per_hour_unit_leaves_value_alone() -> None:
    d = _map({
        "battery_state_report.charge_rate": "800",
        "battery_state_report.charge_rate_unit": "km_per_h",
    })
    assert d.charging_rate_kmh == 80


def test_931_missing_unit_leaves_value_alone() -> None:
    # "No unit" must never silently rescale an already-correct value.
    assert _map({"battery_state_report.charge_rate": "800"}).charging_rate_kmh == 80


def test_931_bff_camelcase_alias_stays_unscaled() -> None:
    # chargeRate_kmph is the BFF/OLA key and really is whole km/h.
    assert _map({"chargeRate_kmph": "80"}).charging_rate_kmh == 80


# ── #909: MBB operationList negative cache ──────────────────────────────────

def _oplist_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    from custom_components.vag_connect.cariad.models import TokenSet

    client = VWEUClient(MagicMock(), "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client


def _denied_get():
    from custom_components.vag_connect.cariad.exceptions import APIError

    return AsyncMock(
        side_effect=APIError(
            401, "https://mal-1a/api/operationlist",
            '{"error":"gw.error.authentication"}',
        )
    )


def test_909_denied_oplist_is_not_requested_again() -> None:
    client = _oplist_client()
    client._mbb_get = _denied_get()
    vin = "WVWZZZ7AZRE000123"
    assert asyncio.run(client._get_mbb_operationlist(vin)) is None
    assert asyncio.run(client._get_mbb_operationlist(vin)) is None
    assert asyncio.run(client._get_mbb_operationlist(vin)) is None
    assert client._mbb_get.await_count == 1


def test_909_denial_is_per_vin() -> None:
    client = _oplist_client()
    client._mbb_get = _denied_get()
    assert asyncio.run(client._get_mbb_operationlist("VIN_A")) is None
    assert asyncio.run(client._get_mbb_operationlist("VIN_B")) is None
    assert client._mbb_get.await_count == 2


def test_909_force_refresh_bypasses_the_denial() -> None:
    """A command pre-flight is an explicit user action — never blocked by it."""
    client = _oplist_client()
    client._mbb_get = _denied_get()
    asyncio.run(client._get_mbb_operationlist("VIN_A"))
    asyncio.run(client._get_mbb_operationlist("VIN_A", force_refresh=True))
    assert client._mbb_get.await_count == 2


def test_909_denial_logged_once_at_warning_then_debug(caplog) -> None:
    import logging

    client = _oplist_client()
    client._mbb_get = _denied_get()
    with caplog.at_level(logging.DEBUG):
        asyncio.run(client._get_mbb_operationlist("VIN_A"))
        asyncio.run(client._get_mbb_operationlist("VIN_A", force_refresh=True))
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "gw.error.authentication" in r.getMessage()
    ]
    assert len(warnings) == 1


def test_909_acl_403_is_negative_cached_too() -> None:
    """The rolesandrights ACL rejection is just as final as the gateway one."""
    from custom_components.vag_connect.cariad.exceptions import APIError

    client = _oplist_client()
    client._mbb_get = AsyncMock(
        side_effect=APIError(
            403, "https://mal-1a/api/operationlist",
            '{"error":{"errorCode":"mbbc.rolesandrights.unauthorized"}}',
        )
    )
    asyncio.run(client._get_mbb_operationlist("VIN_A"))
    asyncio.run(client._get_mbb_operationlist("VIN_A"))
    assert client._mbb_get.await_count == 1


def test_909_other_statuses_are_not_negative_cached() -> None:
    """A 500 is transient — it must keep being retried."""
    from custom_components.vag_connect.cariad.exceptions import APIError

    client = _oplist_client()
    client._mbb_get = AsyncMock(
        side_effect=APIError(500, "https://mal-1a/api/operationlist", "boom")
    )
    asyncio.run(client._get_mbb_operationlist("VIN_A"))
    asyncio.run(client._get_mbb_operationlist("VIN_A"))
    assert client._mbb_get.await_count == 2


def test_909_hard_auth_setup_error_asks_for_reauth() -> None:
    """A stop that only a human can clear must not loop ConfigEntryNotReady."""
    from custom_components.vag_connect import _HARD_AUTH_SETUP_ERRORS

    for reason in (
        "invalid_credentials", "two_factor_required", "email_two_factor_required",
        "terms_and_conditions", "marketing_consent", "portal_interaction_required",
    ):
        assert reason in _HARD_AUTH_SETUP_ERRORS
    # A rate limit clears by itself — it stays a retry.
    assert "too_many_requests" not in _HARD_AUTH_SETUP_ERRORS


# ── #933: our own rate-limit cooldown is self-healing ───────────────────────

def test_933_synthetic_cooldown_is_selfhealing() -> None:
    from custom_components.vag_connect.cariad.exceptions import APIError
    from custom_components.vag_connect.coordinator import _is_selfhealing_poll_error

    err = APIError(
        429, "https://emea.bff.cariad.digital/x",
        "rate-limit lockout active — 300s remaining (account cooldown)",
    )
    assert _is_selfhealing_poll_error(err) is True


def test_933_backend_throttle_is_selfhealing_too() -> None:
    from custom_components.vag_connect.cariad.exceptions import APIError
    from custom_components.vag_connect.coordinator import _is_selfhealing_poll_error

    assert _is_selfhealing_poll_error(APIError(429, "u", "Too Many Requests")) is True


def test_933_real_failures_still_escalate() -> None:
    from custom_components.vag_connect.cariad.exceptions import APIError
    from custom_components.vag_connect.coordinator import _is_selfhealing_poll_error

    assert _is_selfhealing_poll_error(APIError(403, "u", "not_entitled")) is False
    assert _is_selfhealing_poll_error(APIError(404, "u", "")) is False


# ── #923: an empty parkingposition keeps the last known position ────────────

def test_923_empty_parking_data_leaves_position_unset() -> None:
    client = _vw_eu_client()
    d = client._parse_status("VIN1", {}, {"data": {}})
    assert d.latitude is None
    assert d.longitude is None


def test_923_half_a_position_is_not_written() -> None:
    """A lone lat with no lon used to land as a half-position (lat set, lon
    blanked) — neither is usable, so neither is written."""
    client = _vw_eu_client()
    d = client._parse_status("VIN1", {}, {"data": {"lat": 48.1}})
    assert d.latitude is None
    assert d.longitude is None


def test_923_real_parking_data_still_parsed() -> None:
    client = _vw_eu_client()
    d = client._parse_status("VIN1", {}, {"data": {"lat": 48.1, "lon": 11.5}})
    assert d.latitude == 48.1
    assert d.longitude == 11.5


def test_923_previous_position_carried_over_empty_poll() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile

    previous = {"latitude": 48.1, "longitude": 11.5}
    merged, _notes = reconcile(previous, {"latitude": None, "longitude": None})
    assert merged["latitude"] == 48.1
    assert merged["longitude"] == 11.5


def test_923_fresh_position_still_wins() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile

    previous = {"latitude": 48.1, "longitude": 11.5}
    merged, _notes = reconcile(previous, {"latitude": 52.5, "longitude": 13.4})
    assert merged["latitude"] == 52.5
    assert merged["longitude"] == 13.4
