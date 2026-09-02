# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""``_build_state`` must emit ``{country}__{language}__{brand}``.

The EU Data Act portal decodes the COUNTRY first, then the language — confirmed
against a live portal authorize (2026-09-02): with ``datahubConfig`` country=de /
language=en the portal produced ``state=de__en__…``, and the portal's
``validLocales`` are all ``{country}/{language}``. The active reader
``EUDataActConnector`` already builds this order (its ``se__sv`` / ``ch__de`` tests
pin it); a v2.10.2 change had left the secondary ``DataActPortalAuth._build_state``
helper on the inverted ``{language}__{country}`` order, invisible because it is only
ever constructed with the symmetric DE/de defaults. This guards the corrected order
so the two implementations can't drift again.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._data_act_portal import _build_state


def test_symmetric_locale_country_then_language():
    assert _build_state("volkswagen", "de", "de") == "de__de__VOLKSWAGEN_PASSENGER_CARS"


def test_asymmetric_locale_puts_country_first():
    # the exact regression this guards: {language}__{country} would give "en__de"
    assert _build_state("volkswagen", "de", "en") == "de__en__VOLKSWAGEN_PASSENGER_CARS"
    assert _build_state("volkswagen", "ch", "de") == "ch__de__VOLKSWAGEN_PASSENGER_CARS"
    assert _build_state("volkswagen", "at", "de") == "at__de__VOLKSWAGEN_PASSENGER_CARS"


def test_brand_suffix_and_case_folding():
    assert _build_state("AUDI", "DE", "DE") == "de__de__AUDI"
    assert _build_state("skoda", "de", "de") == "de__de__SKODA"


def test_unknown_brand_falls_back_to_passenger_cars():
    assert _build_state("nope", "de", "de") == "de__de__VOLKSWAGEN_PASSENGER_CARS"
