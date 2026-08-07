# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1022 / #717 — charge rate scale by UUID, mirroring the charge-power fix.

battery_state_report.charge_rate is emitted under several dict UUIDs with
different units: 1efb6000 is "The float value" (already km/h) and 732b602c is
tagged unit=kmPerHour, while 0c60a14f / 1edd4c7f / 9e366e14 state "resolution of
0,1" (deci) and 370c2092 (actual_charge_rate) is the same deci datum. The old
rule always divided battery_state_report.charge_rate by ten, which is right for
the deci UUIDs (149 -> 14.9) but wrong for the ID.7's plain 68.0 km/h under
1efb6000 (it became 6.8). Keying by the UUID fixes that; the name-based rule
stays as the fallback when no encoding UUID is present.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_NAME = "battery_state_report.charge_rate"
_FLOAT_UUID = "1efb6000-6b54-366a-9233-d320699687cf"   # "The float value" = km/h
_DECI_UUID = "0c60a14f-116d-3ccd-b551-940a0814364e"    # "resolution of 0,1"
_DECI_UUID2 = "9e366e14-a8ce-30b4-a204-b573596d1dbf"   # another deci variant


def _cr_kmh(payload: list) -> float | None:
    fields = _walk_fields(payload)
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X")).charging_rate_kmh


def _pt(value: str, uuid: str | None = None, name: str = _NAME) -> list:
    pt = {"dataFieldName": name, "value": value}
    if uuid:
        pt["key"] = uuid
    return [pt]


class TestChargeRateUuid:
    def test_float_uuid_kept_as_kmh(self) -> None:
        # THE fix: the ID.7's 68.0 km/h under the float UUID must NOT be /10 (#1022).
        assert _cr_kmh(_pt("68.0", _FLOAT_UUID)) == 68.0

    def test_float_uuid_exact_integer_kept(self) -> None:
        # a round integer under the float UUID must survive too (the case the
        # name-based /10 rule would otherwise wreck).
        assert _cr_kmh(_pt("70", _FLOAT_UUID)) == 70.0

    def test_deci_uuid_divided_by_ten(self) -> None:
        # #717: a deci UUID reading of 149 is 14.9 km/h.
        assert _cr_kmh(_pt("149", _DECI_UUID)) == 14.9

    def test_second_deci_uuid_divided(self) -> None:
        assert _cr_kmh(_pt("80", _DECI_UUID2)) == 8.0


class TestChargeRateNameFallback:
    """No encoding UUID present => the name-based rule behaves exactly as before
    (no regression)."""

    def test_report_charge_rate_name_divided(self) -> None:
        assert _cr_kmh(_pt("149")) == 14.9

    def test_camelcase_kmph_unscaled(self) -> None:
        assert _cr_kmh(_pt("80", name="charging_rate_kmh")) == 80.0
