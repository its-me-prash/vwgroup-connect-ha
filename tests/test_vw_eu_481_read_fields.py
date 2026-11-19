# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""We Connect app 4.8.1 read fields: ``safelockActive`` and ``chargePowerLimitationReason``.

The shapes come from the decompiled app (AccessStatus gained a required
``safelockActive`` Boolean, BatteryStatus an optional ``chargePowerLimitationReason``
string-wrapper enum). No car has been seen sending either. The vocabulary of the
reason is unknown, so the token is surfaced raw and never mapped or dropped.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.binary_sensor import (
    _DATA_PRESENT_REQUIRED as BIN_REQUIRED,
    BINARY_DESCRIPTIONS,
)
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.sensor import (
    _DATA_PRESENT_REQUIRED as SENSOR_REQUIRED,
    SENSOR_DESCRIPTIONS,
)


def _parse(payload: dict):
    client = VWEUClient(MagicMock(), "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client._parse_status("VIN1", payload, {})


def _payload(safelock=None, reason=None, *, with_safelock=True, with_reason=True):
    access = {"overallStatus": "safe", "doorLockStatus": "locked"}
    if with_safelock:
        access["safelockActive"] = safelock
    battery = {"currentSOC_pct": 80}
    if with_reason:
        battery["chargePowerLimitationReason"] = reason
    return {
        "access": {"accessStatus": {"value": access}},
        "charging": {"batteryStatus": {"value": battery}},
    }


@pytest.mark.parametrize("sent", [True, False])
def test_safelock_boolean_is_mapped(sent: bool) -> None:
    assert _parse(_payload(safelock=sent)).safelock_active is sent


@pytest.mark.parametrize("sent", [None, "true", 1, 0, "", {}])
def test_safelock_non_boolean_stays_none(sent) -> None:
    assert _parse(_payload(safelock=sent)).safelock_active is None


def test_safelock_absent_stays_none() -> None:
    assert _parse(_payload(with_safelock=False)).safelock_active is None


@pytest.mark.parametrize("token", [
    "chargePurposeReachedAndNotConservationCharging",
    "someTokenFromAFutureFirmware",
    "unknown",
])
def test_reason_is_passed_through_raw(token: str) -> None:
    assert _parse(_payload(reason=token)).charge_power_limitation_reason == token


def test_reason_is_trimmed() -> None:
    d = _parse(_payload(reason="  chargePurposeReached "))
    assert d.charge_power_limitation_reason == "chargePurposeReached"


@pytest.mark.parametrize("sent", [None, "", "  ", 3, {"rawValue": "x"}])
def test_reason_junk_stays_none(sent) -> None:
    assert _parse(_payload(reason=sent)).charge_power_limitation_reason is None


def test_reason_absent_stays_none() -> None:
    assert _parse(_payload(with_reason=False)).charge_power_limitation_reason is None


def test_existing_neighbours_unchanged() -> None:
    d = _parse(_payload(safelock=True, reason="x"))
    assert d.doors_locked is True
    assert d.battery_soc == 80


def test_scout_knows_both_paths() -> None:
    from custom_components.vag_connect.cariad._unexpected_keys import detect_unexpected

    payload = _payload(safelock=True, reason="x")
    for brand in ("volkswagen", "audi"):
        found = {u.path for u in detect_unexpected(brand, "selectivestatus", payload)}
        assert not any("safelockActive" in p or "chargePowerLimitationReason" in p for p in found)


def test_entities_read_real_vehicle_fields_and_phantom_gate_hides_none() -> None:
    from dataclasses import fields

    from custom_components.vag_connect.cariad.models import VehicleData

    names = {f.name for f in fields(VehicleData)}
    assert {"safelock_active", "charge_power_limitation_reason"} <= names
    empty = VehicleData(vin="VIN1")
    # the spawn gate is ``key in _DATA_PRESENT_REQUIRED and value is None``
    assert empty.safelock_active is None and empty.charge_power_limitation_reason is None
    got = _parse(_payload(safelock=False, reason="x"))
    assert got.safelock_active is False and got.charge_power_limitation_reason == "x"


def test_entities_are_wired_and_phantom_gated() -> None:
    b = next(x for x in BINARY_DESCRIPTIONS if x.key == "safelock_active")
    assert b.data_key == "safelock_active"
    assert "safelock_active" in BIN_REQUIRED
    s = next(x for x in SENSOR_DESCRIPTIONS if x.key == "charge_power_limitation_reason")
    assert s.data_key == "charge_power_limitation_reason"
    assert "charge_power_limitation_reason" in SENSOR_REQUIRED
