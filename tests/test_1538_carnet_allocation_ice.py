# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1538 — VW's relations response classifies the drivetrain via
``carnetAllocationType`` (e.g. ``CARNET_ENROLLMENT_APPLICATION:ICE`` on a Golf
GTD). When the telemetry feed is empty (EU-Data-Act no_content, authproxy status
without a fuel/range block) the engine-type inference leaves has_combustion=False
even though VW explicitly says the car is ICE. The allocation type is applied as
an ADDITIVE drivetrain hint — only ever setting a flag True, never forcing False
(so it can't re-introduce a phantom flag, cf. #1316).
"""
from __future__ import annotations


def _client(alloc: str | None):
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    c = VWEUClient.__new__(VWEUClient)
    c._vehicle_metadata = {"VINX": {"allocation_type": alloc}}
    return c


def _parse(alloc: str | None):
    return _client(alloc)._parse_status("VINX", raw={}, parking={})


def test_ice_allocation_sets_has_combustion() -> None:
    d = _parse("CARNET_ENROLLMENT_APPLICATION:ICE")
    assert d.has_combustion is True
    assert d.has_battery is not True
    assert d.is_hybrid is False
    assert d.is_electric is False


def test_bev_allocation_sets_has_battery() -> None:
    d = _parse("CARNET_ENROLLMENT_APPLICATION:BEV")
    assert d.has_battery is True
    assert d.has_combustion is not True
    assert d.is_electric is True


def test_hybrid_allocation_sets_both() -> None:
    d = _parse("CARNET_ENROLLMENT_APPLICATION:HYBRID")
    assert d.has_battery is True
    assert d.has_combustion is True
    assert d.is_hybrid is True


def test_no_allocation_is_noop_no_phantom() -> None:
    d = _parse(None)
    assert d.has_combustion is not True
    assert d.has_battery is not True


def test_unknown_allocation_type_is_noop() -> None:
    # A value with no recognised type suffix must not set any flag.
    d = _parse("CARNET_ENROLLMENT_APPLICATION")
    assert d.has_combustion is not True
    assert d.has_battery is not True


def test_type_matched_case_insensitively_after_last_colon() -> None:
    assert _parse("something:ice").has_combustion is True
