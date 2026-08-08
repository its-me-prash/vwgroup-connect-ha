# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda device model + year were blank because the reader looked top-level.

Škoda's ``GET /api/v1/vehicle-information/{vin}`` nests ``model`` and
``modelYear`` under a ``specification`` object; only ``devicePlatform`` sits at
the top level (grounded against the skodaconnect/myskoda ``Info`` model). The
coordinator read ``info.get("model")`` / ``info.get("modelYear")`` top-level, so
every Škoda's device card showed no model and no year. The reader now prefers a
top-level value and falls back to ``specification``.
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import _static_info_model_year


def test_skoda_real_shape_reads_from_specification() -> None:
    # The real MyŠkoda payload shape.
    info = {
        "name": "Enyaq",
        "devicePlatform": "WCAR",
        "specification": {
            "title": "Enyaq Coupé RS iV",
            "trimLevel": "RS",
            "model": "Enyaq",
            "modelYear": "2024",
        },
    }
    model, year = _static_info_model_year(info)
    assert model == "Enyaq"
    assert year == "2024"


def test_top_level_still_wins_when_present() -> None:
    # A forward-compat / other shape carrying it top-level must be honoured.
    info = {"model": "Octavia iV", "modelYear": "2023",
            "specification": {"model": "IGNORED", "modelYear": "1999"}}
    model, year = _static_info_model_year(info)
    assert model == "Octavia iV"
    assert year == "2023"


def test_missing_everywhere_is_none() -> None:
    model, year = _static_info_model_year({"devicePlatform": "MBB_ODP"})
    assert model is None
    assert year is None


def test_specification_not_a_dict_is_safe() -> None:
    model, year = _static_info_model_year({"specification": "oops"})
    assert model is None
    assert year is None


def test_empty_top_level_string_falls_through_to_specification() -> None:
    info = {"model": "", "specification": {"model": "Elroq", "modelYear": "2025"}}
    model, year = _static_info_model_year(info)
    assert model == "Elroq"
    assert year == "2025"
