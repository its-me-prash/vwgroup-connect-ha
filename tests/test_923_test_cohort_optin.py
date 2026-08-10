# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 — opt-in test cohort: the experimental vw.de parkingposition probe and its
share-request Repair run ONLY for users who ticked the cohort option, and the flag
is read the trap-safe way (entry.data, never entry.options).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.const import CONF_TEST_COHORT
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_REPAIRS = "custom_components.vag_connect.repairs"


# ── connector: self-limiting probe gate ─────────────────────────────────────

def _conn(*, cohort: bool, tries: int = 0, available: bool = False):
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c.probe_position = cohort
    c._position_probe_tries = tries
    c._position_available = available
    return c


def test_opted_out_never_probes() -> None:
    assert _conn(cohort=False)._should_probe_position() is False


def test_opted_in_probes_within_budget() -> None:
    assert _conn(cohort=True, tries=0)._should_probe_position() is True
    assert _conn(cohort=True, tries=3)._should_probe_position() is True


def test_self_limits_after_the_budget() -> None:
    """A car whose proxy keeps refusing stops probing — no doomed request forever."""
    max_tries = WebsiteAuthProxyConnector._POSITION_PROBE_MAX_TRIES
    assert _conn(cohort=True, tries=max_tries)._should_probe_position() is False


def test_coordinates_seen_latches_the_read_on() -> None:
    """Once a position came back, keep reading even if the budget is spent — it is
    a real feature at that point, not a probe."""
    assert _conn(cohort=False, tries=99, available=True)._should_probe_position() is True


# ── coordinator: cohort flag → connector + Repair, read from entry.data ─────

def _coord(*, data: dict, options: dict, web: bool = True):
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = SimpleNamespace(entry_id="e1", data=data, options=options)
    conn = SimpleNamespace(probe_position=False) if web else None
    coord._cariad_client = SimpleNamespace(
        _website_proxy=conn, _supplementary_authproxy=None,
    )
    return coord, conn


def test_cohort_on_arms_probe_and_raises_repair() -> None:
    coord, conn = _coord(data={CONF_TEST_COHORT: True}, options={})
    with patch(f"{_REPAIRS}.raise_issue_test_cohort_share") as raise_m, \
         patch(f"{_REPAIRS}.clear_issue_test_cohort_share") as clear_m:
        asyncio.run(coord._apply_test_cohort())
    assert conn.probe_position is True
    raise_m.assert_called_once()
    clear_m.assert_not_called()


def test_cohort_off_clears_probe_and_repair() -> None:
    coord, conn = _coord(data={CONF_TEST_COHORT: False}, options={})
    with patch(f"{_REPAIRS}.raise_issue_test_cohort_share") as raise_m, \
         patch(f"{_REPAIRS}.clear_issue_test_cohort_share") as clear_m:
        asyncio.run(coord._apply_test_cohort())
    assert conn.probe_position is False
    clear_m.assert_called_once()
    raise_m.assert_not_called()


def test_reads_entry_data_not_options_the_trap() -> None:
    """entry.options is folded into entry.data by the listener and is always {} at
    read time — reading options would be dead code (the documented options trap).
    data=False must win even though options=True."""
    coord, conn = _coord(
        data={CONF_TEST_COHORT: False}, options={CONF_TEST_COHORT: True},
    )
    with patch(f"{_REPAIRS}.raise_issue_test_cohort_share") as raise_m, \
         patch(f"{_REPAIRS}.clear_issue_test_cohort_share") as clear_m:
        asyncio.run(coord._apply_test_cohort())
    assert conn.probe_position is False  # data wins, not options
    clear_m.assert_called_once()
    raise_m.assert_not_called()


def test_cohort_on_but_no_web_channel_does_not_nag() -> None:
    """An opted-in user with no vw.de channel has nothing to test → no Repair."""
    coord, _ = _coord(data={CONF_TEST_COHORT: True}, options={}, web=False)
    with patch(f"{_REPAIRS}.raise_issue_test_cohort_share") as raise_m, \
         patch(f"{_REPAIRS}.clear_issue_test_cohort_share") as clear_m:
        asyncio.run(coord._apply_test_cohort())
    raise_m.assert_not_called()
    clear_m.assert_called_once()
