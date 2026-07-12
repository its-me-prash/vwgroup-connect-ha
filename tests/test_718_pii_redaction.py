# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#718 — redact user_id + VIN VALUES in raw_unmapped_fields (PII leak).

The EU-Data-Act dataset carries the account UUID (``user_id``) and the ``vin`` as
data fields. Being unmapped, they landed in the ``raw_unmapped_fields`` diagnostic
attribute with their REAL values — a PII leak. They are now value-redacted while
the field NAMES stay (so the Vehicle Data Scout still surfaces them — no
suppression, per the scout no-suppress policy).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_718_user_id_and_vin_values_redacted_names_kept() -> None:
    d = _map(
        {
            "user_id": "00000000-1111-2222-3333-444455556666",
            "eu_data_act.vin": "WVWZZZTEST0000718",
            "some_new_telemetry_field": "42",
        }
    )
    raw = d.raw_unmapped_fields or {}
    # NAMES stay (not suppressed → the Scout still surfaces them)
    assert "user_id" in raw and "eu_data_act.vin" in raw
    # ...but the real account UUID + VIN values are redacted
    assert raw["user_id"] == "<redacted>"
    assert raw["eu_data_act.vin"] == "<redacted>"
    # a genuine unmapped telemetry field keeps its real value for discovery
    assert raw["some_new_telemetry_field"] == "42"
