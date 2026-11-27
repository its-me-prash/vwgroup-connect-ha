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
named point, and looked up by that name only. A row names only the keys of the
points that sent the value it shows: a point whose value lost, by time or by the
#1088 majority, and a sibling attribute of the same name lend it nothing.
"""
from __future__ import annotations

import pytest

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
_OPEN_B = "d5dc7c87-5051-34db-ae99-0bd2cf987c45"  # the other ownerless "open"
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


@pytest.mark.parametrize("ownerless", [_OPEN, _OPEN_B])
def test_borrowed_ownerless_key_no_longer_skips_the_repair(ownerless: str) -> None:
    """The repair skip looks for c0bb1348 or d5dc7c87 in the sample. A borrowed
    key would have silenced the repair for an unrelated field ending in
    ``.open``."""
    d, _ = _parse(_dataset(
        {"dataFieldName": "open", "value": "true", "key": ownerless},
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


@pytest.mark.parametrize("key", [
    "driver",
    "deadbeef",  # hex, but only the short form
    "deadbeef000040008000000000000000",  # 32 hex digits without dashes
    "deadbeef0-000-4000-8000-000000000000",  # 36 characters, wrong groups
    "deadbeef-0000-4000-8000-00000000000g",  # UUID groups, one non-hex digit
])
def test_key_that_is_not_a_uuid_is_not_shown(key: str) -> None:
    d, field_uuids = _parse(_dataset(
        {"dataFieldName": "some_new_field", "value": "42", "key": key},
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


def test_rejected_point_never_counts_even_when_its_text_matches() -> None:
    """A point with no value is dropped before its key is recorded. Recorded
    first, it would land under the text "None" and be named next to a point
    that really sent the string "None"."""
    field_uuids: dict[str, set[str]] = {}
    fields = _walk_fields(
        _dataset(
            {"dataFieldName": "some_new_field.reading", "value": "None", "key": _OWN},
            {"dataFieldName": "some_new_field.reading", "value": None, "key": _OTHER},
        ),
        {}, {}, {}, field_uuids,
    )
    assert fields["some_new_field.reading"] == "None"
    assert field_uuids == {"some_new_field.reading": {_OWN}}


def test_points_that_sent_the_same_value_are_all_named() -> None:
    """Both points sent the shown value, so the row came from one of these."""
    d, _ = _parse(_dataset(
        {"dataFieldName": "some_new_field.reading", "value": "1", "key": _OWN},
        {"dataFieldName": "some_new_field.reading", "value": "1", "key": _OTHER},
    ))
    assert (d.raw_unmapped_fields or {}).get("some_new_field.reading") == (
        "1 (uuid deadbeef, feedface)"
    )


def test_newer_point_without_a_key_does_not_borrow_the_older_points_key() -> None:
    """The #2204 kind of failure (a value shown next to another point's key),
    reached through a shared name instead of a suffix. It also passes on the
    code before #2204, which recorded no key for such a name; it guards against
    a fix that records keys without asking whose value is shown."""
    d, _ = _parse(_dataset(
        {"dataFieldName": "some_new_field.reading", "value": "50", "key": _OWN,
         "timestamp": "2026-10-01T10:00:00Z"},
        {"dataFieldName": "some_new_field.reading", "value": "80",
         "timestamp": "2026-11-01T10:00:00Z"},
    ))
    assert (d.raw_unmapped_fields or {}).get("some_new_field.reading") == "80"


def test_only_the_key_of_the_point_whose_value_won_is_named() -> None:
    d, _ = _parse(_dataset(
        {"dataFieldName": "some_new_field.reading", "value": "50", "key": _OTHER,
         "timestamp": "2026-10-01T10:00:00Z"},
        {"dataFieldName": "some_new_field.reading", "value": "80", "key": _OWN,
         "timestamp": "2026-11-01T10:00:00Z"},
    ))
    assert (d.raw_unmapped_fields or {}).get("some_new_field.reading") == (
        "80 (uuid deadbeef)"
    )


def test_majority_value_names_only_the_points_that_sent_it() -> None:
    """#1088: 60 twice beats 71 once; the 71 point's key stays out. The 71 comes
    last, so it is the pick before the majority pass and 60 only after it: keys
    taken before that pass would name the 71 point."""
    third = "cafebabe-0000-4000-8000-000000000000"
    field_uuids: dict[str, set[str]] = {}
    fields = _walk_fields(
        _dataset(
            {"dataFieldName": "some_new_field.reading", "value": "60", "key": _OWN},
            {"dataFieldName": "some_new_field.reading", "value": "60", "key": third},
            {"dataFieldName": "some_new_field.reading", "value": "71", "key": _OTHER},
        ),
        {}, {}, {}, field_uuids,
    )
    assert fields["some_new_field.reading"] == "60"
    assert field_uuids["some_new_field.reading"] == {_OWN, third}


def test_sibling_attribute_of_the_same_name_lends_no_key() -> None:
    """A top-level list emits sibling attributes under their bare name; the
    sibling's value wins here and was not sent by the keyed point."""
    field_uuids: dict[str, set[str]] = {}
    fields = _walk_fields(
        [{"dataFieldName": "some_new_field", "value": "1", "key": _OWN,
          "some_new_field": "2"}],
        {}, {}, {}, field_uuids,
    )
    assert fields["some_new_field"] == "2"
    assert "some_new_field" not in field_uuids


