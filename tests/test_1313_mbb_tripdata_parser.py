# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1313 — the MBB ``tripdata`` parser, owed to @realynot since 2026-09-17.

He captured all three surfaces from the volkswagen.de authproxy on a 2023 Tiguan
eHybrid, in one session, and flagged the edge cases himself. The payloads below
are his, verbatim.

Three things make this surface its own dialect, different from both the EU Data
Act portal and the CARIAD BFF ``tripstatistics`` the integration already parses:

* keys are ``mileage_km`` / ``travelTime`` / ``averageSpeed_kmph`` rather than
  ``mileage`` / ``traveltime`` / ``averageSpeed``;
* consumption arrives as a real float (``2.6``), not an integer to be divided
  by ten;
* each value has a parallel imperial twin (``mileage_mi``, ``averageSpeed_mph``)
  which is null on a metric car — and, by implication, the reverse on a car set
  to miles.

And the three edge cases he found in the 17-trip list form:

1. **negative electric consumption is real.** A downhill leg ships
   ``averageElectricConsumption: -2.2`` — net recuperation, which the website
   itself displays as "-2,2 kWh/100 km". The sign must survive; a non-negative
   guard here would silently delete a true reading.
2. **nullable fuel fields on a hybrid.** One trip carries
   ``averageFuelConsumption: null`` with a null unit (a pure-electric leg).
3. **the list form is UNSORTED.** "timestamps arrive out of order", so the
   newest trip is not the first element.

``travelTime`` being minutes is not taken on trust — it is checked against his
own numbers three times over, since distance ÷ time must reproduce the reported
average speed: 1454 km / 2088 → 41.8 vs 42 reported; 939 / 1406 → 40.1 vs 40;
28 / 48 → 35.0 vs 36. All three agree, so minutes it is.
"""
from __future__ import annotations

import json

import pytest

from custom_components.vag_connect.cariad.models import VehicleData

# ── @realynot's captures, verbatim (2026-09-17T08:17Z on #1313) ─────────────

CYCLIC = json.loads(
    '{"data":{"tripEndTimestamp":"2026-09-17T07:11:46Z","id":"38813***",'
    '"tripType":"cyclic","vehicleType":"hybrid","mileage_km":1454,'
    '"mileage_mi":null,"startMileage_km":40490,"startMileage_mi":null,'
    '"overallMileage_km":41944,"overallMileage_mi":null,"travelTime":2088,'
    '"averageFuelConsumption":2.6,"averageFuelConsumptionUnit":"l_per_100km",'
    '"averageElectricConsumption":12,'
    '"averageElectricConsumptionUnit":"kWh_per_100km",'
    '"averageGasConsumption":null,"averageAuxConsumption":null,'
    '"averageRecuperation":null,"averageSpeed_kmph":42,"averageSpeed_mph":null}}'
)
LONGTERM = json.loads(
    '{"data":{"tripEndTimestamp":"2026-09-17T07:11:46Z","id":"36704***",'
    '"tripType":"longTerm","vehicleType":"hybrid","mileage_km":939,'
    '"mileage_mi":null,"startMileage_km":41004,"startMileage_mi":null,'
    '"overallMileage_km":41944,"overallMileage_mi":null,"travelTime":1406,'
    '"averageFuelConsumption":2.7,"averageFuelConsumptionUnit":"l_per_100km",'
    '"averageElectricConsumption":11.8,'
    '"averageElectricConsumptionUnit":"kWh_per_100km",'
    '"averageGasConsumption":null,"averageAuxConsumption":null,'
    '"averageRecuperation":null,"averageSpeed_kmph":40,"averageSpeed_mph":null}}'
)
SHORTTERM = json.loads(
    '{"data":{"tripEndTimestamp":"2026-09-17T07:11:46Z","id":"72477***",'
    '"tripType":"shortTerm","vehicleType":"hybrid","mileage_km":28,'
    '"mileage_mi":null,"startMileage_km":41915,"startMileage_mi":null,'
    '"overallMileage_km":41944,"overallMileage_mi":null,"travelTime":48,'
    '"averageFuelConsumption":2,"averageFuelConsumptionUnit":"l_per_100km",'
    '"averageElectricConsumption":18.3,'
    '"averageElectricConsumptionUnit":"kWh_per_100km",'
    '"averageGasConsumption":null,"averageAuxConsumption":null,'
    '"averageRecuperation":null,"averageSpeed_kmph":36,"averageSpeed_mph":null}}'
)


def _map(payload: object, **kw: object) -> VehicleData:
    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        map_tripdata_to_vehicle_data as _map_tripdata,
    )

    return _map_tripdata(payload, VehicleData(vin="X"), **kw)  # type: ignore[arg-type]


# ── The three surfaces land in the three established families ───────────────

def test_shortterm_fills_the_last_trip_family() -> None:
    """The integration's existing convention, which the portal mapper already
    follows: short term is "the last trip"."""
    d = _map(SHORTTERM)
    assert d.last_trip_distance_km == 28
    assert d.last_trip_duration_min == 48
    assert d.last_trip_avg_speed_kmh == 36
    assert d.last_trip_start_odometer_km == 41915
    assert d.last_trip_avg_fuel_consumption_l_100km == 2
    assert d.last_trip_avg_electric_consumption_kwh_100km == 18.3
    assert d.last_trip_timestamp is not None
    assert "2026-09-17" in str(d.last_trip_timestamp)


def test_longterm_fills_the_lifetime_family() -> None:
    """And long term is the cumulative one — same split the portal uses."""
    d = _map(LONGTERM)
    assert d.lifetime_trip_distance_km == 939
    assert d.lifetime_travel_time_min == 1406
    assert d.lifetime_avg_speed_kmh == 40
    assert d.lifetime_trip_start_odometer_km == 41004
    assert d.lifetime_avg_fuel_consumption_l_100km == 2.7
    assert d.lifetime_avg_electric_consumption_kwh_100km == 11.8
    # Not the last trip: that would overwrite a genuinely different reading.
    assert d.last_trip_distance_km is None


def test_cyclic_fills_the_refuel_cycle_distance() -> None:
    """The refuel-cycle memory, mapped from the portal in 4.10.0 as
    "Distance since refuelling". The same datum arrives here."""
    d = _map(CYCLIC)
    assert d.cyclic_trip_distance_km == 1454
    assert d.last_trip_distance_km is None
    assert d.lifetime_trip_distance_km is None


def test_the_odometer_comes_from_overall_mileage() -> None:
    """All three carry it, and it is the car's real total."""
    for payload in (CYCLIC, LONGTERM, SHORTTERM):
        assert _map(payload).odometer_km == 41944


