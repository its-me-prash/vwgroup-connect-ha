# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW CARIAD-BFF full-grounding wave (4.0.0) — P0 foundation.

Pins the capabilities-first foundation grounded from We Connect 4.3.2 (androguard):
- ``read_capability_hidden`` soft gate for capability-tagged READ entities
  (hide only on an explicitly-absent capability; never on unknown/supported so a
  missing capabilities document can't remove a working sensor).
- the new VW ``CAPABILITY_MAP`` rows (command bindings + pre-registered read-only
  cap-ids), whose cap-ids are verbatim members of the app's 87-strong
  ``capabilitiesfinder/Capability`` enum.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad._capabilities import cap_id_for


def _coord(caps_for_vin=None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.vehicle_capabilities = {"VIN1": caps_for_vin} if caps_for_vin else {}
    return coord


# ── read_capability_hidden soft gate ──────────────────────────────────────────

def test_no_cache_never_hides() -> None:
    # No capabilities document → unknown → must NOT hide a read entity.
    assert _coord().read_capability_hidden("VIN1", "batteryHealthState") is False


def test_supported_cap_not_hidden() -> None:
    coord = _coord({"capabilities": [{"id": "batteryHealthState", "status": []}]})
    assert coord.read_capability_hidden("VIN1", "batteryHealthState") is False


def test_limited_cap_is_hidden() -> None:
    coord = _coord({"capabilities": [
        {"id": "batteryHealthState", "status": [{"reason": "LICENSE_REQUIRED"}]},
    ]})
    assert coord.read_capability_hidden("VIN1", "batteryHealthState") is True


def test_absent_cap_is_hidden() -> None:
    # Doc loaded but the cap isn't listed → explicit absence → hide.
    coord = _coord({"capabilities": [{"id": "somethingElse", "status": []}]})
    assert coord.read_capability_hidden("VIN1", "batteryHealthState") is True


def test_tuple_any_variant_supported_not_hidden() -> None:
    coord = _coord({"capabilities": [
        {"id": "vehicleHealthInspection", "status": []},  # one of the variants
    ]})
    cap = ("vehicleHealth", "vehicleHealthInspection", "vehicleHealthWarnings")
    assert coord.read_capability_hidden("VIN1", cap) is False


def test_tuple_all_variants_absent_is_hidden() -> None:
    coord = _coord({"capabilities": [{"id": "charging", "status": []}]})
    cap = ("vehicleHealth", "vehicleHealthInspection", "vehicleHealthWarnings")
    assert coord.read_capability_hidden("VIN1", cap) is True


def test_tuple_unknown_vin_not_hidden() -> None:
    coord = _coord({"capabilities": [{"id": "charging", "status": []}]})
    cap = ("vehicleHealth", "vehicleHealthInspection")
    assert coord.read_capability_hidden("VIN_OTHER", cap) is False


# ── CAPABILITY_MAP new VW rows (androguard-grounded cap-ids) ───────────────────

# The 87-strong capabilitiesfinder/Capability enum members we bind to.
_VW_ENUM_SUBSET = frozenset({
    "access", "activeVentilation", "batterySupport", "batteryChargingCare",
    "batteryHealthState", "parkingPosition", "warningLights", "theftWarning",
    "plugAndCharge", "chargingProfiles", "honkAndFlash", "climatisation",
    "charging", "vehicleHealth", "vehicleHealthInspection", "vehicleHealthWarnings",
    "vehicleWakeUpTrigger", "windowHeating", "departureTimers", "tripStatistics",
    "auxiliaryHeating",
})


def test_new_command_cap_bindings() -> None:
    assert cap_id_for("volkswagen", "command_battery_support_toggle") == "batterySupport"
    assert cap_id_for("volkswagen", "command_set_battery_care") == "batteryChargingCare"
    assert cap_id_for("volkswagen", "command_set_battery_care_target") == "batteryChargingCare"
    assert cap_id_for("volkswagen", "command_start_active_ventilation") == "activeVentilation"
    assert cap_id_for("volkswagen", "command_stop_active_ventilation") == "activeVentilation"
    assert cap_id_for("volkswagen", "command_unlock_trunk") == "access"


def test_readonly_pre_registrations() -> None:
    assert cap_id_for("volkswagen", "command_battery_health") == "batteryHealthState"
    assert cap_id_for("volkswagen", "command_parking_position") == "parkingPosition"
    assert cap_id_for("volkswagen", "command_warning_lights") == "warningLights"
    assert cap_id_for("volkswagen", "command_theft_warning") == "theftWarning"
    assert cap_id_for("volkswagen", "command_plug_and_charge") == "plugAndCharge"
    assert cap_id_for("volkswagen", "command_charging_profiles") == "chargingProfiles"
    assert cap_id_for("volkswagen", "command_vehicle_health") == (
        "vehicleHealth", "vehicleHealthInspection", "vehicleHealthWarnings",
    )


def test_audi_inherits_new_vw_rows() -> None:
    # Audi shares the VW EU CARIAD-BFF table (alias at module load).
    assert cap_id_for("audi", "command_battery_support_toggle") == "batterySupport"
    assert cap_id_for("audi", "command_battery_health") == "batteryHealthState"


# ── new VW two-way commands (grounded routes/bodies) ──────────────────────────

def _vw_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    c = VWEUClient.__new__(VWEUClient)
    c._tokens = None
    c._spin = ""
    c._v2_command_paths = {}
    c._mbb_command_target = MagicMock(return_value=None)  # non-MBB entry
    return c


def test_vw_active_ventilation_posts_grounded_route() -> None:
    c = _vw_client()
    c._post_command = AsyncMock(return_value=None)
    asyncio.run(c.command_start_active_ventilation("VINX"))
    c._post_command.assert_awaited_once_with("VINX", "activeventilation/start", json={})
    c._post_command.reset_mock()
    asyncio.run(c.command_stop_active_ventilation("VINX"))
    c._post_command.assert_awaited_once_with("VINX", "activeventilation/stop", json={})


def test_vw_battery_care_puts_grounded_mode_body() -> None:
    c = _vw_client()
    c._settings_put_with_fallback = AsyncMock(return_value=None)
    asyncio.run(c.command_set_battery_care("VINX", True))
    call = c._settings_put_with_fallback.await_args
    assert call.args[1] == "charging/care/settings"
    assert call.kwargs["put_body"] == {"batteryCareMode": "ACTIVATED"}
    asyncio.run(c.command_set_battery_care("VINX", False))
    assert c._settings_put_with_fallback.await_args.kwargs["put_body"] == {
        "batteryCareMode": "DEACTIVATED"
    }


def test_vw_battery_care_target_puts_grounded_body() -> None:
    c = _vw_client()
    c._settings_put_with_fallback = AsyncMock(return_value=None)
    asyncio.run(c.command_set_battery_care_target("VINX", 80))
    assert c._settings_put_with_fallback.await_args.kwargs["put_body"] == {
        "batteryCareTargetSOC_pct": 80
    }


def test_vw_active_ventilation_blocked_on_mbb() -> None:
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
    c = _vw_client()
    c._mbb_command_target = MagicMock(return_value=object())  # durable-MBB entry
    c._post_command = AsyncMock(return_value=None)
    try:
        asyncio.run(c.command_start_active_ventilation("VINX"))
        assert False, "expected VehicleCommandError on MBB"
    except VehicleCommandError:
        pass
    c._post_command.assert_not_awaited()


def test_new_cap_ids_are_grounded_enum_members() -> None:
    # The cap-ids added in the 4.0.0 wave must each be a verbatim member of the
    # androguard-grounded capabilitiesfinder/Capability enum (no typo/guess).
    added = [
        "command_battery_support_toggle", "command_set_battery_care",
        "command_set_battery_care_target",
        "command_start_active_ventilation", "command_stop_active_ventilation",
        "command_unlock_trunk", "command_battery_health",
        "command_parking_position", "command_warning_lights",
        "command_theft_warning", "command_plug_and_charge",
        "command_charging_profiles", "command_vehicle_health",
    ]
    for cmd in added:
        cap = cap_id_for("volkswagen", cmd)
        assert cap is not None, cmd
        for c in (cap if isinstance(cap, tuple) else (cap,)):
            assert c in _VW_ENUM_SUBSET, (cmd, c)
