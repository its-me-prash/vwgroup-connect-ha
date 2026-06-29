# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.1 (2.15.0 plan) — EU Data Act + BFF wire-key mapping.

Covers both parser dialects:

- EU Data Act portal dialect (``_eu_data_act.map_dataset_to_vehicle_data``):
  MAP-INTO-EXISTING rows + the EU NEW fields, the 3 new enum prefixes
  (CHARGE_TYPE_ / CHARGING_SCENARIO_ / PROFILE_CHARGE_REASON_), the
  enum-shortening, and the guard/fallback rules.
- BFF / selectivestatus dialect (``vw_eu.VWEUClient._parse_status``):
  the BFF MAP-INTO-EXISTING rows + BFF NEW fields, the battery-care
  fallback-only rule, the petrol/gas range ``is None`` guards, and the
  shared parking_brake / tire-state fields.

Modelled on tests/test_v2150b13_charger_dialect.py (EU dialect) and
tests/test_v210_vw_eu_gaps.py (BFF dialect).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


# ── EU Data Act dialect helpers ──────────────────────────────────────────────


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def _vw_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client


def _bff(value_block: dict) -> VehicleData:
    """Parse a tyrePressure value block via the BFF parser."""
    raw = {"tyrePressure": {"tyrePressureStatus": {"value": value_block}}}
    return _vw_client()._parse_status("VINX", raw, parking={})


def _bff_raw(raw: dict) -> VehicleData:
    return _vw_client()._parse_status("VINX", raw, parking={})


# ─────────────────────────────────────────────────────────────────────────────
# 1. EU Data Act — MAP-INTO-EXISTING
# ─────────────────────────────────────────────────────────────────────────────


