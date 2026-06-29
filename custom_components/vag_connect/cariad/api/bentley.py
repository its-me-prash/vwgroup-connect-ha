# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bentley My Bentley API client — Cariad-BFF backend.

v2.14.11 — ACTIVATED (login + read). The 2026-06-18 app-atlas resolved the
former placeholders from ``uk.co.bentley.mybentley``: the production IDK
client_id (``idkClientIDLive`` in the app's ``url-configuration.json``) is
byte-identical to Audi's primary, and the redirect_uri is ``mybentleyapp:///``
(both now set in ``BRAND_BENTLEY``). Wired into ``CariadClientFactory``,
``BRANDS`` and the config-flow UI.

Bentley runs on the Audi IDK client + tenant (Bentley = Audi platform), so
the data path inherits unchanged from ``VWEUClient``.

**Two-way is still live-test gated:** the qmauth/CARIAD assertion headers are
gated to audi/volkswagen in ``idk.py``, so Bentley's classic token exchange
degrades to the read-only data_act_portal until a tester with a real My
Bentley account confirms the Audi qmauth secret is accepted for client
09b6cbec under the bentleyid tenant. At that point ``"bentley"`` is added to
those gates to unlock commands.
"""

from __future__ import annotations

import logging

from aiohttp import ClientSession

from ..models import BRAND_BENTLEY
from .vw_eu import VWEUClient

_LOGGER = logging.getLogger(__name__)


class BentleyClient(VWEUClient):
    """Bentley My Bentley client — Cariad-BFF for data, no AZS exchange.

    Inherits the full data-fetch + command-send surface from
    ``VWEUClient``. The only brand-specific override is the
    ``BRAND_BENTLEY`` binding passed to the base ``__init__``.

    Unlike ``AudiClient`` (which exchanges for an AZS token to fetch
    vgql render images), Bentley doesn't have a separate vgql
    endpoint — vehicle images come from the standard Cariad-BFF
    image endpoint. So we don't need a separate token exchange.

    v2.14.11 — activated (login + read). ``BRAND_BENTLEY.client_id`` +
    ``redirect_uri`` are atlas-confirmed; two-way is live-test gated.
    """

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        # Must call CariadBaseClient directly — VWEUClient hardcodes
        # BRAND_VW_EU in its own __init__. Same pattern as AudiClient
        # + LamboClient.
        from .base import CariadBaseClient  # noqa: PLC0415

        CariadBaseClient.__init__(
            self, session, BRAND_BENTLEY, email, password, spin
        )
        _LOGGER.info(
            "Bentley client instantiated (Audi IDK tenant; read-only until "
            "two-way live-test). Brand: %s",
            BRAND_BENTLEY.name,
        )
