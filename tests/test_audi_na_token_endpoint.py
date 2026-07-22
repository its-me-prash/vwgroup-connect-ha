# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#13 — Audi US/CA legacy token exchange must hit the NA IDP, not the EU BFF.

Live report (coreywillwhat, a real US Audi): the email/password login itself
works — the redirects complete and an authorization code comes back — but the
token exchange then fails with ``HTTP 400 {"error":"invalid key id"}``.

Root cause: the code is issued by the NA IDP (``identity.na.vwgroup.io``), but
``_NA_TOKEN_URL`` pointed the exchange at the EU BFF
(``emea.bff.cariad.digital/auth/v1/idk/oidc/token``). The EU BFF has no signing
key matching the NA code's ``kid`` → "invalid key id". READS legitimately go to
emea.bff (there is no na.bff host), but the TOKEN exchange + refresh must go to
the IDP that issued the code — the same endpoint the device-grant path already
uses (``_NA_IDP_TOKEN_URL``).
"""

from __future__ import annotations


class TestAudiNaTokenEndpoint:
    def test_na_token_url_is_the_na_idp_not_the_eu_bff(self) -> None:
        from custom_components.vag_connect.cariad.api.audi_na import (
            _NA_IDP_BASE,
            _NA_TOKEN_URL,
        )

        assert _NA_TOKEN_URL == "https://identity.na.vwgroup.io/oidc/v1/token"
        assert _NA_TOKEN_URL == f"{_NA_IDP_BASE}/oidc/v1/token"
        # never route the NA-issued code back to the EU BFF again (#13)
        assert "emea.bff" not in _NA_TOKEN_URL
        assert "/auth/v1/idk/oidc/token" not in _NA_TOKEN_URL

    def test_legacy_exchange_and_device_grant_share_the_na_token_endpoint(self) -> None:
        # The authorization_code exchange (legacy login) and the device-grant
        # refresh must agree on the endpoint — both hit the NA IDP.
        from custom_components.vag_connect.cariad.api.audi_na import _NA_TOKEN_URL
        from custom_components.vag_connect.cariad.auth._device_grant import (
            _NA_IDP_TOKEN_URL,
        )

        assert _NA_TOKEN_URL == _NA_IDP_TOKEN_URL

    def test_reads_still_target_emea_bff(self) -> None:
        # The fix must NOT move reads — the NA app has no na.bff host, reads
        # stay on the global emea.bff. Only the token endpoint moved.
        from custom_components.vag_connect.cariad.api.audi_na import (
            _NA_BFF_BASE,
            BRAND_AUDI_NA,
        )

        assert _NA_BFF_BASE == "https://emea.bff.cariad.digital"
        assert BRAND_AUDI_NA.api_base == "https://emea.bff.cariad.digital"
