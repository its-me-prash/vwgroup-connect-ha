# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way source priority (v4.0.0).

When two-way (device_grant CARIAD BFF) is active it is the PRIMARY read, so it
must be authoritative — it wins every field it provides, EU Data Act only fills
the gaps it does not, and EU-DA must never clobber a BFF value with older data.
When two-way FAILS (the BFF read raises), the read-only supplementary channels
(EU-DA / vw.de) must resume immediately instead of the entry freezing on
last-known data. These pin both halves.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import VagConnectCoordinator


# ── merge precedence: BFF (primary) authoritative, EU-DA gap-fills ────────────

def test_bff_primary_wins_euda_fills_gaps() -> None:
    bff = VehicleData(vin="V")
    bff.battery_soc = 80          # fresh two-way value
    bff.charging_state = "charging"
    euda = VehicleData(vin="V")
    euda.battery_soc = 94         # STALE EU-DA value — must NOT win
    euda.odometer_km = 42000      # a field the BFF didn't provide — EU-DA fills it
    merged = merge_channels([("volkswagen", bff), ("eu_data_act", euda)])
    assert merged.battery_soc == 80            # BFF authoritative, not clobbered
    assert merged.charging_state == "charging"
    assert merged.odometer_km == 42000         # EU-DA gap-filled
    assert merged.field_sources["battery_soc"] == "volkswagen"
    assert merged.field_sources["odometer_km"] == "eu_data_act"


def test_euda_never_overwrites_a_provided_bff_field() -> None:
    # Even when EU-DA carries a different (newer-looking) value, the BFF field
    # wins because there is no timestamp/"freshest" comparison in the merge.
    bff = VehicleData(vin="V")
    bff.odometer_km = 1000
    euda = VehicleData(vin="V")
    euda.odometer_km = 2000
    merged = merge_channels([("volkswagen", bff), ("eu_data_act", euda)])
    assert merged.odometer_km == 1000


# ── hard-failure fallback: two-way raises → EU-DA resumes ─────────────────────

def _coord(client):
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._cariad_client = client
    return coord


def test_revive_no_supplementary_readers_returns_none() -> None:
    client = MagicMock(spec=[])  # no supplementary_readers attribute
    assert asyncio.run(_coord(client)._revive_after_hard_failure("V")) is None


def test_revive_empty_supplier_list_returns_none() -> None:
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=[])
    assert asyncio.run(_coord(client)._revive_after_hard_failure("V")) is None


def test_revive_uses_supplementary_when_it_serves_data() -> None:
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=[("eu_data_act", object())])
    coord = _coord(client)
    revived = VehicleData(vin="V")
    revived.battery_soc = 55
    coord._revive_from_supplementary = AsyncMock(return_value=revived)
    out = asyncio.run(coord._revive_after_hard_failure("V"))
    assert out is revived
    coord._revive_from_supplementary.assert_awaited_once()


def test_revive_is_failsoft() -> None:
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=[("eu_data_act", object())])
    coord = _coord(client)
    coord._revive_from_supplementary = AsyncMock(side_effect=RuntimeError("boom"))
    assert asyncio.run(coord._revive_after_hard_failure("V")) is None
