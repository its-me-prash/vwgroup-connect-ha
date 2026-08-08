# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MyŠkoda 8.15.0 P2 net-new reads + capabilities re-source (APK-grounded)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient

VIN = "TMBJJ7NX1M0000004"


def _client(routes: dict[str, dict]) -> SkodaClient:
    """routes: url-suffix -> payload. Everything else returns {}."""
    c = SkodaClient(MagicMock(), "u@t.de", "pw")

    async def _fake_get(url: str, **kw: object):
        for suffix, payload in routes.items():
            if url.endswith(suffix):
                return payload
        return {}

    c._get = AsyncMock(side_effect=_fake_get)  # type: ignore[method-assign]
    c.get_charging_statistics = AsyncMock(return_value={})  # type: ignore[method-assign]
    return c


def _status(routes: dict[str, dict]):
    return asyncio.run(_client(routes).get_status(VIN))


# ── preferredChargeMode + availableChargeModes ───────────────────────────────

def test_preferred_and_available_charge_modes() -> None:
    d = _status({f"/charging/{VIN}": {
        "status": {"battery": {"stateOfChargeInPercent": 60}},
        "settings": {
            "preferredChargeMode": "MANUAL",
            "availableChargeModes": ["MANUAL", "PREFERRED_CHARGING_TIMES"],
        },
    }})
    assert d.preferred_charge_mode == "MANUAL"
    assert d.available_charge_modes == ["MANUAL", "PREFERRED_CHARGING_TIMES"]


# ── windowHeatingState.unspecified fold ──────────────────────────────────────

def test_window_heating_unspecified_folds_into_both() -> None:
    d = _status({f"/air-conditioning/{VIN}": {
        "windowHeatingState": {"unspecified": "ON"},
    }})
    assert d.window_heating_front is True
    assert d.window_heating_back is True


def test_window_heating_specific_channels_win() -> None:
    d = _status({f"/air-conditioning/{VIN}": {
        "windowHeatingState": {"front": "ON", "rear": "OFF", "unspecified": "ON"},
    }})
    assert d.window_heating_front is True
    assert d.window_heating_back is False  # explicit rear=OFF beats unspecified


# ── remainingCruisingRangeInMeters fallback ──────────────────────────────────

def test_electric_range_fallback_from_charging_block() -> None:
    # No driving-range endpoint data → the charging battery's cruising range
    # (metres) fills electric_range_km.
    d = _status({f"/charging/{VIN}": {
        "status": {"battery": {
            "stateOfChargeInPercent": 70,
            "remainingCruisingRangeInMeters": 348000,
        }},
    }})
    assert d.electric_range_km == 348


def test_driving_range_overrides_the_fallback() -> None:
    d = _status({
        f"/charging/{VIN}": {"status": {"battery": {
            "stateOfChargeInPercent": 70,
            "remainingCruisingRangeInMeters": 348000,
        }}},
        f"/vehicle-status/{VIN}/driving-range": {
            "primaryEngineRange": {"remainingRangeInKm": 400},
        },
    })
    assert d.electric_range_km == 400  # primary source wins


# ── capabilities re-source (garage VehicleDto) ───────────────────────────────

def test_get_capabilities_resourced_from_garage() -> None:
    c = _client({f"/garage/vehicles/{VIN}": {
        "vin": VIN,
        "capabilities": {"capabilities": [
            {"id": "CHARGING", "statuses": []},
            {"id": "AIR_CONDITIONING", "statuses": ["LICENSE_EXPIRED"]},
            {"bad": "no id"},
        ], "errors": []},
    }})
    caps = asyncio.run(c.get_capabilities(VIN))
    ids = [x["id"] for x in caps["capabilities"]]
    assert ids == ["CHARGING", "AIR_CONDITIONING"]  # the id-less entry dropped
    # statuses preserved; no synthetic active flag (never false-hide)
    assert caps["capabilities"][1]["statuses"] == ["LICENSE_EXPIRED"]
    assert "active" not in caps["capabilities"][0]
    # the URL is the garage vehicle doc, not the dead standalone route
    assert any("/garage/vehicles/" in url for (url,), _ in c._get.call_args_list)


def test_get_capabilities_empty_on_missing() -> None:
    c = _client({})  # garage GET returns {}
    assert asyncio.run(c.get_capabilities(VIN)) == {}
