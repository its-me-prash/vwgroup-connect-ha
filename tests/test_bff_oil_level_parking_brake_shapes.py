# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oil level and parking brake in the shape the status endpoint sends them.

Both arrive as a true/false ``value`` under their status block:

    oilLevel.oilLevelStatus.value         = {"value": true, "carCapturedTimestamp": ...}
    parkingBrake.parkingBrakeStatus.value = {"value": true, "carCapturedTimestamp": ...}

For the oil level true means the level is in order; for the parking brake
true means it is engaged. The oil level shape was measured on an Audi S6
(C8); the meaning of both values and the parking brake shape are the ones the
Audi app reads. The reader used to accept text only for the oil level and a
flat leaf only for the parking brake, so both were dropped.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad._unexpected_keys import detect_unexpected
from custom_components.vag_connect.cariad.api.vw_eu import (
    _SELECTIVE_STATUS_JOBS,
    VWEUClient,
)
from custom_components.vag_connect.cariad.models import VehicleData

_TS = "2026-01-01T00:00:00Z"


def _parse(raw: dict[str, Any]) -> VehicleData:
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client._parse_status("VINX", raw, parking={})


def _oil(value: Any) -> VehicleData:
    block = {"value": value, "carCapturedTimestamp": _TS}
    return _parse({"oilLevel": {"oilLevelStatus": {"value": block}}})


def _brake(value: Any) -> VehicleData:
    block = {"value": value, "carCapturedTimestamp": _TS}
    return _parse({"parkingBrake": {"parkingBrakeStatus": {"value": block}}})


# ── oil level ────────────────────────────────────────────────────────────────


def test_oil_level_true_means_no_warning() -> None:
    assert _oil(True).oil_level_warning is False


def test_oil_level_false_is_a_warning() -> None:
    assert _oil(False).oil_level_warning is True


def test_oil_level_boolean_invents_no_status_text() -> None:
    # The status field carries the backend's own text. A boolean has none.
    assert _oil(True).oil_level_status is None
    assert _oil(False).oil_level_status is None


@pytest.mark.parametrize(
    ("text", "warning"),
    [("normal", False), ("ok", False), ("warningLow", True), ("serviceRequired", True)],
)
def test_oil_level_text_is_read_as_before(text: str, warning: bool) -> None:
    data = _oil(text)
    assert data.oil_level_status == text
    assert data.oil_level_warning is warning


def test_oil_level_unknown_text_stays_undecided() -> None:
    data = _oil("somethingNew")
    assert data.oil_level_status == "somethingNew"
    assert data.oil_level_warning is None


def test_oil_level_error_block_sets_nothing() -> None:
    data = _parse({"oilLevel": {"oilLevelStatus": {"error": {"code": 4111, "message": "x"}}}})
    assert data.oil_level_warning is None
    assert data.oil_level_status is None


@pytest.mark.parametrize("value", [1, 0])
def test_oil_level_number_is_not_taken_as_true_or_false(value: int) -> None:
    # True and False are numbers to Python. A 1 or a 0 from the backend is not
    # the true/false shape and must stay undecided, as it did before.
    data = _oil(value)
    assert data.oil_level_warning is None
    assert data.oil_level_status is None


@pytest.mark.parametrize(
    ("value", "flat", "warning"),
    [(False, "ok", True), (True, "low", False), (False, "normal", True), (True, "warningLow", False)],
)
def test_oil_level_true_or_false_is_not_overridden_by_a_flat_text(value: bool, flat: str, warning: bool) -> None:
    # The older flat ``oilLevelResult`` text is a fallback for an answer that
    # has no oil level block. Once the block has decided, it must not decide
    # again, and it must not put a text next to a warning it contradicts.
    raw = {
        "oilLevel": {"oilLevelStatus": {"value": {"value": value, "carCapturedTimestamp": _TS}}},
        "elsewhere": {"oilLevelResult": flat},
    }
    data = _parse(raw)
    assert data.oil_level_warning is warning
    assert data.oil_level_status is None


@pytest.mark.parametrize(("flat", "warning"), [("ok", False), ("low", True)])
def test_oil_level_flat_text_still_decides_without_a_block(flat: str, warning: bool) -> None:
    # Control for the test above: the fallback itself is unchanged.
    data = _parse({"elsewhere": {"oilLevelResult": flat}})
    assert data.oil_level_status == flat
    assert data.oil_level_warning is warning


# ── parking brake ────────────────────────────────────────────────────────────


def test_parking_brake_true_is_engaged() -> None:
    assert _brake(True).parking_brake_engaged is True


def test_parking_brake_false_is_released() -> None:
    assert _brake(False).parking_brake_engaged is False


def test_parking_brake_without_a_value_stays_unknown() -> None:
    data = _parse({"parkingBrake": {"parkingBrakeStatus": {"value": {"carCapturedTimestamp": _TS}}}})
    assert data.parking_brake_engaged is None


def test_parking_brake_error_block_stays_unknown() -> None:
    data = _parse({"parkingBrake": {"parkingBrakeStatus": {"error": {"code": 4111, "message": "x"}}}})
    assert data.parking_brake_engaged is None


def test_parking_brake_flat_leaf_is_read_as_before() -> None:
    assert _parse({"parkingBrakeStatus": "engaged"}).parking_brake_engaged is True
    assert _parse({"parkingBrakeStatus": "released"}).parking_brake_engaged is False


def test_parking_brake_block_wins_over_a_flat_leaf_elsewhere() -> None:
    raw = {
        "parkingBrake": {"parkingBrakeStatus": {"value": {"value": False, "carCapturedTimestamp": _TS}}},
        "other": {"parkingBrakeStatus": "engaged"},
    }
    assert _parse(raw).parking_brake_engaged is False


@pytest.mark.parametrize("value", ["engaged", 1, 0])
def test_parking_brake_block_takes_only_true_or_false(value: Any) -> None:
    # The app reads a true/false value from this block. A text or a number
    # there is not that shape; nothing is read from it.
    assert _brake(value).parking_brake_engaged is None


def test_parking_brake_job_is_requested() -> None:
    assert "parkingBrake" in _SELECTIVE_STATUS_JOBS.split(",")


@pytest.mark.parametrize("brand", ["audi", "volkswagen"])
@pytest.mark.parametrize(
    "block",
    [
        {"value": {"value": True, "carCapturedTimestamp": _TS}},
        {"error": {"message": "x", "errorTimeStamp": _TS, "info": "x", "code": 4111, "group": 2, "retry": True}},
    ],
    ids=["value", "error"],
)
def test_parking_brake_block_is_not_reported_as_unmapped(brand: str, block: dict[str, Any]) -> None:
    # The job is asked for on every poll, so its answer must be a known shape,
    # or every car that reports it would open an "unmapped field" report.
    found = list(detect_unexpected(brand, "selectivestatus", {"parkingBrake": {"parkingBrakeStatus": block}}))
    assert [f.path for f in found] == []


def test_the_unmapped_field_check_can_fire() -> None:
    # Control for the test above: the same call does report a block it does not know.
    found = list(detect_unexpected("audi", "selectivestatus", {"notAKnownJob": {"x": 1}}))
    assert [f.path for f in found] == ["notAKnownJob"]
