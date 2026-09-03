# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b7 — grounded-audit regression fixes.

One test module per finding from the competitor-grounded audit sweep. Each pins the
exact behaviour the fix changed so it can't silently regress:

* P0-2a — parking_city redacted in diagnostics (cleartext city leak).
* P1-2  — parked-GPS TTL honours a datetime last_seen_at (Škoda/SEAT/CUPRA).
* P1-4  — the Škoda-official merge overlay never regresses the odometer.
* P1-5  — total_charged_energy_kwh clamped monotonic (Energy-Dashboard spike).
* P1-6  — tyre-pressure warning: telemetry-absent status never lights a fake red.
* P1-7  — SEAT/CUPRA trip-statistics sensors are allowed to spawn.
* Commit I — the Škoda-official parser reads the ~20 fields it used to drop plus the
  aux-heating / active-ventilation blocks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock


# ── P0-2a — parking_city redaction ──────────────────────────────────────────

def test_parking_city_is_redacted():
    from custom_components.vag_connect.diagnostics import _REDACT_KEYS
    # parking_address was redacted but its sibling cleartext city was not.
    assert "parking_city" in _REDACT_KEYS
    assert "parking_address" in _REDACT_KEYS


# ── P1-2 — position TTL accepts a datetime stamp ────────────────────────────

class TestPositionAgeDatetime:
    def test_datetime_stamp_yields_a_real_age(self):
        from custom_components.vag_connect.cariad.vehicle_cache import (
            POSITION_MAX_AGE_S,
            position_age_seconds,
        )
        now = datetime.now(tz=timezone.utc)
        # Škoda/SEAT/CUPRA set last_seen_at as a datetime object — previously
        # _parse_iso rejected it and the age came back None (TTL disabled).
        stale = position_age_seconds({"last_seen_at": now - timedelta(hours=30)})
        assert stale is not None
        assert stale > POSITION_MAX_AGE_S
        fresh = position_age_seconds({"last_seen_at": now - timedelta(hours=1)})
        assert fresh is not None
        assert fresh < POSITION_MAX_AGE_S

    def test_iso_string_stamp_still_works(self):
        from custom_components.vag_connect.cariad.vehicle_cache import (
            position_age_seconds,
        )
        iso = (datetime.now(tz=timezone.utc) - timedelta(hours=2)).isoformat()
        age = position_age_seconds({"last_seen_at": iso})
        assert age is not None and age > 3600


# ── P1-4 — official merge never regresses the odometer ──────────────────────

class TestOfficialMergeOdometerGuard:
    def _coord_with_official(self, official_odo):
        import custom_components.vag_connect.coordinator as coord_mod
        from custom_components.vag_connect.cariad.models import VehicleData
        coord = coord_mod.VagConnectCoordinator.__new__(coord_mod.VagConnectCoordinator)
        official = VehicleData(vin="VINX")
        official.odometer_km = official_odo
        client = MagicMock()
        client.official_live_read = AsyncMock(return_value=official)
        coord._cariad_client = client
        return coord

    def test_staler_official_odometer_does_not_regress(self):
        import asyncio
        coord = self._coord_with_official(45000)  # staler / lower
        enriched = {"odometer_km": 45010, "field_sources": {}}  # fresher / higher
        asyncio.run(coord._merge_official_live("VINX", enriched))
        assert enriched["odometer_km"] == 45010  # kept, not jumped backwards

    def test_official_fills_odometer_gap(self):
        import asyncio
        coord = self._coord_with_official(45000)
        enriched = {"field_sources": {}}  # primary had no odometer
        asyncio.run(coord._merge_official_live("VINX", enriched))
        assert enriched["odometer_km"] == 45000  # gap-filled


# ── P1-5 — charged-energy totalizer clamped monotonic ───────────────────────

class TestChargedEnergyMonotonic:
    def test_field_is_monotonic(self):
        from custom_components.vag_connect.cariad.vehicle_cache import (
            MONOTONIC_INCREASING_FIELDS,
        )
        assert "total_charged_energy_kwh" in MONOTONIC_INCREASING_FIELDS

    def test_reconcile_clamps_a_window_eviction_drop(self):
        from custom_components.vag_connect.cariad.vehicle_cache import reconcile
        prev = {"total_charged_energy_kwh": 500.0}
        fresh = {"total_charged_energy_kwh": 480.0}  # old session left the window
        out, _disc = reconcile(prev, fresh)
        assert out["total_charged_energy_kwh"] == 500.0  # no fake meter reset

    def test_reconcile_allows_a_real_increase(self):
        from custom_components.vag_connect.cariad.vehicle_cache import reconcile
        prev = {"total_charged_energy_kwh": 500.0}
        fresh = {"total_charged_energy_kwh": 520.0}
        out, _disc = reconcile(prev, fresh)
        assert out["total_charged_energy_kwh"] == 520.0


