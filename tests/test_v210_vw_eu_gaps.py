# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v2.10.0 Group A VW EU field parity additions.

Coverage:

A) Parser fills each new field from a canonical CARIAD BFF JSON shape.
B) Parser leaves every new field None when input is an empty dict.
C) Kelvin / Celsius detection: values > 200 are treated as Kelvin and
   converted; values <= 200 are treated as already-Celsius and stored
   verbatim.
D) Trip totals: backend totals are preserved; totals are derived from
   avg * distance / 100 only when no backend total is present AND both
   avg and distance are populated.
E) All new keys are members of ``_DATA_PRESENT_REQUIRED`` in
   sensor.py or binary_sensor.py so vehicles without the underlying
   leaves stay phantom-free.
"""

from __future__ import annotations


def _vw_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client


# ---------------------------------------------------------------------------
# A) Parser fills each new field from a canonical shape.
# ---------------------------------------------------------------------------


class TestParserPositiveShape:
    def test_hv_battery_temperatures(self):
        client = _vw_client()
        raw = {
            "charging": {
                "batteryStatus": {
                    "value": {
                        "minTemperature_K": 295.15,  # 22 C
                        "maxTemperature_K": 300.15,  # 27 C
                    },
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.hv_battery_min_temperature_c == 22.0
        assert data.hv_battery_max_temperature_c == 27.0

    def test_charge_max_ac_setting_and_ampere(self):
        client = _vw_client()
        raw = {
            "charging": {
                "chargingSettings": {
                    "value": {
                        "maxChargeCurrentAC_setting": 32,
                        "maxChargeCurrentAC": 16,
                    },
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.charge_max_ac_setting == 32
        assert data.charge_max_ac_ampere == 16

    def test_auto_release_ac_connector_bool_and_state(self):
        client = _vw_client()
        raw = {
            "charging": {
                "chargingSettings": {
                    "value": {"autoReleaseAcConnector": True},
                },
                "plugStatus": {
                    "value": {"autoReleaseState": "IDLE"},
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.auto_release_ac_connector is True
        assert data.auto_release_ac_connector_state == "IDLE"

    def test_auto_release_ac_connector_string_variant(self):
        client = _vw_client()
        raw = {
            "charging": {
                "plugStatus": {
                    "value": {"autoUnlockPlugWhenCharged": "PERMANENT"},
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.auto_release_ac_connector is True

    def test_optimised_battery_use_bool(self):
        client = _vw_client()
        raw = {
            "charging": {
                "chargingSettings": {
                    "value": {"optimisedBatteryUse": True},
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.optimised_battery_use is True

    def test_optimised_battery_use_string(self):
        client = _vw_client()
        raw = {
            "charging": {
                "chargingSettings": {
                    "value": {"optimizedBatteryUse": "ACTIVATED"},
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.optimised_battery_use is True

    def test_active_ventilation_state_and_remaining(self):
        client = _vw_client()
        raw = {
            "climatisation": {
                "climatisationStatus": {
                    "value": {
                        "ventilationState": "running",
                        "ventilationRemainingTimeInMinutes": 12,
                    },
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.active_ventilation_state == "running"
        assert data.active_ventilation_remaining_time_min == 12

    def test_sunroof_rear_and_roof_cover_closed_via_windows_list(self):
        client = _vw_client()
        raw = {
            "access": {
                "accessStatus": {
                    "value": {
                        "windows": [
                            {"name": "sunRoofRear", "status": [{"value": "closed"}]},
                            {"name": "roofCover", "status": [{"value": "open"}]},
                        ],
                    },
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.sunroof_rear_closed is True
        assert data.roof_cover_closed is False

    def test_connection_state_battery_power_level(self):
        client = _vw_client()
        raw = {"connectionStatus": {"batteryPowerLevel": "normal"}}
        data = client._parse_status("VINX", raw, parking={})
        assert data.connection_state_battery_power_level == "normal"

    def test_connection_state_battery_power_level_fallback_path(self):
        client = _vw_client()
        raw = {
            "vehicleHealthInspection": {
                "value": {"battery12VLevel": "low"},
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.connection_state_battery_power_level == "low"


# ---------------------------------------------------------------------------
# B) Empty input keeps every new field at None.
# ---------------------------------------------------------------------------


class TestParserEmptyShape:
    def test_empty_dict_leaves_all_new_fields_none(self):
        client = _vw_client()
        data = client._parse_status("VINX", raw={}, parking={})
        # Every Group A new field stays None on an empty backend
        # response (phantom-gate honesty).
        new_fields = [
            "hv_battery_min_temperature_c",
            "hv_battery_max_temperature_c",
            "charge_max_ac_setting",
            "charge_max_ac_ampere",
            "auto_release_ac_connector",
            "auto_release_ac_connector_state",
            "optimised_battery_use",
            "active_ventilation_state",
            "active_ventilation_remaining_time_min",
            "sunroof_rear_closed",
            "roof_cover_closed",
            "connection_state_battery_power_level",
            "last_trip_total_fuel_consumption_l",
            "last_trip_total_electric_consumption_kwh",
        ]
        for field in new_fields:
            assert getattr(data, field) is None, field


# ---------------------------------------------------------------------------
# C) Kelvin / Celsius detection.
# ---------------------------------------------------------------------------


class TestKelvinCelsiusDetection:
    def test_kelvin_value_converted(self):
        client = _vw_client()
        raw = {
            "charging": {
                "batteryStatus": {
                    "value": {"minTemperature_K": 273.15},  # 0 C
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.hv_battery_min_temperature_c == 0.0

    def test_already_celsius_value_left_alone(self):
        """Heuristic: raw <= 200 is treated as already-Celsius (no
        backend has ever shipped a 200 C+ HV battery temp — that
        would be a fire). Values like 22.0 pass through as-is."""
        client = _vw_client()
        raw = {
            "charging": {
                "batteryStatus": {
                    "value": {"maxTemperature_K": 22.0},
                },
            },
        }
        data = client._parse_status("VINX", raw, parking={})
        assert data.hv_battery_max_temperature_c == 22.0


# ---------------------------------------------------------------------------
# D) Trip-statistics totals — backend wins, derive only when both avg
#    and distance are present, and never overwrite a backend total.
# ---------------------------------------------------------------------------


class TestTripTotals:
    def _trip_only(self, last_trip):
        """Run _parse_trip_statistics with a synthetic shortTerm[0]."""
        from custom_components.vag_connect.cariad.models import VehicleData

        client = _vw_client()
        d = VehicleData(vin="VINX")
        client._parse_trip_statistics(
            d,
            short_term={"tripData": [last_trip]},
            long_term={},
        )
        return d

    def test_backend_total_fuel_wins(self):
        d = self._trip_only({
            "mileage_km": 100,
            "averageFuelConsumption": 60,  # 6.0 L/100km -> derived 6.0
            "totalFuelConsumption_l": 5.5,
        })
        # Backend total wins, not the derived 6.0.
        assert d.last_trip_total_fuel_consumption_l == 5.5

    def test_derived_total_fuel_when_no_backend_total(self):
        d = self._trip_only({
            "mileage_km": 100,
            "averageFuelConsumption": 60,  # 6.0 L/100km
        })
        # avg 6.0 * 100km / 100 = 6.0 L
        assert d.last_trip_total_fuel_consumption_l == 6.0

    def test_no_total_when_distance_missing(self):
        d = self._trip_only({
            "averageFuelConsumption": 60,  # avg only, no distance
        })
        # avg without distance leaves total None (can't derive).
        assert d.last_trip_total_fuel_consumption_l is None

    def test_no_total_when_avg_missing(self):
        d = self._trip_only({
            "mileage_km": 100,  # distance only, no avg
        })
        assert d.last_trip_total_fuel_consumption_l is None

    def test_backend_total_electric_wins(self):
        d = self._trip_only({
            "mileage_km": 50,
            "averageElectricEngineConsumption": 200,  # 20 kWh/100km -> derived 10 kWh
            "totalElectricConsumption_kwh": 9.5,
        })
        assert d.last_trip_total_electric_consumption_kwh == 9.5

    def test_derived_total_electric_when_no_backend_total(self):
        d = self._trip_only({
            "mileage_km": 50,
            "averageElectricEngineConsumption": 200,  # 20.0 kWh/100km
        })
        # 20.0 * 50 / 100 = 10.0 kWh
        assert d.last_trip_total_electric_consumption_kwh == 10.0


# ---------------------------------------------------------------------------
# E) Phantom-gate membership.
# ---------------------------------------------------------------------------


class TestPhantomGateMembership:
    def test_sensor_keys_in_data_present_required(self):
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        expected = {
            "hv_battery_min_temperature_c",
            "hv_battery_max_temperature_c",
            "charge_max_ac_setting",
            "charge_max_ac_ampere",
            "auto_release_ac_connector_state",
            "active_ventilation_state",
            "active_ventilation_remaining_time_min",
            "connection_state_battery_power_level",
            "last_trip_total_fuel_consumption_l",
            "last_trip_total_electric_consumption_kwh",
        }
        missing = expected - _DATA_PRESENT_REQUIRED
        assert not missing, (
            f"sensor keys missing from _DATA_PRESENT_REQUIRED: {missing}"
        )

    def test_binary_sensor_keys_in_data_present_required(self):
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        expected = {
            "auto_release_ac_connector",
            "optimised_battery_use",
            "sunroof_rear_closed",
            "roof_cover_closed",
        }
        missing = expected - _DATA_PRESENT_REQUIRED
        assert not missing, (
            f"binary_sensor keys missing from _DATA_PRESENT_REQUIRED: {missing}"
        )

    def test_closed_invert_keys_registered(self):
        """The two ``*_closed`` keys must be in ``_CLOSED_INVERT_KEYS``
        so the entity flips True (closed) to ``is_on = False`` per the
        HA WINDOW device class convention (``on = open``)."""
        from custom_components.vag_connect.binary_sensor import (
            _CLOSED_INVERT_KEYS,
        )

        assert "sunroof_rear_closed" in _CLOSED_INVERT_KEYS
        assert "roof_cover_closed" in _CLOSED_INVERT_KEYS
