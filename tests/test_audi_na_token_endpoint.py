# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#13 — where the Audi US/CA token exchange has to go, and why.

History, because this endpoint moved twice:

v2.22.1 moved the exchange OFF the EU BFF. That was right: the code is issued by
the NA IDP, and the EU BFF has no signing key for its ``kid``, so it answered
``400 {"error":"invalid key id"}`` (coreywillwhat, a real US Audi).

v2.24.0 moved it again, because the NA IDP's own ``/oidc/v1/token`` was still not
the right door. Live probes, unauthenticated, deliberately invalid codes, same
client id and body each time:

    POST identity.na.vwgroup.io/oidc/v1/token       grant=authorization_code
      -> 401 invalid_client "missing client_secret for clientId 7c6b4634-..."
    POST na.bff.cariad.digital/auth/v1/idk/oidc/token  grant=authorization_code
      -> 400 Bad Request            (rejects the CODE, having accepted the client)

    POST identity.na.vwgroup.io/oidc/v1/token       grant=device_code
      -> 400 expired_token          (client accepted)
    POST na.bff.cariad.digital/auth/v1/idk/oidc/token  grant=device_code
      -> 400 expired_token          (client accepted)

So the IDP demands client authentication for the authorization_code grant only.
Audi's IDK is a public PKCE client with no secret to offer, which is why adding a
client_secret never helped: it was the wrong endpoint, not a missing credential.
The device_code grant is accepted without a secret on BOTH hosts, which is why
the QR path always worked while email/password login never did.

Consequence: the two flows legitimately use DIFFERENT endpoints, and pinning them
to the same one (as this file used to) would re-break the login.

Still live-gated: the 400 proves the client is accepted, not that a real code
completes. Needs a confirming capture on a real US/CA Audi.
"""

from __future__ import annotations


class TestAudiNaTokenEndpoint:
    def test_legacy_exchange_uses_the_bff_proxy_not_the_raw_idp(self) -> None:
        from custom_components.vag_connect.cariad.api.audi_na import _NA_TOKEN_URL

        # The BFF proxy accepts the public PKCE client; the raw IDP token
        # endpoint demands a client_secret we do not (and cannot) have.
        assert _NA_TOKEN_URL == "https://na.bff.cariad.digital/auth/v1/idk/oidc/token"
        # never route the NA-issued code back to the EU BFF again (the v2.22.1 bug)
        assert "emea.bff" not in _NA_TOKEN_URL
        # and never back to the confidential-client endpoint (the #13 bug)
        assert _NA_TOKEN_URL != "https://identity.na.vwgroup.io/oidc/v1/token"

    def test_authorize_still_targets_the_na_idp(self) -> None:
        # Only the TOKEN step moved. The code is still issued by the NA IDP.
        from custom_components.vag_connect.cariad.api.audi_na import (
            _NA_AUTHORIZE_URL,
            _NA_IDP_BASE,
        )

        assert _NA_IDP_BASE == "https://identity.na.vwgroup.io"
        assert _NA_AUTHORIZE_URL == f"{_NA_IDP_BASE}/oidc/v1/authorize"

    def test_device_grant_keeps_its_own_endpoint(self) -> None:
        # The device_code grant is accepted without client auth on the raw IDP,
        # so the QR path stays where it is. The two flows differ on purpose:
        # asserting they match is what this file used to do, and it is wrong.
        from custom_components.vag_connect.cariad.api.audi_na import _NA_TOKEN_URL
        from custom_components.vag_connect.cariad.auth._device_grant import (
            _NA_IDP_TOKEN_URL,
        )

        assert _NA_IDP_TOKEN_URL == "https://identity.na.vwgroup.io/oidc/v1/token"
        assert _NA_TOKEN_URL != _NA_IDP_TOKEN_URL

    def test_reads_still_target_emea_bff(self) -> None:
        # The fix must NOT move reads. The myAudi APK's only data BFF is the
        # global emea.bff; na.bff is the auth proxy, supplied by the US market
        # config at runtime (hence zero DEX hits for either it or the NA client id).
        from custom_components.vag_connect.cariad.api.audi_na import (
            BRAND_AUDI_NA,
            _NA_BFF_BASE,
        )

        assert _NA_BFF_BASE == "https://emea.bff.cariad.digital"
        assert BRAND_AUDI_NA.api_base == "https://emea.bff.cariad.digital"
