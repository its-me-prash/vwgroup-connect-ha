# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1805: trip statistics over the addresses the Audi app uses.

The integration only asked ``.../vehicles/<vin>/tripstatistics?type=...``. On
an RS e-tron GT that address answers 404 although the car lists the trip
statistics capability. The Audi app (myAudi 5.9.0) does not use that address:
it reads ``.../trips/<vin>/<type>/last`` with the type in lower case
(``shortterm``, ``longterm``, ``cyclic``) and gets the trip under ``data``.

So when the old address answers 404, the app's address is asked. One request
decides whether the car has it; only then are the other two types read.
Everything here is synthetic; no car was available to try it on.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError
from custom_components.vag_connect.cariad.models import VehicleData

_BASE = "https://b"
_OLD = f"{_BASE}/vehicle/v1/vehicles/V/tripstatistics"
_APP = f"{_BASE}/vehicle/v1/trips/V"
_TRIP = {
    "id": "1", "tripType": "shortTerm", "vehicleType": "electric",
    "tripEndTimestamp": "2026-01-02T10:00:00Z", "mileage_km": 12.5, "travelTime": 20,
    "averageSpeed_kmph": 37, "overallMileage_km": 50123, "startMileage_km": 50110,
    "averageElectricConsumption": 18.5,  # the app answers in final units (#2136)
}
_MARK = {"units": "final"}


def _client(routes: dict[str, Any]) -> tuple[VWEUClient, list[str]]:
    """``routes`` maps an address (query appended as ``?type=x``) to an answer or an error."""
    c = VWEUClient.__new__(VWEUClient)
    c.parser_stats = {}
    asked: list[str] = []

    async def get(url: str, params: dict[str, Any] | None = None) -> Any:
        key = url + (f"?type={params['type']}" if params and "type" in params else "")
        asked.append(key)
        answer = routes.get(key, APIError(404, url, "not found"))
        if isinstance(answer, Exception):
            raise answer
        return answer

    c._get = get  # type: ignore[method-assign]
    return c, asked


def _fetch(c: VWEUClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return asyncio.run(c._fetch_trip_statistics("V", _BASE))


def test_the_apps_address_is_asked_when_the_old_one_is_absent() -> None:
    long_trip = {**_TRIP, "tripType": "longTerm", "mileage_km": 900.0}
    cyclic_trip = {**_TRIP, "tripType": "cyclic", "mileage_km": 300.0}
    c, asked = _client({
        f"{_APP}/shortterm/last": {"data": _TRIP},
        f"{_APP}/longterm/last": {"data": long_trip},
        f"{_APP}/cyclic/last": {"data": cyclic_trip},
    })
    short, long_, cyclic = _fetch(c)
    assert asked == [
        f"{_OLD}?type=shortTerm",
        f"{_APP}/shortterm/last",
        f"{_APP}/longterm/last",
        f"{_APP}/cyclic/last",
    ]
    assert short == {"tripData": [_TRIP], **_MARK}
    assert long_ == {"tripData": [long_trip], **_MARK}
    assert cyclic == {"tripData": [cyclic_trip], **_MARK}
    assert c.parser_stats.get("trip_statistics", {}).get("fail", 0) == 0


def test_a_car_without_either_address_costs_one_more_request_and_no_failure() -> None:
    c, asked = _client({})
    assert _fetch(c) == ({}, {}, {})
    assert asked == [f"{_OLD}?type=shortTerm", f"{_APP}/shortterm/last"]
    assert c.parser_stats.get("trip_statistics", {}).get("fail", 0) == 0


def test_the_old_address_is_still_the_first_choice() -> None:
    old = {"tripData": [_TRIP]}
    c, asked = _client({f"{_OLD}?type=shortTerm": old, f"{_OLD}?type=longTerm": old, f"{_OLD}?type=cyclic": old})
    assert _fetch(c) == (old, old, old)
    assert not any("/trips/" in a for a in asked)


def test_an_old_address_that_answered_the_first_request_is_not_left() -> None:
    # The old address answers the short-term request (even with nothing in it)
    # and 404 only for the long-term one: that is the earlier behaviour, the
    # app's address is not asked and the cyclic request still goes to the old one.
    c, asked = _client({f"{_OLD}?type=shortTerm": {}, f"{_OLD}?type=cyclic": {"tripData": [_TRIP]}})
    short, long_, cyclic = _fetch(c)
    assert asked == [f"{_OLD}?type=shortTerm", f"{_OLD}?type=longTerm", f"{_OLD}?type=cyclic"]
    assert (short, long_, cyclic) == ({}, {}, {"tripData": [_TRIP]})


def test_the_other_two_types_may_be_missing() -> None:
    c, asked = _client({f"{_APP}/shortterm/last": {"data": _TRIP}})
    short, long_, cyclic = _fetch(c)
    assert short == {"tripData": [_TRIP], **_MARK}
    assert (long_, cyclic) == ({}, {})
    assert c.parser_stats.get("trip_statistics", {}).get("fail", 0) == 0


def test_a_server_error_on_the_apps_address_still_counts_as_a_failure() -> None:
    c, _ = _client({f"{_APP}/shortterm/last": APIError(502, "u", "bad gateway")})
    assert _fetch(c) == ({}, {}, {})
    assert c.parser_stats.get("trip_statistics", {}).get("fail", 0) == 1


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ({"data": _TRIP}, {"tripData": [_TRIP], **_MARK}),                       # one trip under data
        ({"data": [_TRIP, _TRIP]}, {"tripData": [_TRIP, _TRIP], **_MARK}),       # a list under data
        (_TRIP, {"tripData": [_TRIP], **_MARK}),                            # the trip itself
        ({"data": None}, {}),
        ({"data": {}}, {}),
        ({"data": [1, "x"]}, {}),
        ({"data": {"unrelated": 1}}, {}),                               # not a trip
        ([], {}),
        ("text", {}),
    ],
    ids=["one", "list", "bare", "null", "empty", "no objects", "not a trip", "array", "text"],
)
def test_the_answer_is_brought_into_the_shape_the_reader_knows(answer: Any, expected: dict[str, Any]) -> None:
    c, _ = _client({f"{_APP}/shortterm/last": answer})
    assert _fetch(c)[0] == expected