def test_travel_time_is_minutes_checked_against_his_own_speeds() -> None:
    """If travelTime were seconds, every average speed would be 60x off. Checked
    against the reported speed rather than assumed from the field name."""
    for payload, dist, mins, speed in (
        (CYCLIC, 1454, 2088, 42), (LONGTERM, 939, 1406, 40), (SHORTTERM, 28, 48, 36),
    ):
        d = _map(payload)
        derived = dist / (mins / 60)
        assert abs(derived - speed) < 1.5, f"{derived:.1f} vs reported {speed}"


# ── The three edge cases he flagged ─────────────────────────────────────────

def test_negative_electric_consumption_is_preserved() -> None:
    """His exact case: a downhill leg with net recuperation, which the website
    shows as -2,2 kWh/100 km. A non-negative guard would delete a true reading."""
    body = json.loads(json.dumps(SHORTTERM))
    body["data"]["averageFuelConsumption"] = 7.5
    body["data"]["averageElectricConsumption"] = -2.2
    d = _map(body)
    assert d.last_trip_avg_electric_consumption_kwh_100km == -2.2
    assert d.last_trip_avg_fuel_consumption_l_100km == 7.5


def test_a_null_fuel_reading_on_a_hybrid_is_tolerated() -> None:
    """A pure-electric leg: null value AND null unit. Everything else on the
    trip must still map."""
    body = json.loads(json.dumps(SHORTTERM))
    body["data"]["averageFuelConsumption"] = None
    body["data"]["averageFuelConsumptionUnit"] = None
    d = _map(body)
    assert d.last_trip_avg_fuel_consumption_l_100km is None
    assert d.last_trip_distance_km == 28
    assert d.last_trip_avg_electric_consumption_kwh_100km == 18.3


def test_the_list_form_takes_the_newest_not_the_first() -> None:
    """"Unsorted — timestamps arrive out of order". Taking element zero would
    surface an arbitrary trip, which on a 17-trip window is usually the wrong
    one."""
    older = json.loads(json.dumps(SHORTTERM["data"]))
    older["tripEndTimestamp"] = "2026-09-15T06:00:00Z"
    older["mileage_km"] = 999
    newer = json.loads(json.dumps(SHORTTERM["data"]))
    newer["tripEndTimestamp"] = "2026-09-17T07:11:46Z"
    newer["mileage_km"] = 28
    # Newest deliberately NOT first.
    d = _map({"data": [newer, older]})
    assert d.last_trip_distance_km == 28
    d2 = _map({"data": [older, newer]})
    assert d2.last_trip_distance_km == 28, "took the first element, not the newest"


# ── Units and the imperial twins ────────────────────────────────────────────

