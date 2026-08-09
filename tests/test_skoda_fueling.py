# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda pay-at-pump LAST fill-up — READ-ONLY consumption (8.15.0 APK).

Surfaces past-consumption data only (litres/cost/station/fuel/time) from
GET api/v2/fueling/sessions/latest. The POST that starts/pays a fueling session
is a prohibited financial transaction and must have NO client method — the last
test pins that invariant.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.coordinator import _parse_fueling

_SESSION = {
    "dateTime": "2026-08-07T14:22:00Z",
    "formattedCardName": "**** 6411",   # masked card — must NOT be surfaced
    "fuelName": "Diesel",
    "quantity": 42.7,
    "quantityUnit": "LITER",
    "price": {"total": 78.9, "currency": "CHF", "pricePerUnit": 1.85},
    "gasStation": {"name": "Socar Othmarsingen", "formattedAddress": "…"},
    "state": "PAYMENT_COMPLETE",
}


def test_parse_extracts_consumption_not_card() -> None:
    out = _parse_fueling(_SESSION)
    assert out["last_refuel_fuel_type"] == "Diesel"
    assert out["last_refuel_quantity"] == 42.7
    assert out["last_refuel_cost"] == 78.9
    assert out["last_refuel_currency"] == "CHF"
    assert out["last_refuel_station"] == "Socar Othmarsingen"
    assert out["last_refuel_at"] == "2026-08-07T14:22:00Z"
    # the masked card number is never surfaced
    assert not any("6411" in str(v) for v in out.values())
    assert not any("card" in k.lower() for k in out)


def test_parse_empty_is_empty() -> None:
    assert _parse_fueling({}) == {}
    assert _parse_fueling(None) == {}
    assert _parse_fueling({"state": "IN_PROGRESS"}) == {}  # no consumption yet


def test_client_read_hits_latest_route() -> None:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._get = AsyncMock(return_value=_SESSION)  # type: ignore[method-assign]
    out = asyncio.run(c.get_latest_fueling())
    assert c._get.call_args.args[0].endswith("/api/v2/fueling/sessions/latest")
    assert out["fuelName"] == "Diesel"


@pytest.mark.asyncio
async def test_refresh_is_skoda_only_and_merges() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    import threading

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    c.entry.data = {"brand": "skoda"}
    c._vehicles_lock = threading.Lock()
    c.vehicles = {"V": {"vin": "V"}}
    c._cariad_client = MagicMock()
    c._cariad_client.get_latest_fueling = AsyncMock(return_value=_SESSION)
    await c.refresh_fueling("V")
    assert c.vehicles["V"]["last_refuel_cost"] == 78.9

    # non-Škoda → no-op
    c2 = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c2.entry = MagicMock()
    c2.entry.data = {"brand": "volkswagen"}
    c2._cariad_client = MagicMock()
    c2._cariad_client.get_latest_fueling = AsyncMock(return_value=_SESSION)
    await c2.refresh_fueling("V")
    c2._cariad_client.get_latest_fueling.assert_not_awaited()


def test_no_fueling_write_method_exists() -> None:
    # House rule: never a method that starts/pays a fueling session (financial).
    for name, _ in inspect.getmembers(SkodaClient, predicate=inspect.isfunction):
        low = name.lower()
        if "fuel" in low:
            assert "get" in low or "latest" in low, (
                f"SkodaClient.{name} looks like a fueling write — the POST "
                f"session is a prohibited financial transaction"
            )
        assert "pay" not in low and "checkout" not in low
