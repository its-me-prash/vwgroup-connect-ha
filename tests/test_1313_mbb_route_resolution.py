# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Route resolution in the MBB DAG harness (2026-10-04).

Why this file exists: the harness's 2nd CLI argument used to be a raw
client_id, which the script then paired with a scope it guessed from the BRAND.
Those two have to match — VW registers a client WITH a scope set — and when
they don't, ``/device_authorization`` answers ``403 unauthorized_client``. That
is indistinguishable, to a reader, from the probe having refuted its own
hypothesis. It actually cost a real run: the Audi *app* client was pasted in,
whose device grant VW retired with the Auth0 migration (#1364, asserted in
``test_1364_device_grant_retired.py``), so nothing was probed at all.

So the argument now names a ROUTE, and each route reads the same single source
of truth the config flow reads. These tests pin that the names map to the pairs
VW actually registered together — above all that the Car-Net brands default to
the e-Remote MBB client and NOT to the retired app client.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._device_grant import (
    DAG_ENABLED_BRANDS,
    MBB_DAG_CLIENT_ID,
    MBB_DAG_CLIENT_ID_BACKUP,
    MBB_DAG_SCOPE,
)
from custom_components.vag_connect.cariad.models import BRANDS

_HARNESS = pathlib.Path("scripts/mbb_dag_test.py")


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("_mbb_dag_harness_routes", _HARNESS)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mbb_dag_harness_routes"] = mod
    spec.loader.exec_module(mod)
    return mod


H = _load()

# The client whose device grant VW retired (#1364). Nothing may route here by
# default, because a run that lands on it returns 403 and proves nothing.
RETIRED_AUDI_APP_CLIENT = BRANDS["audi"].client_id


# ── the default: Car-Net brands must land on the MBB client ─────────────────

@pytest.mark.parametrize("brand", ["audi", "volkswagen"])
def test_car_net_brands_default_to_the_mbb_client(brand: str) -> None:
    client_id, scope, route = H.resolve_route(brand, None)
    assert route == "mbb"
    assert client_id == MBB_DAG_CLIENT_ID
    assert scope == MBB_DAG_SCOPE


def test_audi_never_defaults_to_the_retired_app_client() -> None:
    """The regression this file is for. A bare ``audi`` run used to be routed to
    the app client, which answers 403 unauthorized_client (#1364)."""
    client_id, _scope, route = H.resolve_route("audi", None)
    assert client_id != RETIRED_AUDI_APP_CLIENT
    assert route != "app"


def test_the_mbb_scope_is_not_trimmed_for_audi() -> None:
    """The old code stripped ``cars`` from the scope when the brand was audi,
    reasoning from the *app* client's myAudi scope set. But the MBB route uses a
    different client, and ``openid profile mbb cars`` is exactly the pair that
    was live-validated on a real Audi account. Keying a scope off the brand when
    it belongs to the client is how the two drift apart."""
    _cid, scope, _route = H.resolve_route("audi", None)
    assert scope == MBB_DAG_SCOPE
    assert "cars" in scope, "the live-validated scope lost a component"
    assert "mbb" in scope.split(), "the load-bearing scope component is gone"


def test_the_mbb_scope_is_identical_for_audi_and_vw() -> None:
    """Same client, same scope — there is no brand-specific variant."""
    audi = H.resolve_route("audi", None)
    vw = H.resolve_route("volkswagen", None)
    assert audi[1] == vw[1]
    assert audi[0] == vw[0]


# ── the named routes ───────────────────────────────────────────────────────

def test_mbb_backup_route_uses_the_failover_client_and_same_scope() -> None:
    client_id, scope, route = H.resolve_route("audi", "mbb-backup")
    assert route == "mbb-backup"
    assert client_id == MBB_DAG_CLIENT_ID_BACKUP
    assert client_id != MBB_DAG_CLIENT_ID
    # Same scope is the whole point of a drop-in failover.
    assert scope == MBB_DAG_SCOPE


def test_app_route_uses_the_brands_own_registered_scope() -> None:
    """Not a hardcoded "openid profile", which silently dropped claims the
    client is entitled to — Audi's registered scope already carries ``mbb``."""
    client_id, scope, route = H.resolve_route("audi", "app")
    assert route == "app"
    assert client_id == BRANDS["audi"].client_id
    assert scope == BRANDS["audi"].scope
    assert scope != "openid profile"


def test_portal_route_is_reachable_by_name() -> None:
    from custom_components.vag_connect.cariad.auth._device_grant import (
        portal_dag_config,
    )

    expected = portal_dag_config("volkswagen")
    assert expected is not None, "precondition: VW has a portal route"
    client_id, scope, route = H.resolve_route("volkswagen", "portal")
    assert route == "portal"
    assert (client_id, scope) == expected


def test_a_raw_client_id_still_works_and_carries_the_mbb_scope() -> None:
    """Ad-hoc probing of an unknown client stays possible — but it no longer
    guesses the scope from the brand."""
    probe = "00000000-1111-2222-3333-444444444444@apps_vw-dilab_com"
    client_id, scope, route = H.resolve_route("audi", probe)
    assert route == "override"
    assert client_id == probe
    assert scope == MBB_DAG_SCOPE


# ── the refusals, which must explain themselves ────────────────────────────

def test_a_non_car_net_brand_cannot_take_the_mbb_route() -> None:
    res = H.resolve_route("seat", "mbb")
    assert isinstance(res, str), "seat must be refused, not routed"
    assert "Car-Net" in res
    assert "Volkswagen" in res and "Audi" in res
    assert "app" in res, "the refusal does not say what to try instead"


def test_a_brand_with_no_route_at_all_is_refused() -> None:
    res = H.resolve_route("skoda", None)
    assert isinstance(res, str)
    assert "skoda" in res


def test_app_route_is_refused_for_a_brand_without_one() -> None:
    assert "volkswagen" not in DAG_ENABLED_BRANDS, "precondition"
    res = H.resolve_route("volkswagen", "app")
    assert isinstance(res, str)
    assert "app device-grant" in res


def test_non_car_net_dag_brands_default_to_the_app_route() -> None:
    """seat/cupra have no MBB route, so the default must fall through to the
    route they DO have rather than refusing."""
    for brand in ("seat", "cupra"):
        client_id, scope, route = H.resolve_route(brand, None)
        assert route == "app", brand
        assert client_id == BRANDS[brand].client_id
        assert scope == BRANDS[brand].scope


# ── counter-check: the test would notice if resolution were gutted ────────

def test_resolution_returns_a_triple_or_an_error_string_only() -> None:
    """Guards against a refactor that returns None and makes every assertion
    above vacuous."""
    for brand, arg in (("audi", None), ("seat", "mbb"), ("skoda", None),
                       ("volkswagen", "portal"), ("audi", "app")):
        res = H.resolve_route(brand, arg)
        assert isinstance(res, (tuple, str)), (brand, arg, type(res))
        if isinstance(res, tuple):
            assert len(res) == 3
            assert all(isinstance(x, str) and x for x in res)