class TestEUMapIntoExisting:
    def test_charge_mode_support_flags_collapse_to_list(self) -> None:
        d = _map({
            "charge_mode_selection_options.immediate_charging": "true",
            "charge_mode_selection_options.timer_charging": "1",
            "charge_mode_selection_options.timer_charging_climatization": "set",
            "charge_mode_selection_options.preferred_charging_times": "false",
            "charge_mode_selection_options.home_storage_charging": "on",
        })
        # only truthy flags appended; no per-flag entity
        assert d.available_charge_modes == [
            "IMMEDIATE", "TIMER", "TIMER_WITH_CLIMATISATION", "HOME_STORAGE",
        ]

    def test_charge_mode_labels_dedup(self) -> None:
        d = VehicleData(vin="X")
        d.available_charge_modes = ["IMMEDIATE"]
        out = map_dataset_to_vehicle_data(
            {"charge_mode_selection_options.immediate_charging": "true"}, d
        )
        assert out.available_charge_modes == ["IMMEDIATE"]  # not duplicated

    def test_charge_type_shortened(self) -> None:
        d = _map({"charging_state_report.charge_type": "CHARGE_TYPE_DC"})
        assert d.charging_type == "DC"

    def test_charge_type_prefix_is_registered(self) -> None:
        from custom_components.vag_connect.cariad.auth import _eu_data_act as m
        assert "CHARGE_TYPE_" in m._ENUM_PREFIXES
        assert "CHARGING_SCENARIO_" in m._ENUM_PREFIXES
        assert "PROFILE_CHARGE_REASON_" in m._ENUM_PREFIXES

    def test_charging_mode_guard_does_not_clobber_existing(self) -> None:
        d = VehicleData(vin="X")
        d.charging_preferred_mode = "manual"  # a BFF value already set
        out = map_dataset_to_vehicle_data({"charging_mode": "CHARGING_MODE_TIMER"}, d)
        assert out.charging_preferred_mode == "manual"  # not clobbered

    def test_charging_mode_fills_when_none(self) -> None:
        d = _map({"charging_mode": "CHARGING_MODE_TIMER"})
        assert d.charging_preferred_mode == "TIMER"

    def test_battery_care_threshold(self) -> None:
        d = _map({"battery_care_mode.charge_bcam_threshold": "80"})
        assert d.battery_care_target_soc_pct == 80

    def test_energy_contents_gated_on_value_type(self) -> None:
        # physical_value is in 0.1-kWh units → divided by 10 to reach kWh (#534).
        d = _map({
            "energy_contents.current_energy_content.physical_value": "425",
            "energy_contents.current_energy_content.value_type": "valid",
            "energy_contents.maximal_energy_content.physical_value": "580",
            "energy_contents.maximal_energy_content.value_type": "valid",
        })
        assert d.battery_available_kwh == 42.5
        assert d.battery_cap_kwh == 58.0

    def test_energy_contents_blocked_on_invalid_value_type(self) -> None:
        d = _map({
            "energy_contents.current_energy_content.physical_value": "42.5",
            "energy_contents.current_energy_content.value_type": "invalid",
        })
        assert d.battery_available_kwh is None

    def test_remaining_charge_time_complete_is_preferred_source(self) -> None:
        # complete wins over the bare remaining_charging_time in the SAME chain
        d = _map({
            "battery_state_report.remaining_charging_time_complete": "95",
            "remaining_charging_time": "40",
        })
        assert d.remaining_charge_time_min == 95

    def test_remaining_charge_time_falls_back_to_bare(self) -> None:
        d = _map({"remaining_charging_time": "40"})
        assert d.remaining_charge_time_min == 40

    def test_trip_consumption_scale_div10(self) -> None:
        d = _map({
            "short_term_data_average_fuel_consumption": "68",
            "short_term_data_average_electr_engine_consumption": "182",
            "long_term_data_average_fuel_consumption": "60",
            "long_term_data_average_electr_engine_consumption": "170",
        })
        assert d.last_trip_avg_fuel_consumption_l_100km == 6.8
        assert d.last_trip_avg_electric_consumption_kwh_100km == 18.2
        assert d.lifetime_avg_fuel_consumption_l_100km == 6.0
        assert d.lifetime_avg_electric_consumption_kwh_100km == 17.0

    def test_parking_light_aggregate(self) -> None:
        d = _map({"parking_light_left": "on", "parking_light_right": "false"})
        assert d.parking_light_left is True
        assert d.parking_light_right is False
        assert d.parking_light is True  # aggregate of either

    def test_last_seen_from_epoch_timestamp(self) -> None:
        d = _map({"car_captured_utc_timestamp": "1718000000"})
        assert isinstance(d.last_seen_at, str)
        assert d.last_seen_at.startswith("2024-06-10")

    def test_parking_brake_engaged(self) -> None:
        d = _map({"parking_brake.is_set": "true"})
        assert d.parking_brake_engaged is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. EU Data Act — NEW fields + enum shortening
# ─────────────────────────────────────────────────────────────────────────────


