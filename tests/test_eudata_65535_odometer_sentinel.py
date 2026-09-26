# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""65535 (0xFFFF) is VW's uint16 "no reading" marker on BOUNDED fields, but a
plausible real reading on a cumulative odometer-class distance (a car at exactly
65,535 km). It must NOT be dropped as a sentinel for the mileage/odometer/
lifetime family, while staying a sentinel everywhere else. The three 32-bit
markers stay global for all fields; drop_odometer_sentinel still screens the
real uint32 odometer sentinels. (Competitor-parity with rafaelhutter, which
excludes 65535 from its unset-sentinels for the same reason.)
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _is_sentinel,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(payload: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))


def test_65535_is_not_a_sentinel_for_odometer_family() -> None:
    for name in ("mileage", "mileage.value", "odometer", "totalMileage",
                 "total_mileage", "overallMileage"):
        assert _is_sentinel(name, 65535) is False, name


def test_65535_stays_a_sentinel_for_bounded_fields() -> None:
    for name in ("battery_state_report.soc", "range", "cruising_range_electric",
                 "target_temperature", "remaining_charging_time"):
        assert _is_sentinel(name, 65535) is True, name


def test_service_interval_65535_stays_a_sentinel() -> None:
    # Service/oil intervals carry "distance", not "mileage"/"odometer" — 65535 km
    # to next service is implausible, so it remains a sentinel.
    assert _is_sentinel("maintenance_interval_distance_until_oil_change", 65535) is True
    assert _is_sentinel("maintenance_interval_distance_until_inspection", 65535) is True


def test_32bit_markers_stay_global_even_on_odometer() -> None:
    for marker in (4294967295, 2147483647, -2147483648):
        assert _is_sentinel("mileage", marker) is True, marker


def test_plausible_odometer_values_never_sentinel() -> None:
    for v in (65534, 65536, 120000, 0):
        assert _is_sentinel("mileage", v) is False, v


def test_end_to_end_odometer_65535_survives() -> None:
    assert _map({"mileage": "65535"}).odometer_km == 65535


def test_end_to_end_lifetime_65535_survives() -> None:
    assert _map({"total_mileage": "65535"}).lifetime_distance_km == 65535


def test_end_to_end_odometer_uint32_sentinel_still_dropped() -> None:
    assert _map({"mileage": "4294967295"}).odometer_km is None


def test_end_to_end_soc_65535_still_dropped() -> None:
    assert _map({"battery_state_report.soc": "65535"}).battery_soc is None
