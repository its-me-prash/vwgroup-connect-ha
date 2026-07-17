# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.2 (#513 Scout) — EU Data Act portal "charger detail" field mappings.

The portal surfaced a per-poll charger-detail block with new fields
(external_power_supply_state, energy_flow, charging_reason_trigger,
charging_state_error_code, remaining_charging_time_target_soc, led_color,
led_state). These map into new EU-Data-Act-dialect-only model fields; the
"0" charging error code is the "no error" sentinel and must drop to None.
The plumbing field ``echo`` must stay Scout-visible (no-suppress policy).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map_flatlog(*pairs: tuple[str, str]) -> VehicleData:
    """Build a flat-log payload [{dataFieldName, value}, ...] → mapped data."""
    payload = [{"dataFieldName": name, "value": value} for name, value in pairs]
    return map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))


def test_external_power_supply_state_maps() -> None:
    d = _map_flatlog(("external_power_supply_state", "available"))
    assert d.external_power_supply_state == "available"


def test_energy_flow_active_maps_truthy() -> None:
    d = _map_flatlog(("energy_flow", "on"))
    assert d.energy_flow_active is True


def test_energy_flow_active_maps_falsy() -> None:
    d = _map_flatlog(("energy_flow", "off"))
    assert d.energy_flow_active is False


def test_charging_reason_maps() -> None:
    d = _map_flatlog(("charging_reason_trigger", "immediate"))
    assert d.charging_reason == "immediate"


def test_charging_error_code_maps_real_code() -> None:
    d = _map_flatlog(("charging_state_error_code", "42"))
    assert d.charging_error_code == "42"


def test_charging_error_code_zero_is_none() -> None:
    # "0" (and "#0") are the portal's "no error" sentinels → None.
    d = _map_flatlog(("charging_state_error_code", "0"))
    assert d.charging_error_code is None


def test_charging_error_code_hash_zero_is_none() -> None:
    d = _map_flatlog(("charging_state_error_code", "#0"))
    assert d.charging_error_code is None


def test_remaining_time_target_soc_maps() -> None:
    d = _map_flatlog(("remaining_charging_time_target_soc", "maxSOC"))
    assert d.remaining_time_target_soc == "maxSOC"


def test_charge_led_color_maps() -> None:
    d = _map_flatlog(("led_color", "green"))
    assert d.charge_led_color == "green"


def test_charge_led_pattern_maps() -> None:
    d = _map_flatlog(("led_state", "pulse"))
    assert d.charge_led_pattern == "pulse"


def test_all_charger_detail_fields_together() -> None:
    d = _map_flatlog(
        ("external_power_supply_state", "available"),
        ("energy_flow", "on"),
        ("charging_reason_trigger", "immediate"),
        ("charging_state_error_code", "0"),
        ("remaining_charging_time_target_soc", "maxSOC"),
        ("led_color", "green"),
        ("led_state", "pulse"),
    )
    assert d.external_power_supply_state == "available"
    assert d.energy_flow_active is True
    assert d.charging_reason == "immediate"
    assert d.charging_error_code is None  # "0" sentinel dropped
    assert d.remaining_time_target_soc == "maxSOC"
    assert d.charge_led_color == "green"
    assert d.charge_led_pattern == "pulse"


def test_echo_envelope_suppressed_mapped_field_not_in_raw() -> None:
    # v2.18.1 — ``echo`` is request-envelope metadata: dropped from the raw/Scout
    # surface (carve-out from no-suppression). The mapped field must also not leak
    # into the unmapped set.
    d = _map_flatlog(
        ("external_power_supply_state", "available"),
        ("echo", "echo"),
    )
    assert "echo" not in d.raw_unmapped_fields
    # the mapped field must NOT leak into the unmapped set
    assert "external_power_supply_state" not in d.raw_unmapped_fields