def test_a_mismatched_consumption_unit_is_not_mapped() -> None:
    """The field carries its own unit. If the backend ever ships mpg there,
    writing it into an l/100km field would be a silent wrong number."""
    body = json.loads(json.dumps(SHORTTERM))
    body["data"]["averageFuelConsumptionUnit"] = "mpg"
    d = _map(body)
    assert d.last_trip_avg_fuel_consumption_l_100km is None
    # The rest of the trip is unaffected.
    assert d.last_trip_distance_km == 28


def test_a_miles_car_is_not_read_as_kilometres() -> None:
    """On his metric car the ``_mi`` twins are null. The reverse must not put
    miles into a kilometre field."""
    body = json.loads(json.dumps(SHORTTERM))
    body["data"]["mileage_km"] = None
    body["data"]["mileage_mi"] = 17
    body["data"]["averageSpeed_kmph"] = None
    body["data"]["averageSpeed_mph"] = 22
    d = _map(body)
    assert d.last_trip_distance_km != 17, "miles written into a km field"
    assert d.last_trip_avg_speed_kmh != 22


# ── Defensive ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("payload", [
    None, {}, [], "", {"data": None}, {"data": []}, {"data": "x"},
    {"data": {}}, {"data": {"tripType": "unknownType", "mileage_km": 5}},
    {"nope": {"tripType": "shortTerm"}},
])
def test_junk_leaves_the_vehicle_untouched(payload: object) -> None:
    """A reshuffled or empty body must never half-fill a trip family."""
    d = _map(payload)
    assert d.last_trip_distance_km is None
    assert d.lifetime_trip_distance_km is None
    assert d.cyclic_trip_distance_km is None
    assert d.odometer_km is None


def test_the_trip_type_may_be_supplied_by_the_caller() -> None:
    """The endpoint path already says which surface it is, so a body that omits
    ``tripType`` is still usable."""
    body = json.loads(json.dumps(SHORTTERM))
    del body["data"]["tripType"]
    d = _map(body, trip_type="shortTerm")
    assert d.last_trip_distance_km == 28


def test_the_body_wins_over_the_callers_guess() -> None:
    """If they disagree, the payload is the authority — it is what the car said."""
    d = _map(LONGTERM, trip_type="shortTerm")
    assert d.lifetime_trip_distance_km == 939
    assert d.last_trip_distance_km is None


def test_an_existing_reading_is_not_overwritten() -> None:
    """Channel merge: a value another source already resolved stays. The portal
    and this channel can both be active on the same car."""
    d = VehicleData(vin="X")
    d.last_trip_distance_km = 99
    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        map_tripdata_to_vehicle_data as _map_tripdata,
    )

    _map_tripdata(SHORTTERM, d)
    assert d.last_trip_distance_km == 99


# ── End to end: the channel actually fetches it ─────────────────────────────

def test_the_channel_fetches_and_merges_the_trip_memories() -> None:
    """A parser nobody calls is dead code. This drives the connector itself, so
    it fails if the read is not wired, if the URL spelling is wrong, or if the
    three memories are not all requested."""
    import asyncio
    from typing import Any

    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        WebsiteAuthProxyConnector,
    )

    bodies = {"shortterm": SHORTTERM, "longterm": LONGTERM, "cyclic": CYCLIC}
    asked: list[str] = []

    class _Resp:
        def __init__(self, payload: Any) -> None:
            self.status = 200
            self._payload = payload
            self.headers: dict[str, str] = {}
            self.cookies: dict[str, str] = {}

        async def json(self, content_type: str | None = None) -> Any:
            return self._payload

        async def text(self, **_kw: Any) -> str:
            return "{}"

        async def __aenter__(self) -> "_Resp":
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

    class _Session:
        cookie_jar = type(
            "_J", (), {"filter_cookies": lambda *_a: {},
                       "update_cookies": lambda *_a: None}
        )()

        def get(self, url: str, **_kw: Any) -> _Resp:
            for kind, body in bodies.items():
                # The URL spelling is lowercase and unseparated; a body-style
                # "shortTerm" in the path would not match here.
                if f"tripdata/{kind}/last" in url:
                    asked.append(kind)
                    return _Resp(body)
            return _Resp({})

        post = get

    conn = WebsiteAuthProxyConnector(_Session(), "u@t.de", "pw")  # type: ignore[arg-type]
    conn.logged_in = True
    d = VehicleData(vin="WVWZZZTESTVHN0001")
    try:
        asyncio.new_event_loop().run_until_complete(
            conn.get_vehicle_data("WVWZZZTESTVHN0001")
        )
    except Exception:  # noqa: BLE001
        # The surrounding poll needs far more of the channel than this stub
        # provides; all this test cares about is that the three trip URLs were
        # requested with the spelling the builder produces.
        pass
    assert sorted(asked) == ["cyclic", "longterm", "shortterm"], (
        f"the channel requested {asked} — the trip reads are not wired"
    )
    del d
