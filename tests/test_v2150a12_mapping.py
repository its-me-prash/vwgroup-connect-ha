# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.0a12 — EU Data Act curated-mapping expansion (additive) + unmapped log."""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _is_miles,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


class TestNewMappings:
    def test_charge_rate(self) -> None:
        assert _map({"battery_state_report.charge_rate": "12"}).charging_rate_kmh == 12

    def test_plug_state_connected(self) -> None:
        d = _map({"charging_plug1_connectionstate": "connected"})
        assert d.plug_state == "connected"
        assert d.plug_connected is True

    def test_plug_state_disconnected(self) -> None:
        d = _map({"plug_connection_state": "disconnected"})
        assert d.plug_connected is False


class TestRegressionExistingMappingsUntouched:
    def test_soc_still_maps(self) -> None:
        assert _map({"soc": "80"}).battery_soc == 80

    def test_odometer_still_maps(self) -> None:
        assert _map({"mileage": "50000"}).odometer_km == 50000

    def test_unmapped_fields_are_ignored_not_fatal(self) -> None:
        d = _map({"totally_unknown_field": "1", "soc": "80"})
        assert d.battery_soc == 80  # known maps, unknown silently ignored

    def test_empty_fields_safe(self) -> None:
        d = _map({})
        assert d.vin == "X"
        assert d.battery_soc is None


class TestFlatMqbSchema:
    """b1/A1 — flat MQB/PHEV schema (Golf GTE, Passat GTE, e-Golf): the fields a
    legacy/PHEV car delivers over the EU Data Act portal."""

    def test_flat_fields_map(self) -> None:
        d = _map({
            "fuel_level_current_level": "42",
            "boardnetBatteryVoltageIndication": "12.4",
            "oil_level_actual_level": "80",
            "cruising_range_secondary_engine": "45",
            "cruising_range_combined": "620",
            "inspectionDistance": "14900",
        })
        assert d.fuel_level == 42
        assert d.voltage_12v == 12.4
        assert d.oil_level_pct == 80
        assert d.secondary_engine_range_km == 45
        assert d.total_range_km == 620
        assert d.service_km == 14900

    def test_outside_temp_decikelvin_converted(self) -> None:
        d = _map({"outsideTemperatureIndication": "2981"})  # 298.1 K
        assert d.outside_temp is not None and 24.0 < d.outside_temp < 26.0

    def test_outside_temp_already_celsius_kept(self) -> None:
        d = _map({"outside_temperature": "17.1"})
        assert d.outside_temp == 17.1


class TestDistanceUnit:
    """b1/A2 — miles→km conversion via the companion unit field."""

    def test_is_miles_helper(self) -> None:
        assert _is_miles("MILES") and _is_miles("mile") and _is_miles("1")
        assert not _is_miles("KM") and not _is_miles("0") and not _is_miles(None)

    def test_miles_string_converts_odometer(self) -> None:
        d = _map({"mileage": "100000", "mileage.unit": "MILES"})
        assert d.odometer_km == round(100000 * 1.60934)  # 160934

    def test_miles_numeric_enum_converts(self) -> None:
        d = _map({"mileage": "100000", "mileage.unit": "1"})
        assert d.odometer_km == 160934

    def test_km_left_unchanged(self) -> None:
        assert _map({"mileage": "100000", "mileage.unit": "KM"}).odometer_km == 100000
        assert _map({"mileage": "100000"}).odometer_km == 100000  # no unit = km


class TestDrivetrainDetection:
    """b1/B3 — derive EV/ICE/PHEV from the data present (#37 e-up class)."""

    def test_ev_is_electric(self) -> None:
        d = _map({"soc": "80"})
        assert d.is_electric is True and d.has_battery is True
        assert d.is_hybrid is False and d.has_combustion is False

    def test_phev_is_hybrid(self) -> None:
        d = _map({"soc": "60", "fuel_level_current_level": "40"})
        assert d.is_hybrid is True
        assert d.has_battery is True and d.has_combustion is True
        assert d.is_electric is False

    def test_ice_is_combustion(self) -> None:
        d = _map({"fuel_level_current_level": "50"})
        assert d.has_combustion is True
        assert d.is_electric is False and d.has_battery is False


class TestEnumShorten:
    """b1/A4 — strip verbose VW enum prefixes for display."""

    def test_helper_strips_known_prefix(self) -> None:
        from custom_components.vag_connect.cariad.auth._eu_data_act import _shorten_enum
        assert _shorten_enum("CHARGE_STATE_CHARGING_HV_BATTERY") == "CHARGING_HV_BATTERY"
        assert _shorten_enum("charging") == "charging"
        assert _shorten_enum(None) is None

    def test_charging_state_shortened_in_map(self) -> None:
        d = _map({"charging_state": "CHARGE_STATE_CHARGING_HV_BATTERY"})
        assert d.charging_state == "CHARGING_HV_BATTERY"

    def test_is_charging_unchanged(self) -> None:
        assert _map({"charging_state": "charging"}).is_charging is True


class TestB5MaintenanceLock:
    """b5 — map the portal raw fields the live Golf surfaced (service intervals,
    lock, window heating) so the portal channel delivers them without vw.de."""

    def test_maintenance_intervals(self) -> None:
        d = _map({
            "maintenance_interval_distance_until_inspection": "-14900",
            "maintenance_interval__time_until_inspection": "-155",
            "maintenance_interval_distance_until_oil_change": "-1700",
            "maintenance_interval__time_until_oil_change": "-17",
        })
        # portal ships these negative (remaining-until-due) → we negate so the
        # sensor reads a positive countdown ("due in 155 days / 14900 km").
        assert d.service_km == 14900
        assert d.service_due_in_days == 155
        assert d.oil_service_km == 1700
        assert d.oil_service_due_in_days == 17

    def test_lock_state(self) -> None:
        assert _map({"lock_state": "locked"}).doors_locked is True
        assert _map({"lock_state": "unlocked"}).doors_locked is False

    def test_window_heating(self) -> None:
        d = _map({"window_heating_state_front": "on", "window_heating_state_rear": "off"})
        assert d.window_heating_front is True
        assert d.window_heating_back is False

    def test_mapped_fields_leave_raw(self) -> None:
        d = _map({"maintenance_interval__time_until_inspection": "-155", "x": "1"})
        assert "maintenance_interval__time_until_inspection" not in d.raw_unmapped_fields
        assert d.raw_unmapped_fields.get("x") == "1"
