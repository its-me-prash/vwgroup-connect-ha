# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.2 — Audi North America login foundation.

Sweep-verified (2026-07-18): US Audi is the EU-Audi CARIAD-BFF stack in the NA
region — NOT the VW-NA con-veh backend. So ``AudiNAClient`` rides ``VWEUClient``
(exactly as the EU ``AudiClient`` does), with the NA host / IDP / client_id, and
is deliberately NOT a ``VWNAClient``.

The US data path was live-verified on 2026-08-08: the device-grant access token
gets 401 from the EMEA garage but 200 from the NA garage. The current market
configuration keeps Canada on EMEA, so discovery and per-VIN reads route by
country.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.audi_na import AudiNAClient
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.api.vw_na import VWNAClient
from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
from custom_components.vag_connect.cariad.models import BRAND_AUDI_NA
from custom_components.vag_connect.const import BRANDS


def _client(country: str = "us") -> AudiNAClient:
    return CariadClientFactory.create(
        "audi_na", MagicMock(), "user@example.com", "pw", country=country
    )


def test_audi_na_rides_cariad_bff_not_conveh() -> None:
    # CARIAD-BFF NA (like EU Audi), NOT the VW-NA con-veh stack.
    assert issubclass(AudiNAClient, VWEUClient)
    assert not issubclass(AudiNAClient, VWNAClient)


def test_brand_audi_na_has_live_na_endpoints() -> None:
    assert BRAND_AUDI_NA.name == "audi_na"
    assert (
        BRAND_AUDI_NA.client_id
        == "7c6b4634-f0c5-488b-a78f-b1a65414fb90@apps_vw-dilab_com"
    )
    assert BRAND_AUDI_NA.api_base == "https://na.bff.cariad.digital"


def test_factory_routes_audi_na() -> None:
    client = _client()
    assert isinstance(client, AudiNAClient)
    assert isinstance(client, VWEUClient)  # CARIAD-BFF read path reused


def test_audi_na_reads_target_na_bff() -> None:
    assert _client("us")._base_for_vin("WAUZZZ00000000000") == (
        "https://na.bff.cariad.digital"
    )


def test_audi_ca_reads_remain_on_emea_bff() -> None:
    assert _client("ca")._base_for_vin("WAUZZZ00000000000") == (
        "https://emea.bff.cariad.digital"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("country", "base"),
    (
        ("us", "https://na.bff.cariad.digital"),
        ("ca", "https://emea.bff.cariad.digital"),
    ),
)
async def test_audi_na_vehicle_discovery_routes_by_market(
    country: str, base: str
) -> None:
    client = _client(country)
    client._get = AsyncMock(return_value={"data": []})
    client._resolve_home_regions = AsyncMock()
    client.fetch_images = AsyncMock()

    assert await client.get_vehicles() == []
    client._get.assert_awaited_once_with(f"{base}/vehicle/v1/vehicles")


def test_audi_na_registered_in_brands() -> None:
    assert "audi_na" in BRANDS


def test_audi_na_country_accepted() -> None:
    # CA is accepted for interface parity (reuses US brand until a CA sweep).
    assert _client("ca")._country == "ca"
