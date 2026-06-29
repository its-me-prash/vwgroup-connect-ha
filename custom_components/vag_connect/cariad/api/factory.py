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
from .bentley import BentleyClient


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
    ) -> CariadBaseClient | PorscheClient | VWNAClient:
        """Return an authenticated-ready client for the given brand.

        Supported brands:
          volkswagen    — VW EU (WeConnect ID, EMEA BFF)
          audi          — Audi EU (myAudi, EMEA BFF)
          skoda         — Škoda (MyŠkoda, mysmob.api.connect.skoda-auto.cz)
          seat          — SEAT (OLA server)
          cupra         — CUPRA (OLA server)
          volkswagen_na — VW North America (US/CA, b-h-s.spr.{cc}00.p.con-veh.net)
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
        if lower == "porsche":
            return PorscheClient(session, email, password, spin)
        if lower == "bentley":
            # v2.14.11 — Bentley on the Audi IDK client/tenant; read-only
            # until the qmauth two-way gates include "bentley" (live-test).
            return BentleyClient(session, email, password, spin)
        raise ValueError(
            f"Unknown brand '{brand}'. Supported: "
            "volkswagen, audi, skoda, seat, cupra, volkswagen_na, porsche, bentley"
        )
