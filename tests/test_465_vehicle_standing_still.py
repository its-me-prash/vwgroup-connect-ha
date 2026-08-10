# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 (zdravac) — `vehicleIsStandingStill` was catalogued in the EU Data Act
dictionary (UUID 0010398f-5fda-39af-9e7a-25db8c2e623a, cluster "Parking Data",
boolean "current motion state") but never wired into the mapper. It now surfaces
through the existing is_driving sensor, inverted: standing still ⇒ not driving.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_STILL_UUID = "0010398f-5fda-39af-9e7a-25db8c2e623a"


def _is_driving(name: str, value: str, uuid: str | None = None):
    pt: dict = {"dataFieldName": name, "value": value}
    if uuid:
        pt["key"] = uuid
    fields = _walk_fields([pt])
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X")).is_driving


def test_standing_still_true_means_not_driving() -> None:
    assert _is_driving("vehicleIsStandingStill", "true") is False


def test_standing_still_false_means_driving() -> None:
    assert _is_driving("vehicleIsStandingStill", "false") is True


def test_case_and_whitespace_tolerant() -> None:
    assert _is_driving("vehicleIsStandingStill", " TRUE ") is False


def test_absent_leaves_is_driving_unset() -> None:
    """A car that doesn't send the field (zdravac's own) must not get a fabricated
    driving state — is_driving stays None so the sensor reads unknown."""
    fields = _walk_fields(
        [{"dataFieldName": "battery_state_report.soc", "value": "50"}]
    )
    assert map_dataset_to_vehicle_data(
        fields, VehicleData(vin="X")
    ).is_driving is None
