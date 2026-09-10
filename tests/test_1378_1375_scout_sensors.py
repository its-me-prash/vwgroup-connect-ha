# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1378 (Škoda Elroq) + #1375 (Audi S6 TDI) — new EU Data Act portal fields the
Vehicle Data Scout surfaced: short-term average electric consumption and the
SCR/AdBlue engine-start counter. Both are now mapped onto their own sensors; the
trip-id metadata leaf is consumed so it stops re-reporting as undiscovered.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(points: list[dict]) -> VehicleData:
    fields = _walk_fields({"data": points})
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_short_term_consumption_is_parsed_from_unit_string() -> None:
    d = _map([{"dataFieldName": "shortTermAverageConsumption",
               "value": "15.8 kWh/100km", "key": "k"}])
    assert d.short_term_avg_electric_consumption_kwh_100km == 15.8


def test_fuel_consumption_is_not_mislabelled_as_electric() -> None:
    # a PHEV/ICE shipping this leaf as l/100km must NOT land in the electric field
    # (the unit guard requires kWh/Wh).
    d = _map([{"dataFieldName": "shortTermAverageConsumption",
               "value": "5.2 l/100km", "key": "k"}])
    assert d.short_term_avg_electric_consumption_kwh_100km is None


def test_engine_starts_counter_is_parsed() -> None:
    d = _map([{"dataFieldName": "scr_number_of_engine_starts", "value": "7",
               "key": "k"}])
    assert d.engine_starts_count == 7


def test_engine_starts_zero_is_kept() -> None:
    d = _map([{"dataFieldName": "scr_number_of_engine_starts", "value": "0",
               "key": "k"}])
    assert d.engine_starts_count == 0


def test_tripId_is_handled_without_inventing_a_sensor() -> None:
    # a bare trip identifier must not crash the mapper and must not invent any
    # field; the parser just consumes it (first("tripId")) so the Scout stops
    # re-reporting it every poll.
    d = _map([{"dataFieldName": "tripId", "value": "abc-123", "key": "k"}])
    assert d.short_term_avg_electric_consumption_kwh_100km is None
    assert d.engine_starts_count is None


def test_absent_scout_fields_are_inert() -> None:
    d = _map([{"dataFieldName": "battery_state_report.soc", "value": "50",
               "key": "k"}])
    assert d.short_term_avg_electric_consumption_kwh_100km is None
    assert d.engine_starts_count is None
