# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.16.2 (#671 audi Q6 Scout) — climatisationMode readback mapping.

tsvyatkov's Scout report surfaced
``climatisation.climatisationSettings.value.climatisationMode`` on an
Audi Q6. It shares the selectivestatus climatisationSettings.value.*
namespace with the already-mapped zone flags but had no READ sensor
(only the command-body param existed). v2.16.2 maps it to the
diagnostic ``climate_mode`` sensor, data-present gated.
"""
from __future__ import annotations

from unittest.mock import MagicMock


def _client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    from custom_components.vag_connect.cariad.models import TokenSet
    client = VWEUClient(MagicMock(), "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client


def _raw(mode) -> dict:
    return {
        "climatisation": {
            "climatisationSettings": {"value": {"climatisationMode": mode}},
        },
    }


class TestClimateModeRead:
    def test_mode_maps_to_climate_mode(self):
        d = _client()._parse_status("VINX", _raw("comfort"), {})
        assert d.climate_mode == "comfort"

    def test_other_enum_value_preserved_raw(self):
        # We surface the raw enum verbatim — no shortening/normalisation.
        d = _client()._parse_status("VINX", _raw("economy"), {})
        assert d.climate_mode == "economy"

    def test_absent_stays_none(self):
        d = _client()._parse_status("VINX", {"climatisation": {}}, {})
        assert d.climate_mode is None

    def test_empty_string_stays_none(self):
        # Guarded by ``isinstance(cmode, str) and cmode`` → "" is not stored.
        d = _client()._parse_status("VINX", _raw(""), {})
        assert d.climate_mode is None

    def test_non_string_stays_none(self):
        # Defensive: a non-string upstream value must not be stored.
        d = _client()._parse_status("VINX", _raw(123), {})
        assert d.climate_mode is None


class TestClimateModeSensorWiring:
    def test_sensor_registered_and_data_present_gated(self):
        from custom_components.vag_connect import sensor as sensor_mod

        keys = {desc.key for desc in sensor_mod.SENSOR_DESCRIPTIONS}
        assert "climate_mode" in keys
        # Data-present gated so cars that omit the field get no phantom.
        assert "climate_mode" in sensor_mod._DATA_PRESENT_REQUIRED

    def test_sensor_is_diagnostic_disabled_by_default(self):
        from homeassistant.helpers.entity import EntityCategory

        from custom_components.vag_connect import sensor as sensor_mod

        desc = next(d for d in sensor_mod.SENSOR_DESCRIPTIONS if d.key == "climate_mode")
        assert desc.entity_category == EntityCategory.DIAGNOSTIC
        assert desc.entity_registry_enabled_default is False
