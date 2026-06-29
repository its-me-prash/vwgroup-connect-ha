# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VAG Connect CARIAD API client — direct async access, zero external dependencies."""

from .api.factory import CariadClientFactory
from .exceptions import (
    AuthenticationError,
    MarketingConsentError,
    RateLimitError,
    SpinError,
    TermsAndConditionsError,
    TwoFactorRequiredError,
    VehicleCommandError,
    VehicleNotFoundError,
)
from .models import BRANDS, BrandConfig, VehicleData

__all__ = [
    "CariadClientFactory",
    "BrandConfig",
    "VehicleData",
    "BRANDS",
    "AuthenticationError",
    "MarketingConsentError",
    "RateLimitError",
    "SpinError",
    "TermsAndConditionsError",
    "TwoFactorRequiredError",
    "VehicleCommandError",
    "VehicleNotFoundError",
]
