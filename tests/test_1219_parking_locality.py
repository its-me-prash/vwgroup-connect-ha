# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1219 (@mhanline) — parking address must carry suburb/state, not just city.

The reverse geocoder only surfaced the city, so an Audi Q6 parked in Summer Hill
showed ``parking_city = "Sydney"`` and dropped the suburb the brand app shows.
``_compose_parking_location`` now prefers the suburb for the locality and builds
``<house> <road>, <suburb>, <state> <postcode>`` — with house-before-road only
outside the German-order countries, so existing DE/AT/CH users are unchanged.
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import VagConnectCoordinator

_compose = VagConnectCoordinator._compose_parking_location


def test_australia_uses_suburb_state_and_house_first() -> None:
    addr = {
        "house_number": "12",
        "road": "Sloane Street",
        "suburb": "Summer Hill",
        "city": "Sydney",
        "state": "New South Wales",
        "postcode": "2130",
        "country_code": "au",
    }
    out = _compose(addr, "12, Sloane Street, Summer Hill, Sydney, ...")
    assert out["address"] == "12 Sloane Street, Summer Hill, New South Wales 2130"
    # locality is the suburb the brand app shows, NOT the metro "Sydney".
    assert out["city"] == "Summer Hill"


def test_dach_keeps_road_then_house_and_city() -> None:
    addr = {
        "house_number": "1",
        "road": "Marienplatz",
        "city": "München",
        "state": "Bayern",
        "postcode": "80331",
        "country_code": "de",
    }
    out = _compose(addr, "")
    # German order preserved: road then house number, no regression for DACH.
    assert out["address"] == "Marienplatz 1, Bayern 80331"
    assert out["city"] == "München"


def test_no_suburb_falls_back_to_city() -> None:
    # Large US metros often have no suburb — must not regress to blank.
    addr = {
        "house_number": "350",
        "road": "5th Avenue",
        "city": "New York",
        "state": "New York",
        "postcode": "10118",
        "country_code": "us",
    }
    out = _compose(addr, "")
    assert out["address"] == "350 5th Avenue, New York 10118"
    assert out["city"] == "New York"


def test_neighbourhood_is_a_suburb_fallback() -> None:
    addr = {
        "road": "Rue de Rivoli",
        "neighbourhood": "Quartier Saint-Merri",
        "city": "Paris",
        "country_code": "fr",
    }
    out = _compose(addr, "")
    assert out["city"] == "Quartier Saint-Merri"
    assert "Quartier Saint-Merri" in out["address"]


def test_empty_address_falls_back_to_display_name() -> None:
    out = _compose({}, "Somewhere remote, Country")
    assert out["address"] == "Somewhere remote, Country"
    assert out["city"] is None