class TestEUNewFields:
    def test_charging_scenario_shortened(self) -> None:
        d = _map({"charging_scenario": "CHARGING_SCENARIO_OPTIMISED_CHARGING_ACTIVE"})
        assert d.charging_scenario == "OPTIMISED_CHARGING_ACTIVE"

    def test_immediate_charge_action_state_shortened(self) -> None:
        d = _map({
            "immediate_charge_action_state": "IMMEDIATE_ACTION_STATE_IMMEDIATE_CHARGING",
        })
        assert d.immediate_charge_action_state == "IMMEDIATE_CHARGING"

    def test_profile_charge_reason_shortened(self) -> None:
        d = _map({"profile_charge_reason": "PROFILE_CHARGE_REASON_MIN_SOC"})
        assert d.profile_charge_reason == "MIN_SOC"

    def test_charge_session_energy(self) -> None:
        # charge_session_energy_kwh is populated from the REAL dict key
        # battery_state_report.charge_energy (with a >=0 guard). The earlier
        # guessed "charge_session_energy" key never existed and was removed.
        d = _map({"battery_state_report.charge_energy": "7.2"})
        assert d.charge_session_energy_kwh == 7.2

    def test_remaining_charge_time_bulk(self) -> None:
        d = _map({"battery_state_report.remaining_charging_time_bulk": "40"})
        assert d.remaining_charge_time_bulk_min == 40

    def test_bulk_sentinel_minus1_not_mapped_but_scout_visible(self) -> None:
        # -1 is the table-driven sentinel for remaining_charging_time fields.
        # NO-SUPPRESSION: the field stays on the flattened surface (Scout) but
        # the mapper must NOT assign the sentinel value to the target.
        from custom_components.vag_connect.cariad.auth._eu_data_act import (
            _walk_fields,
        )
        payload = {
            "battery_state_report": {"remaining_charging_time_bulk": -1},
        }
        flat = _walk_fields(payload)
        # kept on the flattened surface (no-suppress)…
        assert "battery_state_report.remaining_charging_time_bulk" in flat
        d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"))
        # …but the sentinel value never lands on the mapped target…
        assert d.remaining_charge_time_bulk_min is None
        # …and it remains Scout-visible for discovery.
        assert (
            "battery_state_report.remaining_charging_time_bulk"
            in d.raw_unmapped_fields
        )

    def test_bulk_real_value_maps(self) -> None:
        from custom_components.vag_connect.cariad.auth._eu_data_act import (
            _walk_fields,
        )
        flat = _walk_fields(
            {"battery_state_report": {"remaining_charging_time_bulk": 40}}
        )
        d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"))
        assert d.remaining_charge_time_bulk_min == 40

    def test_odometer_state(self) -> None:
        d = _map({"mileage.state": "VALID"})
        assert d.odometer_state == "VALID"

    def test_instrument_cluster_time_passthrough(self) -> None:
        d = _map({"instrument_cluster_time": "2026-06-20T10:00:00Z"})
        assert d.instrument_cluster_time == "2026-06-20T10:00:00Z"

    def test_data_error_detail_filters_no_error_sentinel(self) -> None:
        d = _map({"error_code": "#0", "error_description": "PNL Missing"})
        # "#0" filtered out, description kept
        assert d.data_error_detail == "PNL Missing"

    def test_data_error_detail_all_sentinels_yields_none(self) -> None:
        d = _map({"error_code": "#0", "error_number": "0"})
        assert d.data_error_detail is None

    def test_last_report_id_surfaced_and_scout_visible(self) -> None:
        d = _map({"message_id": "rep-123"})
        assert d.last_report_id == "rep-123"
        # b14 no-suppress: still visible in raw_unmapped_fields
        assert "message_id" in d.raw_unmapped_fields

    def test_climate_and_residual_energy(self) -> None:
        # Real EU data-dictionary keys (the earlier guessed names never matched).
        d = _map({
            "additional_consumptions.interior_climatization_consumption": "1.5",
            "additional_consumptions.residual_consumption": "0.4",
        })
        assert d.climate_energy_consumption_kwh == 1.5
        assert d.residual_energy_consumption_kwh == 0.4

    def test_recuperation_scale_div10(self) -> None:
        d = _map({
            "short_term_data_average_recuperation": "22",
            "long_term_data_average_recuperation": "18",
        })
        assert d.last_trip_avg_recuperation_kwh_100km == 2.2
        assert d.lifetime_avg_recuperation_kwh_100km == 1.8

    def test_dataset_key_low_confidence_surfaced_and_scout_visible(self) -> None:
        d = _map({"key": "abc-key"})
        assert d.dataset_key == "abc-key"
        # LOW-confidence metadata stays Scout-visible (b14 no-suppress)
        assert "key" in d.raw_unmapped_fields

    def test_bare_open_not_mapped_to_sunroof(self) -> None:
        # plan §5 LOW: leave bare `open` to raw_unmapped_fields until live-test
        d = _map({"open": "true"})
        assert d.sunroof_open is None
        assert "open" in d.raw_unmapped_fields


# ─────────────────────────────────────────────────────────────────────────────
# 3. BFF / selectivestatus — MAP-INTO-EXISTING
# ─────────────────────────────────────────────────────────────────────────────


