# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.11.1 — Issue #96 fixes + 3B-Part-3 Optimistic UI.

Two main areas:

A) **#96 Golf 7 GTE / Passat GTE fuel range parsing** — when the
   ``fuelStatus.rangeStatus`` block returns ``{"error": ...}`` instead
   of ``{"value": ...}``, drivetrain detection must still come from
   ``measurements.fuelLevelStatus.value.{primaryEngineType,
   secondaryEngineType, carType}`` so ``has_combustion`` flips True
   and the ``fuel_level`` / ``combustion_range_km`` entities get
   created.

   Three concrete shapes covered:
   - GTE 2015 with fuelStatus + measurements both populated
   - Passat GTE with fuelStatus.rangeStatus.error + measurements
     fallback (verbatim from evcc-io/evcc#19045)
   - carType="hybrid" with no engine-detail blocks at all

B) **Optimistic UI** (myskoda PR #832 pattern) — toggling lock /
   climate / charging / window_heating flips the local state
   immediately so the HA card feels responsive. Failed commands
   revert the optimistic state.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# #96 — Golf 7 GTE / Passat GTE drivetrain + fuel parsing
# ─────────────────────────────────────────────────────────────────────────────


def _vw_eu():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client


class TestGolfGTEFuelRange:
    def test_gte_with_full_engine_blocks(self):
        """Golf 7 GTE on firmware that DOES populate fuelStatus —
        verifies the v1.10.0 path still works as a regression check."""
        client = _vw_eu()
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "electric",
                            "remainingRange_km": 45,
                            "currentSOC_pct": 60,
                        },
                        "secondaryEngine": {
                            "type": "gasoline",
                            "remainingRange_km": 520,
                            "currentFuelLevel_pct": 80,
                        },
                        "totalRange_km": 565,
                    }
                }
            },
            "measurements": {
                "fuelLevelStatus": {
                    "value": {"primaryEngineType": "electric", "carType": "hybrid"},
                },
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.has_battery is True
        assert d.has_combustion is True
        assert d.electric_range_km == 45
        assert d.combustion_range_km == 520
        assert d.total_range_km == 565

    def test_passat_gte_error_payload_only_measurements(self):
        """v1.11.1 (#96 root cause) — Passat GTE returns Bad-Gateway
        error inside fuelStatus.rangeStatus, but measurements still has
        the data. Verbatim shape from evcc-io/evcc#19045."""
        client = _vw_eu()
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "error": {
                        "message": "Bad Gateway",
                        "code": 4007,
                        "retry": True,
                    }
                }
            },
            "measurements": {
                "rangeStatus": {
                    "value": {"gasolineRange": 200, "totalRange_km": 200},
                },
                "fuelLevelStatus": {
                    "value": {
                        "currentFuelLevel_pct": 31,
                        "primaryEngineType": "gasoline",
                        "secondaryEngineType": "electric",
                        "carType": "hybrid",
                    },
                },
            },
        }
        d = client._parse_status("V", raw, parking={})
        # Drivetrain comes from measurements engine types
        assert d.has_combustion is True
        assert d.has_battery is True
        # Fuel level from the documented measurements path
        assert d.fuel_level == 31
        # Combustion range from the dedicated fallback (gasolineRange)
        assert d.combustion_range_km == 200
        # Total range now also has measurements fallback (v1.11.1 Track C)
        assert d.total_range_km == 200

    def test_carType_hybrid_alone_sets_both_drivetrains(self):
        """v1.11.1 (#96 Track A) — pure ``carType="hybrid"`` (no engine
        detail blocks) means both battery+combustion. Pre-1.11.1 the
        substring match missed this string."""
        client = _vw_eu()
        raw = {
            "measurements": {
                "fuelLevelStatus": {"value": {"carType": "hybrid"}},
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.has_battery is True
        assert d.has_combustion is True
        assert d.is_hybrid is True

    def test_fuel_level_fallback_from_engine_block(self):
        """v1.11.1 (#96 Track D) — when measurements.fuelLevelStatus.value
        omits currentFuelLevel_pct, fall back to whichever engine block
        is combustion."""
        client = _vw_eu()
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "gasoline",
                            "remainingRange_km": 760,
                            "currentFuelLevel_pct": 100,
                        },
                    }
                }
            },
            # No measurements.fuelLevelStatus.value.currentFuelLevel_pct
            "measurements": {
                "fuelLevelStatus": {
                    "value": {"primaryEngineType": "gasoline", "carType": "gasoline"},
                },
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.fuel_level == 100  # from engine block fallback
        assert d.combustion_range_km == 760

    def test_pure_gasoline_carType(self):
        """ICE-only vehicle: carType="gasoline", no fuelStatus."""
        client = _vw_eu()
        raw = {
            "measurements": {
                "rangeStatus": {"value": {"gasolineRange": 760, "totalRange_km": 760}},
                "fuelLevelStatus": {
                    "value": {
                        "currentFuelLevel_pct": 100,
                        "primaryEngineType": "gasoline",
                        "carType": "gasoline",
                    },
                },
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.has_battery is False
        assert d.has_combustion is True
        assert d.fuel_level == 100
        assert d.combustion_range_km == 760
        assert d.total_range_km == 760

    def test_pure_ev_unchanged(self):
        """Regression: pure EV must NOT get has_combustion=True from
        measurements path."""
        client = _vw_eu()
        raw = {
            "charging": {
                "batteryStatus": {"value": {"cruisingRangeElectric_km": 380}},
            },
            "measurements": {
                "fuelLevelStatus": {
                    "value": {"primaryEngineType": "electric", "carType": "electric"},
                },
            },
        }
        d = client._parse_status("V", raw, parking={})
        assert d.has_battery is True
        assert d.has_combustion is False
        assert d.combustion_range_km is None  # phantom protection still works


# ─────────────────────────────────────────────────────────────────────────────
# 3B-Part-3 Optimistic UI
# ─────────────────────────────────────────────────────────────────────────────


def _make_coord_with_vehicle():
    """Build a coordinator stub with one vehicle and mocked client."""
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    import threading

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "audi", "spin": "1234"}
    coord.entry.options = {}
    coord._vehicles_lock = threading.Lock()
    coord.vehicles = {
        "VINX": {
            "doors_locked": False,
            "climatisation_state": "OFF",
            "climatisation_active": False,
            "charging_state": "NOT_CHARGING",
            "is_charging": False,
            "window_heating_front": False,
            "window_heating_back": False,
        }
    }
    coord._cariad_client = MagicMock()
    coord._cariad_client.command_lock = AsyncMock()
    coord._cariad_client.command_unlock = AsyncMock()
    coord._cariad_client.command_start_climate = AsyncMock()
    coord._cariad_client.command_stop_climate = AsyncMock()
    coord._cariad_client.command_start_charging = AsyncMock()
    coord._cariad_client.command_stop_charging = AsyncMock()
    coord._cariad_client.command_start_window_heating = AsyncMock()
    coord._cariad_client.command_stop_window_heating = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    coord.async_set_updated_data = MagicMock()
    coord.record_command_success = MagicMock()
    coord.record_command_failure = MagicMock()
    return coord


class TestOptimisticLock:
    def test_lock_flips_doors_locked_immediately(self):
        coord = _make_coord_with_vehicle()
        asyncio.run(coord.async_lock("VINX"))
        # State flipped before async_request_refresh would have polled
        assert coord.vehicles["VINX"]["doors_locked"] is True
        # async_set_updated_data was called so HA UI knows
        assert coord.async_set_updated_data.called

    def test_unlock_flips_doors_locked_to_false(self):
        coord = _make_coord_with_vehicle()
        coord.vehicles["VINX"]["doors_locked"] = True
        coord.entry.options = {"spin": "1234"}
        asyncio.run(coord.async_unlock("VINX"))
        assert coord.vehicles["VINX"]["doors_locked"] is False

    def test_lock_failure_reverts_optimistic_state(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        coord = _make_coord_with_vehicle()
        coord._cariad_client.command_lock = AsyncMock(
            side_effect=APIError(500, "/x", "Server Error")
        )
        # Before: doors_locked=False
        assert coord.vehicles["VINX"]["doors_locked"] is False
        with pytest.raises(APIError):
            asyncio.run(coord.async_lock("VINX"))
        # Reverted after failure
        assert coord.vehicles["VINX"]["doors_locked"] is False


class TestOptimisticClimate:
    def test_start_climate_sets_active_immediately(self):
        coord = _make_coord_with_vehicle()
        asyncio.run(
            coord.async_start_climatisation("VINX")
        )
        assert coord.vehicles["VINX"]["climatisation_active"] is True
        assert coord.vehicles["VINX"]["climatisation_state"] == "VENTILATION"

    def test_stop_climate_sets_off_immediately(self):
        coord = _make_coord_with_vehicle()
        coord.vehicles["VINX"]["climatisation_active"] = True
        coord.vehicles["VINX"]["climatisation_state"] = "HEATING"
        asyncio.run(
            coord.async_stop_climatisation("VINX")
        )
        assert coord.vehicles["VINX"]["climatisation_active"] is False
        assert coord.vehicles["VINX"]["climatisation_state"] == "OFF"


class TestOptimisticCharging:
    def test_start_charging_flips_is_charging(self):
        coord = _make_coord_with_vehicle()
        asyncio.run(
            coord.async_start_charging("VINX")
        )
        assert coord.vehicles["VINX"]["is_charging"] is True
        assert coord.vehicles["VINX"]["charging_state"] == "CHARGING"

    def test_stop_charging_reverts_on_failure(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        coord = _make_coord_with_vehicle()
        coord.vehicles["VINX"]["is_charging"] = True
        coord.vehicles["VINX"]["charging_state"] = "CHARGING"
        coord._cariad_client.command_stop_charging = AsyncMock(
            side_effect=APIError(403, "/x", "not_entitled"),
        )
        with pytest.raises(APIError):
            asyncio.run(
                coord.async_stop_charging("VINX")
            )
        # Reverted
        assert coord.vehicles["VINX"]["is_charging"] is True
        assert coord.vehicles["VINX"]["charging_state"] == "CHARGING"


class TestOptimisticWindowHeating:
    def test_start_window_heating_flips_both(self):
        coord = _make_coord_with_vehicle()
        asyncio.run(
            coord.async_start_window_heating("VINX")
        )
        assert coord.vehicles["VINX"]["window_heating_front"] is True
        assert coord.vehicles["VINX"]["window_heating_back"] is True


class TestOptimisticHelpers:
    """Direct unit tests for the helper methods themselves."""

    def test_optimistic_set_returns_previous_snapshot(self):
        coord = _make_coord_with_vehicle()
        prev = coord._optimistic_set("VINX", {"doors_locked": True})
        assert prev == {"doors_locked": False}
        assert coord.vehicles["VINX"]["doors_locked"] is True

    def test_optimistic_revert_restores_previous(self):
        coord = _make_coord_with_vehicle()
        coord._optimistic_set("VINX", {"doors_locked": True, "is_charging": True})
        coord._optimistic_revert(
            "VINX",
            {"doors_locked": False, "is_charging": False},
        )
        assert coord.vehicles["VINX"]["doors_locked"] is False
        assert coord.vehicles["VINX"]["is_charging"] is False

    def test_optimistic_set_unknown_vin_returns_empty(self):
        """Defensive: if VIN isn't tracked yet, helper returns empty
        snapshot rather than crashing."""
        coord = _make_coord_with_vehicle()
        prev = coord._optimistic_set("UNKNOWN_VIN", {"doors_locked": True})
        assert prev == {}

    def test_optimistic_set_pushes_update_to_ha(self):
        coord = _make_coord_with_vehicle()
        coord._optimistic_set("VINX", {"doors_locked": True})
        # async_set_updated_data was called so HA notifies entity listeners
        assert coord.async_set_updated_data.called
