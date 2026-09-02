# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1286 (@n3roGit) — the Škoda official-API source mode.

A user can choose how the official manufacturer API interacts with the primary
"mysmob" channel: auto (merge, official preferred) / prefer_official / failover /
official_only (mysmob off, per-VIN degrade) / mysmob_only (official off). The
coordinator reads a single per-entry mode and pushes it onto the Škoda client so
"official_only" reroutes the primary read; the other modes gate the merge /
failover / auto-enrol coordinator-side.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.const import SKODA_OFFICIAL_MODES
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord(options: dict | None = None, data: dict | None = None) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = SimpleNamespace(options=options or {}, data=data or {})  # type: ignore[attr-defined]
    return c


def test_all_five_modes_are_declared():
    assert SKODA_OFFICIAL_MODES == (
        "auto", "prefer_official", "failover", "official_only", "mysmob_only",
    )


def test_mode_defaults_to_auto():
    assert _coord()._skoda_official_mode() == "auto"


def test_mode_reads_from_entry_data():
    assert _coord(data={"skoda_official_mode": "failover"})._skoda_official_mode() == "failover"


def test_mode_options_win_over_data():
    # options-then-data precedence (the entry.options-trap safe read)
    c = _coord(
        options={"skoda_official_mode": "official_only"},
        data={"skoda_official_mode": "auto"},
    )
    assert c._skoda_official_mode() == "official_only"


def test_unknown_mode_falls_back_to_auto():
    assert _coord(data={"skoda_official_mode": "bogus"})._skoda_official_mode() == "auto"


def test_push_official_mode_sets_client_attribute():
    c = _coord(data={"skoda_official_mode": "official_only"})
    client = MagicMock()
    c._cariad_client = client  # type: ignore[attr-defined]
    c._push_official_mode()
    client.set_official_mode.assert_called_once_with("official_only")


def test_push_official_mode_is_a_noop_for_non_skoda_clients():
    # a client with no set_official_mode (getattr → None) must never raise
    c = _coord()
    c._cariad_client = SimpleNamespace()  # type: ignore[attr-defined]
    c._push_official_mode()  # no exception


def test_push_official_mode_accepts_an_explicit_client():
    # the #584 captured-client path passes the client explicitly
    c = _coord(data={"skoda_official_mode": "prefer_official"})
    c._cariad_client = None  # type: ignore[attr-defined]
    captured = MagicMock()
    c._push_official_mode(captured)
    captured.set_official_mode.assert_called_once_with("prefer_official")


def test_set_official_mode_stores_on_client():
    client = SkodaClient.__new__(SkodaClient)
    client.set_official_mode("official_only")
    assert client._official_mode == "official_only"
    client.set_official_mode("")  # empty → auto
    assert client._official_mode == "auto"


@pytest.mark.asyncio
async def test_official_only_routes_get_status_to_the_official_api():
    client = SkodaClient.__new__(SkodaClient)
    client._eu_portal = None
    client._official_mode = "official_only"
    off = VehicleData(vin="V", battery_soc=55)
    client._official_read_rate_safe = AsyncMock(return_value=off)  # type: ignore[method-assign]
    result = await client.get_status("V")
    assert result is off  # served straight from the official API, no mysmob read
    client._official_read_rate_safe.assert_awaited_once_with("V")


@pytest.mark.asyncio
async def test_official_only_degrades_to_mysmob_when_no_official_read():
    # per-VIN degrade: no official key / rate-limited → official read is None, so
    # get_status must NOT return early — it falls through to the mysmob path. We
    # prove the fall-through by leaving the mysmob internals unset so the very next
    # access (self._val) raises AttributeError rather than returning None early.
    client = SkodaClient.__new__(SkodaClient)
    client._eu_portal = None
    client._official_mode = "official_only"
    client._official_read_rate_safe = AsyncMock(return_value=None)  # type: ignore[method-assign]
    with pytest.raises(AttributeError):
        await client.get_status("V")
    client._official_read_rate_safe.assert_awaited_once_with("V")
