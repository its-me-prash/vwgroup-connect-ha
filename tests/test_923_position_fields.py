# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 — pins the vehicle-position field map and the V6.0 dictionary adoption.

The GPS coordinates live only in the portal's Historical export (the Continuous
feed has none). These UUIDs were verified against the official V6.0 PDFs; this
test freezes them so a future dictionary edit can't silently drift the position
block, and guards that the V6.0 merge preserved our curated V5.0 names.
"""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.vag_connect.cariad.auth._position_fields import (
    HISTORICAL_POSITION_FIELDS,
    HISTORY_PATH_POSITION_FIELDS,
    is_position_false_friend,
)

_DICT = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "vag_connect" / "cariad" / "auth"
    / "eu_data_dictionary.json"
)


def _dict() -> dict:
    return json.loads(_DICT.read_text(encoding="utf-8"))


def test_gps_lat_lon_uuids_are_pinned():
    # The two that matter most, straight from the official V6.0 GPS block.
    assert HISTORICAL_POSITION_FIELDS["784c4692-9041-3cf7-9446-09efedd1d708"] == "latitude"
    assert HISTORICAL_POSITION_FIELDS["787807ad-3246-3f82-82d3-78baa334c574"] == "longitude"
    # Staleness/motion fields are present so a fix can be labelled honestly.
    roles = set(HISTORICAL_POSITION_FIELDS.values())
    assert {"latitude", "longitude", "moving", "outdated"} <= roles


def test_position_uuids_are_in_the_dictionary():
    d = _dict()
    for uuid in {**HISTORICAL_POSITION_FIELDS, **HISTORY_PATH_POSITION_FIELDS}:
        assert uuid in d, f"position UUID {uuid} missing from the data dictionary"
    # latitude entry carries the historical-export cluster marker
    lat = d["784c4692-9041-3cf7-9446-09efedd1d708"]
    assert "Historical" in (lat.get("cluster") or "")


def test_false_friends_are_rejected_but_real_position_is_not():
    # charging-record / navigation coordinates must not be read as the car's position
    assert is_position_false_friend("05_fleet.fleet_public_charging_record_details.location_coordinates_latitude")
    assert is_position_false_friend("destination-memory.entries.[*].data.destination.locationTokens.geoLocations.[*].location.latitude")
    assert is_position_false_friend("07_wallbox_elli.wallbox_elli_hss_charging_records.location_latitude")
    # the real vehicle-position paths are NOT false friends
    assert not is_position_false_friend("history.[*].lat")
    assert not is_position_false_friend("GPS Location Latitude value")


def test_v6_merge_preserved_v5_curation():
    d = _dict()
    assert d["_meta"]["version"] == "V6.0"
    # a curated V5.0 name must survive the merge (not be overwritten by the raw id)
    assert d["86df6747-e512-39b2-9de3-6b2458be62fb"]["name"] == "Charge Type"
    # the deliberately Scout-visible ownerless openings stay named as before
    assert d["c0bb1348-5d0d-3140-9a51-06881db06490"]["name"] == "open"
