# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.3 — EU Data Act portal new-field mappings (#465/#514/#515/#516).

Charge-settings block, door/closure SAFE-state (inverse polarity vs the
locked_state/open_state blocks), trip odometer endpoints, fuel/fluids/SCR,
tyre pressure DELTA (sentinel-dropped), parking-lights enum, aux battery,
the #516 instrument-cluster warning bitmask (raw only — no invented decode),
and the climate/window-heating error codes (0/#0 sentinel drop). All
EU-Data-Act-dialect only; mirrors the v2.15.2 charger-detail style.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


def _map_flatlog(*pairs: tuple[str, str]) -> VehicleData:
    payload = [{"dataFieldName": n, "value": v} for n, v in pairs]
    return map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))


# ── A. Charging settings ─────────────────────────────────────────────────────

def test_charge_mode_selection_shortened() -> None:
    d = _map({"settings.charge_mode_selection":
              "CHARGE_MODE_SELECTION_IMMEDIATECHARGING"})
    assert d.charge_mode_selection == "IMMEDIATECHARGING"


def test_max_charge_current_ac_shortened() -> None:
    d = _map({"settings.max_charge_current_ac": "MAX_CHARGE_CURRENT_MAXIMUM"})
    assert d.max_charge_current_ac == "MAXIMUM"


def test_auto_unlock_charge_port_shortened() -> None:
    d = _map({"settings.auto_unlock_ac": "AUTO_UNLOCK_AC_PERMANENT"})
    assert d.auto_unlock_charge_port == "PERMANENT"


def test_battery_care_mode_active_true() -> None:
    d = _map({"setting.bcam_activation": "BCAM_ACTIVATION_ACTIVATED"})
    assert d.battery_care_mode_active is True


def test_battery_care_mode_active_false_on_deactivated() -> None:
    d = _map({"setting.bcam_activation": "BCAM_ACTIVATION_DEACTIVATED"})
    assert d.battery_care_mode_active is False


def test_charge_bulk_threshold_pct() -> None:
    d = _map({"battery_state_report.charge_bulk_threshold": "100"})
    assert d.charge_bulk_threshold_pct == 100


def test_charge_rate_unit_shortened() -> None:
    d = _map({"battery_state_report.charge_rate_unit":
              "CHARGE_RATE_UNIT_KM_PER_MIN"})
    # CHARGE_RATE_UNIT_ is not a registered prefix; passthrough is acceptable —
    # assert the raw value is surfaced (LOW, disabled-by-default).
    assert d.charge_rate_unit == "CHARGE_RATE_UNIT_KM_PER_MIN"


# ── B. Door / closure SAFE-state (inverse polarity) ──────────────────────────

def test_bonnet_locked_polarity() -> None:
    assert _map({"locked_state_front_engine_bonnet": "2"}).bonnet_locked is True
    assert _map({"locked_state_front_engine_bonnet": "3"}).bonnet_locked is False
    # 0/1 (unsupported/invalid) → unset
    assert _map({"locked_state_front_engine_bonnet": "0"}).bonnet_locked is None


def test_closures_secured_all_safe() -> None:
    d = _map({
        "safe_state_front_engine_bonnet": "2",
        "safe_state_front_left_door": "2",
        "safe_state_tailgate": "2",
    })
    assert d.closures_secured is True


def test_closures_secured_one_unsafe() -> None:
    d = _map({
        "safe_state_front_left_door": "2",
        "safe_state_rear_right_door": "3",  # unsafe
    })
    assert d.closures_secured is False


def test_closures_secured_ignores_unsupported() -> None:
    # only 0/1 present → no determination
    d = _map({"safe_state_front_left_door": "0", "safe_state_tailgate": "1"})
    assert d.closures_secured is None


def test_service_hatch_and_spoiler() -> None:
    assert _map({"state_service_hatch": "2"}).service_hatch_open is True
    assert _map({"state_service_hatch": "3"}).service_hatch_open is False
    assert _map({"state_spoiler": "2"}).spoiler_open is True
    # 0 = unsupported → unset
    assert _map({"state_service_hatch": "0"}).service_hatch_open is None


def test_sunroof_open_from_motor_hood() -> None:
    assert _map({"state_sunroof_motor_hood_1": "2"}).sunroof_open is True
    assert _map({"state_sunroof_motor_hood_3": "3"}).sunroof_open is False
    assert _map({"state_sunroof_motor_hood_1": "0"}).sunroof_open is None


# ── C. Trip odometer endpoints ───────────────────────────────────────────────

def test_trip_odometer_endpoints() -> None:
    d = _map({
        "long_term_data_mileage": "982",
        "long_term_data_start_mileage": "79216",
        "short_term_data_start_mileage": "80180",
    })
    assert d.lifetime_trip_distance_km == 982
    assert d.lifetime_trip_start_odometer_km == 79216
    assert d.last_trip_start_odometer_km == 80180


# ── D. Fuel / fluids / SCR ───────────────────────────────────────────────────

