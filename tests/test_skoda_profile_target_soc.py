# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-location target SoC write (#25) — MyŠkoda 8.15.0 (APK-grounded, LIVE-GATED).

A per-location target lives on a charging PROFILE, not the global set-charge-limit.
The app echoes the WHOLE profile on PUT api/v1/charging/{vin}/profiles/{id}
(no partial PATCH); we read, mutate only settings.targetStateOfChargeInPercent,
and echo it back.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient

_PROFILES = {
    "chargingProfiles": [
        {"id": 1, "name": "Home",
         "settings": {"maxChargingCurrent": "MAXIMUM",
                      "targetStateOfChargeInPercent": 80,
                      "autoUnlockPlugWhenCharged": "PERMANENT"},
         "timers": [{"id": 1, "enabled": False}],
         "location": {"latitude": 47.39, "longitude": 8.21}},
        {"id": 2, "name": "Work",
         "settings": {"targetStateOfChargeInPercent": 60}},
    ],
    "currentVehiclePositionProfile": {"id": 1, "name": "Home"},
}


def _client() -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c.get_charging_profiles = AsyncMock(return_value={  # type: ignore[method-assign]
        "chargingProfiles": [dict(p, settings=dict(p["settings"]))
                             for p in _PROFILES["chargingProfiles"]],
        "currentVehiclePositionProfile": _PROFILES["currentVehiclePositionProfile"],
    })
    c._put = AsyncMock()  # type: ignore[method-assign]
    return c


def test_puts_full_profile_with_mutated_soc() -> None:
    c = _client()
    asyncio.run(c.command_set_profile_target_soc("VIN1", 1, 90))
    url = c._put.call_args.args[0]
    body = c._put.call_args.kwargs["json"]
    assert url.endswith("/api/v1/charging/VIN1/profiles/1")
    # full profile echoed (name, timers, location preserved) …
    assert body["name"] == "Home"
    assert body["timers"] == [{"id": 1, "enabled": False}]
    assert body["location"] == {"latitude": 47.39, "longitude": 8.21}
    # … with only the target SoC changed, under the PROFILE key (not the global one)
    assert body["settings"]["targetStateOfChargeInPercent"] == 90
    assert "targetSOCInPercent" not in body["settings"]
    # sibling settings untouched
    assert body["settings"]["autoUnlockPlugWhenCharged"] == "PERMANENT"


def test_only_the_named_profile_is_written() -> None:
    c = _client()
    asyncio.run(c.command_set_profile_target_soc("VIN1", 2, 100))
    url = c._put.call_args.args[0]
    body = c._put.call_args.kwargs["json"]
    assert url.endswith("/profiles/2")
    assert body["name"] == "Work"
    assert body["settings"]["targetStateOfChargeInPercent"] == 100


def test_unknown_profile_raises() -> None:
    c = _client()
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(c.command_set_profile_target_soc("VIN1", 99, 80))
    c._put.assert_not_awaited()
