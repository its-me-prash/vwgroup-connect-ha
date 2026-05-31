# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Tests for v1.12.3 — #111 Audi Scout coverage (DnnsJp74's report).

Second community Scout report from a non-maintainer (DnnsJp74 on
2026-05-01 — first was tritanium73's #107 for Skoda). 23 new paths
across the CARIAD-BFF selectivestatus endpoint. v1.12.3 registers
all of them in EXPECTED_KEYS["volkswagen"] (Audi inherits via the
table alias).
"""

from __future__ import annotations



class TestAudiScout111:
    def test_all_23_paths_registered(self):
        """Verbatim DnnsJp74's #111 report — synthetic payload that
        nests every reported path. v1.12.3 registry must silence them
        all (returns empty findings list)."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )

        # Synthesize the structure DnnsJp74 reported. Use list values
        # for [N items] containers (Scout doesn't recurse into lists).
        payload = {
            "automation": {
                "climatisationTimer": {"value": {"a": 1, "b": 2, "c": 3}},
                "chargingProfiles": {"value": {"a": 1, "b": 2, "c": 3, "d": 4}},
            },
            "batteryChargingCare": {"someKey": "someValue"},
            "userCapabilities": {"capabilitiesStatus": {"value": [
                {"id": "x"}, {"id": "y"},
            ]}},  # 52 items in real report
            "charging": {
                "chargingSettings": {"value": {"autoUnlockPlugWhenCharged": "off"}},
                "chargeMode": {"value": {"a": 1, "b": 2}},
                "chargingCareSettings": {"a": 1},
            },
            "climatisation": {
                "climatisationSettings": {"value": {
                    "unitInCar": "celsius",
                    "climatizationAtUnlock": True,
                    "windowHeatingEnabled": False,
                    "zoneFrontLeftEnabled": True,
                    "zoneFrontRightEnabled": True,
                }},
            },
            "climatisationTimers": {"a": 1},
            "fuelStatus": {"rangeStatus": {"value": [
                {"a": 1}, {"b": 2},
            ]}},  # 4 keys in real report (use list to be opaque)
            "measurements": {
                "temperatureBatteryStatus": {"value": {
                    "temperatureHvBatteryMin_K": "284.15",
                    "temperatureHvBatteryMax_K": "285.15",
                }},
            },
            "readiness": {
                "readinessStatus": {"value": {
                    "connectionState": {
                        "isOnline": True,
                        "isActive": False,
                        "batteryPowerLevel": "comfort",
                        "dailyPowerBudgetAvailable": True,
                    },
                    "connectionWarning": {
                        "insufficientBatteryLevelWarning": False,
                        "dailyPowerBudgetWarning": False,
                    },
                }},
            },
            "vehicleHealthWarnings": {"warningLights": {"value": {
                "a": 1, "b": 2,
            }}},  # 2 keys in real report
        }

        # Use volkswagen brand — Audi inherits the same table.
        findings = list(detect_unexpected("volkswagen", "selectivestatus", payload))
        unexpected_paths = [f.path for f in findings]

        assert findings == [], (
            "Scout still finds unexpected paths after v1.12.3 registry: "
            + ", ".join(unexpected_paths)
        )

    def test_audi_inherits_via_table_alias(self):
        """Defensive: Audi sees the same table as VW EU."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        assert EXPECTED_KEYS["audi"] is EXPECTED_KEYS["volkswagen"]

    def test_climatisation_zone_fields_individually_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        for path in (
            "climatisation.climatisationSettings.value.unitInCar",
            "climatisation.climatisationSettings.value.climatizationAtUnlock",
            "climatisation.climatisationSettings.value.windowHeatingEnabled",
            "climatisation.climatisationSettings.value.zoneFrontLeftEnabled",
            "climatisation.climatisationSettings.value.zoneFrontRightEnabled",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_battery_temperature_min_max_both_registered(self):
        """v1.12.3 — Min/Max temperature fields. Min is read by parser
        for battery_temp sensor (since v1.10.x), Max is new metadata."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "measurements.temperatureBatteryStatus.value.temperatureHvBatteryMin_K", keys
        )
        assert _path_matches(
            "measurements.temperatureBatteryStatus.value.temperatureHvBatteryMax_K", keys
        )

    def test_readiness_connection_state_4_subfields(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        for sub in (
            "isOnline", "isActive", "batteryPowerLevel", "dailyPowerBudgetAvailable",
        ):
            path = f"readiness.readinessStatus.value.connectionState.{sub}"
            assert _path_matches(path, keys), f"missing: {path}"

    def test_battery_charging_care_top_level_with_wildcard(self):
        """Top-level meta block + future-proof wildcard for unknown
        children. Same defensive pattern as climatisationTimers."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches("batteryChargingCare", keys)
        assert _path_matches("batteryChargingCare.someUnknownChild", keys)
        assert _path_matches("climatisationTimers", keys)
        assert _path_matches("climatisationTimers.someTimer", keys)

    def test_113_golf_gte_payload_silent(self):
        """v1.12.3 also silences #113 (Prash's Golf GTE 14 fields).
        Pattern: deeper children of .value containers from v1.12.1."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        payload = {
            "departureProfiles": {"departureProfilesStatus": {"value": {
                "carCapturedTimestamp": "2026-04-12T15:18:26Z",
                "minSOC_pct": 60,
                "timers": [],
                "profiles": [],
            }}},
            "fuelStatus": {"rangeStatus": {"value": {
                "carCapturedTimestamp": "2026-05-01T15:25:26Z",
                "carType": "electric",
                "primaryEngine": {"type": "electric", "remainingRange_km": 8, "currentSOC_pct": 30},
                "totalRange_km": 8,
            }}},
            "vehicleHealthInspection": {"maintenanceStatus": {"value": {
                "carCapturedTimestamp": "2026-05-01T13:26:33Z",
                "inspectionDue_days": 207,
                "inspectionDue_km": 18300,
                "mileage_km": 158597,
                "oilServiceDue_days": 17,
                "oilServiceDue_km": 1700,
            }}},
        }
        findings = list(detect_unexpected("volkswagen", "selectivestatus", payload))
        assert findings == [], (
            "Scout still finds unexpected paths after v1.12.3 wildcards: "
            + ", ".join(f.path for f in findings)
        )

    def test_114_audi_s6_payload_silent(self):
        """v1.12.3 also silences #114 (Prash's Audi S6 C8 Diesel 20 fields).
        Same wildcard coverage as #113 (Audi inherits VW EU table)."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        payload = {
            "fuelStatus": {"rangeStatus": {"value": {
                "carCapturedTimestamp": "2026-04-15T16:33:31Z",
                "carType": "diesel",
                "primaryEngine": {
                    "type": "diesel",
                    "remainingRange_km": 260,
                    "currentFuelLevel_pct": 60,
                    "remainingFuelInLitre": 30,
                },
                "totalRange_km": 260,
            }}},
            "vehicleHealthInspection": {"maintenanceStatus": {"value": {
                "carCapturedTimestamp": "2026-04-15T16:33:29Z",
                "inspectionDue_days": 512,
                "inspectionDue_km": 12900,
                "mileage_km": 226085,
                "oilServiceDue_days": 512,
                "oilServiceDue_km": 12900,
            }}},
        }
        # Audi inherits volkswagen table — using either brand works
        findings = list(detect_unexpected("audi", "selectivestatus", payload))
        assert findings == [], (
            "Scout still finds unexpected paths after v1.12.3 wildcards: "
            + ", ".join(f.path for f in findings)
        )
