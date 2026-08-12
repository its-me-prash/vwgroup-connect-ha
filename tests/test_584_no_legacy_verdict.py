# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 — durable "no legacy MBB enrolment" verdict.

When the MBB operationList returns the definitive ``gw.error.authentication``
401 (the Mattheisen87 / B8-GTE-line verdict — the car/account has no legacy
Car-Net enrolment, so reads work only via EU-DA/vw.de and MBB commands never
will), the client records the VIN in a public ``mbb_no_legacy_vins`` set so the
diagnostics can surface it and a #584-class report is triageable at a glance.
It clears the moment a fresh operationList succeeds (enrolment recovered), and
it is NOT set by the transient bare-401/403 (systemId ACL) backoff path.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError

VIN = "WVWZZZAUZFW805377"
_URL = "https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/operationlist/v3"
_AUTH_401 = APIError(
    401, _URL,
    '{"error":{"errorCode":"gw.error.authentication","description":"Unauthorized"}}',
)
_ACL_403 = APIError(
    403, _URL,
    '{"error":{"errorCode":"mbbc.rolesandrights.unauthorized",'
    '"description":"Did not find permission for systemId \'XID_APP_VW\'"}}',
)
_GOOD = {"operationList": {"vin": VIN, "role": "PRIMARY_USER", "status": "ENABLED",
                           "serviceInfo": [{"serviceId": "rclima_v1",
                                            "serviceStatus": {"status": "Enabled"}}]}}


def _client(side_effect) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._mbb_get = AsyncMock(side_effect=side_effect)
    c._refresh_tokens = AsyncMock(return_value=None)
    return c


def test_gw_error_authentication_records_no_legacy_verdict() -> None:
    c = _client([_AUTH_401])
    assert asyncio.run(c._get_mbb_operationlist(VIN, for_command=True)) is None
    assert VIN in c.mbb_no_legacy_vins


def test_successful_operationlist_clears_the_verdict() -> None:
    """Enrolment recovered (e.g. the user became primary user in the app) → a
    fresh list succeeds and the durable verdict drops."""
    c = _client([_AUTH_401, _GOOD])
    asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
    assert VIN in c.mbb_no_legacy_vins
    ol = asyncio.run(
        c._get_mbb_operationlist(VIN, for_command=True, force_refresh=True)
    )
    assert ol is not None
    assert VIN not in c.mbb_no_legacy_vins


def test_systemid_acl_403_is_not_a_no_legacy_verdict() -> None:
    """Only the definitive gw.error.authentication verdict counts. The bare
    401/403 (systemId ACL) is the transient soft-backoff path and must NOT mark
    the car as no-legacy — that would falsely flag a car having a bad minute."""
    c = _client([_ACL_403])
    assert asyncio.run(c._get_mbb_operationlist(VIN, for_command=True)) is None
    assert VIN not in c.mbb_no_legacy_vins


def test_verdict_set_exists_even_before_any_call() -> None:
    """A fresh client that has never fetched an operationList still answers the
    diagnostics probe cleanly (empty set, not AttributeError)."""
    c = _client([_GOOD])
    asyncio.run(c._get_mbb_operationlist(VIN))
    assert c.mbb_no_legacy_vins == set()
