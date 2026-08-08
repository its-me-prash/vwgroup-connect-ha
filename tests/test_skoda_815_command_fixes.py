# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MyŠkoda 8.15.0 command-correctness fixes (APK-grounded, LIVE-GATED).

Grounded against the decoded MyŠkoda 8.15.0 app:
- vehicle-access migrated to v2 (bff_vehicle_access/v2/VehicleAccessApi): lock
  takes AccessRequestDto{spin} at POST api/v2/vehicle-access/{vin}/lock.
- auxiliary-heating/start requires a non-null ``spin``
  (StartAuxiliaryHeatingConfigurationDto) — the old empty {} never started it.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient


def _client() -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._post = AsyncMock()  # type: ignore[method-assign]
    c._spin = ""
    return c


def _url_body(c: SkodaClient) -> tuple[str, dict]:
    a = c._post.call_args
    return a.args[0], a.kwargs.get("json")


def test_lock_uses_v2_route_and_spin() -> None:
    c = _client()
    asyncio.run(c.command_lock("VIN1", spin="4321"))
    url, body = _url_body(c)
    assert url.endswith("/api/v2/vehicle-access/VIN1/lock")
    assert body == {"spin": "4321"}


def test_lock_without_spin_sends_empty_body() -> None:
    c = _client()
    asyncio.run(c.command_lock("VIN1"))
    url, body = _url_body(c)
    assert url.endswith("/api/v2/vehicle-access/VIN1/lock")
    assert body == {}  # spin nullable on v2 → empty body valid


def test_lock_falls_back_to_entry_spin() -> None:
    c = _client()
    c._spin = "0000"
    asyncio.run(c.command_lock("VIN1"))
    _, body = _url_body(c)
    assert body == {"spin": "0000"}


def test_aux_heating_sends_required_spin() -> None:
    c = _client()
    asyncio.run(c.command_start_aux_heating("VIN1", spin="1234"))
    url, body = _url_body(c)
    assert url.endswith("/api/v2/air-conditioning/VIN1/auxiliary-heating/start")
    assert body == {"spin": "1234"}  # required by StartAuxiliaryHeatingConfigurationDto
