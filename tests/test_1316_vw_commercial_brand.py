# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1316 — the ``volkswagen_commercial`` brand (VW Commercial Vehicles / Nutzfahrzeuge).

A SEPARATE EU Data Act data-controller realm from passenger VW (one account can
hold an ID.3 in the passenger realm and a T6.1 in the commercial one), reached via
the SAME portal client with ``state_brand`` ``VOLKSWAGEN_COMMERCIAL_VEHICLES``.
Adding a brand is cross-cutting; these pin the wiring (factory routing, registry,
BrandConfig parity, clean device label, display/deeplink maps) so it can't
half-exist. The portal-state guard lives in test_v2120_eu_data_act_connector.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.api.commercial import VWCommercialClient
from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
from custom_components.vag_connect.cariad.models import (
    BRANDS,
    BRAND_VW_COMMERCIAL,
    BRAND_VW_EU,
)
from custom_components.vag_connect.const import BRANDS as BRAND_LABELS
from custom_components.vag_connect.const import DEEPLINK_SCHEMES
from custom_components.vag_connect.entity_base import _brand_display, _device_name


def test_factory_creates_vw_commercial_client():
    client = CariadClientFactory.create(
        "volkswagen_commercial", MagicMock(), "u@t.de", "pw",
    )
    assert isinstance(client, VWCommercialClient)
    # the distinct brand name is what routes the portal to the commercial realm
    assert client._brand.name == "volkswagen_commercial"


def test_registry_and_brandconfig_parity():
    assert BRANDS["volkswagen_commercial"] is BRAND_VW_COMMERCIAL
    assert BRAND_VW_COMMERCIAL.name == "volkswagen_commercial"
    # every field except the name mirrors passenger VW (same BFF/portal surface)
    assert BRAND_VW_COMMERCIAL.client_id == BRAND_VW_EU.client_id
    assert BRAND_VW_COMMERCIAL.scope == BRAND_VW_EU.scope
    assert BRAND_VW_COMMERCIAL.api_base == BRAND_VW_EU.api_base
    assert BRAND_VW_COMMERCIAL.redirect_uri == BRAND_VW_EU.redirect_uri
    assert BRAND_VW_COMMERCIAL.name != BRAND_VW_EU.name


def test_clean_device_label_not_the_raw_slug():
    # the raw brand.title() would be "Volkswagen_Commercial" — must not leak out
    assert _brand_display("volkswagen_commercial") == "Volkswagen Commercial Vehicles"
    name = _device_name({"vin": "WVWZZZ0000000001"}, "volkswagen_commercial")
    assert name.startswith("Volkswagen Commercial Vehicles")
    assert "_" not in name
    # an unmapped brand is unchanged (still title-cased) — no blast radius
    assert _brand_display("audi") == "Audi"


def test_display_and_deeplink_maps_have_the_brand():
    assert BRAND_LABELS["volkswagen_commercial"] == "Volkswagen Commercial Vehicles"
    assert DEEPLINK_SCHEMES["volkswagen_commercial"] == "weconnect://"