def test_container_path_named_like_another_point_keeps_the_keys_apart() -> None:
    field_uuids: dict[str, set[str]] = {}
    fields = _walk_fields(
        {
            "some_box": {"dataFieldName": "inner", "value": "3", "key": _OTHER,
                         "timestamp": "2026-10-01T10:00:00Z"},
            "data": [{"dataFieldName": "some_box", "value": "9", "key": _OWN,
                      "timestamp": "2026-11-01T10:00:00Z"}],
        },
        {}, {}, {}, field_uuids,
    )
    assert fields["some_box"] == "9"
    assert field_uuids["some_box"] == {_OWN}
    assert field_uuids["inner"] == {_OTHER}


def test_float_value_names_its_key() -> None:
    d, _ = _parse(_dataset(
        {"dataFieldName": "some_new_field.reading", "value": 12.5, "key": _OWN},
    ))
    assert (d.raw_unmapped_fields or {}).get("some_new_field.reading") == (
        "12.5 (uuid deadbeef)"
    )


def test_upper_case_or_padded_key_is_normalised() -> None:
    d, _ = _parse(_dataset(
        {"dataFieldName": "some_new_field", "value": "42",
         "key": f"  {_OWN.upper()} "},
    ))
    assert (d.raw_unmapped_fields or {}).get("some_new_field") == (
        "42 (uuid deadbeef)"
    )


def test_generic_name_with_a_key_that_is_not_a_uuid_shows_no_key() -> None:
    d, _ = _parse(_dataset(
        {"dataFieldName": "open", "value": "true", "key": "driver"},
    ))
    assert (d.raw_unmapped_fields or {}).get("open") == "true"


@pytest.mark.parametrize("ownerless", [_OPEN, _OPEN_B])
def test_open_row_whose_value_came_from_another_key_raises_the_repair(
    ownerless: str,
) -> None:
    """The skip keys on c0bb1348 or d5dc7c87 in the sample. When the shown
    value came from a different opening point, that point is what the repair is
    there for. Whether the row is skipped therefore follows the shown value."""
    d, _ = _parse(_dataset(
        {"dataFieldName": "open", "value": "true", "key": ownerless,
         "timestamp": "2026-10-01T10:00:00Z"},
        {"dataFieldName": "open", "value": "false", "key": _OWN,
         "timestamp": "2026-11-01T10:00:00Z"},
    ))
    row = (d.raw_unmapped_fields or {})["open"]
    assert row == "false (uuid deadbeef)"
    assert not _is_scout_repair_skipped(_scout_finding("open", row))


def test_raw_api_fields_sensor_keeps_its_rows_out_of_the_recorder() -> None:
    """The live attribute stays; only its history is not written. Exactly
    ``fields`` is added, and only on this sensor."""
    from custom_components.vag_connect.sensor import (
        VagConnectSensor,
        VagRawApiFieldsSensor,
    )

    # The set Home Assistant hands to the recorder (helpers/entity.py).
    attr = "_Entity__combined_unrecorded_attributes"
    base = getattr(VagConnectSensor, attr)
    assert "fields" not in base
    assert getattr(VagRawApiFieldsSensor, attr) == base | {"fields"}


def test_setup_builds_the_raw_api_fields_sensor_with_that_class() -> None:
    import asyncio
    from unittest.mock import MagicMock

    from custom_components.vag_connect.sensor import (
        VagRawApiFieldsSensor,
        async_setup_entry,
    )

    vehicle = {"vin": "X", "raw_unmapped_fields": {"some_new_field": "42"}}
    coord = MagicMock()
    coord.vehicles = {"X": vehicle}
    coord.data = coord.vehicles
    coord.is_read_only = MagicMock(return_value=False)
    coord.last_update_success = True
    coord.command_capability_supported = MagicMock(return_value=None)
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    entry = MagicMock()
    entry.runtime_data = coord
    entry.options = {"hide_empty_entities": True}
    entry.data = {"brand": "skoda"}
    entry.async_on_unload = lambda x: None
    added: list = []
    asyncio.run(async_setup_entry(MagicMock(), entry, lambda e: added.extend(e)))
    raw = [e for e in added if e.entity_description.key == "raw_api_fields"]
    assert len(raw) == 1
    assert isinstance(raw[0], VagRawApiFieldsSensor)
    assert raw[0].extra_state_attributes == {"fields": {"some_new_field": "42"}}
