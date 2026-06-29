# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""CUPRA-standalone API client — brand-isolated backend (scaffold).

**BETA — TESTER VALIDATION PENDING.** Third luxury/standalone scaffold
in Phase 4 alongside ``lambo.py`` (PR #15) and ``bentley.py`` (PR #16),
but with a meaningfully different inheritance story:

  - Lambo / Bentley → ``VWEUClient`` (Cariad-BFF backend, same as VW/Audi)
  - CUPRA-standalone → ``SeatCupraClient`` (OLA-flavoured backend, same
    parser surface as the existing CUPRA path)

**What's distinct from existing CUPRA (``seat_cupra.py``)**: the current
CUPRA integration goes through the shared SEAT/CUPRA OLA backend
(``ola.prod.code.seat.cloud.vwgroup.com``). Per pycupra commit 0f3b1c7
+ multiple 2026-Q1/Q2 community reports, CUPRA Connect is progressively
migrating to a brand-isolated backend (rumoured host
``cupra-api.vwgroup.io``) expected to fully cut over by 2026-H2.

Once a tester's account flips to the standalone backend, they can:

  1. Confirm the actual host (currently PLACEHOLDER in BRAND_CUPRA_STANDALONE)
  2. Exercise the parser against the cut-over response shapes
  3. Report back which endpoints stayed identical vs. drifted

This scaffold inherits ``SeatCupraClient`` so 95% of the parser surface
is already correct (OLA-flavoured JSON, same authentication, same
capability schema). The only override is the API base host via
``BRAND_CUPRA_STANDALONE``.

Until tester validation:
- NOT wired into ``CariadClientFactory``
- NOT exposed in the config-flow UI
- A tester can manually instantiate ``CupraStandaloneClient(...)``
  in a debug-script

"In our profession, precision matters. Especially when reserving
brand-IDs for backend cut-overs that haven't fully cut over yet."
— Leonard Hofstadter, on defensive scaffolding
"""

from __future__ import annotations

import logging

from aiohttp import ClientSession

from ..models import BRAND_CUPRA_STANDALONE
from .seat_cupra import SeatCupraClient

_LOGGER = logging.getLogger(__name__)


class CupraStandaloneClient(SeatCupraClient):
    """CUPRA-standalone client — brand-isolated backend (scaffold).

    Inherits the full data-fetch + command-send surface from
    ``SeatCupraClient`` (same parser shape, same OLA-flavoured JSON).
    The only delta is the API base host, configured via
    ``BRAND_CUPRA_STANDALONE``.

    v2.2.0 PR #17/20 — scaffold. Activation requires tester to
    confirm ``BRAND_CUPRA_STANDALONE.api_base`` once the backend
    cut-over reaches their account. Parser-divergence (if any) will
    be addressed in follow-up PRs based on tester response-dumps.
    """

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        # Bypass ``SeatCupraClient.__init__``'s brand-string parameter
        # (which only knows "seat" / "cupra") and bind directly to
        # BRAND_CUPRA_STANDALONE via the grandparent base.
        from .base import CariadBaseClient  # noqa: PLC0415

        CariadBaseClient.__init__(
            self, session, BRAND_CUPRA_STANDALONE, email, password, spin
        )
        self._user_id: str | None = None
        _LOGGER.info(
            "CUPRA-standalone client instantiated (BETA scaffold — "
            "api_base is placeholder until tester validation). Brand: %s",
            BRAND_CUPRA_STANDALONE.name,
        )
