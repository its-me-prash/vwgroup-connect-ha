# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.3 — Sprint A: easter-egg + scout closures + config-flow UX fix.

This single test-file pins the four user-facing changes that ship
together in v2.2.3 PATCH:

1. **Easter-egg `show_vag` service** (community tribute — Jordan Waeles'
   Pandas-style joke + the HA UK / HA Ideas FB-thread renaming
   discussion). Source-level checks: service is registered and
   un-registered alongside its peers; services.yaml + strings.json
   declare the new entry; persistent_notification helper is imported;
   the no-vehicles-configured branch falls back to a placeholder line.

2. **Scout #268 (VW EU arvcer)** — `charging.chargingStatus.requests`
   is now parsed into ``d.charging_status_pending`` (mirror of the
   existing ``charging_settings_pending`` from v1.27.2 #181) AND
   registered in EXPECTED_KEYS so the Scout stops firing. Audi inherits
   via the brand-vererbung at the bottom of ``_unexpected_keys.py``.

3. **Scout #263 (Audi DnnsJp74)** — re-verifies that
   ``charging.chargingSettings.error`` envelope is silenced (we
   shipped that in v2.0.x already; DnnsJp74 was on an older version).
   This test pins the silencer so we don't regress.

4. **#270 (roberttco VW NA)** — config-flow now preserves the user's
   brand selection (and other field values) when authentication fails
   and the form re-renders. Previously ``_credentials_schema()`` was
   called with no arguments → all fields reset → user was surprised by
   their brand pick disappearing.

All tests source-level (no HA runtime needed) so they run cleanly
under the existing CI workflow without ``homeassistant`` installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_INIT_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "__init__.py"
_SERVICES_YAML = _REPO_ROOT / "custom_components" / "vag_connect" / "services.yaml"
_STRINGS_JSON = _REPO_ROOT / "custom_components" / "vag_connect" / "strings.json"
_VW_EU_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "api" / "vw_eu.py"
_MODELS_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "models.py"
_SENSOR_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "sensor.py"
_UNEXPECTED_KEYS_PY = (
    _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "_unexpected_keys.py"
)
_CONFIG_FLOW_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "config_flow.py"


# ──────────────────────────────────────────────────────────────────────
# 1. Easter-egg ``show_vag`` service
# ──────────────────────────────────────────────────────────────────────


class TestEasterEggShowVag:
    """Source-level pins for the show_vag community easter-egg service."""

    def test_handler_defined(self) -> None:
        """The ``_handle_show_vag`` handler function exists in __init__.py."""
        src = _INIT_PY.read_text(encoding="utf-8")
        assert "async def _handle_show_vag" in src, (
            "Easter-egg handler ``_handle_show_vag`` missing from __init__.py"
        )

    def test_registered_in_services_tuple(self) -> None:
        """Service-registration tuple-list contains the ``show_vag`` entry."""
        src = _INIT_PY.read_text(encoding="utf-8")
        assert '"show_vag"' in src, "show_vag not registered in services tuple"
        # Must be paired with the handler we defined above.
        assert "_handle_show_vag" in src

    def test_unregistered_on_unload(self) -> None:
        """async_unload_entry must clean up show_vag like every other service."""
        src = _INIT_PY.read_text(encoding="utf-8")
        # Find the unload-services tuple-list and assert show_vag is in it.
        # The list is built in async_unload_entry.
        assert src.count('"show_vag"') >= 2, (
            "show_vag must appear in BOTH the register-tuple AND the unload-cleanup-tuple"
        )

    def test_uses_persistent_notification(self) -> None:
        """Easter-egg uses persistent_notification helper for visibility."""
        src = _INIT_PY.read_text(encoding="utf-8")
        assert "persistent_notification" in src
        assert "async_create" in src

    def test_no_vehicles_placeholder(self) -> None:
        """Always-works contract — empty config still renders a line."""
        src = _INIT_PY.read_text(encoding="utf-8")
        assert "(no vehicles configured yet)" in src, (
            "Easter-egg must show placeholder when zero vehicles configured "
            "(spec: always-works contract — never error on a community feature)"
        )

    def test_log_line_present(self) -> None:
        """Telemetry: we log when the easter-egg is triggered."""
        src = _INIT_PY.read_text(encoding="utf-8")
        assert "community easter egg triggered" in src

    def test_credits_mention_jordan_waeles(self) -> None:
        """Spec mandates Jordan Waeles credit (the show_vag joke author)."""
        src = _INIT_PY.read_text(encoding="utf-8")
        assert "Jordan Waeles" in src

    def test_credits_mention_other_community_members(self) -> None:
        """Spec mandates credits for the renaming-discussion authors."""
        src = _INIT_PY.read_text(encoding="utf-8")
        for name in ("Si Gregory", "Ben Johnson", "Evets David", "Stuart McBride"):
            assert name in src, f"Missing community credit: {name}"

    def test_services_yaml_entry(self) -> None:
        """services.yaml declares the show_vag entry with name + description."""
        src = _SERVICES_YAML.read_text(encoding="utf-8")
        assert "show_vag:" in src
        # Bilingual name with egg emoji per spec.
        assert "🥚" in src

    def test_no_fields_schema(self) -> None:
        """show_vag is parameter-less (vol.Schema({}) — empty dict)."""
        src = _INIT_PY.read_text(encoding="utf-8")
        # Pattern: ("show_vag", _handle_show_vag, vol.Schema({}))
        assert '"show_vag",' in src
        # Look for ``vol.Schema({})`` near show_vag registration.
        idx = src.find('"show_vag",')
        # The schema should appear within the next ~120 chars (same tuple line).
        assert "vol.Schema({})" in src[idx : idx + 200]


# ──────────────────────────────────────────────────────────────────────
# 2. Scout #268 — charging.chargingStatus.requests parser + silencer
# ──────────────────────────────────────────────────────────────────────


class TestScout268ChargingStatusRequests:
    """#268 (VW EU arvcer 2026-05-21): parse + silence chargingStatus.requests."""

    def test_path_in_expected_keys(self) -> None:
        """The dotted path is registered in EXPECTED_KEYS so Scout stops firing."""
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"charging.chargingStatus.requests"' in src, (
            "Scout #268 silencer-add missing — path must be registered in "
            "EXPECTED_KEYS for the CARIAD-BFF selectivestatus endpoint"
        )

    def test_parser_in_vw_eu(self) -> None:
        """vw_eu.py reads the field via the same ``v()`` walker pattern."""
        src = _VW_EU_PY.read_text(encoding="utf-8")
        assert 'd.charging_status_pending = len(' in src
        assert '"chargingStatus", "requests"' in src

    def test_dataclass_field_declared(self) -> None:
        """models.py declares the new ``charging_status_pending`` field."""
        src = _MODELS_PY.read_text(encoding="utf-8")
        assert "charging_status_pending: int | None" in src

    def test_sensor_entity_registered(self) -> None:
        """sensor.py wires the new field to a diagnostic sensor entity."""
        src = _SENSOR_PY.read_text(encoding="utf-8")
        assert 'key="charging_status_pending"' in src
        assert 'data_key="charging_status_pending"' in src
        # Mirror of the charging_settings_pending sibling — disabled by
        # default (diagnostic, opt-in for power users).
        assert "entity_registry_enabled_default=False" in src

    def test_strings_json_translation(self) -> None:
        """strings.json declares the entity-name translation."""
        src = _STRINGS_JSON.read_text(encoding="utf-8")
        assert '"charging_status_pending"' in src

    def test_audi_inherits_via_brand_alias(self) -> None:
        """Audi inherits the silencer-add automatically via brand-vererbung."""
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        # The single-line ``EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]``
        # at the bottom of the module makes the inheritance unconditional.
        assert 'EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]' in src


