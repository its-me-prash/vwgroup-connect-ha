# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2068 — the climate entity must not pass the OUTSIDE temperature off as the
cabin ``current_temperature``.

A Škoda Elroq owner saw ``current_temperature`` track the outside-temperature
sensor to the second, even while climate control was running. The old code
literally returned ``outside_temp``. The fix: ``current_temperature`` reads a
dedicated cabin field (``cabin_temp_c``), and when the feed carries no cabin
temperature the attribute is omitted (None) rather than showing the outside
value — an empty reading is honest, a wrong one implies the cabin is already as
cold as the street.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.climate import VagClimate

VIN = "WVWZZZTESTVIN2068"


def _coord(vehicle: dict) -> MagicMock:
    coord = MagicMock()
    coord.command_method_available = MagicMock(return_value=True)
    coord.data = {VIN: dict(vehicle)}
    return coord


def test_current_temperature_never_falls_back_to_outside_temp() -> None:
    e = VagClimate(_coord({"outside_temp": 7.0}), VIN)
    # The outside temperature must NOT leak into the cabin reading.
    assert e.current_temperature is None


def test_current_temperature_uses_the_cabin_field_when_present() -> None:
    e = VagClimate(_coord({"outside_temp": 7.0, "cabin_temp_c": 21.5}), VIN)
    assert e.current_temperature == 21.5


def test_cabin_temp_c_is_a_real_vehicle_data_field() -> None:
    # Forward-compatible: the interior-temperature scout mapping has a home to
    # populate, and VehicleData.as_dict() carries it through to the entity.
    from custom_components.vag_connect.cariad.models import VehicleData

    vd = VehicleData(vin=VIN)
    assert hasattr(vd, "cabin_temp_c")
    assert "cabin_temp_c" in vd.to_dict()
