# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.4 batch (#518/#521/#522/#523) — EU-Data-Act portal field mapping.

Drives ``map_dataset_to_vehicle_data`` over each field added in the held
v2.15.4 commits and asserts the resulting ``VehicleData`` attribute. Field
shapes/units are taken from the EU data dictionary; where the dict leaves a
unit genuinely unknown (slope consumption unit=null, charging_power kW-by-
convention) the asserts only check the value passes through, not a scaled unit.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


# ── #518 — active charge target, charge-time display, dual charging-plug states
# All dict type=string; mapped via _charge_str (junk sentinels → None,
# _shorten_enum applied — unprefixed sample tokens pass through unchanged).


def test_518_active_target_soc_passthrough() -> None:
    assert _map({"active_target_soc": "80"}).active_target_soc == "80"


def test_518_charge_time_display_passthrough() -> None:
    assert _map({"charge_time_display": "02:30"}).charge_time_display == "02:30"


def test_518_plug1_string_states() -> None:
    d = _map(
        {
            "charging_plug1_flap_lock_state": "locked",
            "charging_plug1_flap_state": "closed",
            "charging_plug1_infrastructure_state": "ready",
            "charging_plug1_lock_state": "locked",
        }
    )
    assert d.charging_plug1_flap_lock_state == "locked"
    assert d.charging_plug1_flap_state == "closed"
    assert d.charging_plug1_infrastructure_state == "ready"
    assert d.charging_plug1_lock_state == "locked"


def test_518_plug2_string_states() -> None:
    d = _map(
        {
            "charging_plug2_connectionstate": "connected",
            "charging_plug2_flap_lock_state": "unlocked",
            "charging_plug2_flap_state": "open",
            "charging_plug2_infrastructure_state": "ready",
            "charging_plug2_lock_state": "unlocked",
        }
    )
    assert d.charging_plug2_connectionstate == "connected"
    assert d.charging_plug2_flap_lock_state == "unlocked"
    assert d.charging_plug2_flap_state == "open"
    assert d.charging_plug2_infrastructure_state == "ready"
    assert d.charging_plug2_lock_state == "unlocked"


def test_518_plug_junk_sentinel_dropped() -> None:
    # "invalid"/"unavailable"/etc. → None (no phantom entity on single-port cars)
    d = _map(
        {
            "charging_plug2_connectionstate": "invalid",
            "charging_plug1_lock_state": "notAvailable",
        }
    )
    assert d.charging_plug2_connectionstate is None
    assert d.charging_plug1_lock_state is None


# ── #521/#522 — next-charging-timer, slope consumption, report_type


def test_521_next_charge_timer_iso_passthrough() -> None:
    # estimated_start/finish are dict type=string ISO timestamps → passthrough.
    d = _map(
        {
            "profile_state_report.next_charging_timer_information."
            "estimated_start_time": "2026-07-01T22:00:00Z",
            "profile_state_report.next_charging_timer_information."
            "estimated_finish_time": "2026-07-02T05:30:00Z",
        }
    )
    assert d.next_charge_timer_start_at == "2026-07-01T22:00:00Z"
    assert d.next_charge_timer_finish_at == "2026-07-02T05:30:00Z"


def test_537_next_charge_timer_number_dotted() -> None:
    # #537 — nextChargingTimer is the slot index (1-15) of the next timer.
    # dict type=number → diagnostic int via _to_int. Dotted-form source.
    d = _map(
        {
            "profile_state_report.next_charging_timer_information."
            "nextChargingTimer": "7",
        }
    )
    assert d.next_charge_timer_number == 7


def test_537_next_charge_timer_number_bare_leaf() -> None:
    # _walk_fields emits the BARE dataFieldName for data-point nodes — the
    # realistic shape. The bare-leaf alias must resolve to the same index.
    d = _map({"nextChargingTimer": "13"})
    assert d.next_charge_timer_number == 13


def test_521_target_reachability_reachable_shortened() -> None:
    d = _map(
        {
            "profile_state_report.next_charging_timer_information."
            "target_reachability": "TARGET_REACHABILITY_REACHABLE",
        }
    )
    assert d.next_charge_target_reachability == "REACHABLE"


def test_521_target_reachability_not_reachable_shortened() -> None:
    d = _map(
        {
            "profile_state_report.next_charging_timer_information."
            "target_reachability": "TARGET_REACHABILITY_NOT_REACHABLE",
        }
    )
    assert d.next_charge_target_reachability == "NOT_REACHABLE"


def test_521_target_reachability_invalid_to_none() -> None:
    # fix #5 — INVALID means uninitialized timer → unknown (None), not a stale
    # literal "INVALID" state.
    d = _map(
        {
            "profile_state_report.next_charging_timer_information."
            "target_reachability": "TARGET_REACHABILITY_INVALID",
        }
    )
    assert d.next_charge_target_reachability is None


