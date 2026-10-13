# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1819 (Kolbi, Audi A6 2026) — a tyre pressure of 2.8 bar was shown as 2.

The portal sent exactly this, quoted from the report:

    {"dataFieldName": "tyre_pressure_actual_rear_right", "value": "2.8"}

and every tyre-pressure entity dropped the fraction. The cause is two lines
apart: ``_to_int`` is ``int(_to_float(raw))``, which truncates rather than
rounds, and all fifteen tyre-pressure fields were typed ``int``. Rounding would
have been just as wrong: 2.8 bar is not 3 bar. The values are a measurement
with one decimal, so they are floats now.

The reporter could not see the worse half. The TPMS classifier reads the same
raw family through the same ``_to_int`` and then asks whether any corner is
``> 1`` or ``== 1``, because the field dictionary defines 0 as unsupported and
1 as invalid for the integer unit. Truncation turns any corner between 1.0 and
2.0 bar into exactly 1, so a car with a soft tyre was classified as having an
indirect TPMS that reports no numbers at all. That is the one moment the
reading matters most, and it is also the inverse of the stated intent, which
``test_tpms_status`` spells out: "measured" when a corner reports a real > 1
reading, "indirect" when the family is present but all-"1".

Unchanged on purpose: the 0/1 sentinel set itself. For the integer unit those
are the documented unsupported and invalid markers, and a bar car reporting a
genuine 1.0 is indistinguishable from the marker in the payload, so dropping it
stays the safe reading until a car actually reports one. Publishing a sentinel
as a measurement is the #1403 mistake, and it is worse than losing one
implausibly low value.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_CORNERS = ("front_left", "front_right", "rear_left", "rear_right")
_SLOTS = ("fl", "fr", "rl", "rr")


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


class TestTheReportedCase:
    """The reporter's own field name and value."""

    def test_the_exact_payload_from_the_report(self):
        d = _map({"tyre_pressure_actual_rear_right": "2.8"})
        assert d.tyre_pressure_actual_rr == 2.8

    def test_it_is_not_truncated(self):
        """Stated as the defect, so the test names what went wrong."""
        d = _map({"tyre_pressure_actual_rear_right": "2.8"})
        assert d.tyre_pressure_actual_rr != 2

    def test_it_is_not_rounded_either(self):
        """2.8 bar is not 3 bar; rounding would be a different wrong answer."""
        d = _map({"tyre_pressure_actual_rear_right": "2.8"})
        assert d.tyre_pressure_actual_rr != 3

    def test_all_four_corners_and_the_spare(self):
        d = _map({
            **{f"tyre_pressure_actual_{c}": "2.4" for c in _CORNERS},
            "tyre_pressure_actual_spare_tyre": "4.2",
        })
        assert [getattr(d, f"tyre_pressure_actual_{s}") for s in _SLOTS] == [2.4] * 4
        assert d.tyre_pressure_actual_spare == 4.2

    def test_the_required_family_keeps_its_decimal(self):
        d = _map({"tyre_pressure_required_front_left": "2.6"})
        assert d.tyre_pressure_required_fl == 2.6

    def test_the_delta_family_keeps_its_decimal(self):
        d = _map({"tyre_pressure_differential_front_left": "0.3"})
        assert d.tyre_pressure_diff_fl == 0.3

    def test_an_integer_unit_car_is_unaffected(self):
        """A car reporting 10 kPa units sends whole numbers; nothing changes."""
        d = _map({"tyre_pressure_actual_front_left": "280"})
        assert d.tyre_pressure_actual_fl == 280

    def test_a_trailing_zero_decimal_is_read_as_the_number(self):
        d = _map({"tyre_pressure_actual_front_left": "2.50"})
        assert d.tyre_pressure_actual_fl == 2.5


class TestTheTpmsClassifier:
    """The half the reporter could not see."""

    def test_a_soft_tyre_is_measured_not_indirect(self):
        """1.8 bar is a real reading, and the worst one to misread."""
        d = _map({"tyre_pressure_actual_front_left": "1.8"})
        assert d.tpms_status == "measured"

    def test_the_soft_tyre_value_also_survives(self):
        d = _map({"tyre_pressure_actual_front_left": "1.8"})
        assert d.tyre_pressure_actual_fl == 1.8

    def test_a_decimal_above_two_is_measured(self):
        d = _map({"tyre_pressure_actual_rear_right": "2.8"})
        assert d.tpms_status == "measured"

    def test_an_all_one_family_is_still_indirect(self):
        """The documented sentinel case, unchanged."""
        d = _map({f"tyre_pressure_actual_{c}": "1" for c in _CORNERS})
        assert d.tpms_status == "indirect"

    def test_an_all_zero_family_still_classifies_as_nothing(self):
        d = _map({f"tyre_pressure_actual_{c}": "0" for c in _CORNERS})
        assert d.tpms_status is None

    def test_an_absent_family_still_classifies_as_nothing(self):
        assert _map({"mileage": "1000"}).tpms_status is None


class TestSentinelsAreUnchanged:
    """The 0/1 markers keep being dropped; that was never the bug."""

    @pytest.mark.parametrize("raw", ["0", "1"])
    def test_the_markers_are_still_dropped(self, raw: str):
        d = _map({"tyre_pressure_actual_front_left": raw})
        assert d.tyre_pressure_actual_fl is None

    @pytest.mark.parametrize("raw", ["2.8", "1.8", "280", "4.2"])
    def test_a_real_reading_survives(self, raw: str):
        d = _map({"tyre_pressure_actual_front_left": raw})
        assert d.tyre_pressure_actual_fl == float(raw)

    def test_the_marker_is_dropped_in_the_required_family_too(self):
        d = _map({"tyre_pressure_required_front_left": "1"})
        assert d.tyre_pressure_required_fl is None


class TestItReachesTheRestOfTheIntegration:
    def test_the_decimal_is_in_to_dict(self):
        d = _map({"tyre_pressure_actual_rear_right": "2.8"})
        assert d.to_dict()["tyre_pressure_actual_rr"] == 2.8

    def test_the_fields_are_typed_as_floats(self):
        """An int annotation is what truncated them in the first place."""
        import dataclasses

        hints = {f.name: str(f.type) for f in dataclasses.fields(VehicleData)}
        wrong = [
            name
            for name, typ in hints.items()
            if name.startswith(
                ("tyre_pressure_actual_", "tyre_pressure_required_",
                 "tyre_pressure_diff_")
            )
            and "float" not in typ
        ]
        assert not wrong, wrong

    def test_all_fifteen_fields_are_covered(self):
        """Guard against fixing four corners and forgetting the spare."""
        import dataclasses

        names = [
            f.name
            for f in dataclasses.fields(VehicleData)
            if f.name.startswith(
                ("tyre_pressure_actual_", "tyre_pressure_required_",
                 "tyre_pressure_diff_")
            )
        ]
        assert len(names) == 15, names

    def test_no_sensor_descriptor_forces_whole_numbers(self):
        """A display precision of 0 would hide the fix in the UI."""
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        bad = [
            desc.key
            for desc in SENSOR_DESCRIPTIONS
            if desc.key.startswith("tyre_pressure_")
            and getattr(desc, "suggested_display_precision", None) == 0
        ]
        assert not bad, bad
