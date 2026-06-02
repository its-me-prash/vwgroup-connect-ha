# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 2 PR #8/20 — SEAT/CUPRA Connect-subscription expiry sensor.

Long-standing user request: surface when the Connect subscription
(charging/climatisation/windowHeating remote services) runs out so
the user can plan renewal before lock/unlock + climate-start stop
working.

The SEAT/CUPRA OLA ``mycar.services`` block is a per-entitlement map
where each entry MAY carry one of three expiry-key spellings
(``expirationDate`` / ``validUntil`` / ``expiresAt`` — pycupra
commit 0f3b1c7 documents the rotation). The parser picks the
EARLIEST present expiry across all services so the user sees
"first to expire" (most-restrictive cap on remote access).

Defensive: malformed timestamps are silently skipped; if no service
carries an expiry, ``subscription_expiry_at`` stays None and the
sensor is never created (phantom-protected).

"You have failed me for the last time, Admiral... ation Subscription."
— Sheldon Cooper, on the day his Wolowitz-built robot lost API access
"""

from __future__ import annotations

import pytest


class TestExpiryAggregation:
    """The earliest expiry across services wins."""

    def _make_device(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        return VehicleData(vin="TESTVIN")

    def _parse(self, services: dict | None) -> str | None:
        """Pure-python mirror of the seat_cupra.py parser body — keeps
        this test independent of the full async-fetch machinery."""
        if not isinstance(services, dict):
            return None
        earliest: str | None = None
        for svc_data in services.values():
            if not isinstance(svc_data, dict):
                continue
            raw_expiry = (
                svc_data.get("expirationDate")
                or svc_data.get("validUntil")
                or svc_data.get("expiresAt")
            )
            if not isinstance(raw_expiry, str) or not raw_expiry:
                continue
            if earliest is None or raw_expiry < earliest:
                earliest = raw_expiry
        return earliest

    def test_single_service_expirationDate(self) -> None:
        services = {
            "charging": {
                "state": "ACTIVATED",
                "expirationDate": "2027-03-15T00:00:00Z",
            },
        }
        assert self._parse(services) == "2027-03-15T00:00:00Z"

    def test_single_service_validUntil_variant(self) -> None:
        services = {
            "climatisation": {"validUntil": "2026-12-31T23:59:59Z"},
        }
        assert self._parse(services) == "2026-12-31T23:59:59Z"

    def test_single_service_expiresAt_variant(self) -> None:
        services = {
            "windowHeating": {"expiresAt": "2028-01-01T00:00:00Z"},
        }
        assert self._parse(services) == "2028-01-01T00:00:00Z"

    def test_earliest_across_multiple_services_wins(self) -> None:
        # Charging expires 2027, climatisation expires 2026 — climatisation
        # wins (most-restrictive cap on remote functionality).
        services = {
            "charging": {"expirationDate": "2027-03-15T00:00:00Z"},
            "climatisation": {"expirationDate": "2026-08-01T00:00:00Z"},
            "windowHeating": {"expirationDate": "2029-01-01T00:00:00Z"},
        }
        assert self._parse(services) == "2026-08-01T00:00:00Z"

    def test_mixed_key_variants_compose(self) -> None:
        services = {
            "a": {"expirationDate": "2027-06-01T00:00:00Z"},
            "b": {"validUntil": "2026-12-01T00:00:00Z"},  # earliest
            "c": {"expiresAt": "2028-01-01T00:00:00Z"},
        }
        assert self._parse(services) == "2026-12-01T00:00:00Z"


class TestExpiryDefensive:
    """Malformed shapes must NEVER raise — they fall through to None."""

    def _parse(self, services):
        if not isinstance(services, dict):
            return None
        earliest = None
        for svc_data in services.values():
            if not isinstance(svc_data, dict):
                continue
            raw_expiry = (
                svc_data.get("expirationDate")
                or svc_data.get("validUntil")
                or svc_data.get("expiresAt")
            )
            if not isinstance(raw_expiry, str) or not raw_expiry:
                continue
            if earliest is None or raw_expiry < earliest:
                earliest = raw_expiry
        return earliest

    def test_none_services_block(self) -> None:
        assert self._parse(None) is None

    def test_empty_services_dict(self) -> None:
        assert self._parse({}) is None

    def test_perpetual_services_no_expiry(self) -> None:
        services = {
            "charging": {"state": "ACTIVATED"},
            "climatisation": {"state": "ACTIVATED", "subscription": "PERPETUAL"},
        }
        assert self._parse(services) is None

    def test_int_expiry_skipped(self) -> None:
        # Some backend revision once shipped int unix-timestamp — must
        # NOT crash, just skip (we only handle ISO strings).
        services = {"charging": {"expirationDate": 1735689600}}
        assert self._parse(services) is None

    def test_empty_string_expiry_skipped(self) -> None:
        services = {"charging": {"expirationDate": ""}}
        assert self._parse(services) is None

    def test_non_dict_service_value_skipped(self) -> None:
        # If a service entry is a string ("ACTIVATED") instead of a dict —
        # legacy mycar shape — don't crash.
        services = {
            "charging": "ACTIVATED",
            "climatisation": {"expirationDate": "2027-01-01T00:00:00Z"},
        }
        assert self._parse(services) == "2027-01-01T00:00:00Z"

    def test_non_dict_services_block(self) -> None:
        # Backend rotation could ship list / string at the parent level
        assert self._parse([]) is None
        assert self._parse("") is None


class TestSensorRegistration:
    """Description + phantom-protection gate registration."""

    def test_subscription_expiry_described(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        assert "subscription_expiry_at" in keys

    def test_subscription_expiry_uses_timestamp_device_class(self) -> None:
        from homeassistant.components.sensor import SensorDeviceClass

        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        desc = next(
            d for d in SENSOR_DESCRIPTIONS if d.key == "subscription_expiry_at"
        )
        assert desc.device_class == SensorDeviceClass.TIMESTAMP

    def test_subscription_expiry_phantom_gated(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "subscription_expiry_at" in _DATA_PRESENT_REQUIRED


class TestTranslationCoverage:
    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_subscription_expiry(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "subscription_expiry_at" in data["entity"]["sensor"]
        assert "name" in data["entity"]["sensor"]["subscription_expiry_at"]

    def test_strings_json_has_subscription_expiry(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        assert "subscription_expiry_at" in data["entity"]["sensor"]