class TestBFFMapIntoExisting:
    def test_tire_pressure_bar_routes_via_existing_suffix_router(self) -> None:
        d = _bff({
            "frontLeftTireActualPressure_bar": 2.41,
            "frontRightTireActualPressure_bar": 2.39,
            "rearLeftTireActualPressure_bar": 2.5,
            "rearRightTireActualPressure_bar": 2.5,
        })
        assert d.tire_pressure_front_left_bar == 2.41
        assert d.tire_pressure_front_right_bar == 2.39
        assert d.tire_pressure_rear_left_bar == 2.5
        assert d.tire_pressure_rear_right_bar == 2.5

    def test_petrol_range_only_when_combustion_none(self) -> None:
        d = _bff_raw({"petrolRange": 350})
        assert d.combustion_range_km == 350

    def test_petrol_range_guard_does_not_clobber_structured(self) -> None:
        raw = {
            "fuelStatus": {"rangeStatus": {"value": {
                "primaryEngine": {"type": "diesel", "remainingRange_km": 600},
            }}},
            "petrolRange": 350,
        }
        d = _bff_raw(raw)
        # structured engine block stays authoritative
        assert d.combustion_range_km == 600

    def test_gas_range_prefers_cng(self) -> None:
        d = _bff_raw({"gasRange": 120})
        assert d.cng_range_km == 120

    def test_oil_level_result(self) -> None:
        d = _bff_raw({"oilLevelResult": "lowWarning"})
        assert d.oil_level_status == "lowWarning"
        assert d.oil_level_warning is True

    def test_oil_level_result_normal(self) -> None:
        d = _bff_raw({"oilLevelResult": "normal"})
        assert d.oil_level_status == "normal"
        assert d.oil_level_warning is False

    def test_battery_care_target_fallback_only(self) -> None:
        # canonical path present → flat fallback ignored
        raw = {
            "batteryChargingCare": {"chargingCareSettings": {"value": {
                "batteryCareTargetSoc": 90,
            }}},
            "batteryCareTargetSOC_pct": 70,
        }
        d = _bff_raw(raw)
        assert d.battery_care_target_soc_pct == 90  # canonical wins

    def test_battery_care_target_flat_used_when_canonical_absent(self) -> None:
        d = _bff_raw({"batteryCareTargetSOC_pct": 70})
        assert d.battery_care_target_soc_pct == 70

    def test_cng_level(self) -> None:
        d = _bff_raw({"currentCngLevel_pct": 55})
        assert d.cng_level_pct == 55

    def test_battery_capacity_netto_wh_heuristic(self) -> None:
        d = _bff_raw({"batteryCapacityNetto": 58000})  # > 500 → Wh → /1000
        assert d.battery_cap_kwh == 58.0

    def test_battery_capacity_netto_kwh_passthrough(self) -> None:
        d = _bff_raw({"batteryCapacityNetto": 58})  # <= 500 → already kWh
        assert d.battery_cap_kwh == 58.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. BFF / selectivestatus — NEW fields + shared fields
# ─────────────────────────────────────────────────────────────────────────────


class TestBFFNewFields:
    def test_tire_state_per_corner(self) -> None:
        d = _bff({
            "frontLeftTireState": "OK",
            "rearRightTireState": "LOW",
        })
        assert d.tire_pressure_fl_state == "ok"
        assert d.tire_pressure_rr_state == "low"

    def test_tire_errorcode_drops_sentinels(self) -> None:
        d = _bff({
            "frontLeftTireErrorCode": 0,   # unsupported → None
            "frontRightTireErrorCode": 1,  # invalid → None
            "rearLeftTireErrorCode": 2,    # real
        })
        assert d.tire_pressure_fl_errorcode is None
        assert d.tire_pressure_fr_errorcode is None
        assert d.tire_pressure_rl_errorcode == 2

    def test_lpg_range(self) -> None:
        d = _bff_raw({"lpgRange": 90})
        assert d.lpg_range_km == 90

    def test_engine_status_bool(self) -> None:
        assert _bff_raw({"engineStatus": True}).engine_status == "on"
        assert _bff_raw({"engineStatus": False}).engine_status == "off"

    def test_engine_status_string(self) -> None:
        assert _bff_raw({"engineStatus": "RUNNING"}).engine_status == "running"

    def test_parking_brake_shared_field_from_bff(self) -> None:
        assert _bff_raw({"parkingBrakeStatus": "engaged"}).parking_brake_engaged is True
        assert _bff_raw({"parkingBrakeStatus": "released"}).parking_brake_engaged is False

    def test_trip_avg_aux_consumption_not_rescaled(self) -> None:
        d = _bff_raw({"tripAverageAuxConsumption": 0.6})
        assert d.trip_avg_aux_consumption_kwh == 0.6  # NOT divided

    def test_departure_charge(self) -> None:
        d = _bff_raw({"departureCharge": 12.0})
        assert d.departure_charge_kwh == 12.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Entity / phantom-gate parity
