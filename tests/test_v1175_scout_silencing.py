# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.17.5 — Scout silencing for #129/#130/#131/#132/#133.

Five Vehicle Data Scout reports landed within 24h on 2026-05-03/04:

- #129 rocksandclouds — Skoda 3 fields (`outsideTemperature.*`)
- #130 Chr1sDub       — Skoda 13 fields (outsideTemp + preferredServicePartner
                        + customerService)
- #132 rborkenhagen   — VW 3 fields (heaterSource, departureTimers,
                        secondaryEngineType=electric)
- #133 christianmhz   — Skoda 15 fields (outsideTemp + preferredServicePartner
                        + customerService + targetTemperature.unitInCar +
                        parking errors[])
- #53 (Gerhard, post-v1.17.4 test) — Cupra 8 fields (services.charging/
        climatisation/windowHeating + settings.maxChargeCurrentAc +
        settings.autoUnlockPlugWhenChargedAc + settings.targetSoc +
        chargingCareSettings.batteryCareMode + chargingCareStatus.
        batteryCareTargetSoc)

v1.17.5 registers all of these in EXPECTED_KEYS so the Scout stops firing.
No new sensors are wired (that's deferred to a future MINOR — strict
semver per ROADMAP).
"""

from __future__ import annotations


class TestSkodaScoutSilencing129_130_133:
    """Three converging Skoda Scout reports — outsideTemperature +
    preferredServicePartner + customerService + parking errors[] +
    targetTemperature.unitInCar."""

    def test_outside_temperature_wildcard_covers_three_leaves(self):
        """#129/#130/#133 all reported `outsideTemperature.{temperatureValue,
        temperatureUnit, carCapturedTimestamp}`. Wildcard registration
        in EXPECTED_KEYS["skoda"]["air-conditioning"] covers all three."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["air-conditioning"]
        for path in (
            "outsideTemperature.temperatureValue",
            "outsideTemperature.temperatureUnit",
            "outsideTemperature.carCapturedTimestamp",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_target_temperature_unit_in_car(self):
        """#133 christianmhz — new sibling of temperatureValue under
        targetTemperature."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["air-conditioning"]
        assert _path_matches("targetTemperature.unitInCar", keys)

    def test_preferred_service_partner_wildcard(self):
        """#130/#133 — 8 children under preferredServicePartner. Wildcard
        covers all current + future fields."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["maintenance"]
        for path in (
            "preferredServicePartner.name",
            "preferredServicePartner.brand",
            "preferredServicePartner.partnerNumber",
            "preferredServicePartner.id",
            "preferredServicePartner.contact",
            "preferredServicePartner.address",
            "preferredServicePartner.location",
            "preferredServicePartner.openingHours",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_customer_service_wildcard(self):
        """#130/#133 — 2 children under customerService. Wildcard covers
        the bookings/history split + any future status enums."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["maintenance"]
        assert _path_matches("customerService.activeBookings", keys)
        assert _path_matches("customerService.bookingHistory", keys)

    def test_parking_errors_wildcard(self):
        """#133 christianmhz — Skoda mysmob now wraps lookup failures in
        an errors[] array on the parking endpoint (mirrors air-
        conditioning + driving-range patterns)."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["skoda"]["parking"]
        assert _path_matches("errors", keys)
        assert _path_matches("errors.foo", keys)

    def test_full_skoda_payload_silent_combined(self):
        """Replay all Skoda findings from #129+#130+#133 combined. Detector
        must yield zero unexpected paths across all four endpoints."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        ac = {
            "outsideTemperature": {
                "temperatureValue": 24.0,
                "temperatureUnit": "CELSIUS",
                "carCapturedTimestamp": "2026-05-03T13:08:24Z",
            },
            "targetTemperature": {"unitInCar": "CELSIUS"},
        }
        assert list(detect_unexpected("skoda", "air-conditioning", ac)) == []

        m = {
            "preferredServicePartner": {
                "name": "Jahnsmüller GmbH",
                "brand": "C",
                "partnerNumber": "53040",
                "id": "DEUC53040",
                "contact": {"phone": "+49…"},
                "address": {"street": "..."},
                "location": {"lat": 50.0, "lon": 10.0},
                "openingHours": [{"weekday": "MONDAY"}],
            },
            "customerService": {
                "activeBookings": [],
                "bookingHistory": [{"id": 1}, {"id": 2}],
            },
        }
        assert list(detect_unexpected("skoda", "maintenance", m)) == []

        p = {"errors": [{"code": "POSITION_UNKNOWN"}]}
        assert list(detect_unexpected("skoda", "parking", p)) == []


class TestVolkswagenScoutSilencing132:
    """rborkenhagen 2026-05-04 — VW selectivestatus 3 new leaves."""

    def test_climatisation_heater_source(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "climatisation.climatisationSettings.value.heaterSource", keys,
        )

    def test_secondary_engine_type(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "measurements.fuelLevelStatus.value.secondaryEngineType", keys,
        )

    def test_departure_timers_wildcard(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches("departureTimers", keys)
        assert _path_matches("departureTimers.foo", keys)

    def test_audi_inheritance_silent(self):
        """Audi inherits VW EU's selectivestatus shape — all three new
        VW silencings should also work for audi without separate
        registration."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["audi"]["selectivestatus"]
        assert _path_matches(
            "climatisation.climatisationSettings.value.heaterSource", keys,
        )
        assert _path_matches(
            "measurements.fuelLevelStatus.value.secondaryEngineType", keys,
        )
        assert _path_matches("departureTimers", keys)

    def test_full_vw_payload_silent(self):
        """Replay verbatim findings from #132. Detector returns zero."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        ss = {
            "climatisation": {
                "climatisationSettings": {
                    "value": {"heaterSource": "electric"},
                },
            },
            "measurements": {
                "fuelLevelStatus": {
                    "value": {"secondaryEngineType": "electric"},
                },
            },
            "departureTimers": {"timer1": {"enabled": True}, "timer2": {}},
        }
        assert list(detect_unexpected("volkswagen", "selectivestatus", ss)) == []


class TestCupraScoutSilencingGerhardBornV1174:
    """Gerhard's #53 follow-up after v1.17.4 install — 8 new Cupra fields
    spread across mycar (services.*) and charging-info (settings.* +
    chargingCareSettings.* + chargingCareStatus.*)."""

    def test_services_wildcard_on_mycar(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["cupra"]["mycar"]
        for path in (
            "services.charging",
            "services.climatisation",
            "services.windowHeating",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_charging_info_settings_wildcard(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["cupra"]["charging-info"]
        # lowercase Ac variant (Born 2026 firmware) alongside legacy AC.
        for path in (
            "settings.maxChargeCurrentAc",
            "settings.autoUnlockPlugWhenChargedAc",
            "settings.targetSoc",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_charging_care_settings_status_wildcards(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        keys = EXPECTED_KEYS["cupra"]["charging-info"]
        assert _path_matches("chargingCareSettings.batteryCareMode", keys)
        assert _path_matches("chargingCareStatus.batteryCareTargetSoc", keys)

    def test_seat_inheritance_silent(self):
        """SEAT inherits CUPRA's OLA shape. New silencings work for seat
        too."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            _path_matches, EXPECTED_KEYS,
        )
        seat_mycar = EXPECTED_KEYS["seat"]["mycar"]
        assert _path_matches("services.charging", seat_mycar)
        seat_ci = EXPECTED_KEYS["seat"]["charging-info"]
        assert _path_matches("settings.targetSoc", seat_ci)

    def test_full_cupra_born_payload_silent(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        mycar = {
            "services": {
                "charging": {"sub": "active", "limit": 10},
                "climatisation": {"sub": "active"},
                "windowHeating": {"sub": "active"},
            },
        }
        assert list(detect_unexpected("cupra", "mycar", mycar)) == []

        ci = {
            "settings": {
                "maxChargeCurrentAc": "reduced",
                "autoUnlockPlugWhenChargedAc": "off",
                "targetSoc": 80,
            },
            "chargingCareSettings": {"batteryCareMode": True},
            "chargingCareStatus": {"batteryCareTargetSoc": 80},
        }
        assert list(detect_unexpected("cupra", "charging-info", ci)) == []
