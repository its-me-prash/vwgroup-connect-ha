# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""B1 — every entity can name the read channel its own value came from.

A car can be read over up to three channels at once and none of them is
complete: on a Golf GTE the fuel level comes from MBB while the SoC comes from
the EU Data Act portal. sensor.data_source_channel can only say "these channels
fed this car" — it cannot tell you where the number in front of you came from.

The merge records {field_name: channel}; the base entity turns that into a
``source`` attribute, so it works for every platform at once and is readable
from templates and automations.
"""
from __future__ import annotations

from unittest.mock import MagicMock

VIN = "WVGZZZ1KZAW123456"


def _coord(field_sources=None, **extra):
    coord = MagicMock()
    coord.is_read_only = MagicMock(return_value=False)
    vehicle = {
        "vin": VIN,
        "battery_soc": 55,
        "fuel_level": 80,
        **extra,
    }
    if field_sources is not None:
        vehicle["field_sources"] = field_sources
    coord.data = {VIN: vehicle}
    return coord


def _entity(coord, data_key):
    from custom_components.vag_connect.entity_base import VagConnectEntity

    e = VagConnectEntity(coord, VIN, "k")
    e.entity_description = MagicMock()
    e.entity_description.data_key = data_key
    return e


def test_entity_reports_its_own_source() -> None:
    coord = _coord({"battery_soc": "eu_data_act", "fuel_level": "mbb"})
    assert _entity(coord, "battery_soc")._field_source == "eu_data_act"


def test_two_entities_on_one_car_can_differ() -> None:
    # The whole point — one car, two channels, two answers.
    coord = _coord({"battery_soc": "eu_data_act", "fuel_level": "mbb"})
    assert _entity(coord, "battery_soc")._field_source == "eu_data_act"
    assert _entity(coord, "fuel_level")._field_source == "mbb"


def test_source_lands_in_extra_state_attributes() -> None:
    coord = _coord({"battery_soc": "eu_data_act"})
    attrs = _entity(coord, "battery_soc").extra_state_attributes
    assert attrs is not None
    assert attrs["source"] == "EU Data Act portal"  # friendly (raw token via _field_source)


def test_unknown_field_has_no_source() -> None:
    coord = _coord({"battery_soc": "eu_data_act"})
    assert _entity(coord, "odometer_km")._field_source is None


def test_missing_map_is_not_an_error() -> None:
    # Pre-merge snapshots / restored cache carry no map at all.
    coord = _coord(None)
    e = _entity(coord, "battery_soc")
    assert e._field_source is None
    assert (e.extra_state_attributes or {}).get("source") is None


def test_entity_without_data_key_has_no_source() -> None:
    coord = _coord({"battery_soc": "eu_data_act"})
    assert _entity(coord, "")._field_source is None


def test_image_url_attribute_still_works() -> None:
    # No regression on the Lovelace-card attribute that already lived here.
    coord = _coord(
        {"battery_soc": "eu_data_act"},
        image_urls={"front": "https://example.invalid/car.png"},
    )
    attrs = _entity(coord, "battery_soc").extra_state_attributes or {}
    assert "image_url" in attrs
    assert attrs["source"] == "EU Data Act portal"  # friendly (raw token via _field_source)
