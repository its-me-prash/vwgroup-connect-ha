# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1917 (with #923, #1971) — a carried reading says that it is carried.

``CARRY_FORWARD_FIELDS`` keep the last recorded value when a poll omits it
("old but visible"). Until now such a value looked exactly like a fresh one:
it has no ``field_sources`` entry, so the freshness attributes gave it
nothing, and the only trace of its age was the *absence* of a source.

This change adds a per-field map ``field_carried_since`` (ISO time of the poll
in which the value started being carried) and shows it on the entity as
``freshness_source: "carried"`` plus ``carried_since``. It is a marker only:
no value changes, nothing is dropped, no age limit is applied.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.vehicle_cache import (
    CARRY_FORWARD_FIELDS,
    reconcile,
    strip_runtime,
)
from custom_components.vag_connect.entity_base import VagConnectEntity
from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS, VagConnectSensor

_ENTITY_ATTRS = VagConnectEntity.extra_state_attributes


def _desc(key: str) -> Any:
    for d in SENSOR_DESCRIPTIONS:
        if d.key == key:
            return d
    raise AssertionError(f"no shipped sensor description for {key!r}")


def _entity(key: str, vehicle: dict[str, Any]) -> Any:
    ent = VagConnectSensor.__new__(VagConnectSensor)
    ent.coordinator = MagicMock()
    ent.coordinator.data = {"V": vehicle}
    ent._vin = "V"
    ent._key = key
    ent.entity_description = _desc(key)
    return ent


def _attrs(ent: Any) -> dict[str, Any]:
    # the shared base property, without any per-platform override
    return _ENTITY_ATTRS.fget(ent) or {}


def test_a_carried_value_is_marked_with_the_time_it_started_being_carried() -> None:
    merged, _ = reconcile(
        {"odometer_km": 100, "fuel_level": 40},
        {"vin": "X", "odometer_km": None, "fuel_level": 39},
    )
    assert merged["odometer_km"] == 100
    since = merged["field_carried_since"]
    assert set(since) == {"odometer_km"}
    # a real ISO time with a zone
    assert datetime.fromisoformat(since["odometer_km"]).tzinfo is not None


def test_the_marker_is_stable_while_the_value_stays_carried() -> None:
    first, _ = reconcile({"odometer_km": 100}, {"vin": "X", "odometer_km": None})
    stamp = first["field_carried_since"]["odometer_km"]
    second, _ = reconcile(first, {"vin": "X", "odometer_km": None})
    third, _ = reconcile(second, {"vin": "X", "odometer_km": None})
    assert second["field_carried_since"]["odometer_km"] == stamp
    assert third["field_carried_since"]["odometer_km"] == stamp


def test_a_fresh_value_clears_the_marker() -> None:
    first, _ = reconcile({"odometer_km": 100}, {"vin": "X", "odometer_km": None})
    assert "odometer_km" in first["field_carried_since"]
    again, _ = reconcile(first, {"vin": "X", "odometer_km": 105})
    assert again["odometer_km"] == 105
    assert "odometer_km" not in (again.get("field_carried_since") or {})


def test_fields_that_are_not_carried_get_no_marker() -> None:
    merged, _ = reconcile(
        {"odometer_km": 100, "doors_open": False, "fuel_level": 40},
        {"vin": "X", "odometer_km": 101, "doors_open": None, "fuel_level": 39},
    )
    # nothing was carried: no map at all (and the volatile field stays unknown)
    assert not merged.get("field_carried_since")
    assert merged.get("doors_open") is None


def test_only_the_carried_field_is_marked_among_several() -> None:
    merged, _ = reconcile(
        {"odometer_km": 100, "fuel_level": 40, "range_km": 500},
        {"vin": "X", "odometer_km": 101, "fuel_level": None, "range_km": 480},
    )
    assert set(merged["field_carried_since"]) == {"fuel_level"}


def test_the_marker_survives_a_restart() -> None:
    """The snapshot written to .storage is ``strip_runtime`` of the vehicle
    dict, round-tripped through JSON; the next poll reconciles against it."""
    first, _ = reconcile({"odometer_km": 100}, {"vin": "X", "odometer_km": None})
    stamp = first["field_carried_since"]["odometer_km"]
    on_disk = json.loads(json.dumps(strip_runtime({**first, "_restored": False})))
    assert on_disk["field_carried_since"] == {"odometer_km": stamp}
    # restored entity shows it before any poll
    ent = _entity("odometer_km", on_disk)
    got = _attrs(ent)
    assert got["freshness_source"] == "carried"
    assert got["carried_since"] == stamp
    # and the next poll that still omits the value keeps the ORIGINAL time
    after, _ = reconcile(on_disk, {"vin": "X", "odometer_km": None})
    assert after["field_carried_since"]["odometer_km"] == stamp
    # while a fresh value after the restart clears it
    fresh, _ = reconcile(on_disk, {"vin": "X", "odometer_km": 110})
    assert "odometer_km" not in (fresh.get("field_carried_since") or {})


def test_the_entity_of_a_carried_value_shows_the_marker() -> None:
    stamp = "2026-11-24T10:00:00+00:00"
    ent = _entity(
        "odometer_km",
        {"odometer_km": 100, "field_carried_since": {"odometer_km": stamp}},
    )
    got = _attrs(ent)
    assert got["freshness_source"] == "carried"
    assert got["carried_since"] == stamp


def test_the_entity_of_a_fresh_value_shows_no_marker() -> None:
    ent = _entity("odometer_km", {"odometer_km": 100, "field_carried_since": {}})
    got = _attrs(ent)
    assert "carried_since" not in got
    assert "freshness_source" not in got
    ent2 = _entity("odometer_km", {"odometer_km": 100})
    assert "carried_since" not in _attrs(ent2)


def test_another_entitys_marker_does_not_leak_onto_this_one() -> None:
    stamp = "2026-11-24T10:00:00+00:00"
    ent = _entity(
        "fuel_level",
        {"fuel_level": 40, "odometer_km": 100,
         "field_carried_since": {"odometer_km": stamp}},
    )
    assert "carried_since" not in _attrs(ent)


def test_a_malformed_marker_map_is_ignored() -> None:
    for bad in ("x", ["odometer_km"], {"odometer_km": 5}, {"odometer_km": ""}):
        ent = _entity("odometer_km", {"odometer_km": 100, "field_carried_since": bad})
        assert "carried_since" not in _attrs(ent)


def test_values_are_identical_with_and_without_the_marker() -> None:
    """Counter-test: the marker adds a key and changes no reading."""
    previous = {f: i + 1 for i, f in enumerate(sorted(CARRY_FORWARD_FIELDS))}
    previous["doors_open"] = False
    fresh = {"vin": "X", "doors_open": None}
    merged, _ = reconcile(previous, fresh)
    expected = {f: previous[f] for f in CARRY_FORWARD_FIELDS}
    for field, value in expected.items():
        assert merged[field] == value, field
    assert merged.get("doors_open") is None
    without_marker = {k: v for k, v in merged.items() if k != "field_carried_since"}
    # every carried field is marked, and nothing else in the snapshot moved
    assert set(merged["field_carried_since"]) == set(CARRY_FORWARD_FIELDS)
    assert {k: v for k, v in without_marker.items() if k in expected} == expected


def test_a_poll_with_no_previous_snapshot_is_returned_untouched() -> None:
    fresh = {"vin": "X", "odometer_km": 5}
    merged, _ = reconcile(None, fresh)
    assert merged is fresh
    assert "field_carried_since" not in merged
