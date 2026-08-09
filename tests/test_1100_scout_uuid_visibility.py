# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1100-#1117 — make a generic-leaf Scout row identifiable by its source UUID.

The EU data portal encodes about ten different opening states (doors, windows,
sunroof, trunk, bonnet) under one generic ``open`` leaf, distinguished only by
the per-point content UUID. The Scout reported just ``open: true``, so every
reporter filed a literally identical, unactionable row — ten people did exactly
that in a single day — and neither they nor we could say which opening it was.

The dictionary shows why that matters: ``f5fa6f61`` is documented as the sun
roof (and is mapped), while ``c0bb1348`` and ``d5dc7c87`` are both bare
"Openig status" with no owner. Only the UUID separates them.

The discovery value now carries the UUID. The field NAME is untouched — every
mapping keys on it — and nothing is suppressed, which the no-suppression rule
requires: this adds information rather than hiding a row.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# Two of the real ambiguous opening UUIDs from the official dictionary.
_UUID_A = "c0bb1348-5d0d-3140-9a51-06881db06490"
_UUID_B = "d5dc7c87-5051-34db-ae99-0bd2cf987c45"


def _dataset(*points: dict) -> dict:
    return {"data": list(points)}


def _parse(payload: dict) -> VehicleData:
    field_ts: dict[str, float] = {}
    field_syn: dict[str, set[str]] = {}
    contested: dict[str, set[str]] = {}
    field_uuids: dict[str, set[str]] = {}
    fields = _walk_fields(payload, field_ts, field_syn, contested, field_uuids)
    return map_dataset_to_vehicle_data(
        fields, VehicleData(vin="X"), field_ts, field_syn, contested, field_uuids
    )


def test_walk_records_the_uuid_of_a_generic_leaf() -> None:
    field_uuids: dict[str, set[str]] = {}
    _walk_fields(
        _dataset({"dataFieldName": "open", "value": "true", "key": _UUID_A}),
        {}, {}, {}, field_uuids,
    )
    assert field_uuids.get("open") == {_UUID_A}


def test_discovery_row_names_the_uuid() -> None:
    d = _parse(_dataset({"dataFieldName": "open", "value": "true", "key": _UUID_A}))
    row = (d.raw_unmapped_fields or {}).get("open")
    assert row is not None, "the open leaf must still be surfaced, never suppressed"
    assert "true" in row  # the real value is still there
    assert "c0bb1348" in row  # ...and is now identifiable


def test_two_reporters_with_different_uuids_are_distinguishable() -> None:
    """The whole point: two cars that both report a bare `open` no longer file
    the same unactionable row."""
    a = _parse(_dataset({"dataFieldName": "open", "value": "true", "key": _UUID_A}))
    b = _parse(_dataset({"dataFieldName": "open", "value": "true", "key": _UUID_B}))
    row_a = (a.raw_unmapped_fields or {})["open"]
    row_b = (b.raw_unmapped_fields or {})["open"]
    assert row_a != row_b
    assert "c0bb1348" in row_a and "d5dc7c87" in row_b


def test_field_name_is_not_rewritten() -> None:
    """Mappings key on the field name — annotating it would break them."""
    d = _parse(_dataset({"dataFieldName": "open", "value": "true", "key": _UUID_A}))
    assert "open" in (d.raw_unmapped_fields or {})


def test_a_named_field_without_a_uuid_is_unchanged() -> None:
    d = _parse(_dataset({"dataFieldName": "some_new_field", "value": "42"}))
    assert (d.raw_unmapped_fields or {}).get("some_new_field") == "42"


def test_legacy_callers_without_the_uuid_map_still_work() -> None:
    fields = _walk_fields(
        _dataset({"dataFieldName": "open", "value": "true", "key": _UUID_A})
    )
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))
    assert (d.raw_unmapped_fields or {}).get("open") == "true"
