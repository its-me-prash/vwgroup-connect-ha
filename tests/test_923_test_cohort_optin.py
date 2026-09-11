# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 — opt-in test cohort: the experimental vw.de parkingposition probe and its
share-request Repair run ONLY for users who ticked the cohort option, and the flag
is read the trap-safe way (entry.data, never entry.options).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


# ── v4.7.9 (#584/#923): the flag must reach the MBB command connector ────────

def test_cohort_reaches_mbb_command_connector_and_probes_no_legacy_cars() -> None:
    coord, _conn = _coord(data={CONF_TEST_COHORT: True}, options={})
    probe = AsyncMock()
    cmd = SimpleNamespace(
        _test_cohort=False,
        mbb_no_legacy_vins={"WVWZZZ0000000001", "WVWZZZ0000000000"},
        _probe_fetched_role_cohort=probe,
    )
    coord._cariad_client._mbb_command = cmd
    with patch(f"{_REPAIRS}.raise_issue_test_cohort_share"), \
         patch(f"{_REPAIRS}.clear_issue_test_cohort_share"):
        asyncio.run(coord._apply_test_cohort())
    assert cmd._test_cohort is True
    # fired once per no-legacy VIN, deterministic order
    assert [c.args[0] for c in probe.await_args_list] == [
        "WVWZZZ0000000000", "WVWZZZ0000000001",
    ]


def test_cohort_off_clears_mbb_flag_and_never_probes() -> None:
    coord, _conn = _coord(data={CONF_TEST_COHORT: False}, options={})
    probe = AsyncMock()
    cmd = SimpleNamespace(
        _test_cohort=True, mbb_no_legacy_vins={"WVWZZZ0000000001"},
        _probe_fetched_role_cohort=probe,
    )
    coord._cariad_client._mbb_command = cmd
    with patch(f"{_REPAIRS}.raise_issue_test_cohort_share"), \
         patch(f"{_REPAIRS}.clear_issue_test_cohort_share"):
        asyncio.run(coord._apply_test_cohort())
    assert cmd._test_cohort is False
    probe.assert_not_awaited()


def test_probe_failure_never_breaks_cohort_apply() -> None:
    coord, _conn = _coord(data={CONF_TEST_COHORT: True}, options={})
    cmd = SimpleNamespace(
        _test_cohort=False, mbb_no_legacy_vins={"WVWZZZ0000000001"},
        _probe_fetched_role_cohort=AsyncMock(side_effect=RuntimeError("net")),
    )
    coord._cariad_client._mbb_fallback = cmd
    with patch(f"{_REPAIRS}.raise_issue_test_cohort_share"), \
         patch(f"{_REPAIRS}.clear_issue_test_cohort_share"):
        asyncio.run(coord._apply_test_cohort())  # must not raise
    assert cmd._test_cohort is True


def test_options_save_reapplies_cohort_live() -> None:
    from custom_components.vag_connect import _async_update_listener
    from custom_components.vag_connect.const import (
        CONF_BRAND, CONF_PASSWORD, CONF_USERNAME,
    )
    coord = SimpleNamespace(
        _apply_test_cohort=AsyncMock(), async_request_refresh=AsyncMock(),
    )
    entry = SimpleNamespace(
        entry_id="e1",
        data={CONF_BRAND: "volkswagen", CONF_USERNAME: "u", CONF_PASSWORD: "p"},
        options={CONF_TEST_COHORT: True},
        runtime_data=coord,
    )
    hass = MagicMock()
    asyncio.run(_async_update_listener(hass, entry))
    coord._apply_test_cohort.assert_awaited_once()      # applied live
    hass.config_entries.async_reload.assert_not_called()  # no reload needed
