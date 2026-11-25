# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2199 (@bzykcar) — a car parked in Poland showed no town.

#1219 made the parking locality prefer the suburb, which matches the Audi app in
Australia. In Poland Nominatim often returns a housing estate or a residential
area as the suburb or neighbourhood, so Parking City showed that name instead of
the town, Parking Address carried no town at all, and the house number came
before the street. For Poland the locality is now the town and the address is
``<postcode> <town>, <street> <house>``; every other country is unchanged.
All address values below are made up.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect import coordinator as coord_mod
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_compose = VagConnectCoordinator._compose_parking_location


def _pl(**extra: str) -> dict[str, str]:
    addr = {
        "house_number": "12",
        "road": "Przykładowa",
        "neighbourhood": "Osiedle Testowe",
        "city": "Warszawa",
        "state": "województwo mazowieckie",
        "postcode": "00-001",
        "country_code": "pl",
    }
    addr.update(extra)
    return addr


def test_poland_city_is_the_town_not_the_neighbourhood() -> None:
    out = _compose(_pl(), "")
    assert out["city"] == "Warszawa"
    assert out["address"] == "00-001 Warszawa, Przykładowa 12"
    # The neighbourhood and the voivodeship are not part of it.
    assert "Osiedle Testowe" not in out["address"]
    assert "mazowieckie" not in out["address"]


def test_poland_town_and_village_keys_count_as_the_town() -> None:
    addr = _pl(suburb="Os. Przykład")
    del addr["city"]
    addr["town"] = "Miasteczko"
    assert _compose(addr, "")["city"] == "Miasteczko"
    addr = _pl()
    del addr["city"]
    addr["village"] = "Wieś Testowa"
    out = _compose(addr, "")
    assert out["city"] == "Wieś Testowa"
    assert out["address"] == "00-001 Wieś Testowa, Przykładowa 12"


def test_poland_without_house_number_keeps_the_street() -> None:
    addr = _pl()
    del addr["house_number"]
    assert _compose(addr, "")["address"] == "00-001 Warszawa, Przykładowa"


def test_poland_without_street_is_postcode_and_town() -> None:
    addr = _pl()
    del addr["house_number"]
    del addr["road"]
    assert _compose(addr, "")["address"] == "00-001 Warszawa"


def test_poland_without_town_falls_back_to_the_suburb() -> None:
    addr = _pl()
    del addr["city"]
    out = _compose(addr, "")
    assert out["city"] == "Osiedle Testowe"
    assert out["address"] == "00-001 Osiedle Testowe, Przykładowa 12"


def test_poland_without_postcode() -> None:
    addr = _pl()
    del addr["postcode"]
    assert _compose(addr, "")["address"] == "Warszawa, Przykładowa 12"


def test_country_code_case_does_not_matter() -> None:
    assert _compose(_pl(country_code="PL"), "")["city"] == "Warszawa"


@pytest.mark.parametrize("cc", ["cz", "fr", "gb", "au", "de"])
def test_other_countries_keep_the_1219_composition(cc: str) -> None:
    # Same address block, another country: the suburb still wins and the
    # address keeps street, suburb, state and postcode, as before #2199.
    out = _compose(_pl(country_code=cc), "")
    assert out["city"] == "Osiedle Testowe"
    assert "Osiedle Testowe" in out["address"]
    assert out["address"].endswith("województwo mazowieckie 00-001")


def test_country_sets() -> None:
    assert "pl" in coord_mod._ROAD_HOUSE_COUNTRIES
    assert {"de", "at", "ch", "li"} <= coord_mod._ROAD_HOUSE_COUNTRIES
    assert coord_mod._TOWN_FIRST_COUNTRIES == frozenset({"pl"})
