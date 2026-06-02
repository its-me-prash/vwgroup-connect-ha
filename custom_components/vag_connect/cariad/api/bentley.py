# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Bentley My Bentley API client — Cariad-BFF backend (scaffold).

**BETA — TESTER VALIDATION PENDING.** This module ships as scaffolding
only. The class compiles, imports cleanly, and inherits the full
VWEUClient feature set, but the OAuth ``client_id`` and ``redirect_uri``
in ``BRAND_BENTLEY`` (``cariad/models.py``) are PLACEHOLDERS that need
a tester with a My Bentley app install to confirm via mitmproxy /
Charles inspection of the production login flow.

Sister-PR to PR #15 (Lamborghini Unica scaffold) — identical pattern
because both luxury brands share the Cariad-BFF backend with VW EU
+ Audi. The only per-brand delta is the OAuth client_id +
redirect_uri + UA header.

Until tester confirms values:
- The class is NOT wired into ``CariadClientFactory``
- The brand is NOT exposed in the config-flow UI
- A power-user / tester can manually instantiate ``BentleyClient(...)``
  in a debug-script to exercise the IDK login and report back

"Two roads diverged in a wood, and I took the one beta-gated."
— Robert Frost, paraphrased for VAG-luxury onboarding
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

    v2.2.0 PR #16/20 — scaffold. Activation requires tester to
    confirm ``BRAND_BENTLEY.client_id`` + ``redirect_uri``.
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
            "Bentley client instantiated (BETA scaffold — client_id is "
            "placeholder until tester validation). Brand: %s",
            BRAND_BENTLEY.name,
        )
