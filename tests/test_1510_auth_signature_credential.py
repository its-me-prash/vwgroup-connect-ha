# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout 2026-09-25 (#1510) — the portal ships ``auth_signature_response``, a
signed auth/attestation token whose value is a hex blob embedding the VIN plus a
cryptographic signature. It is credential + identity material, not vehicle data,
and must be WITHHELD from raw discovery entirely (like ``idp_idt``) so the VIN
never reaches the diagnostic sensor or a public Scout report.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _CREDENTIAL_FIELDS,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _raw_leaves(payload: dict) -> set[str]:
    d = map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))
    return {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}


def test_auth_signature_response_is_a_credential_field() -> None:
    assert "auth_signature_response" in _CREDENTIAL_FIELDS


def test_auth_signature_response_is_withheld_from_discovery() -> None:
    # A realistic blob (hex, embeds a VIN + signature) must not surface.
    blob = "23a14848489e5211ae00190100000057564" + "75a5a5a4532355445303433303938bf0f"
    leaves = _raw_leaves({"auth_signature_response": blob, "some_real_field": "42"})
    assert "auth_signature_response" not in leaves  # withheld
    assert "some_real_field" in leaves  # no over-suppression


def test_idp_idt_still_withheld() -> None:
    # The existing credential carve-out must keep working.
    leaves = _raw_leaves({"idp_idt": "tok", "x_field": "1"})
    assert "idp_idt" not in leaves
    assert "x_field" in leaves
