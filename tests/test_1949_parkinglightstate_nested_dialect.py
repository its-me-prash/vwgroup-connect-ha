# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1949 / #2064 / #2066 — the per-side parking lights, nested under a
``parkinglightstate`` container.

The parser already read the bare ``parking_light_left`` / ``_right`` leaves and
the one-time-export ``parking_lights_info.*`` spelling, but VW / CUPRA /
VW-commercial ship the pair nested as ``parkinglightstate.parking_light_left``,
which no key covered — so it reached the per-side binary sensors as nothing and
the Scout re-filed it on every car. The nested spelling now maps onto the same
existing sensors.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


def test_nested_parkinglightstate_maps_to_the_per_side_fields() -> None:
    d = _map({
        "parkinglightstate.parking_light_left": "true",
        "parkinglightstate.parking_light_right": "false",
    })
    assert d.parking_light_left is True
    assert d.parking_light_right is False
    # aggregate derived from the per-side values
    assert d.parking_light is True


def test_the_bare_spelling_still_works() -> None:
    d = _map({"parking_light_left": "true", "parking_light_right": "true"})
    assert d.parking_light_left is True
    assert d.parking_light_right is True
