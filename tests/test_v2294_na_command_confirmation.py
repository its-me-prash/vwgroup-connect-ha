# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.29.x (#659) — VW NA command completion poll.

Found while digging the current myVW APK for remote-start: a con-veh command
2xx-accepts, then runs asynchronously, and the app confirms the real outcome by
polling ``/history/v1/vehicle/{id}/correlationId/{cid}/ro/``. Without that, a
command the car quietly REJECTS still looks successful. We now poll to a terminal
outcome and raise ONLY on an explicit rejected/failed; everything else (no
correlationId, no carnet, a poll error, an unknown shape, a timeout) stays
optimistic, so it is never worse than the old fire-and-forget accept.

Outcome enum (sstur/vwapp live-verified): 0 REJECTED / 1 QUEUED / 2 SUCCESS /
3 FAILED.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api import vw_na
from custom_components.vag_connect.cariad.api.vw_na import (
    VWNAClient,
    _na_command_outcome,
    _na_correlation_id,
)
from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    VehicleCommandError,
)

pytestmark = pytest.mark.ha_required

_VIN = "WVWZZZ1KZAW000659"
_UUID = "uuid-659"


# ── pure helpers ────────────────────────────────────────────────────────────


class TestCorrelationId:
    def test_top_level(self):
        assert _na_correlation_id({"correlationId": "abc123"}) == "abc123"

    def test_data_envelope(self):
        assert _na_correlation_id({"data": {"correlationId": "xy"}}) == "xy"

    def test_alt_keys(self):
        assert _na_correlation_id({"requestId": "r1"}) == "r1"

    def test_absent(self):
        assert _na_correlation_id({"foo": "bar"}) is None
        assert _na_correlation_id("nope") is None


class TestOutcome:
    def test_responsebody_eventstatus(self):
        h = {"responseBody": {"eventStatus": {"responseOutcome": 2}}}
        assert _na_command_outcome(h) == 2

    def test_data_envelope(self):
        h = {"data": {"eventStatus": {"responseOutcome": 0}}}
        assert _na_command_outcome(h) == 0

    def test_string_int_coerced(self):
        h = {"eventStatus": {"responseOutcome": "3"}}
        assert _na_command_outcome(h) == 3

    def test_bool_is_not_outcome(self):
        h = {"eventStatus": {"responseOutcome": True}}
        assert _na_command_outcome(h) is None

    def test_absent_or_nonterminal(self):
        assert _na_command_outcome({"eventStatus": {}}) is None
        assert _na_command_outcome({}) is None
        assert _na_command_outcome("x") is None


# ── _confirm_na_command behaviour ───────────────────────────────────────────


def _client() -> VWNAClient:
    c = VWNAClient.__new__(VWNAClient)
    c._base = "https://example.test"
    c._vin_to_uuid = {_VIN: _UUID}
    c._read_session_tokens = {}
    c._get_read_session_token = AsyncMock(return_value="carnet-tok")  # type: ignore[method-assign]
    return c


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(vw_na, "_NA_CONFIRM_SLEEP_S", 0)


class TestConfirm:
    @pytest.mark.asyncio
    async def test_no_correlation_id_no_poll(self):
        c = _client()
        c._read = AsyncMock()  # type: ignore[method-assign]
        await c._confirm_na_command(_VIN, {"status": "accepted"})
        c._read.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejected_raises(self):
        c = _client()
        c._read = AsyncMock(  # type: ignore[method-assign]
            return_value={"responseBody": {"eventStatus": {"responseOutcome": 0}}}
        )
        with pytest.raises(VehicleCommandError):
            await c._confirm_na_command(_VIN, {"correlationId": "cid1"})

    @pytest.mark.asyncio
    async def test_failed_raises(self):
        c = _client()
        c._read = AsyncMock(  # type: ignore[method-assign]
            return_value={"eventStatus": {"responseOutcome": 3}}
        )
        with pytest.raises(VehicleCommandError):
            await c._confirm_na_command(_VIN, {"correlationId": "cid1"})

    @pytest.mark.asyncio
    async def test_success_returns(self):
        c = _client()
        c._read = AsyncMock(  # type: ignore[method-assign]
            return_value={"eventStatus": {"responseOutcome": 2}}
        )
        await c._confirm_na_command(_VIN, {"correlationId": "cid1"})  # no raise

    @pytest.mark.asyncio
    async def test_queued_then_success(self):
        c = _client()
        c._read = AsyncMock(side_effect=[  # type: ignore[method-assign]
            {"eventStatus": {"responseOutcome": 1}},   # queued
            {"eventStatus": {"responseOutcome": 2}},   # success
        ])
        await c._confirm_na_command(_VIN, {"correlationId": "cid1"})
        assert c._read.await_count == 2

    @pytest.mark.asyncio
    async def test_poll_error_stays_optimistic(self):
        c = _client()
        c._read = AsyncMock(  # type: ignore[method-assign]
            side_effect=APIError(500, "/x", "boom")
        )
        await c._confirm_na_command(_VIN, {"correlationId": "cid1"})  # no raise

    @pytest.mark.asyncio
    async def test_no_carnet_no_poll(self):
        c = _client()
        c._get_read_session_token = AsyncMock(return_value=None)  # type: ignore[method-assign]
        c._read = AsyncMock()  # type: ignore[method-assign]
        await c._confirm_na_command(_VIN, {"correlationId": "cid1"})
        c._read.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_timeout_queued_stays_optimistic(self):
        c = _client()
        c._read = AsyncMock(  # type: ignore[method-assign]
            return_value={"eventStatus": {"responseOutcome": 1}}  # always queued
        )
        await c._confirm_na_command(_VIN, {"correlationId": "cid1"})  # no raise
        assert c._read.await_count == vw_na._NA_CONFIRM_ATTEMPTS


class TestCarnetCommandIntegration:
    @pytest.mark.asyncio
    async def test_rejected_command_raises_through_carnet_command(self):
        c = _client()
        c._request = AsyncMock(  # type: ignore[method-assign]
            return_value={"correlationId": "cid1"}
        )
        c._read = AsyncMock(  # type: ignore[method-assign]
            return_value={"responseBody": {"eventStatus": {"responseOutcome": 0}}}
        )
        with pytest.raises(VehicleCommandError):
            await c._carnet_command("PUT", "https://example.test/x", _VIN,
                                    json={"lock": True})
