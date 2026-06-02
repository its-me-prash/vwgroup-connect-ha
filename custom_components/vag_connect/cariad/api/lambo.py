# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Lamborghini Unica API client — Cariad-BFF backend (scaffold).

**BETA — TESTER VALIDATION PENDING.** This module ships as scaffolding
only. The class compiles, imports cleanly, and inherits the full
VWEUClient feature set, but the OAuth ``client_id`` and ``redirect_uri``
in ``BRAND_LAMBO`` (``cariad/models.py``) are PLACEHOLDERS that need
a tester with a Lamborghini Unica app install to confirm via
mitmproxy / Charles inspection of the production login flow.

Until those values are confirmed:
- The class is NOT wired into ``CariadClientFactory``
- The brand is NOT exposed in the config-flow UI
- A power-user / tester can manually instantiate ``LamboClient(...)``
  in a debug-script to exercise the IDK login and report back what
  succeeds or fails

Inheritance rationale (from API-Evangelist OpenAPI catalog metadata,
2026-05-03):

- Lamborghini Unica is a VAG luxury brand fronted by the same
  Cariad-BFF host (``emea.bff.cariad.digital``) as VW EU + Audi
- Vehicle-data endpoints, capability schema, charging settings —
  all share the parent contract via ``VWEUClient``
- The only brand-specific delta is the IDK ``client_id`` /
  ``redirect_uri`` (login flow) and the User-Agent header

This file is intentionally minimal: subclass + ``BRAND_LAMBO``
binding. When tester confirms values, the binding fills in and
a single one-line addition to ``factory.py`` enables the brand.

"And that's why you always leave a note." — Marshall Eriksen,
on shipping defensive scaffolding for unknown firmware
"""

from __future__ import annotations

import logging

from aiohttp import ClientSession

from ..models import BRAND_LAMBO
from .vw_eu import VWEUClient

_LOGGER = logging.getLogger(__name__)


class LamboClient(VWEUClient):
    """Lamborghini Unica client — Cariad-BFF for data, no AZS exchange.

    Inherits the full data-fetch + command-send surface from
    ``VWEUClient``. The only brand-specific override is the
    ``BRAND_LAMBO`` binding passed to the base ``__init__``.

    Unlike ``AudiClient`` (which exchanges for an AZS token to fetch
    vgql render images), Lamborghini doesn't have a separate vgql
    endpoint — vehicle images come from the standard Cariad-BFF
    image endpoint. So we don't need a separate token exchange.

    v2.2.0 PR #15/20 — scaffold. Activation requires tester to
    confirm ``BRAND_LAMBO.client_id`` + ``redirect_uri``.
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
        _LOGGER.info(
            "Lambo client instantiated (BETA scaffold — client_id is "
            "placeholder until tester validation). Brand: %s",
            BRAND_LAMBO.name,
        )
