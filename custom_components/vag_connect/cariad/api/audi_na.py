# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audi North America (myAudi US / CA) — CARIAD-BFF NA login foundation.

LIVE-VERIFIED architecture (US myAudi market-config + NA OIDC discovery, sweep
2026-07-18): US Audi is the **EU-Audi CARIAD-BFF stack in the NA region** — NOT
the VW-NA ``con-veh`` backend. So this mirrors the EU ``AudiClient`` (itself a
CARIAD-BFF client on ``VWEUClient``) with the NA host / IDP / client_id, exactly
as ``AudiClient`` mirrors ``VWEUClient``:

  · client_id  ``7c6b4634-…@apps_vw-dilab_com``   (``BRAND_AUDI_NA``)
  · authorize  ``identity.na.vwgroup.io/oidc/v1/authorize``
  · token      ``na.bff.cariad.digital/auth/v1/idk/oidc/token``
  · reads      ``na.bff.cariad.digital/vehicle/v1/vehicles/{vin}/selectivestatus``

════════════════════════════════════════════════════════════════════════════
  DATA PLANE IS ATTESTATION-WALLED — this is a LOGIN FOUNDATION, not a working
  read path. ``na.bff.cariad.digital`` is the same CARIAD-BFF product as EU Audi,
  so vehicle reads will very likely 403 on the Play-Integrity / ``x-qmauth`` wall
  (#503/#464/#526) off-device — the same open problem as EU Audi, minus the EU
  Data Act portal fallback (the US has none). Auth is wired + real; a live US-Audi
  login is what confirms (1) the client_id is accepted and (2) whether the
  attestation wall blocks the token exchange / reads.
════════════════════════════════════════════════════════════════════════════

AUTH MODE — DAG is now WIRED (Prash's preferred clean auth): ``audi_na`` is in
``DAG_ENABLED_BRANDS`` and the browser-login flow drives RFC-8628 against the NA
IDP via ``dag_idp_urls`` + the per-instance URL overrides on
``DeviceAuthorizationGrant``. This client also carries the IDK-PKCE (password)
path as a fallback.

READ-PATH — corrected understanding: a community HA Audi-NA reference reads NA
vehicle data via the PASSWORD / authorization-code IDK bearer against
``na.bff.cariad.digital`` with NO attestation on the reads — the Play-Integrity
wall sits on the device-grant / registration flow, not the authcode read. So NA
reads may well work. The open, LIVE-GATED questions (a real US-Audi tester settles
all three): does the NA IDP expose ``/oidc/v1/device_authorization``, is client
7c6b4634 device-code-capable, and does a device-grant token (vs the password one)
read ``na.bff``.

Country: only the US market-config is live-verified. CA is accepted for interface
parity but currently reuses the US brand — a CA-specific market-config sweep
(``.../market/CA/en``) is a follow-up before CA can be trusted.

v2.29.1 — one CA question is now answered externally. A CA-account debug capture
(audi_connect_ha #814, 2026-08-05) showed the Canadian market config carries
``marketSupportsAppAttestation: True`` and its discovery document routes CA to
``token_endpoint = emea.bff.cariad.digital`` with ``device_code`` present in
``grant_types_supported``. So CA has attestation enforced, which is why a
password login there fails at the token step with the EU "invalid assertion
headers" body, and device-code is the way through — exactly the path this client
already drives (``audi_na`` is in ``DAG_ENABLED_BRANDS``). CA should therefore
use the browser/device-code login, not the password fallback; a live CA-Audi
tester is still what confirms it end to end (#13).
"""

from __future__ import annotations

from aiohttp import ClientSession

from ..models import BRAND_AUDI_NA, VehicleData
from ..auth.idk import IDKAuth
from .vw_eu import VWEUClient

# v2.20.0 (APK audit) — the current myAudi 5.6.0 app has NO ``na.bff.cariad.digital``
# string anywhere; its ONLY data BFF is the global ``emea.bff.cariad.digital`` (same
# host EU Audi uses). The NA split is ONLY at the IDP layer (authorize at
# identity.na.vwgroup.io). READS go to emea.bff (global).
#
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
# STILL LIVE-GATED: the 400 proves the client is accepted, not that a real code
# completes. Needs a confirming capture on a real US/CA Audi (#13).
_NA_BFF_BASE = "https://emea.bff.cariad.digital"
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

    def _base_for_vin(self, vin: str) -> str:  # noqa: ARG002
        """All NA reads target na.bff.cariad.digital. Overrides VWEUClient's EU
        per-VIN HomeRegion base (there is no EU HomeRegion split on the NA BFF)."""
        return _NA_BFF_BASE

    async def get_status(self, vin: str) -> VehicleData:  # type: ignore[override]
        """Inherit the CARIAD-BFF selectivestatus read (NA host via _base_for_vin);
        just stamp the manufacturer (BRAND_AUDI_NA.name is ``audi_na``)."""
        d = await super().get_status(vin)
        d.manufacturer = "Audi"
        return d