def test_an_answer_without_a_trip_ends_the_asking() -> None:
    c, asked = _client({f"{_APP}/shortterm/last": {"data": None}})
    assert _fetch(c) == ({}, {}, {})
    assert asked == [f"{_OLD}?type=shortTerm", f"{_APP}/shortterm/last"]


def test_the_answer_is_asked_for_once_an_hour() -> None:
    c, asked = _client({f"{_APP}/shortterm/last": {"data": _TRIP}})
    _fetch(c)
    count = len(asked)
    _fetch(c)
    assert len(asked) == count


def test_the_reader_fills_the_last_trip_from_the_apps_answer() -> None:
    c, _ = _client({f"{_APP}/shortterm/last": {"data": _TRIP}})
    short, long_, _cyclic = _fetch(c)
    d = VehicleData(vin="V")
    c._parse_trip_statistics(d, short, long_)
    assert d.last_trip_distance_km == 12.5
    assert d.last_trip_duration_min == 20
    assert d.last_trip_avg_speed_kmh == 37.0
    assert d.last_trip_timestamp == "2026-01-02T10:00:00Z"


def test_the_apps_name_for_the_electric_average_is_read() -> None:
    # The app's trip carries ``averageElectricConsumption``; the reader knew
    # only ``averageElectricEngineConsumption``. On the app route the value is
    # already in final units (#2136), so it is not divided.
    c, _ = _client({})
    d = VehicleData(vin="V")
    app = {"tripData": [_TRIP], **_MARK}
    c._parse_trip_statistics(d, app, app)
    assert d.last_trip_avg_electric_consumption_kwh_100km == 18.5
    assert d.lifetime_avg_electric_consumption_kwh_100km == 18.5


def test_the_legacy_route_keeps_the_tenth_of_a_unit_scale() -> None:
    # Only an explicit legacy-route answer (no marker) is divided by ten.
    c, _ = _client({})
    d = VehicleData(vin="V")
    legacy = {"tripData": [{**_TRIP, "averageElectricConsumption": 185}]}
    c._parse_trip_statistics(d, legacy, legacy)
    assert d.last_trip_avg_electric_consumption_kwh_100km == 18.5
    assert d.lifetime_avg_electric_consumption_kwh_100km == 18.5


def test_the_older_name_still_wins_when_both_are_there() -> None:
    c, _ = _client({})
    d = VehicleData(vin="V")
    trip = {**_TRIP, "averageElectricEngineConsumption": 200}
    c._parse_trip_statistics(d, {"tripData": [trip]}, {})  # legacy answer: tenths
    assert d.last_trip_avg_electric_consumption_kwh_100km == 20.0
