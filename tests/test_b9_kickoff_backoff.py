# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1273 (steemandavid) — EU-DA kickoff re-POST backoff.

The anonymous-AEM active-request probe false-negatives, and the portal 500s on a
2nd active Custom Data Request per VIN, so a blind re-POST storms on every restart.
When a cached Identifier was re-verified within KICKOFF_REVERIFY_S the kickoff must
be SKIPPED; past that window it re-verifies once. The attempt timestamp is persisted
so the backoff survives a restart.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_SCRAPER = "custom_components.vag_connect.cariad.auth._data_act_scraper.DataActScraper"
_SESS = "homeassistant.helpers.aiohttp_client.async_get_clientsession"
_VIN = "WVWZZZAUZFW805377"


def _stub(identifiers: dict, kickoff_ts: dict) -> Any:
    stub = type("S", (), {})()
    stub._active_vins = lambda vins: vins  # #1434 pass-through (no disabled-filtering here)
    stub._data_act_kickoff_error = {}  # #1439
    stub.entry = MagicMock()
    stub.entry.options = {
        "eu_data_act_auto_kickoff": True,
        "data_act_identifiers": dict(identifiers),
        "data_act_kickoff_ts": dict(kickoff_ts),
    }
    stub.entry.data = {"brand": "volkswagen", "eu_data_act_auto_kickoff": True}
    client = MagicMock()
    client._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i", strategy="data_act_portal",
    )
    stub._cariad_client = client
    stub.vehicles = {_VIN: {}}
    stub.hass = MagicMock()
    return stub


def _run(stub, active_return, kickoff_return="NEWID", *, force: bool = False):
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=active_return)
    scraper.kickoff_custom_data_request = AsyncMock(return_value=kickoff_return)
    with patch(_SCRAPER, return_value=scraper), patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(
                stub, force=force,
            )
        )
    return scraper


def _iso(**kw) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(**kw)).isoformat()


def test_skips_repost_when_cached_and_recently_verified() -> None:
    # the storm-stopper: cached id + a probe false-negative + recent stamp → no POST.
    stub = _stub({_VIN: "CACHEDID"}, {_VIN: _iso(hours=1)})
    scraper = _run(stub, active_return=None)
    scraper.kickoff_custom_data_request.assert_not_awaited()
    # nothing changed → no entry write
    stub.hass.config_entries.async_update_entry.assert_not_called()


def test_reverifies_when_cached_stamp_is_stale() -> None:
    # past the 24h window, a false-negative probe must re-POST once.
    stub = _stub({_VIN: "CACHEDID"}, {_VIN: _iso(hours=30)})
    scraper = _run(stub, active_return=None)
    scraper.kickoff_custom_data_request.assert_awaited_once()


def test_posts_and_stamps_when_no_cached_request() -> None:
    stub = _stub({}, {})
    scraper = _run(stub, active_return=None)
    scraper.kickoff_custom_data_request.assert_awaited_once()
    # the attempt is persisted (stamp + identifier) so the backoff survives a restart
    stub.hass.config_entries.async_update_entry.assert_called_once()
    opts = stub.hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert opts["data_act_identifiers"][_VIN] == "NEWID"
    assert _VIN in opts["data_act_kickoff_ts"]


def test_adopting_an_active_request_still_works() -> None:
    # unchanged behaviour: a live active id is adopted (no POST needed).
    stub = _stub({}, {})
    scraper = _run(stub, active_return="LIVEID")
    scraper.kickoff_custom_data_request.assert_not_awaited()
    opts = stub.hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert opts["data_act_identifiers"][_VIN] == "LIVEID"


# ── #1412 (chrisbamtam) — backoff also applies with NO cached Identifier ─────────
#
# A portal that refuses the request for an account-state reason (400-0011,
# "primary user relation is missing tag EUDA_SCOPED") never yields an Identifier,
# so the cached branch above never ran and the POST repeated on every setup,
# reload and 6-hourly runtime retry — twice per pass, once per duration.


def test_no_identifier_recent_attempt_backs_off() -> None:
    """Attempted recently, still no Identifier → no POST this cycle."""
    stub = _stub({}, {_VIN: _iso(hours=1)})
    scraper = _run(stub, active_return=None)
    scraper.kickoff_custom_data_request.assert_not_awaited()


def test_no_identifier_stale_attempt_retries() -> None:
    """Past the re-verify window the POST is attempted again."""
    stub = _stub({}, {_VIN: _iso(hours=30)})
    scraper = _run(stub, active_return=None)
    scraper.kickoff_custom_data_request.assert_awaited_once()


def test_no_identifier_first_ever_attempt_posts() -> None:
    """No stamp at all (fresh setup) → unchanged first-time behaviour."""
    stub = _stub({}, {})
    scraper = _run(stub, active_return=None)
    scraper.kickoff_custom_data_request.assert_awaited_once()


def test_manual_button_bypasses_the_backoff() -> None:
    """force=True is the user saying "I fixed it on VW's side, try now"."""
    stub = _stub({}, {_VIN: _iso(hours=1)})
    scraper = _run(stub, active_return=None, force=True)
    scraper.kickoff_custom_data_request.assert_awaited_once()