def test_521_target_reachability_calculating_to_none() -> None:
    # fix #5 — CALCULATING means not-yet-computed → unknown (None).
    d = _map(
        {
            "profile_state_report.next_charging_timer_information."
            "target_reachability": "TARGET_REACHABILITY_CALCULATING",
        }
    )
    assert d.next_charge_target_reachability is None


def test_522_slope_consumption_value_type_gated() -> None:
    # dict type=number, unit=null → raw physical_value passes through (no scale);
    # gated on the sibling value_type not being an invalid/error/0 token.
    d = _map(
        {
            "slope_consumption_values.ascent_slope_consumption."
            "physical_value": "12.5",
            "slope_consumption_values.ascent_slope_consumption."
            "value_type": "valid",
            "slope_consumption_values.descent_slope_consumption."
            "physical_value": "-4.0",
            "slope_consumption_values.descent_slope_consumption."
            "value_type": "valid",
        }
    )
    assert d.ascent_slope_consumption == 12.5
    assert d.descent_slope_consumption == -4.0


def test_522_slope_consumption_invalid_value_type_blocks() -> None:
    d = _map(
        {
            "slope_consumption_values.ascent_slope_consumption."
            "physical_value": "12.5",
            "slope_consumption_values.ascent_slope_consumption."
            "value_type": "invalid",
        }
    )
    assert d.ascent_slope_consumption is None


def test_522_report_type_no_prefix_passthrough() -> None:
    # dict lists NO values for report_type → no confirmed prefix; raw passes
    # through _shorten_enum unchanged (illustrative token, not prefix-stripped).
    d = _map({"report_type": "REPORT_TYPE_CONSUMPTION_VALUES"})
    assert d.report_type == "REPORT_TYPE_CONSUMPTION_VALUES"


def test_535_result_app_no_prefix_passthrough() -> None:
    # #535 Scout — generic delivery/sync result enum; dict lists NO values →
    # no confirmed prefix, raw passes through _shorten_enum unchanged.
    d = _map({"result_app": "RESULT_APP_SUCCESS"})
    assert d.result_app == "RESULT_APP_SUCCESS"


def test_535_result_master_no_prefix_passthrough() -> None:
    # #535 Scout — generic delivery/sync result enum; dict lists NO values →
    # no confirmed prefix, raw passes through _shorten_enum unchanged.
    d = _map({"result_master": "RESULT_MASTER_SUCCESS"})
    assert d.result_master == "RESULT_MASTER_SUCCESS"


# ── #523 — comfort/climate settings (bool), start/stop action


def test_523_setting_bool_truthy() -> None:
    d = _map(
        {
            "setting_climatisation_at_unlock": "true",
            "setting_mirror_heating_enabled": "on",
            "setting_zone_enabled_front_left": "enabled",
            "setting_zone_enabled_front_right": "active",
        }
    )
    assert d.climatisation_at_unlock is True
    assert d.mirror_heating_enabled is True
    assert d.climate_zone_front_left_enabled is True
    assert d.climate_zone_front_right_enabled is True


def test_523_setting_bool_falsy() -> None:
    d = _map(
        {
            "setting_climatisation_at_unlock": "false",
            "setting_mirror_heating_enabled": "off",
            "setting_zone_enabled_front_left": "disabled",
            "setting_zone_enabled_front_right": "inactive",
        }
    )
    assert d.climatisation_at_unlock is False
    assert d.mirror_heating_enabled is False
    assert d.climate_zone_front_left_enabled is False
    assert d.climate_zone_front_right_enabled is False


def test_523_setting_bool_unknown_token_to_none() -> None:
    # unrecognized vocab → None (not a hard False) until a live payload pins it.
    d = _map({"setting_climatisation_at_unlock": "weird"})
    assert d.climatisation_at_unlock is None


def test_523_start_stop_action_passthrough() -> None:
    # dict type=string, no enum list → no prefix; passes through unchanged.
    d = _map({"start_stop_action": "START"})
    assert d.start_stop_action == "START"


# ── #528 — start/stop modification, hood state, actual front tyre pressures


def test_528_start_stop_modification_passthrough() -> None:
    # dict type=string, no enum list → no prefix; distinct from start_stop_action.
    d = _map({"start_stop_modification": "ENABLED"})
    assert d.start_stop_modification == "ENABLED"


def test_528_start_stop_modification_distinct_from_action() -> None:
    d = _map({"start_stop_action": "START", "start_stop_modification": "STOP"})
    assert d.start_stop_action == "START"
    assert d.start_stop_modification == "STOP"


def test_528_state_of_hood_open() -> None:
    # dict enum: unsupported 0 / invalid 1 / open 2 / closed 3.
    assert _map({"state_of_hood": "2"}).hood_open is True


def test_528_state_of_hood_closed() -> None:
    assert _map({"state_of_hood": "3"}).hood_open is False


