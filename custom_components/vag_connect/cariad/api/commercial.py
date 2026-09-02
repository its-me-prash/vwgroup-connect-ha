# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Volkswagen Commercial Vehicles (Nutzfahrzeuge) client — EU Data Act portal.

#1316 — VW Commercial Vehicles is a SEPARATE EU Data Act data-controller realm
from passenger VW: on one account the ID.3 lives in the passenger realm and a
T6.1 in the commercial realm, each with its own consent + data delivery. The
native BFF/IDK path is attestation-walled exactly like passenger VW, so this
brand reads through the read-only EU-Data-Act portal, where the SOLE difference
is the OIDC ``state_brand`` ``VOLKSWAGEN_COMMERCIAL_VEHICLES`` (live-confirmed
2026-09-02; wired in ``cariad/auth/_eu_data_act.py``). The data + command surface
is inherited unchanged from ``VWEUClient``.
"""
from __future__ import annotations

import logging

from aiohttp import ClientSession

from ..models import BRAND_VW_COMMERCIAL
from .vw_eu import VWEUClient

_LOGGER = logging.getLogger(__name__)


class VWCommercialClient(VWEUClient):
    """VW Commercial Vehicles client — reads via the EU Data Act portal.

    Mirrors ``BentleyClient``: ``VWEUClient`` hardcodes ``BRAND_VW_EU`` in its own
    ``__init__``, so we must call ``CariadBaseClient.__init__`` directly with
    ``BRAND_VW_COMMERCIAL`` — that distinct brand name is what steers the portal
    OIDC state to the commercial realm (``base.py`` builds the state from
    ``self._brand.name``). Native BFF is attestation-walled (same as passenger
    VW), so the strategy chain resolves straight to ``data_act_portal``.
    """

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        from .base import CariadBaseClient  # noqa: PLC0415

        CariadBaseClient.__init__(
            self, session, BRAND_VW_COMMERCIAL, email, password, spin
        )
        _LOGGER.info(
            "VW Commercial Vehicles client instantiated (EU Data Act portal, "
            "read-only; commercial realm). Brand: %s",
            BRAND_VW_COMMERCIAL.name,
        )
