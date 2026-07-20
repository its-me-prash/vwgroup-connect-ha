# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.20.1 (#584) — MBB operationList: refresh + retry once on a token-auth 401.

Mattheisen87's Passat GTE on v2.20.0: the durable-MBB token refresh works (the
v2.18.0 fix), reads are healthy, but the operationList GET returns
``401 gw.error.authentication`` 26× → an empty service directory → every command
entity stays ``unavailable``. That 401 is a TOKEN-AUTH failure (the gateway
rejects the bearer as unauthenticated), NOT the data-plane systemId ACL
(``mbbc.rolesandrights.unauthorized`` / ``*.security.9007``) which no refresh can
fix. Mirroring audi_connect_ha #782, a token-auth failure is recovered by
refreshing the bearer once and retrying — guarded to exactly one retry so the
refresh endpoint is never stormed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError

VIN = "WVWZZZ3CZ9W025570"

_URL = "https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/operationlist/v3"
_AUTH_401 = APIError(401, _URL, '{"error":{"errorCode":"gw.error.authentication","description":"Unauthorized"}}')
_ACL_403 = APIError(403, _URL, '{"error":{"errorCode":"mbbc.rolesandrights.unauthorized","description":"Did not find permission for systemId \'XID_APP_VW\'"}}')
_ACL_401 = APIError(401, _URL, '{"error":{"errorCode":"mbbc.rolesandrights.unauthorized"}}')

_GOOD = {"operationList": {"vin": VIN, "role": "PRIMARY_USER", "status": "ENABLED",
                           "serviceInfo": [{"serviceId": "rclima_v1",
                                            "serviceStatus": {"status": "Enabled"}}]}}


def _client(mbb_get_side_effect) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._mbb_get = AsyncMock(side_effect=mbb_get_side_effect)
    c._refresh_tokens = AsyncMock(return_value=None)
    return c


class TestOplist401Retry:
    def test_auth_401_then_success_refreshes_and_retries(self) -> None:
        c = _client([_AUTH_401, _GOOD])
        oplist = asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
        assert oplist is not None
        assert "rclima_v1" in oplist.services
        c._refresh_tokens.assert_awaited_once()          # refreshed exactly once
        assert c._mbb_get.await_count == 2               # original + retry
        # the refresh was routed to the command channel
        assert c._refresh_tokens.await_args.kwargs.get("for_command") is True

    def test_auth_401_persists_refreshes_once_then_gives_up(self) -> None:
        # Both attempts 401 → one refresh, one retry, then None — NO storm.
        c = _client([_AUTH_401, _AUTH_401])
        oplist = asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
        assert oplist is None
        c._refresh_tokens.assert_awaited_once()
        assert c._mbb_get.await_count == 2               # never a third attempt

    def test_systemid_403_does_not_refresh(self) -> None:
        # The data-plane ACL is unrecoverable — must NOT refresh/retry.
        c = _client([_ACL_403])
        oplist = asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
        assert oplist is None
        c._refresh_tokens.assert_not_awaited()
        assert c._mbb_get.await_count == 1

    def test_systemid_401_does_not_refresh(self) -> None:
        # A 401 that is the systemId ACL (not gw.error.authentication) is also
        # unrecoverable — the trigger is the error code, not the status.
        c = _client([_ACL_401])
        oplist = asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
        assert oplist is None
        c._refresh_tokens.assert_not_awaited()
        assert c._mbb_get.await_count == 1

    def test_happy_path_200_never_refreshes(self) -> None:
        # Prash's Golf: operationList 200 on the first call — no retry logic runs.
        c = _client([_GOOD])
        oplist = asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
        assert oplist is not None
        c._refresh_tokens.assert_not_awaited()
        assert c._mbb_get.await_count == 1
