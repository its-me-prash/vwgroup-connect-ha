# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lamborghini Unica API client — NOT a Cariad-BFF brand (do NOT wire).

v2.14.11 — the 2026-06-18 app-atlas (``lamborghini.connectedcar``) DISPROVED
the original "same Cariad-BFF as Audi/VW EU" assumption. Lamborghini Unica:
- ships **NO** ``@apps_vw-dilab_com`` IDK client_id anywhere in the APK;
- authenticates via **MBB co-auth proxied through Lamborghini's own SDP
  gateway**: token endpoint ``https://sdp.lamborghini.com/unicav2/mbbcoauth``,
  scope ``sc2:fal``; the real VW MBB client_id is held SERVER-SIDE on the SDP
  proxy and is never shipped in the app;
- uses AWS Cognito only as an analytics identity-pool (Pinpoint), not login.

Therefore this ``LamboClient(VWEUClient)`` subclass is the WRONG shape — the
IDK/Cariad-BFF login path it inherits cannot speak the SDP-proxy MBB flow, and
``BRAND_LAMBO.api_base = emea.bff.cariad.digital`` is incorrect. Integrating
Lamborghini needs a dedicated SDP-proxy MBB-co-auth adapter (Tier-3 project)
whose request shape can only be derived from a live mitmproxy capture of a
real Unica login — not from static APK analysis.

Kept as documentation only: NOT wired into ``CariadClientFactory`` / ``BRANDS``
/ config-flow, and must stay that way until the SDP-proxy adapter exists.
"""

from __future__ import annotations

import logging

from aiohttp import ClientSession

from ..models import BRAND_LAMBO
from .vw_eu import VWEUClient

_LOGGER = logging.getLogger(__name__)


class LamboClient(VWEUClient):
    """Lamborghini Unica — placeholder subclass, structurally WRONG, NOT wired.

    Inherits ``VWEUClient`` only because the brand was originally (mis)assumed
    to be a Cariad-BFF brand. The atlas (v2.14.11) proved Unica uses an
    SDP-proxy MBB co-auth flow (see module docstring), which this IDK subclass
    cannot perform. Do NOT instantiate in production — a dedicated SDP-proxy
    MBB adapter is required first (Tier-3). Retained as documentation of why.
    """

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        # Must call CariadBaseClient directly — VWEUClient hardcodes
        # BRAND_VW_EU in its own __init__. Same pattern as AudiClient.
        from .base import CariadBaseClient  # noqa: PLC0415

        CariadBaseClient.__init__(
            self, session, BRAND_LAMBO, email, password, spin
        )
        _LOGGER.warning(
            "Lambo client instantiated, but Lamborghini Unica uses an "
            "SDP-proxy MBB flow this IDK client cannot speak — NOT wired for "
            "production. Brand: %s",
            BRAND_LAMBO.name,
        )
