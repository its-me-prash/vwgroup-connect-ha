# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.23.3 — remaining sweep fixes (triaged + adversarially verified).

- vw_na garage enumeration: robust recursive VIN walk (#503/#659, vrouleau CA)
  finds a vehicle dict under any nesting, replacing the rigid data.data.vehicles
  path that returned empty for per-region CA shapes.
- select.py gains the read-only guard (it sends a charge-mode command).
- Six duplicate diagnostic sensors demoted to disabled-by-default (kept, not
  deleted): charge_max_ac_setting/ampere, hv_battery_min/max_temperature_c,
  battery_care_mode_active, energy_flow_active.
- Fixed Audi/VW render viewpoints wired to a translation_key (were the hardcoded
  German "Seitenprofil groß" leaking into non-German HA).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.binary_sensor import BINARY_DESCRIPTIONS
from custom_components.vag_connect.image import _RENDER_TKEYS
from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS


# ── vw_na robust recursive garage walk ───────────────────────────────────────

def _vwna_client():
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient
    c = VWNAClient.__new__(VWNAClient)
    c._base = "https://x"
    c._vin_to_uuid = {}
    c._vin_to_nickname = {}
    c._vin_to_model = {}
    return c


def test_vwna_finds_vin_under_deep_nesting() -> None:
    # vrouleau's CA account: vehicles are NOT at data.data.vehicles — the old
    # rigid path returned [] and raised "no vehicles". A vin-bearing dict nested
    # anywhere must now be found.
    c = _vwna_client()
    c._get = AsyncMock(return_value={  # type: ignore[method-assign]
        "data": {"garage": {"enrolledVehicles": [
            {"vehicle": {"vin": "WVWZZZ7AZRE000123", "vehicleId": "uuid-1",
                         "vehicleNickName": "Nick", "modelName": "ID.4"}},
        ]}}
    })
    vins = asyncio.run(c.get_vehicles())
    assert vins == ["WVWZZZ7AZRE000123"]
    assert c._vin_to_uuid["WVWZZZ7AZRE000123"] == "uuid-1"
    assert c._vin_to_nickname["WVWZZZ7AZRE000123"] == "Nick"
    assert c._vin_to_model["WVWZZZ7AZRE000123"] == "ID.4"


def test_vwna_still_handles_old_flat_shape() -> None:
    c = _vwna_client()
    c._get = AsyncMock(return_value={  # type: ignore[method-assign]
        "data": {"vehicles": [{"vin": "WVWZZZ7AZRE000999", "uuid": "u9"}]}
    })
    assert asyncio.run(c.get_vehicles()) == ["WVWZZZ7AZRE000999"]


def test_vwna_empty_garage_returns_empty() -> None:
    c = _vwna_client()
    c._get = AsyncMock(return_value={"data": {}})  # type: ignore[method-assign]
    assert asyncio.run(c.get_vehicles()) == []


def test_vwna_ignores_non_17char_vin() -> None:
    c = _vwna_client()
    c._get = AsyncMock(return_value={  # type: ignore[method-assign]
        "data": {"placeholder": {"vin": "SHORT"}}
    })
    assert asyncio.run(c.get_vehicles()) == []


# ── select.py read-only guard ────────────────────────────────────────────────

def test_select_setup_skipped_when_read_only() -> None:
    from custom_components.vag_connect.select import async_setup_entry
    coord = MagicMock()
    coord.is_read_only = MagicMock(return_value=True)
    entry = MagicMock()
    entry.runtime_data = coord
    added: list = []
    asyncio.run(async_setup_entry(MagicMock(), entry, added.extend))
    assert added == []  # charge-mode select sends a command → skipped


# ── dedup demotes (kept, disabled-by-default) ────────────────────────────────

def test_duplicate_sensors_disabled_by_default() -> None:
    demoted = {
        "charge_max_ac_setting", "charge_max_ac_ampere",
        "hv_battery_min_temperature_c", "hv_battery_max_temperature_c",
    }
    by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
    for k in demoted:
        assert k in by_key, f"{k} was deleted (should be demoted, not removed)"
        assert by_key[k].entity_registry_enabled_default is False, k


def test_duplicate_binary_sensors_disabled_by_default() -> None:
    by_key = {d.key: d for d in BINARY_DESCRIPTIONS}
    for k in ("battery_care_mode_active", "energy_flow_active"):
        assert k in by_key, f"{k} was deleted"
        assert by_key[k].entity_registry_enabled_default is False, k


# ── image render viewpoints wired to translation_key ─────────────────────────

def test_render_catalog_keys_have_translation_keys() -> None:
    # the 7 fixed Audi/VW GraphQL viewpoints are the ones that leaked German.
    assert _RENDER_TKEYS == {
        "render_side_lg", "render_angle_lg", "render_medium",
        "render_side_sm", "render_small", "render_icon", "render_angle_hd",
    }
