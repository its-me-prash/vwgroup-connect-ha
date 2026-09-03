# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1273 (steemandavid) — cancel_historical_export off-switch.

An accidentally-triggered one-time export otherwise re-attempts its import every
~30 min until the 72h deadline, with no way to stop it. The new service clears the
pending state so the poll loop stops, and clears the paired timeout repair.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock


def _hist_coord(state: dict) -> object:
    import custom_components.vag_connect.coordinator as cm

    c = cm.VagConnectCoordinator.__new__(cm.VagConnectCoordinator)
    c._historical_export_state = dict(state)
    c.hass = MagicMock()
    c.entry = MagicMock(entry_id="e1")
    c.entry.data = {}
    return c


def test_cancel_clears_pending_and_returns_true() -> None:
    c = _hist_coord({"VINX": {"state": "pending", "submitted_at": "2026-09-04T00:00:00Z"}})
    assert asyncio.run(c.async_cancel_historical_export("VINX")) is True
    # the poll loop keys off this state — must be gone so it stops re-attempting
    assert c.historical_export_state("VINX") == "idle"


def test_cancel_returns_false_when_nothing_pending() -> None:
    c = _hist_coord({})
    assert asyncio.run(c.async_cancel_historical_export("VINX")) is False


def test_cancel_leaves_other_vins_untouched() -> None:
    c = _hist_coord({
        "VINX": {"state": "pending", "submitted_at": "2026-09-04T00:00:00Z"},
        "VINY": {"state": "pending", "submitted_at": "2026-09-04T00:00:00Z"},
    })
    assert asyncio.run(c.async_cancel_historical_export("VINX")) is True
    assert c.historical_export_state("VINX") == "idle"
    assert c.historical_export_state("VINY") == "pending"
