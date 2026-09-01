# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1310 (indigomejor) — two grounded fixes from his debug captures.

1. The Škoda ``primaryEngineRange.currentSoCInPercent`` was mapped to a 12V SoC
   sensor on an unverified #116 scout note. His raw payloads show the backend
   mirrors the fuel level into that field on a combustion engine (100/100 full,
   41/41 part-tank, fuel gauge matching), so a "SoC" equal to the fuel level is
   the fuel duplicated, not a 12V reading — it must not surface as one.
2. Škoda fills BOTH trip-stat groups from its own mysmob parse — the 4 per-trip
   keys (last_trip_*) AND the 3 lifetime_* aggregates — so it belongs in the
   sensor-spawn brand gate. The CARIAD-BFF FETCH gate stays audi/volkswagen only
   (Škoda has the data inline), so no wrong trip-stats call fires for Škoda.
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


def test_spawn_gate_covers_both_trip_stat_groups() -> None:
    # Škoda populates last_trip_* AND lifetime_*, so both groups must be in the
    # spawn key-set — otherwise the lifetime_* sensors would never appear for it.
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