def test_528_state_of_hood_sentinels_to_none() -> None:
    # sample "0" = unsupported, 1 = invalid → no entity.
    assert _map({"state_of_hood": "0"}).hood_open is None
    assert _map({"state_of_hood": "1"}).hood_open is None


def test_528_state_of_hood_does_not_override_bonnet_channel() -> None:
    # primary open_state channel wins; state_of_hood only fills when absent.
    d = _map({"open_state_front_engine_bonnet": "2", "state_of_hood": "3"})
    assert d.hood_open is True


def test_528_tyre_pressure_actual_front_pair() -> None:
    # _FIELD_SENTINELS drops 0/1; a surviving >1 reading passes through as int.
    d = _map(
        {
            "tyre_pressure_actual_front_left": "230",
            "tyre_pressure_actual_front_right": "228",
        }
    )
    assert d.tyre_pressure_actual_fl == 230
    assert d.tyre_pressure_actual_fr == 228


def test_528_tyre_pressure_actual_sentinels_dropped() -> None:
    # 0=unsupported, 1=invalid → None (no entity). This flat dict never hits
    # _walk_fields; the drop happens inside first()/_is_sentinel via the
    # ``tyre_pressure_actual`` _FIELD_SENTINELS rule ({0.0, 1.0}).
    d = _map(
        {
            "tyre_pressure_actual_front_left": "0",
            "tyre_pressure_actual_front_right": "1",
        }
    )
    assert d.tyre_pressure_actual_fl is None
    assert d.tyre_pressure_actual_fr is None


# ── aliases (LAST-fallback dialect names folding onto canonical attributes)


def test_alias_actual_charge_rate_to_charging_rate_kmh() -> None:
    # fix #2 — actual_charge_rate (dict unit=null) folds into charging_rate_kmh
    # as the "actual" variant of the same charge-rate family.
    assert _map({"actual_charge_rate": "11"}).charging_rate_kmh == 11


def test_alias_canonical_charge_rate_wins_over_actual() -> None:
    d = _map({"battery_state_report.charge_rate": "7", "actual_charge_rate": "11"})
    assert d.charging_rate_kmh == 7


def test_alias_charging_power_to_charging_power_kw() -> None:
    # fix #3 — charging_power (dict "Power of charging", unit=null) folds into
    # charging_power_kw by kW convention; value passes through unscaled.
    assert _map({"charging_power": "22.0"}).charging_power_kw == 22.0


def test_alias_outdoor_temperature_to_outside_temp() -> None:
    # plain-°C sample (< 200) passes through untouched.
    assert _map({"outdoor_temperature": "21.5"}).outside_temp == 21.5


def test_alias_charging_state_report_error_code() -> None:
    # nested EU-portal alias maps onto charging_error_code; sentinel-drop applies.
    assert _map(
        {"charging_state_report.error_code": "7"}
    ).charging_error_code == "7"


def test_alias_charging_error_code_zero_sentinel_dropped() -> None:
    assert _map({"charging_state_report.error_code": "0"}).charging_error_code is None


# ── #528 short-term (last-trip) gas/range-gain/zero-emission counterparts.
# Same conversions as the long-term/lifetime mappings: gas dict kg/1000km → /10
# for kg/100 km; range-gain + zero-emission dict 100m → *0.1 for km.


def test_528_last_trip_avg_gas_consumption() -> None:
    # kg/1000km → kg/100 km (÷10), mirroring lifetime_avg_gas_consumption.
    d = _map({"short_term_data_average_gas_consumption": "45"})
    assert d.last_trip_avg_gas_consumption_kg_100km == 4.5


def test_528_last_trip_range_gain() -> None:
    # 100m steps → km (×0.1), mirroring lifetime_range_gain_km.
    d = _map({"short_term_data_range_gain_distance": "123"})
    assert d.last_trip_range_gain_km == pytest.approx(12.3)


def test_528_last_trip_zero_emission() -> None:
    # 100m steps → km (×0.1), mirroring lifetime_zero_emission_km.
    d = _map({"short_term_data_zero_emission_distance": "87"})
    assert d.last_trip_zero_emission_km == pytest.approx(8.7)


def test_528_short_term_matches_lifetime_conversion() -> None:
    # Identical raw inputs through short- and long-term keys must yield equal
    # converted values (same conversion semantics).
    st = _map(
        {
            "short_term_data_average_gas_consumption": "45",
            "short_term_data_range_gain_distance": "123",
            "short_term_data_zero_emission_distance": "87",
        }
    )
    lt = _map(
        {
            "long_term_data_average_gas_consumption": "45",
            "long_term_data_range_gain_distance": "123",
            "long_term_data_zero_emission_distance": "87",
        }
    )
    assert st.last_trip_avg_gas_consumption_kg_100km == lt.lifetime_avg_gas_consumption_kg_100km
    assert st.last_trip_range_gain_km == lt.lifetime_range_gain_km
    assert st.last_trip_zero_emission_km == lt.lifetime_zero_emission_km
