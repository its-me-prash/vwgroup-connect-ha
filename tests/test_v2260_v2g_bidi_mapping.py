# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.26.0 — map-not-suppress for the rest of the bidirectional_charging_mode.*
V2G family (#981) and the container-qualified profile_charge_reason (#978).

Both are verified the source-of-truth way: drive the REAL mapper and assert the
fields land on VehicleData AND leave raw_unmapped_fields (so the Scout stops
re-reporting them). No unit is asserted because the dict ships unit=null and we
map them unitless on purpose.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="V"))


class TestV2GBidiMapping:
    def test_maps_all_eight_and_consumes_them(self) -> None:
        fields = {
            "bidirectional_charging_mode.amount_of_energy": "12",
            "bidirectional_charging_mode.amount_of_energy_threshold": "50",
            "bidirectional_charging_mode.numbers_of_cycles": "7",
            "bidirectional_charging_mode.numbers_of_cycles_threshold": "100",
            "bidirectional_charging_mode.operating_hours": "34",
            "bidirectional_charging_mode.operating_hours_threshold": "500",
            "bidirectional_charging_mode.quota": "20",
            "bidirectional_charging_mode.quota_Threshold": "80",
        }
        d = _map(fields)
        assert d.bidi_energy_used == 12
        assert d.bidi_energy_used_threshold == 50
        assert d.bidi_cycles == 7
        assert d.bidi_cycles_threshold == 100
        assert d.bidi_operating_hours == 34
        assert d.bidi_operating_hours_threshold == 500
        assert d.bidi_quota == 20
        assert d.bidi_quota_threshold == 80
        # consumed → the Scout must not re-report any of them
        leftover = [k for k in (d.raw_unmapped_fields or {})
                    if "bidirectional_charging_mode" in k]
        assert leftover == [], leftover

    def test_bare_spelling_also_maps(self) -> None:
        d = _map({"amount_of_energy": "9", "numbers_of_cycles": "3"})
        assert d.bidi_energy_used == 9
        assert d.bidi_cycles == 3

    def test_profile_charge_reason_container_spelling(self) -> None:
        # #978 — the container-qualified spelling now maps (was Scout-reported).
        d = _map({"charging_state_report.profile_charge_reason": "PROFILE_CHARGE_REASON_LOW_COST"})
        assert d.profile_charge_reason
        leftover = [k for k in (d.raw_unmapped_fields or {})
                    if "profile_charge_reason" in k]
        assert leftover == [], leftover
