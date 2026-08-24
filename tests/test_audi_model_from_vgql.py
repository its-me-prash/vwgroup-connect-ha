# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audi/VW-EU model name falls back to the vgql media designation.

The REST vehicles-list often carries no ``model`` (an Audi S6 returns an empty
one), so the device fell back to "Audi (2021)". The vgql GraphQL block we
already fetch for render images also carries ``media.longName`` ("S6 Avant TDI")
and the exterior colour — surface them, and use the media name as the model
fallback when the REST list gave nothing (parity with what the SEAT/CUPRA path
and a competing Audi integration already do).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.graphql import VehicleImageData
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient


def _client(meta: dict, image_data: dict) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._vehicle_metadata = meta
    c._image_data = image_data
    return c


def test_model_falls_back_to_vgql_long_name():
    c = _client(
        {"VINX": {"model": None, "model_year": 2021}},  # REST list has no model
        {"VINX": VehicleImageData(
            vin="VINX", image_urls={}, long_name="S6 Avant TDI",
            short_name="S6", exterior_color="Daytona Grey")},
    )
    d = c._parse_status("VINX", {}, parking={})
    assert d.model == "S6 Avant TDI"
    assert d.media_long_name == "S6 Avant TDI"
    assert d.media_short_name == "S6"
    assert d.exterior_color == "Daytona Grey"


def test_rest_model_still_wins_when_present():
    c = _client(
        {"VINX": {"model": "Golf GTE"}},   # user nickname / REST model present
        {"VINX": VehicleImageData(vin="VINX", image_urls={}, long_name="VW Golf")},
    )
    d = c._parse_status("VINX", {}, parking={})
    assert d.model == "Golf GTE"           # REST wins, media only fills gaps
    assert d.media_long_name == "VW Golf"  # media still surfaced as its own field


def test_no_image_data_is_graceful():
    c = _client({"VINX": {"model": None}}, {})
    d = c._parse_status("VINX", {}, parking={})
    assert d.model is None                 # nothing to fall back to → device uses brand+year