# ──────────────────────────────────────────────────────────────────────
# 3. Scout #263 — chargingSettings.error envelope regression-pin
# ──────────────────────────────────────────────────────────────────────


class TestScout263ChargingSettingsError:
    """#263 (Audi DnnsJp74 2026-05-19): chargingSettings.error envelope.

    Was already silenced in v2.0.x (defensive-envelope handling per
    #185/#190/#191 pattern). This test pins it so any future refactor
    that drops the silencer-entries causes CI to fail loudly.
    """

    def test_chargingSettings_error_silenced(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"charging.chargingSettings.error"' in src
        assert '"charging.chargingSettings.error.*"' in src

    def test_chargingStatus_error_silenced(self) -> None:
        """Sibling envelope on chargingStatus side — also must stay silenced."""
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"charging.chargingStatus.error"' in src
        assert '"charging.chargingStatus.error.*"' in src


# ──────────────────────────────────────────────────────────────────────
# 4. #270 — config-flow brand preservation on auth error
# ──────────────────────────────────────────────────────────────────────


class TestScout272ClimatisationStatusRequests:
    """#272 (arvcer VW EU 2026-05-23) — third *_pending sibling.

    Same shape as #268 chargingStatus.requests but on the climatisation
    side. Counts queued start/stop_climatisation commands at the
    gateway. No condition filter (electric AND combustion vehicles
    support remote-climate).
    """

    def test_path_in_expected_keys(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"climatisation.climatisationStatus.requests"' in src

    def test_parser_in_vw_eu(self) -> None:
        src = _VW_EU_PY.read_text(encoding="utf-8")
        assert 'd.climatisation_status_pending = len(' in src
        assert '"climatisationStatus", "requests"' in src

    def test_dataclass_field_declared(self) -> None:
        src = _MODELS_PY.read_text(encoding="utf-8")
        assert "climatisation_status_pending: int | None" in src

    def test_sensor_entity_registered(self) -> None:
        src = _SENSOR_PY.read_text(encoding="utf-8")
        assert 'key="climatisation_status_pending"' in src
        assert 'data_key="climatisation_status_pending"' in src
        assert "entity_registry_enabled_default=False" in src

    def test_strings_json_translation(self) -> None:
        src = _STRINGS_JSON.read_text(encoding="utf-8")
        assert '"climatisation_status_pending"' in src


class TestScout273ReadinessErrorEnvelope:
    """#273 (gudden VW EU 2026-05-23) — readiness.readinessStatus.error.

    Defensive backend-error envelope, same shape as the other ``*.error``
    siblings already silenced (#185/#190/#191). Parser ignores it
    cleanly — only silencer-add needed.
    """

    def test_error_envelope_silenced(self) -> None:
        src = _UNEXPECTED_KEYS_PY.read_text(encoding="utf-8")
        assert '"readiness.readinessStatus.error"' in src
        assert '"readiness.readinessStatus.error.*"' in src


class TestIssue270BrandPreservedOnError:
    """#270 (roberttco VW NA 2026-05-21): brand reset after login error."""

    def test_credentials_schema_invoked_with_suggested(self) -> None:
        """Re-rendering the user form must pass user_input back as defaults.

        Previously ``_credentials_schema()`` was called with NO args after
        an error, resetting brand/username/spin/scan_interval/force_access
        to their defaults. The fix threads ``user_input or {}`` back via
        ``suggested = user_input or {}`` and forwards the values.
        """
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # The fix introduces a ``suggested = user_input or {}`` line.
        assert "suggested = user_input or {}" in src, (
            "#270 fix missing — config_flow must capture user_input before "
            "re-rendering the form so brand/username/spin/etc. are preserved"
        )

    def test_credentials_schema_forwards_brand(self) -> None:
        """The schema-rebuild forwards brand from suggested."""
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # Brand must be the first arg passed to _credentials_schema in the
        # re-render path (see the ``suggested.get(CONF_BRAND, "")`` call).
        assert "brand=suggested.get(CONF_BRAND" in src

    def test_credentials_schema_forwards_username(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert "username=suggested.get(CONF_USERNAME" in src

    def test_password_not_preserved(self) -> None:
        """Security: passwords must NEVER be echoed back to the schema."""
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # Find the suggested-block area and assert password is NOT in it.
        idx = src.find("suggested = user_input or {}")
        assert idx > 0
        # Within ~600 chars of the suggested-block, password must not be
        # forwarded as a default value.
        block = src[idx : idx + 600]
        assert "password=suggested" not in block, (
            "HA convention forbids echoing passwords back to the client "
            "even via schema-default — must require re-entry"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
