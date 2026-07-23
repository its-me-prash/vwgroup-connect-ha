# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.23.1 — Audi S6 device-page cleanup: localise dynamic names + de-dup.

Three fixes, verified live on a real diesel Audi S6 (German HA):
1. The per-part door / window / light binary sensors hardcoded English into
   ``_attr_name`` — they now use a ``translation_key`` so the name localises.
2. The range family collapses to one value on a single-energy car, so the
   redundant total_range_km / combustion_range_km are gated off there (hybrids
   keep all three).
3. ``primary_engine_fuel_level_pct`` duplicates ``fuel_level`` — demoted to a
   disabled-by-default diagnostic (not deleted).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from homeassistant.const import EntityCategory

from custom_components.vag_connect.binary_sensor import (
    VagDoorSensor,
    VagLightSensor,
    VagWindowSensor,
)
from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS


def _coord():
    c = MagicMock()
    c.data = {}
    return c


# ── Fix 1: dynamic sensors use translation_key, not hardcoded English ────────

def test_door_sensor_uses_translation_key() -> None:
    d = VagDoorSensor(_coord(), "VIN", "frontLeft")
    assert d._attr_translation_key == "door_front_left"
    assert getattr(d, "_attr_name", None) is None
    assert d.unique_id == "VIN_door_frontLeft"  # entity id unchanged (camelCase)


def test_door_trunk_and_bonnet_translation_keys() -> None:
    assert VagDoorSensor(_coord(), "V", "trunk")._attr_translation_key == "door_trunk"
    assert VagDoorSensor(_coord(), "V", "bonnet")._attr_translation_key == "door_bonnet"


def test_window_sensor_uses_translation_key() -> None:
    w = VagWindowSensor(_coord(), "V", "rearRight")
    assert w._attr_translation_key == "window_rear_right"
    assert getattr(w, "_attr_name", None) is None


def test_light_left_right_use_translation_key() -> None:
    assert VagLightSensor(_coord(), "V", "left")._attr_translation_key == "light_left"
    assert VagLightSensor(_coord(), "V", "right")._attr_translation_key == "light_right"


def test_unknown_light_keeps_readable_fallback() -> None:
    # an open-ended CARIAD light name we ship no translation for must not point
    # at a missing translation_key (empty name) — keep the plain fallback.
    lg = VagLightSensor(_coord(), "V", "dippedBeam")
    assert getattr(lg, "_attr_translation_key", None) is None
    assert lg._attr_name == "Light dippedBeam"


# ── Fix 3: primary_engine_fuel_level_pct demoted (not deleted) ───────────────

def test_primary_fuel_level_is_disabled_diagnostic() -> None:
    desc = next(
        d for d in SENSOR_DESCRIPTIONS if d.key == "primary_engine_fuel_level_pct"
    )
    assert desc.entity_category == EntityCategory.DIAGNOSTIC
    assert desc.entity_registry_enabled_default is False
    # still present (not deleted) so existing entity_ids survive
    assert desc.data_key == "primary_engine_fuel_level_pct"


# ── Fix 2: range de-dup on single-energy cars ────────────────────────────────

def _built_keys(vehicle: dict) -> set[str]:
    """Run sensor.async_setup_entry for one vehicle and return the sensor keys.

    Mirrors the pattern in tests/test_entities.py — a mock coordinator + a
    capturing async_add_entities.
    """
    from custom_components.vag_connect import sensor as sensor_mod

    coord = MagicMock()
    coord.is_read_only = MagicMock(return_value=False)
    coord.data = {"VINX": vehicle}
    coord.vehicles = coord.data
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "audi"}
    coord.command_capability_supported = MagicMock(return_value=True)
    entry = MagicMock()
    entry.runtime_data = coord
    added: list = []

    def _collect(entities, **kw):
        added.extend(entities)

    asyncio.run(sensor_mod.async_setup_entry(MagicMock(), entry, _collect))
    return {
        e.entity_description.key
        for e in added
        if hasattr(e, "entity_description")
    }


_COMBUSTION = {
    "vin": "VINX", "has_battery": False, "has_combustion": True,
    "range_km": 890, "combustion_range_km": 890, "total_range_km": 890,
}
_HYBRID = {
    "vin": "VINX", "has_battery": True, "has_combustion": True,
    "range_km": 60, "combustion_range_km": 500, "total_range_km": 560,
    "electric_range_km": 60,
}


def test_single_energy_car_hides_redundant_range_sensors() -> None:
    keys = _built_keys(_COMBUSTION)
    assert "range_km" in keys  # the single headline stays
    assert "total_range_km" not in keys  # redundant, hidden
    assert "combustion_range_km" not in keys  # equals range_km → hidden


def test_hybrid_keeps_all_three_ranges() -> None:
    keys = _built_keys(_HYBRID)
    assert "range_km" in keys
    assert "total_range_km" in keys  # genuinely distinct on a hybrid
    assert "combustion_range_km" in keys
