# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Tests for v1.14.0 — Audi Feature Pack Bundle.

Four feature groups:

A) #24 Trip Statistics — `_parse_trip_statistics` pure function +
   `VWEUClient.get_trip_statistics` URL/params + coordinator
   `refresh_trip_statistics` brand-restriction + 1h cache.
B) #28 Audi ICE Engine Start — two-step S-PIN flow + endpoint URLs +
   request body shapes + S-PIN-required guard + engine stop endpoint.
C) #29 PPC Climate Body conditional — `command_start_climate(ppe_mode=True)`
   uses the PPE body shape (no targetTemperature, climatisationMode mandatory).
D) Capability-Map Audi-only Engine Start — Audi has command_engine_start,
   VW EU does not.

Plus E) #116 Scout-Pfade — registered EXPECTED_KEYS for skoda
``primaryEngineRange.*`` + ``predictiveMaintenance.setting.*`` wildcard.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) #24 — Trip Statistics
# ─────────────────────────────────────────────────────────────────────────────


class TestParseTripStatistics:
    """Pure function: shape-tolerant parser + sort + ×10 division."""

    def _short(self, *trips):
        return {"tripDataList": {"tripData": list(trips)}}

    def test_parse_empty_response_returns_empty_dict(self):
        from custom_components.vag_connect.coordinator import _parse_trip_statistics
        out = _parse_trip_statistics({}, {})
        assert out == {"_shortterm_count": 0, "_longterm_count": 0}

    def test_parse_short_term_picks_highest_overall_mileage(self):
        from custom_components.vag_connect.coordinator import _parse_trip_statistics
        short = self._short(
            {"overallMileage": 100, "mileage": 5, "averageFuelConsumption": 80,
             "averageElectricEngineConsumption": 0, "traveltime": 12,
             "averageSpeed": 30, "timestamp": "2026-04-29T08:00:00Z"},
            {"overallMileage": 200, "mileage": 12, "averageFuelConsumption": 65,
             "averageElectricEngineConsumption": 0, "traveltime": 25,
             "averageSpeed": 50, "timestamp": "2026-04-30T17:00:00Z"},
        )
        out = _parse_trip_statistics(short, {})
        # Newest = overallMileage 200 trip
        assert out["last_trip_distance_km"] == 12.0
        assert out["last_trip_avg_fuel_consumption_l_100km"] == 6.5
        assert out["last_trip_avg_electric_consumption_kwh_100km"] is None
        assert out["last_trip_duration_min"] == 25
        assert out["last_trip_avg_speed_kmh"] == 50.0
        assert out["last_trip_timestamp"] == "2026-04-30T17:00:00Z"
        # recent_trips sorted same way
        assert out["recent_trips"][0]["distance_km"] == 12

    def test_consumption_division_by_ten(self):
        """Backend returns averageFuelConsumption × 10 — divider must apply."""
        from custom_components.vag_connect.coordinator import _parse_trip_statistics
        short = self._short(
            {"overallMileage": 1, "mileage": 10,
             "averageFuelConsumption": 78,
             "averageElectricEngineConsumption": 145,
             "traveltime": 15, "averageSpeed": 40},
        )
        out = _parse_trip_statistics(short, {})
        assert out["last_trip_avg_fuel_consumption_l_100km"] == 7.8
        assert out["last_trip_avg_electric_consumption_kwh_100km"] == 14.5

    def test_long_term_aggregates_into_lifetime_fields(self):
        from custom_components.vag_connect.coordinator import _parse_trip_statistics
        long = self._short({
            "overallMileage": 12345, "averageFuelConsumption": 70,
            "averageElectricEngineConsumption": 0,
        })
        out = _parse_trip_statistics({}, long)
        assert out["lifetime_distance_km"] == 12345.0
        assert out["lifetime_avg_fuel_consumption_l_100km"] == 7.0

    def test_recent_trips_capped_at_five(self):
        from custom_components.vag_connect.coordinator import _parse_trip_statistics
        trips = [
            {"overallMileage": i, "mileage": 1, "averageFuelConsumption": 50}
            for i in range(20)
        ]
        out = _parse_trip_statistics(self._short(*trips), {})
        assert len(out["recent_trips"]) == 5

    def test_garbage_response_is_safe(self):
        from custom_components.vag_connect.coordinator import _parse_trip_statistics
        # not a dict
        assert _parse_trip_statistics("oops", None) == {
            "_shortterm_count": 0, "_longterm_count": 0
        }
        # missing nested wrapper
        assert _parse_trip_statistics({"unrelated": True}, {}) == {
            "_shortterm_count": 0, "_longterm_count": 0
        }
        # tripData not a list
        assert _parse_trip_statistics(
            {"tripDataList": {"tripData": "broken"}}, {}
        ) == {"_shortterm_count": 0, "_longterm_count": 0}


