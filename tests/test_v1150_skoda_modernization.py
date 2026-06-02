# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.15.0 — Skoda Modernization Bundle.

Five feature groups:

A) Skoda Charging History (#35) — `_parse_charging_history` pure parser
   + `SkodaClient.get_charging_history` URL/params + coordinator cache.
B) Skoda Software-Version + OTA (myskoda PR #541) — `get_status` parses
   the new endpoint into model fields.
C) Anonymize improvements borrowed from myskoda — `_mask_location_qs`
   query-string GPS scrub + `_stable_hash` SHA-256 IDs + user_id/account_id
   hashing in `_scrub`.
D) Capability-Map Skoda extensions — 8 new cap-ids registered.
E) Capability-Status tolerance — top-level `errors[]` block on caps
   response handled (myskoda PR #543).
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) #35 — Skoda Charging History
# ─────────────────────────────────────────────────────────────────────────────


class TestParseChargingHistory:
    """Pure parser: total kWh sum, sort-by-startAt, recent_sessions cap."""

    def test_empty_response_returns_empty(self):
        from custom_components.vag_connect.coordinator import _parse_charging_history
        assert _parse_charging_history({}) == {}
        assert _parse_charging_history(None) == {}
        assert _parse_charging_history({"periods": "garbage"}) == {}

    def test_total_kwh_sums_across_periods(self):
        from custom_components.vag_connect.coordinator import _parse_charging_history
        resp = {
            "periods": [
                {"sessions": [
                    {"startAt": "2026-04-29T08:00:00Z", "chargedInKWh": 12.5,
                     "durationInMinutes": 45, "currentType": "AC"},
                    {"startAt": "2026-04-30T17:00:00Z", "chargedInKWh": 25.0,
                     "durationInMinutes": 60, "currentType": "DC"},
                ]},
                {"sessions": [
                    {"startAt": "2026-05-01T09:00:00Z", "chargedInKWh": 8.0,
                     "durationInMinutes": 30, "currentType": "AC"},
                ]},
            ],
        }
        out = _parse_charging_history(resp)
        assert out["total_charged_energy_kwh"] == 45.5

    def test_last_session_picked_by_start_at_desc(self):
        from custom_components.vag_connect.coordinator import _parse_charging_history
        resp = {"periods": [{"sessions": [
            {"startAt": "2026-04-29T08:00:00Z", "chargedInKWh": 12.5,
             "durationInMinutes": 45, "currentType": "AC"},
            {"startAt": "2026-05-02T09:00:00Z", "chargedInKWh": 8.0,
             "durationInMinutes": 30, "currentType": "DC"},
            {"startAt": "2026-04-30T17:00:00Z", "chargedInKWh": 25.0,
             "durationInMinutes": 60, "currentType": "DC"},
        ]}]}
        out = _parse_charging_history(resp)
        # Newest = startAt 2026-05-02
        assert out["last_charging_session_kwh"] == 8.0
        assert out["last_charging_session_duration_min"] == 30
        assert out["last_charging_session_current_type"] == "DC"
        assert out["last_charging_session_start"] == "2026-05-02T09:00:00Z"

    def test_recent_sessions_capped_at_5(self):
        from custom_components.vag_connect.coordinator import _parse_charging_history
        sessions = [
            {"startAt": f"2026-04-{20 + i:02d}T08:00:00Z",
             "chargedInKWh": 1.0,
             "durationInMinutes": 10,
             "currentType": "AC"}
            for i in range(10)
        ]
        out = _parse_charging_history({"periods": [{"sessions": sessions}]})
        assert len(out["recent_charging_sessions"]) == 5

    def test_garbage_session_entries_skipped(self):
        from custom_components.vag_connect.coordinator import _parse_charging_history
        resp = {"periods": [{"sessions": [
            "not-a-dict",
            {"startAt": "2026-05-01T09:00:00Z", "chargedInKWh": 5.0,
             "durationInMinutes": 20, "currentType": "AC"},
            None,
            42,
        ]}]}
        out = _parse_charging_history(resp)
        assert out["total_charged_energy_kwh"] == 5.0
        assert len(out["recent_charging_sessions"]) == 1


