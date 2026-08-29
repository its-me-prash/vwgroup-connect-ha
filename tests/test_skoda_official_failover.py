# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda official public API as a FAILOVER-ONLY source.

When the primary (unofficial mysmob) Škoda channel HARD-fails, the coordinator's
``_revive_after_hard_failure`` falls back to the official public API — but only
there, never on a healthy poll, because the official API is rate-limited to
20 requests/hour/key. These tests pin both the delegation and, crucially, that
the official channel is NOT wired into the continuous supplementary merge.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.api.skoda_official import SkodaOfficialClient
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _skoda_client() -> SkodaClient:
    c = SkodaClient.__new__(SkodaClient)
    c._session = object()
    c._spin = "1234"
    c._supplementary_authproxy = None
    c._supplementary_eu_portal = None
    c._supplementary_tibber = None
    c._supplementary_official = None
    return c


def test_arm_supplementary_official_creates_and_disarms():
    c = _skoda_client()
    c.arm_supplementary_official("key-abc")
    assert isinstance(c._supplementary_official, SkodaOfficialClient)
    # an empty key disarms it
    c.arm_supplementary_official("")
    assert c._supplementary_official is None


@pytest.mark.asyncio
async def test_official_failover_read_delegates_and_failsoft():
    c = _skoda_client()
    # not armed → None
    assert await c.official_failover_read("V") is None
    # armed → delegates to the official client's get_status
    c._supplementary_official = MagicMock()
    c._supplementary_official.get_status = AsyncMock(
        return_value=VehicleData(vin="V", battery_soc=55)
    )
    d = await c.official_failover_read("V")
    assert d is not None and d.battery_soc == 55
    # any error → None (a failover must never itself sink the poll)
    c._supplementary_official.get_status = AsyncMock(side_effect=RuntimeError("boom"))
    assert await c.official_failover_read("V") is None


def test_official_is_failover_only_never_continuous_merge():
    """The 20/h/key rate limit means the official API must NEVER be a
    continuous-merge supplementary — only a failover. Even when armed, it must
    not appear in supplementary_readers (which is consulted every poll)."""
    c = _skoda_client()
    c.arm_supplementary_official("key")
    names = [name for name, _ in c.supplementary_readers("V")]
    assert "skoda_official" not in names
    assert names == []   # nothing else armed → readers empty (failover stays out)


@pytest.mark.asyncio
async def test_revive_after_hard_failure_falls_over_to_official():
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=[])   # no continuous suppliers
    client.official_failover_read = AsyncMock(
        return_value=VehicleData(vin="V", battery_soc=42)
    )
    coord._cariad_client = client
    d = await coord._revive_after_hard_failure("V")
    assert d is not None and d.battery_soc == 42
    client.official_failover_read.assert_awaited_once_with("V")


@pytest.mark.asyncio
async def test_revive_prefers_supplementary_over_official():
    """A normal read-only supplementary (EU-DA / vw.de) still wins; the official
    API is the last resort, so its budget is only spent when nothing else has
    the car."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=[("eu_data_act", None)])
    client.official_failover_read = AsyncMock(return_value=VehicleData(vin="V", battery_soc=42))
    coord._cariad_client = client
    coord._revive_from_supplementary = AsyncMock(
        return_value=VehicleData(vin="V", battery_soc=90)
    )
    d = await coord._revive_after_hard_failure("V")
    assert d is not None and d.battery_soc == 90        # supplementary won
    client.official_failover_read.assert_not_called()   # official budget untouched


@pytest.mark.asyncio
async def test_no_official_on_other_brands_is_a_noop():
    """A non-Škoda client has no official_failover_read → getattr None → no-op."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock(spec=[])           # no attributes at all
    coord._cariad_client = client
    assert await coord._revive_after_hard_failure("V") is None
