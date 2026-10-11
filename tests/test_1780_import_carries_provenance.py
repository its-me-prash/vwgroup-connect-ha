# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1780 (@kmeinderink) — an imported value has to say when the car captured it.

He measured that the body sensors filled in by ``import_historical_export``
carried no ``data_captured_at`` and no ``freshness_source``, while feed-fed
sensors did, and then told us plainly which half of the problem actually matters
to him: his dashboard keeps the last known door, window, boot and bonnet state
itself and compares the capture time against the car's last report, so carrying
the values forward is optional, but a value with no capture time cannot be
judged at all.

The cause was the shape of the gap-fill. A sensor's freshness attributes are
built from two side maps (see ``_eu_da_freshness_attributes`` in sensor.py):
``field_sources`` must name ``eu_data_act`` before any attribute is added, and
then ``field_captured_ts`` supplies ``data_captured_at`` and turns
``freshness_source`` from "dataset" into "point". Those maps are themselves keys
in the snapshot, so a loop that copied key by key only where the destination was
empty skipped them whole on any car with a live feed: ``field_sources`` already
existed, so nothing merged into it and every imported value arrived anonymous.

Two properties are pinned as hard as the fix, because getting either wrong is
worse than the missing timestamp:

* a live value is never clobbered, which is the rule the whole import rests on;
* the maps are merged per filled key and never replaced, because for every other
  field they describe the LIVE feed, and replacing them would relabel live
  readings as imported.
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import (
    _PROVENANCE_MAPS,
    _gap_fill_from_export,
)

#: His car: a live feed supplying the odometer, no body state anywhere, and a
#: one-time export from 2026-10-09 02:15 UTC that has all four.
EXPORT: dict = {
    "doors_open": False,
    "windows_open": False,
    "trunk_open": False,
    "hood_open": False,
    "odometer_km": None,
    "field_sources": {
        "doors_open": "eu_data_act",
        "windows_open": "eu_data_act",
        "trunk_open": "eu_data_act",
        "hood_open": "eu_data_act",
    },
    # Only two of the four carry a genuine per-point stamp, which is the real
    # shape: the rest fall back to the dataset floor.
    "field_captured_ts": {
        "doors_open": "2026-10-09T02:15:00Z",
        "windows_open": "2026-10-09T02:15:00Z",
    },
}


def _live_car() -> dict:
    return {
        "odometer_km": 6775,
        "doors_open": None,
        "windows_open": None,
        "trunk_open": None,
        "hood_open": None,
        "field_sources": {"odometer_km": "eu_data_act"},
        "field_captured_ts": {"odometer_km": "2026-10-11T08:48:00Z"},
    }


def test_an_imported_value_can_be_dated() -> None:
    """FAILS BEFORE THE FIX: the maps were skipped, so this was empty."""
    car = _live_car()
    filled = _gap_fill_from_export(car, EXPORT)

    assert sorted(filled) == [
        "doors_open", "hood_open", "trunk_open", "windows_open",
    ]
    # The two conditions sensor.py needs, in the order it checks them.
    assert car["field_sources"]["doors_open"] == "eu_data_act"
    assert car["field_captured_ts"]["doors_open"] == "2026-10-09T02:15:00Z"


def test_a_field_without_a_point_stamp_is_honest_about_it() -> None:
    """``trunk_open`` has a source but no per-point time.

    That is not a gap to paper over: the attribute then reads
    ``freshness_source: dataset``, which says the age is the export's and not
    the boot's. Inventing a stamp for it would be the one thing worse than
    having none.
    """
    car = _live_car()
    _gap_fill_from_export(car, EXPORT)

    assert car["field_sources"]["trunk_open"] == "eu_data_act"
    assert "trunk_open" not in car["field_captured_ts"]


def test_a_live_value_is_never_clobbered() -> None:
    """The rule the whole import rests on."""
    car = _live_car()
    _gap_fill_from_export(car, {**EXPORT, "odometer_km": 1})

    assert car["odometer_km"] == 6775


def test_the_live_feeds_own_provenance_survives() -> None:
    """The maps are merged per key, not replaced.

    Replacing them would relabel the odometer as imported and overwrite its
    capture time with the export's, which would make a live reading look days
    old.
    """
    car = _live_car()
    _gap_fill_from_export(car, EXPORT)

    assert car["field_sources"]["odometer_km"] == "eu_data_act"
    assert car["field_captured_ts"]["odometer_km"] == "2026-10-11T08:48:00Z"


def test_an_existing_entry_is_left_alone() -> None:
    """A stamp already in the destination wins over the export's."""
    car = _live_car()
    car["doors_open"] = None
    car["field_captured_ts"]["doors_open"] = "2026-10-11T08:00:00Z"
    _gap_fill_from_export(car, EXPORT)

    assert car["field_captured_ts"]["doors_open"] == "2026-10-11T08:00:00Z"


def test_a_car_with_no_snapshot_maps_at_all_gets_them() -> None:
    """A portal-only car may have no side maps yet."""
    car: dict = {"doors_open": None}
    _gap_fill_from_export(car, EXPORT)

    assert car["field_sources"]["doors_open"] == "eu_data_act"
    assert car["field_captured_ts"]["doors_open"] == "2026-10-09T02:15:00Z"


def test_the_maps_are_not_imported_as_values() -> None:
    """The side maps must not be gap-filled as if they were readings.

    Returning them among the filled keys would also make the service report that
    it had imported something when it had only copied bookkeeping.
    """
    car: dict = {"doors_open": None}
    filled = _gap_fill_from_export(car, EXPORT)

    for name in _PROVENANCE_MAPS:
        assert name not in filled


def test_nothing_to_fill_reports_nothing() -> None:
    """An export whose every field already has a live value gains nothing, and
    the caller uses this to tell the user so."""
    car = {
        "doors_open": False, "windows_open": False,
        "trunk_open": False, "hood_open": False, "odometer_km": 6775,
    }
    assert _gap_fill_from_export(car, EXPORT) == []
