# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.24.0 — learn the signin client id, and stop silencing discovery children.

Two changes that came out of the same sweep:

1. The sign-in page lives at ``.../signin-service/v1/<client-id>``, and that id
   is not always the OAuth client we authorized with. On VW North America the
   con-veh host proxies to the IDP with its OWN client, so the page belongs to
   that one. We only use the value to rebuild a URL when the served page has no
   parseable form action, but the NA sign-in service answers HTTP 500 for a
   client id it cannot resolve, so guessing wrong turns into a fake "outage".
   Probed: ``.../v1/signin/59992128-..._MYVW_ANDROID`` -> 500, while the same
   path with ``b680e751-...@apps_vw-dilab_com`` -> 400.

2. A settings container was absorbed together with its children. A reporter was
   asked for a diagnostic so the inner fields could be mapped, and the export
   could not contain them because our own filter had already dropped them
   (#843). Containers stay silenced; their named children are the discovery
   signal and must stay visible.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.models import BRAND_VW_EU


def _auth(override: str | None = None) -> IDKAuth:
    return IDKAuth(MagicMock(), BRAND_VW_EU, signin_client_id_override=override)


# ── 1. signin client id is learned from the URL we land on ───────────────────

def test_adopts_client_id_from_the_landed_signin_url() -> None:
    a = _auth()
    a._learn_signin_client_id(
        "https://identity.na.vwgroup.io/signin-service/v1/"
        "b680e751-7e1f-4008-8ec1-3a528183d215@apps_vw-dilab_com?relayState=abc"
    )
    assert a._signin_client_id == (
        "b680e751-7e1f-4008-8ec1-3a528183d215@apps_vw-dilab_com"
    )


def test_handles_the_signin_segment_variant() -> None:
    # Some deployments serve .../signin-service/v1/signin/<client-id>
    a = _auth()
    a._learn_signin_client_id(
        "https://identity.na.vwgroup.io/signin-service/v1/signin/"
        "b680e751-7e1f-4008-8ec1-3a528183d215@apps_vw-dilab_com"
    )
    assert a._signin_client_id.startswith("b680e751-")


def test_explicit_override_always_wins() -> None:
    a = _auth(override="EXPLICIT_ID_FROM_CALLER")
    a._learn_signin_client_id(
        "https://identity.na.vwgroup.io/signin-service/v1/somebody-else"
    )
    assert a._signin_client_id == "EXPLICIT_ID_FROM_CALLER"


def test_unparseable_url_leaves_the_configured_value_alone() -> None:
    a = _auth()
    before = a._signin_client_id
    for url in (
        "https://identity.vwgroup.io/u/login?state=x",   # Auth0 variant
        "https://example.invalid/",                       # nothing to parse
        "https://identity.vwgroup.io/signin-service/v1/",  # empty segment
        "https://identity.vwgroup.io/signin-service/v1/ab",  # too short
    ):
        a._learn_signin_client_id(url)
        assert a._signin_client_id == before, url


# ── 2. container silenced, children still discoverable ───────────────────────

def test_settings_container_children_are_not_silenced() -> None:
    from custom_components.vag_connect.cariad import _unexpected_keys as uk

    blob = uk.__file__ and open(uk.__file__, encoding="utf-8").read()
    base = "climatisation.climatisationSettings.value"
    for container in ("auxiliaryHeatingSettings", "activeVentilationSettings"):
        # the container itself stays absorbed (it is one anonymous blob)
        assert f'"{base}.{container}",' in blob, container
        # but its named children must stay visible, they are the whole point
        assert f'"{base}.{container}.*",' not in blob, (
            f"{container}.* re-added: this is what made the #843 diagnostic "
            "unable to contain the fields we asked the reporter for"
        )
