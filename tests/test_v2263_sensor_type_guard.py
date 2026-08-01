# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A backend field changing type must not break entity rendering.

This has happened for real: CUPRA firmware turned ``settings.maxChargeCurrentAc``
from an integer into the enum "maximum"/"reduced", and the amp sensor blew up
with ``could not convert string to float: 'maximum'`` (#392). That was patched
inside the SEAT/CUPRA parser, and later inside the Skoda one, each time after
somebody's entity had already broken.

The raise happens in Home Assistant's state write, which is OUTSIDE the
coordinator's parse guard, so no amount of coordinator-side hardening can catch
it. The guard therefore lives at the entity boundary, where it covers the whole
class once: a non-numeric value on a numeric sensor reports unknown.

Text sensors (no state class, no numeric device class) must keep passing their
strings through untouched.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.vag_connect.sensor import (
    VagSensorDescription,
    VagConnectSensor,
)

_VIN = "VIN123"


def _sensor(desc: VagSensorDescription, raw_value: object) -> VagConnectSensor:
    coord = MagicMock()
    coord.data = {_VIN: {desc.data_key: raw_value}}
    coord.vehicles = coord.data
    ent = VagConnectSensor(coord, _VIN, desc)
    # _vehicle is what native_value reads.
    type(ent)._vehicle = property(lambda self: coord.data[_VIN])  # type: ignore[assignment]
    return ent


_NUMERIC = VagSensorDescription(
    key="max_charge_current",
    data_key="max_charge_current",
    device_class=SensorDeviceClass.CURRENT,
    state_class=SensorStateClass.MEASUREMENT,
)
_TEXT = VagSensorDescription(key="charging_state", data_key="charging_state")


class TestSensorTypeGuard:
    def test_enum_string_on_a_numeric_sensor_reports_unknown(self) -> None:
        """#392's exact shape: an int field starts arriving as an enum."""
        assert _sensor(_NUMERIC, "maximum").native_value is None

    def test_numeric_values_are_untouched(self) -> None:
        assert _sensor(_NUMERIC, 16).native_value == 16
        assert _sensor(_NUMERIC, 16.5).native_value == 16.5

    def test_stringified_number_still_works(self) -> None:
        """Firmware that sends "85" kept working before the guard and must
        keep working after it — HA's own float() accepted those too."""
        assert _sensor(_NUMERIC, "85").native_value == 85.0

    def test_none_stays_none(self) -> None:
        assert _sensor(_NUMERIC, None).native_value is None

    def test_text_sensor_passes_its_string_through(self) -> None:
        """The guard must not turn a legitimate text sensor into unknown."""
        assert _sensor(_TEXT, "CHARGING").native_value == "CHARGING"

    def test_case_variant_enum_does_not_raise(self) -> None:
        """Backends have been seen sending the same enum in different cases;
        neither may reach HA as a numeric state."""
        for variant in ("Maximum", "MAXIMUM", "reduced"):
            assert _sensor(_NUMERIC, variant).native_value is None


# ── target-SoC gap-fill from the battery-care threshold ─────────────────────

class TestTargetSocFallback:
    """Cars that report only a battery-care ceiling still get a charge target.

    Some exports (the Audi Q4 e-tron is the known case) carry
    battery_care_mode.charge_bcam_threshold and no settings.target_soc, so the
    headline target sensor was never populated even though the car has a
    ceiling. Gap-fill only: an explicit target always wins.
    """

    @staticmethod
    def _map(fields: dict[str, str]):
        from custom_components.vag_connect.cariad.auth._eu_data_act import (
            map_dataset_to_vehicle_data,
        )
        from custom_components.vag_connect.cariad.models import VehicleData

        return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))

    def test_threshold_fills_an_empty_target(self) -> None:
        d = self._map({"battery_care_mode.charge_bcam_threshold": "80"})
        assert d.target_soc == 80
        assert d.battery_care_target_soc_pct == 80  # still exposed separately

    def test_explicit_target_wins(self) -> None:
        d = self._map({
            "settings.target_soc": "90",
            "battery_care_mode.charge_bcam_threshold": "80",
        })
        assert d.target_soc == 90
        assert d.battery_care_target_soc_pct == 80

    def test_no_threshold_leaves_target_empty(self) -> None:
        d = self._map({"battery_state_report.soc": "55"})
        assert d.target_soc is None
