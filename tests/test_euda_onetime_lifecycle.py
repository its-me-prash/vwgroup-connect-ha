# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage-1 EU Data Act — one-time historical export lifecycle safety.

The machinery to request + import a one-time export already existed; this pins
the safety around it: the WEDGE-GUARD (#923 @naked-head, field-corrected — refuse
only while OUR OWN one-time export is still pending; a one-time submits fine
alongside the active 15-min feed, which keeps publishing), the KILL-SWITCH, and
the client-side DEADLINE (the portal gives the request no terminal state, so a
stuck one is timed out instead of pending forever).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.exceptions import ServiceValidationError

from custom_components.vag_connect.coordinator import VagConnectCoordinator

_VIN = "WVWZZZTESTVHN0001"
_MOD = "custom_components.vag_connect.coordinator"


def _coord(entry_data: dict | None = None) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.data = {"brand": "volkswagen", **(entry_data or {})}
    c.entry.entry_id = "e1"
    c._historical_export_state = None  # force a fresh load from entry.data
    return c


def _patch_scraper(active_id, kickoff_ok=True):
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=active_id)
    scraper.kickoff_historical_export = AsyncMock(return_value=kickoff_ok)
    return patch(
        "custom_components.vag_connect.cariad.auth._data_act_scraper.DataActScraper",
        return_value=scraper,
    ), scraper


@pytest.mark.asyncio
async def test_kill_switch_refuses_and_never_touches_the_portal():
    c = _coord()
    with patch(f"{_MOD}.ONETIME_EXPORT_DISABLED", True, create=True):
        # patched on const; the method imports it locally, so patch there too
        with patch("custom_components.vag_connect.const.ONETIME_EXPORT_DISABLED", True):
            with pytest.raises(ServiceValidationError):
                await c.async_request_historical_export(_VIN)


@pytest.mark.asyncio
async def test_one_time_export_allowed_while_continuous_feed_active():
    # #923 (@naked-head, field-corrected) — the portal allows a one-time export
    # ALONGSIDE the active 15-min continuous feed, and the feed keeps publishing.
    # The old guard checked the continuous request's identifier (active for
    # essentially everyone via auto-kickoff) and refused every attempt, making the
    # button unreachable. An active continuous request must NOT block it.
    c = _coord()
    p, scraper = _patch_scraper(active_id="an-active-15min-identifier", kickoff_ok=True)
    with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()), p:
        ok = await c.async_request_historical_export(_VIN)
    assert ok is True
    scraper.kickoff_historical_export.assert_awaited_once()
    assert c.historical_export_state(_VIN) == "pending"


@pytest.mark.asyncio
async def test_wedge_guard_refuses_only_while_our_own_export_is_pending():
    # Refuse to avoid double-submitting while OUR OWN one-time export is in flight;
    # a genuine duplicate is the portal's to reject.
    c = _coord()
    c._historical_export_state = {_VIN: {"state": "pending", "submitted_at": "x"}}
    p, scraper = _patch_scraper(active_id=None, kickoff_ok=True)
    with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()), p:
        with pytest.raises(ServiceValidationError):
            await c.async_request_historical_export(_VIN)
    scraper.kickoff_historical_export.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_continuous_request_kicks_off_and_records_pending():
    c = _coord()
    p, scraper = _patch_scraper(active_id=None, kickoff_ok=True)
    with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()), p:
        ok = await c.async_request_historical_export(_VIN)
    assert ok is True
    scraper.kickoff_historical_export.assert_awaited_once()
    assert c.historical_export_state(_VIN) == "pending"


@pytest.mark.asyncio
async def test_advance_times_out_a_stuck_export_and_clears_pending():
    c = _coord()
    # a pending export submitted 74h ago (past the 72h client deadline)
    old = (datetime.now(tz=timezone.utc) - timedelta(hours=74)).isoformat()
    c._historical_export_state = {_VIN: {"state": "pending", "submitted_at": old}}
    c.async_import_historical_export = AsyncMock()  # must NOT be called past deadline
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_historical_timeout",
        MagicMock(),
    ) as raise_repair:
        await c._advance_historical_exports()
    raise_repair.assert_called_once()
    assert c.historical_export_state(_VIN) == "timed_out"
    c.async_import_historical_export.assert_not_awaited()


@pytest.mark.asyncio
async def test_advance_imports_a_ready_export_to_done():
    c = _coord()
    fresh = datetime.now(tz=timezone.utc).isoformat()
    c._historical_export_state = {_VIN: {"state": "pending", "submitted_at": fresh}}
    c.async_import_historical_export = AsyncMock(return_value=True)
    await c._advance_historical_exports()
    assert c.historical_export_state(_VIN) == "done"
    c.async_import_historical_export.assert_awaited_once_with(_VIN)


@pytest.mark.asyncio
async def test_advance_noop_without_any_pending_export():
    c = _coord()
    c._historical_export_state = {_VIN: {"state": "done", "submitted_at": "x"}}
    c.async_import_historical_export = AsyncMock()
    await c._advance_historical_exports()
    c.async_import_historical_export.assert_not_awaited()


def test_state_helper_defaults_to_idle():
    assert _coord().historical_export_state("UNKNOWN") == "idle"
