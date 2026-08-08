# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda unlock S-PIN body + route — v2 migration (MyŠkoda 8.15.0).

History: b13 (8.13.0) found the v1 SpinDto wire key was ``currentSpin``. In
8.15.0 the app migrated vehicle-access to v2 (bff_vehicle_access/v2, v1 is
compiled-but-unwired): the unlock body is now ``AccessRequestDto`` with the key
renamed ``currentSpin`` → ``spin``, on ``POST api/v2/vehicle-access/{vin}/unlock``.
Grounded: bff_vehicle_access/v2/VehicleAccessApi.smali + AccessRequestDto.smali.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient


def _client() -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._post = AsyncMock(return_value={})
    return c


def test_unlock_sends_spin_on_v2_route() -> None:
    c = _client()
    asyncio.run(c.command_unlock("TMBVIN0000000001", spin="1234"))
    url = c._post.call_args.args[0]
    body = c._post.call_args.kwargs["json"]
    assert url.endswith("/api/v2/vehicle-access/TMBVIN0000000001/unlock")
    assert body == {"spin": "1234"}
    assert "currentSpin" not in body  # renamed in v2


def test_unlock_without_spin_sends_empty_body() -> None:
    c = _client()
    c._spin = ""
    asyncio.run(c.command_unlock("TMBVIN0000000001"))
    assert c._post.call_args.kwargs["json"] == {}
