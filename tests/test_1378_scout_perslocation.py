# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1378 / #923 — MEB portal cars (Škoda Elroq …) ship the vehicle position in
the CONTINUOUS EU Data Act feed under ``persLocation`` = "[lat, lon]" (the sample
#923 was waiting for), plus a ``heading``. The parser now reads them defensively
into latitude/longitude/heading — validated, in-range, not the 0/0 sentinel, so a
charging/destination coordinate or a placeholder can never be mistaken for the
car's own position.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _parse_pers_location,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(points: list[dict]) -> VehicleData:
    fields = _walk_fields({"data": points})
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


# ── the parser helper ───────────────────────────────────────────────────────
def test_parse_pers_location_accepts_a_valid_pair() -> None:
    assert _parse_pers_location("[50.799918, 4.408567]") == (50.799918, 4.408567)
    assert _parse_pers_location("50.8,4.4") == (50.8, 4.4)
    assert _parse_pers_location([50.8, 4.4]) == (50.8, 4.4)


def test_parse_pers_location_rejects_junk_and_sentinels() -> None:
    for bad in ("", "garbage", "[0, 0]", "[999, 4]", "[50]", "[50,4,9]", None,
                "[abc, def]", "0,0"):
        assert _parse_pers_location(bad) == (None, None)


# ── end to end ──────────────────────────────────────────────────────────────
def test_persLocation_populates_latitude_longitude() -> None:
    d = _map([
        {"dataFieldName": "persLocation", "value": "[50.799918, 4.408567]",
         "key": "k1"},
        {"dataFieldName": "heading", "value": "326", "key": "k2"},
    ])
    assert d.latitude == 50.799918
    assert d.longitude == 4.408567
    assert d.heading == 326


def test_heading_wraps_360_to_0() -> None:
    d = _map([{"dataFieldName": "heading", "value": "360", "key": "k"}])
    assert d.heading == 0


def test_bad_persLocation_leaves_position_unset() -> None:
    d = _map([{"dataFieldName": "persLocation", "value": "[0, 0]", "key": "k"}])
    assert d.latitude is None
    assert d.longitude is None


def test_no_position_leaves_are_inert() -> None:
    d = _map([{"dataFieldName": "battery_state_report.soc", "value": "50",
               "key": "k"}])
    assert d.latitude is None
    assert d.heading is None
