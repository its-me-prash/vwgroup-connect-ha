# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
#
# ╔════════════════════════════════════════════════════════════════════╗
# ║ ACTIVATED v1.21.0 — wired for Audi/VW MBB legacy-path migration.  ║
# ║ Used by `vw_eu.py:command_wake` to discover per-VIN read-base      ║
# ║ when Cariad-BFF returns wrapper-404 (VIN is MBB-backed). See      ║
# ║ `cariad/_mbb.py` for the broader MBB-fallback architecture.       ║
# ╚════════════════════════════════════════════════════════════════════╝
"""HomeRegion resolution for CARIAD-BFF brands (VW EU + Audi).

Ported from ``evcc-io/evcc`` (``vehicle/vw/api.go``). Some VAG vehicles
do not live on the default ``emea.bff.cariad.digital`` host: a vehicle
imported from a non-EU region, or a US-spec VW EU model, may answer
status calls only through a region-specific gateway. The discovery
endpoint at ``mal-1a.prd.ece.vwg-connect.com`` returns the actual
base URI per VIN so the client can route subsequent calls correctly.

This module provides the **lookup helper** + **per-VIN cache**. It is
deliberately NOT wired into ``vw_eu.py`` URL builders yet — the default
``emea.bff.cariad.digital`` host works for the EU community we serve
today, and a 13-call-site refactor would risk regressing the 99%-EU
case for an edge-case fix. The helper is ready for wire-up in a future
PATCH release should a community member confirm that homeRegion
resolution fixes their setup (e.g. issue #75 follow-up, or an
imported-vehicle live test).

Wire-up plan when needed:
- ``VWEUClient.__init__`` adds ``self._vehicle_bases: dict[str, str] = {}``
- ``VWEUClient.get_vehicles`` calls ``resolve_home_region`` per new VIN
  and populates ``self._vehicle_bases``
- ``VWEUClient._base_for_vin(vin) -> str`` returns
  ``self._vehicle_bases.get(vin, _BASE)`` (sync — uses pre-cached value)
- All 13 ``f"{_BASE}/..."`` usages in ``vw_eu.py`` switch to
  ``f"{self._base_for_vin(vin)}/..."``
- Audi inherits via ``AudiClient(VWEUClient)`` — no extra changes

Privacy: VINs are not logged or sent anywhere — we only call the
manufacturer's own discovery endpoint with the user's existing token.

Reference: evcc-io/evcc ``vehicle/vw/api.go:HomeRegion()`` (2026-05).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Discovery endpoint base. Same for all CARIAD-BFF brands; the
# response payload tells us per-VIN which actual gateway to use.
DISCOVERY_BASE = "https://mal-1a.prd.ece.vwg-connect.com"

# Default base when discovery fails or no override is needed. EU
# community = 99% of the user base. Same constant as ``vw_eu._BASE``.
DEFAULT_BASE = "https://emea.bff.cariad.digital"

# Cache TTL — evcc uses no expiry but our HA process can run for
# weeks; 7 days strikes a balance between staleness (vehicle ownership
# transfer / re-import would need a re-resolve) and call frequency
# (one HTTP per VIN per week is harmless).
_CACHE_TTL = timedelta(days=7)


class HomeRegionCache:
    """Per-VIN resolved-base cache with TTL.

    Thread-safety note: HA's coordinator runs all CARIAD calls on the
    asyncio event loop, so simple dict mutation is safe here. We do
    not need an async lock for read/write.
    """

    def __init__(self) -> None:
        # vin -> (resolved_base, expires_at)
        self._entries: dict[str, tuple[str, datetime]] = {}

    def get(self, vin: str) -> str | None:
        """Return cached base for ``vin`` if still fresh, else ``None``."""
        entry = self._entries.get(vin)
        if not entry:
            return None
        base, expires_at = entry
        if datetime.now(tz=timezone.utc) >= expires_at:
            # Expired — drop and force re-resolve next time.
            self._entries.pop(vin, None)
            return None
        return base

    def set(self, vin: str, base: str) -> None:
        """Record ``base`` for ``vin`` with TTL ``_CACHE_TTL``."""
        expires_at = datetime.now(tz=timezone.utc) + _CACHE_TTL
        self._entries[vin] = (base, expires_at)

    def clear(self) -> None:
        """Wipe the cache (e.g. after Reauth or option change)."""
        self._entries.clear()


async def resolve_home_region(
    client: Any,
    vin: str,
    *,
    cache: HomeRegionCache | None = None,
) -> str:
    """Resolve the per-VIN base URI via the discovery endpoint.

    Uses ``cache`` if provided. On any error (4xx, 5xx, network,
    parse) returns ``DEFAULT_BASE`` — the integration must keep
    working even when the optional discovery call fails. Successful
    resolutions are cached.

    Args:
        client: A ``CariadBaseClient`` (or subclass) instance with a
            working ``_get`` method that handles auth.
        vin: The 17-character VIN to resolve.
        cache: Optional shared ``HomeRegionCache``. If omitted, every
            call hits the network — useful for tests; production code
            should always pass an instance.

    Returns:
        The resolved base URI (no trailing slash). For EU/standard
        vehicles this is ``DEFAULT_BASE``; for region-routed vehicles
        it's the URI returned by the discovery endpoint.

    Discovery endpoint response shape (verified evcc-io/evcc source):
        ``{"homeRegion": {"baseUri": {"content": "https://..."}}}``
    """
    if cache is not None:
        cached = cache.get(vin)
        if cached is not None:
            return cached

    url = f"{DISCOVERY_BASE}/api/cs/vds/v1/vehicles/{vin}/homeRegion"
    try:
        data = await client._get(url)  # noqa: SLF001 — intentional protected access
    except Exception as err:  # noqa: BLE001
        # Discovery is optional. Any failure → use default. Don't log
        # at WARN/ERROR — a missing homeRegion endpoint is the
        # default for most VINs.
        _LOGGER.debug(
            "homeRegion lookup failed for ***%s: %s — using default base",
            vin[-6:], err,
        )
        if cache is not None:
            cache.set(vin, DEFAULT_BASE)
        return DEFAULT_BASE

    # Parse response — defensive against shape changes.
    base_uri: str | None = None
    if isinstance(data, dict):
        home_region = data.get("homeRegion")
        if isinstance(home_region, dict):
            base_uri_obj = home_region.get("baseUri")
            if isinstance(base_uri_obj, dict):
                content = base_uri_obj.get("content")
                if isinstance(content, str) and content.startswith("http"):
                    # Strip any trailing slash for consistency with our
                    # f-string call patterns (``f"{_BASE}/..."``).
                    base_uri = content.rstrip("/")

    resolved = base_uri or DEFAULT_BASE
    if cache is not None:
        cache.set(vin, resolved)

    if resolved != DEFAULT_BASE:
        _LOGGER.info(
            "VAG homeRegion: vin ***%s routes to %s (non-default)",
            vin[-6:], resolved,
        )
    else:
        _LOGGER.debug(
            "VAG homeRegion: vin ***%s uses default base", vin[-6:],
        )
    return resolved
