# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1022 — charge power arrives in two encodings, not one.

The portal was believed to always report charge power in 0.1-kW steps, proven
twice: #717 saw 65 for 6.5 kW, and #764 settled it with a live export showing
19 while the car charged at an 11 kW AC maximum, so 19 could only be 1.9 kW.

An ID.7 on the MEB platform then reported 10.399994 on an 11 kW wallbox, i.e.
already kilowatts. Dividing that by ten published 1.0 kW.

The discriminator is the fractional part: a deci-kW reading counts whole
0.1-kW steps and therefore arrives as an integer, while a value with decimals
is already in kW. Every integer reading keeps behaving exactly as before, so
the two settled cases are untouched.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _power(raw: str, key: str = "battery_state_report.charge_power") -> float | None:
    d = map_dataset_to_vehicle_data({key: raw}, VehicleData(vin="X"))
    return d.charging_power_kw


class TestDeciDialectUnchanged:
    """The two cases that were settled with live data must not move."""

    def test_717_sixty_five_is_six_and_a_half_kw(self) -> None:
        assert _power("65") == 6.5

    def test_764_nineteen_is_one_point_nine_kw(self) -> None:
        assert _power("19") == 1.9

    def test_an_integral_float_is_still_deci(self) -> None:
        """65.0 is the same reading as 65, just serialised with a decimal."""
        assert _power("65.0") == 6.5

    def test_zero_stays_zero(self) -> None:
        assert _power("0") == 0.0


class TestKilowattDialect:
    def test_1022_id7_reports_its_real_power(self) -> None:
        """10.399994 on an 11 kW wallbox published as 1.0 kW before this."""
        assert _power("10.399994") == 10.4

    def test_a_dc_rate_survives(self) -> None:
        assert _power("149.5") == 149.5

    @pytest.mark.parametrize("key", ["charge_power", "charging_power"])
    def test_the_other_spellings_behave_the_same(self, key: str) -> None:
        assert _power("10.399994", key) == 10.4


class TestExplicitKwFieldUnaffected:
    def test_chargepower_kw_is_never_scaled(self) -> None:
        """The field that names its unit was always taken as-is."""
        d = map_dataset_to_vehicle_data({"chargePower_kW": "11"}, VehicleData(vin="X"))
        assert d.charging_power_kw == 11
