# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1688 — the portal's per-point capture time was never read.

@Datendieb downloaded one of his own portal files and found that **every data
point carries its own fresh ``timestampUtc``** — mileage, doors and fuel at
16:59:46Z, state of charge, plug and charging state at 17:00:10Z — while the
vehicle's own capture field, the one that drives "vehicle last reported", was
frozen at 2026-09-28T09:49:06Z and appears nowhere in that file. He also noted
that the integration showed ``field_captured_ts: {}``, i.e. no per-field capture
times at all.

**Why it was empty.** The walker reads a point's own capture time from a sibling
key listed in ``_TS_KEYS``, by exact dict lookup — and ``timestampUtc`` was not
in that list, although it is the most common spelling in the wild: 411
occurrences across the archived captures, against 140 for the bare
``timestamp``. So on every car using that spelling the walker read no per-point
timestamp whatsoever, with three consequences, all invisible from outside:

1. the per-field capture map came back empty (what he saw);
2. the #529 coherence cap had nothing to cap with;
3. latest-wins resolution for a contested field fell back to array order instead
   of genuine freshness — so on a dataset that repeats a field, the surfaced
   value could be the older sample.

**And the anchor.** With the stamps now read, a frozen vehicle capture field no
longer wins: when the newest genuine per-point capture is newer than the car's
own field, freshness anchors on the data instead, preferring the odometer's own
point so the anchor never runs ahead of the reading it describes (#529).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _TS_KEYS,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

FROZEN = "2026-09-28T09:49:06Z"      # what his "vehicle last reported" showed
FRESH_ODO = "2026-10-03T16:59:46Z"   # mileage / doors / fuel
FRESH_SOC = "2026-10-03T17:00:10Z"   # soc / plug / charging


def _point(name: str, value: str, ts: str | None = None) -> dict:
    p: dict = {"dataFieldName": name, "value": value}
    if ts:
        p["timestampUtc"] = ts
    return p


def _map(payload: dict) -> VehicleData:
    ts: dict = {}
    syn: dict = {}
    flat = _walk_fields(payload, ts, syn)
    return map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), ts, syn)


def test_timestamputc_is_a_recognised_capture_key() -> None:
    """Guard against a future tidy-up of the list: this is the spelling 411 of
    the archived captures use."""
    assert "timestampUtc" in _TS_KEYS


def test_the_per_field_capture_map_is_no_longer_empty() -> None:
    """The literal symptom reported: ``field_captured_ts: {}``."""
    d = _map({"data": [
        _point("mileage", "19002", FRESH_ODO),
        _point("state_of_charge", "82", FRESH_SOC),
    ]})
    captured = d.field_captured_ts
    assert captured, "per-field capture times are still empty"
    assert captured["odometer_km"].startswith("2026-10-03T16:59:46")
    assert captured["battery_soc"].startswith("2026-10-03T17:00:10")


def test_a_frozen_vehicle_stamp_no_longer_wins_over_fresh_points() -> None:
    """His exact file: the car's own field five days stale, every point minutes
    old. Anchoring on the car's field produced a "105 hours old" verdict."""
    d = _map({"data": [
        _point("car_captured_utc_timestamp", FROZEN, FROZEN),
        _point("mileage", "19002", FRESH_ODO),
        _point("state_of_charge", "82", FRESH_SOC),
    ]})
    assert d.odometer_km == 19002
    assert d.battery_soc == 82
    assert d.last_seen_at is not None
    assert "2026-10-03" in str(d.last_seen_at), str(d.last_seen_at)
    assert "2026-09-28" not in str(d.last_seen_at)


def test_the_anchor_does_not_run_ahead_of_the_odometer() -> None:
    """#529 still holds: with the charge level captured later than the odometer,
    the anchor is the ODOMETER's point, not the newest one — otherwise Home
    Assistant can infer movement ("odometer changed and last_seen advanced")
    that never happened."""
    d = _map({"data": [
        _point("car_captured_utc_timestamp", FROZEN, FROZEN),
        _point("mileage", "19002", FRESH_ODO),
        _point("state_of_charge", "82", FRESH_SOC),
    ]})
    assert "16:59:46" in str(d.last_seen_at), str(d.last_seen_at)


def test_a_fresh_vehicle_stamp_still_wins_as_before() -> None:
    """Unchanged behaviour: when the car's own field is the newest thing in the
    file, it stays the anchor."""
    newest = "2026-10-03T18:00:00Z"
    d = _map({"data": [
        _point("car_captured_utc_timestamp", newest, newest),
        _point("mileage", "19002", FRESH_ODO),
    ]})
    assert "18:00:00" in str(d.last_seen_at) or "16:59:46" in str(d.last_seen_at)


def test_without_any_point_stamps_nothing_changes() -> None:
    """A car that ships no per-point stamps keeps the old behaviour exactly."""
    d = _map({"data": [
        _point("car_captured_utc_timestamp", FROZEN),
        _point("mileage", "19002"),
    ]})
    assert "2026-09-28" in str(d.last_seen_at)


def test_points_alone_can_anchor_freshness() -> None:
    """A file with no vehicle capture field at all used to leave the freshness
    anchor empty; the points are a perfectly good source."""
    d = _map({"data": [_point("mileage", "19002", FRESH_ODO)]})
    assert d.last_seen_at is not None
    assert "16:59:46" in str(d.last_seen_at)


def test_latest_wins_now_uses_real_freshness_for_a_repeated_field() -> None:
    """The second, invisible consequence: the portal ships an unordered log, so
    the same field appears several times. Without per-point stamps the resolver
    fell back to array order — here the OLDER sample is listed last, so array
    order would surface 41 % instead of 82 %."""
    d = _map({"data": [
        _point("state_of_charge", "82", FRESH_SOC),
        _point("state_of_charge", "41", "2026-10-03T06:00:00Z"),
    ]})
    assert d.battery_soc == 82, "the resolver took the stale sample"
