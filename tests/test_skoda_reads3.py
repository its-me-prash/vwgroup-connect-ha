# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda read-only diagnostics: service reminders + departure timers + consents.

All grounded against MyŠkoda 8.15.0 (PredictiveMaintenanceDto / DepartureTimerDto
/ Mandatory+MarketingConsentDto). Read-only — consent changes go through a
separate PATCH/Repair flow, never these reads.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.coordinator import (
    _parse_consents,
    _parse_departure_timers,
    _parse_predictive_maintenance,
)


def test_predictive_maintenance_due_or_status() -> None:
    out = _parse_predictive_maintenance({"reminders": [
        {"type": "TECHNICAL_INSPECTION", "dueDate": "2026-11-01", "status": "DUE_SOON"},
        {"type": "FIRST_AID_KIT", "status": "EXPIRED"},  # no dueDate → status
        {"type": "UNKNOWN_THING", "dueDate": "2027-01-01"},  # dropped
    ]})
    assert out["reminder_technical_inspection"] == "2026-11-01"
    assert out["reminder_first_aid_kit"] == "EXPIRED"
    assert "reminder_tyre_repair_kit" not in out
    assert _parse_predictive_maintenance({}) == {}


def test_departure_timers_time_and_count() -> None:
    out = _parse_departure_timers({"timers": [
        {"id": 1, "time": "07:30", "enabled": True},
        {"id": 2, "time": "17:00", "enabled": False},
        {"id": 9, "time": "23:00", "enabled": True},   # out of 1..3 range → dropped
    ]})
    assert out["departure_timer_1_time"] == "07:30"
    assert out["departure_timer_2_time"] == "17:00"
    assert "departure_timer_9_time" not in out
    assert out["departure_timer_enabled_count"] == 1


def test_consents_bools_and_link() -> None:
    out = _parse_consents({
        "mandatory": {"consented": False, "termsAndConditionsLink": "https://x/tc"},
        "marketing": {"consented": True, "title": "News", "text": "…"},
    })
    assert out["mandatory_consent_given"] is False
    assert out["mandatory_consent_link"] == "https://x/tc"
    assert out["marketing_consent_given"] is True
    assert _parse_consents({}) == {}


def test_client_routes() -> None:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._get = AsyncMock(return_value={})  # type: ignore[method-assign]
    asyncio.run(c.get_predictive_maintenance("VIN1"))
    assert c._get.call_args.args[0].endswith("/api/v2/predictive-maintenance/vehicles/VIN1")
    asyncio.run(c.get_departure_timers("VIN1"))
    assert c._get.call_args.args[0].endswith("/api/v1/vehicle-automatization/VIN1/departure/timers")
    asyncio.run(c.get_consents())
    urls = [call.args[0] for call in c._get.call_args_list]
    assert any(u.endswith("/api/v2/consents/mandatory") for u in urls)
    assert any(u.endswith("/api/v2/consents/marketing") for u in urls)


@pytest.mark.asyncio
async def test_refresh_is_skoda_only() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    c.entry.data = {"brand": "volkswagen"}
    c._cariad_client = MagicMock()
    c._cariad_client.get_predictive_maintenance = AsyncMock(return_value={})
    await c.refresh_predictive_maintenance("V")
    c._cariad_client.get_predictive_maintenance.assert_not_awaited()  # non-Škoda no-op
