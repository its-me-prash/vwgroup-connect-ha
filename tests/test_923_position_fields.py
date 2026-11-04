# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 — pins the vehicle-position field map and the V6.0 dictionary adoption.

The **dictionary** documents GPS coordinates only in the portal's Historical
export: its ``Vehicle Location (Historical Export)`` cluster holds exactly the
ten UUIDs this module maps, while the continuous side's ``Vehicle Location
Tracking`` cluster holds three members and no coordinate. These UUIDs were
verified against the official V6.0 PDFs; this test freezes them so a future
dictionary edit can't silently drift the position block, and guards that the
V6.0 merge preserved our curated V5.0 names.

What the dictionary documents is **not** what cars send. MEB portal cars ship
the position in the continuous feed under an undocumented ``persLocation`` leaf
(#1378), read by ``_parse_pers_location`` in ``_eu_data_act.py`` — this file
says nothing about that path, and the module docstring says so explicitly. The
earlier wording here ("coordinates live only in the Historical export, the
continuous feed has none") stated the dictionary's answer as if it were the
feed's, which is the confusion this test now pins apart.
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


def test_alert_positions_are_false_friends():
    """The largest coordinate family, and it IS the car — which is the trap.

    Counted 2026-11-03: 48 of the 110 coordinate-named dictionary entries are
    geofence / speed-alert / valet-alert ``occurrencePosition`` fields. They
    record where the car was when an alert fired, not where it is parked, so a
    name-matching reader would be most tempted by exactly the wrong family.
    """
    for name in (
        "GEOFEN.geofencingAlerts.[*].occurrencePosition.latitude",
        "SPEEDA.speedalertAlerts.[*].occurrencePosition.longitude",
        "VALETA.valetalertAlerts.[*].occurrencePosition.trueness",
    ):
        assert is_position_false_friend(name), name
    # positive control: the guard still lets the real historical paths through
    assert not is_position_false_friend("history.[*].lon")


def test_the_two_clusters_say_different_things():
    """Pins the split the module docstring now rests on.

    The continuous cluster documents no coordinate; the historical one documents
    exactly the ten UUIDs this module maps. Both are measured from the shipped
    dictionary, so a future merge that blurs them fails here.
    """
    d = _dict()
    entries = [v for k, v in d.items() if k != "_meta" and isinstance(v, dict)]

    continuous = {
        str(e.get("name")) for e in entries
        if "Vehicle Location Tracking" in str(e.get("cluster") or "")
    }
    assert continuous == {"mileage", "outside_temperature", "trueness"}, continuous

    historical = {
        k for k, v in d.items()
        if isinstance(v, dict)
        and "Vehicle Location (Historical" in str(v.get("cluster") or "")
    }
    assert historical == {
        **HISTORICAL_POSITION_FIELDS, **HISTORY_PATH_POSITION_FIELDS,
    }.keys() | set(), f"cluster drifted from the field map: {historical}"


def test_persLocation_is_undocumented_and_not_mapped_here():
    """The leaf cars actually use is absent from the dictionary on purpose.

    If a future dictionary release documents it, this test fails — which is the
    moment to revisit both docstrings rather than discover the change by a
    reporter's missing pin.
    """
    raw = _DICT.read_text(encoding="utf-8")
    assert "persLocation" not in raw
    roles = {**HISTORICAL_POSITION_FIELDS, **HISTORY_PATH_POSITION_FIELDS}.values()
    assert "persLocation" not in roles
    # positive control: the comparison does find a name that IS in the file
    assert "GPS Latitude" in raw


def test_manual_kickoff_is_not_justified_by_a_settled_question():
    """The opt-in must not rest on a question #923 already answered.

    Until 2026-11-03 the module docstring said the kickoff stays manual "until
    it's settled whether an in-flight historical request suspends the
    continuous feed". That was settled on #923 in August -- measured with a
    control night -- and the answer is no. Hanging the restriction on an
    answered question makes it look removable. The real reason is that a
    one-time request can vanish with no terminal state, so there is nothing to
    hang client state on.
    """
    import inspect

    from custom_components.vag_connect.cariad.auth import _position_fields

    doc = inspect.getdoc(_position_fields) or ""
    low = doc.lower()
    # the retracted justification must not be the stated condition
    assert "until it's settled whether an in-flight historical request" not in low
    # the real reason must be stated, and named as the reason
    assert "vanish" in low
    assert "no response" in low and "resubmit" in low
    # positive control: the conclusion itself is still there, so a docstring
    # that merely dropped the whole paragraph would fail this test too
    assert "never an automatic kickoff" in low


def test_v6_merge_preserved_v5_curation():
    d = _dict()
    assert d["_meta"]["version"] == "V6.0"
    # a curated V5.0 name must survive the merge (not be overwritten by the raw id)
    assert d["86df6747-e512-39b2-9de3-6b2458be62fb"]["name"] == "Charge Type"
    # the deliberately Scout-visible ownerless openings stay named as before
    assert d["c0bb1348-5d0d-3140-9a51-06881db06490"]["name"] == "open"
