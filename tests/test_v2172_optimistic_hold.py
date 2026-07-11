# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.2 — optimistic-command hold across polls (#666, torstentosh).

After a lock/climate/charge command the UI flips optimistically, but the very
next poll used to overwrite it with VW's still-pre-command state, so the toggle
snapped back until a manual refresh. The hold keeps the optimistic value until
the backend confirms it or a window elapses.
"""
from __future__ import annotations

import threading
from unittest.mock import patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _stub():
    s = type("S", (), {})()
    s.vehicles = {}
    s._vehicles_lock = threading.Lock()
    s._optimistic_hold = {}
    s.async_set_updated_data = lambda *a, **k: None
    return s


def test_hold_keeps_optimistic_value_when_poll_is_stale():
    s = _stub()
    s.vehicles["VIN"] = {"doors_locked": False}
    VagConnectCoordinator._optimistic_set(s, "VIN", {"doors_locked": True})
    # next poll still reports the pre-command state
    fresh = VagConnectCoordinator._apply_optimistic_hold(
        s, "VIN", {"doors_locked": False, "range_km": 200}
    )
    assert fresh["doors_locked"] is True   # held, not snapped back
    assert fresh["range_km"] == 200        # untouched keys flow through
    assert "VIN" in s._optimistic_hold     # still pending


def test_hold_drops_when_backend_confirms():
    s = _stub()
    s.vehicles["VIN"] = {"doors_locked": False}
    VagConnectCoordinator._optimistic_set(s, "VIN", {"doors_locked": True})
    fresh = VagConnectCoordinator._apply_optimistic_hold(
        s, "VIN", {"doors_locked": True}
    )
    assert fresh["doors_locked"] is True
    assert "VIN" not in s._optimistic_hold  # confirmed → hold cleared


def test_hold_expires_and_trusts_backend():
    s = _stub()
    s.vehicles["VIN"] = {"climatisation_active": False}
    with patch("time.monotonic", return_value=1000.0):
        VagConnectCoordinator._optimistic_set(
            s, "VIN", {"climatisation_active": True}
        )
    # past the 150 s window → backend state wins even if it disagrees
    with patch("time.monotonic", return_value=1000.0 + 200):
        fresh = VagConnectCoordinator._apply_optimistic_hold(
            s, "VIN", {"climatisation_active": False}
        )
    assert fresh["climatisation_active"] is False
    assert "VIN" not in s._optimistic_hold


def test_revert_clears_hold():
    s = _stub()
    s.vehicles["VIN"] = {"doors_locked": False}
    prev = VagConnectCoordinator._optimistic_set(s, "VIN", {"doors_locked": True})
    assert "VIN" in s._optimistic_hold
    VagConnectCoordinator._optimistic_revert(s, "VIN", prev)
    assert "VIN" not in s._optimistic_hold  # failed command → no stale hold


def test_apply_is_noop_without_holds():
    s = _stub()
    fresh = {"doors_locked": False}
    out = VagConnectCoordinator._apply_optimistic_hold(s, "VIN", fresh)
    assert out is fresh
    assert out["doors_locked"] is False
