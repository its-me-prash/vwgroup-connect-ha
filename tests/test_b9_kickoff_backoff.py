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


def _run(stub, active_return, kickoff_return="NEWID"):
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=active_return)
    scraper.kickoff_custom_data_request = AsyncMock(return_value=kickoff_return)
    with patch(_SCRAPER, return_value=scraper), patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(stub)
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
