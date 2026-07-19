# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#764 re-sweep — three portal-mapper bugs surfaced by Motii08's real
one-time export (Cupra Leon VZ e-Hybrid 272 PHEV, captured while charging):

1. charging_state='chargingHvBattery' was not in the is_charging token set, so
   the charging binary_sensor read OFF while the car was actively charging.
2. charging_mode='invalid' (the portal no-reading sentinel) leaked the literal
   'invalid' onto charging_preferred_mode instead of being dropped like the
   sibling plug-state strings.
3. long_term_data_start_mileage=-1 (a 'not set yet' sentinel) leaked -1 km onto
   the lifetime trip start odometer.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


# ── 1. charging_state ────────────────────────────────────────────────────────

def test_charging_hv_battery_is_charging() -> None:
    # Motii08's real value while actively charging.
    assert _map({"charging_state": "chargingHvBattery"}).is_charging is True


def test_charging_dc_active_is_charging() -> None:
    assert _map({"charging_state": "chargingDcActive"}).is_charging is True


def test_charging_ac_active_still_charging() -> None:
    assert _map({"charging_state": "chargingAcActive"}).is_charging is True


def test_ready_for_charging_is_not_charging() -> None:
    # a plugged-but-idle state must stay NOT charging.
    assert _map({"charging_state": "readyForCharging"}).is_charging is False
    assert _map({"charging_state": "notReadyForCharging"}).is_charging is False


# ── 2. charging_mode junk drop ───────────────────────────────────────────────

def test_charging_mode_invalid_dropped() -> None:
    assert _map({"charging_mode": "invalid"}).charging_preferred_mode is None


def test_charging_mode_real_value_kept() -> None:
    d = _map({"charging_mode": "immediatelyDefault"})
    assert d.charging_preferred_mode is not None
    assert d.charging_preferred_mode.lower() != "invalid"


# ── 3. start-odometer negative sentinel guard ────────────────────────────────

def test_negative_start_mileage_dropped() -> None:
    d = _map({"long_term_data_start_mileage": "-1"})
    assert d.lifetime_trip_start_odometer_km is None


def test_valid_start_mileage_kept() -> None:
    d = _map({"short_term_data_start_mileage": "451"})
    assert d.last_trip_start_odometer_km == 451


def test_negative_trip_distance_dropped() -> None:
    assert _map({"long_term_data_mileage": "-1"}).lifetime_trip_distance_km is None
