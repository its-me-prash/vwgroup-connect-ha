# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW Canada authorize client_id regression (#915/#990/#659).

N7 (v2.20.0) collapsed Canada onto the US authorize client_id on a "re-grep
found 0 hits" reading — the same static-scan artefact that also wrongly dropped
the ca00 data host (restored v2.26.0). The Canadian client is APK-confirmed real
(b13). Two testers (vrouleau #990, shaunadam #659) get HTTP 500 at the CA
password POST while the MyVW app works; a CA account authorizing with the US
client is the leading suspect. These tests lock the per-country authorize client
so the collapse cannot silently return.

NOTE: fixing the client is grounded but LIVE-UNVERIFIED — it needs a real CA
account to confirm the 500 clears. It cannot regress CA (already 500).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.api.vw_na import (
    BRAND_VW_NA,
    _CA_CLIENT_ID,
    VWNAClient,
)


def _client(country: str):
    return VWNAClient(MagicMock(), "u@t.com", "pw", country=country)._auth


def _ca_client_id(country: str) -> str:
    return _client(country)._brand.client_id


def test_ca_uses_its_own_authorize_client() -> None:
    assert _ca_client_id("ca") == _CA_CLIENT_ID


def test_us_uses_the_shared_client() -> None:
    assert _ca_client_id("us") == BRAND_VW_NA.client_id


def test_ca_and_us_authorize_clients_differ() -> None:
    # the whole point of the fix: they are NOT the same id.
    assert _CA_CLIENT_ID != BRAND_VW_NA.client_id
    assert _ca_client_id("ca") != _ca_client_id("us")


def test_ca_client_is_the_apk_confirmed_id() -> None:
    # pin the exact APK-confirmed literal so a future refactor cannot swap it.
    assert _CA_CLIENT_ID == "69eb3c39-d2be-4006-8197-37cc4971e8fe_MYVW_ANDROID"


# ── per-country OIDC proxy (live-probe grounded) ──────────────────────────────
# ca00 /oidc/v1/authorize 302s to the en-CA sign-in with the CA client (and 400s
# with the US client); us00 is the mirror for US. Routing CA through us00 landed
# CA accounts on the US sign-in whose password POST 500s (#990, #659).

def test_ca_authorizes_on_its_own_ca00_host() -> None:
    url = _client("ca")._authorize_url
    assert "ca00" in url and "us00" not in url


def test_us_authorizes_on_us00_unchanged() -> None:
    assert "us00" in _client("us")._authorize_url
