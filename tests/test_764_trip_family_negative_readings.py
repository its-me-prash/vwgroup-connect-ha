# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A negative reading in the portal's trip family, decided per field.

Three members of the family (the trip-odometer endpoints) screened negatives;
their twenty-odd siblings did not, so a negative could reach a DISTANCE- or
DURATION-classed sensor and its long-term statistics — a negative trip distance,
a negative travel time, a negative average speed.

The guard is NOT applied by prefix, because the family is genuinely mixed, and
the evidence says so:

* The catalogue documents the maintenance countdowns as SIGNED on purpose:
  "Indicates the remaining running distance until the next service; if this
  limit was exceeded, this value indicates the distance that has been driven
  since then (always in km)". Same for the oil interval and both time twins.
  Those are normalised by the parser's own ``_svc`` helper (negate-if-negative,
  grounded in #39/#36) and must keep passing negatives through.
* The one real trip-family capture in the archive (#709, @dazj1990,
  2026-08-18) backs that split exactly: the whole trip family arrives positive
  (``long_term_data_start_mileage`` 121492, ``long_term_data_mileage`` 5431,
  ``short_term_data_mileage`` 38, ``short_term_data_travel_time`` 41), and the
  ONLY negatives in the payload are ``maintenance_interval_distance_until_
  oil_change`` -12553, ``..._until_inspection`` -13679 and
  ``maintenance_interval__time_until_inspection`` -203.
* ``maintenance_interval_monthly_mileage`` is the counter-example that makes
  "decide per field" necessary: it carries the maintenance prefix but is "the
  distance driven monthly in kilometer", so it IS guarded.
* The electric, auxiliary-consumer and recuperation averages are deliberately
  left unguarded: they are net-energy figures and a trip that recuperates more
  than it draws can legitimately come out negative.

(The ``-1`` "not set yet" marker the original guard's comment attributed to
#764 is not in that issue — its payload is all 65535/1 tyre-and-charge
sentinels — and does not appear in any archived capture. The guard stands on
"a distance is never negative" instead; the attribution is corrected in the
code.)
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# @dazj1990's real payload (#709), trip half only — every value positive.
REAL_TRIP_CAPTURE = {
    "long_term_data_start_mileage": "121492",
    "long_term_data_mileage": "5431",
    "long_term_data_average_speed": "56",
    "short_term_data_mileage": "38",
    "short_term_data_travel_time": "41",
    "short_term_data_average_fuel_consumption": "43",
    "long_term_data_average_fuel_consumption": "32",
    "short_term_data_average_electr_engine_consumption": "17",
    "long_term_data_average_electr_engine_consumption": "56",
}

#: field -> (source leaf, attribute) for every member that must drop a negative
GUARDED = {
    "last trip distance": ("short_term_data_mileage", "last_trip_distance_km"),
    "last trip duration": ("short_term_data_travel_time", "last_trip_duration_min"),
    "lifetime travel time": ("long_term_data_travel_time", "lifetime_travel_time_min"),
    "lifetime average speed": ("long_term_data_average_speed", "lifetime_avg_speed_kmh"),
    "monthly average distance": (
        "maintenance_interval_monthly_mileage", "monthly_mileage_km"),
    "lifetime trip distance": ("long_term_data_mileage", "lifetime_trip_distance_km"),
    "lifetime start odometer": (
        "long_term_data_start_mileage", "lifetime_trip_start_odometer_km"),
    "last trip start odometer": (
        "short_term_data_start_mileage", "last_trip_start_odometer_km"),
    "lifetime fuel average": (
        "long_term_data_average_fuel_consumption",
        "lifetime_avg_fuel_consumption_l_100km"),
    "last trip fuel average": (
        "short_term_data_average_fuel_consumption",
        "last_trip_avg_fuel_consumption_l_100km"),
    "lifetime gas average": (
        "long_term_data_average_gas_consumption",
        "lifetime_avg_gas_consumption_kg_100km"),
    "last trip gas average": (
        "short_term_data_average_gas_consumption",
        "last_trip_avg_gas_consumption_kg_100km"),
    "lifetime range gain": (
        "long_term_data_range_gain_distance", "lifetime_range_gain_km"),
    "last trip range gain": (
        "short_term_data_range_gain_distance", "last_trip_range_gain_km"),
    "lifetime zero-emission distance": (
        "long_term_data_zero_emission_distance", "lifetime_zero_emission_km"),
    "last trip zero-emission distance": (
        "short_term_data_zero_emission_distance", "last_trip_zero_emission_km"),
}

