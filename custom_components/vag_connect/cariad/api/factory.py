# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Factory for creating the correct brand API client."""

from __future__ import annotations

from aiohttp import ClientSession

from .base import CariadBaseClient
from .vw_eu import VWEUClient
from .audi import AudiClient
from .skoda import SkodaClient
from .seat_cupra import SeatCupraClient
from .porsche import PorscheClient
from .vw_na import VWNAClient
from .audi_na import AudiNAClient
from .bentley import BentleyClient
from .commercial import VWCommercialClient
from .plugandplay import PlugAndPlayCloudClient
from .skoda_official import SkodaOfficialClient


class CariadClientFactory:
    """Instantiate the correct API client for a given brand."""

    @staticmethod
    def create(
        brand: str,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
        country: str = "us",
        ola_app_version_override: str | None = None,
        ola_user_agent_override: str | None = None,
    ) -> (
        CariadBaseClient | PorscheClient | VWNAClient
        | PlugAndPlayCloudClient | SkodaOfficialClient
    ):
        """Return an authenticated-ready client for the given brand.

        Supported brands:
          volkswagen    — VW EU (WeConnect ID, EMEA BFF)
          volkswagen_commercial — VW Commercial Vehicles / Nutzfahrzeuge
                          (EU-Data-Act portal realm, read-only)
          audi          — Audi EU (myAudi, EMEA BFF)
          skoda         — Škoda (MyŠkoda, mysmob.api.connect.skoda-auto.cz)
          seat          — SEAT (OLA server)
          cupra         — CUPRA (OLA server)
          volkswagen_na — VW North America (US/CA, b-h-s.spr.{cc}00.p.con-veh.net)
          audi_na       — Audi North America (myAudi US/CA; the CARIAD BFF in
                          the NA region, the same client family as Audi EU)
          porsche       — Porsche Connect (Auth0, api.ppa.porsche.com)
          bentley       — Bentley (My Bentley, Audi IDK client/tenant; read-only)

        v2.4.1 (#281+#282) — ``ola_*_override`` kwargs are forwarded
        only to SEAT/CUPRA clients (OLA defense-in-depth Layer 2). All
        other brands ignore them. ``None`` = use built-in defaults
        from ``cariad/_ola_headers.py``.
        """
        lower = brand.lower()
        if lower == "volkswagen":
            return VWEUClient(session, email, password, spin)
        if lower == "volkswagen_commercial":
            # #1316 — VW Commercial Vehicles (Nutzfahrzeuge): a separate EU-Data-Act
            # realm, reads via the portal (state_brand VOLKSWAGEN_COMMERCIAL_VEHICLES).
            return VWCommercialClient(session, email, password, spin)
        if lower == "audi":
            return AudiClient(session, email, password, spin)
        if lower == "skoda":
            return SkodaClient(session, email, password, spin)
        if lower in ("seat", "cupra"):
            return SeatCupraClient(
                session, lower, email, password, spin,
                ola_app_version_override=ola_app_version_override,
                ola_user_agent_override=ola_user_agent_override,
            )
        if lower == "volkswagen_na":
            return VWNAClient(session, email, password, spin, country=country)
        if lower == "audi_na":
            # Audi US/CA. NOT the VW North America stack above: ``AudiNAClient``
            # is a ``VWEUClient`` on the CARIAD BFF in the NA region (see
            # audi_na.py), so it takes ``CariadBaseClient.authenticate`` and the
            # base refresh path, exactly like Audi EU.
            #
            # #1813 review finding: this comment used to call it a subclass of
            # ``VWNAClient`` with its client id still pending. Neither was true
            # when the class was added in v2.19.0 or at any time since, and it
            # matters which one it is:
            # ``VWNAClient`` signs in on its own and has no check for an entry
            # that holds no password; that check lives in ``CariadBaseClient``.
            # Audi US/CA is the one North America brand with a code sign-in, so
            # it needs that check and gets it from ``CariadBaseClient``. tests/
            # test_1813_passwordless_brands_carry_the_guard.py holds that.
            return AudiNAClient(session, email, password, spin, country=country)
        if lower == "porsche":
            return PorscheClient(session, email, password, spin)
        if lower == "bentley":
            # v2.14.11 — Bentley on the Audi IDK client/tenant; read-only
            # until the qmauth two-way gates include "bentley" (live-test).
            return BentleyClient(session, email, password, spin)
        if lower == "audi_acpp":
            # plug&play OBD-dongle cloud reader (Audi acpp). Read-only and its
            # own silo (token is NOT BFF-whitelisted). Takes a BrandConfig, not a
            # brand string, so IDKAuth uses the plain-OAuth (no x-qmauth) branch.
            from ..models import BRAND_AUDI_ACPP
            return PlugAndPlayCloudClient(
                session, BRAND_AUDI_ACPP, email, password, spin
            )
        if lower == "skoda_official":
            # Škoda OFFICIAL public API (opt-in) — first-party, attestation-free,
            # X-API-Key auth (no OAuth). No BrandConfig needed. The VIN(s) ride the
            # ``email`` slot (comma-separated) and the API key the ``password`` slot.
            from .skoda_official import SkodaOfficialClient
            return SkodaOfficialClient(session, email, password, spin)
        raise ValueError(
            f"Unknown brand '{brand}'. Supported: "
            "volkswagen, volkswagen_commercial, audi, skoda, seat, cupra, "
            "volkswagen_na, audi_na, porsche, bentley"
        )
