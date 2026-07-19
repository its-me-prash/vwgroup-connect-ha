# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.2 — Audi North America login foundation.

Sweep-verified (2026-07-18): US Audi is the EU-Audi CARIAD-BFF stack in the NA
region — NOT the VW-NA con-veh backend. So ``AudiNAClient`` rides ``VWEUClient``
(exactly as the EU ``AudiClient`` does), with the NA host / IDP / client_id, and
is deliberately NOT a ``VWNAClient``.

These tests cover the WIRING + the real endpoints. They do NOT cover a live login
or read: the CARIAD-BFF NA data plane is attestation-walled like EU Audi, so reads
403 off-device until a data path exists (see audi_na.py / BRAND_AUDI_NA).
"""
from __future__ import annotations

from unittest.mock import MagicMock

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
    # v2.20.0 (APK audit) — myAudi 5.6.0 has no na.bff host; reads/token use the
    # global emea.bff (only authorize is region-split at identity.na.vwgroup.io).
    assert BRAND_AUDI_NA.api_base == "https://emea.bff.cariad.digital"


def test_factory_routes_audi_na() -> None:
    client = _client()
    assert isinstance(client, AudiNAClient)
    assert isinstance(client, VWEUClient)  # CARIAD-BFF read path reused


def test_audi_na_reads_target_na_bff() -> None:
    # v2.20.0 (APK audit) — reads hit the global emea.bff (the NA app has no
    # na.bff host); the EU per-VIN HomeRegion split is still overridden off.
    assert _client()._base_for_vin("WAUZZZ00000000000") == "https://emea.bff.cariad.digital"


def test_audi_na_registered_in_brands() -> None:
    assert "audi_na" in BRANDS


def test_audi_na_country_accepted() -> None:
    # CA is accepted for interface parity (reuses US brand until a CA sweep).
    assert _client("ca")._country == "ca"
