# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v2.15.10 — Skoda AC max-charging-current select.

Grounded in the RE contract:
  * write  — POST /api/v1/charging/{vin}/set-charging-current
             body {"maxChargingCurrent": "MAXIMUM"|"REDUCED"}
             (VAG_GROUP_ECOSYSTEM.md:260 + mysmob command block)
  * enum   — settings.maxChargingCurrent = "MAXIMUM"|"REDUCED"
             (skoda.py get_charging_profiles read shape)

Three groups:
  A) coordinator._parse_charging_profiles — new top-level
     ``max_charging_current`` derived from the active profile.
  B) SkodaClient.command_update_charging_settings — URL + body + the
     target_soc → set-charge-limit forwarding.
  C) VagSkodaChargeCurrentSelect — current_option normalisation +
     async_select_option dispatch.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# A) Parser — top-level max_charging_current from the active profile
# ─────────────────────────────────────────────────────────────────────────────
class TestParserTopLevelMaxCurrent:
    def _parse(self, resp):
        from custom_components.vag_connect.coordinator import _parse_charging_profiles
        return _parse_charging_profiles(resp)

    def test_active_profile_matched_by_name(self):
        resp = {
            "chargingProfiles": [
                {"id": 1, "name": "Home",
                 "settings": {"maxChargingCurrent": "REDUCED"}},
                {"id": 2, "name": "Work",
                 "settings": {"maxChargingCurrent": "MAXIMUM"}},
            ],
            "currentVehiclePositionProfile": {"id": 2, "name": "Work"},
        }
        out = self._parse(resp)
        # active profile is "Work" → MAXIMUM
        assert out["max_charging_current"] == "MAXIMUM"

    def test_single_profile_fallback(self):
        resp = {
            "chargingProfiles": [
                {"id": 1, "name": "Home",
                 "settings": {"maxChargingCurrent": "REDUCED"}},
            ],
            # no currentVehiclePositionProfile → single-profile fallback
        }
        out = self._parse(resp)
        assert out["max_charging_current"] == "REDUCED"

    def test_ambiguous_multi_profile_unset(self):
        # No active profile match AND more than one profile → leave unset.
        resp = {
            "chargingProfiles": [
                {"id": 1, "name": "Home",
                 "settings": {"maxChargingCurrent": "REDUCED"}},
                {"id": 2, "name": "Work",
                 "settings": {"maxChargingCurrent": "MAXIMUM"}},
            ],
        }
        out = self._parse(resp)
        assert "max_charging_current" not in out

    def test_no_current_value_unset(self):
        resp = {
            "chargingProfiles": [
                {"id": 1, "name": "Home", "settings": {}},
            ],
        }
        out = self._parse(resp)
        assert "max_charging_current" not in out


# ─────────────────────────────────────────────────────────────────────────────
# B) SkodaClient setter
# ─────────────────────────────────────────────────────────────────────────────
class TestSkodaCommandUpdateChargingSettings:
    def _client(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client._post = AsyncMock(return_value={})
        client._put = AsyncMock(return_value={})
        return client

    def test_max_current_puts_grounded_url_and_body(self):
        # v2.20.1 (#866) — charging-SETTINGS routes are PUT (not POST) and the
        # write DTO field is chargingCurrent (upstream myskoda), not the
        # read-side maxChargingCurrent.
        client = self._client()
        asyncio.run(
            client.command_update_charging_settings(
                "VINX", max_charge_current="REDUCED"
            )
        )
        client._put.assert_awaited_once_with(
            "https://mysmob.api.connect.skoda-auto.cz/api/v1/charging/VINX/set-charging-current",
            json={"chargingCurrent": "REDUCED"},
        )
        client._post.assert_not_awaited()

    def test_maximum_enum_passthrough(self):
        client = self._client()
        asyncio.run(
            client.command_update_charging_settings(
                "VINX", max_charge_current="MAXIMUM"
            )
        )
        _, kwargs = client._put.await_args
        assert kwargs["json"] == {"chargingCurrent": "MAXIMUM"}

    def test_target_soc_forwarded_to_set_charge_limit(self):
        # target_soc must route through the dedicated grounded endpoint,
        # NOT a guessed combined body.
        client = self._client()
        client.command_set_target_soc = AsyncMock()
        asyncio.run(
            client.command_update_charging_settings("VINX", target_soc=70)
        )
        client.command_set_target_soc.assert_awaited_once_with("VINX", 70)
        client._post.assert_not_awaited()

    def test_no_fields_is_noop(self):
        client = self._client()
        asyncio.run(client.command_update_charging_settings("VINX"))
        client._post.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# C) Select entity
# ─────────────────────────────────────────────────────────────────────────────
class TestSkodaChargeCurrentSelect:
    def _entity(self, raw_current):
        from custom_components.vag_connect.select import VagSkodaChargeCurrentSelect
        coord = MagicMock()
        coord.async_update_charging_settings = AsyncMock()
        vehicle = {"vin": "VINX", "max_charging_current": raw_current}
        coord.data = {"VINX": vehicle}
        coord.vehicles = {"VINX": vehicle}
        e = VagSkodaChargeCurrentSelect.__new__(VagSkodaChargeCurrentSelect)
        e.coordinator = coord
        e._vin = "VINX"
        return e

    def test_options_are_canonical_keys(self):
        e = self._entity("MAXIMUM")
        assert e._attr_options == ["maximum", "reduced"]

    def test_current_option_maximum(self):
        assert self._entity("MAXIMUM").current_option == "maximum"

    def test_current_option_reduced_casefold(self):
        # tolerate either casing from the read plane
        assert self._entity("reduced").current_option == "reduced"

    def test_current_option_unknown_is_none(self):
        assert self._entity("WEIRD").current_option is None
        assert self._entity(None).current_option is None

    def test_select_maximum_dispatches_api_enum(self):
        e = self._entity("REDUCED")
        asyncio.run(e.async_select_option("maximum"))
        e.coordinator.async_update_charging_settings.assert_awaited_once_with(
            "VINX", max_charge_current="MAXIMUM"
        )

    def test_select_reduced_dispatches_api_enum(self):
        e = self._entity("MAXIMUM")
        asyncio.run(e.async_select_option("reduced"))
        e.coordinator.async_update_charging_settings.assert_awaited_once_with(
            "VINX", max_charge_current="REDUCED"
        )

    def test_select_unknown_option_noop(self):
        e = self._entity("MAXIMUM")
        asyncio.run(e.async_select_option("bogus"))
        e.coordinator.async_update_charging_settings.assert_not_awaited()
