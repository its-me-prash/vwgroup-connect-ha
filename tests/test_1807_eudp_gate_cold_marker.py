# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1807 follow-up — the EU-DP command refusal has to survive a cold marker.

#1807 keeps MBB commands away from a car whose service list came from the EU-DP
host, and it does so at two levels, which was the right instinct: the capability
gate hides the entities, and ``_command_mbb_op`` refuses before anything is sent,
because a service call does not go through the entity gate at all.

The second gate reads ``mbb_eudp_oplist_vins`` near the top of the function, but
the only thing that ever fills that set is ``_get_mbb_operationlist``, which the
same function calls fourteen lines further down. So the gate is correct exactly
when the set is already warm. On a cold marker, which is every fresh start until
the first poll runs ``_refresh_mbb_command_capabilities``, the first service call
walks straight past it, the list arrives, ``mbb_service_base`` resolves a host
from it, and the flow reaches the S-PIN legs. Wrong S-PIN attempts lock the
vehicle PIN, which is why #1807 put a second gate there in the first place.

The window is narrow and the entity gate still hides the controls, so this is a
race rather than an open door. It gets its own fix because of what it costs when
it is lost, not because it is likely.

Why it was not caught: the existing test warms the marker deliberately, calling
``_get_mbb_operationlist`` before the command, so it exercises the warm path
only. These tests call the command first, which is what a user's automation does
after a restart.
"""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    VehicleCommandError,
)

VIN = "WVWZZZSYNTHET0001"
_LEGACY = "https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/operationlist/v3"
_EUDP = "https://mal-3a.prd.eu.dp.vwg-connect.com/api/rolesrights/operationlist/v3"
_AUTH_401 = APIError(
    401, _LEGACY,
    '{"error":{"errorCode":"gw.error.authentication","description":"Unauthorized"}}',
)


def _list(*services: dict) -> dict:
    return {"operationList": {"vin": VIN, "role": "PRIMARY_USER",
                              "status": "ENABLED", "serviceInfo": list(services)}}


_RCLIMA = {
    "serviceId": "rclima_v1",
    "serviceStatus": {"status": "Enabled"},
    "invocationUrl": {"content":
        "https://mal-3a.prd.eu.dp.vwg-connect.com/api/bs/climatisation/v1/vehicles/{vin}/"},
    "operation": [{"id": "P_START_CLIMA_NOSET", "permission": "granted"}],
}
_SPIN = {
    "serviceId": "rolesrights_securitypin_v1",
    "serviceStatus": {"status": "Enabled"},
    "invocationUrl": {"content":
        "https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/securitypin/v1/users/{userId}/"},
}
_GOOD = _list(_RCLIMA, _SPIN)


def _client(side_effect) -> VWEUClient:
    """A client with NO warmed marker: exactly the state after a restart."""
    c = VWEUClient.__new__(VWEUClient)
    c._brand = types.SimpleNamespace(name="volkswagen")
    c._mbb_country_from_id_token = lambda: "DE"
    c._mbb_get = AsyncMock(side_effect=side_effect)
    c._refresh_tokens = AsyncMock(return_value=None)
    c._spin = "1234"
    return c


class TestColdMarker:
    """The case the existing test could not reach, because it warms first."""

    def test_the_command_is_refused_on_a_cold_marker(self):
        c = _client([_AUTH_401, _GOOD])
        assert not hasattr(c, "mbb_eudp_oplist_vins")  # genuinely cold
        with pytest.raises(VehicleCommandError, match="EU-DP"):
            asyncio.run(c._command_mbb_op(VIN, "climate_start"))

    def test_nothing_beyond_the_two_list_reads_goes_out(self):
        """The point of the gate: no S-PIN leg, so no PIN attempt to lose."""
        c = _client([_AUTH_401, _GOOD])
        with pytest.raises(VehicleCommandError):
            asyncio.run(c._command_mbb_op(VIN, "climate_start"))
        assert c._mbb_get.await_count == 2

    def test_the_marker_is_set_by_the_fetch_inside_the_command(self):
        """Grounds WHY the early gate cannot see it: the fetch fills it later."""
        c = _client([_AUTH_401, _GOOD])
        with pytest.raises(VehicleCommandError):
            asyncio.run(c._command_mbb_op(VIN, "climate_start"))
        assert VIN in c.mbb_eudp_oplist_vins

    def test_the_refusal_names_the_same_cause_as_the_warm_path(self):
        c = _client([_AUTH_401, _GOOD])
        with pytest.raises(VehicleCommandError) as err:
            asyncio.run(c._command_mbb_op(VIN, "climate_start"))
        assert "read-only" in str(err.value).lower()


class TestWarmMarkerUnchanged:
    """#1807's own behaviour must be exactly as it was."""

    def test_a_warm_marker_still_refuses_before_any_fetch(self):
        c = _client([_AUTH_401, _GOOD])
        c.mbb_eudp_oplist_vins = {VIN}
        with pytest.raises(VehicleCommandError, match="EU-DP"):
            asyncio.run(c._command_mbb_op(VIN, "climate_start"))
        assert c._mbb_get.await_count == 0  # refused before the wire

    def test_the_early_gate_is_still_the_first_thing_that_runs(self):
        """Keeping it means a warm car never pays for a list it cannot use."""
        c = _client([])
        c.mbb_eudp_oplist_vins = {VIN}
        with pytest.raises(VehicleCommandError, match="EU-DP"):
            asyncio.run(c._command_mbb_op(VIN, "climate_start"))


class TestNoFalseRefusal:
    """A car served by the legacy host must not be caught by this."""

    def test_a_legacy_car_gets_past_the_gate(self):
        c = _client([_GOOD])
        try:
            asyncio.run(c._command_mbb_op(VIN, "climate_start"))
        except VehicleCommandError as err:
            assert "EU-DP" not in str(err), str(err)
        except Exception:
            pass  # fails later in the S-PIN legs, which are not mocked here
        assert VIN not in getattr(c, "mbb_eudp_oplist_vins", set())

    def test_an_unknown_command_still_fails_first(self):
        """Ordering guard: the spec lookup stays ahead of both gates."""
        c = _client([])
        c.mbb_eudp_oplist_vins = {VIN}
        with pytest.raises(VehicleCommandError, match="unknown MBB command"):
            asyncio.run(c._command_mbb_op(VIN, "not_a_real_command"))