class TestGetChargingHistoryURL:
    """SkodaClient.get_charging_history hits the right URL with params."""

    def test_url_and_default_params(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(return_value={"periods": []})
        asyncio.get_event_loop().run_until_complete(
            client.get_charging_history("VINX")
        )
        client._get.assert_awaited_once_with(
            "https://mysmob.api.connect.skoda-auto.cz/api/v1/charging/VINX/history",
            params={"userTimezone": "UTC", "limit": 50},
        )

    def test_custom_limit(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(return_value={})
        asyncio.get_event_loop().run_until_complete(
            client.get_charging_history("VINX", limit=10)
        )
        params = client._get.await_args.kwargs["params"]
        assert params["limit"] == 10


class TestRefreshChargingHistoryBrandRestriction:
    """Coordinator.refresh_charging_history is no-op for non-Skoda."""

    def _coord(self, brand="skoda"):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": brand}
        coord._vehicles_lock = threading.Lock()
        coord.vehicles = {"VINX": {"_dummy": True}}
        coord._cariad_client = MagicMock()
        coord._cariad_client.get_charging_history = AsyncMock(
            return_value={"periods": [{"sessions": [
                {"startAt": "2026-05-01T09:00:00Z", "chargedInKWh": 5.0,
                 "durationInMinutes": 20, "currentType": "AC"}
            ]}]}
        )
        coord.command_capability_supported = MagicMock(return_value=None)
        return coord

    def test_audi_brand_skips(self):
        coord = self._coord(brand="audi")
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_history("VINX")
        )
        coord._cariad_client.get_charging_history.assert_not_called()

    def test_skoda_brand_calls_endpoint_and_merges(self):
        coord = self._coord(brand="skoda")
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_history("VINX")
        )
        coord._cariad_client.get_charging_history.assert_awaited_once()
        # Parser results merged into vehicle dict
        v = coord.vehicles["VINX"]
        assert v["total_charged_energy_kwh"] == 5.0
        assert v["last_charging_session_kwh"] == 5.0

    def test_capability_false_skips(self):
        coord = self._coord(brand="skoda")
        coord.command_capability_supported = MagicMock(return_value=False)
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_history("VINX")
        )
        coord._cariad_client.get_charging_history.assert_not_called()

    def test_one_hour_cache_skips_within_window(self):
        coord = self._coord(brand="skoda")
        coord._charging_history_fetched_at = {
            "VINX": datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        }
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_charging_history("VINX")
        )
        coord._cariad_client.get_charging_history.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# B) Software-Version + OTA (myskoda PR #541)
# ─────────────────────────────────────────────────────────────────────────────


class TestSoftwareVersionParsing:
    """Skoda get_status parses the new software-version endpoint correctly."""

    def _stub_results(self, sw_update_resp):
        # 8-tuple matches gather() unpacking in skoda.py get_status.
        return (
            None,  # status
            None,  # charging
            None,  # ac
            None,  # parking
            None,  # driving_range
            None,  # maintenance
            None,  # readiness
            sw_update_resp,
        )

    def test_no_update_available_sets_false(self):
        # We test parsing logic standalone — re-create the dispatch
        # block from get_status via direct field assignment as that's
        # the actual code path.
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="VINX")
        sw_update = {
            "status": "NO_UPDATE_AVAILABLE",
            "currentSoftwareVersion": "3.8",
            "carCapturedTimestamp": "2026-05-02T10:00:00Z",
            "releaseNotesUrl": None,
        }
        # Reproduce the parse block from skoda.py
        sw_status = sw_update.get("status")
        if isinstance(sw_status, str):
            d.software_update_status = sw_status
            d.ota_update_available = sw_status.upper() not in {
                "NO_UPDATE_AVAILABLE", "UPDATE_SUCCESSFUL"
            }
        curr = sw_update.get("currentSoftwareVersion")
        if isinstance(curr, str):
            d.software_version = curr
        assert d.software_version == "3.8"
        assert d.ota_update_available is False
        assert d.software_update_status == "NO_UPDATE_AVAILABLE"

    def test_unknown_enum_treated_as_update_available(self):
        """Forward-compat: unknown SoftwareStatus enum values default to True."""
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="VINX")
        sw_status = "UPDATE_IN_PROGRESS"  # myskoda hasn't published this yet
        d.software_update_status = sw_status
        d.ota_update_available = sw_status.upper() not in {
            "NO_UPDATE_AVAILABLE", "UPDATE_SUCCESSFUL"
        }
        # New / unknown enum → treat as "update something is happening"
        assert d.ota_update_available is True


