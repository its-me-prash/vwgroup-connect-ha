# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1104 (Lagaff86, Audi e-tron GT) — the charge_type field leaked the backend
end-of-charge sentinel: CHARGE_TYPE_INVALID shortened to the literal "invalid"
and Recorder stored it as a real charging type, painting "invalid" history
bands around every session end. charge_type was missing the junk-sentinel
filter its sibling fields (charging_mode/#764, the connector states) already
have — and the junk arrives PREFIXED, so the check must run on the shortened
value. It now drops to None until the backend sends a real type again.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_charge_type_prefixed_invalid_sentinel_dropped() -> None:
    # the real end-of-charge value Lagaff86 saw
    assert _map({"charge_type": "CHARGE_TYPE_INVALID"}).charging_type is None


def test_charge_type_bare_invalid_sentinel_dropped() -> None:
    # bare-spelling dialects are screened too
    assert _map({"charge_type": "invalid"}).charging_type is None
    assert _map({"charge_type": "unavailable"}).charging_type is None


def test_charge_type_real_value_kept() -> None:
    d = _map({"charge_type": "CHARGE_TYPE_AC"})
    assert d.charging_type is not None
    assert d.charging_type.strip().lower() not in (
        "invalid", "error", "unavailable", "unknown", "notavailable",
    )
    assert d.charging_type.lower() == "ac"  # prefix stripped, real value kept
