# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2096 — the state of charge and the odometer take their OWN capture time.

A flat EU Data Act export is an unordered event log. The walker gave every
value the time of the nearest capture entry before it in the list, so when the
portal reordered the list between two downloads the same, unchanged reading
got a different ``data_captured_at`` (up to 2.5 h off on one ID.7).

Two values can be tied to their time by KEY instead of by position: each of
``battery_level_HV.value`` / ``.state`` and ``mileage.value`` / ``.state`` has
a ``timestamp`` entry under a fixed key that is present in exactly the same
exports. A value with no such time gets NO capture time rather than the
neighbour's. The other stamped fields are not touched.
"""
from __future__ import annotations

import random
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

SOC_TS_KEY = "3f5a294b-b672-3963-83d8-bfb54e5b943d"
ODO_TS_KEY = "067f539c-85fe-3067-9c29-d63e177e3712"
SOC_TS = "2026-11-13T06:57:12Z"
ODO_TS = "2026-11-13T06:57:06Z"


def _p(key: str, name: str, value: str) -> dict[str, str]:
    return {"key": key, "dataFieldName": name, "value": value}


SOC_VALUE = _p("ac1108b1-b8cc-3db9-a663-03d387e42223", "battery_level_HV.value", "81")
SOC_STATE = _p("2a9de7f7-a846-3d18-9883-650de9c4e4e1", "battery_level_HV.state", "VALID")
SOC_STAMP = _p(SOC_TS_KEY, "timestamp", SOC_TS)
ODO_VALUE = _p("30cc36fd-71ca-3c09-9296-e94ebd47bd2b", "mileage.value", "12345")
ODO_STATE = _p("a04d086d-70bb-30c2-8361-68da66b4fd97", "mileage.state", "VALID")
ODO_STAMP = _p(ODO_TS_KEY, "timestamp", ODO_TS)
# Frozen/stale capture markers of the kind the Cupra file carries.
MARKERS = [
    _p("11111111-0000-0000-0000-00000000000%d" % i, "car_captured_utc_timestamp",
       "2026-11-0%dT18:04:38Z" % i)
    for i in (6, 7, 8)
]
CHARGING = _p("22222222-0000-0000-0000-000000000001", "charging_state", "charging")
PLUG = _p("22222222-0000-0000-0000-000000000002",
          "plugStatusItem.plugConnectionState", "connected")


def _map(items: list[dict[str, str]]) -> VehicleData:
    ts: dict[str, float] = {}
    syn: dict[str, set[str]] = {}
    contested: dict[str, set[str]] = {}
    uuids: dict[str, set[str]] = {}
    inh: set[str] = set()
    flat = _walk_fields({"data": items}, ts, syn, contested, uuids, None, inh)
    return map_dataset_to_vehicle_data(
        flat, VehicleData(vin="X"), ts, syn, contested, uuids, inh
    )


def _full() -> list[dict[str, str]]:
    return [SOC_VALUE, SOC_STATE, SOC_STAMP, ODO_VALUE, ODO_STATE, ODO_STAMP,
            *MARKERS, CHARGING, PLUG]


def test_soc_and_odometer_stamps_do_not_depend_on_list_order() -> None:
    seen: set[tuple[Any, Any]] = set()
    rng = random.Random(2096)
    for _ in range(200):
        items = _full()
        rng.shuffle(items)
        d = _map(items)
        assert d.battery_soc == 81
        assert d.odometer_km == 12345
        seen.add((d.field_captured_ts.get("battery_soc"),
                  d.field_captured_ts.get("odometer_km")))
    assert len(seen) == 1, f"stamps moved with the list order: {seen}"
    soc_iso, odo_iso = next(iter(seen))
    assert soc_iso is not None and soc_iso.startswith("2026-11-13T06:57:12")
    assert odo_iso is not None and odo_iso.startswith("2026-11-13T06:57:06")


def test_a_file_without_the_time_keys_gives_no_stamp_for_the_two() -> None:
    rng = random.Random(7)
    for _ in range(50):
        items = [SOC_VALUE, SOC_STATE, ODO_VALUE, ODO_STATE, *MARKERS]
        rng.shuffle(items)
        d = _map(items)
        assert d.battery_soc == 81
        assert d.odometer_km == 12345
        assert "battery_soc" not in d.field_captured_ts
        assert "odometer_km" not in d.field_captured_ts


def test_only_the_missing_pair_loses_its_stamp() -> None:
    items = [SOC_VALUE, SOC_STATE, SOC_STAMP, ODO_VALUE, ODO_STATE, *MARKERS]
    d = _map(items)
    assert d.field_captured_ts["battery_soc"].startswith("2026-11-13T06:57:12")
    assert "odometer_km" not in d.field_captured_ts


def test_the_other_stamped_fields_still_take_the_neighbour_stamp() -> None:
    items = [MARKERS[0], CHARGING, MARKERS[1], PLUG, MARKERS[2],
             SOC_VALUE, SOC_STATE, SOC_STAMP]
    d = _map(items)
    assert d.field_captured_ts["charging_state"].startswith("2026-11-06")
    assert d.field_captured_ts["plug_state"].startswith("2026-11-07")


def test_a_point_with_its_own_sibling_stamp_keeps_it() -> None:
    """The #1688 dialect (``timestampUtc`` beside the value) is a genuine own
    stamp, not a neighbour's, and stays."""
    items = [{"dataFieldName": "mileage", "value": "777",
              "timestampUtc": "2026-10-03T16:59:46Z"}]
    d = _map(items)
    assert d.field_captured_ts["odometer_km"].startswith("2026-10-03T16:59:46")


@pytest.mark.parametrize("seed", range(5))
def test_the_walker_reports_which_stamps_were_inherited(seed: int) -> None:
    items = _full()
    random.Random(seed).shuffle(items)
    ts: dict[str, float] = {}
    inh: set[str] = set()
    _walk_fields({"data": items}, ts, None, None, None, None, inh)
    assert "charging_state" in inh
    assert "battery_level_HV.value" not in inh
    assert "mileage.value" not in inh
