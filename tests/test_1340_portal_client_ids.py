# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1340 (@cyrano330) — Audi/Škoda/Bentley each authenticate against the EU Data
Act portal with their OWN OIDC client. Reusing the VW client made login "succeed"
(it lands on the portal host) while the session stayed ANONYMOUS, so every
proxy_api data read 401'd. The full ids are grounded from the portal's per-brand
login redirect (each 302s to identity.vwgroup.io/signin-service/<that id>), match
every other EU-Data-Act reader, and are verified live 2026-09-05. Both portal-auth
consumers (the cookie reader and the token/device-grant login) must use them and
must never drift apart.
"""
from __future__ import annotations

# Grounded 2026-09-05: triple-source (independent EU-DA readers) + a live
# unauthenticated authorize handshake (each id 302 → signin-service/<id>).
_AUDI = "cc29b87a-5e9a-4362-aecf-5adea6b01bbb@apps_vw-dilab_com"
_SKODA = "3ea88bf9-1d4e-4a68-b3ad-4098c1f1d246@apps_vw-dilab_com"
_BENTLEY = "d38aac0f-3d89-4a63-8538-b75b31322c7b@apps_vw-dilab_com"
_CUPRA_SEAT = "f85e5b69-e3b2-43aa-9c0d-1b7d0e0b576f@apps_vw-dilab_com"
_VW = "9b58543e-1c15-4193-91d5-8a14145bebb0@apps_vw-dilab_com"


def _cookie_client(brand: str) -> str:
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )
    return EUDataActConnector(object(), brand=brand)._client_id  # type: ignore[arg-type]


def test_cookie_reader_uses_own_client_per_brand() -> None:
    assert _cookie_client("audi") == _AUDI
    assert _cookie_client("skoda") == _SKODA
    assert _cookie_client("bentley") == _BENTLEY
    # unchanged brands keep their own client
    assert _cookie_client("volkswagen") == _VW
    assert _cookie_client("volkswagen_commercial") == _VW
    assert _cookie_client("cupra") == _CUPRA_SEAT
    assert _cookie_client("seat") == _CUPRA_SEAT
    # a genuinely unknown brand still falls back to VW (graceful)
    assert _cookie_client("porsche") == _VW


def test_portal_login_path_uses_own_client_per_brand() -> None:
    from custom_components.vag_connect.cariad.auth._data_act_portal import (
        _brand_client_id,
    )
    assert _brand_client_id("audi") == _AUDI
    assert _brand_client_id("skoda") == _SKODA
    assert _brand_client_id("bentley") == _BENTLEY
    assert _brand_client_id("cupra") == _CUPRA_SEAT
    assert _brand_client_id("seat") == _CUPRA_SEAT
    assert _brand_client_id("volkswagen") == _VW
    assert _brand_client_id("porsche") == _VW      # unknown → VW fallback
    assert _brand_client_id("AUDI") == _AUDI        # case-insensitive


def test_both_consumers_agree_on_every_brand() -> None:
    # The cookie reader and the token/device-grant login must never disagree on a
    # brand's portal client — a drift would make one channel silently anonymous.
    from custom_components.vag_connect.cariad.auth._data_act_portal import (
        _brand_client_id,
    )
    for brand in (
        "audi", "skoda", "bentley", "cupra", "seat",
        "volkswagen", "volkswagen_commercial", "porsche",
    ):
        assert _cookie_client(brand) == _brand_client_id(brand), brand