class TestGetTripStatisticsURL:
    """VWEUClient.get_trip_statistics hits the right URL with type param."""

    def test_url_and_query_param(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

        client = VWEUClient.__new__(VWEUClient)
        client._get = AsyncMock(return_value={"tripDataList": {"tripData": []}})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_trip_statistics("VINX", "longTerm")
        )
        client._get.assert_awaited_once_with(
            "https://emea.bff.cariad.digital/vehicle/v1/vehicles/VINX/tripstatistics",
            params={"type": "longTerm"},
        )
        assert result == {"tripDataList": {"tripData": []}}


class TestRefreshTripStatisticsBrandRestriction:
    """Coordinator.refresh_trip_statistics is no-op for non-CARIAD brands."""

    def _coord(self, brand="audi"):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": brand}
        coord._vehicles_lock = threading.Lock()
        coord.vehicles = {"VINX": {"_dummy": True}}
        coord._cariad_client = MagicMock()
        coord._cariad_client.get_trip_statistics = AsyncMock(
            return_value={"tripDataList": {"tripData": []}}
        )
        coord.command_capability_supported = MagicMock(return_value=None)
        return coord

    def test_skoda_brand_skips_fetch(self):
        coord = self._coord(brand="skoda")
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_trip_statistics("VINX")
        )
        coord._cariad_client.get_trip_statistics.assert_not_called()

    def test_audi_brand_calls_both_endpoints(self):
        coord = self._coord(brand="audi")
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_trip_statistics("VINX")
        )
        # Two calls: shortTerm + longTerm
        assert coord._cariad_client.get_trip_statistics.await_count == 2

    def test_capability_false_skips(self):
        coord = self._coord(brand="audi")
        coord.command_capability_supported = MagicMock(return_value=False)
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_trip_statistics("VINX")
        )
        coord._cariad_client.get_trip_statistics.assert_not_called()

    def test_one_hour_cache_skips_within_window(self):
        coord = self._coord(brand="audi")
        coord._trip_stats_fetched_at = {
            "VINX": datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        }
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_trip_statistics("VINX")
        )
        coord._cariad_client.get_trip_statistics.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# B) #28 — Audi ICE Engine Start
# ─────────────────────────────────────────────────────────────────────────────