#: deliberately NOT guarded — net-energy figures that can legitimately be
#: negative on a trip that recuperates more than it draws.
NET_ENERGY = {
    "lifetime electric average": (
        "long_term_data_average_electr_engine_consumption",
        "lifetime_avg_electric_consumption_kwh_100km"),
    "last trip electric average": (
        "short_term_data_average_electr_engine_consumption",
        "last_trip_avg_electric_consumption_kwh_100km"),
    "lifetime aux average": (
        "long_term_data_average_aux_consumer_consumption",
        "lifetime_avg_aux_consumption_kwh_100km"),
    "last trip aux average": (
        "short_term_data_average_aux_consumer_consumption",
        "last_trip_avg_aux_consumption_kwh_100km"),
    "lifetime recuperation average": (
        "long_term_data_average_recuperation",
        "lifetime_avg_recuperation_kwh_100km"),
    "last trip recuperation average": (
        "short_term_data_average_recuperation",
        "last_trip_avg_recuperation_kwh_100km"),
}


def _map(fields: dict) -> VehicleData:
    syn: dict = {}
    return map_dataset_to_vehicle_data(
        _walk_fields(fields, None, syn), VehicleData(vin="X"), field_syn=syn
    )


def test_a_negative_reading_is_dropped_on_every_guarded_field() -> None:
    """Collected rather than fail-fast: an unguarded sibling should be named in
    the failure, not hidden behind the first one."""
    leaked = []
    for label, (leaf, attr) in GUARDED.items():
        for negative in ("-1", "-38", "-12553"):
            got = getattr(_map({leaf: negative}), attr)
            if got is not None:
                leaked.append(f"{label} ({attr}) kept {negative} as {got}")
    assert not leaked, "\n".join(leaked)


def test_the_same_fields_still_map_a_real_reading() -> None:
    """The guard must not cost the normal case — including zero, which is a
    legitimate reading for a trip that has just been reset."""
    for label, (leaf, attr) in GUARDED.items():
        assert getattr(_map({leaf: "12"}), attr) is not None, label
        assert getattr(_map({leaf: "0"}), attr) == 0, f"{label} dropped a real 0"


def test_the_real_capture_maps_completely() -> None:
    d = _map(REAL_TRIP_CAPTURE)
    assert d.lifetime_trip_start_odometer_km == 121492
    assert d.lifetime_trip_distance_km == 5431
    assert d.lifetime_avg_speed_kmh == 56
    assert d.last_trip_distance_km == 38
    assert d.last_trip_duration_min == 41
    assert d.last_trip_avg_fuel_consumption_l_100km == 4.3
    assert d.lifetime_avg_fuel_consumption_l_100km == 3.2


def test_the_maintenance_countdowns_keep_their_documented_negatives() -> None:
    """The catalogue says a negative here means "overdue by", and the parser
    normalises it to a positive magnitude. A blanket non-negative guard would
    have turned an overdue service into no reading at all — @dazj1990's real
    payload is exactly that car.
    """
    d = _map({
        "maintenance_interval_distance_until_oil_change": "-12553",
        "maintenance_interval_distance_until_inspection": "-13679",
        "maintenance_interval__time_until_inspection": "-203",
    })
    assert d.oil_service_km == 12553
    assert d.service_km == 13679
    assert d.service_due_in_days == 203


def test_the_net_energy_averages_may_stay_negative() -> None:
    """A downhill trip can recuperate more than it draws, so these are the one
    part of the family where a negative reading may be the truth. Pinned so the
    "inconsistency" is not tidied away."""
    for label, (leaf, attr) in NET_ENERGY.items():
        d = _map({leaf: "-25"})
        assert getattr(d, attr) == -2.5, f"{label} ({attr}) was dropped"


def test_the_warning_flags_are_untouched() -> None:
    d = _map({"maintenance_interval_oil_change_warning": "1",
              "maintenance_interval_inspection_warning": "0"})
    assert d.warning_oil is True
    assert d.warning_inspection is False


def test_no_guarded_field_is_also_a_signed_one() -> None:
    """A field cannot be in both sets — that would mean the per-field decision
    contradicts itself."""
    assert not set(GUARDED) & set(NET_ENERGY)
    assert not {a for _, a in GUARDED.values()} & {a for _, a in NET_ENERGY.values()}
