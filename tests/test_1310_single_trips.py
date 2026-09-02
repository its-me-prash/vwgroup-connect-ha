# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1310 — last_trip_* from the mysmob single-trips endpoint.

The WEEK/MONTH/YEAR trip-statistics overview returns a metric-hollow
detailedStatistics on combustion cars (only a date), so last_trip_* never spawned
(indigomejor). The single-trips endpoint carries genuine per-trip records
(SingleTripDto with mileageInKm + travelTimeInMin + averageSpeedInKmph +
averageFuelConsumption); _apply_single_trip picks the most recent and fills from it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.skoda import _apply_single_trip
from custom_components.vag_connect.cariad.models import VehicleData


def test_single_trip_fills_last_trip_from_most_recent():
    payload = {"dailyTrips": [
        {"date": "2026-09-05", "trips": [
            {"endTime": "2026-09-05T08:00:00", "mileageInKm": 12, "travelTimeInMin": 20,
             "averageSpeedInKmph": 36, "averageFuelConsumption": 6.1,
             "startMileageInKm": 1000},
        ]},
        {"date": "2026-09-06", "trips": [  # newest day
            {"endTime": "2026-09-06T07:00:00", "mileageInKm": 33, "travelTimeInMin": 40,
             "averageSpeedInKmph": 49, "averageFuelConsumption": 5.8,
             "startMileageInKm": 1012},
            {"endTime": "2026-09-06T18:30:00", "mileageInKm": 8, "travelTimeInMin": 15,
             "averageSpeedInKmph": 32, "averageFuelConsumption": 7.2,
             "startMileageInKm": 1045},  # latest endTime within the newest day
        ]},
    ]}
    d = VehicleData(vin="V")
    _apply_single_trip(payload, d)
    assert d.last_trip_distance_km == 8
    assert d.last_trip_duration_min == 15
    assert d.last_trip_avg_speed_kmh == 32
    assert d.last_trip_avg_fuel_consumption_l_100km == 7.2
    assert d.last_trip_start_odometer_km == 1045
    assert d.last_trip_timestamp == "2026-09-06"


def test_single_trip_partial_trip_fills_only_present_metrics():
    d = VehicleData(vin="V")
    _apply_single_trip({"dailyTrips": [{"date": "2026-09-06", "trips": [
        {"endTime": "t", "mileageInKm": 33, "travelTimeInMin": 40}]}]}, d)
    assert d.last_trip_distance_km == 33
    assert d.last_trip_duration_min == 40
    assert d.last_trip_avg_speed_kmh is None      # absent → stays None, no crash
    assert d.last_trip_avg_fuel_consumption_l_100km is None


def test_single_trip_tolerates_empty_or_missing():
    d = VehicleData(vin="V")
    for bad in (None, {}, {"dailyTrips": []}, {"dailyTrips": [{"date": "x", "trips": []}]},
                {"dailyTrips": "nope"}, {"dailyTrips": [None, {"trips": None}]}):
        _apply_single_trip(bad, d)
    assert d.last_trip_distance_km is None
