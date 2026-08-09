# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MyŠkoda 8.15.0 net-new reads (APK-grounded): seat-heating state + camping end.

air-conditioning.seatHeatingActivated is a SeatHeatingSettingsDto
{frontLeft,frontRight,rearLeft,rearRight} of nullable Booleans; we fold it into
the single seat_heating flag (any seat on). CampingModeDto carries {enabled,
endsAt}; endsAt is surfaced as the camping auto-stop time.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient

VIN = "TMBJJ7NX1M0000003"


def _client(ac_payload: dict) -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")

    async def _fake_get(url: str, **kw: object):
        if url.endswith(f"/air-conditioning/{VIN}"):
            return ac_payload
        return {}

    c._get = AsyncMock(side_effect=_fake_get)  # type: ignore[method-assign]
    c.get_charging_statistics = AsyncMock(return_value={})  # type: ignore[method-assign]
    return c


def _status(ac_payload: dict):
    return asyncio.run(_client(ac_payload).get_status(VIN))


def test_seat_heating_any_seat_on() -> None:
    d = _status({"seatHeatingActivated": {
        "frontLeft": True, "frontRight": False, "rearLeft": None, "rearRight": None,
    }})
    assert d.seat_heating is True


def test_seat_heating_all_off() -> None:
    d = _status({"seatHeatingActivated": {
        "frontLeft": False, "frontRight": False,
        "rearLeft": False, "rearRight": False,
    }})
    assert d.seat_heating is False


def test_seat_heating_absent_stays_none() -> None:
    d = _status({})
    assert d.seat_heating is None  # phantom-gate: not reported → no sensor


def test_camping_ends_at_parsed() -> None:
    d = _status({"campingMode": {"enabled": True, "endsAt": "2026-08-08T20:30:00Z"}})
    assert d.camping_mode is True
    assert d.camping_ends_at is not None
    assert d.camping_ends_at.hour == 20 and d.camping_ends_at.minute == 30


def test_camping_without_endsat_leaves_it_none() -> None:
    d = _status({"campingMode": {"enabled": False}})
    assert d.camping_mode is False
    assert d.camping_ends_at is None


def test_aux_heating_active_from_top_level_state() -> None:
    # The top-level AirConditioningStateDto enum includes HEATING_AUXILIARY,
    # so the aux-heating switch's read-state comes free from the AC GET.
    assert _status({"state": "HEATING_AUXILIARY"}).aux_heating_active is True
    assert _status({"state": "COOLING"}).aux_heating_active is False
