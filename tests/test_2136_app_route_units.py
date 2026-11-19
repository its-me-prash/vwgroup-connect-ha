# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2136: the app's trip address answers in final units, not tenths.

5.4.0 (#1805) read ``.../trips/<vin>/<type>/last`` but kept dividing the
consumption averages by ten, as the older ``tripstatistics`` address needs. The
app's own trip carries floats (21.8 kWh/100 km), so an Audi RS e-tron GT
(#923) showed 2.18 where the app shows 21.8. #2136 reports the same symptom on
an Audi Q5 hybrid; which address answered there is not confirmed.

Numbers below are the RS e-tron GT's from #923: a 75 km trip at 21.8 kWh/100 km
with 16.35 kWh used, a 47 km trip at 21.5, and a long-term window of 12280 km
at 25.3 kWh/100 km. The scale is decided per answer (the app route marks its
answer) and per value (a unit the trip declares wins). Nothing here was tried on
a car beyond what the reporters' diagnostics show.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.models import VehicleData

_FINAL = {"units": "final"}


def _parse(
    short: dict[str, Any] | None = None,
    long_: dict[str, Any] | None = None,
) -> VehicleData:
    c = VWEUClient.__new__(VWEUClient)
    d = VehicleData(vin="V")
    c._parse_trip_statistics(d, short or {}, long_ or {})
    return d


def _short(trip: dict[str, Any], *, final: bool = True) -> dict[str, Any]:
    return {"tripData": [trip], **(_FINAL if final else {})}


def test_the_app_envelope_is_marked_final_and_the_legacy_answer_is_not() -> None:
    trip = {"tripEndTimestamp": "2026-01-02T10:00:00Z", "mileage_km": 75}
    assert VWEUClient._trip_envelope({"data": trip}) == {
        "tripData": [trip], "units": "final",
    }
    assert VWEUClient._trip_envelope({"data": {"unrelated": 1}}) == {}


def test_last_trip_on_the_app_route_keeps_the_apps_numbers() -> None:
    d = _parse(_short({
        "tripEndTimestamp": "2026-01-02T10:00:00Z", "mileage_km": 75,
        "averageElectricConsumption": 21.8, "totalElectricConsumption": 16.35,
    }))
    assert d.last_trip_avg_electric_consumption_kwh_100km == pytest.approx(21.8)
    assert d.last_trip_total_electric_consumption_kwh == pytest.approx(16.35)
    assert d.last_trip_distance_km == 75.0


def test_total_is_derived_from_the_final_average_when_the_trip_has_none() -> None:
    d = _parse(_short({
        "tripEndTimestamp": "2026-01-02T10:00:00Z", "mileage_km": 47,
        "averageElectricConsumption": 21.5,
    }))
    assert d.last_trip_avg_electric_consumption_kwh_100km == pytest.approx(21.5)
    assert d.last_trip_total_electric_consumption_kwh == pytest.approx(10.105, abs=0.006)


def test_a_fuel_trip_on_the_app_route_is_not_divided() -> None:
    d = _parse(_short({
        "tripEndTimestamp": "2026-01-02T10:00:00Z", "mileage_km": 100,
        "averageFuelConsumption": 6.8,
    }))
    assert d.last_trip_avg_fuel_consumption_l_100km == pytest.approx(6.8)
    assert d.last_trip_total_fuel_consumption_l == pytest.approx(6.8)


def test_the_long_term_window_on_the_app_route() -> None:
    d = _parse(long_=_short({
        "tripEndTimestamp": "2026-01-02T10:00:00Z", "mileage_km": 12280,
        "startMileage_km": 48512, "overallMileage_km": 60792,
        "travelTime": 15200, "averageSpeed_kmph": 48,
        "averageElectricConsumption": 25.3, "averageFuelConsumption": 4.1,
    }))
    assert d.lifetime_avg_electric_consumption_kwh_100km == pytest.approx(25.3)
    assert d.lifetime_avg_fuel_consumption_l_100km == pytest.approx(4.1)
    assert d.lifetime_trip_distance_km == 12280
    assert d.lifetime_trip_start_odometer_km == 48512
    assert d.lifetime_travel_time_min == 15200
    assert d.lifetime_avg_speed_kmh == 48.0
    # The TOTAL_INCREASING statistic keeps meaning the odometer, not the window.
    assert d.lifetime_distance_km == 60792.0


@pytest.mark.parametrize("final", [True, False], ids=["app", "legacy"])
def test_a_zero_odometer_never_reaches_the_lifetime_distance(final: bool) -> None:
    """lifetime_distance_km feeds a TOTAL_INCREASING sensor: a 0 odometer is
    treated as no reading and the next field is used, exactly as before #2136."""
    d = _parse(long_=_short({
        "mileage_km": 120, "overallMileage_km": 0,
    }, final=final))
    assert d.lifetime_distance_km == 120.0


def test_the_legacy_long_term_answer_does_not_fill_the_window_fields() -> None:
    d = _parse(long_=_short({
        "mileage_km": 900, "startMileage_km": 100, "travelTime": 50,
        "averageSpeed_kmph": 40, "averageFuelConsumption": 68,
    }, final=False))
    assert d.lifetime_trip_distance_km is None
    assert d.lifetime_trip_start_odometer_km is None
    assert d.lifetime_travel_time_min is None
    assert d.lifetime_avg_speed_kmh is None


def test_the_legacy_route_still_divides_by_ten() -> None:
    d = _parse(
        _short({"mileage_km": 100, "averageElectricConsumption": 185,
                "averageFuelConsumption": 68}, final=False),
        _short({"averageElectricEngineConsumption": 185,
                "averageFuelConsumption": 68}, final=False),
    )
    assert d.last_trip_avg_electric_consumption_kwh_100km == 18.5
    assert d.last_trip_avg_fuel_consumption_l_100km == 6.8
    assert d.lifetime_avg_electric_consumption_kwh_100km == 18.5
    assert d.lifetime_avg_fuel_consumption_l_100km == 6.8


def test_a_declared_per_100_unit_is_never_divided_even_without_the_marker() -> None:
    d = _parse(_short({
        "mileage_km": 100,
        "averageElectricConsumption": 21.8,
        "averageElectricConsumptionUnit": "kWh_per_100km",
        "averageFuelConsumption": 6.8,
        "averageFuelConsumptionUnit": "l_per_100km",
    }, final=False))
    assert d.last_trip_avg_electric_consumption_kwh_100km == pytest.approx(21.8)
    assert d.last_trip_avg_fuel_consumption_l_100km == pytest.approx(6.8)


@pytest.mark.parametrize("final", [True, False])
def test_a_foreign_unit_gives_no_value_at_all(final: bool) -> None:
    d = _parse(_short({
        "mileage_km": 100,
        "averageFuelConsumption": 28.0,
        "averageFuelConsumptionUnit": "mpg",
        "averageElectricConsumption": 3.2,
        "averageElectricConsumptionUnit": "mi_per_kWh",
    }, final=final))
    assert d.last_trip_avg_fuel_consumption_l_100km is None
    assert d.last_trip_avg_electric_consumption_kwh_100km is None
    assert d.last_trip_total_fuel_consumption_l is None
    assert d.last_trip_total_electric_consumption_kwh is None


def test_a_negative_electric_average_is_kept_on_the_app_route() -> None:
    d = _parse(_short({
        "mileage_km": 10, "averageElectricConsumption": -2.2,
    }))
    assert d.last_trip_avg_electric_consumption_kwh_100km == pytest.approx(-2.2)


@pytest.mark.parametrize(
    ("final", "older", "newer", "expected"),
    [(True, 20.0, 18.5, 20.0), (False, 200, 185, 20.0)],
    ids=["app", "legacy"],
)
def test_the_older_key_still_wins_and_the_scale_follows_the_source(
    final: bool, older: float, newer: float, expected: float,
) -> None:
    d = _parse(_short({
        "mileage_km": 10,
        "averageElectricEngineConsumption": older,
        "averageElectricConsumption": newer,
    }, final=final))
    assert d.last_trip_avg_electric_consumption_kwh_100km == pytest.approx(expected)


def test_the_unit_of_the_key_that_won_is_the_one_that_counts() -> None:
    # The older name wins and declares a foreign unit: no value, and the
    # newer name's number is not used as a stand-in.
    d = _parse(_short({
        "mileage_km": 10,
        "averageElectricEngineConsumption": 3.2,
        "averageElectricEngineConsumptionUnit": "mi_per_kWh",
        "averageElectricConsumption": 21.8,
    }))
    assert d.last_trip_avg_electric_consumption_kwh_100km is None


def test_the_refuel_cycle_on_the_app_route() -> None:
    c = VWEUClient.__new__(VWEUClient)
    d = VehicleData(vin="V")
    c._parse_refuel_trip(d, {"tripData": [{
        "mileage_km": 200, "averageFuelConsumption": 5.8,
        "averageElectricConsumption": 19.5, "averageRecuperation": 3.1,
    }], "units": "final"})
    assert d.refuel_trip_avg_fuel_consumption_l_100km == pytest.approx(5.8)
    assert d.refuel_trip_avg_electric_consumption_kwh_100km == pytest.approx(19.5)
    assert d.refuel_trip_total_fuel_consumption_l == pytest.approx(11.6)
    assert d.refuel_trip_recuperation_kwh == pytest.approx(3.1)


def test_the_refuel_cycle_on_the_legacy_route_still_divides() -> None:
    c = VWEUClient.__new__(VWEUClient)
    d = VehicleData(vin="V")
    c._parse_refuel_trip(d, {"tripData": [{
        "mileage_km": 200, "averageFuelConsumption": 58,
        "averageElectricConsumption": 195, "averageRecuperation": 31,
    }]})
    assert d.refuel_trip_avg_fuel_consumption_l_100km == pytest.approx(5.8)
    assert d.refuel_trip_avg_electric_consumption_kwh_100km == pytest.approx(19.5)
    assert d.refuel_trip_recuperation_kwh == pytest.approx(3.1)


def test_the_refuel_cycle_honours_a_foreign_unit() -> None:
    c = VWEUClient.__new__(VWEUClient)
    d = VehicleData(vin="V")
    c._parse_refuel_trip(d, {"tripData": [{
        "mileage_km": 200, "averageFuelConsumption": 28.0,
        "averageFuelConsumptionUnit": "mpg",
    }], "units": "final"})
    assert d.refuel_trip_avg_fuel_consumption_l_100km is None


def test_a_list_answer_is_sorted_newest_first() -> None:
    old = {"tripEndTimestamp": "2026-01-01T08:00:00Z", "mileage_km": 1}
    mid = {"tripEndTimestamp": "2026-01-02T08:00:00Z", "mileage_km": 2}
    new = {"tripEndTimestamp": "2026-01-03T08:00:00Z", "mileage_km": 3}
    undated = {"mileage_km": 9}
    env = VWEUClient._trip_envelope({"data": [mid, undated, new, old]})
    assert env["tripData"][0] == new
    assert env["tripData"][-1] == undated
    d = _parse(env)
    assert d.last_trip_distance_km == 3.0


def test_the_long_term_totals_on_the_app_route() -> None:
    """#2136: the app's long-term answer carries the energy and fuel used in
    the window; the fuel key is spelled with a capital L."""
    d = _parse(long_=_short({
        "mileage_km": 5204, "overallMileage_km": 20000,
        "totalElectricConsumption_kwh": 947.128, "totalFuelConsumption_L": 130.1,
        "averageElectricConsumption": 18.2, "averageFuelConsumption": 2.5,
    }))
    assert d.lifetime_trip_total_electric_consumption_kwh == pytest.approx(947.128)
    assert d.lifetime_trip_total_fuel_consumption_l == pytest.approx(130.1)


def test_the_long_term_fuel_total_falls_back_to_the_lowercase_key() -> None:
    d = _parse(long_=_short({"totalFuelConsumption_l": 12.5}))
    assert d.lifetime_trip_total_fuel_consumption_l == pytest.approx(12.5)


def test_missing_long_term_totals_stay_none() -> None:
    d = _parse(long_=_short({"mileage_km": 900, "averageFuelConsumption": 4.1}))
    assert d.lifetime_trip_total_electric_consumption_kwh is None
    assert d.lifetime_trip_total_fuel_consumption_l is None


def test_a_zero_long_term_total_is_a_reading() -> None:
    """A plug-in hybrid driven only on fuel has used 0 kWh in the window."""
    d = _parse(long_=_short({
        "totalElectricConsumption_kwh": 0, "totalFuelConsumption_L": 0.0,
    }))
    assert d.lifetime_trip_total_electric_consumption_kwh == 0.0
    assert d.lifetime_trip_total_fuel_consumption_l == 0.0


def test_a_non_numeric_long_term_total_is_ignored() -> None:
    d = _parse(long_=_short({
        "totalElectricConsumption_kwh": "947", "totalFuelConsumption_L": None,
    }))
    assert d.lifetime_trip_total_electric_consumption_kwh is None
    assert d.lifetime_trip_total_fuel_consumption_l is None


def test_the_legacy_long_term_answer_does_not_fill_the_totals() -> None:
    d = _parse(long_=_short({
        "mileage_km": 900, "totalElectricConsumption_kwh": 947.128,
        "totalFuelConsumption_L": 130.1,
    }, final=False))
    assert d.lifetime_trip_total_electric_consumption_kwh is None
    assert d.lifetime_trip_total_fuel_consumption_l is None


def test_the_last_trip_fuel_total_reads_the_capital_l_key() -> None:
    d = _parse(short=_short({"mileage_km": 80, "totalFuelConsumption_L": 6.4}))
    assert d.last_trip_total_fuel_consumption_l == pytest.approx(6.4)


# ── what keeps the two long-term totals on screen ─────────────────────────────
_TOTAL_KEYS = (
    "lifetime_trip_total_electric_consumption_kwh",
    "lifetime_trip_total_fuel_consumption_l",
)


def test_the_long_term_totals_are_held_when_a_poll_omits_them() -> None:
    from custom_components.vag_connect.cariad.vehicle_cache import (
        CARRY_FORWARD_FIELDS,
        reconcile,
    )

    for k in _TOTAL_KEYS:
        assert k in CARRY_FORWARD_FIELDS
    prev = {_TOTAL_KEYS[0]: 947.128, _TOTAL_KEYS[1]: 130.1}
    out, _disc = reconcile(prev, {"battery_soc": 80})
    assert out[_TOTAL_KEYS[0]] == 947.128
    assert out[_TOTAL_KEYS[1]] == 130.1
    # a reset window ships a fresh 0 and wins over the carried value
    out, _disc = reconcile(prev, {_TOTAL_KEYS[0]: 0.0})
    assert out[_TOTAL_KEYS[0]] == 0.0


_VIN = "WAUZZZ00000000001"


def _spawned(vehicle: dict[str, Any], *, hide_empty: bool = True) -> set[str]:
    import asyncio
    from unittest.mock import MagicMock

    from custom_components.vag_connect import sensor as mod
    from custom_components.vag_connect.const import CONF_HIDE_EMPTY_ENTITIES

    c = MagicMock()
    c.vehicles = {_VIN: vehicle}
    c.data = c.vehicles
    c.is_read_only = MagicMock(return_value=False)
    c.is_companion = MagicMock(return_value=False)
    c.read_capability_hidden = MagicMock(return_value=False)
    c.command_capability_supported = MagicMock(return_value=None)
    c.command_method_available = MagicMock(return_value=False)
    c.async_add_listener = MagicMock(return_value=lambda: None)
    entry = MagicMock()
    entry.runtime_data = c
    entry.data = {"brand": "audi"}
    entry.options = {CONF_HIDE_EMPTY_ENTITIES: hide_empty}
    entry.async_on_unload = lambda x: None
    added: list[Any] = []
    asyncio.run(mod.async_setup_entry(MagicMock(), entry, lambda e: added.extend(e)))
    return {
        e.entity_description.key for e in added
        if getattr(e, "entity_description", None) is not None
    }


def test_the_total_sensors_spawn_only_with_a_reading_and_the_right_drivetrain() -> None:
    plug_in = {
        "vin": _VIN, "has_battery": True, "has_combustion": True,
        _TOTAL_KEYS[0]: 947.128, _TOTAL_KEYS[1]: 0.0,
    }
    assert set(_TOTAL_KEYS) <= _spawned(plug_in)  # 0.0 is a reading
    absent = {"vin": _VIN, "has_battery": True, "has_combustion": True}
    assert not set(_TOTAL_KEYS) & _spawned(absent)  # no phantom without data
    # ...and the allow-list holds even with "hide empty entities" switched off
    assert not set(_TOTAL_KEYS) & _spawned(absent, hide_empty=False)
    diesel = {
        "vin": _VIN, "has_battery": False, "has_combustion": True,
        _TOTAL_KEYS[0]: 5.0, _TOTAL_KEYS[1]: 130.1,
    }
    keys = _spawned(diesel)
    assert _TOTAL_KEYS[1] in keys
    assert _TOTAL_KEYS[0] not in keys  # no electric sensor on a diesel
