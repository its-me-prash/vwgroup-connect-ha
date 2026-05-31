# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Tests for v1.16.0 — Cross-Brand UX + Skoda Charging Profiles.

Three feature groups:

A) #26 Klima-Timer HA `time` platform — `VagDepartureTimerTime`
   reads ``departure_timer_X_time`` as `datetime.time` and writes
   back via the existing `set_departure_timer` service path.
B) #25/#31 Skoda Charging Profiles — `_parse_charging_profiles` pure
   parser + `SkodaClient.get_charging_profiles` URL + coordinator
   `refresh_charging_profiles` brand-restriction + 1h cache +
   capability gate.
C) Cross-Brand OTA Probe documentation in place — research notes
   file referenced + plan documented.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock



# ─────────────────────────────────────────────────────────────────────────────
# A) #26 — HA time platform for departure-timer editing
# ─────────────────────────────────────────────────────────────────────────────


class TestDepartureTimerTimeEntity:
    """VagDepartureTimerTime native_value parses + async_set_value dispatches."""

    def _entity(self, raw_time):
        from custom_components.vag_connect.time import VagDepartureTimerTime
        coord = MagicMock()
        coord.is_read_only = MagicMock(return_value=False)
        coord.async_set_departure_timer = AsyncMock()
        # entity_base.VagConnectEntity._vehicle reads from
        # ``self.coordinator.data`` (the DataUpdateCoordinator
        # convention) — NOT ``self.coordinator.vehicles``. Set both
        # so the test fixture works regardless of which attribute the
        # entity layer ends up reading.
        vehicle = {
            "vin": "VINX",
            "model": "Test Vehicle",
            "departure_timer_1_time": raw_time,
        }
        coord.data = {"VINX": vehicle}
        coord.vehicles = {"VINX": vehicle}
        e = VagDepartureTimerTime.__new__(VagDepartureTimerTime)
        # Bypass the full HA entity __init__ — just set the bits we test.
        e.coordinator = coord
        e._vin = "VINX"
        e._timer_id = 1
        return e

    def test_native_value_parses_hh_mm(self):
        e = self._entity("07:30")
        assert e.native_value == time(7, 30)

    def test_native_value_parses_hh_mm_ss(self):
        e = self._entity("18:45:00")
        assert e.native_value == time(18, 45, 0)

    def test_native_value_parses_iso_datetime(self):
        e = self._entity("2026-05-02T07:30:00Z")
        assert e.native_value == time(7, 30)

    def test_native_value_returns_none_for_garbage(self):
        e = self._entity("not-a-time")
        assert e.native_value is None

    def test_native_value_returns_none_when_field_missing(self):
        e = self._entity(None)
        assert e.native_value is None

    def test_async_set_value_dispatches_to_coordinator(self):
        e = self._entity("07:30")
        asyncio.get_event_loop().run_until_complete(
            e.async_set_value(time(8, 15))
        )
        e.coordinator.async_set_departure_timer.assert_awaited_once_with(
            "VINX", 1, enabled=True, departure_time="08:15"
        )

    def test_setting_time_also_enables_timer(self):
        """UX: editing the time implies the user wants this timer on."""
        e = self._entity("07:30")
        asyncio.get_event_loop().run_until_complete(
            e.async_set_value(time(6, 0))
        )
        kwargs = e.coordinator.async_set_departure_timer.await_args.kwargs
        assert kwargs["enabled"] is True


# ─────────────────────────────────────────────────────────────────────────────
# B) #25/#31 — Skoda Charging Profiles
# ─────────────────────────────────────────────────────────────────────────────


