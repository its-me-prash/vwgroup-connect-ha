# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche oil level, Connect contract, OTA start and service reset.

Shapes from My Porsche 21.26.46:

- ``OIL_LEVEL_CURRENT.value`` is ``{lastModified?, percent}``,
  ``OIL_LEVEL_MAX.value`` is ``{lastModified?, liters}``. A percent must not
  be scaled against a litre figure.
- ``CONNECT_CONTRACT.value`` is ``{lastModified?, isEnabled, until?}``;
  ``until`` is a timestamp.
- ``OTA_UPDATE_REMOTE_START`` takes ``{spin?, updateId, campaignCode?}``.
- ``SERVICE_PREDICTIONS_RESET`` takes ``{spin?, id, expirationDate,
  odometerLastReset}``. The app fills ``expirationDate`` from an optional
  date (its start of day as an instant, or the text "null" when there is
  none) and ``odometerLastReset`` from the current mileage.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.porsche import PorscheClient
from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

_VIN = "WP0ZZZ99ZTS300001"


def _client() -> PorscheClient:
    return PorscheClient.__new__(PorscheClient)


async def _status(measurements: list[dict]) -> object:
    c = _client()
    c._get = AsyncMock(return_value={"measurements": measurements})
    return await c.get_status(_VIN)


def _m(key: str, value: dict, enabled: bool = True) -> dict:
    return {"key": key, "status": {"isEnabled": enabled}, "value": value}


class TestOilLevel:
    @pytest.mark.asyncio
    async def test_percent_is_taken_as_it_stands(self) -> None:
        d = await _status([
            _m("OIL_LEVEL_CURRENT", {"percent": 25}),
            _m("OIL_LEVEL_MAX", {"liters": 2.0}),
        ])
        assert d.oil_level_pct == 25

    @pytest.mark.asyncio
    async def test_low_percent_is_not_scaled_against_litres(self) -> None:
        d = await _status([
            _m("OIL_LEVEL_CURRENT", {"percent": 2}),
            _m("OIL_LEVEL_MAX", {"liters": 8.0}),
        ])
        assert d.oil_level_pct == 2

    @pytest.mark.asyncio
    async def test_one_percent_stays_one_percent(self) -> None:
        d = await _status([_m("OIL_LEVEL_CURRENT", {"percent": 1})])
        assert d.oil_level_pct == 1

    @pytest.mark.asyncio
    async def test_value_without_percent_keeps_the_earlier_reading(self) -> None:
        """Fallback for a shape without ``percent``: a 0..1 ratio."""
        d = await _status([_m("OIL_LEVEL_CURRENT", {"value": 0.6})])
        assert d.oil_level_pct == 60


class TestConnectContract:
    @pytest.mark.asyncio
    async def test_contract_flag_and_end_date_from_the_value(self) -> None:
        d = await _status([
            _m("CONNECT_CONTRACT", {"isEnabled": False, "until": "2026-01-31T00:00:00Z"}),
        ])
        assert d.connect_contract_active is False
        assert d.subscription_expiry_at == "2026-01-31T00:00:00Z"
        assert d.subscription_days_remaining is not None
        assert d.subscription_days_remaining < 0

    @pytest.mark.asyncio
    async def test_active_contract_with_future_end(self) -> None:
        d = await _status([
            _m("CONNECT_CONTRACT", {"isEnabled": True, "until": "2999-01-01T00:00:00Z"}),
        ])
        assert d.connect_contract_active is True
        assert d.subscription_expiry_at == "2999-01-01T00:00:00Z"
        assert d.subscription_days_remaining > 0

    @pytest.mark.asyncio
    async def test_disabled_measurement_still_means_inactive(self) -> None:
        d = await _status([_m("CONNECT_CONTRACT", {}, enabled=False)])
        assert d.connect_contract_active is False
        assert d.subscription_expiry_at is None

    @pytest.mark.asyncio
    async def test_enabled_measurement_without_value_keeps_active(self) -> None:
        d = await _status([{"key": "CONNECT_CONTRACT", "status": {"isEnabled": True}}])
        assert d.connect_contract_active is True
        assert d.subscription_expiry_at is None

    @pytest.mark.asyncio
    async def test_unparseable_end_date_is_left_out(self) -> None:
        d = await _status([_m("CONNECT_CONTRACT", {"isEnabled": True, "until": "soon-ish"})])
        assert d.connect_contract_active is True
        assert d.subscription_expiry_at is None
        assert d.subscription_days_remaining is None


class TestOtaStart:
    @pytest.mark.asyncio
    async def test_given_update_id_goes_into_the_payload(self) -> None:
        c = _client()
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_start_ota_update(_VIN, update_id="U-1")
        body = c._post.call_args.kwargs["json"]
        assert body == {"key": "OTA_UPDATE_REMOTE_START", "payload": {"spin": None, "updateId": "U-1"}}

    @pytest.mark.asyncio
    async def test_update_id_read_from_update_details(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": [
            _m("OTA_UPDATE_DETAILS", {"updateId": "U-2", "updateState": "READY"}),
        ]})
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_start_ota_update(_VIN)
        params = dict(c._get.call_args.kwargs["params"])
        assert params["mf"] == "OTA_UPDATE_DETAILS"
        assert c._post.call_args.kwargs["json"]["payload"] == {"spin": None, "updateId": "U-2"}

    @pytest.mark.asyncio
    async def test_no_pending_update_sends_nothing(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": []})
        c._post = AsyncMock()
        with pytest.raises(VehicleCommandError):
            await c.command_start_ota_update(_VIN)
        c._post.assert_not_called()


class TestServicePredictionReset:
    @pytest.mark.asyncio
    async def test_reset_with_date_and_current_mileage(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": [_m("MILEAGE", {"kilometers": 12345})]})
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_reset_service_predictions(_VIN, "BRAKE_FLUID", expiration_date=date(2027, 5, 1))
        assert dict(c._get.call_args.kwargs["params"])["mf"] == "MILEAGE"
        body = c._post.call_args.kwargs["json"]
        assert body == {"key": "SERVICE_PREDICTIONS_RESET", "payload": {
            "spin": None, "id": "BRAKE_FLUID",
            "expirationDate": "2027-05-01T00:00:00Z", "odometerLastReset": 12345,
        }}

    @pytest.mark.asyncio
    async def test_reset_without_date_sends_the_app_placeholder(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": [_m("MILEAGE", {"kilometers": 800})]})
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_reset_service_predictions(_VIN, "OIL")
        payload = c._post.call_args.kwargs["json"]["payload"]
        assert payload["expirationDate"] == "null"
        assert payload["odometerLastReset"] == 800

    @pytest.mark.asyncio
    async def test_unknown_mileage_sends_no_odometer(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={"measurements": []})
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_reset_service_predictions(_VIN, "OIL")
        assert c._post.call_args.kwargs["json"]["payload"]["odometerLastReset"] is None
