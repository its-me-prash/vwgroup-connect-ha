# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A ``NaN`` in the portal payload must not take down the whole snapshot.

``float("nan")`` and ``float("inf")`` SUCCEED, and Python's json decoder accepts
bare ``NaN`` / ``Infinity`` literals by default — so such a token can genuinely
arrive from the portal. Before v4.10.0 ``_to_float`` returned it unchanged,
which meant:

* ``_to_int`` raised ``ValueError: cannot convert float NaN to integer``. It is
  called 66 times in the mapper, so one junk token aborted the mapping of the
  ENTIRE snapshot and every good field in it was lost.
* a NaN that did land in a field reached ``to_dict()`` / the diagnostics
  download, which HA serialises with the stdlib encoder — that writes the bare
  literal ``NaN``, which strict JSON parsers reject, so the dump a reporter
  attaches to an issue could no longer be read back.
* a field with NO range guard accepted it silently. A guard of the shape
  ``0 <= v <= 255`` does the opposite — it rejects NaN, because every
  comparison against NaN is False — so the guard-less assignments were the
  exposed ones.

The same literal in a capture-TIME field was worse again: ``_parse_ts`` fed it
straight into the candidate ranking, where it is a sort key, so "freshest"
became arbitrary and a stale reading could win over a current one.
``last_seen_at`` itself was never at risk — the conversion to a timestamp
string already catches the ValueError — but the ranking had no such guard.

Found by the non-finite case of the #1689 climatisation-duration tests.
"""
from __future__ import annotations

import math

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _parse_ts,
    _to_float,
    _to_int,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

NON_FINITE = ("nan", "NaN", "-NaN", "inf", "-inf", "Infinity", "-Infinity")


def test_to_float_rejects_every_non_finite_spelling() -> None:
    for token in NON_FINITE:
        assert _to_float(token) is None, token


def test_to_int_no_longer_raises_on_them() -> None:
    for token in NON_FINITE:
        assert _to_int(token) is None, token


def test_real_numbers_are_untouched() -> None:
    assert _to_float("26432") == 26432.0
    assert _to_float("21,5") == 21.5          # comma decimal still works
    assert _to_float("-1") == -1.0            # sentinels stay the caller's job
    assert _to_int("120") == 120
    assert _to_float("0") == 0.0              # falsy but present


def test_a_nan_token_cannot_abort_a_whole_snapshot() -> None:
    """The expensive failure mode: the odometer goes through ``_to_int``, so a
    NaN there used to raise out of the mapper and discard the charge level,
    range and everything else delivered in the same snapshot."""
    payload = {
        "mileage": "NaN",
        "battery_state_report": {"soc": "62"},
        "cycle_data_mileage": "NaN",
        "climatisation_settings": {"duration": "NaN", "target_temperature": "120"},
    }
    syn: dict = {}
    d = map_dataset_to_vehicle_data(
        _walk_fields(payload, None, syn), VehicleData(vin="X"), field_syn=syn
    )
    assert d.battery_soc == 62          # the good field survived
    assert d.target_temperature == 22.0  # and so did the good neighbour
    assert d.odometer_km is None
    assert d.cyclic_trip_distance_km is None
    assert d.climatisation_duration_raw is None


def test_a_non_finite_capture_time_is_unparseable_not_a_sort_key() -> None:
    for token in (*NON_FINITE, float("nan"), float("inf"), float("-inf")):
        assert _parse_ts(token) is None, token


def test_real_timestamps_still_parse() -> None:
    assert _parse_ts("1759500000") == 1759500000.0
    assert _parse_ts(1759500000000) == 1759500000.0   # ms heuristic
    assert _parse_ts("2026-10-03T06:00:00Z") is not None
    assert _parse_ts("not a time") is None


def test_a_junk_capture_time_is_not_recorded_as_a_ranking_key() -> None:
    """The ranking is the part that had no guard: a NaN sort key makes
    "freshest" arbitrary, so a stale reading can win over a current one. The
    walker's per-field timestamp map must therefore hold no NaN, and the
    reading delivered beside it must still map."""
    payload = {
        "battery_state_report": {"soc": "55", "car_captured_timestamp": "NaN"},
    }
    syn: dict = {}
    ts: dict = {}
    flat = _walk_fields(payload, ts, syn)
    bad = {k: v for k, v in ts.items()
           if isinstance(v, float) and not math.isfinite(v)}
    assert not bad, bad
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    assert d.battery_soc == 55


def test_a_junk_capture_time_cannot_poison_the_freshness_anchor() -> None:
    """``last_seen_at`` feeds the staleness verdict, so whatever it ends up
    holding has to be a usable instant — never a NaN-derived one."""
    payload = {
        "battery_state_report": {"soc": "55", "car_captured_timestamp": "NaN"},
    }
    syn: dict = {}
    d = map_dataset_to_vehicle_data(
        _walk_fields(payload, None, syn), VehicleData(vin="X"), field_syn=syn
    )
    assert d.battery_soc == 55
    assert d.last_seen_at is None or math.isfinite(
        _parse_ts(d.last_seen_at) or 0.0
    )


def test_no_mapped_field_ends_up_holding_a_nan() -> None:
    """Whatever the payload throws, the dump must stay JSON-serialisable."""
    payload = {k: "NaN" for k in (
        "mileage", "soc", "cycle_data_mileage", "outside_temperature",
        "total_range", "oil_level_percentage",
    )}
    payload["climatisation_settings"] = {"duration": "Infinity"}
    syn: dict = {}
    d = map_dataset_to_vehicle_data(
        _walk_fields(payload, None, syn), VehicleData(vin="X"), field_syn=syn
    )
    bad = [
        k for k, v in d.to_dict().items()
        if isinstance(v, float) and not math.isfinite(v)
    ]
    assert not bad, bad
