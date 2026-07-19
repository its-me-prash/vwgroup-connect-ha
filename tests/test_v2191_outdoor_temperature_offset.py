"""v2.19.1 — EU-DA ``outdoor_temperature.temperature`` offset decode.

The one-time-export dialect carries the ambient reading as the nested
``outdoor_temperature.temperature`` field, which shares the cabin sensor's
offset encoding (EU-DA dict UUID f2e30577 == 74039fb6: 0.1 °C, -46 offset;
1461..2513 = 0.25 °F subrange). The mapper previously only consumed the flat
plain-°C ``outdoor_temperature`` alias and the deci-Kelvin ``outside_temperature``,
so a car emitting only the nested spelling lost its outside temperature — and
had the passthrough path ever seen the raw (e.g. 675) it would report -205 °C,
the exact bug fixed for cabin. This adds the nested decode as a fallback that
never overrides the flat/dK sources.
"""

from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="WVWTEST0000002191"))


def test_outdoor_nested_offset_celsius() -> None:
    # raw 675 = 675*0.1 - 46 = 21.5 °C (NOT deci-Kelvin, which would give -205).
    d = _map(
        {
            "outdoor_temperature.temperature": "675",
            "outdoor_temperature.measurement_state": "valid",
        }
    )
    assert d.outside_temp == 21.5


def test_outdoor_nested_no_state_accepted() -> None:
    d = _map({"outdoor_temperature.temperature": "650"})  # 650*0.1 - 46 = 19.0
    assert d.outside_temp == 19.0


def test_outdoor_nested_fahrenheit_subrange() -> None:
    # raw 1461 = -51 °F (dict) → -46.1 °C.
    d = _map({"outdoor_temperature.temperature": "1461"})
    assert d.outside_temp == -46.1


def test_outdoor_nested_invalid_state_skipped() -> None:
    d = _map(
        {
            "outdoor_temperature.temperature": "675",
            "outdoor_temperature.measurement_state": "MEASUREMENT_INVALID",
        }
    )
    assert d.outside_temp is None


def test_flat_celsius_alias_wins_over_nested() -> None:
    # flat plain-°C `outdoor_temperature` is consumed first; the nested offset
    # form must not overwrite it. nested 700 would decode to 24.0, so asserting
    # 21.0 proves the flat alias won.
    d = _map(
        {
            "outdoor_temperature": "21.0",
            "outdoor_temperature.temperature": "700",
        }
    )
    assert d.outside_temp == 21.0


def test_deci_kelvin_source_wins_over_nested() -> None:
    # dK `outside_temperature` (2981 dK ≈ 24.95 °C) wins; nested is fallback.
    # K→C lands on a .x5 hundredth so assert the range, not the exact tenth
    # (mirrors the #701 hvbattery test) — and confirm it is NOT the nested
    # decode of 700 (24.0) or its offset value.
    d = _map(
        {
            "outside_temperature": "2981",
            "outdoor_temperature.temperature": "670",
        }
    )
    assert 24.5 <= d.outside_temp <= 25.5


def test_nested_does_not_clobber_prefilled_bff_value() -> None:
    d = VehicleData(vin="WVWTEST0000002191")
    d.outside_temp = 12.3  # already filled by the CARIAD-BFF channel
    map_dataset_to_vehicle_data({"outdoor_temperature.temperature": "675"}, d)
    assert d.outside_temp == 12.3


def test_no_outdoor_fields_stay_none() -> None:
    d = _map({"odometer": "12345"})
    assert d.outside_temp is None
