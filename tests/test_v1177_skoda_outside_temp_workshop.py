# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.17.7 — Skoda outside_temperature + preferred_workshop attrs.

Wires up two existing-but-not-Skoda-populated data points:

1. ``outside_temp`` (existing field on VehicleData since early releases,
   already populated by VW EU + SEAT/CUPRA, exposed as a sensor in
   ``sensor.py``). Skoda backend started shipping this on the air-
   conditioning endpoint per #129/#130/#133 Scout reports.

2. ``preferred_workshop`` (new field on VehicleData) — surfaced as
   ``extra_state_attributes`` on the existing ``service_due_in_days``
   sensor (#130/#133 Scout reports).

Both are PATCH-level changes (no new sensors, no new entity_ids, no new
translation keys, no new platforms — purely new data sources for fields
the integration already knows about).

Test pattern follows v1.15.0 Skoda Modernization: parsing logic in
``skoda.py:get_status`` is inline (one big method), so we reproduce
the relevant parse blocks in tests rather than mocking the full HTTP
gather pipeline. This matches the existing convention in
``tests/test_v1150_skoda_modernization.py``.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# A) outside_temperature parsing block (Skoda air-conditioning endpoint)
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaOutsideTemperatureBlock:
    """Reproduces the air-conditioning outsideTemperature parse block
    from ``skoda.py:get_status`` so we can verify it standalone without
    mocking the full network gather pipeline.

    The block under test (in skoda.py around line 312-330):

        outside_t = v(ac, "outsideTemperature", "temperatureValue")
        if outside_t is not None:
            unit = v(ac, "outsideTemperature", "temperatureUnit")
            ot_val = safe_float(outside_t)
            if ot_val is not None:
                if unit == "FAHRENHEIT":
                    ot_val = round((ot_val - 32) * 5 / 9, 1)
                d.outside_temp = ot_val
    """

    def _parse(self, ac):
        """Reproduce the v1.17.7 outsideTemperature parse block."""
        from custom_components.vag_connect.cariad._util import safe_float
        from custom_components.vag_connect.cariad.models import VehicleData

        def v(d, *keys):
            cur = d
            for k in keys:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(k)
            return cur

        veh = VehicleData(vin="TMBJR8NX2RY179915")
        outside_t = v(ac, "outsideTemperature", "temperatureValue")
        if outside_t is not None:
            unit = v(ac, "outsideTemperature", "temperatureUnit")
            ot_val = safe_float(outside_t)
            if ot_val is not None:
                if unit == "FAHRENHEIT":
                    ot_val = round((ot_val - 32) * 5 / 9, 1)
                veh.outside_temp = ot_val
        return veh

    def test_celsius_value_parsed(self):
        """#129/#130/#133 — backend ships native Celsius."""
        ac = {
            "outsideTemperature": {
                "temperatureValue": 24.0,
                "temperatureUnit": "CELSIUS",
                "carCapturedTimestamp": "2026-05-03T13:08:24Z",
            },
        }
        d = self._parse(ac)
        assert d.outside_temp == 24.0

    def test_fahrenheit_converted_to_celsius(self):
        """Defensive — backend always sends CELSIUS for Skoda but if a
        future region/firmware ships Fahrenheit, convert."""
        ac = {
            "outsideTemperature": {
                "temperatureValue": 75.2,
                "temperatureUnit": "FAHRENHEIT",
            },
        }
        d = self._parse(ac)
        # 75.2 F == 24.0 C
        assert d.outside_temp == 24.0

    def test_string_dot_decimal_value(self):
        """Defensive — temperatureValue may arrive as a stringified
        decimal (Skoda firmwares occasionally do this for cached
        responses). safe_float handles dot-decimal strings."""
        ac = {
            "outsideTemperature": {
                "temperatureValue": "21.5",
                "temperatureUnit": "CELSIUS",
            },
        }
        d = self._parse(ac)
        assert d.outside_temp == 21.5

    def test_missing_block_leaves_field_none(self):
        ac = {}  # No outsideTemperature
        d = self._parse(ac)
        assert d.outside_temp is None

    def test_partial_block_leaves_field_none(self):
        """If temperatureValue missing, leave field alone — do not crash."""
        ac = {"outsideTemperature": {"temperatureUnit": "CELSIUS"}}
        d = self._parse(ac)
        assert d.outside_temp is None

    def test_garbage_value_safe_float_returns_none(self):
        ac = {"outsideTemperature": {"temperatureValue": "not-a-number"}}
        d = self._parse(ac)
        assert d.outside_temp is None

    def test_unit_default_assumed_celsius(self):
        """If temperatureUnit is missing, treat as CELSIUS (no
        conversion). All three Scout reports confirm Skoda uses
        CELSIUS by default."""
        ac = {"outsideTemperature": {"temperatureValue": 18.5}}
        d = self._parse(ac)
        assert d.outside_temp == 18.5


# ─────────────────────────────────────────────────────────────────────────────
# B) preferred_workshop parsing block (Skoda maintenance endpoint)
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaPreferredWorkshopBlock:
    """Reproduces the maintenance preferredServicePartner parse block.

    The block under test:

        workshop = v(maintenance, "preferredServicePartner")
        if isinstance(workshop, dict) and workshop:
            trimmed = {k: val for k, val in workshop.items()
                       if k != "openingHours"}
            d.preferred_workshop = trimmed
    """

    def _parse(self, maintenance):
        from custom_components.vag_connect.cariad.models import VehicleData

        def v(d, *keys):
            cur = d
            for k in keys:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(k)
            return cur

        veh = VehicleData(vin="TMBJR8NX2RY179915")
        workshop = v(maintenance, "preferredServicePartner")
        if isinstance(workshop, dict) and workshop:
            trimmed = {
                k: val for k, val in workshop.items()
                if k != "openingHours"
            }
            veh.preferred_workshop = trimmed
        return veh

    def test_workshop_dict_passed_through(self):
        m = {
            "maintenanceReport": {"inspectionDueInDays": 365},
            "preferredServicePartner": {
                "name": "Jahnsmüller GmbH",
                "brand": "C",
                "partnerNumber": "53040",
                "id": "DEUC53040",
                "contact": {"phone": "+49…", "email": "info@…"},
                "address": {"street": "Hauptstr. 1", "city": "Beispielstadt"},
                "location": {"lat": 52.5, "lon": 13.4},
            },
        }
        d = self._parse(m)
        assert d.preferred_workshop is not None
        assert d.preferred_workshop["name"] == "Jahnsmüller GmbH"
        assert d.preferred_workshop["partnerNumber"] == "53040"
        assert "contact" in d.preferred_workshop
        assert d.preferred_workshop["contact"]["phone"] == "+49…"

    def test_opening_hours_dropped(self):
        """openingHours is large + rarely actionable in HA UI — trimmed
        from attrs to keep state machine lean."""
        m = {
            "preferredServicePartner": {
                "name": "X",
                "openingHours": [
                    {"weekday": "MONDAY"},
                    {"weekday": "TUESDAY"},
                    {"weekday": "WEDNESDAY"},
                ],
            },
        }
        d = self._parse(m)
        assert d.preferred_workshop is not None
        assert d.preferred_workshop["name"] == "X"
        assert "openingHours" not in d.preferred_workshop

    def test_missing_workshop_leaves_field_none(self):
        m = {"maintenanceReport": {"inspectionDueInDays": 365}}
        d = self._parse(m)
        assert d.preferred_workshop is None

    def test_empty_workshop_dict_leaves_field_none(self):
        """Empty dict {} should NOT populate (avoid empty attrs blob in HA)."""
        m = {"preferredServicePartner": {}}
        d = self._parse(m)
        assert d.preferred_workshop is None

    def test_non_dict_workshop_leaves_field_none(self):
        """Defensive against backend shape changes."""
        m = {"preferredServicePartner": "not-a-dict"}
        d = self._parse(m)
        assert d.preferred_workshop is None

    def test_realistic_full_payload_from_133(self):
        """Replay verbatim shape from #133 christianmhz Scout report."""
        m = {
            "preferredServicePartner": {
                "name": "Jahnsmüller GmbH",
                "brand": "C",
                "partnerNumber": "53040",
                "id": "DEUC53040",
                "contact": {"phone": "+49…", "email": "info@…", "fax": "+49…"},
                "address": {
                    "street": "Hauptstr. 1",
                    "city": "Beispielstadt",
                    "postalCode": "12345",
                    "country": "DE",
                },
                "location": {"lat": 52.5, "lon": 13.4},
                "openingHours": [
                    {"weekday": "MONDAY", "open": "08:00", "close": "18:00"},
                    {"weekday": "TUESDAY", "open": "08:00", "close": "18:00"},
                ],
            },
            "customerService": {
                "activeBookings": [],
                "bookingHistory": [
                    {"id": 1, "date": "2026-01-15"},
                    {"id": 2, "date": "2025-07-10"},
                ],
            },
        }
        d = self._parse(m)
        assert d.preferred_workshop is not None
        assert d.preferred_workshop["partnerNumber"] == "53040"
        # All scalar+nested-dict fields preserved, only openingHours dropped.
        assert "name" in d.preferred_workshop
        assert "brand" in d.preferred_workshop
        assert "id" in d.preferred_workshop
        assert "contact" in d.preferred_workshop
        assert "address" in d.preferred_workshop
        assert "location" in d.preferred_workshop
        assert "openingHours" not in d.preferred_workshop
        # 7 keys total (8 minus openingHours)
        assert len(d.preferred_workshop) == 7


# ─────────────────────────────────────────────────────────────────────────────
# C) Model field invariant
# ─────────────────────────────────────────────────────────────────────────────


class TestVehicleDataPreferredWorkshopField:
    def test_field_exists_and_default_none(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        assert hasattr(d, "preferred_workshop")
        assert d.preferred_workshop is None

    def test_field_accepts_dict(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        d.preferred_workshop = {"name": "X"}
        assert d.preferred_workshop == {"name": "X"}
