# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#5 (#1431 Lagaff86) — the stale-data repair measures the FRESHEST last_seen_at.

The EU-DA portal ships a fresh block next to a frozen one, so a single poll can
carry the older contested stamp while a newer capture is already recorded. Since
_enrich runs before reconcile, the previous snapshot in self.vehicles still holds
the newer (advance-only) value — the watchdog now measures against the freshest of
the two, so a 166h stamp next to a fresh 3.5h one no longer fires a false repair.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN = "WVWZZZ0000000345"


def _iso(hours_ago: float) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _coord(prev_last_seen_iso: str | None) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.hass.async_add_executor_job = AsyncMock(return_value=None)
    c.entry = MagicMock()
    c.entry.data = {"brand": "volkswagen", "username": "t@t.com", "password": "x", "spin": ""}
    c.entry.entry_id = "entryX"
    c._vehicles_lock = threading.Lock()
    c._cariad_client = MagicMock()
    c._cariad_client._image_data = {}
    c._cariad_client._eu_portal = None          # avoid the portal-health branch
    c._cariad_client._supplementary_eu_portal = None
    c.vehicle_static_info = {}
    c._was_available = True
    c.data = None
    c.vehicles = {}
    if prev_last_seen_iso is not None:
        c.vehicles[VIN] = {"vin": VIN, "last_seen_at": prev_last_seen_iso}
    return c


def _run(prev_iso: str | None, poll_iso: str):
    c = _coord(prev_iso)
    data = {"vin": VIN, "latitude": None, "longitude": None, "last_seen_at": poll_iso}
    with patch("custom_components.vag_connect.repairs.raise_issue_stale_data") as raise_m,          patch("custom_components.vag_connect.repairs.clear_stale_data_issue") as clear_m:
        out = asyncio.run(c._enrich(data))
    return out, raise_m, clear_m


def test_fresh_prev_snapshot_suppresses_false_repair() -> None:
    # this poll carries a 166h-old contested stamp; the recorded snapshot is 3.5h
    out, raise_m, clear_m = _run(prev_iso=_iso(3.5), poll_iso=_iso(166))
    raise_m.assert_not_called()
    clear_m.assert_called_once()
    assert out["data_stale"] is False


def test_both_old_still_flags_genuine_stale() -> None:
    # recorded snapshot AND this poll are both frozen (>72h) → genuine stale
    out, raise_m, clear_m = _run(prev_iso=_iso(166), poll_iso=_iso(166))
    raise_m.assert_called_once()
    clear_m.assert_not_called()
    assert out["data_stale"] is True


def test_no_prev_snapshot_uses_this_poll() -> None:
    # first poll, no recorded snapshot: fresh poll → no repair
    out, raise_m, clear_m = _run(prev_iso=None, poll_iso=_iso(2))
    raise_m.assert_not_called()
    clear_m.assert_called_once()
    assert out["data_stale"] is False
