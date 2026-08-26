# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""vw.de master-data must survive a NON-PRIMARY relation.

Verified live 2026-08-26 against a guest account on a family Golf GTE: the rich
``details`` endpoint (engine / year / colour-text / ``specifications`` list) is
the vehicle-FILE service and 403s for anyone who isn't the primary user, but the
flat ``data`` endpoint still returns ``modelName`` + colour code. Before the fix,
``get_master_data`` read ``details`` first with ``soft=True`` — a 403 there raised
and aborted before ``data`` was ever read, so a guest car got NO model name even
though ``data`` carried it. The reads are now ``optional`` so a per-car 4xx
degrades to None and the other endpoint still fills what it can.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.models import VehicleData

_VIN = "WVWZZZTESTVHN0001"
# The exact live shapes captured 2026-08-26 (values are VW's, no PII).
_DATA_200 = {
    "vin": _VIN,
    "modelName": "Golf GTE Plug in Hybrid 1,4 l TSI Plug-In-Hybrid",
    "exteriorColor": "0R",
}
_DETAILS_200 = {
    "modelName": "Golf GTE Plug in Hybrid 1,4 l TSI Plug-In-Hybrid",
    "engine": "110 kW (150 PS)",
    "modelYear": "2015",
    "exteriorColorText": "Oryxweiß Perlmutteffekt",
    "specifications": [{"codeText": "x", "origin": "L"}] * 3,
}
# RFC7807 problem+json — the real 403 body the guest read returns.
_DETAILS_403 = {"status": 403, "title": "Forbidden", "detail": "x", "instance": "/y"}


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
    """Routes /details/ and /data/ to caller-supplied statuses."""

    cookie_jar = _Jar()

    def __init__(self, details_status: int) -> None:
        self._details_status = details_status

    def get(self, url: str, **_kw: Any) -> _FakeResp:
        if "/details/" in url:
            if self._details_status == 200:
                return _FakeResp(url, status=200, json_data=_DETAILS_200)
            return _FakeResp(url, status=self._details_status, json_data=_DETAILS_403)
        if "/data/" in url:
            return _FakeResp(url, status=200, json_data=_DATA_200)
        raise AssertionError(f"unexpected GET {url}")


def _conn(details_status: int) -> WebsiteAuthProxyConnector:
    return WebsiteAuthProxyConnector(
        _Session(details_status), "u@x.z", "pw"  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_guest_403_on_details_still_yields_model_from_data() -> None:
    # The regression: a 403 on details must NOT abort — data still fills the model.
    info = await _conn(403).get_master_data(_VIN)
    assert info.model_name == _DATA_200["modelName"]
    assert info.exterior_color_code == "0R"
    # details-only fields stay empty for a guest (no crash, no bogus value)
    assert info.engine is None
    assert info.model_year is None


@pytest.mark.asyncio
async def test_primary_user_gets_full_master_data() -> None:
    info = await _conn(200).get_master_data(_VIN)
    assert info.model_name == _DETAILS_200["modelName"]
    assert info.engine == "110 kW (150 PS)"
    assert info.model_year == "2015"
    assert info.exterior_color_text == "Oryxweiß Perlmutteffekt"
    assert info.spec_count == 3


def test_supplementary_model_and_engine_fill_the_empty_primary() -> None:
    # End-to-end: the master-data model/engine reach the merged device record when
    # the primary channel left them empty (portal "Volkswagen (2023)", no model).
    primary = VehicleData(vin=_VIN)          # portal read: no model / engine_power
    supp = VehicleData(vin=_VIN)             # vw.de read
    supp.model = "Golf GTE Plug in Hybrid 1,4 l TSI Plug-In-Hybrid"
    supp.engine_power = "110 kW (150 PS)"
    merged = merge_channels([
        ("eu_data_act", primary),
        ("website_authproxy", supp),
    ])
    assert merged.model == supp.model
    assert merged.engine_power == "110 kW (150 PS)"


def test_real_primary_model_is_not_overwritten() -> None:
    primary = VehicleData(vin=_VIN)
    primary.model = "ID.4"
    supp = VehicleData(vin=_VIN)
    supp.model = "Golf GTE Plug in Hybrid 1,4 l TSI Plug-In-Hybrid"
    merged = merge_channels([("bff", primary), ("website_authproxy", supp)])
    assert merged.model == "ID.4"
