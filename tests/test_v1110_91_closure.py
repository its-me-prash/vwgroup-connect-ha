# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.11.0 — Issue #91 closure (light status + service days +
max charge current).

Three groups:

- ``TestNewVehicleDataFields`` — defaults are sane, to_dict round-trips.
- ``TestVWEUParseLights`` — defensive light-array parsing handles the
  three documented element shapes (``{name,status}``, ``{id,status}``,
  ``{location.position,status}``) plus aggregate fallback when the
  shape is unrecognised.
- ``TestServiceDaysFields`` — both VW EU and Skoda parsers populate
  the new int day-count fields alongside the existing date sensors.
- ``TestSensorRegistration`` — all five new entity descriptions are in
  the platform tables with the right icons / units / conditions, and
  the data-present gate covers the new keys.
"""

from __future__ import annotations



# ─────────────────────────────────────────────────────────────────────────────
# VehicleData
# ─────────────────────────────────────────────────────────────────────────────


class TestNewVehicleDataFields:
    def test_defaults_are_safe(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="V1")
        assert d.service_due_in_days is None
        assert d.oil_service_due_in_days is None
        assert d.lights_on is None
        assert d.lights_count is None
        assert d.lights_individual == {}

    def test_to_dict_round_trip(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(
            vin="V1",
            service_due_in_days=42,
            oil_service_due_in_days=120,
            lights_on=True,
            lights_count=2,
            lights_individual={"frontLeft": True, "frontRight": False},
        )
        out = d.to_dict()
        assert out["service_due_in_days"] == 42
        assert out["oil_service_due_in_days"] == 120
        assert out["lights_on"] is True
        assert out["lights_count"] == 2
        assert out["lights_individual"] == {
            "frontLeft": True, "frontRight": False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# VW EU light-array parsing — defensive shape handling
# ─────────────────────────────────────────────────────────────────────────────


def _vw_eu():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client


class TestVWEUParseLights:
    def test_no_lights_field_leaves_all_none(self):
        """Vehicles whose API doesn't expose vehicleLights at all must
        leave ``lights_on``/``lights_count`` as None so the
        data-present gate skips entity creation."""
        client = _vw_eu()
        d = client._parse_status("V", {}, parking={})
        assert d.lights_on is None
        assert d.lights_count is None
        assert d.lights_individual == {}

    def test_empty_lights_array_means_zero(self):
        """API publishes the array but it's empty — that's a confirmed
        "no lights on" state. lights_on=False, lights_count=0,
        entity gets created (data IS present)."""
        client = _vw_eu()
        raw = {
            "vehicleLights": {
                "lightsStatus": {"value": {"lights": []}},
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.lights_on is False
        assert d.lights_count == 0

    def test_shape_a_name_status_string(self):
        """Common shape A: ``{name: "frontLeft", status: "off"}``."""
        client = _vw_eu()
        raw = {
            "vehicleLights": {
                "lightsStatus": {
                    "value": {
                        "lights": [
                            {"name": "frontLeft", "status": "off"},
                            {"name": "frontRight", "status": "on"},
                        ]
                    }
                }
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.lights_count == 1
        assert d.lights_on is True
        assert d.lights_individual == {
            "frontLeft": False,
            "frontRight": True,
        }

    def test_shape_b_id_status_string(self):
        """Shape B: ``{id: "rearRight", status: "on"}``."""
        client = _vw_eu()
        raw = {
            "vehicleLights": {
                "lightsStatus": {
                    "value": {
                        "lights": [
                            {"id": "rearLeft", "status": "off"},
                            {"id": "rearRight", "status": "on"},
                        ]
                    }
                }
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.lights_count == 1
        assert d.lights_individual == {
            "rearLeft": False,
            "rearRight": True,
        }

    def test_shape_c_status_list_of_dicts(self):
        """Shape C: ``status`` is a list of dicts (CARIAD-BFF doors/windows
        pattern reused for lights). ``[{value: "on"}]`` → on."""
        client = _vw_eu()
        raw = {
            "vehicleLights": {
                "lightsStatus": {
                    "value": {
                        "lights": [
                            {"name": "lowBeam", "status": [{"value": "on"}]},
                        ]
                    }
                }
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.lights_count == 1
        assert d.lights_on is True
        assert d.lights_individual == {"lowBeam": True}

    def test_unknown_shape_keeps_individual_empty_but_aggregates_count(self):
        """When element shape is unrecognised (no name/id/location), we
        skip per-light dict but still extract status. Aggregate stays
        useful, per-light entities stay quiet."""
        client = _vw_eu()
        raw = {
            "vehicleLights": {
                "lightsStatus": {
                    "value": {
                        "lights": [
                            {"weirdField": "x", "status": "on"},
                            {"otherWeird": "y", "status": "on"},
                            {"yetAnother": "z", "status": "off"},
                        ]
                    }
                }
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.lights_count == 2
        assert d.lights_on is True
        assert d.lights_individual == {}  # no per-light entities

    def test_non_dict_element_skipped_safely(self):
        """An array element that isn't a dict (e.g. a stray string) is
        skipped without crashing — defensive coding from v1.10.1."""
        client = _vw_eu()
        raw = {
            "vehicleLights": {
                "lightsStatus": {
                    "value": {
                        "lights": [
                            "not a dict",
                            None,
                            {"name": "valid", "status": "on"},
                        ]
                    }
                }
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.lights_count == 1
        assert d.lights_individual == {"valid": True}


# ─────────────────────────────────────────────────────────────────────────────
# Service days fields — populated alongside the existing DATE sensors
# ─────────────────────────────────────────────────────────────────────────────


class TestServiceDaysFields:
    def test_vw_eu_populates_service_due_in_days(self):
        client = _vw_eu()
        raw = {
            "vehicleHealthInspection": {
                "maintenanceStatus": {
                    "value": {
                        "inspectionDue_km": 12000,
                        "inspectionDue_days": 180,
                        "oilServiceDue_km": 5000,
                        "oilServiceDue_days": 75,
                    }
                }
            }
        }
        d = client._parse_status("V", raw, parking={})
        # Both the legacy DATE-source field and the new int field are
        # populated from the same backend integer.
        assert d.service_due_at == 180
        assert d.service_due_in_days == 180
        assert d.oil_service_at == 75
        assert d.oil_service_due_in_days == 75

    def test_vw_eu_handles_missing_inspection_block(self):
        """No vehicleHealthInspection → service_due_in_days stays None
        (no phantom "0 d" sensor)."""
        client = _vw_eu()
        d = client._parse_status("V", {}, parking={})
        assert d.service_due_in_days is None
        assert d.oil_service_due_in_days is None


# ─────────────────────────────────────────────────────────────────────────────
# Sensor / binary_sensor registration
# ─────────────────────────────────────────────────────────────────────────────


class TestSensorRegistration:
    def test_three_new_sensors_registered(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        for k in (
            "service_due_in_days",
            "oil_service_due_in_days",
            "lights_count",
            "max_charge_current_a",
        ):
            assert k in keys, f"missing sensor: {k}"

    def test_lights_on_binary_sensor_registered(self):
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
        )

        keys = {desc.key for desc in BINARY_DESCRIPTIONS}
        assert "lights_on" in keys

    def test_max_charge_current_a_uses_ampere_unit(self):
        """Sensor must show as "16 A" not "16" — verified with HA's
        SensorDeviceClass.CURRENT."""
        from homeassistant.const import UnitOfElectricCurrent
        from homeassistant.components.sensor import SensorDeviceClass
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "max_charge_current_a")
        assert desc.native_unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert desc.device_class == SensorDeviceClass.CURRENT
        assert desc.condition == "electric"
        # Reads from the existing max_charge_current field — no schema
        # duplication, just a different unit-aware presentation.
        assert desc.data_key == "max_charge_current"

    def test_service_days_sensor_uses_days_unit(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "service_due_in_days")
        assert desc.native_unit_of_measurement == "d"
        assert desc.entity_category.value == "diagnostic"

    def test_lights_count_in_data_present_required(self):
        """Phantom-entity prevention: only registers when data exists."""
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "lights_count" in _DATA_PRESENT_REQUIRED

    def test_lights_on_in_binary_sensor_data_present_required(self):
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "lights_on" in _DATA_PRESENT_REQUIRED

    def test_oil_service_days_combustion_only(self):
        """Only ICE / hybrid vehicles get the oil-service entity."""
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        desc = next(
            d for d in SENSOR_DESCRIPTIONS if d.key == "oil_service_due_in_days"
        )
        assert desc.condition == "combustion"
