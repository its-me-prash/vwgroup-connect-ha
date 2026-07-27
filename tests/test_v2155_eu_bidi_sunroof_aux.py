# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.5 — EU Data Act portal new-field mappings + aux sentinel fix.

#541 — V2G / bidirectional-charging upper/lower charge-level limits
       (bidirectional_charging_mode.bidi_max_Soc / bidi_min_Soc → percent).
#544 — sunroof motor hood 1 POSITION (position_sunroof_motor_hood_1 → percent),
       distinct from the open/closed STATE; and the aux-consumer consumption
       65535 uint16 not-available SENTINEL drop (must read None, not 65535).

All EU-Data-Act dialect only; mirrors the v2.15.3/v2.15.4 mapping style.
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


# ── #541 — V2G / bidirectional charge-level limits ───────────────────────────

def test_bidi_max_min_container_spelling() -> None:
    d = _map({
        "bidirectional_charging_mode.bidi_max_Soc": "80",
        "bidirectional_charging_mode.bidi_min_Soc": "20",
    })
    assert d.bidi_max_charge_level_pct == 80
    assert d.bidi_min_charge_level_pct == 20


def test_bidi_max_min_bare_spelling() -> None:
    d = _map({"bidi_max_Soc": "90", "bidi_min_Soc": "10"})
    assert d.bidi_max_charge_level_pct == 90
    assert d.bidi_min_charge_level_pct == 10


def test_bidi_consumed_not_in_raw() -> None:
    d = _map({"bidirectional_charging_mode.bidi_max_Soc": "75"})
    assert "bidirectional_charging_mode.bidi_max_Soc" not in d.raw_unmapped_fields


def test_bidi_sentinel_dropped_and_consumed() -> None:
    # 65535 uint16 not-available sentinel → None. v2.25.0: mapped field, no
    # reading → consumed, not left Scout-visible.
    d = _map_flatlog(("bidirectional_charging_mode.bidi_max_Soc", "65535"))
    assert d.bidi_max_charge_level_pct is None
    assert "bidirectional_charging_mode.bidi_max_Soc" not in d.raw_unmapped_fields


# ── #544 — sunroof motor hood 1 POSITION (distinct from STATE) ───────────────

def test_sunroof_position_maps() -> None:
    d = _map({"position_sunroof_motor_hood_1": "45"})
    assert d.sunroof_position_pct == 45


def test_sunroof_position_zero_is_closed_not_dropped() -> None:
    # 0 = closed is a VALID position reading (not a sentinel) → must survive.
    d = _map({"position_sunroof_motor_hood_1": "0"})
    assert d.sunroof_position_pct == 0


def test_sunroof_position_distinct_from_state() -> None:
    # STATE (open/closed) and POSITION (%) are independent fields.
    d = _map({
        "state_sunroof_motor_hood_1": "2",       # open
        "position_sunroof_motor_hood_1": "30",
    })
    assert d.sunroof_open is True
    assert d.sunroof_position_pct == 30


def test_sunroof_position_sentinel_dropped_and_consumed() -> None:
    d = _map_flatlog(("position_sunroof_motor_hood_1", "65535"))
    assert d.sunroof_position_pct is None
    # v2.25.0: mapped field, sentinel reading → consumed, not Scout-visible.
    assert "position_sunroof_motor_hood_1" not in d.raw_unmapped_fields


# ── #544 — aux-consumer consumption 65535 SENTINEL fix ───────────────────────

def test_aux_consumption_65535_sentinel_dropped() -> None:
    # uint16 not-available sentinel must NOT pass through as a real value.
    d = _map_flatlog(
        ("long_term_data_average_aux_consumer_consumption", "65535"),
        ("short_term_data_average_aux_consumer_consumption", "65535"),
    )
    assert d.lifetime_avg_aux_consumption_kwh_100km is None
    assert d.last_trip_avg_aux_consumption_kwh_100km is None
    # v2.25.0: mapped fields with a sentinel reading are consumed, not left
    # Scout-visible (they must not re-report every poll).
    assert (
        "long_term_data_average_aux_consumer_consumption"
        not in d.raw_unmapped_fields
    )
    assert (
        "short_term_data_average_aux_consumer_consumption"
        not in d.raw_unmapped_fields
    )


def test_aux_consumption_valid_value_still_maps() -> None:
    # Valid path intact: dict kwH/1000km → kWh/100 km (÷10).
    d = _map({
        "long_term_data_average_aux_consumer_consumption": "120",
        "short_term_data_average_aux_consumer_consumption": "95",
    })
    assert d.lifetime_avg_aux_consumption_kwh_100km == 12.0
    assert d.last_trip_avg_aux_consumption_kwh_100km == 9.5
