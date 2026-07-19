"""v2.20.0 (#752) — capability status → legible gating reason.

Grounds the CARIAD ``capabilities/Status`` vocabulary (31 camelCase values) plus
the Skoda UPPER_SNAKE variants, and the coordinator hooks that surface WHY a
capability is gated — so heyensh's climate 404 (#752) can say "this vehicle does
not offer this feature" / "subscription inactive" instead of a bare backend
error. The gating DECISION (vehicle_supports_capability) is unchanged; this only
adds the reason.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad._capability_status import (
    capability_status_reason,
    category_for_status,
)
from custom_components.vag_connect.const import CONF_BRAND
from custom_components.vag_connect.coordinator import VagConnectCoordinator


# ── pure module: category_for_status ────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "category"),
    [
        ("licenseExpired", "license"),
        ("missingLicense", "license"),
        ("LICENSE_REQUIRED", "license"),  # Skoda UPPER_SNAKE
        ("consentMissing", "consent"),
        ("termsAndConditionsNotAccepted", "consent"),
        ("insufficientSecurityLevel", "permission"),
        ("unsupported", "unsupported"),
        ("missingService", "unsupported"),
        ("deactivated", "deactivated"),
        ("disabledByUser", "deactivated"),
        ("insufficientBatteryLevel", "transient"),
        ("INSUFFICIENT_BATTERY_LEVEL", "transient"),  # Skoda == CARIAD after fold
        ("deepSleep", "transient"),
        ("someBrandNewValue", "unknown"),
        ("", "unknown"),
    ],
)
def test_category_for_status(value: str, category: str) -> None:
    assert category_for_status(value) == category


# ── pure module: capability_status_reason ───────────────────────────────


def test_reason_empty_is_none() -> None:
    assert capability_status_reason([]) is None
    assert capability_status_reason(None) is None
    assert capability_status_reason(["", None]) is None


def test_reason_single_transient() -> None:
    cat, text = capability_status_reason(["deepSleep"])
    assert cat == "transient"
    assert "asleep" in text or "temporarily" in text


def test_reason_priority_license_over_transient() -> None:
    # Both present → the more actionable "license" wins over "transient".
    cat, _ = capability_status_reason(["deepSleep", "licenseExpired"])
    assert cat == "license"


def test_reason_priority_unsupported_over_deactivated() -> None:
    cat, _ = capability_status_reason(["deactivated", "unsupported"])
    assert cat == "unsupported"


def test_reason_accepts_single_string() -> None:
    cat, _ = capability_status_reason("unsupported")
    assert cat == "unsupported"


# ── coordinator hooks ───────────────────────────────────────────────────


def _coord(brand: str, caps: dict[str, object]) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {CONF_BRAND: brand}
    coord._vehicles_lock = threading.Lock()
    coord.vehicles = {"VIN1": {}}
    coord.vehicle_capabilities = caps
    return coord


def test_gating_reason_752_climate_license() -> None:
    # #752 shape: climatisation present but status = licenseExpired.
    coord = _coord(
        "audi",
        {"VIN1": {"capabilities": [{"id": "climatisation", "status": ["licenseExpired"]}]}},
    )
    reason = coord.capability_gating_reason("VIN1", "climatisation")
    assert reason is not None
    assert reason[0] == "license"


def test_gating_reason_752_climate_unsupported() -> None:
    # The other #752 case: combustion car simply doesn't offer remote climate.
    coord = _coord(
        "audi",
        {"VIN1": {"capabilities": [{"id": "climatisation", "status": ["unsupported"]}]}},
    )
    assert coord.capability_gating_reason("VIN1", "climatisation")[0] == "unsupported"


def test_gating_reason_usable_capability_is_none() -> None:
    coord = _coord(
        "audi", {"VIN1": {"capabilities": [{"id": "climatisation", "status": []}]}}
    )
    assert coord.capability_gating_reason("VIN1", "climatisation") is None


def test_gating_reason_absent_capability_is_none() -> None:
    coord = _coord(
        "audi", {"VIN1": {"capabilities": [{"id": "access", "status": []}]}}
    )
    assert coord.capability_gating_reason("VIN1", "climatisation") is None


def test_gating_reason_no_cache_is_none() -> None:
    coord = _coord("audi", {})
    assert coord.capability_gating_reason("VIN1", "climatisation") is None


def test_command_gating_reason_maps_command_to_capability() -> None:
    # command_start_climate → cap "climatisation" (audi) → license reason.
    coord = _coord(
        "audi",
        {"VIN1": {"capabilities": [{"id": "climatisation", "status": ["missingLicense"]}]}},
    )
    reason = coord.command_gating_reason("VIN1", "command_start_climate")
    assert reason is not None and reason[0] == "license"


def test_command_gating_reason_unmapped_command_is_none() -> None:
    coord = _coord("audi", {"VIN1": {"capabilities": []}})
    assert coord.command_gating_reason("VIN1", "command_does_not_exist") is None


def test_gating_reason_skoda_license_issue_flag() -> None:
    # Skoda expresses gating via a license-issue flag, not a status array.
    coord = _coord(
        "skoda",
        {"VIN1": {"capabilities": [{"id": "charging", "license-issue": {"type": "MISSING"}}]}},
    )
    reason = coord.capability_gating_reason("VIN1", "charging")
    assert reason is not None and reason[0] == "license"


def test_gating_reason_skoda_active_false_flag() -> None:
    coord = _coord(
        "skoda",
        {"VIN1": {"capabilities": [{"id": "charging", "active": False}]}},
    )
    assert coord.capability_gating_reason("VIN1", "charging")[0] == "deactivated"
