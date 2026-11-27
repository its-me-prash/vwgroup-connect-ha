# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2204 — the Scout names a field's own content UUID, never a borrowed one.

Since #1100 a discovery row carries the content UUID of the point it came from.
Keys were recorded only for the generic names (``value``, ``state``, ``open`` …)
and every other name was looked up by its last segment. On a CUPRA Raval that
showed ``battery_level.value`` as ``80 (uuid 0ca40e18)``: 0ca40e18 is the range
point, the only point there named just ``value``, and the reporter read it as
the key of the battery field. ``battery_level.state`` got the keys of every
point named ``state`` the same way.

Keys are now recorded under the exact name a value is stored under, for every
named point, and looked up by that name only.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._reporter_pipeline import (
    _is_scout_repair_skipped,
)
from custom_components.vag_connect.cariad._unexpected_keys import (
    UnexpectedField,
    mask_value,
)
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# Real dictionary keys, as they appear in the CUPRA Born export on #2096.
_RANGE = "0ca40e18-0564-3eda-bcc0-7aee9ef44f04"  # "value", the primary range
_STATE_A = "0718582b-7259-3c9a-818a-ea848a7365a8"  # a point named "state"
_OPEN = "c0bb1348-5d0d-3140-9a51-06881db06490"  # ownerless "open"
# Made up: battery_level.value has no dictionary entry, so no real key is known.
_OWN = "deadbeef-0000-4000-8000-000000000000"
_OTHER = "feedface-0000-4000-8000-000000000000"


def _dataset(*points: dict) -> dict:
    return {"data": list(points)}


def _parse(payload: dict) -> tuple[VehicleData, dict[str, set[str]]]:
    field_ts: dict[str, float] = {}
    field_syn: dict[str, set[str]] = {}
    contested: dict[str, set[str]] = {}
    field_uuids: dict[str, set[str]] = {}
    fields = _walk_fields(payload, field_ts, field_syn, contested, field_uuids)
    d = map_dataset_to_vehicle_data(
        fields, VehicleData(vin="X"), field_ts, field_syn, contested, field_uuids
    )
    return d, field_uuids


def _raval(**battery_extra: str) -> dict:
    """The shape behind #2204: generic points next to dotted battery fields."""
    return _dataset(
        {"dataFieldName": "value", "value": "386", "key": _RANGE},
        {"dataFieldName": "state", "value": "VALID", "key": _STATE_A},
        {"dataFieldName": "open", "value": "true", "key": _OPEN},
        {"dataFieldName": "battery_level.value", "value": 80, **battery_extra},
        {"dataFieldName": "battery_level.state", "value": "VALID"},
    )


def _scout_finding(name: str, row: str) -> UnexpectedField:
    """What the coordinator files for a discovery row (coordinator.py)."""
    path = f"eu_data_act.{name}"
    return UnexpectedField(
        path=path,
        sample_masked=mask_value(row, path_hint=path),
        endpoint="eu_data_act",
        first_seen_at="2026-11-27T00:00:00Z",
    )


def test_dotted_name_does_not_borrow_the_key_of_a_value_point() -> None:
    d, _ = _parse(_raval())
    rows = d.raw_unmapped_fields or {}
    assert rows.get("battery_level.value") == "80"
    assert rows.get("battery_level.state") == "VALID"


def test_generic_leaf_still_names_its_key_next_to_them() -> None:
    d, _ = _parse(_raval())
    assert (d.raw_unmapped_fields or {}).get("open") == "true (uuid c0bb1348)"


def test_dotted_name_shows_its_own_key() -> None:
    d, field_uuids = _parse(_raval(key=_OWN))
    assert (d.raw_unmapped_fields or {}).get("battery_level.value") == (
        "80 (uuid deadbeef)"
    )
    assert field_uuids.get("battery_level.value") == {_OWN}


def test_range_is_still_read_from_its_key() -> None:
    d, _ = _parse(_raval(key=_OWN))
    assert d.range_km == 386


def test_borrowed_ownerless_key_no_longer_skips_the_repair() -> None:
    """The repair skip looks for c0bb1348 in the sample. A borrowed key would
    have silenced the repair for an unrelated field ending in ``.open``."""
    d, _ = _parse(_dataset(
        {"dataFieldName": "open", "value": "true", "key": _OPEN},
        {"dataFieldName": "some_new_opening.open", "value": "true"},
    ))
    rows = d.raw_unmapped_fields or {}
    assert rows.get("some_new_opening.open") == "true"
    assert not _is_scout_repair_skipped(
        _scout_finding("some_new_opening.open", rows["some_new_opening.open"])
    )
    assert _is_scout_repair_skipped(_scout_finding("open", rows["open"]))


def test_container_qualified_key_carries_the_same_uuid() -> None:
    field_uuids: dict[str, set[str]] = {}
    _walk_fields(
        {"slope": {"ascent": {
            "dataFieldName": "physical_value", "value": 5, "key": _OWN,
        }}},
        {}, {}, {}, field_uuids,
    )
    assert field_uuids.get("physical_value") == {_OWN}
    assert field_uuids.get("slope.ascent") == {_OWN}


def test_key_that_is_not_a_uuid_is_not_shown() -> None:
    d, field_uuids = _parse(_dataset(
        {"dataFieldName": "some_new_field", "value": "42", "key": "driver"},
    ))
    assert (d.raw_unmapped_fields or {}).get("some_new_field") == "42"
    assert field_uuids == {}


def test_point_without_a_usable_value_adds_no_key() -> None:
    field_uuids: dict[str, set[str]] = {}
    _walk_fields(
        _dataset(
            {"dataFieldName": "some_new_field.reading", "value": "1", "key": _OWN},
            {"dataFieldName": "some_new_field.reading", "value": None, "key": _OTHER},
            {"dataFieldName": "some_new_field.reading", "value": {"a": 1},
             "key": _RANGE},
        ),
        {}, {}, {}, field_uuids,
    )
    assert field_uuids == {"some_new_field.reading": {_OWN}}


def test_several_points_on_one_name_list_all_their_keys() -> None:
    """Same rule as for a generic name: the row came from one of these."""
    d, _ = _parse(_dataset(
        {"dataFieldName": "some_new_field.reading", "value": "1", "key": _OWN},
        {"dataFieldName": "some_new_field.reading", "value": "1", "key": _OTHER},
    ))
    assert (d.raw_unmapped_fields or {}).get("some_new_field.reading") == (
        "1 (uuid deadbeef, feedface)"
    )
