# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.0a10 — failsafe batch.

Two independent fixes from the failsafe audit + a live tester log:

1. PORTAL no-data carry-over flag (#481-residue). A portal timeout/outage makes
   ``get_vehicle_data`` return a *bare* VehicleData. The coordinator used to treat
   that as a successful poll and overwrite SoC/odometer with blanks (+ reset the
   failure counter + stamp last-good). The connector now flags such a poll
   ``no_data=True`` so the coordinator can keep the previous good values visible.
   A brand-new car (no prior data) still falls through and appears.

2. MBB read no-refresh-storm. The MBB operationList/VSR reads are data-plane
   ACL-blocked (401). The default ``_mbb_get`` 401→refresh fired every poll and
   tripped the refresh-storm guard ("pausing to prevent IP ban", seen live). The
   read callers now pass ``_retry=False`` so an ACL 401 never triggers a refresh.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
from custom_components.vag_connect.cariad.exceptions import APIError
from custom_components.vag_connect.cariad.models import VehicleData

_VIN = "WVWZZZAUZFW805377"


def _conn() -> EUDataActConnector:
    return EUDataActConnector(MagicMock(), brand="volkswagen")


class TestPortalNoDataFlag:
    def test_no_data_request_sets_no_data_true(self) -> None:
        """No continuous-data-request yet (metadata carries no identifier) →
        bare VehicleData flagged no_data=True."""
        conn = _conn()
        conn._get_json = AsyncMock(return_value={})  # metadata: no identifier
        d = asyncio.run(conn.get_vehicle_data(_VIN))
        assert d.no_data is True
        assert conn.last_no_data_reason == "no_request"

    def test_empty_listing_sets_no_data_true(self) -> None:
        """Metadata OK but the dataset listing is a transient None (soft 5xx) →
        no_data=True so the coordinator carries last-good forward."""
        conn = _conn()
        conn._get_json = AsyncMock(side_effect=[{"identifier": "abc"}, None])
        d = asyncio.run(conn.get_vehicle_data(_VIN))
        assert d.no_data is True
        assert conn.last_no_data_reason == "empty"

    def test_default_vehicledata_no_data_is_false(self) -> None:
        """Every other channel returns a plain VehicleData → defaults no_data
        False, so the coordinator carry-over branch never fires for them."""
        assert VehicleData(vin="X").no_data is False


def _client() -> VWEUClient:
    client = VWEUClient(MagicMock(), "u@t.de", "pw")
    client._mbb_oplist_cache = {}
    client._mbb_headers = MagicMock(return_value={})
    client._refresh_tokens = AsyncMock()
    return client


def _resp(status: int, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status = status
    r.text = AsyncMock(return_value=text)
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    return r


class TestMbbNoRefreshStorm:
    def test_operationlist_401_does_not_refresh(self) -> None:
        """The actual fix at the read caller: a 401 on the MBB operationList
        read returns None WITHOUT calling _refresh_tokens (no storm)."""
        client = _client()
        client._session.get = MagicMock(return_value=_resp(401, "unauthorized"))
        out = asyncio.run(client._get_mbb_operationlist(_VIN))
        assert out is None
        client._refresh_tokens.assert_not_called()

    def test_mbb_get_no_retry_raises_apierror_without_refresh(self) -> None:
        """_mbb_get(_retry=False) on a 401 raises APIError and never refreshes."""
        client = _client()
        client._session.get = MagicMock(return_value=_resp(401, "nope"))
        with pytest.raises(APIError):
            asyncio.run(client._mbb_get("https://mal/x", _retry=False))
        client._refresh_tokens.assert_not_called()

    def test_mbb_get_default_still_refreshes_once(self) -> None:
        """Regression shield: the storm fix is scoped to read callers passing
        _retry=False — _mbb_get's DEFAULT (used by command paths) still refreshes
        once on a 401 so a genuine expiry recovers."""
        client = _client()
        # both attempts 401 → refresh fires once, retry (_retry=False) re-raises
        client._session.get = MagicMock(side_effect=[_resp(401), _resp(401)])
        with pytest.raises(APIError):
            asyncio.run(client._mbb_get("https://mal/x"))
        assert client._refresh_tokens.await_count == 1
