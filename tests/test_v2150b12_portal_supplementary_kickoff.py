# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b12 — make the EU Data Act portal SUPPLEMENTARY actually deliver reads.

Root cause (verified): on a non-portal primary (e.g. MBB for commands), the
Custom Data Request kickoff was gated to a portal-PRIMARY strategy, so the
supplementary portal returned no_request → zero reads, and the "no data"
notice only checked the PRIMARY portal → silent failure. These pin both fixes.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_SCRAPER = "custom_components.vag_connect.cariad.auth._data_act_scraper.DataActScraper"
_SESS = "homeassistant.helpers.aiohttp_client.async_get_clientsession"
_VIN = "WVWZZZAUZFW805377"


def _kickoff_stub(*, strategy: str, supp_portal: bool, auto: bool = True) -> Any:
    stub = type("S", (), {})()
    stub.entry = MagicMock()
    stub.entry.options = {
        "eu_data_act_auto_kickoff": auto,
        "data_act_identifiers": {},
    }
    stub.entry.data = {
        "brand": "volkswagen",
        "supplementary_eu_portal": supp_portal,
        "eu_data_act_auto_kickoff": auto,
    }
    client = MagicMock()
    client._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i", strategy=strategy,
    )
    stub._cariad_client = client
    stub.vehicles = {_VIN: {}}
    stub.hass = MagicMock()
    return stub


def test_kickoff_runs_for_supplementary_portal_on_mbb() -> None:
    # the fix: MBB primary + portal supplementary → kickoff must run.
    stub = _kickoff_stub(strategy="mbb", supp_portal=True)
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=None)
    scraper.kickoff_custom_data_request = AsyncMock(return_value="NEWID")
    with patch(_SCRAPER, return_value=scraper), patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(stub)
        )
    scraper.kickoff_custom_data_request.assert_awaited_once()


def test_kickoff_still_skipped_for_mbb_without_supplementary() -> None:
    # regression guard: a plain MBB entry (no portal) must NOT kick off.
    stub = _kickoff_stub(strategy="mbb", supp_portal=False)
    with patch(_SCRAPER) as ctor, patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(stub)
        )
    ctor.assert_not_called()  # gate returned before building the scraper


def test_kickoff_still_runs_for_portal_primary() -> None:
    # regression guard: portal-primary path unchanged.
    stub = _kickoff_stub(strategy="data_act_portal", supp_portal=False)
    scraper = MagicMock()
    scraper.get_active_custom_request_identifier = AsyncMock(return_value=None)
    scraper.kickoff_custom_data_request = AsyncMock(return_value="ID")
    with patch(_SCRAPER, return_value=scraper), patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(stub)
        )
    scraper.kickoff_custom_data_request.assert_awaited_once()


def test_kickoff_opt_in_still_required() -> None:
    # auto_kickoff off → no kickoff even with a supplementary portal.
    stub = _kickoff_stub(strategy="mbb", supp_portal=True, auto=False)
    with patch(_SCRAPER) as ctor, patch(_SESS, return_value=MagicMock()):
        asyncio.run(
            VagConnectCoordinator._ensure_data_act_custom_request_kickoff(stub)
        )
    ctor.assert_not_called()


# ── Fix B: the no-data notice surfaces for the SUPPLEMENTARY portal ──────────

def _norepair_stub(*, primary: Any, supp: Any) -> Any:
    stub = type("S", (), {})()
    stub.entry = MagicMock()
    stub.entry.entry_id = "E1"
    stub.entry.data = {"brand": "volkswagen"}
    client = MagicMock()
    client._eu_portal = primary
    client._supplementary_eu_portal = supp
    stub._cariad_client = client
    stub.hass = MagicMock()
    return stub


def test_no_data_repair_surfaces_supplementary_reason() -> None:
    supp = MagicMock()
    supp.last_no_data_reason = "no_request"
    stub = _norepair_stub(primary=None, supp=supp)
    with patch("homeassistant.helpers.issue_registry.async_create_issue") as create, \
         patch("homeassistant.helpers.issue_registry.async_delete_issue"):
        VagConnectCoordinator._update_data_act_no_data_repair(stub)
    create.assert_called_once()  # supplementary no_request now surfaced


def test_no_data_repair_clears_when_data_flows() -> None:
    supp = MagicMock()
    supp.last_no_data_reason = ""  # data arrived
    stub = _norepair_stub(primary=None, supp=supp)
    with patch("homeassistant.helpers.issue_registry.async_create_issue") as create, \
         patch("homeassistant.helpers.issue_registry.async_delete_issue") as delete:
        VagConnectCoordinator._update_data_act_no_data_repair(stub)
    create.assert_not_called()
    delete.assert_called_once()
