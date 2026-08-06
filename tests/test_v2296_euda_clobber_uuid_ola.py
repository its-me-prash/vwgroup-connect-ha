# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.29.x — three grounded EU-Data-Act / OLA fixes:

1. Empty-ZIP clobber in the MANUAL-REFRESH write path (coordinator
   ``_async_update_data``) — the residual third member of the #702
   ``self.vehicles`` clobber family. A no-data portal result must keep
   last-known-good VISIBLE, not overwrite SoC/odometer with blanks.
2. UUID last-resort fallback for SoC / range / odometer in the EU-Data-Act
   mapper, grounded in openWB's ``vweuda`` catalogue — resolves portal-only
   cars whose value is keyed ONLY by content-UUID, without out-competing a
   real name match.
3. OLA 403 detection keyed on the numeric status, not a substring of
   ``str(exc)`` (which embeds the body + URL) — a non-403 whose body merely
   contains "403" must not be misread as an attestation 403.
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api import seat_cupra as sc
from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.exceptions import APIError
from custom_components.vag_connect.cariad.models import VehicleData

_OLA_URL = "https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/X/status"


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


# ── 2. UUID last-resort fallback (openWB vweuda catalogue) ────────────────────

class TestUuidFallback:
    def test_soc_resolves_by_primary_uuid_when_unnamed(self) -> None:
        # portal-only car: SoC arrives only under its content-UUID.
        d = _map({"ae0294b4-1286-3e98-a818-1485b8d88430": "55"})
        assert d.battery_soc == 55
        assert d.has_battery is True

    def test_soc_resolves_by_fallback_uuid(self) -> None:
        d = _map({"0a18a053-b4b0-3db1-be44-a6c5dba629b1": "42"})
        assert d.battery_soc == 42

    def test_named_soc_still_beats_uuid(self) -> None:
        # a real name match must win — the UUID is strictly last-resort.
        d = _map({
            "soc": "80",
            "ac1108b1-b8cc-3db9-a663-03d387e42223": "55",
        })
        assert d.battery_soc == 80

    def test_odometer_resolves_by_primary_uuid(self) -> None:
        d = _map({"41c0805c-43e5-313e-9dfb-356cb8d20f7c": "12345"})
        assert d.odometer_km == 12345

    def test_range_resolves_by_openwb_primary_uuid(self) -> None:
        d = _map({"153e8c40-4c6c-3c17-a11b-0ecc35d55b81": "300"})
        assert d.range_km == 300

    def test_unknown_uuid_is_inert(self) -> None:
        # a UUID we do not map must not resolve to anything (no crash, no value).
        d = _map({"deadbeef-0000-0000-0000-000000000000": "999"})
        assert d.battery_soc is None
        assert d.odometer_km is None
        assert d.range_km is None

    def test_walker_roundtrip_generic_leaf_keyed_by_uuid(self) -> None:
        # END-TO-END: a portal-only car ships SoC/odo/range as generic-leaf
        # ("value") points carrying ONLY the content-UUID in ``key``. The walker
        # must alias them by UUID (they are now in _MAPPED_UUIDS) so the mapper's
        # UUID last-resort resolves them — the real path, not just the mapper half.
        payload = [
            {"dataFieldName": "value", "value": "55",
             "key": "ae0294b4-1286-3e98-a818-1485b8d88430"},
            {"dataFieldName": "value", "value": "12345",
             "key": "41c0805c-43e5-313e-9dfb-356cb8d20f7c"},
            {"dataFieldName": "value", "value": "300",
             "key": "153e8c40-4c6c-3c17-a11b-0ecc35d55b81"},
        ]
        fields = _walk_fields(payload)
        d = map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))
        assert d.battery_soc == 55
        assert d.odometer_km == 12345
        assert d.range_km == 300


# ── 3. OLA 403: status-keyed, not substring-keyed ─────────────────────────────

class TestOla403StatusKeyed:
    def _client(self) -> SeatCupraClient:
        return SeatCupraClient(MagicMock(), "cupra", "u@t.de", "pw")

    def test_non_403_with_403_in_body_is_not_misread(self) -> None:
        client = self._client()
        # a 500 whose body coincidentally carries "403" (e.g. a trace id).
        exc = APIError(500, _OLA_URL, '{"traceId":"abc403def","error":"outage"}')
        with patch.object(CariadBaseClient, "_request", new=AsyncMock(side_effect=exc)):
            with pytest.raises(APIError) as ei:
                asyncio.run(client._request("GET", _OLA_URL))
            # propagates unchanged — not swallowed into the 403 fallback path.
            assert ei.value.status == 500
        # and it was NOT counted toward the attestation-lockdown threshold.
        assert client._ola_consecutive_403 == 0
        assert client.ola_headers_repair_needed is False

    def test_real_403_still_counts(self) -> None:
        client = self._client()
        exc = APIError(403, _OLA_URL, '{"message":"Forbidden device detected"}')
        with (
            patch.object(CariadBaseClient, "_request", new=AsyncMock(side_effect=exc)),
            patch.object(sc, "get_fallback_count", return_value=0),
        ):
            with pytest.raises(APIError):
                asyncio.run(client._request("GET", _OLA_URL))
        # a genuine 403 is still intercepted + counted (fix didn't break it).
        assert client._ola_consecutive_403 == 1


# ── 1. Empty-ZIP clobber in the manual-refresh write path ─────────────────────

class TestManualRefreshNoDataKeepsLastGood:
    def _coord(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord._vehicles_lock = threading.Lock()
        coord._was_available = True
        coord._started = True
        coord._cariad_client = MagicMock()
        coord._persist_website_cookies = MagicMock()
        coord._persist_supplementary_cookies = MagicMock()
        coord._persist_companion_rate_limit = MagicMock()
        coord.vehicles = {"VIN1": {"battery_soc": 80, "odometer_km": 12345}}
        return coord

    def test_no_data_refresh_keeps_last_good(self) -> None:
        coord = self._coord()
        # an empty/failed portal ZIP -> a bare no_data VehicleData.
        empty = VehicleData(vin="VIN1", no_data=True)
        coord._cariad_client.get_status = AsyncMock(return_value=empty)
        result = asyncio.run(coord._async_update_data())
        # last-known-good MUST survive — this is the #702 clobber the fix closes.
        assert coord.vehicles["VIN1"]["battery_soc"] == 80
        assert coord.vehicles["VIN1"]["odometer_km"] == 12345
        assert result["VIN1"]["battery_soc"] == 80
