# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 — MBB operationList: a gw.error.authentication 401 must NOT refresh.

History: v2.20.1 refreshed-and-retried once on a ``gw.error.authentication`` 401,
on the theory that the gateway had rejected a stale bearer (mirroring
audi_connect_ha #782). That premise was disproven 2026-07-22:

- a live Golf 7 GTE returns 200 on this exact operationList call with the
  integration's own header set (the header-provenance A/B test), and
- Mattheisen87 re-ran the full device-code approval and a one-second-old,
  freshly-approved token STILL 401s on the first call.

So the 401 is a gateway/rolesrights AUTHORIZATION rejection scoped to the
vehicle↔account (Car-Net enrolment / primary-user), which no token refresh can
fix. Worse, refreshing once per poll fed the command refresh budget until the
storm guard raised a misleading "please reauthenticate". The operationList now
treats every 401 (gw.error.authentication OR the systemId ACL) the same: log
once, spend no refresh, return None.
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


class TestOplist401NoRefresh:
    def test_gw_error_authentication_returns_none_without_refresh(self) -> None:
        # The core reversal: the gw.error.authentication 401 is a vehicle/account
        # authz rejection, NOT a stale bearer → no refresh, no retry, None.
        c = _client([_AUTH_401])
        oplist = asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
        assert oplist is None
        c._refresh_tokens.assert_not_awaited()           # never spends the budget
        assert c._mbb_get.await_count == 1               # single call, no retry

    def test_gw_error_authentication_never_storms(self) -> None:
        # Even called repeatedly (e.g. once per poll), it must never refresh —
        # that is exactly what used to trip the storm guard into a false
        # "please reauthenticate".
        c = _client([_AUTH_401, _AUTH_401, _AUTH_401, _AUTH_401])
        for _ in range(4):
            assert asyncio.run(c._get_mbb_operationlist(VIN, for_command=True)) is None
        c._refresh_tokens.assert_not_awaited()
        # #909 — the denial is now negative-cached, so the follow-up polls do not
        # even reach the wire any more (it used to be one call per poll forever).
        assert c._mbb_get.await_count == 1

    def test_systemid_403_does_not_refresh(self) -> None:
        # The data-plane ACL is unrecoverable — must NOT refresh/retry.
        c = _client([_ACL_403])
        oplist = asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
        assert oplist is None
        c._refresh_tokens.assert_not_awaited()
        assert c._mbb_get.await_count == 1

    def test_systemid_401_does_not_refresh(self) -> None:
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
        assert "rclima_v1" in oplist.services
        c._refresh_tokens.assert_not_awaited()
        assert c._mbb_get.await_count == 1
