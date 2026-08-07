# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""EU Data Act self-audit P0 fixes (competitor deep-dive 2026-08-07).

P0-2: the portal reports the "until service" interval with an inconsistent sign.
We used to negate it unconditionally, so a car that already reports a POSITIVE
remaining (TommiG1 #39/#36) got flipped to a false "overdue". Now we normalise
to a positive countdown, negating only the negative-sign readings.

P0-4: Enyaq / MEB-Entry (e-up) ship the traction SoC under a bespoke leaf
``currentSoc`` whose UUID never aliases (leaf is not generic), so SoC was missed.
We now match the leaf by name.
"""
from __future__ import annotations

from typing import Any

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, Any]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


class TestServiceIntervalSign:
    def test_negative_remaining_becomes_positive_countdown(self) -> None:
        d = _map({
            "maintenance_interval_distance_until_inspection": "-14900",
            "maintenance_interval__time_until_inspection": "-155",
        })
        assert d.service_km == 14900
        assert d.service_due_in_days == 155

    def test_positive_remaining_is_not_flipped_to_overdue(self) -> None:
        # TommiG1 #39: a car already reporting positive remaining must not be
        # negated into a false "overdue".
        d = _map({
            "maintenance_interval_distance_until_inspection": "14900",
            "maintenance_interval__time_until_inspection": "155",
        })
        assert d.service_km == 14900
        assert d.service_due_in_days == 155

    def test_oil_interval_normalised_both_signs(self) -> None:
        d = _map({
            "maintenance_interval_distance_until_oil_change": "9000",   # positive
            "maintenance_interval__time_until_oil_change": "-30",       # negative
        })
        assert d.oil_service_km == 9000
        assert d.oil_service_due_in_days == 30


class TestEnyaqBespokeSoc:
    def test_currentsoc_leaf_maps_soc(self) -> None:
        assert _map({"currentSoc": "73"}).battery_soc == 73

    def test_snake_case_variant_also_maps(self) -> None:
        assert _map({"current_soc": "64"}).battery_soc == 64

    def test_canonical_soc_still_wins_when_both_present(self) -> None:
        d = _map({"battery_state_report.soc": "80", "currentSoc": "55"})
        assert d.battery_soc == 80
