# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""CARIAD API clients — one per brand backend."""

from .base import CariadBaseClient
from .vw_eu import VWEUClient
from .audi import AudiClient
from .skoda import SkodaClient
from .seat_cupra import SeatCupraClient

__all__ = [
    "CariadBaseClient",
    "VWEUClient",
    "AudiClient",
    "SkodaClient",
    "SeatCupraClient",
]
