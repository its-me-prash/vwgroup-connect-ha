# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The pre-flight MBB eligibility is stashed off the relations read for the
diagnostics surface. Observability only — this must never gate a read or command,
so the test asserts the classification lands in ``mbb_eligibility`` and nothing
else changes. Grounded on the exact live relations shapes (2026-08-26): a guest
on an MBB car → ``not_provisioned``; an MEB/ID car → ``not_mbb``.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)

_RELATIONS_BODY = {
    "user": {"idKitUserId": "u1", "mbbUserId": "MMxxx", "legalEntityCode": "VOLKSWAGEN"},
    "relations": [
        {  # guest on an MBB car → not_provisioned
            "role": "UNKNOWN",
            "enrollmentStatus": "NOT_STARTED",
            "primaryCar": False,
            "carnetIndicator": False,
            "carnetAllocationType": None,
            "vehicle": {"vin": "WVWZZZTESTVHN0001", "modBackend": "MBB"},
        },
        {  # enrolled owner of an MEB/ID car → not_mbb (its two-way is the BFF)
            "role": "PRIMARY_USER",
            "enrollmentStatus": "COMPLETED",
            "primaryCar": True,
            "carnetIndicator": True,
            "vehicle": {"vin": "WVWZZZTESTVHN0002", "modBackend": "MEB"},
        },
    ],
}


class _FakeResp:
    def __init__(self, url: str, *, status: int = 200, json_data: Any = None) -> None:
        self.url = url
        self.status = status
        self._json = json_data

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return ""

    async def json(self, content_type: Any = None) -> Any:
        return self._json


class _Jar:
    def filter_cookies(self, _url: Any) -> dict[str, Any]:
        return {}


class _Session:
    cookie_jar = _Jar()

    def get(self, url: str, **_kw: Any) -> _FakeResp:
        if "relations" in url:
            return _FakeResp(url, status=200, json_data=_RELATIONS_BODY)
        raise AssertionError(f"unexpected GET {url}")


@pytest.mark.asyncio
async def test_get_relations_stashes_mbb_eligibility() -> None:
    conn = WebsiteAuthProxyConnector(_Session(), "u@x.z", "pw")  # type: ignore[arg-type]
    assert conn.mbb_eligibility == {}
    rels = await conn.get_relations()
    assert rels is not None
    assert conn.mbb_eligibility == {
        "WVWZZZTESTVHN0001": "not_provisioned",
        "WVWZZZTESTVHN0002": "not_mbb",
    }
    # the platform cache still works exactly as before (no behavior change)
    assert conn._vin_backend["WVWZZZTESTVHN0001"] == "MBB"
    assert conn._vin_backend["WVWZZZTESTVHN0002"] == "MEB"
