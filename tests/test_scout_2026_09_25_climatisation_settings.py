# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-25 (#1446, #1449-1460) — the modern MEB portal reports climate
element settings nested under ``climatisation_settings.climatisation_element_
settings.*`` (with a rear ``_enabled`` pair the older ``setting_*`` dialect
lacked), climatisation_without_hv_power under ``climatisation_settings.*``, and
the hood as a PERCENTAGE (``position_of_hood``, 0 = closed). Each is wired as an
additional first() candidate / read that fills the SAME existing field + sensor.

These tests drive the REAL nested payload through ``_walk_fields`` so a wrong
source-key spelling (the #1439 lesson) fails loudly instead of silently mapping
nothing.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _is_envelope_noise,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map_nested(vin: str = "X") -> VehicleData:
    payload = {
        "climatisation_settings": {
            "climatisation_element_settings": {
                "is_climatisation_at_unlock": "false",
                "zone_front_left_enabled": "true",
                "zone_front_right_enabled": "false",
                "zone_rear_left_enabled": "false",
                "zone_rear_right_enabled": "true",
            },
            "climatisation_without_hv_power": "true",
        },
    }
    return map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin=vin))


def test_nested_climate_element_settings_map() -> None:
    d = _map_nested()
    assert d.climatisation_at_unlock is False
    assert d.climate_zone_front_left_enabled is True
    assert d.climate_zone_front_right_enabled is False
    assert d.climate_zone_rear_left is False
    assert d.climate_zone_rear_right is True


def test_nested_fields_are_silenced_from_scout_surface() -> None:
    # A wired field must ALSO stop flooding the Vehicle Data Scout. The flattener
    # emits both the dotted path and the bare leaf for a nested scalar; unless the
    # bare leaf is a first() candidate too, it re-surfaces in raw_unmapped_fields
    # every poll even though the value mapped. Drive the real production path
    # (with the synonym map) and assert every wired leaf is reclaimed.
    payload = {
        "climatisation_settings": {
            "climatisation_element_settings": {
                "is_climatisation_at_unlock": "false",
                "zone_front_left_enabled": "true",
                "zone_front_right_enabled": "false",
                "zone_rear_left_enabled": "false",
                "zone_rear_right_enabled": "true",
            },
            "climatisation_without_hv_power": "true",
        },
        "position_of_hood": "0",
    }
    syn: dict = {}
    flat = _walk_fields(payload, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    raw_leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    for leaf in (
        "is_climatisation_at_unlock",
        "zone_front_left_enabled",
        "zone_front_right_enabled",
        "zone_rear_left_enabled",
        "zone_rear_right_enabled",
        "climatisation_without_hv_power",
        "position_of_hood",
    ):
        assert leaf not in raw_leaves, f"{leaf} still floods the Scout surface"


# --- setup_real_speed_ratios: a fixed speedometer calibration curve bundled into
# one diagnostic field (Prash's ruling 2026-09-25: take it along). Consumed so the
# ~10 qualified leaves stop flooding the Scout, but kept in to_dict() (not hidden).

_SPEED_RATIO_PAYLOAD = {
    "setup_real_speed_ratios": {
        "speed_ratio_x1_y1": {"value_type": "VALUE_TYPE_PHYSICAL"},
        "speed_ratio_x2_y2": {
            "physical_value_x": "0.6",
            "physical_value_y": "0.2",
            "value_type": "VALUE_TYPE_PHYSICAL",
        },
        "speed_ratio_x3_y3": {
            "physical_value_x": "0.9",
            "physical_value_y": "0.95",
            "value_type": "VALUE_TYPE_PHYSICAL",
        },
        "speed_ratio_x4_y4": {
            "physical_value_x": "1.0",
            "physical_value_y": "1.0",
            "value_type": "VALUE_TYPE_PHYSICAL",
        },
    }
}


def _map_speed_ratios() -> VehicleData:
    syn: dict = {}
    flat = _walk_fields(_SPEED_RATIO_PAYLOAD, None, syn)
    return map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)