class TestAudiEngineStart:
    """AudiClient.command_engine_start two-step S-PIN flow."""

    def _client(self, spin="9999"):
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        client = AudiClient.__new__(AudiClient)
        client._spin = spin
        client._request = AsyncMock(return_value={"userPromptProof": "TOKEN_ABC"})
        client._post = AsyncMock(return_value={"data": {"requestID": "r1"}})
        return client

    def test_engine_start_two_step_flow(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(
            client.command_engine_start("vinx")
        )
        # Step 1: PUT userpromptproof with S-PIN
        client._request.assert_awaited_once_with(
            "PUT",
            "https://emea.bff.cariad.digital/vehicle/v1/engine/VINX/userpromptproof",
            json={"spin": "9999"},
        )
        # Step 2: POST start with proof token
        client._post.assert_awaited_once_with(
            "https://emea.bff.cariad.digital/vehicle/v1/engine/VINX/start",
            json={"securedActivationData": "TOKEN_ABC", "spin": "9999"},
        )

    def test_engine_start_uppercases_vin(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(
            client.command_engine_start("wvwzzz1jzcw000123")
        )
        url = client._request.await_args.args[1]
        assert "WVWZZZ1JZCW000123" in url

    def test_engine_start_no_spin_raises(self):
        from custom_components.vag_connect.cariad.exceptions import SpinError

        client = self._client(spin="")
        with pytest.raises(SpinError):
            asyncio.get_event_loop().run_until_complete(
                client.command_engine_start("vinx")
            )

    def test_engine_start_missing_proof_in_response_raises(self):
        from custom_components.vag_connect.cariad.exceptions import SpinError

        client = self._client()
        client._request = AsyncMock(return_value={})  # no userPromptProof
        with pytest.raises(SpinError):
            asyncio.get_event_loop().run_until_complete(
                client.command_engine_start("vinx")
            )

    def test_engine_stop_no_body_no_spin(self):
        client = self._client(spin="")  # stop ignores S-PIN
        client._post = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(client.command_engine_stop("vinx"))
        client._post.assert_awaited_once_with(
            "https://emea.bff.cariad.digital/vehicle/v1/engine/VINX/stop"
        )


# ─────────────────────────────────────────────────────────────────────────────
# C) #29 — PPC Climate Body conditional
# ─────────────────────────────────────────────────────────────────────────────


class TestPpcClimateBody:
    """command_start_climate uses different body shape based on ppe_mode."""

    def _client(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        client = VWEUClient.__new__(VWEUClient)
        client._post_command_with_fallback_paths = AsyncMock(return_value=None)
        return client

    def test_legacy_body_includes_target_temperature(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(
            client.command_start_climate("VINX", ppe_mode=False)
        )
        kwargs = client._post_command_with_fallback_paths.await_args.kwargs
        fallback = kwargs["fallback_payload"]
        assert "targetTemperature" in fallback
        assert "targetTemperatureUnit" in fallback
        assert "climatisationMode" not in fallback

    def test_ppe_body_omits_target_temperature_and_sets_mode(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(
            client.command_start_climate("VINX", ppe_mode=True)
        )
        kwargs = client._post_command_with_fallback_paths.await_args.kwargs
        fallback = kwargs["fallback_payload"]
        # PPE: targetTemperature MUST be omitted
        assert "targetTemperature" not in fallback
        assert "targetTemperatureUnit" not in fallback
        # PPE: climatisationMode MANDATORY
        assert fallback["climatisationMode"] == "comfort"
        # Other fields preserved
        assert fallback["windowHeatingEnabled"] is True

    def test_default_is_legacy_body(self):
        """Backwards-compat: existing callers without ppe_mode get legacy."""
        client = self._client()
        asyncio.get_event_loop().run_until_complete(
            client.command_start_climate("VINX")
        )
        fallback = client._post_command_with_fallback_paths.await_args.kwargs[
            "fallback_payload"
        ]
        assert "targetTemperature" in fallback


# ─────────────────────────────────────────────────────────────────────────────
# D) Capability-Map — Audi-only Engine Start
# ─────────────────────────────────────────────────────────────────────────────


class TestCapabilityMapEngineStart:
    """v1.14.0 (#28): audi gets engine_start cap-id; VW EU does NOT
    (the inheritance dict was COPIED before the audi-only patch)."""

    def test_audi_has_engine_start(self):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for("audi", "command_engine_start") == "engineRemoteStart"
        assert cap_id_for("audi", "command_engine_stop") == "engineRemoteStart"

    def test_volkswagen_does_not_have_engine_start(self):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for("volkswagen", "command_engine_start") is None
        assert cap_id_for("volkswagen", "command_engine_stop") is None

    def test_audi_inheritance_was_copied_not_aliased(self):
        """Adding an audi-only cap-id must NOT leak into VW EU's table."""
        from custom_components.vag_connect.cariad._capabilities import CAPABILITY_MAP
        assert "command_engine_start" not in CAPABILITY_MAP["volkswagen"]
        assert "command_engine_start" in CAPABILITY_MAP["audi"]

    def test_trip_stats_cap_id_present_on_vw_and_audi(self):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for("volkswagen", "command_trip_stats") == "tripStatistics"
        assert cap_id_for("audi", "command_trip_stats") == "tripStatistics"
        # Other brands don't have trip stats
        assert cap_id_for("skoda", "command_trip_stats") is None
        assert cap_id_for("cupra", "command_trip_stats") is None


# ─────────────────────────────────────────────────────────────────────────────
# E) #116 Scout-Pfade — Skoda EXPECTED_KEYS extensions
# ─────────────────────────────────────────────────────────────────────────────


class TestScoutPathsSkoda:
    """v1.14.0 (#116, MavericklCS): four primaryEngineRange.* fields +
    predictiveMaintenance.setting wildcard registered for skoda."""

    def test_primary_engine_range_children_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import EXPECTED_KEYS
        skoda_dr = EXPECTED_KEYS["skoda"]["driving-range"]
        assert "primaryEngineRange.engineType" in skoda_dr
        assert "primaryEngineRange.currentSoCInPercent" in skoda_dr
        assert "primaryEngineRange.currentFuelLevelInPercent" in skoda_dr
        assert "primaryEngineRange.remainingRangeInKm" in skoda_dr

    def test_predictive_maintenance_setting_wildcard_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import EXPECTED_KEYS
        skoda_m = EXPECTED_KEYS["skoda"]["maintenance"]
        assert "predictiveMaintenance.setting" in skoda_m
        assert "predictiveMaintenance.setting.*" in skoda_m


# ─────────────────────────────────────────────────────────────────────────────
# F) Coordinator command-class registry — engine grouping
# ─────────────────────────────────────────────────────────────────────────────


class TestEngineCommandClass:
    """Engine start/stop share the same lock class so they serialize."""

    def test_engine_start_and_stop_share_class(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        cmd_class = VagConnectCoordinator._COMMAND_CLASS
        assert cmd_class["command_engine_start"] == "engine"
        assert cmd_class["command_engine_stop"] == "engine"
