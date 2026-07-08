# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.16.2 (#636) — EU-Data-Act report-delivery trigger mapping."""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


class TestReportTrigger:
    def test_trigger_type_maps_to_report_trigger(self) -> None:
        d = _map({"trigger_type": "ROA_REMOTE"})
        assert d.report_trigger == "ROA_REMOTE"

    def test_no_field_stays_none(self) -> None:
        d = _map({"soc": "80"})
        assert d.report_trigger is None
        assert d.battery_soc == 80  # unrelated field still maps
