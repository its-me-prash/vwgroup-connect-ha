# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1222 — a dead-upstream primary sign-in must NOT tear down the whole entry.

When VW disables the login that renews the token (2026-08-18), the primary
enumeration fails; if an EU Data Act channel is configured it serves reads
independently of that sign-in, so ``async_setup`` keeps the entry live by
enumerating VINs from the portal instead of raising ``invalid_credentials`` and
taking every entity (incl. the unrelated eu_data_act sensors) down. These pin the
fallback helper + its strict no-op for entries without an EU Data Act channel.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord() -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = MagicMock()
    c._cariad_client._supplementary_eu_portal = None
    c._cariad_client._eu_portal = None
    c._arm_supplementary_channels = AsyncMock()
    return c


def test_fallback_returns_vins_when_portal_enumerates() -> None:
    c = _coord()
    portal = MagicMock()
    portal.list_vehicle_vins = AsyncMock(return_value=["WVWZZZE1ZTP000001",
                                                       "WVWZZZE1ZTP000002"])
    c._cariad_client._supplementary_eu_portal = portal
    vins = asyncio.run(c._enumerate_via_eu_data_act_fallback())
    assert vins == ["WVWZZZE1ZTP000001", "WVWZZZE1ZTP000002"]


def test_fallback_arms_portal_when_not_yet_armed() -> None:
    c = _coord()
    portal = MagicMock()
    portal.list_vehicle_vins = AsyncMock(return_value=["WVWZZZE1ZTP000009"])

    async def _arm() -> None:
        # arming makes the supplementary portal available (what the real
        # _arm_supplementary_channels does)
        c._cariad_client._supplementary_eu_portal = portal

    c._arm_supplementary_channels = AsyncMock(side_effect=_arm)
    vins = asyncio.run(c._enumerate_via_eu_data_act_fallback())
    c._arm_supplementary_channels.assert_awaited_once()
    assert vins == ["WVWZZZE1ZTP000009"]


def test_fallback_empty_without_eu_data_act_channel() -> None:
    # strict no-op: no EU Data Act channel + arming does not produce one → []
    # so the caller keeps the original invalid_credentials behaviour.
    c = _coord()
    vins = asyncio.run(c._enumerate_via_eu_data_act_fallback())
    assert vins == []


def test_fallback_empty_on_enumeration_error() -> None:
    c = _coord()
    portal = MagicMock()
    portal.list_vehicle_vins = AsyncMock(side_effect=RuntimeError("portal down"))
    c._cariad_client._supplementary_eu_portal = portal
    vins = asyncio.run(c._enumerate_via_eu_data_act_fallback())
    assert vins == []


def test_fallback_empty_when_portal_lacks_enumeration() -> None:
    # a portal object without list_vehicle_vins must not be treated as usable
    c = _coord()
    portal = object()  # no list_vehicle_vins attribute
    c._cariad_client._supplementary_eu_portal = portal
    vins = asyncio.run(c._enumerate_via_eu_data_act_fallback())
    assert vins == []
