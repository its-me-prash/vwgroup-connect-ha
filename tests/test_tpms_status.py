# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#528/#538 — TPMS system-type (tpms_status) from the EU Data Act actual-pressure family.

Indirect/ABS-based TPMS ships the whole actual-pressure family as the "1" sentinel,
which the parser drops — so the per-wheel sensors never spawn and the fact the car
HAS a TPMS was invisible. tpms_status surfaces it: "measured" when a corner reports
a real >1 reading, "indirect" when the family is present but all-"1". Read from the
RAW ``fields`` (read-only), so the sentinel-consume bookkeeping is untouched.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_ACTUAL = (
    "tyre_pressure_actual_front_left",
    "tyre_pressure_actual_front_right",
    "tyre_pressure_actual_rear_left",
    "tyre_pressure_actual_rear_right",
)


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_indirect_when_the_actual_family_is_all_one() -> None:
    d = _map({k: "1" for k in _ACTUAL})
    assert d.tpms_status == "indirect"
    # the per-wheel pressure targets still drop (regression guard on the sentinel)
    assert d.tyre_pressure_actual_fl is None
    assert d.tyre_pressure_actual_rr is None


def test_measured_when_any_corner_reports_a_real_reading() -> None:
    d = _map({
        "tyre_pressure_actual_front_left": "230",
        "tyre_pressure_actual_front_right": "1",  # one faulty/invalid corner
    })
    assert d.tpms_status == "measured"
    assert d.tyre_pressure_actual_fl == 230  # the real reading still maps


def test_none_when_absent_or_all_unsupported() -> None:
    assert _map({}).tpms_status is None
    # 0 = unsupported → no TPMS signal, no phantom entity
    assert _map({"tyre_pressure_actual_front_left": "0"}).tpms_status is None


def test_spare_only_indirect_still_classifies() -> None:
    d = _map({"tyre_pressure_actual_spare_tyre": "1"})
    assert d.tpms_status == "indirect"
