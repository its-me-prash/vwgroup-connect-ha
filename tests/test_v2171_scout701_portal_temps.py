"""v2.17.1 — Scout #701 (VW ID.7) EU-portal telemetry mappings.

Covers the genuinely-new fields the ID.7 report surfaced that we did not
map before: HV-battery min/max temperature, interior (cabin) temperature,
charge-target time and the profile user capacity. Everything else in the
#701 dump was the standard report envelope or already-mapped signals.
"""

from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="WVWTEST0000000701"))


def test_hvbattery_min_max_celsius() -> None:
    d = _map(
        {
            "hvbatterytemperature.min_temperature": "18.5",
            "hvbatterytemperature.max_temperature": "24.0",
        }
    )
    assert d.battery_temp == 18.5
    assert d.battery_temp_max == 24.0


def test_hvbattery_deci_kelvin_converted() -> None:
    # >200 → treated as deci-Kelvin (2951 dK ≈ 22 °C, 2981 dK ≈ 25 °C).
    # Assert the range, not the exact tenth — K→C always lands on a .x5
    # hundredth so the 1-decimal round is float-representation dependent.
    d = _map(
        {
            "hvbatterytemperature.min_temperature": "2951",
            "hvbatterytemperature.max_temperature": "2981",
        }
    )
    assert 21.5 <= d.battery_temp <= 22.5
    assert 24.5 <= d.battery_temp_max <= 25.5


def test_hvbattery_does_not_clobber_bff_value() -> None:
    d = VehicleData(vin="WVWTEST0000000701")
    d.battery_temp = 20.0  # already filled by the CARIAD-BFF channel
    map_dataset_to_vehicle_data({"hvbatterytemperature.min_temperature": "5.0"}, d)
    assert d.battery_temp == 20.0  # portal must not overwrite


def test_cabin_temperature_mapped() -> None:
    # EU-DA dict 74039fb6: raw is offset-encoded (0.1 °C, -46 offset), so a
    # 21.5 °C cabin is raw 675 (675*0.1 - 46 = 21.5) — NOT deci-Kelvin.
    d = _map(
        {
            "in_cabin_temperature.temperature": "675",
            "in_cabin_temperature.measurement_state": "valid",
        }
    )
    assert d.cabin_temp == 21.5


def test_cabin_temperature_no_state_still_accepted() -> None:
    d = _map({"in_cabin_temperature.temperature": "650"})  # 650*0.1 - 46 = 19.0
    assert d.cabin_temp == 19.0


def test_cabin_temperature_fahrenheit_subrange_converted() -> None:
    # raw > 1460 = the 0.25 °F alternative sub-range. raw 1937 → 20.0 °C, a
    # plausible cabin, exercising the Fahrenheit conversion path.
    d = _map({"in_cabin_temperature.temperature": "1937"})
    assert d.cabin_temp == 20.0


def test_cabin_temperature_implausible_sentinel_screened() -> None:
    # #465 (Schraube11) — a bottom-of-range sentinel (raw ~21 → -43.9 °C) and the
    # F-range floor (raw 1461 → -46.1 °C) are physically impossible cabin temps,
    # so they are screened to None instead of surfacing as a real ~-44 °C.
    assert _map({"in_cabin_temperature.temperature": "21"}).cabin_temp is None
    assert _map({"in_cabin_temperature.temperature": "1461"}).cabin_temp is None
    # a hot but still plausible cabin passes.
    assert _map({"in_cabin_temperature.temperature": "1060"}).cabin_temp == 60.0


def test_cabin_temperature_invalid_state_skipped() -> None:
    d = _map(
        {
            "in_cabin_temperature.temperature": "0",
            "in_cabin_temperature.measurement_state": "invalid",
        }
    )
    assert d.cabin_temp is None


def test_charge_target_time_iso_passthrough() -> None:
    d = _map({"battery_state_report.charge_target_time": "2026-07-10T18:30:00Z"})
    assert d.charge_target_time == "2026-07-10T18:30:00Z"


def test_max_number_users_int() -> None:
    d = _map({"max_number_users": "5"})
    assert d.max_number_users == 5


def test_absent_fields_stay_none() -> None:
    d = _map({"odometer": "12345"})
    assert d.cabin_temp is None
    assert d.charge_target_time is None
    assert d.max_number_users is None
    assert d.battery_temp is None
    assert d.battery_temp_max is None
