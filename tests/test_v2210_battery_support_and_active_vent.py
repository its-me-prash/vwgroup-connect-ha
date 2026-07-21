# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.21.0 — map the MEB/PPE 12V ``batterySupport`` state and the
``activeVentilationStatus`` container spelling that a wave of Scout issues
surfaced (#832 et al.; #845/#856/#859). Both were interim-silenced/too-shallow;
now mapped so they stop flooding the Vehicle Data Scout AND surface real data.
"""

from __future__ import annotations

from pathlib import Path


def _vw_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client


def test_battery_support_state_mapped() -> None:
    client = _vw_client()
    raw = {
        "batterySupport": {
            "batterySupportStatus": {"value": {"batterySupport": "enabled"}},
        },
    }
    data = client._parse_status("VINX", raw, parking={})
    assert data.battery_support_state == "enabled"


def test_battery_support_state_charging_nested_variant() -> None:
    client = _vw_client()
    raw = {
        "charging": {
            "batterySupport": {
                "batterySupportStatus": {"value": {"batterySupport": "disabled"}},
            },
        },
    }
    data = client._parse_status("VINX", raw, parking={})
    assert data.battery_support_state == "disabled"


def test_battery_support_state_absent_is_none() -> None:
    client = _vw_client()
    data = client._parse_status("VINX", {}, parking={})
    assert data.battery_support_state is None


def test_active_ventilation_status_container_variant() -> None:
    # The activeVentilationStatus.value.{climatisationState,remainingClimatisationTime_min}
    # spelling (#845/#856/#859) now feeds the existing active-ventilation fields.
    client = _vw_client()
    raw = {
        "climatisation": {
            "activeVentilationStatus": {
                "value": {
                    "climatisationState": "ventilation",
                    "remainingClimatisationTime_min": 8,
                },
            },
        },
    }
    data = client._parse_status("VINX", raw, parking={})
    assert data.active_ventilation_state == "ventilation"
    assert data.active_ventilation_remaining_time_min == 8


def test_battery_support_sensor_registered_and_phantom_protected() -> None:
    from custom_components.vag_connect.sensor import (
        _DATA_PRESENT_REQUIRED,
        SENSOR_DESCRIPTIONS,
    )
    keys = {d.key for d in SENSOR_DESCRIPTIONS}
    assert "battery_support_state" in keys
    # Must be phantom-protected so it never spawns on non-MEB cars.
    assert "battery_support_state" in _DATA_PRESENT_REQUIRED


def test_battery_support_translation_in_all_locales() -> None:
    trans = Path("custom_components/vag_connect/translations")
    for f in trans.glob("*.json"):
        assert '"battery_support_state"' in f.read_text(encoding="utf-8"), f.name