def test_speed_ratios_bundled_into_calibration_field() -> None:
    d = _map_speed_ratios()
    cal = d.speed_ratio_calibration
    assert set(cal) == {
        "speed_ratio_x1_y1",
        "speed_ratio_x2_y2",
        "speed_ratio_x3_y3",
        "speed_ratio_x4_y4",
    }
    assert cal["speed_ratio_x2_y2"]["physical_value_x"] == "0.6"
    assert cal["speed_ratio_x4_y4"]["physical_value_y"] == "1.0"
    assert cal["speed_ratio_x1_y1"]["value_type"] == "VALUE_TYPE_PHYSICAL"


def test_speed_ratio_qualified_leaves_no_longer_flood_scout() -> None:
    d = _map_speed_ratios()
    raw = d.raw_unmapped_fields or {}
    # The fully-qualified paths the Scout reports must all be consumed.
    assert not [k for k in raw if k.startswith("setup_real_speed_ratios.")]


def test_speed_ratio_calibration_is_in_diagnostics_dump() -> None:
    # No entity, but kept in to_dict() so the values are never hidden.
    d = _map_speed_ratios()
    dumped = d.to_dict()
    assert dumped["speed_ratio_calibration"]["speed_ratio_x3_y3"]["physical_value_y"] == "0.95"


def test_nested_climatisation_without_hv_power() -> None:
    assert _map_nested().climatisation_without_hv_power is True


def test_position_of_hood_percentage_closed() -> None:
    d = map_dataset_to_vehicle_data(
        _walk_fields({"position_of_hood": "0"}), VehicleData(vin="X")
    )
    assert d.hood_open is False


def test_position_of_hood_percentage_open() -> None:
    d = map_dataset_to_vehicle_data(
        _walk_fields({"position_of_hood": "35"}), VehicleData(vin="X")
    )
    assert d.hood_open is True


def test_legacy_setting_dialect_still_maps() -> None:
    # The older ``setting_*`` dialect must keep working (both are first() candidates).
    payload = {
        "setting_zone_enabled_front_left": "true",
        "setting_climatisation_at_unlock": "true",
    }
    d = map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))
    assert d.climate_zone_front_left_enabled is True
    assert d.climatisation_at_unlock is True


def test_brand_native_value_is_not_clobbered() -> None:
    # Fill-if-empty: a value already set (brand-native / enum read) wins over the
    # nested portal leaf.
    base = VehicleData(vin="X")
    base.hood_open = True
    base.climate_zone_front_left_enabled = False
    d = map_dataset_to_vehicle_data(
        _walk_fields(
            {
                "position_of_hood": "0",
                "climatisation_settings": {
                    "climatisation_element_settings": {"zone_front_left_enabled": "true"}
                },
            }
        ),
        base,
    )
    assert d.hood_open is True  # not overwritten by pct=0
    assert d.climate_zone_front_left_enabled is False  # not overwritten


# --- Envelope carve-out (Prash's ruling 2026-09-25): auth_level + transaction_id
# are portal session/request metadata, not vehicle data. They must be silenced
# from the Scout/raw surface WITHOUT touching the meaningful ocpp_transaction_id.


def test_auth_level_and_transaction_id_are_envelope_noise() -> None:
    for key in (
        "auth_level",
        "eu_data_act.auth_level",
        "transaction_id",
        "eu_data_act.transaction_id",
    ):
        assert _is_envelope_noise(key) is True, key


def test_ocpp_transaction_id_is_not_over_suppressed() -> None:
    # Different leaf → the charging-session transaction id stays Scout-visible.
    assert (
        _is_envelope_noise(
            "08_wallbox_oem.wallbox_oem_hss_csms_charging_session.ocpp_transaction_id"
        )
        is False
    )


def test_carveout_silences_metadata_but_keeps_real_field_visible() -> None:
    payload = {
        "auth_level": "2",
        "transaction_id": "abc-123",
        "some_unmapped_real_field": "42",
    }
    d = map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))
    raw = d.raw_unmapped_fields or {}
    leaves = {k.rsplit(".", 1)[-1] for k in raw}
    assert "auth_level" not in leaves
    assert "transaction_id" not in leaves
    assert "some_unmapped_real_field" in leaves  # no-suppression still holds
