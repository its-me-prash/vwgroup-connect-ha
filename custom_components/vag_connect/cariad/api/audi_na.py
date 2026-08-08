# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audi North America (myAudi US / CA) — regional CARIAD-BFF client.

LIVE-VERIFIED architecture (US account, 2026-08-08): US Audi uses the
EU-Audi CARIAD-BFF stack in the NA region, not the VW-NA ``con-veh`` backend.
This client therefore mirrors EU ``AudiClient`` on ``VWEUClient`` with the NA
IDP, public client ID, and US data host:

  · client_id  ``7c6b4634-…@apps_vw-dilab_com``   (``BRAND_AUDI_NA``)
  · authorize  ``identity.na.vwgroup.io/oidc/v1/authorize``
  · token      ``na.bff.cariad.digital/auth/v1/idk/oidc/token``
  · reads      ``na.bff.cariad.digital/vehicle/v1/vehicles/{vin}/selectivestatus``

The RFC-8628 device grant returns an identity.na access token with
``jtt=access_token``. That token is accepted directly by the US data BFF. Sending
the same token to the EMEA garage produces 401 ``expected user token``; exchanging
it for an Audi retail/AZS token produces 403 ``invalid token type``. The 401 was
therefore a region mismatch, not evidence of a missing token exchange.

The market configuration is authoritative because these endpoints are supplied
at runtime and need not appear in the APK DEX. Its
``connectedVehicleVehicleServiceBaseURLProduction`` currently maps US to
``na.bff.cariad.digital`` and CA to ``emea.bff.cariad.digital``. Route reads by
the configured country so fixing US does not change the Canadian path. CA still
uses browser/device-code login because its token endpoint is attestation-gated;
a live Canadian read remains to be confirmed (#13).
"""

from __future__ import annotations

from aiohttp import ClientSession

from ..models import BRAND_AUDI_NA, VehicleData
from ..auth.idk import IDKAuth
from .vw_eu import VWEUClient

# v2.24.0 (#13) — TOKEN EXCHANGE: the endpoint was wrong, and that is the whole
# reason NA login never worked. Both of these were probed live (unauthenticated,
# a deliberately invalid code, same client id and body in each):
#
#   POST identity.na.vwgroup.io/oidc/v1/token
#     -> 401 {"error":"invalid_client","error_description":"Request requires a
#             valid client authentication method but is missing client_secret
#             for clientId 7c6b4634-..."}          <- exactly the #13 symptom
#   POST na.bff.cariad.digital/auth/v1/idk/oidc/token
#     -> 400 {"error":"Bad Request"}               <- rejects the CODE, not the client
#
# The IDP's raw /oidc/v1/token is the CONFIDENTIAL-client endpoint and demands a
# client_secret. Audi's IDK is a public PKCE client and has no secret to give,
# which is why "just add a client_secret" never helped: it was the wrong endpoint,
# not a missing credential. The CARIAD BFF proxy accepts the public client.
# ``na.bff.cariad.digital`` has zero hits in the DEX because, like the NA client
# id itself, it is supplied at runtime by the US market config.
_NA_BFF_BASE = "https://na.bff.cariad.digital"
_EMEA_BFF_BASE = "https://emea.bff.cariad.digital"
_NA_IDP_BASE = "https://identity.na.vwgroup.io"
_NA_AUTHORIZE_URL = f"{_NA_IDP_BASE}/oidc/v1/authorize"
_NA_TOKEN_URL = "https://na.bff.cariad.digital/auth/v1/idk/oidc/token"


class AudiNAClient(VWEUClient):
    """myAudi US / CA — CARIAD-BFF NA. Mirrors ``AudiClient`` with NA endpoints."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
        country: str = "us",
    ) -> None:
        # Mirror AudiClient: build on CariadBaseClient directly (VWEUClient's
        # __init__ hardcodes BRAND_VW_EU), with the NA Audi brand config.
        from .base import CariadBaseClient  # noqa: PLC0415
        CariadBaseClient.__init__(self, session, BRAND_AUDI_NA, email, password, spin)
        self._country = (country or "us").lower()
        # NA auth: authorize at the NA IDP, exchange the code at na.bff. The base
        # default IDKAuth targets the EU IDP (identity.vwgroup.io), so rebind with
        # the NA overrides — the same pattern vw_na.py uses.
        self._auth = IDKAuth(
            session,
            BRAND_AUDI_NA,
            authorize_url_override=_NA_AUTHORIZE_URL,
            token_url_override=_NA_TOKEN_URL,
            idk_base_override=_NA_IDP_BASE,
        )

    def _market_bff_base(self) -> str:
        """Return the data BFF advertised by the selected market."""
        return _EMEA_BFF_BASE if self._country == "ca" else _NA_BFF_BASE

    def _garage_base(self) -> str:
        """Route vehicle discovery to the selected market's data BFF."""
        return self._market_bff_base()

    def _base_for_vin(self, vin: str) -> str:  # noqa: ARG002
        """Route vehicle reads without the EU per-VIN HomeRegion split."""
        return self._market_bff_base()

    async def get_status(self, vin: str) -> VehicleData:  # type: ignore[override]
        """Inherit the CARIAD-BFF selectivestatus read (NA host via _base_for_vin);
        just stamp the manufacturer (BRAND_AUDI_NA.name is ``audi_na``)."""
        d = await super().get_status(vin)
        d.manufacturer = "Audi"
        return d