class TestParseChargingProfiles:
    """Pure parser: profiles list flattening + currentVehiclePositionProfile."""

    def test_empty_response_returns_empty(self):
        from custom_components.vag_connect.coordinator import _parse_charging_profiles
        assert _parse_charging_profiles({}) == {}
        assert _parse_charging_profiles(None) == {}

    def test_profiles_flattened_with_settings(self):
        from custom_components.vag_connect.coordinator import _parse_charging_profiles
        resp = {
            "chargingProfiles": [{
                "id": 1,
                "name": "Home",
                "settings": {
                    "maxChargingCurrent": "MAXIMUM",
                    "minBatteryStateOfCharge": {
                        "minimumBatteryStateOfChargeInPercent": 20
                    },
                    "targetStateOfChargeInPercent": 80,
                    "autoUnlockPlugWhenCharged": "PERMANENT",
                },
                "preferredChargingTimes": [{"id": 1, "enabled": True}],
                "timers": [{"id": 1, "enabled": False}, {"id": 2, "enabled": True}],
                "location": {"latitude": 47.39, "longitude": 8.21},
            }],
        }
        out = _parse_charging_profiles(resp)
        assert out["charging_profiles_count"] == 1
        p = out["charging_profiles"][0]
        assert p["id"] == 1
        assert p["name"] == "Home"
        assert p["target_soc_pct"] == 80
        assert p["max_charging_current"] == "MAXIMUM"
        assert p["auto_unlock_plug"] == "PERMANENT"
        assert p["min_battery_soc_pct"] == 20
        assert p["preferred_times_count"] == 1
        assert p["timers_count"] == 2
        # GPS rounded to 2 decimals for attribute storage
        assert p["location_lat"] == 47.39
        assert p["location_lon"] == 8.21

    def test_current_vehicle_position_profile_extracted(self):
        from custom_components.vag_connect.coordinator import _parse_charging_profiles
        resp = {
            "chargingProfiles": [],
            "currentVehiclePositionProfile": {
                "id": 1,
                "name": "Home",
                "targetStateOfChargeInPercent": 80,
                "nextChargingTime": "22:00",
            },
        }
        out = _parse_charging_profiles(resp)
        assert out["active_charging_profile_name"] == "Home"
        assert out["active_charging_profile_target_soc_pct"] == 80
        assert out["next_charging_time"] == "22:00"

    def test_missing_current_profile_no_active_fields(self):
        from custom_components.vag_connect.coordinator import _parse_charging_profiles
        resp = {
            "chargingProfiles": [{"id": 1, "name": "Home", "settings": {}}],
            # No currentVehiclePositionProfile
        }
        out = _parse_charging_profiles(resp)
        assert "active_charging_profile_name" not in out
        assert "next_charging_time" not in out

    def test_garbage_profiles_skipped(self):
        from custom_components.vag_connect.coordinator import _parse_charging_profiles
        resp = {"chargingProfiles": ["not-a-dict", None, 42, {
            "id": 99, "name": "Real",
            "settings": {"targetStateOfChargeInPercent": 90},
        }]}
        out = _parse_charging_profiles(resp)
        assert out["charging_profiles_count"] == 1
        assert out["charging_profiles"][0]["id"] == 99


class TestGetChargingProfilesURL:
    """SkodaClient.get_charging_profiles hits the right URL."""

    def test_url_no_params(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(return_value={"chargingProfiles": []})
        asyncio.get_event_loop().run_until_complete(
            client.get_charging_profiles("VINX")
        )
        client._get.assert_awaited_once_with(
            "https://mysmob.api.connect.skoda-auto.cz/api/v1/charging/VINX/profiles"
        )


class TestRefreshChargingProfilesBrandRestriction:
    """Coordinator.refresh_charging_profiles is no-op for non-Skoda."""

    def _coord(self, brand="skoda"):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": brand}
        coord._vehicles_lock = threading.Lock()
        coord.vehicles = {"VINX": {"_dummy": True}}
        coord._cariad_client = MagicMock()
        coord._cariad_client.get_charging_profiles = AsyncMock(
            return_value={
                "chargingProfiles": [{
                    "id": 1, "name": "Home",
                    "settings": {"targetStateOfChargeInPercent": 80},
                }],
                "currentVehiclePositionProfile": {
                    "id": 1, "name": "Home",
                    "targetStateOfChargeInPercent": 80,
                },
            }
        )
        coord.command_capability_supported = MagicMock(return_value=None)
        return coord

    def test_audi_brand_skips(self):
        coord = self._coord(brand="audi")
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_profiles("VINX")
        )
        coord._cariad_client.get_charging_profiles.assert_not_called()

    def test_skoda_brand_calls_endpoint_and_merges(self):
        coord = self._coord(brand="skoda")
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_profiles("VINX")
        )
        coord._cariad_client.get_charging_profiles.assert_awaited_once()
        v = coord.vehicles["VINX"]
        assert v["active_charging_profile_name"] == "Home"
        assert v["charging_profiles_count"] == 1

    def test_capability_false_skips(self):
        coord = self._coord(brand="skoda")
        coord.command_capability_supported = MagicMock(return_value=False)
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_profiles("VINX")
        )
        coord._cariad_client.get_charging_profiles.assert_not_called()

    def test_one_hour_cache_skips_within_window(self):
        coord = self._coord(brand="skoda")
        coord._charging_profiles_fetched_at = {
            "VINX": datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        }
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_profiles("VINX")
        )
        coord._cariad_client.get_charging_profiles.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# C) Cross-Brand OTA Probe documentation
# ─────────────────────────────────────────────────────────────────────────────


class TestOtaProbeDocsExist:
    """v1.16.0 OTA Probe planning doc.

    The doc was retired in v2.8.0 task #44 (dead-weight cleanup). It
    had served its purpose as the scoping doc for the v1.16.x probe
    runs; the actual OTA / software-update parsing landed in v1.16.0
    and is exercised by the rest of this test module. The doc is
    preserved locally in _private/research-archive/ for history but is
    no longer tracked in the public tree.
    """

    def test_research_notes_file_present(self):
        import pytest
        pytest.skip("OTA probe doc retired in v2.8.0 dead-weight cleanup")

    def test_research_notes_lists_both_backend_probes(self):
        import pytest
        pytest.skip("OTA probe doc retired in v2.8.0 dead-weight cleanup")
