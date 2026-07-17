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


def test_718_user_id_and_vin_dropped_real_field_kept() -> None:
    # v2.18.1 — Prash's ruling (2026-07-17): account id + VIN are pure identity
    # metadata, the ONE carve-out from no-suppression. They are now DROPPED from
    # the raw/Scout surface entirely (stronger than the old value-redaction), so
    # they stop flooding the Scout on every poll. A genuine telemetry field with
    # a real name still surfaces with its real value for discovery.
    d = _map(
        {
            "user_id": "00000000-1111-2222-3333-444455556666",
            "eu_data_act.vin": "WVWZZZTEST0000718",
            "some_new_telemetry_field": "42",
        }
    )
    raw = d.raw_unmapped_fields or {}
    assert "user_id" not in raw
    assert "eu_data_act.vin" not in raw
    # a genuine unmapped telemetry field keeps its real value for discovery
    assert raw["some_new_telemetry_field"] == "42"
