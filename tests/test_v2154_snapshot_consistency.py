# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.4 (#529) — EU Data Act portal snapshot COHERENCE.

The portal ZIP is a flat, append-ordered multi-snapshot event-log. Resolving
each field independently let soc, odometer and last_seen surface from DIFFERENT
snapshots — odometer in particular was lifted by a within-ZIP monotonic MAX from
an arbitrary OLDER snapshot while last_seen tracked the newest one, manufacturing
a phantom "moved at night". The fix makes every field resolve to its latest
available sample, so the surfaced values no longer contradict each other; and
odometer's cross-poll "never regress" guarantee is owned by
``vehicle_cache.reconcile`` (against the PERSISTED value), not by a within-ZIP max.

Scenarios encoded here match the empirical #529 diagnosis traces:
  S1  newest snapshot has mileage + cct but NOT soc → fields must be consistent
  S3  odometer must not exceed last_seen's snapshot → no phantom movement
  S5  no real per-point ts anywhere → LAST (newest append) value wins
  S6  two samples in the SAME snapshot block → LAST appended value wins
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


# ── S1: newest snapshot carries mileage + cct but no soc ──────────────────────
def test_s1_soc_not_stale_while_odo_and_last_seen_fresh() -> None:
    # Older snapshot (15:00) carried soc=80 + mileage=10000; newer snapshot
    # (18:00) re-reported only mileage=10004. odometer/last_seen are fresh; soc
    # is carried from the only snapshot that has it. The surfaced odometer and
    # last_seen must BOTH come from the latest (18:00) snapshot — they may not
    # disagree with each other (the desync that caused the bug).
    payload = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T15:00:00Z"},
        {"dataFieldName": "soc", "value": "80"},
        {"dataFieldName": "mileage", "value": "10000"},
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:00:00Z"},
        {"dataFieldName": "mileage", "value": "10004"},
    ]
    f = _walk_fields(payload)
    assert f["mileage"] == "10004"             # latest snapshot's odometer
    assert f["car_captured_time"] == "2026-06-24T18:00:00Z"
    # soc reflects the latest available SAMPLE (only the 15:00 block had it); it
    # is not silently dropped, and odometer/cct are mutually consistent.
    assert f["soc"] == "80"
    d = map_dataset_to_vehicle_data(f, VehicleData(vin="X"))
    assert d.odometer_km == 10004
    assert d.battery_soc == 80


# ── S3: odometer must not be lifted from an OLDER snapshot ─────────────────────
def test_s3_odometer_from_same_snapshot_as_last_seen_no_phantom_move() -> None:
    # The 18:00 snapshot (newest) reports mileage=9000; an OLDER 15:00 snapshot
    # reports a HIGHER 10000. The old within-ZIP monotonic-MAX surfaced 10000
    # (from 15:00) while last_seen tracked 18:00 → HA saw odo change + last_seen
    # advance = phantom movement. The surfaced odometer must come from the SAME
    # snapshot as last_seen (18:00 → 9000).
    payload = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:00:00Z"},
        {"dataFieldName": "mileage", "value": "9000"},
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T15:00:00Z"},
        {"dataFieldName": "mileage", "value": "10000"},
    ]
    f = _walk_fields(payload)
    assert f["mileage"] == "9000"  # latest cct's odometer, NOT the older max
    assert f["car_captured_time"] == "2026-06-24T18:00:00Z"


def test_s3_last_seen_capped_to_odometer_snapshot() -> None:
    # Decoupling (#529 step 2): newest snapshot (18:00) re-reports the capture
    # time but NOT the odometer; odometer is genuinely from the older 15:00
    # block. last_seen_at must NOT be advanced past the odometer's snapshot, so
    # HA can't infer movement from two desynced fields.
    payload = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T15:00:00Z"},
        {"dataFieldName": "mileage", "value": "10000"},
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:00:00Z"},
        # 18:00 block carries no mileage — odometer stays at the 15:00 reading.
    ]
    field_ts: dict[str, float] = {}
    f = _walk_fields(payload, field_ts)
    d = map_dataset_to_vehicle_data(f, VehicleData(vin="X"), field_ts)
    assert d.odometer_km == 10000
    # last_seen capped back to the odometer's 15:00 snapshot, not the raw 18:00
    # capture time → no "odometer changed AND last_seen advanced" phantom move.
    assert d.last_seen_at is not None
    assert d.last_seen_at.startswith("2026-06-24T15:00:00")


def test_last_seen_not_capped_when_odometer_is_fresh() -> None:
    # Sanity: when the odometer IS in the newest snapshot, last_seen tracks it
    # normally (no spurious cap).
    payload = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T15:00:00Z"},
        {"dataFieldName": "mileage", "value": "10000"},
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:00:00Z"},
        {"dataFieldName": "mileage", "value": "10004"},
    ]
    field_ts: dict[str, float] = {}
    f = _walk_fields(payload, field_ts)
    d = map_dataset_to_vehicle_data(f, VehicleData(vin="X"), field_ts)
    assert d.odometer_km == 10004
    assert d.last_seen_at is not None
    assert d.last_seen_at.startswith("2026-06-24T18:00:00")


# ── S5: no real per-point ts anywhere → last (newest append) wins ─────────────
def test_s5_no_real_ts_last_write_wins() -> None:
    payload = [
        {"dataFieldName": "soc", "value": "55"},  # earlier append
        {"dataFieldName": "soc", "value": "90"},  # later append = newer
    ]
    assert _walk_fields(payload)["soc"] == "90"


# ── S6: two samples in the SAME snapshot block → last appended wins ───────────
def test_s6_same_block_duplicate_last_wins() -> None:
    payload = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:00:00Z"},
        {"dataFieldName": "soc", "value": "55"},  # same block, earlier append
        {"dataFieldName": "soc", "value": "90"},  # same block, later append
    ]
    assert _walk_fields(payload)["soc"] == "90"


# ── regression guard: distinct real timestamps still pick the freshest ────────
def test_distinct_real_ts_still_picks_freshest_either_order() -> None:
    fwd = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T15:00:00Z"},
        {"dataFieldName": "soc", "value": "55"},
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:00:00Z"},
        {"dataFieldName": "soc", "value": "90"},
    ]
    assert _walk_fields(fwd)["soc"] == "90"
    bwd = [
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T18:00:00Z"},
        {"dataFieldName": "soc", "value": "90"},
        {"dataFieldName": "car_captured_time", "value": "2026-06-24T15:00:00Z"},
        {"dataFieldName": "soc", "value": "55"},
    ]
    assert _walk_fields(bwd)["soc"] == "90"
