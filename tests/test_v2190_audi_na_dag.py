# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.19.0 — Audi US/CA (audi_na) via the Device Authorization Grant (DAG).

Prash's preferred clean auth for Audi NA is device-code (no stored password).
DAG now drives the SAME RFC-8628 flow against the NA IDP (identity.na.vwgroup.io)
instead of the EU one, via per-instance URL overrides on
``DeviceAuthorizationGrant`` + the ``dag_idp_urls`` brand switch.

LIVE-GATED (unconfirmed until a real US-Audi tester): whether the NA IDP exposes
device_authorization, whether client 7c6b4634 is device-code-capable, and whether
a device-grant token reads na.bff. (The community Audi-NA reference reads via the
password/authcode path instead — this DAG path is the clean-auth alternative.)
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.auth._device_grant import (
    DAG_ENABLED_BRANDS,
    DeviceAuthorizationGrant,
    dag_idp_urls,
    _IDP_DEVICE_AUTH_URL,
    _IDP_TOKEN_URL,
)
from custom_components.vag_connect.cariad.models import BRANDS, BRAND_AUDI_NA


def test_audi_na_is_dag_eligible() -> None:
    assert "audi_na" in DAG_ENABLED_BRANDS
    # the EU brands are untouched
    assert {"audi", "skoda", "seat", "cupra"} <= DAG_ENABLED_BRANDS


def test_dag_idp_urls_switches_na_vs_eu() -> None:
    dev, tok = dag_idp_urls("audi_na")
    assert dev == "https://identity.na.vwgroup.io/oidc/v1/device_authorization"
    assert tok == "https://identity.na.vwgroup.io/oidc/v1/token"
    # every other brand keeps the EU IDP
    for eu in ("audi", "skoda", "seat", "cupra"):
        assert dag_idp_urls(eu) == (_IDP_DEVICE_AUTH_URL, _IDP_TOKEN_URL)


def test_audi_na_client_id_resolves_from_brands() -> None:
    assert BRANDS["audi_na"] is BRAND_AUDI_NA
    assert BRANDS["audi_na"].client_id.startswith("7c6b4634-")


def test_device_grant_accepts_url_overrides() -> None:
    dev, tok = dag_idp_urls("audi_na")
    grant = DeviceAuthorizationGrant(
        MagicMock(), BRAND_AUDI_NA.client_id,
        scope="openid", device_auth_url=dev, token_url=tok,
    )
    assert grant._device_auth_url == dev
    assert grant._token_url == tok


def test_device_grant_defaults_to_eu_urls() -> None:
    grant = DeviceAuthorizationGrant(MagicMock(), "x@apps_vw-dilab_com")
    assert grant._device_auth_url == _IDP_DEVICE_AUTH_URL
    assert grant._token_url == _IDP_TOKEN_URL
