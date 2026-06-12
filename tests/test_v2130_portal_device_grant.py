# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.13.0 Block A1 — portal device-grant plumbing in _device_grant.py.

The EU-Data-Act PORTAL clients (VW 9b58543e, CUPRA/SEAT f85e5b69) support a
public device-grant whose token the portal proxy_api accepts (read-only) but
the CARIAD BFF rejects. These are routed via PORTAL_DAG_BRANDS + the
device_grant_portal strategy tag, SEPARATE from the BFF DAG path.

Audit-pinned: portal_dag_config MUST return None for audi/skoda (they map to
the VW client inside _EUDA_BRANDS, so a bare table lookup would wrongly
self-gate them into portal mode).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_CAR = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect" / "cariad"


def _load_dg():
    for n, p in [
        ("_pg", _CAR.parent.parent),
        ("_pg.vag_connect", _CAR.parent),
        ("_pg.vag_connect.cariad", _CAR),
        ("_pg.vag_connect.cariad.auth", _CAR / "auth"),
    ]:
        m = types.ModuleType(n)
        m.__path__ = [str(p)]
        sys.modules[n] = m

    def load(n, f):
        spec = importlib.util.spec_from_file_location(n, f)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[n] = mod
        spec.loader.exec_module(mod)
        return mod

    load("_pg.vag_connect.cariad.exceptions", _CAR / "exceptions.py")
    load("_pg.vag_connect.cariad.models", _CAR / "models.py")
    load("_pg.vag_connect.cariad.auth._eu_data_act", _CAR / "auth" / "_eu_data_act.py")
    return load("_pg.vag_connect.cariad.auth._device_grant", _CAR / "auth" / "_device_grant.py")


def test_portal_dag_config_vw():
    dg = _load_dg()
    cid, scope = dg.portal_dag_config("volkswagen")
    assert cid.startswith("9b58543e")
    assert scope == "openid cars profile"


@pytest.mark.parametrize("brand", ["cupra", "seat"])
def test_portal_dag_config_cupra_seat(brand):
    dg = _load_dg()
    cid, scope = dg.portal_dag_config(brand)
    assert cid.startswith("f85e5b69")
    assert scope == "openid profile cars"


@pytest.mark.parametrize("brand", ["audi", "skoda", "porsche"])
def test_portal_dag_config_none_for_non_portal_brands(brand):
    """Audit #1 — audi/skoda map to the VW client in _EUDA_BRANDS, but the
    PORTAL_DAG_BRANDS guard must keep them OUT of portal device-grant."""
    dg = _load_dg()
    assert dg.portal_dag_config(brand) is None


def test_is_portal_dag_eligible():
    dg = _load_dg()
    assert dg.is_portal_dag_eligible("volkswagen")
    assert dg.is_portal_dag_eligible("cupra")
    assert not dg.is_portal_dag_eligible("audi")


def test_dag_enabled_brands_unchanged():
    """The BFF DAG set must NOT gain volkswagen (would route to the dead BFF)."""
    dg = _load_dg()
    assert dg.DAG_ENABLED_BRANDS == frozenset({"audi", "skoda", "seat", "cupra"})
    assert "volkswagen" not in dg.DAG_ENABLED_BRANDS


def test_strategy_param_wired():
    dg = _load_dg()
    g = dg.DeviceAuthorizationGrant(None, "cid", scope="s", strategy="device_grant_portal")
    assert g._strategy == "device_grant_portal"
    g2 = dg.DeviceAuthorizationGrant(None, "cid")
    assert g2._strategy == "device_grant"  # backward-compatible default