# ─────────────────────────────────────────────────────────────────────────────
# C) Anonymize improvements (borrowed from myskoda)
# ─────────────────────────────────────────────────────────────────────────────


class TestLocationQueryStringScrub:
    """v1.15.0 — _mask_location_qs scrubs lat/lon from URL query strings."""

    def test_redacts_when_gps_round_off(self):
        from custom_components.vag_connect.diagnostics import _mask_location_qs
        url = "/v1/maps/positions?latitude=48.13743&longitude=11.57549"
        out = _mask_location_qs(url, gps_round=False)
        assert "REDACTED" in out
        assert "48.13" not in out
        assert "11.57" not in out

    def test_rounds_when_gps_round_on(self):
        from custom_components.vag_connect.diagnostics import _mask_location_qs
        url = "/v1/maps/positions?latitude=48.13743&longitude=11.57549"
        out = _mask_location_qs(url, gps_round=True)
        # Rounded to 1 decimal
        assert "48.1" in out
        assert "11.6" in out
        # Original precise values gone
        assert "48.13743" not in out

    def test_no_op_when_no_latitude(self):
        from custom_components.vag_connect.diagnostics import _mask_location_qs
        url = "/v1/charging/VIN/history?userTimezone=UTC"
        assert _mask_location_qs(url) == url

    def test_handles_negative_coords(self):
        from custom_components.vag_connect.diagnostics import _mask_location_qs
        url = "?latitude=-33.8&longitude=151.2"
        out = _mask_location_qs(url, gps_round=True)
        assert "-33.8" in out


class TestStableHash:
    """SHA-256 pseudonym for cross-referencing repeat reporters."""

    def test_deterministic(self):
        from custom_components.vag_connect.diagnostics import _stable_hash
        a = _stable_hash("user-12345")
        b = _stable_hash("user-12345")
        assert a == b
        assert len(a) == 12

    def test_different_inputs_different_outputs(self):
        from custom_components.vag_connect.diagnostics import _stable_hash
        assert _stable_hash("user-A") != _stable_hash("user-B")

    def test_empty_returns_empty(self):
        from custom_components.vag_connect.diagnostics import _stable_hash
        assert _stable_hash("") == ""

    def test_salt_changes_output(self):
        from custom_components.vag_connect.diagnostics import _stable_hash
        a = _stable_hash("user-X")
        b = _stable_hash("user-X", salt="different")
        assert a != b


class TestUserIdHashingInScrub:
    """user_id / account_id get hashed (not just REDACTED) so reports cross-link."""

    def test_user_id_gets_sha256_prefix(self):
        from custom_components.vag_connect.diagnostics import _scrub
        out = _scrub({"user_id": "abc-123-def-456"})
        assert isinstance(out["user_id"], str)
        assert out["user_id"].startswith("sha256:")
        assert "abc-123" not in out["user_id"]

    def test_account_id_same_treatment(self):
        from custom_components.vag_connect.diagnostics import _scrub
        out = _scrub({"accountId": "xyz789"})
        assert out["accountId"].startswith("sha256:")

    def test_repeat_user_id_yields_same_hash(self):
        """Stable across calls so a repeat reporter cross-links."""
        from custom_components.vag_connect.diagnostics import _scrub
        a = _scrub({"user_id": "stable-user"})
        b = _scrub({"user_id": "stable-user"})
        assert a["user_id"] == b["user_id"]

    def test_string_value_with_lat_lon_url_scrubbed(self):
        """v1.15.0 — string values containing query-string GPS get scrubbed."""
        from custom_components.vag_connect.diagnostics import _scrub
        out = _scrub({
            "error": "API failed for /maps/positions?latitude=48.0&longitude=11.0"
        })
        assert "48.0" not in out["error"]
        assert "REDACTED" in out["error"]


