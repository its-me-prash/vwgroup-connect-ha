# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2145 / #922 — the BFF answers selectivestatus with a structured 404
``error.code == 2104`` ("Car is not enrolled anymore.") for a car that has left
the account. That is not a transient hiccup, so the first hit arms the same 6 h
per-VIN backoff as the #1590 unserved path, logs one warning and records no
error for the reporter. Every other 404 keeps the strike path unchanged.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import (
    _SELECTIVESTATUS_UNSERVED_STRIKES,
    VWEUClient,
    _is_not_enrolled_404,
)
from custom_components.vag_connect.cariad.exceptions import APIError

_VIN = "WAUZZZF1ZPX000001"
_URL = "https://emea.bff.cariad.digital/vehicle/v1/vehicles/x/selectivestatus"
_BODY_2104 = (
    '{"error":{"retry":false,"message":"Not Found",'
    '"info":"Car is not enrolled anymore.","code":2104,"group":1}}'
)


def _client() -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._tokens = None
    c._base_for_vin = lambda vin: "https://emea.bff.cariad.digital"  # type: ignore[method-assign]
    return c


def _err(status: int, body: str) -> APIError:
    return APIError(status, _URL, body)


def test_helper_matches_only_404_with_code_2104() -> None:
    assert _is_not_enrolled_404(_err(404, _BODY_2104)) is True
    assert _is_not_enrolled_404(_err(404, '{"error":{"code":2105}}')) is False
    assert _is_not_enrolled_404(_err(404, '{"error":{"message":"Not Found"}}')) is False
    assert _is_not_enrolled_404(_err(404, "404 page not found")) is False
    assert _is_not_enrolled_404(_err(404, "")) is False
    assert _is_not_enrolled_404(_err(404, "[1,2]")) is False
    assert _is_not_enrolled_404(_err(404, '{"error":"x"}')) is False
    # the structured code decides, not the message text
    assert _is_not_enrolled_404(
        _err(404, '{"error":{"info":"Car is not enrolled anymore.","code":1}}')
    ) is False
    assert _is_not_enrolled_404(_err(500, _BODY_2104)) is False


@pytest.mark.asyncio
async def test_code_2104_backs_off_on_first_hit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    c = _client()
    c._get = AsyncMock(side_effect=_err(404, _BODY_2104))  # type: ignore[method-assign]
    with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect"):
        data = await c.get_status(_VIN)  # no raise: nothing for the reporter
        calls = c._get.call_count
        data2 = await c.get_status(_VIN)
    assert data.no_data is True
    assert data2.no_data is True
    assert _VIN in c.selectivestatus_unserved_vins
    assert c._get.call_count == calls, "backed-off VIN must not hit the endpoint"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "no longer enrolled" in warnings[0].getMessage()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        '{"error":{"message":"Not Found"}}',
        '{"error":{"retry":false,"message":"Not Found","code":2105,"group":1}}',
        "this is not json",
    ],
)
async def test_other_404_bodies_keep_the_strike_path(body: str) -> None:
    c = _client()
    c._get = AsyncMock(side_effect=_err(404, body))  # type: ignore[method-assign]
    for _ in range(_SELECTIVESTATUS_UNSERVED_STRIKES - 1):
        with pytest.raises(APIError):
            await c.get_status(_VIN)
    assert _VIN not in c.selectivestatus_unserved_vins
    data = await c.get_status(_VIN)
    assert data.no_data is True
    assert _VIN in c.selectivestatus_unserved_vins
