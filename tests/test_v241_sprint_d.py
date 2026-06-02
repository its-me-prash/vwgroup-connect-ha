# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.4.1 — Sprint D: bundle test-suite.

This single file pins ALL the v2.4.1 changes that ship together. The
release covers four parallel work-streams plus a methodology shift:

1. **OLA defense-in-depth** (#281 goncal SEAT Mii, #282 matthias0304 +
   smartmatic CUPRA Terramar). VW Group's OLA backend started
   enforcing app-identifying headers on 2026-05-20 — parallel
   discovery in PyCupra #89 and CarConnectivity-connector-seatcupra
   #112/PR113/v0.6.3. Four-layer architecture: centralized constants
   (``cariad/_ola_headers.py``), OptionsFlow overrides (const +
   coordinator + factory wiring), multi-version fallback chain
   (``seat_cupra.py`` _request override), and persistent-403 repair
   issue (``repairs.py`` + coordinator flag-check).

2. **VW NA garage envelope** (#285 roberttco). v2.3.0 fixed auth but
   exposed the next bug: garage response is wrapped in ``data``
   envelope per matpoulin's reference implementation, not top-level.

3. **Scout #283 + #284** parse + silence. #283 (Brinki99) is the
   4th *_pending family member on the climatisationSettings side;
   #284 (KimmoT727) is a silencer-gap for a long-parsed field.

4. **Scout Policy Compliance Audit** — 12 T1 entities promoted from
   silencer-only to parsed-and-surfaced per the new policy
   (``docs/SCOUT_POLICY.md``).

5. **Methodology shift**: SCOUT_POLICY.md documents the "always parse"
   rule going forward + the T2-T5 exemption tiers for legitimate
   non-parse cases.

Plus: weekly CI watcher (``.github/workflows/upstream-ola-watcher.yml``)
monitors CarConnectivity upstream and opens issues when our OLA
header versions drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_INIT_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "__init__.py"
_CONST_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "const.py"
_COORD_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "coordinator.py"
_FACTORY_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "api" / "factory.py"
_VW_NA_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "api" / "vw_na.py"
_VW_EU_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "api" / "vw_eu.py"
_SEAT_CUPRA_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "api" / "seat_cupra.py"
_MODELS_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "models.py"
_SENSOR_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "sensor.py"
_BINSENS_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "binary_sensor.py"
_UNEXPECTED_KEYS_PY = (
    _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "_unexpected_keys.py"
)
_OLA_HEADERS_PY = (
    _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "_ola_headers.py"
)
_REPAIRS_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "repairs.py"
_STRINGS_JSON = _REPO_ROOT / "custom_components" / "vag_connect" / "strings.json"
_SCOUT_POLICY_MD = _REPO_ROOT / "docs" / "SCOUT_POLICY.md"
# Watcher workflow removed in the upstream-name-scrub cleanup.


# ──────────────────────────────────────────────────────────────────────
# 1. OLA defense-in-depth (#281 + #282)
# ──────────────────────────────────────────────────────────────────────


class TestOLAHeadersModule:
    """Layer 1: centralized SSoT module."""

    def test_module_exists(self) -> None:
        assert _OLA_HEADERS_PY.exists(), (
            "cariad/_ola_headers.py missing — Layer 1 of OLA defense-"
            "in-depth requires the centralized constants module"
        )

    def test_seat_headers_present(self) -> None:
        src = _OLA_HEADERS_PY.read_text(encoding="utf-8")
        assert '"seat":' in src
        # CarConnectivity v0.6.3 values per upstream session config.
        assert '"app-brand": "seat"' in src
        assert '"app-version": "2.17.0"' in src

    def test_cupra_headers_present(self) -> None:
        src = _OLA_HEADERS_PY.read_text(encoding="utf-8")
        assert '"cupra":' in src
        assert '"app-brand": "cupra"' in src
        assert '"app-version": "2.15.0"' in src

    def test_common_headers_for_both_brands(self) -> None:
        """app-market + origin are universal across brands."""
        src = _OLA_HEADERS_PY.read_text(encoding="utf-8")
        # Both brand entries must include these two universal headers.
        assert src.count('"app-market": "android"') >= 2
        assert src.count('"origin": "app"') >= 2

    def test_get_ola_headers_function_signature(self) -> None:
        """Public helper must accept overrides per Layer 2 design."""
        src = _OLA_HEADERS_PY.read_text(encoding="utf-8")
        assert "def get_ola_headers(" in src
        assert "app_version_override:" in src
        assert "user_agent_override:" in src
        assert "fallback_index:" in src

    def test_get_fallback_count_helper(self) -> None:
        """Multi-version chain requires fallback count introspection."""
        src = _OLA_HEADERS_PY.read_text(encoding="utf-8")
        assert "def get_fallback_count(" in src


class TestOLAOptionsFlowConsts:
    """Layer 2: OptionsFlow override config keys."""

    def test_const_keys_defined(self) -> None:
        src = _CONST_PY.read_text(encoding="utf-8")
        assert 'CONF_OLA_APP_VERSION_OVERRIDE = "ola_app_version_override"' in src
        assert 'CONF_OLA_USER_AGENT_OVERRIDE  = "ola_user_agent_override"' in src

    def test_coordinator_reads_overrides(self) -> None:
        """Coordinator pulls the override values from entry.data."""
        src = _COORD_PY.read_text(encoding="utf-8")
        assert "CONF_OLA_APP_VERSION_OVERRIDE" in src
        assert "CONF_OLA_USER_AGENT_OVERRIDE" in src
        assert "ola_app_version_override=ola_app_v" in src
        assert "ola_user_agent_override=ola_ua" in src

    def test_factory_forwards_overrides(self) -> None:
        """Factory routes overrides only to SEAT/CUPRA clients."""
        src = _FACTORY_PY.read_text(encoding="utf-8")
        assert "ola_app_version_override:" in src
        assert "ola_user_agent_override:" in src
        # Only the seat/cupra branch should forward them.
        assert "ola_app_version_override=ola_app_version_override" in src


class TestOLARequestOverride:
    """Layer 3: SeatCupraClient._request injects headers + retry."""

    def test_request_method_overridden(self) -> None:
        src = _SEAT_CUPRA_PY.read_text(encoding="utf-8")
        assert "async def _request(" in src
        # Override forwards to super()._request after header mixin.
        assert "super()._request(" in src

    def test_imports_ola_helpers(self) -> None:
        src = _SEAT_CUPRA_PY.read_text(encoding="utf-8")
        assert "from .._ola_headers import" in src
        assert "get_ola_headers" in src
        assert "get_fallback_count" in src

    def test_init_accepts_override_kwargs(self) -> None:
        src = _SEAT_CUPRA_PY.read_text(encoding="utf-8")
        assert "ola_app_version_override:" in src
        assert "ola_user_agent_override:" in src

    def test_403_fallback_chain_logic(self) -> None:
        """On 403 against OLA, code retries with next fallback set."""
        src = _SEAT_CUPRA_PY.read_text(encoding="utf-8")
        # Must reference get_fallback_count to know when to stop iterating.
        assert "get_fallback_count(" in src
        # Must increment _attempt to walk the chain.
        assert "_attempt + 1" in src

    def test_consecutive_403_counter(self) -> None:
        src = _SEAT_CUPRA_PY.read_text(encoding="utf-8")
        assert "_ola_consecutive_403" in src
        # Must reset on successful response.
        assert "self._ola_consecutive_403 = 0" in src

    def test_repair_flag_raised(self) -> None:
        """Layer 4: public flag for coordinator to surface Repair issue."""
        src = _SEAT_CUPRA_PY.read_text(encoding="utf-8")
        assert "ola_headers_repair_needed" in src
        # Set to True only after fallback exhaustion + threshold breach.
        assert "self.ola_headers_repair_needed = True" in src


class TestOLARepairIssue:
    """Layer 4: repairs.py raises the user-actionable HA Repair issue."""

    def test_raise_helper_exists(self) -> None:
        src = _REPAIRS_PY.read_text(encoding="utf-8")
        assert "def raise_issue_ola_headers_outdated(" in src

    def test_clear_helper_exists(self) -> None:
        src = _REPAIRS_PY.read_text(encoding="utf-8")
        assert "def clear_ola_headers_issue(" in src

    def test_translation_key_in_strings(self) -> None:
        src = _STRINGS_JSON.read_text(encoding="utf-8")
        assert '"ola_headers_outdated":' in src
        # Title + description with brand + count placeholders.
        assert "{brand}" in src
        assert "{count}" in src

    def test_coordinator_polls_repair_flag(self) -> None:
        src = _COORD_PY.read_text(encoding="utf-8")
        assert "ola_headers_repair_needed" in src
        assert "raise_issue_ola_headers_outdated" in src
        assert "clear_ola_headers_issue" in src


# TestOLAUpstreamWatcher class removed alongside the workflow.


# ──────────────────────────────────────────────────────────────────────
# 2. VW NA garage envelope (#285)
# ──────────────────────────────────────────────────────────────────────


class TestVWNAGarageEnvelope:
    """#285 roberttco — payload is wrapped in ``data`` envelope per matpoulin."""

    def test_parser_walks_data_envelope(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        # Defensive walk: data.data.vehicles preferred, top-level fallback.
        assert "(data.get(\"data\") or {}).get(\"vehicles\")" in src
        assert 'or data.get("vehicles")' in src

    def test_nickname_cache_added(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "_vin_to_nickname" in src

    def test_model_cache_added(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "_vin_to_model" in src

    def test_caches_initialized(self) -> None:
        """Both caches must be initialized in __init__ to avoid AttributeError."""
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "self._vin_to_nickname: dict[str, str] = {}" in src
        assert "self._vin_to_model: dict[str, str] = {}" in src


# ──────────────────────────────────────────────────────────────────────
# 3. Scout #283 + #284 (parse + silence)
# ──────────────────────────────────────────────────────────────────────


class TestScout283ClimatisationSettingsRequests:
    """#283 Brinki99 VW EU — 4th *_pending family member."""

    def test_silencer_path_added(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"climatisation.climatisationSettings.requests"' in src

    def test_parser_present(self) -> None:
        src = _VW_EU_PY.read_text(encoding="utf-8")
        assert "clim_settings_pending = v(" in src
        assert "climatisationSettings" in src
        assert "d.climatisation_settings_pending = len(clim_settings_pending)" in src

    def test_dataclass_field(self) -> None:
        src = _MODELS_PY.read_text(encoding="utf-8")
        assert "climatisation_settings_pending: int | None" in src

    def test_sensor_entity(self) -> None:
        src = _SENSOR_PY.read_text(encoding="utf-8")
        assert 'key="climatisation_settings_pending"' in src
        assert "entity_registry_enabled_default=False" in src

    def test_strings_translation(self) -> None:
        src = _STRINGS_JSON.read_text(encoding="utf-8")
        assert '"climatisation_settings_pending"' in src


class TestScout284ChargingSettingsRequestsSilencerGap:
    """#284 KimmoT727 Audi — already parsed since v1.27.2, silencer was missing."""

    def test_silencer_path_now_present(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"charging.chargingSettings.requests"' in src

    def test_parser_still_works(self) -> None:
        """The original v1.27.2 parser must remain untouched."""
        src = _VW_EU_PY.read_text(encoding="utf-8")
        assert "d.charging_settings_pending = len(pending)" in src
        assert '"charging", "chargingSettings", "requests"' in src


# ──────────────────────────────────────────────────────────────────────
# 4. Scout Policy Compliance Audit T1 — 12 new entities
# ──────────────────────────────────────────────────────────────────────


class TestAuditT1Entities:
    """12 silenced-only paths promoted to parsed-and-surfaced."""

    @pytest.mark.parametrize(
        "field",
        [
            "battery_temp_c",
            "climate_without_external_power",
            "climate_zone_front_left",
            "climate_zone_front_right",
            "climate_remaining_time_min",
            "connection_battery_power_level",
            "connection_active",
            "daily_power_budget_warning",
            "insufficient_battery_level_warning",
            "license_plate",
            "vehicle_nickname",
            "parking_map_url_dark",
            "parking_map_url_light",
        ],
    )
    def test_dataclass_field_present(self, field: str) -> None:
        src = _MODELS_PY.read_text(encoding="utf-8")
        # Match the field declaration: either `field: type | None` form.
        assert f"{field}:" in src, f"Dataclass field {field} missing in models.py"

    @pytest.mark.parametrize(
        "field",
        [
            "battery_temp_c",
            "climate_remaining_time_min",
            "connection_battery_power_level",
            "license_plate",
            "vehicle_nickname",
            "parking_map_url_dark",
            "parking_map_url_light",
            "climatisation_settings_pending",
        ],
    )
    def test_sensor_entity_present(self, field: str) -> None:
        """T1 fields with scalar values become sensor entities."""
        src = _SENSOR_PY.read_text(encoding="utf-8")
        assert f'key="{field}"' in src

    @pytest.mark.parametrize(
        "field",
        [
            "climate_without_external_power",
            "climate_zone_front_left",
            "climate_zone_front_right",
            "connection_active",
            "daily_power_budget_warning",
            "insufficient_battery_level_warning",
        ],
    )
    def test_binary_sensor_present(self, field: str) -> None:
        """T1 boolean fields become binary_sensor entities."""
        src = _BINSENS_PY.read_text(encoding="utf-8")
        assert f'key="{field}"' in src

    def test_all_t1_strings_translated(self) -> None:
        src = _STRINGS_JSON.read_text(encoding="utf-8")
        for field in [
            "battery_temp_c", "climate_without_external_power",
            "climate_zone_front_left", "climate_zone_front_right",
            "climate_remaining_time_min", "connection_battery_power_level",
            "connection_active", "daily_power_budget_warning",
            "insufficient_battery_level_warning", "license_plate",
            "vehicle_nickname", "parking_map_url_dark", "parking_map_url_light",
        ]:
            assert f'"{field}":' in src, f"strings.json missing entry for {field}"

    def test_cariad_t1_parsers_in_vw_eu(self) -> None:
        """CARIAD-BFF T1 fields parsed in vw_eu.py (Audi inherits)."""
        src = _VW_EU_PY.read_text(encoding="utf-8")
        # Each parser must assign to d.{field}.
        for field in [
            "battery_temp_c", "climate_without_external_power",
            "climate_zone_front_left", "climate_zone_front_right",
            "climate_remaining_time_min", "connection_battery_power_level",
            "connection_active", "daily_power_budget_warning",
            "insufficient_battery_level_warning",
        ]:
            assert f"d.{field} =" in src, f"vw_eu.py missing parser for {field}"

    def test_ola_t1_parsers_in_seat_cupra(self) -> None:
        """OLA-only T1 fields parsed in seat_cupra.py."""
        src = _SEAT_CUPRA_PY.read_text(encoding="utf-8")
        for field in [
            "license_plate", "vehicle_nickname",
            "parking_map_url_dark", "parking_map_url_light",
        ]:
            assert f"d.{field} =" in src, f"seat_cupra.py missing parser for {field}"

    def test_disabled_by_default(self) -> None:
        """All T1 entities are disabled-by-default per SCOUT_POLICY.md Rule 5."""
        src_sensor = _SENSOR_PY.read_text(encoding="utf-8")
        src_binsens = _BINSENS_PY.read_text(encoding="utf-8")
        # Coarse check: every T1 entity description includes
        # entity_registry_enabled_default=False nearby. Find each key
        # and assert the False default is in the same description block.
        for field in [
            "battery_temp_c", "climate_remaining_time_min",
            "connection_battery_power_level", "license_plate",
            "vehicle_nickname", "parking_map_url_dark", "parking_map_url_light",
        ]:
            idx = src_sensor.find(f'key="{field}"')
            assert idx > 0
            # Look in the next ~500 chars (same description block).
            block = src_sensor[idx : idx + 500]
            assert "entity_registry_enabled_default=False" in block, (
                f"T1 sensor {field} not disabled-by-default"
            )


# ──────────────────────────────────────────────────────────────────────
# 5. Scout Policy + methodology
# ──────────────────────────────────────────────────────────────────────


class TestScoutPolicyDoc:
    """docs/SCOUT_POLICY.md documents the new "always parse" methodology."""

    def test_file_exists(self) -> None:
        assert _SCOUT_POLICY_MD.exists(), "docs/SCOUT_POLICY.md missing"

    def test_tldr_present(self) -> None:
        src = _SCOUT_POLICY_MD.read_text(encoding="utf-8")
        assert "Parse it" in src
        assert "Silence it" in src
        assert "Surface it" in src
        assert "Cross-brand check" in src

    def test_documents_exemption_tiers(self) -> None:
        src = _SCOUT_POLICY_MD.read_text(encoding="utf-8")
        # T1 through T5 with exemption rules.
        for tier in ("T1", "T2", "T3", "T4", "T5"):
            assert tier in src, f"SCOUT_POLICY.md missing tier {tier}"

    def test_checklist_present(self) -> None:
        src = _SCOUT_POLICY_MD.read_text(encoding="utf-8")
        # Must include the pre-merge checklist.
        assert "Before merging" in src
        assert "Parser exists" in src
        assert "Dataclass field declared" in src

    def test_documents_migration_history(self) -> None:
        src = _SCOUT_POLICY_MD.read_text(encoding="utf-8")
        assert "Migration history" in src
        assert "v2.4.1 audit" in src


class TestUnexpectedKeysHeader:
    """The silencer module header now documents the new policy."""

    def test_header_references_scout_policy(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert "docs/SCOUT_POLICY.md" in src

    def test_header_documents_tiers(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert "T2" in src and "T3" in src and "T4" in src and "T5" in src

    def test_header_mentions_audit(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert "v2.4.1 audit" in src


# ──────────────────────────────────────────────────────────────────────
# 6. JSON validity (regression-shield for the many strings.json edits)
# ──────────────────────────────────────────────────────────────────────


class TestStringsJsonParses:
    """All the new translation keys must keep strings.json valid JSON."""

    def test_strings_json_valid(self) -> None:
        data = json.loads(_STRINGS_JSON.read_text(encoding="utf-8"))
        # Sanity-check the top-level structure stays intact.
        assert "config" in data
        assert "entity" in data
        assert "issues" in data
        # All v2.4.1 new entity-name keys exist.
        sensor_entries = data["entity"].get("sensor", {})
        for key in ("battery_temp_c", "license_plate", "vehicle_nickname"):
            assert key in sensor_entries

    def test_issues_section_has_new_repair(self) -> None:
        data = json.loads(_STRINGS_JSON.read_text(encoding="utf-8"))
        assert "ola_headers_outdated" in data["issues"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
