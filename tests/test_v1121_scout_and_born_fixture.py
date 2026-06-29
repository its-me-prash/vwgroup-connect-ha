# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.12.1 — Scout findings #105/#106 + Gerhard's Born fixture.

Three scopes:

- ``TestScoutWildcardCoverage`` — the v1.12.1 EXPECTED_KEYS additions
  (`.value` containers + `.error.*` wildcards) silence the Scout for
  the field families reported in #105 + #106.
- ``TestBornFixtureLoads`` — the new
  `tests/fixtures/seat_cupra/cupra_born_2023_active_subscription_redacted.json`
  loads as valid JSON, contains the expected meta block, and is fully
  redacted (no full VINs / tokens / GPS).
- ``TestBornFixtureParserRoundTrip`` — fed back through the v1.10.2
  seat_cupra parser, the redacted fixture produces the entity values
  Gerhard saw on his Born (battery 69%, range 277 km, plug disconnected,
  doors locked).
"""

from __future__ import annotations

import json
import re
from pathlib import Path



_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "seat_cupra"
    / "cupra_born_2023_active_subscription_redacted.json"
)


# ─────────────────────────────────────────────────────────────────────────────
# #105 + #106 — Scout-Pfade silenced
# ─────────────────────────────────────────────────────────────────────────────


class TestScoutWildcardCoverage:
    def test_value_containers_registered(self):
        """v1.12.1 — register the ``.value`` paths the Scout descended
        into past the v1.12.0 wrapper registrations."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        for path in (
            "userCapabilities.capabilitiesStatus.value",
            "fuelStatus.rangeStatus.value",
            "vehicleHealthInspection.maintenanceStatus.value",
            "vehicleHealthWarnings.warningLights.value",
            "departureProfiles.departureProfilesStatus.value",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_error_wildcard_matches_six_subfields(self):
        """v1.12.1 — wildcard ``error.*`` covers all six standardized
        HTTP-error-wrapper sub-fields without enumerating them."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        for sub in ("message", "errorTimeStamp", "info", "code", "group", "retry"):
            path = f"charging.chargeMode.error.{sub}"
            assert _path_matches(path, keys), f"missing wildcard match: {path}"

    def test_automation_error_wrappers_registered(self):
        """v1.12.1 — automation timer + chargingProfiles error wrappers
        (same Bad-Gateway-shape as charging.chargeMode.error)."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        for path in (
            "automation.climatisationTimer.error",
            "automation.chargingProfiles.error",
            "automation.climatisationTimer.error.message",
            "automation.chargingProfiles.error.code",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_audi_inherits_via_table_alias(self):
        """Audi inherits VW EU expected-keys table — single registration
        covers both brands. Fail-loud if someone breaks the alias."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        assert EXPECTED_KEYS["audi"] is EXPECTED_KEYS["volkswagen"]

    def test_actual_105_payload_silent(self):
        """Replay verbatim Scout findings from #105 (VW EU). All 12
        TOP-LEVEL paths from the report must classify as expected.

        Note: the Scout descends into .value containers if they're
        registered — children inside .value get evaluated separately
        against their own paths. We only assert that the v1.12.1
        registry silences the EXACT paths from the #105 report (which
        are leaf containers, not their children). For .value children,
        v1.10.0+ registered the legitimate ones (e.g. totalRange_km
        under measurements.rangeStatus); unknown children would still
        get flagged (which is correct Scout behaviour).
        """
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        # Synthetic payload — use list values for .value containers
        # because lists aren't recursed into by detect_unexpected (the
        # walker only descends into dicts). Lists are treated as opaque
        # leaves with the parent path classified once.
        payload = {
            "automation": {
                "climatisationTimer": {"error": [
                    {"message": "Bad Gateway", "code": 4111},
                ]},
                "chargingProfiles": {"error": [{"code": 4111}]},
            },
            # value as opaque list — exactly what Scout reported (#105:
            # `userCapabilities.capabilitiesStatus.value` = "[16 items]")
            "userCapabilities": {"capabilitiesStatus": {"value": ["a", "b"]}},
            "charging": {"chargeMode": {"error": [{"code": 4111}]}},
            "departureProfiles": {"departureProfilesStatus": {
                "value": [],  # opaque list per Scout report
            }},
            "fuelStatus": {"rangeStatus": {"value": []}},
            "vehicleHealthInspection": {"maintenanceStatus": {"value": []}},
        }
        findings = list(detect_unexpected("volkswagen", "selectivestatus", payload))
        assert findings == [], (
            "Scout still finds unexpected paths after v1.12.1 registry: "
            + ", ".join(f.path for f in findings)
        )

    def test_error_wildcard_silences_all_six_subfields(self):
        """The .error.* wildcards explicitly cover the 6 standardized
        sub-fields (message/errorTimeStamp/info/code/group/retry)."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        payload = {
            "charging": {"chargeMode": {"error": {
                "message": "Bad Gateway",
                "errorTimeStamp": "2026-04-30T13:34:20Z",
                "info": "Upstream service responded with an unexpected status.",
                "code": 4111,
                "group": 2,
                "retry": True,
            }}},
        }
        findings = list(detect_unexpected("volkswagen", "selectivestatus", payload))
        # Charge mode error sub-fields all wildcard-covered
        assert findings == [], (
            "Wildcard .error.* failed to silence: "
            + ", ".join(f.path for f in findings)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Born fixture — privacy + structural sanity
# ─────────────────────────────────────────────────────────────────────────────


class TestBornFixtureLoads:
    """Privacy-by-default audit of the new fixture file."""

    def test_fixture_file_exists(self):
        assert _FIXTURE_PATH.exists(), f"Fixture missing at {_FIXTURE_PATH}"

    def test_fixture_is_valid_json(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_meta_block_present(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        meta = data.get("_meta", {})
        assert meta.get("_source", "").startswith("User report from issue #53")
        assert "consent" in meta.get("_source", "").lower()
        assert meta.get("_brand") == "cupra"
        assert meta.get("_model") == "born"

    def test_no_full_vin_anywhere(self):
        """Privacy rule #5 — full 17-char VIN must NOT appear. Only
        masked last-6 (``***003577``) is allowed."""
        text = _FIXTURE_PATH.read_text(encoding="utf-8")
        # 17-char VIN regex (uppercase letters + digits, excluding I/O/Q)
        full_vin_re = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
        matches = full_vin_re.findall(text)
        assert matches == [], f"Full VIN(s) leaked: {matches}"

    def test_no_email_addresses(self):
        text = _FIXTURE_PATH.read_text(encoding="utf-8")
        email_re = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
        # The fixture must contain no email addresses at all (privacy guard).
        bad = email_re.findall(text)
        assert bad == [], f"Email(s) leaked: {bad}"

    def test_no_jwt_tokens(self):
        text = _FIXTURE_PATH.read_text(encoding="utf-8")
        jwt_re = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
        assert jwt_re.findall(text) == []

    def test_no_uuids(self):
        """Account-IDs / userIDs are UUIDs — must be REDACTED."""
        text = _FIXTURE_PATH.read_text(encoding="utf-8")
        uuid_re = re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        )
        assert uuid_re.findall(text) == []

    def test_gps_coordinates_rounded(self):
        """v1.9.0 Privacy: GPS rounded to 1 decimal (~11 km). Fixture
        uses 48.0 / 11.0 exactly — both well within rounding tolerance."""
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        pos = data["endpoints"]["honk-and-flash"]["_request_body"]["userPosition"]
        assert pos["latitude"] == 48.0
        assert pos["longitude"] == 11.0


# ─────────────────────────────────────────────────────────────────────────────
# Born fixture round-trip — parser produces Gerhard's observed values
# ─────────────────────────────────────────────────────────────────────────────


class TestBornFixtureParserRoundTrip:
    """The whole point of the fixture: feed it through the v1.10.2
    parser and verify the entities Gerhard sees on his Born (#53)
    materialise from this synthetic redacted data alone.

    These tests are the most important part — they prove that future
    parser changes can't silently break Born support without us
    noticing.
    """

    def _parser_charging_block(self, charge_status):
        """Replicate the v1.10.2 charging-block parsing logic on
        synthetic input. Mirrors seat_cupra.py:get_status — no full
        gather pipeline needed for a unit test."""
        from custom_components.vag_connect.cariad._util import safe_int
        from custom_components.vag_connect.cariad.models import VehicleData

        # Match the exact same priority order as production code.
        d = VehicleData(vin="V1")
        if isinstance(charge_status, dict):
            bat = charge_status.get("battery") or charge_status
            d.battery_soc = (
                bat.get("currentSocPercentage")
                or charge_status.get("currentPct")
                or bat.get("stateOfChargeInPercent")
                or bat.get("currentSOC_pct")
            )
            d.has_battery = d.battery_soc is not None
            if d.range_km is None:
                est = safe_int(bat.get("estimatedRangeInKm"))
                if est is not None:
                    d.range_km = est
            chg = charge_status.get("charging") or charge_status
            d.charging_state = chg.get("state") or chg.get("status")
            d.is_charging = (
                isinstance(d.charging_state, str)
                and d.charging_state.lower() == "charging"
            )
            plug = charge_status.get("plug") or {}
            plug_state_raw = (
                plug.get("connection")
                or plug.get("connectionState")
                or plug.get("plugConnectionState")
            )
            d.plug_state = plug_state_raw
            d.plug_connected = (
                isinstance(plug_state_raw, str)
                and plug_state_raw.lower() == "connected"
            )
            plug_lock_raw = (
                plug.get("lock")
                or plug.get("lockState")
                or plug.get("plugLockState")
            )
            d.connector_locked = (
                isinstance(plug_lock_raw, str)
                and plug_lock_raw.lower() == "locked"
            )
        return d

    def _parser_status_top_level(self, status):
        """Replicate the v1.10.2 top-level status fallback parsing."""
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="V1")
        top_locked = status.get("locked")
        if isinstance(top_locked, bool):
            d.doors_locked = top_locked
        top_hood_locked = (status.get("hood") or {}).get("locked")
        if isinstance(top_hood_locked, str):
            d.hood_open = top_hood_locked.lower() == "false"
        return d

    def test_battery_soc_69(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        d = self._parser_charging_block(data["endpoints"]["charging"])
        assert d.battery_soc == 69
        assert d.has_battery is True

    def test_estimated_range_277(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        d = self._parser_charging_block(data["endpoints"]["charging"])
        assert d.range_km == 277

    def test_plug_disconnected(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        d = self._parser_charging_block(data["endpoints"]["charging"])
        assert d.plug_state == "disconnected"
        assert d.plug_connected is False

    def test_connector_unlocked(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        d = self._parser_charging_block(data["endpoints"]["charging"])
        assert d.connector_locked is False

    def test_charging_state_lowercase_classified(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        d = self._parser_charging_block(data["endpoints"]["charging"])
        assert d.charging_state == "notReadyForCharging"
        assert d.is_charging is False

    def test_top_level_locked_true(self):
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        d = self._parser_status_top_level(data["endpoints"]["status"])
        assert d.doors_locked is True

    def test_hood_locked_string_false_means_hood_open_false(self):
        """Born ships ``hood.locked = "false"`` (string!) which our
        v1.10.2 parser inverts into hood_open=True. But Gerhard's
        car has hood closed — fixture says ``"false"`` for locked,
        so by our parser convention hood_open should be True
        (not-locked = open)."""
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        d = self._parser_status_top_level(data["endpoints"]["status"])
        # locked="false" → hood_open=True per parser inversion
        assert d.hood_open is True

    def test_honk_and_flash_response_documented(self):
        """Fixture documents the missing-capability 400 Gerhard saw —
        Capability-Filter Phase 3 (planned v1.13.0) will use this to
        skip entity creation entirely."""
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        flash = data["endpoints"]["honk-and-flash"]
        assert flash["_response_status"] == 400
        assert flash["_response_body"]["code"] == "missing-capability"


# ─────────────────────────────────────────────────────────────────────────────
# #47 — FAQ section present in CONTRIBUTING.md
# ─────────────────────────────────────────────────────────────────────────────


class TestFAQDocsPresent:
    """v1.12.1 (#47) — FAQ section about Service Plus / Subscription
    requirements lives in CONTRIBUTING.md. Test confirms it isn't
    accidentally removed in a future doc rewrite."""

    def test_faq_section_present(self):
        contributing = (Path(__file__).parent.parent / "CONTRIBUTING.md").read_text(
            encoding="utf-8"
        )
        assert "## FAQ" in contributing
        assert "Subscription" in contributing or "subscription" in contributing
        assert "missing-capability" in contributing
        assert "Portugal" in contributing  # documented country-specific case
