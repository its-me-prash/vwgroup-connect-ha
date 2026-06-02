# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.19.3 — Scout-Welle 6 silencing.

Five new community Scout reports landed 2026-05-04/06:

- #143 whaak58 — Skoda 14 fields (charging settings + air-conditioning
  toggles + readiness flags)
- #144 HaaseJ64 — VW ID.4 Pro 24 fields (most already silenced via
  v1.17.5 + earlier wildcards; only audit confirmation needed)
- #145 manentw — VW 10 fields (5 unique + 5 duplicates of #146)
- #146 ammelch — VW 5 fields (subset of #145, shows pattern is
  brand-wide)
- #147 gudden — VW 5 fields (identical to #145/#146 → strong
  3-user convergence)

After audit only **19 truly new paths** needed silencing (most
v1.17.5+v1.12.x wildcards already cover the rest):

- 14 Skoda paths (charging.{settings.*, isVehicleInSavedLocation,
  carCapturedTimestamp, errors.*}, air-conditioning.{airConditioning-
  AtUnlock, seatHeatingActivated.*, windowHeatingEnabled},
  readiness.{ignitionOn, batteryProtectionLimitOn})
- 5 VW paths (5-segment automation.chargingProfiles.value.* leaves +
  3-segment batteryChargingCare/charging/climatisationTimers
  containers)
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# A) Skoda silencing (#143 whaak58)
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaWelle6Silencing:
    def test_charging_settings_lowercase_variants(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["charging"]
        for path in (
            "settings.autoUnlockPlugWhenCharged",
            "settings.availableChargeModes",
            "settings.batteryCareModeTargetValueInPercent",
            "settings.chargingCareMode",
            "settings.maxChargeCurrentAc",
            "settings.preferredChargeMode",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_charging_top_level_meta(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["charging"]
        assert _path_matches("isVehicleInSavedLocation", keys)
        assert _path_matches("carCapturedTimestamp", keys)
        assert _path_matches("errors", keys)
        assert _path_matches("errors.foo", keys)

    def test_air_conditioning_per_feature_toggles(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["air-conditioning"]
        assert _path_matches("airConditioningAtUnlock", keys)
        assert _path_matches("seatHeatingActivated", keys)
        assert _path_matches("seatHeatingActivated.frontLeft", keys)
        assert _path_matches("seatHeatingActivated.frontRight", keys)
        assert _path_matches("windowHeatingEnabled", keys)

    def test_readiness_new_flags(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["readiness"]
        assert _path_matches("ignitionOn", keys)
        assert _path_matches("batteryProtectionLimitOn", keys)

    def test_full_skoda_payload_silent(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        # charging endpoint (all 9 new fields)
        ch = {
            "isVehicleInSavedLocation": True,
            "carCapturedTimestamp": "2026-05-04T18:37:27Z",
            "errors": [{"code": "X"}],
            "settings": {
                "autoUnlockPlugWhenCharged": "OFF",
                "availableChargeModes": ["MANUAL"],
                "batteryCareModeTargetValueInPercent": 80,
                "chargingCareMode": "ACTIVATED",
                "maxChargeCurrentAc": "MAXIMUM",
                "preferredChargeMode": "MANUAL",
            },
        }
        assert list(detect_unexpected("skoda", "charging", ch)) == []

        # air-conditioning (3 new fields with seat dict)
        ac = {
            "airConditioningAtUnlock": False,
            "seatHeatingActivated": {"frontLeft": False, "frontRight": False},
            "windowHeatingEnabled": False,
        }
        assert list(detect_unexpected("skoda", "air-conditioning", ac)) == []

        # readiness (2 new flags)
        r = {"ignitionOn": False, "batteryProtectionLimitOn": False}
        assert list(detect_unexpected("skoda", "readiness", r)) == []


# ─────────────────────────────────────────────────────────────────────────────
# B) VW silencing (#145/#146/#147 convergent)
# ─────────────────────────────────────────────────────────────────────────────


class TestVolkswagenWelle6Silencing:
    def test_5_segment_charging_profile_timer(self):
        """3 convergent reports show 5-segment leaves under
        automation.chargingProfiles.value.nextChargingTimer.*."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "automation.chargingProfiles.value.nextChargingTimer.id", keys,
        )
        assert _path_matches(
            "automation.chargingProfiles.value.nextChargingTimer.targetSOCreachable",
            keys,
        )

    def test_battery_charging_care_settings_value(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "batteryChargingCare.chargingCareSettings.value", keys,
        )
        # 4-segment future-proofing
        assert _path_matches(
            "batteryChargingCare.chargingCareSettings.value.someFutureKey", keys,
        )

    def test_charging_care_settings_battery_care_mode(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "charging.chargingCareSettings.value.batteryCareMode", keys,
        )

    def test_climatisation_timers_status_value(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "climatisationTimers.climatisationTimersStatus.value", keys,
        )
        # Future-proof for nested children
        assert _path_matches(
            "climatisationTimers.climatisationTimersStatus.value.timerId", keys,
        )

    def test_audi_inheritance_silent(self):
        """Audi inherits VW EU's selectivestatus shape — all VW
        Welle-6 silencings should also silence audi automatically."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["audi"]["selectivestatus"]
        assert _path_matches(
            "automation.chargingProfiles.value.nextChargingTimer.id", keys,
        )
        assert _path_matches(
            "batteryChargingCare.chargingCareSettings.value", keys,
        )
        assert _path_matches(
            "climatisationTimers.climatisationTimersStatus.value", keys,
        )

    def test_full_vw_payload_silent_convergent_reports(self):
        """Replay the convergent 5-field VW payload from #145/#146/#147."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        vw = {
            "automation": {
                "chargingProfiles": {
                    "value": {
                        "nextChargingTimer": {
                            "id": 0,
                            "targetSOCreachable": "calculating",
                        },
                    },
                },
            },
            "batteryChargingCare": {
                "chargingCareSettings": {"value": {}},
            },
            "charging": {
                "chargingCareSettings": {
                    "value": {"batteryCareMode": "activated"},
                },
            },
            "climatisationTimers": {
                "climatisationTimersStatus": {"value": {}},
            },
        }
        assert list(detect_unexpected("volkswagen", "selectivestatus", vw)) == []
