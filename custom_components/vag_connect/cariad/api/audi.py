# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Audi EU API client — CARIAD BFF + AZS token for vgql image fetching.

Vehicle data uses the IDK Bearer token against the CARIAD BFF (same as VW EU).
Image fetching uses the AZS (Audi Authorization Server) token, obtained by
exchanging the IDK access_token at the Audi token proxy endpoint.

AZS token exchange (clean-room reimplementation):
  POST https://emea.bff.cariad.digital/login/v1/audi/token
  Body: {"token": <idk_access_token>, "grant_type": "id_token",
         "stage": "live", "config": "myaudi"}
  → access_token valid for app-api.live-my.audi.com/vgql/v1/graphql

Source: arjenvrh/upstream (MIT) — token exchange pattern
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ..exceptions import SpinError
from ..models import BRAND_AUDI
from .graphql import VehicleImageData, VehicleImageFetcher
from .vw_eu import VWEUClient

_LOGGER = logging.getLogger(__name__)

_AZS_TOKEN_URL  = "https://emea.bff.cariad.digital/login/v1/audi/token"
_GRAPHQL_URL    = "https://app-api.live-my.audi.com/vgql/v1/graphql"
_APP_VERSION    = "4.31.0"
_USER_AGENT     = "Android/4.31.0 (Build 800341641.root project 'myaudi_android'.ext.buildTime) Android/13"

# v1.14.0 (#28) — Audi ICE Remote Engine Start (CARIAD BFF, two-step S-PIN flow).
# Source: arjenvrh/upstream PR #717 (`audi_services.py`). The path is
# ``/vehicle/v1/engine/{VIN}/...`` — note: NOT under ``/vehicles/{VIN}/engine``.
# VIN must be uppercased in the URL — confirmed in upstream PR.
_ENGINE_BASE = "https://emea.bff.cariad.digital/vehicle/v1/engine"


class AudiClient(VWEUClient):
    """Audi EU client — CARIAD BFF for data, AZS token for render images."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        # Must call CariadBaseClient directly — VWEUClient hardcodes BRAND_VW_EU
        from .base import CariadBaseClient  # noqa: PLC0415
        CariadBaseClient.__init__(self, session, BRAND_AUDI, email, password, spin)
        self._azs_token: str | None = None

    async def _exchange_azs_token(self) -> str | None:
        """Exchange IDK access_token for AZS (Audi portal) token.

        The vgql endpoint app-api.live-my.audi.com requires this token.
        One POST call — no second PKCE login needed.
        Returns the AZS access_token or None on failure.
        """
        try:
            async with self._session.post(
                _AZS_TOKEN_URL,
                json={
                    "token":      self._access_token,
                    "grant_type": "id_token",
                    "stage":      "live",
                    "config":     "myaudi",
                },
                headers={
                    "Accept":        "application/json",
                    "Accept-Charset":"utf-8",
                    "X-App-Name":    "myAudi",
                    "X-App-Version": _APP_VERSION,
                    "User-Agent":    _USER_AGENT,
                    "Content-Type":  "application/json; charset=utf-8",
                },
                timeout=ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.warning(
                        "AZS token exchange failed HTTP %d: %s", resp.status, body[:200]
                    )
                    return None
                data = await resp.json()
                token = data.get("access_token")
                if token:
                    _LOGGER.info("Audi AZS token acquired for image fetching")
                return str(token) if token else None
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("AZS token exchange error: %s", err)
            return None

    # ── v1.14.0 (#28) — ICE Remote Engine Start ─────────────────────────
    async def command_engine_start(self, vin: str, spin: str = "") -> None:
        """v1.14.0 (#28) — Audi ICE Remote Engine Start (two-step S-PIN flow).

        Step 1: ``PUT /vehicle/v1/engine/{VIN}/userpromptproof`` with
        ``{"spin": ...}`` returns a top-level ``userPromptProof`` token.
        Step 2: ``POST /vehicle/v1/engine/{VIN}/start`` with
        ``{"securedActivationData": <token>, "spin": ...}``.

        Raises ``SpinError`` if no S-PIN is configured. Wrong S-PIN /
        missing capability surface as ``APIError`` and are routed to
        ``classify_command_failure`` by the coordinator wrapper.

        Audi-only — VW EU does not expose this endpoint. Capability gating
        is recommended (see ``_capabilities.py:command_engine_start``).

        Source: arjenvrh/upstream PR #717 (audi_services.py).
        """
        pin = spin or self._spin
        if not pin:
            raise SpinError("S-PIN required for Audi engine start")
        vin_u = vin.upper()
        # Step 1 — proof. Response is read at the top level: {"userPromptProof": "..."}.
        proof_resp: Any = await self._request(
            "PUT",
            f"{_ENGINE_BASE}/{vin_u}/userpromptproof",
            json={"spin": pin},
        )
        secured = (
            proof_resp.get("userPromptProof") if isinstance(proof_resp, dict) else None
        )
        if not isinstance(secured, str) or not secured:
            raise SpinError(
                "Audi engine start: missing userPromptProof in response — "
                "S-PIN may be wrong or vehicle does not support engine start"
            )
        # Step 2 — start. Body uses the proof token from step 1.
        await self._post(
            f"{_ENGINE_BASE}/{vin_u}/start",
            json={"securedActivationData": secured, "spin": pin},
        )

    async def command_engine_stop(self, vin: str) -> None:
        """v1.14.0 (#28) — Audi ICE Remote Engine Stop.

        Single ``POST /vehicle/v1/engine/{VIN}/stop`` with no body. No S-PIN
        required (mirrors upstream PR #717).
        """
        vin_u = vin.upper()
        await self._post(f"{_ENGINE_BASE}/{vin_u}/stop")

    async def fetch_images(self) -> None:
        """Override: exchange IDK→AZS token, call app-api.live-my.audi.com."""
        if not self._azs_token:
            self._azs_token = await self._exchange_azs_token()

        if not self._azs_token:
            _LOGGER.debug("Audi images: no AZS token yet — will exchange on next call")
            self._image_data = {}
            return

        try:
            fetcher = VehicleImageFetcher(self._session)
            data: dict[str, VehicleImageData] = await fetcher.fetch_image_data(
                self._azs_token, "audi", graphql_url=_GRAPHQL_URL
            )
            if data:
                self._image_data = data
                _LOGGER.info(
                    "Audi images:  render URLs for %d vehicle(s)", len(data)
                )
            else:
                # AZS token might have expired — reset to force re-exchange next time
                self._azs_token = None
                _LOGGER.warning("Audi images: empty response from vgql — AZS token reset for retry")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Audi image fetch failed: %s", err)
            self._azs_token = None
            self._image_data = {}
