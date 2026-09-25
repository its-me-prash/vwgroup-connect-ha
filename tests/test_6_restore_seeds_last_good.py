# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#6 — a restored vehicle snapshot seeds ``vehicle_last_good_at`` from ``saved_at``.

Without it the availability gate in ``entity_base`` (which requires a
last-known-good timestamp) drops every entity to unavailable on the first failed
poll after a restart, even though a valid cached snapshot was loaded. The
snapshot's own ``saved_at`` is a sound last-known-good proxy.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _coord():
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.vehicle_last_good_at = {}
    return c


def test_seeds_from_valid_saved_at() -> None:
    c = _coord()
    c._seed_last_good_from_snapshot("2026-09-23T06:00:00+00:00", ["VIN_A", "VIN_B"])
    expect = datetime(2026, 9, 23, 6, 0, tzinfo=timezone.utc)
    assert c.vehicle_last_good_at["VIN_A"] == expect
    assert c.vehicle_last_good_at["VIN_B"] == expect


def test_naive_saved_at_gets_utc() -> None:
    c = _coord()
    c._seed_last_good_from_snapshot("2026-09-23T06:00:00", ["VIN_A"])
    assert c.vehicle_last_good_at["VIN_A"].tzinfo is not None


def test_does_not_overwrite_live_value() -> None:
    c = _coord()
    live = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    c.vehicle_last_good_at = {"VIN_A": live}
    c._seed_last_good_from_snapshot("2026-09-23T06:00:00+00:00", ["VIN_A"])
    assert c.vehicle_last_good_at["VIN_A"] == live  # setdefault, not overwritten


def test_malformed_saved_at_is_noop() -> None:
    c = _coord()
    c._seed_last_good_from_snapshot("not-a-date", ["VIN_A"])
    assert "VIN_A" not in c.vehicle_last_good_at


def test_none_saved_at_is_noop() -> None:
    c = _coord()
    c._seed_last_good_from_snapshot(None, ["VIN_A"])
    assert c.vehicle_last_good_at == {}


def test_missing_attr_is_initialised() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._seed_last_good_from_snapshot("2026-09-23T06:00:00+00:00", ["VIN_A"])
    assert c.vehicle_last_good_at["VIN_A"].year == 2026