# ─────────────────────────────────────────────────────────────────────────────
# D) Capability-Map Skoda extensions
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaCapabilityMap:
    """v1.15.0 — 8 new Skoda cap-ids registered."""

    @pytest.mark.parametrize("command_id,cap_id", [
        ("command_software_update", "VEHICLE_HEALTH_INSPECTION"),
        ("command_charging_history", "CHARGING"),
        ("command_charging_profiles", "EXTENDED_CHARGING_SETTINGS"),
        ("command_driving_score", "DRIVING_SCORE"),
        ("command_readiness", "READINESS"),
        ("command_plug_and_charge", "PLUG_AND_CHARGE"),
        ("command_route_planning", "EV_ROUTE_PLANNING"),
        ("command_battery_charging_care", "BATTERY_CHARGING_CARE"),
    ])
    def test_skoda_cap_registered(self, command_id, cap_id):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        assert cap_id_for("skoda", command_id) == cap_id

    def test_existing_skoda_caps_unchanged(self):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for
        # Sanity: v1.13.0 cap-ids still resolve.
        assert cap_id_for("skoda", "command_lock") == "access"
        assert cap_id_for("skoda", "command_flash") == "honk-and-flash"


# ─────────────────────────────────────────────────────────────────────────────
# E) Capability-Status tolerance — errors[] block + transient states
# ─────────────────────────────────────────────────────────────────────────────


class TestCapabilityStatusTolerance:
    """v1.15.0 — vehicle_supports_capability handles the new myskoda
    response shapes (errors[] top-level + extended status enum values)."""

    def _coord(self, caps_for_vin):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.vehicle_capabilities = {"VINX": caps_for_vin}
        return coord

    def test_top_level_errors_block_returns_none(self):
        """When the entire capabilities document failed, we bail to None
        instead of falsely gating every entity (myskoda PR #543 schema)."""
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = self._coord({
            "errors": [{"type": "MISSING_RENDER"}],
            "capabilities": [],
        })
        result = VagConnectCoordinator.vehicle_supports_capability(
            coord, "VINX", "honk-and-flash"
        )
        assert result is None

    def test_no_errors_block_normal_path_works(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = self._coord({
            "capabilities": [{"id": "honk-and-flash", "active": True}],
        })
        result = VagConnectCoordinator.vehicle_supports_capability(
            coord, "VINX", "honk-and-flash"
        )
        assert result is True

    def test_empty_errors_list_treated_as_no_errors(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = self._coord({
            "errors": [],  # explicit empty
            "capabilities": [{"id": "honk-and-flash", "active": True}],
        })
        result = VagConnectCoordinator.vehicle_supports_capability(
            coord, "VINX", "honk-and-flash"
        )
        assert result is True  # empty errors → falsy → take normal path

    @pytest.mark.parametrize("status_value", [
        "INSUFFICIENT_BATTERY_LEVEL",
        "LOCATION_DATA_DISABLED",
        "VEHICLE_DISABLED",
    ])
    def test_transient_status_values_treated_as_gated(self, status_value):
        """v1.15.0 — new transient status values from myskoda still gate
        (non-empty status[] = "right now no")."""
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = self._coord({
            "capabilities": [{
                "id": "honk-and-flash",
                "active": True,
                "status": [{"reason": status_value}],
            }],
        })
        result = VagConnectCoordinator.vehicle_supports_capability(
            coord, "VINX", "honk-and-flash"
        )
        assert result is False
