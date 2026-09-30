# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1628 (ekirchma) — a car removed from the account was polled forever.

The vehicle set is only enumerated at setup and the cache was never reconciled
against the live account, so a deleted car kept 404-spamming the error log.
``_prune_absent_vehicles`` drops any cached VIN no longer on the account (and its
per-VIN sidecar state); the setup path only ever calls it with an authoritative,
non-empty ``get_vehicles()`` result, so a partial/failed enumeration never drops
a real car.
"""
from __future__ import annotations

import threading

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord() -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._vehicles_lock = threading.Lock()  # type: ignore[attr-defined]
    c.vehicles = {}  # type: ignore[attr-defined]
    c.vehicle_failure_count = {}  # type: ignore[attr-defined]
    c.vehicle_last_good_at = {}  # type: ignore[attr-defined]
    c._optimistic_hold = {}  # type: ignore[attr-defined]
    c._data_act_kickoff_error = {}  # type: ignore[attr-defined]
    c._capabilities_fetched_at = {}  # type: ignore[attr-defined]
    return c


def test_prunes_vin_no_longer_on_account() -> None:
    c = _coord()
    c.vehicles = {"WVWKEEP0000000001": {}, "WVWGONE0000000002": {}, "_meta": {}}
    c.vehicle_failure_count = {"WVWGONE0000000002": 3, "WVWKEEP0000000001": 0}
    c.vehicle_last_good_at = {"WVWGONE0000000002": object()}
    c._data_act_kickoff_error = {"WVWGONE0000000002": "HTTP 404"}
    c._prune_absent_vehicles({"WVWKEEP0000000001"}, "volkswagen")
    assert set(c.vehicles) == {"WVWKEEP0000000001", "_meta"}
    assert "WVWGONE0000000002" not in c.vehicle_failure_count
    assert "WVWGONE0000000002" not in c.vehicle_last_good_at
    assert "WVWGONE0000000002" not in c._data_act_kickoff_error
    assert c.vehicle_failure_count == {"WVWKEEP0000000001": 0}


def test_keeps_all_when_every_vin_present() -> None:
    c = _coord()
    c.vehicles = {"A": {}, "B": {}}
    c._prune_absent_vehicles({"A", "B"}, "volkswagen")
    assert set(c.vehicles) == {"A", "B"}


def test_underscore_bookkeeping_keys_are_never_pruned() -> None:
    c = _coord()
    c.vehicles = {"_meta": {}, "A": {}}
    # even an account set that omits "_meta" must not drop it
    c._prune_absent_vehicles({"A"}, "volkswagen")
    assert "_meta" in c.vehicles
    assert "A" in c.vehicles


def test_noop_leaves_everything() -> None:
    c = _coord()
    c.vehicles = {"A": {}}
    c.vehicle_failure_count = {"A": 5}
    c._prune_absent_vehicles({"A"}, "volkswagen")
    assert c.vehicles == {"A": {}}
    assert c.vehicle_failure_count == {"A": 5}
