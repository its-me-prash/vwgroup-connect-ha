# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.0 — a mapped field must not re-surface as a "new field" forever.

The walker emits BOTH spellings of a nested field: the bare leaf and the
dotted path. `first()` reclaims every spelling it was *told about* — so a
names list containing only the bare leaf consumes that one and leaves the
dotted twin unclaimed, which then lands in raw_unmapped_fields on every poll
and reaches the reporter as a brand-new discovery.

That is what put `profile_state_report.car_captured_time` in front of a
reporter (#790) for a field the parser has read since v2.15.1.

The fix is the names list, not a synonym mechanism: an adversarial check
showed that recording bare<->dotted synonyms would collapse *distinct* nodes
that merely share a leaf name (rangeStatus.range vs secondaryDrive.range) and
delete genuinely-unmapped data — a no-suppression violation.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _unmapped(payload: dict) -> set[str]:
    ts: dict[str, float] = {}
    syn: dict[str, set[str]] = {}
    fields = _walk_fields(payload, ts, syn)
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="X"), ts, syn)
    return set(d.raw_unmapped_fields or [])


def test_dotted_car_captured_time_is_not_reported_as_new() -> None:
    out = _unmapped({"profile_state_report": {"car_captured_time": "2026-07-16T16:21:02.143Z"}})
    assert "profile_state_report.car_captured_time" not in out
    assert "car_captured_time" not in out


def test_dotted_instrument_cluster_time_is_not_reported_as_new() -> None:
    out = _unmapped(
        {"profile_state_report": {"instrument_cluster_time": "2026-07-16T18:21:02.000+02:00"}}
    )
    assert "profile_state_report.instrument_cluster_time" not in out
    assert "instrument_cluster_time" not in out


def test_the_value_still_lands() -> None:
    # Claiming the name without reading the value would be worse than the noise.
    ts: dict[str, float] = {}
    syn: dict[str, set[str]] = {}
    f = _walk_fields(
        {"profile_state_report": {"instrument_cluster_time": "2026-07-16T18:21:02.000+02:00"}},
        ts, syn,
    )
    d = map_dataset_to_vehicle_data(f, VehicleData(vin="X"), ts, syn)
    assert d.instrument_cluster_time == "2026-07-16T18:21:02.000+02:00"


def test_bare_spelling_still_works() -> None:
    # Cars that ship the bare leaf must be unaffected.
    ts: dict[str, float] = {}
    syn: dict[str, set[str]] = {}
    f = _walk_fields({"Data": [
        {"dataFieldName": "instrument_cluster_time", "value": "2026-07-16T18:21:02.000+02:00"},
    ]}, ts, syn)
    d = map_dataset_to_vehicle_data(f, VehicleData(vin="X"), ts, syn)
    assert d.instrument_cluster_time == "2026-07-16T18:21:02.000+02:00"


def test_a_genuinely_unmapped_field_is_still_reported() -> None:
    # The point is to stop lying about what's new — not to go quiet.
    out = _unmapped({"profile_state_report": {"something_we_never_saw": "42"}})
    assert any("something_we_never_saw" in k for k in out)
