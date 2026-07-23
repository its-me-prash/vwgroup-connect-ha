# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MBB command grant pre-check is advisory, not a hard block.

Live evidence (Prash's Golf GTE, 2026-07-23): after re-entering the S-PIN, the
climate/charge/window commands started failing with
``P_START not granted — check the We Connect subscription / that you're the
primary user`` even though the operationList grants those exact ops (proven by
the live self-test). The cached/parsed operationList had briefly dropped the
grants right after the reconfigure.

The grant pre-check must therefore NOT hard-block: on a negative result it force-
refreshes the operationList once, and if still unconfirmed it proceeds to the
op-auth leg — which is the real authority. A genuinely-ungranted op 403s at
leg-1 (rolesrights) WITHOUT burning an S-PIN try (the counter only moves at
leg-3 / security-pin-auth-completed), so attempting is safe.
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad._mbb import parse_mbb_operationlist
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError, VehicleCommandError

VIN = "WVWZZZAUZFW805377"


def _oplist(granted: bool, *, with_service: bool = True):
    perm = "granted" if granted else "denied"
    services = []
    if with_service:
        services.append({
            "serviceId": "rbatterycharge_v1",
            "serviceStatus": {"status": "Enabled"},
            "invocationUrl": {"content":
                "https://msg.audi.de/fs-car/bs/batterycharge/v1/{brand}/{country}/vehicles/{vin}/"},
            "operation": [{"id": "P_START", "permission": perm},
                          {"id": "P_STOP", "permission": "granted"}],
        })
    return parse_mbb_operationlist({"operationList": {
        "vin": VIN, "role": "PRIMARY_USER", "status": "ENABLED",
        "serviceInfo": services}})


def _client(oplist):
    c = VWEUClient.__new__(VWEUClient)
    c._brand = types.SimpleNamespace(name="volkswagen")
    c._spin = "1234"
    c._get_mbb_operationlist = AsyncMock(return_value=oplist)
    c._mbb_country_from_id_token = lambda: "DE"
    # Leg-1 (op-auth) — raise so the flow stops right after the pre-check.
    # Reaching it at all proves we did NOT hard-block on the grant pre-check.
    c._mbb_get = AsyncMock(side_effect=APIError(403, "op-auth", "rolesrights forbidden"))
    return c


class TestGrantAdvisory:
    def test_ungranted_op_proceeds_to_op_auth_and_force_refreshes(self) -> None:
        c = _client(_oplist(granted=False))
        # must NOT raise the "not granted" VehicleCommandError; instead it
        # proceeds to the op-auth leg (which we made raise APIError).
        with pytest.raises(APIError):
            asyncio.run(c._command_mbb_op(VIN, "charge_start"))
        # a fresh operationList was fetched to rule out a stale cache
        assert any(call.kwargs.get("force_refresh")
                   for call in c._get_mbb_operationlist.await_args_list)
        # and we actually reached the authoritative op-auth leg
        c._mbb_get.assert_awaited()

    def test_granted_op_does_not_force_refresh(self) -> None:
        c = _client(_oplist(granted=True))
        with pytest.raises(APIError):  # still stops at the mocked op-auth leg
            asyncio.run(c._command_mbb_op(VIN, "charge_start"))
        # grant confirmed on the first fetch → no force-refresh needed
        assert not any(call.kwargs.get("force_refresh")
                       for call in c._get_mbb_operationlist.await_args_list)

    def test_service_genuinely_absent_still_raises_not_available(self) -> None:
        c = _client(_oplist(granted=False, with_service=False))
        with pytest.raises(VehicleCommandError, match="not available"):
            asyncio.run(c._command_mbb_op(VIN, "charge_start"))
        # never reaches the op-auth leg
        c._mbb_get.assert_not_awaited()
