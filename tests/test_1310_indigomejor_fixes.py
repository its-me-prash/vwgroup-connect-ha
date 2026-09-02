# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1310 (indigomejor) — two grounded fixes from his debug captures.

1. The Škoda ``primaryEngineRange.currentSoCInPercent`` was mapped to a 12V SoC
   sensor on an unverified #116 scout note. His raw payloads show the backend
   mirrors the fuel level into that field on a combustion engine (100/100 full,
   41/41 part-tank, fuel gauge matching), so a "SoC" equal to the fuel level is
   the fuel duplicated, not a 12V reading — it must not surface as one.
2. Škoda fills the per-trip (last_trip_*) keys from its own mysmob parse, so it
   belongs in the sensor-spawn brand gate. It does NOT fill the lifetime_*
   aggregates (its mysmob endpoint returns a weekly window, not a lifetime total —
   corrected in a later #1310 pass). The CARIAD-BFF FETCH gate stays audi/volkswagen
   only (Škoda has the per-trip data inline), so no wrong trip-stats call fires.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.api.skoda import _primary_soc_or_none


# ── 1. 12V-vs-fuel mirror guard ─────────────────────────────────────────────

@pytest.mark.parametrize("soc,fuel,engine", [
    (41, 41, "gasoline"),
    (100, 100, "gasoline"),
    (33, 33, "diesel"),
    (60, 60, "PETROL"),  # case-insensitive
    (50, 50, "cng"),
])
def test_combustion_soc_equal_to_fuel_is_suppressed(soc, fuel, engine) -> None:
    # a combustion "SoC" that equals the fuel level is the fuel duplicated → None
    assert _primary_soc_or_none(soc, fuel, engine) is None


@pytest.mark.parametrize("soc,fuel,engine", [
    (80, 41, "gasoline"),   # genuinely distinct value on a combustion car → kept
    (12, 90, "diesel"),
])
def test_combustion_soc_distinct_from_fuel_is_kept(soc, fuel, engine) -> None:
    assert _primary_soc_or_none(soc, fuel, engine) == soc


@pytest.mark.parametrize("engine", ["electric", "hybrid", "", None])
def test_non_combustion_soc_always_kept(engine) -> None:
    # not a combustion engine → the field is not a fuel mirror; keep it even if it
    # happens to equal the fuel value (e.g. an HV SoC on a hybrid).
    assert _primary_soc_or_none(80, 80, engine) == 80


def test_none_soc_stays_none() -> None:
    assert _primary_soc_or_none(None, 41, "gasoline") is None


def test_missing_fuel_keeps_soc() -> None:
    # no fuel value to compare against → cannot be a mirror, keep the SoC
    assert _primary_soc_or_none(55, None, "gasoline") == 55


# ── 2. Trip-stats brand gates (spawn includes Škoda; fetch does not) ─────────

def test_skoda_in_sensor_spawn_gate() -> None:
    from custom_components.vag_connect.sensor import _TRIP_STATS_BRANDS
    assert "skoda" in _TRIP_STATS_BRANDS
    assert {"audi", "volkswagen"} <= _TRIP_STATS_BRANDS


def test_spawn_gate_covers_trip_stat_keys() -> None:
    # last_trip_* (Škoda + Audi/VW) and lifetime_* (Audi/VW only) must all be in
    # the spawn key-set. Škoda leaves lifetime_* None → hide-empty → no sensor, but
    # the keys stay so Audi/VW's lifetime aggregates still spawn.
    from custom_components.vag_connect.sensor import _TRIP_STATS_KEYS
    assert {
        "last_trip_distance_km",
        "last_trip_avg_speed_kmh",
    } <= _TRIP_STATS_KEYS
    assert {
        "lifetime_distance_km",
        "lifetime_avg_fuel_consumption_l_100km",
        "lifetime_avg_electric_consumption_kwh_100km",
    } <= _TRIP_STATS_KEYS


def test_skoda_not_in_coordinator_fetch_gate() -> None:
    # the CARIAD-BFF /tripstatistics fetch must NOT fire for Škoda (its trip data
    # comes from the mysmob parse), so the fetch gate stays audi/volkswagen only.
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    assert "skoda" not in VagConnectCoordinator._TRIP_STATS_BRANDS
    assert set(VagConnectCoordinator._TRIP_STATS_BRANDS) == {"audi", "volkswagen"}


# ── follow-up fixes from indigomejor's v4.6.0b1 field test (comment 5507008727) ──

def test_suppressed_12v_soc_is_not_carried_forward() -> None:
    # #1310 — _primary_soc_or_none suppresses the fuel-mirror by returning None;
    # carrying primary_engine_soc_pct forward resurrected the stale full-tank value
    # and latched the bogus 12V sensor at 100 % forever. It must NOT be carried.
    from custom_components.vag_connect.cariad.vehicle_cache import (
        CARRY_FORWARD_FIELDS,
        reconcile,
    )
    assert "primary_engine_soc_pct" not in CARRY_FORWARD_FIELDS
    merged, _ = reconcile({"primary_engine_soc_pct": 100},
                          {"primary_engine_soc_pct": None})
    assert merged["primary_engine_soc_pct"] is None  # suppression sticks


def test_skoda_weekly_overview_is_not_lifetime_and_last_trip_uses_date() -> None:
    # #1310 — the mysmob /trip-statistics response is a CURRENT-WEEK window, so
    # overallMileageInKm is weekly (not lifetime); and last_trip_* come from the
    # most-recent per-DAY entry, timestamped by `date` (there is no tripEndTimestamp).
    from custom_components.vag_connect.cariad.api.skoda import _apply_trip_statistics
    from custom_components.vag_connect.cariad.models import VehicleData
    d = VehicleData(vin="X")
    _apply_trip_statistics({
        "overallMileageInKm": 33, "overallAverageFuelConsumption": 5.4,
        "detailedStatistics": [
            {"date": "2026-08-29", "mileageInKm": 6, "averageSpeedInKmph": 30},
            {"date": "2026-09-01", "mileageInKm": 33, "travelTimeInMin": 40,
             "averageSpeedInKmph": 50, "averageFuelConsumption": 5.4},
        ],
    }, d)
    assert d.lifetime_distance_km is None               # weekly total ≠ lifetime
    assert d.lifetime_avg_fuel_consumption_l_100km is None
    assert d.last_trip_distance_km == 33                # newest day (09-01), not [0]
    assert d.last_trip_avg_speed_kmh == 50
    assert d.last_trip_duration_min == 40
    assert d.last_trip_timestamp == "2026-09-01"


def test_skoda_empty_detailed_statistics_leaves_last_trip_none() -> None:
    from custom_components.vag_connect.cariad.api.skoda import _apply_trip_statistics
    from custom_components.vag_connect.cariad.models import VehicleData
    d = VehicleData(vin="X")
    _apply_trip_statistics({"overallMileageInKm": 33, "detailedStatistics": []}, d)
    assert d.last_trip_distance_km is None
    assert d.last_trip_timestamp is None
    assert d.lifetime_distance_km is None


def test_diagnostics_scrub_masks_vin_inside_render_url() -> None:
    # #1310 — render_url embeds the full VIN in the blob filename; the string-value
    # scrub masked only email + GPS, so the VIN leaked. It's masked now.
    import json

    from custom_components.vag_connect.diagnostics import _scrub
    out = _scrub({
        "render_url": (
            "https://x.blob.core.windows.net/widget-renders/"
            "TMBJK0NX4MY109119.png?etag=0x8DEEC19E6798565"
        ),
        "composite_render_urls": {"side": "https://x/WAUZZZ8T99A012765.png"},
    }, gps_round=False)
    blob = json.dumps(out)
    assert "TMBJK0NX4MY109119" not in blob      # full VIN gone
    assert "WAUZZZ8T99A012765" not in blob       # composite VIN gone too
    assert "109119" in blob                      # masked tail survives
    assert "0x8DEEC19E6798565" in blob           # etag hash untouched
