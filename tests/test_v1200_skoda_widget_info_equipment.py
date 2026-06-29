# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.20.0 Bundle 2 Phase A — Skoda widget + vehicle-info + equipment.

Three new endpoints from skodaconnect/myskoda (MIT-licensed,
attributed in NOTICE.md):

1. ``GET /api/v2/widgets/vehicle-status/{vin}`` (myskoda PR #557)
   Lightweight glance-card payload — license plate, render image
   URL, formatted parking address. Wired into per-tick get_status.

2. ``GET /api/v1/vehicle-information/{vin}``
   Static device data (model, year, software version). Cached 24h
   via coordinator.refresh_static_info.

3. ``GET /api/v1/vehicle-information/{vin}/equipment``
   Static equipment list (heated steering, towbar, ...). Same 24h
   cache.

Tests cover: parser blocks (widget vehicle.* + parking.formattedAddress),
EXPECTED_KEYS coverage, model field defaults, sensor description
exposure, and full payload silencing.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# A) Widget endpoint — parser block
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaWidgetParseBlock:
    """Reproduces the widget parse-block from skoda.py:get_status."""

    def _parse(self, widget):
        from custom_components.vag_connect.cariad.models import VehicleData

        def v(d, *keys):
            cur = d
            for k in keys:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(k)
            return cur

        veh = VehicleData(vin="TMBJR8NX2RY179915")
        if isinstance(widget, dict):
            vehicle_meta = v(widget, "vehicle") or {}
            if isinstance(vehicle_meta, dict):
                lic = vehicle_meta.get("licensePlate")
                if isinstance(lic, str) and lic:
                    veh.license_plate = lic
                render = vehicle_meta.get("renderUrl")
                if isinstance(render, str) and render.startswith("http"):
                    veh.render_url = render
            addr = v(widget, "parkingPosition", "formattedAddress")
            if isinstance(addr, str) and addr and not veh.parking_address:
                veh.parking_address = addr
        return veh

    def test_parsed_widget_full_payload(self):
        """Verbatim shape from myskoda's widget-parked.json fixture."""
        widget = {
            "vehicle": {
                "name": "Octavia iV",
                "licensePlate": "BE-XXX-1234",
                "renderUrl": "https://images.skoda-auto.com/render/octavia.png",
            },
            "vehicleStatus": {
                "doorsLocked": True,
                "drivingRangeInKm": 380,
            },
            "chargingStatus": {
                "stateOfChargeInPercent": 80,
                "remainingTimeToFullyChargedInMinutes": 45,
            },
            "parkingPosition": {
                "state": "PARKED",
                "maps": {
                    "lightMapUrl": "https://maps.example/light.png",
                    "darkMapUrl": "https://maps.example/dark.png",
                },
                "gpsCoordinates": {"latitude": 52.5, "longitude": 13.4},
                "formattedAddress": "Hauptstraße 1, 12345 Berlin",
            },
        }
        d = self._parse(widget)
        assert d.license_plate == "BE-XXX-1234"
        assert d.render_url == "https://images.skoda-auto.com/render/octavia.png"
        assert d.parking_address == "Hauptstraße 1, 12345 Berlin"

    def test_parsed_widget_missing_blocks(self):
        """Missing vehicle / parkingPosition → no fields set, no crash."""
        d = self._parse({})
        assert d.license_plate is None
        assert d.render_url is None
        assert d.parking_address is None

    def test_parsed_widget_partial_vehicle(self):
        """Only some fields present → others stay None."""
        widget = {"vehicle": {"licensePlate": "BE-X-1"}}
        d = self._parse(widget)
        assert d.license_plate == "BE-X-1"
        assert d.render_url is None

    def test_render_url_only_if_http(self):
        """Defensive — backend could send a relative path or empty
        string; we only accept absolute http(s) URLs."""
        d = self._parse({"vehicle": {"renderUrl": "/relative/path"}})
        assert d.render_url is None
        d = self._parse({"vehicle": {"renderUrl": ""}})
        assert d.render_url is None
        d = self._parse({"vehicle": {"renderUrl": "https://x"}})
        assert d.render_url == "https://x"

    def test_widget_address_does_not_clobber_existing(self):
        """If parking parser already set parking_address (from
        /v3/maps/positions endpoint), widget shouldn't overwrite."""
        from custom_components.vag_connect.cariad.models import VehicleData
        veh = VehicleData(vin="TEST")
        veh.parking_address = "Already set address"
        # Re-run parse manually with pre-set field
        widget = {"parkingPosition": {"formattedAddress": "Different address"}}
        addr = (widget.get("parkingPosition") or {}).get("formattedAddress")
        if isinstance(addr, str) and addr and not veh.parking_address:
            veh.parking_address = addr
        # parking_address kept original
        assert veh.parking_address == "Already set address"


# ─────────────────────────────────────────────────────────────────────────────
# B) Equipment list parsing
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaEquipmentParse:
    """Reproduces the equipment parse from get_vehicle_static_info +
    coordinator._enrich."""

    def test_equipment_count_derived(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        veh = VehicleData(vin="TEST")
        equip = [
            {"id": "1234", "name": "Heated steering wheel"},
            {"id": "5678", "name": "Towbar"},
            {"id": "9012", "name": "Panoramic sunroof"},
        ]
        veh.equipment = equip
        veh.equipment_count = len(equip)
        assert veh.equipment_count == 3
        assert veh.equipment[0]["name"] == "Heated steering wheel"

    def test_empty_equipment_list(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        veh = VehicleData(vin="TEST")
        veh.equipment = []
        veh.equipment_count = 0
        assert veh.equipment_count == 0
        assert veh.equipment == []


# ─────────────────────────────────────────────────────────────────────────────
# C) EXPECTED_KEYS coverage for widget endpoint
# ─────────────────────────────────────────────────────────────────────────────


class TestWidgetExpectedKeys:
    def test_widget_endpoint_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        assert "widget" in EXPECTED_KEYS["skoda"]

    def test_widget_full_payload_silent(self):
        """myskoda fixture-like payload returns 0 unexpected paths."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        widget = {
            "vehicle": {
                "name": "Octavia iV",
                "licensePlate": "BE-XXX-1234",
                "renderUrl": "https://...",
            },
            "vehicleStatus": {
                "doorsLocked": True,
                "drivingRangeInKm": 380,
            },
            "chargingStatus": {
                "stateOfChargeInPercent": 80,
                "remainingTimeToFullyChargedInMinutes": 45,
            },
            "parkingPosition": {
                "state": "PARKED",
                "maps": {
                    "lightMapUrl": "https://...",
                    "darkMapUrl": "https://...",
                },
                "gpsCoordinates": {"latitude": 52.5, "longitude": 13.4},
                "formattedAddress": "...",
            },
        }
        unexp = list(detect_unexpected("skoda", "widget", widget))
        assert unexp == [], f"unexpected: {unexp}"

    def test_widget_inmotion_payload_silent(self):
        """Wenn das Vehicle in motion ist, fehlen einige optional fields."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        widget = {
            "vehicle": {"name": "X", "licensePlate": "Y", "renderUrl": "z"},
            "vehicleStatus": {"doorsLocked": False, "drivingRangeInKm": 200},
            "parkingPosition": {"state": "DRIVING"},
        }
        unexp = list(detect_unexpected("skoda", "widget", widget))
        assert unexp == [], f"unexpected: {unexp}"


# ─────────────────────────────────────────────────────────────────────────────
# D) Model field defaults
# ─────────────────────────────────────────────────────────────────────────────


class TestVehicleDataNewFields:
    def test_license_plate_default_none(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        assert hasattr(d, "license_plate")
        assert d.license_plate is None

    def test_render_url_default_none(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        assert hasattr(d, "render_url")
        assert d.render_url is None

    def test_equipment_default_none(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        assert hasattr(d, "equipment")
        assert d.equipment is None

    def test_equipment_count_default_none(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        assert hasattr(d, "equipment_count")
        assert d.equipment_count is None


# ─────────────────────────────────────────────────────────────────────────────
# E) Sensor exposure
# ─────────────────────────────────────────────────────────────────────────────


class TestNewSensorExposure:
    def test_license_plate_sensor_present(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "license_plate" in keys

    def test_equipment_count_sensor_present(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "equipment_count" in keys

    def test_both_sensors_diagnostic(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
        from homeassistant.helpers.entity import EntityCategory
        for key in ("license_plate", "equipment_count"):
            desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
            assert desc.entity_category == EntityCategory.DIAGNOSTIC


# ─────────────────────────────────────────────────────────────────────────────
# F) Static-info coordinator helper
# ─────────────────────────────────────────────────────────────────────────────


class TestStaticInfoCacheConstants:
    def test_24h_refresh_interval(self):
        """Static data shouldn't refresh more often than 24h —
        same pattern as capabilities cache (saves API quota)."""
        from datetime import timedelta
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        assert VagConnectCoordinator._STATIC_INFO_REFRESH_INTERVAL == timedelta(hours=24)

    def test_brand_restricted_to_skoda(self):
        """Other brands don't have an analogous endpoint set yet —
        only skoda is wired in v1.20.0 Phase A."""
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        assert VagConnectCoordinator._STATIC_INFO_BRANDS == ("skoda",)
