# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.19.0 — Tibber Data API supplementary EV source (read-only gap-fill).

Covers the pure capability→VehicleData mapping, VIN extraction from externalId,
and the range unit handling. The OAuth2 token dance + coordinator merge wiring
are integration concerns tested separately.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._tibber_source import (
    map_tibber_device,
    vin_from_external_id,
    _range_to_km,
    _to_int_pct,
)

_VIN = "WVWZZZ1KZAW000000"


def _device(caps: list[dict], external_id: str = f"tibber:{_VIN}", category: str = "vehicle") -> dict:
    return {"externalId": external_id, "category": category, "capabilities": caps}


def test_full_vehicle_maps_all_fields() -> None:
    d = map_tibber_device(_device([
        {"id": "storage.stateOfCharge", "value": 62, "unit": "%"},
        {"id": "storage.targetStateOfCharge", "value": 80, "unit": "%"},
        {"id": "range.remaining", "value": 285000, "unit": "m"},
        {"id": "connector.status", "value": "connected"},
        {"id": "charging.status", "value": "charging"},
        {"id": "charging.current.max", "value": 16, "unit": "A"},
        {"id": "isOnline", "value": True},
    ]))
    assert d is not None
    assert d.vin == _VIN
    assert d.battery_soc == 62
    assert d.target_soc == 80
    assert d.range_km == 285 and d.electric_range_km == 285
    assert d.plug_connected is True
    assert d.charging_state == "charging" and d.is_charging is True
    assert d.charge_max_ac_setting == 16
    assert d.is_online is True
    assert d.has_battery is True


def test_partial_only_soc_is_sparse() -> None:
    d = map_tibber_device(_device([{"id": "storage.stateOfCharge", "value": 41, "unit": "%"}]))
    assert d is not None
    assert d.battery_soc == 41
    assert d.target_soc is None
    assert d.range_km is None
    assert d.charging_state is None


def test_idle_charging_status_not_charging() -> None:
    d = map_tibber_device(_device([
        {"id": "storage.stateOfCharge", "value": 50, "unit": "%"},
        {"id": "charging.status", "value": "idle"},
        {"id": "connector.status", "value": "disconnected"},
    ]))
    assert d.is_charging is False
    assert d.charging_state == "idle"
    assert d.plug_connected is False


def test_non_vehicle_device_returns_none() -> None:
    # a home battery / charger (no vehicle marker, no SoC) is skipped
    assert map_tibber_device(_device([{"id": "onOff", "value": True}], category="charger")) is None


def test_missing_vin_returns_none() -> None:
    assert map_tibber_device(_device(
        [{"id": "storage.stateOfCharge", "value": 50}], external_id="tibber:short",
    )) is None


def test_vin_extraction() -> None:
    assert vin_from_external_id(f"tibber:{_VIN}") == _VIN
    assert vin_from_external_id(_VIN) == _VIN
    assert vin_from_external_id("prefix:mid:" + _VIN) == _VIN
    assert vin_from_external_id("tibber:abc") is None  # too short
    assert vin_from_external_id(None) is None


def test_range_unit_handling() -> None:
    assert _range_to_km(285000, "m") == 285      # metres
    assert _range_to_km(285000, None) == 285     # default metres
    assert _range_to_km(177, "mi") == 285        # miles -> km (177 * 1.609)
    assert _range_to_km(285, "km") == 285        # already km
    assert _range_to_km(-1, "m") is None
    assert _range_to_km("n/a", "m") is None


def test_pct_bounds() -> None:
    assert _to_int_pct(62.4) == 62
    assert _to_int_pct(150) is None   # out of range
    assert _to_int_pct(None) is None
