# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.19.0 — rich device model from the vgql image fetch.

The userVehicles GraphQL (already used for render images) returns the rich
``media.longName`` and now also ``core.modelYear`` — routed into the device
model so the HA device page shows "S6 Avant TDI quattro tiptronic (2021)"
instead of a bare "VAG Vehicle".
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher


def _one(vehicle: dict) -> object:
    data = {"data": {"userVehicles": [{"vin": "V1", "vehicle": vehicle}]}}
    return VehicleImageFetcher._parse_response(data)["V1"]


def test_vgql_parses_long_name_and_model_year_int() -> None:
    v = _one({
        "brand": {"name": "Audi"},
        "core": {"modelYear": 2021},
        "media": {"shortName": "S6 Avant", "longName": "Audi S6 Avant TDI quattro tiptronic"},
        "renderPictures": [],
    })
    assert v.long_name == "Audi S6 Avant TDI quattro tiptronic"
    assert v.model_year == 2021


def test_vgql_model_year_string_is_coerced() -> None:
    v = _one({"core": {"modelYear": "2024"}, "media": {"longName": "VW ID.4"}, "renderPictures": []})
    assert v.model_year == 2024


def test_vgql_missing_year_stays_none_longname_kept() -> None:
    v = _one({"media": {"longName": "Volkswagen Golf GTE"}, "renderPictures": []})
    assert v.model_year is None
    assert v.long_name == "Volkswagen Golf GTE"


def test_vgql_garbage_year_ignored() -> None:
    v = _one({"core": {"modelYear": "n/a"}, "media": {"longName": "Škoda Enyaq"}, "renderPictures": []})
    assert v.model_year is None