# ─────────────────────────────────────────────────────────────────────────────


class TestEntityWiring:
    EU_BFF_SENSOR_KEYS = (
        "charging_scenario", "immediate_charge_action_state",
        "profile_charge_reason", "charge_session_energy_kwh",
        "remaining_charge_time_bulk_min", "odometer_state",
        "instrument_cluster_time", "data_error_detail", "last_report_id",
        "climate_energy_consumption_kwh", "residual_energy_consumption_kwh",
        "last_trip_avg_recuperation_kwh_100km",
        "lifetime_avg_recuperation_kwh_100km", "dataset_key",
        "tire_pressure_fl_state", "tire_pressure_fr_state",
        "tire_pressure_rl_state", "tire_pressure_rr_state",
        "tire_pressure_fl_errorcode", "tire_pressure_fr_errorcode",
        "tire_pressure_rl_errorcode", "tire_pressure_rr_errorcode",
        "lpg_range_km", "engine_status", "trip_avg_aux_consumption_kwh",
        "departure_charge_kwh",
    )
    DISABLED_BY_DEFAULT = (
        "dataset_key", "tire_pressure_fl_state", "tire_pressure_fr_state",
        "tire_pressure_rl_state", "tire_pressure_rr_state",
        "tire_pressure_fl_errorcode", "tire_pressure_fr_errorcode",
        "tire_pressure_rl_errorcode", "tire_pressure_rr_errorcode",
        "trip_avg_aux_consumption_kwh", "departure_charge_kwh",
    )
    BINARY_KEYS = (
        "parking_brake_engaged", "parking_light_left", "parking_light_right",
    )

    def test_every_sensor_has_a_description_and_is_phantom_gated(self) -> None:
        from custom_components.vag_connect import sensor as s
        keys = {d.key: d for d in s.SENSOR_DESCRIPTIONS}
        for key in self.EU_BFF_SENSOR_KEYS:
            assert key in keys, f"missing sensor description for {key}"
            assert keys[key].data_key == key
            assert keys[key].translation_key == key
            assert key in s._DATA_PRESENT_REQUIRED, f"{key} not phantom-gated"

    def test_disabled_by_default_flags(self) -> None:
        from custom_components.vag_connect import sensor as s
        keys = {d.key: d for d in s.SENSOR_DESCRIPTIONS}
        for key in self.DISABLED_BY_DEFAULT:
            assert keys[key].entity_registry_enabled_default is False, key

    def test_binary_sensors_present_and_gated(self) -> None:
        from custom_components.vag_connect import binary_sensor as b
        keys = {d.key: d for d in b.BINARY_DESCRIPTIONS}
        for key in self.BINARY_KEYS:
            assert key in keys, f"missing binary description for {key}"
            assert key in b._DATA_PRESENT_REQUIRED, f"{key} not phantom-gated"

    def test_translation_parity_all_locales(self) -> None:
        import json
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        files = [repo / "custom_components/vag_connect/strings.json"] + [
            repo / f"custom_components/vag_connect/translations/{loc}.json"
            for loc in ("en", "de", "fr", "es", "nl", "pl", "cs", "sv")
        ]
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            s = data["entity"]["sensor"]
            b = data["entity"]["binary_sensor"]
            for key in self.EU_BFF_SENSOR_KEYS:
                assert key in s, f"{path.name} missing sensor name for {key}"
                assert s[key]["name"].strip()
            for key in self.BINARY_KEYS:
                assert key in b, f"{path.name} missing binary name for {key}"
                assert b[key]["name"].strip()
