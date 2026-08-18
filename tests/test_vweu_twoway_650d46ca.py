# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way (modern CARIAD BFF) via device-grant client 650d46ca.

650d46ca is a VW-EU app client that is BOTH device-code-mintable AND
BFF-whitelisted (confirmed live 2026-08-18: device_authorization 200, BFF
/vehicles + /capabilities 200 with command operations), unlike the DAG-dead app
client (a24fba63) and the read-only portal client (9b58543e). Its token drives
the modern CARIAD BFF read/command path in vw_eu.py directly (strategy
``device_grant``), NOT the legacy Car-Net MBB pipeline (which needs the ``mbb``
scope / VWGMBB01DELIV1 audience). This module pins that foundation.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._device_grant import (
    DeviceAuthorizationGrant,
    VWEU_DAG_CLIENT_ID,
    VWEU_DAG_SCOPE,
    mbb_dag_config,
    vweu_dag_config,
)


def test_vweu_config_returns_650d46ca_for_volkswagen() -> None:
    cfg = vweu_dag_config("volkswagen")
    assert cfg == (VWEU_DAG_CLIENT_ID, VWEU_DAG_SCOPE)
    assert cfg[0].startswith("650d46ca-2475-4384-85c2-6af3bf3d52f1@apps_vw-dilab_com")


def test_vweu_config_case_insensitive() -> None:
    assert vweu_dag_config("Volkswagen") == vweu_dag_config("volkswagen")


def test_vweu_config_none_for_other_brands() -> None:
    for brand in ("audi", "skoda", "seat", "cupra", "audi_na", "porsche"):
        assert vweu_dag_config(brand) is None, brand


def test_vweu_scope_is_the_full_bff_scope_not_mbb() -> None:
    # The BFF scope carries cars/vin/offline_access; crucially NOT ``mbb`` — the
    # ``mbb`` scope would route the id_token at the Car-Net exchange, which is a
    # different pipeline. 650d46ca is a direct BFF bearer.
    assert "cars" in VWEU_DAG_SCOPE
    assert "vin" in VWEU_DAG_SCOPE
    assert "mbb" not in VWEU_DAG_SCOPE.split()


def test_vweu_is_distinct_from_mbb_client_and_scope() -> None:
    mbb = mbb_dag_config("volkswagen")
    assert mbb is not None
    mbb_client, mbb_scope = mbb
    assert VWEU_DAG_CLIENT_ID != mbb_client
    assert VWEU_DAG_SCOPE != mbb_scope
    # MBB is the load-bearing ``mbb`` scope; 650d46ca must not be.
    assert "mbb" in mbb_scope.split()


def test_grant_built_from_vweu_config_tags_device_grant_for_bff_routing() -> None:
    # A DeviceAuthorizationGrant defaults to strategy 'device_grant' — the tag
    # that makes vw_eu.py fall through to the BFF read/command path (NOT 'mbb',
    # NOT 'device_grant_portal'). Build it exactly as the config flow will.
    client_id, scope = vweu_dag_config("volkswagen")
    grant = DeviceAuthorizationGrant(None, client_id, scope=scope)
    assert grant._strategy == "device_grant"
    assert grant._client_id == VWEU_DAG_CLIENT_ID
    assert grant._scope == VWEU_DAG_SCOPE