# ── P1-6 — tyre-pressure warning polarity ───────────────────────────────────

def _tyre_warning(status: str):
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    client._tokens = None
    client._spin = ""
    raw = {"tyrePressure": {"tyrePressureStatus": {"value": {"overallStatus": status}}}}
    return client._parse_status("VINX", raw, parking={}).tire_pressure_warning


class TestTyrePressurePolarity:
    def test_absent_telemetry_never_lights_red(self):
        # the bug: any non-allowlisted token → True → fake red on a fault-free car.
        for status in ("unavailable", "unknown", "notSupported", "invalid", "na"):
            assert _tyre_warning(status) is not True, status

    def test_ok_states_are_false(self):
        assert _tyre_warning("ok") is False
        assert _tyre_warning("normal") is False

    def test_real_fault_is_true(self):
        assert _tyre_warning("warning") is True
        assert _tyre_warning("alert") is True


# ── P1-7 — SEAT/CUPRA trip statistics ───────────────────────────────────────

def test_trip_stats_brands_includes_seat_cupra():
    from custom_components.vag_connect.sensor import _TRIP_STATS_BRANDS
    assert {"seat", "cupra"} <= _TRIP_STATS_BRANDS
    # regression guard: the brands that already had it stay.
    assert {"audi", "volkswagen", "skoda"} <= _TRIP_STATS_BRANDS


# ── Commit I — Škoda-official parser expansion ──────────────────────────────

def _official(v: dict):
    from custom_components.vag_connect.cariad.api.skoda_official import (
        SkodaOfficialClient,
    )
    return SkodaOfficialClient._parse_vehicle("VINX", v)


class TestSkodaOfficialExpandedParse:
    def test_aux_heating_and_active_ventilation(self):
        d = _official({
            "auxiliaryHeating": {"state": "HEATING", "durationInSeconds": 1200},
            "activeVentilation": {"state": "VENTILATION", "durationInSeconds": 900},
        })
        assert d.auxiliary_heating_status == "HEATING"
        assert d.aux_heating_active is True
        assert d.active_ventilation_state == "VENTILATION"
        assert d.active_ventilation_remaining_time_min == 15

    def test_charging_extras(self):
        d = _official({"charging": {
            "isVehicleInSavedLocation": True,
            "status": {
                "chargingRateInKilometersPerHour": 22.0,
                "chargeType": "AC",
                "remainingTimeToFullyChargedInMinutes": 30,
            },
            "settings": {
                "chargingCareMode": "ACTIVATED",
                "autoUnlockPlugWhenCharged": "PERMANENT",
                "availableChargeModes": ["MANUAL", "TIMER"],
            },
        }})
        assert d.vehicle_at_saved_location is True
        assert d.charging_rate_kmh == 22.0
        assert d.charging_type == "AC"
        assert d.charge_complete_eta is not None
        assert d.battery_care_enabled is True
        assert d.auto_unlock_when_charged is True
        assert d.available_charge_modes == ["MANUAL", "TIMER"]

    def test_status_climate_and_fuel_extras(self):
        d = _official({
            "renderUrl": "https://img.example/car.png",
            "status": {
                "overall": {"lights": "ON"},
                "detail": {"sunroof": "OPEN", "bonnet": "CLOSED"},
            },
            "airConditioning": {
                "estimatedReachOfTargetTemperatureAt": "2026-09-03T08:00:00Z",
                "airConditioningWithoutExternalPower": True,
                "airConditioningAtUnlock": False,
                "windowHeating": {"enabled": True},
            },
            "parkingPosition": {"formattedAddress": "Bahnhofstrasse 1"},
            "fuelStatus": {
                "adBlueRange": 4200,
                "secondaryEngineRange": {
                    "engineType": "GASOLINE",
                    "currentFuelLevelInPercent": 55,
                    "remainingRangeInKm": 480,
                },
            },
        })
        assert d.render_url == "https://img.example/car.png"
        assert d.lights_on is True
        assert d.sunroof_open is True
        assert d.hood_open is False
        assert d.climate_ready_at == "2026-09-03T08:00:00Z"
        assert d.air_conditioning_without_external_power is True
        assert d.climate_at_unlock is False
        assert d.window_heating_enabled is True
        assert d.parking_address == "Bahnhofstrasse 1"
        assert d.adblue_range_km == 4200
        assert d.secondary_engine_type == "GASOLINE"
        assert d.secondary_engine_fuel_level_pct == 55
        assert d.secondary_engine_range_km == 480

    def test_unsupported_sunroof_stays_none(self):
        # a car without a sunroof reports UNSUPPORTED — must not spawn a phantom
        # "closed" reading (unlike the universal trunk).
        d = _official({"status": {"detail": {"sunroof": "UNSUPPORTED"}}})
        assert d.sunroof_open is None
