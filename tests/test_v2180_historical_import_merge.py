# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase C — importing the one-time export gap-fills config, never clobbers live.

`async_import_historical_export` fetches the historical export and merges its
config fields (min_soc, target temps, timer profiles) into the live snapshot.
The one rule that matters: it fills a field ONLY where the live snapshot has
none. Live telemetry — SoC, charging state, and above all the drivetrain flags
— must survive untouched, so the legacy dialect's "looks electric" config dump
can never flip a live PHEV to electric.
"""
from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import VagConnectCoordinator


class _Portal:
    def __init__(self, historical: VehicleData) -> None:
        self._historical = historical
        self.calls: list[str] = []

    async def get_vehicle_data(self, vin: str, request_type: str = "partial") -> VehicleData:
        self.calls.append(request_type)
        return self._historical


def _coord(historical: VehicleData, current: Any) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = MagicMock()
    c._cariad_client._eu_portal = _Portal(historical)
    c.vehicles = {"V": current} if current is not None else {}
    c._vehicles_lock = threading.Lock()
    c.pushed: list[dict] = []
    c.async_set_updated_data = lambda data: c.pushed.append(data)  # type: ignore[assignment]
    return c


@pytest.mark.asyncio
async def test_config_field_fills_a_gap() -> None:
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.min_soc = 50
    c = _coord(hist, {"soc": 80})  # live snapshot, no min_soc
    ok = await c.async_import_historical_export("V")
    assert ok is True
    assert c.vehicles["V"]["min_soc"] == 50
    assert c._cariad_client._eu_portal.calls == ["all"]  # read the historical type


@pytest.mark.asyncio
async def test_live_value_is_never_overwritten() -> None:
    # Historical carries an OLD soc; the live snapshot's soc must win.
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.battery_soc = 15  # stale config-dump value
    hist.min_soc = 50
    c = _coord(hist, {"battery_soc": 80})  # fresh live soc
    await c.async_import_historical_export("V")
    assert c.vehicles["V"]["battery_soc"] == 80  # live preserved
    assert c.vehicles["V"]["min_soc"] == 50  # gap still filled


@pytest.mark.asyncio
async def test_drivetrain_flag_not_flipped() -> None:
    # The legacy dialect has no combustion evidence → is_electric True. A live
    # PHEV (is_hybrid True) must NOT be flipped to electric by the import.
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.is_electric = True
    hist.is_hybrid = False
    c = _coord(hist, {"is_hybrid": True, "is_electric": False})
    await c.async_import_historical_export("V")
    assert c.vehicles["V"]["is_hybrid"] is True
    assert c.vehicles["V"]["is_electric"] is False


@pytest.mark.asyncio
async def test_no_data_returns_false_and_pushes_nothing() -> None:
    hist = VehicleData(vin="V")
    hist.no_data = True  # ZIP not ready yet
    c = _coord(hist, {"soc": 80})
    assert await c.async_import_historical_export("V") is False
    assert c.pushed == []


@pytest.mark.asyncio
async def test_portal_only_car_takes_the_snapshot() -> None:
    # A car we have nothing live for yet → adopt the historical snapshot.
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.min_soc = 50
    c = _coord(hist, None)  # no current entry
    assert await c.async_import_historical_export("V") is True
    assert c.vehicles["V"]["min_soc"] == 50


@pytest.mark.asyncio
async def test_portal_not_ready_raises() -> None:
    from homeassistant.exceptions import ServiceValidationError

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = MagicMock(spec=[])  # no _eu_portal
    with pytest.raises(ServiceValidationError):
        await c.async_import_historical_export("V")


def _coord_supplementary(historical: VehicleData, current: Any) -> VagConnectCoordinator:
    """A MERGED setup: the portal is a supplementary channel on a command
    primary, so ``_eu_portal`` is None and only ``_supplementary_eu_portal`` is
    armed (#923)."""
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = MagicMock()
    c._cariad_client._eu_portal = None                       # no primary portal
    c._cariad_client._supplementary_eu_portal = _Portal(historical)
    c.vehicles = {"V": current} if current is not None else {}
    c._vehicles_lock = threading.Lock()
    c.pushed = []
    c.async_set_updated_data = lambda data: c.pushed.append(data)  # type: ignore[assignment]
    return c


@pytest.mark.asyncio
async def test_923_supplementary_portal_import_uses_it() -> None:
    """#923 end-to-end guard: on a merged ``eu_data_act+website_authproxy`` setup
    the historical export must import through ``_supplementary_eu_portal`` — the
    export button now spawns there, so the import path has to follow. Before the
    fix this raised ``historical_portal_not_ready`` because only ``_eu_portal``
    was checked."""
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.min_soc = 50
    c = _coord_supplementary(hist, {"soc": 80})
    ok = await c.async_import_historical_export("V")
    assert ok is True
    assert c.vehicles["V"]["min_soc"] == 50
    assert c._cariad_client._supplementary_eu_portal.calls == ["all"]


@pytest.mark.asyncio
async def test_923_supplementary_import_still_gap_fill_only() -> None:
    """#923 — the supplementary path keeps the gap-fill-only contract: a live
    value is never overwritten by the historical config dump."""
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.battery_soc = 15          # stale config-dump value
    hist.min_soc = 50
    c = _coord_supplementary(hist, {"battery_soc": 80})   # fresh live soc
    await c.async_import_historical_export("V")
    assert c.vehicles["V"]["battery_soc"] == 80           # live preserved
    assert c.vehicles["V"]["min_soc"] == 50               # gap filled


def test_both_services_are_registered() -> None:
    # The two Phase C services must be wired into the registration table.
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "custom_components/vag_connect/__init__.py"
    ).read_text(encoding="utf-8")
    assert '"request_historical_export"' in src
    assert '"import_historical_export"' in src
    assert "async_request_historical_export" in src
    assert "async_import_historical_export" in src


def test_both_services_are_documented() -> None:
    import pathlib

    yaml = (
        pathlib.Path(__file__).resolve().parents[1]
        / "custom_components/vag_connect/services.yaml"
    ).read_text(encoding="utf-8")
    assert "request_historical_export:" in yaml
    assert "import_historical_export:" in yaml