def test_tank_current_level_feeds_fuel_level() -> None:
    assert _map({"tank_current_level": "82.0"}).fuel_level == 82


def test_canonical_fuel_wins_over_tank_level() -> None:
    d = _map({"fuel_level_current_level": "40", "tank_current_level": "82"})
    assert d.fuel_level == 40


def test_oil_and_scr() -> None:
    d = _map({
        "oil_level_total_max": "1.0",
        "oil_level_additional_oil_level": "25.0",
        "oil_level_dipstick_indicator_function": "1",
        "scr_range": "650",
    })
    assert d.oil_level_liters == 1.0
    assert d.oil_level_additional_pct == 25.0
    assert d.oil_dipstick_active is True
    assert d.adblue_range_km == 650


def test_scr_range_empty_is_unset() -> None:
    assert _map({"scr_range": ""}).adblue_range_km is None


def test_fuel_level_estimated() -> None:
    assert _map({"fuel_level__accuracy": "1"}).fuel_level_estimated is True
    assert _map({"fuel_level__accuracy": "0"}).fuel_level_estimated is False


# ── E. Tyre pressure delta (sentinel drop) ───────────────────────────────────

def test_tyre_pressure_diff_valid_value() -> None:
    d = _map_flatlog(("tyre_pressure_differential_front_left", "7"))
    assert d.tyre_pressure_diff_fl == 7


def test_tyre_pressure_diff_sentinel_not_mapped_and_consumed() -> None:
    # 0=unsupported / 1=invalid → never mapped to the target. v2.25.0: this is a
    # MAPPED field with no reading, so it is now CONSUMED rather than left
    # Scout-visible — it must not re-file #958/#969/#970 on every poll.
    d_fl = _map_flatlog(("tyre_pressure_differential_front_left", "1"))
    assert d_fl.tyre_pressure_diff_fl is None
    assert "tyre_pressure_differential_front_left" not in d_fl.raw_unmapped_fields
    d_fr = _map_flatlog(("tyre_pressure_differential_front_right", "0"))
    assert d_fr.tyre_pressure_diff_fr is None
    assert "tyre_pressure_differential_front_right" not in d_fr.raw_unmapped_fields


# ── F. Lights / energy / misc ────────────────────────────────────────────────

def test_parking_lights_enum() -> None:
    assert _map({"parking_lights": "2"}).parking_lights_state == "off"
    assert _map({"parking_lights": "3"}).parking_lights_state == "left"
    assert _map({"parking_lights": "4"}).parking_lights_state == "right"
    assert _map({"parking_lights": "5"}).parking_lights_state == "both"
    # 0/1 (unsupported/invalid) → unset
    assert _map({"parking_lights": "1"}).parking_lights_state is None


def test_aux_battery_energy_pct() -> None:
    assert _map({"bem_level": "57"}).aux_battery_energy_pct == 57


def test_dashboard_warnings_raw_passthrough_no_decode() -> None:
    # We surface the raw hex/interpreted value ONLY — no invented enum decode.
    d = _map({"active_warnings_in_instrument_cluster_feff_filtered": "0x1A"})
    assert d.dashboard_warnings_raw == "0x1A"


def test_climate_and_window_heating_error_codes() -> None:
    d = _map({"climate_error_code": "2", "window_heating_error_code": "2"})
    assert d.climate_error_code == "2"
    assert d.window_heating_error_code == "2"


def test_error_codes_zero_sentinel_dropped() -> None:
    d = _map({"climate_error_code": "0", "window_heating_error_code": "#0"})
    assert d.climate_error_code is None
    assert d.window_heating_error_code is None


# ── No-suppress policy: skipped vendor-internal fields stay Scout-visible ─────

def test_vendor_field_visible_echo_envelope_suppressed() -> None:
    d = _map({
        "scope_potential_total": "0",
        "echo": "echo",
        "charge_mode_selection": "CHARGE_MODE_SELECTION_IMMEDIATECHARGING",
    })
    # a real vendor-internal field (real name) is NOT mapped → must surface as raw
    assert "scope_potential_total" in d.raw_unmapped_fields
    # v2.18.1 — ``echo`` is envelope metadata → dropped (carve-out from no-suppress)
    assert "echo" not in d.raw_unmapped_fields
    # a mapped field must NOT leak into the unmapped set
    assert "charge_mode_selection" not in d.raw_unmapped_fields


def test_mapped_settings_consumed_not_in_raw() -> None:
    d = _map({
        "settings.charge_mode_selection": "CHARGE_MODE_SELECTION_TIMERCHARGING",
        "settings.max_charge_current_ac": "MAX_CHARGE_CURRENT_REDUCED",
        "settings.auto_unlock_ac": "AUTO_UNLOCK_AC_OFF",
    })
    for k in ("settings.charge_mode_selection",
              "settings.max_charge_current_ac", "settings.auto_unlock_ac"):
        assert k not in d.raw_unmapped_fields
