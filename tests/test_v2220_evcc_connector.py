# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.22.0 — evcc connector: the normalized IEC-61851 charge-status helper.

evcc's custom-vehicle ``status`` parses the first char and throws on anything
unrecognised, so the helper must return strictly A/B/C for any car with
charging data, and None (no phantom sensor) for combustion cars. See docs/EVCC.md.
"""

from __future__ import annotations

from pathlib import Path

from custom_components.vag_connect.coordinator import evcc_charge_status


def test_charging_is_C() -> None:
    assert evcc_charge_status({"is_charging": True, "plug_connected": True}) == "C"


def test_conservation_charging_is_C() -> None:
    assert evcc_charge_status(
        {"charging_state": "conservationCharging", "plug_connected": True}
    ) == "C"


def test_plugged_idle_is_B() -> None:
    assert evcc_charge_status({"is_charging": False, "plug_connected": True}) == "B"


def test_unplugged_is_A() -> None:
    assert evcc_charge_status({"is_charging": False, "plug_connected": False}) == "A"


def test_ev_with_only_state_defaults_to_A_not_none() -> None:
    # readyForCharging etc. → not charging, unknown plug → A (never None/unknown).
    assert evcc_charge_status({"charging_state": "readyForCharging"}) == "A"


def test_combustion_no_charging_data_is_none() -> None:
    # No charging fields at all → None → the sensor never spawns (no phantom).
    assert evcc_charge_status({"fuel_level": 55, "odometer_km": 1000}) is None


def test_never_returns_unknown_for_any_charging_car() -> None:
    for d in (
        {"plug_connected": True},
        {"plug_connected": False},
        {"is_charging": True},
        {"is_charging": False},
        {"charging_state": "off"},
        {"charging_state": "charging"},
    ):
        assert evcc_charge_status(d) in {"A", "B", "C"}, d


def test_sensor_registered_electric_diagnostic_disabled_and_phantom_gated() -> None:
    from custom_components.vag_connect.sensor import (
        _DATA_PRESENT_REQUIRED,
        SENSOR_DESCRIPTIONS,
    )
    desc = next((d for d in SENSOR_DESCRIPTIONS if d.key == "evcc_charge_status"), None)
    assert desc is not None
    assert desc.condition == "electric"
    assert desc.entity_registry_enabled_default is False
    assert "evcc_charge_status" in _DATA_PRESENT_REQUIRED


def test_translation_in_all_locales() -> None:
    trans = Path("custom_components/vag_connect/translations")
    for f in trans.glob("*.json"):
        assert '"evcc_charge_status"' in f.read_text(encoding="utf-8"), f.name
