# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""EU Data Act (EUDA) abstraction shim — v2.0.0 (Big-Bang) preview.

The EU Data Act, Article 3, takes effect **September 2026**. It mandates
that car OEMs expose vehicle-data to end users (and chosen third parties)
via a documented API. COVESA recommends VSS / VISS as the standard
schema; binding is non-binding so each OEM may pick its own surface.

This module is **interface-only** for v2.0.0. It establishes the
architectural seam (one ABC + two adapter shells) so that when an OEM
publishes their EUDA endpoint, only the inner adapter's ``get_signal``
method needs implementing — the integration's brand clients, coordinator,
and entity layers already consume an ``EUDADataSource`` indirectly via
the existing ``VehicleData`` parser.

### Why ship the shim now (vs. waiting for binding)

1. **Six-month buffer**: between v2.0.0 ship + Sept 2026 deadline.
2. **Refactor cost is in the call sites, not the surface**: by adding
   the shim now, no future PR has to plumb a new dependency through
   the brand clients.
3. **Cross-integration alignment**: upstream + volkswagencarnet
   are tracking the same deadline; landing the same ABC name + signature
   makes a future consolidation possible.

### Adapters

- ``LegacyEUDAAdapter`` — wraps the current Cariad-BFF / OLA / mysmob /
  PPA / VW NA path. ``get_signal`` raises ``NotImplementedError`` until
  the EUDA path goes live; today's polling continues unchanged.
- ``VSSEUDAAdapter`` — placeholder for the upcoming VSS / VISS
  endpoint. ``get_signal`` raises ``NotImplementedError`` until OEMs
  publish their VSS surface (expected mid-2026).

### Cross-references

- COVESA VSS spec: https://covesa.global/project/vehicle-signal-specification/
- W3C VISS/VISSv2: https://www.w3.org/TR/viss2-core/
- EU Data Act (Reg. 2023/2854) Art. 3 (data access) + Art. 5 (third-party
  sharing) take effect 2026-09-12.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EUDADataSource(ABC):
    """Abstract source of EU Data Act signals.

    Implementations expose the OEM's EUDA-compliant vehicle-data surface
    (or its near-term equivalent — Cariad-BFF / OLA / etc.) via a single
    ``get_signal`` coroutine. Brand clients will eventually take an
    ``EUDADataSource`` constructor parameter so unit tests can swap a
    fake adapter in without monkey-patching the network layer.

    The schema is intentionally signal-path-based (e.g.
    ``Vehicle.Powertrain.TractionBattery.StateOfCharge.Current``) so
    callers can use the canonical VSS path even when the underlying
    adapter speaks Cariad-BFF JSON. Adapters do path translation.
    """

    @abstractmethod
    async def get_signal(
        self,
        vin: str,
        signal_path: str,
    ) -> Any:
        """Return the current value of *signal_path* for *vin*.

        Args:
            vin: Vehicle VIN (17-char canonical).
            signal_path: VSS dot-path (preferred) or backend native key.

        Returns:
            The raw signal value. Type depends on the signal — int for
            SoC, str for charging state, dict for compound objects.

        Raises:
            NotImplementedError: until the underlying adapter binds to
                the live EUDA endpoint. v2.0.0 ships shims only.
            ValueError: if ``signal_path`` is not recognised by this
                adapter's translation table.
        """


class LegacyEUDAAdapter(EUDADataSource):
    """Pre-EUDA adapter — wraps the current per-brand client path.

    The integration's existing brand clients (CariadClient, SkodaClient,
    OlaClient, PorscheClient, VwNaClient) already poll the OEM endpoints
    and produce a ``VehicleData`` row. ``get_signal`` here will eventually
    map a VSS path to the equivalent ``VehicleData`` field name and
    return the cached value — but that mapping table is deferred to the
    activation PR so v2.0.0 ships the surface only.
    """

    def __init__(self, brand_client: Any) -> None:
        """Initialise.

        Args:
            brand_client: One of the brand clients
                (``VWEUClient``, ``SkodaClient``, ``SeatCupraClient``,
                ``PorscheClient``, ``VwNaClient``). Held as opaque so
                this file doesn't pull a brand-import cycle.
        """
        self._brand_client = brand_client

    async def get_signal(self, vin: str, signal_path: str) -> Any:
        """Not yet bound — raises until v2.x activates the path map."""
        raise NotImplementedError(
            "LegacyEUDAAdapter.get_signal: signal-path-to-VehicleData "
            "translation table is deferred until the EUDA activation "
            f"PR (signal_path={signal_path!r}, vin masked)."
        )


class VSSEUDAAdapter(EUDADataSource):
    """Future adapter for OEM-native VSS / VISS endpoints.

    Placeholder for the upcoming OEM-published VSS endpoints expected
    mid-2026 (per COVESA + EUDA Art. 3 Sept 2026 deadline). When live,
    ``get_signal`` will issue a single VISSv2 GET and return the
    ``data.dp.value`` field.
    """

    def __init__(self, base_url: str, token_provider: Any) -> None:
        """Initialise.

        Args:
            base_url: OEM's VSS endpoint (e.g.
                ``https://eu.vss.api.audi.com``).
            token_provider: Async coroutine returning a fresh OAuth
                access token. Mirrors the brand client's
                ``async_get_access_token`` pattern so adapters can share
                the existing IDK / Auth0 / OLA token machinery.
        """
        self._base_url = base_url
        self._token_provider = token_provider

    async def get_signal(self, vin: str, signal_path: str) -> Any:
        """Not yet bound — raises until OEMs publish VSS endpoints."""
        raise NotImplementedError(
            "VSSEUDAAdapter.get_signal: OEMs have not yet published "
            "VSS-compliant endpoints. Tracker: COVESA VSS roadmap, "
            f"EUDA Art. 3 deadline 2026-09-12 (signal_path={signal_path!r})."
        )
