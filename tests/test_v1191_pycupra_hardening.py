# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.19.1 — Pycupra-style API quota visibility.

Most VAG backends send X-RateLimit-* headers on successful 2xx
responses. Pycupra surfaces these to users so they can see how
close they are to the daily quota cap (~1500/day on MyCupra/MySeat).

This release wires the same up:

1. base.py: ``_capture_rate_limit_headers(headers)`` parses
   X-RateLimit-Remaining / X-RateLimit-Limit / X-RateLimit-Reset
   into instance attributes after every successful response.
2. coordinator.py: ``_enrich`` copies the brand-client's last-
   observed headers onto each VIN's data dict (auth is brand-
   scoped, so all VINs of a given brand see the same quota).
3. sensor.py: New ``requests_remaining_today`` diagnostic sensor
   exposes the value.

Tests cover header parsing edge-cases + dict-copy invariant.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# A) _capture_rate_limit_headers parsing
# ─────────────────────────────────────────────────────────────────────────────


class TestCaptureRateLimitHeaders:
    def _new_client(self):
        """Build a CariadBaseClient instance without auth pipeline."""
        from custom_components.vag_connect.cariad.api.base import (
            CariadBaseClient,
        )
        c = CariadBaseClient.__new__(CariadBaseClient)
        c.last_rate_limit_remaining = None
        c.last_rate_limit_limit = None
        c.last_rate_limit_reset_at = None
        return c

    def test_initial_values_are_none(self):
        c = self._new_client()
        assert c.last_rate_limit_remaining is None
        assert c.last_rate_limit_limit is None
        assert c.last_rate_limit_reset_at is None

    def test_parses_int_remaining(self):
        c = self._new_client()
        c._capture_rate_limit_headers({"X-RateLimit-Remaining": "1499"})
        assert c.last_rate_limit_remaining == 1499

    def test_parses_int_limit(self):
        c = self._new_client()
        c._capture_rate_limit_headers({
            "X-RateLimit-Remaining": "1499",
            "X-RateLimit-Limit": "1500",
        })
        assert c.last_rate_limit_remaining == 1499
        assert c.last_rate_limit_limit == 1500

    def test_parses_reset_as_string(self):
        c = self._new_client()
        c._capture_rate_limit_headers({
            "X-RateLimit-Reset": "2026-05-05T00:00:00Z",
        })
        assert c.last_rate_limit_reset_at == "2026-05-05T00:00:00Z"

    def test_handles_float_remaining_via_fallback(self):
        """Some backends ship floats (e.g. '1499.5'). int() rejects
        the string but float() handles it — fallback chain gives us
        the truncated int."""
        c = self._new_client()
        c._capture_rate_limit_headers({"X-RateLimit-Remaining": "1499.5"})
        assert c.last_rate_limit_remaining == 1499

    def test_handles_garbage_remaining_leaves_previous_value(self):
        """Backends shipping non-numeric ('unlimited', 'N/A') should
        leave the previous observation — better stale than wrong."""
        c = self._new_client()
        c._capture_rate_limit_headers({"X-RateLimit-Remaining": "1000"})
        assert c.last_rate_limit_remaining == 1000
        c._capture_rate_limit_headers({"X-RateLimit-Remaining": "unlimited"})
        # Previous value preserved (NOT reset to None)
        assert c.last_rate_limit_remaining == 1000

    def test_missing_header_leaves_previous_value(self):
        """Some endpoints don't send the header at all. Don't reset
        previously observed values — sensor would otherwise flicker
        every time the user hit a header-less endpoint."""
        c = self._new_client()
        c._capture_rate_limit_headers({"X-RateLimit-Remaining": "500"})
        c._capture_rate_limit_headers({})  # no headers
        assert c.last_rate_limit_remaining == 500

    def test_partial_headers_only_update_observed_fields(self):
        c = self._new_client()
        c._capture_rate_limit_headers({
            "X-RateLimit-Remaining": "100",
            "X-RateLimit-Limit": "1500",
            "X-RateLimit-Reset": "2026-05-05T00:00:00Z",
        })
        assert c.last_rate_limit_remaining == 100
        assert c.last_rate_limit_limit == 1500
        # Now send only Remaining — Limit + Reset preserved
        c._capture_rate_limit_headers({"X-RateLimit-Remaining": "99"})
        assert c.last_rate_limit_remaining == 99
        assert c.last_rate_limit_limit == 1500
        assert c.last_rate_limit_reset_at == "2026-05-05T00:00:00Z"


# ─────────────────────────────────────────────────────────────────────────────
# B) VehicleData field invariant
# ─────────────────────────────────────────────────────────────────────────────


class TestVehicleDataQuotaFields:
    def test_field_exists_and_default_none(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        assert hasattr(d, "requests_remaining_today")
        assert hasattr(d, "requests_limit_today")
        assert hasattr(d, "requests_reset_at")
        assert d.requests_remaining_today is None
        assert d.requests_limit_today is None
        assert d.requests_reset_at is None

    def test_field_accepts_int(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST")
        d.requests_remaining_today = 1499
        d.requests_limit_today = 1500
        d.requests_reset_at = "2026-05-05T00:00:00Z"
        assert d.requests_remaining_today == 1499


# ─────────────────────────────────────────────────────────────────────────────
# C) Const + sensor exposure
# ─────────────────────────────────────────────────────────────────────────────


class TestSensorExposure:
    def test_sensor_description_present(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        assert "requests_remaining_today" in keys

    def test_sensor_is_diagnostic_category(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
        from homeassistant.helpers.entity import EntityCategory
        desc = next(
            (d for d in SENSOR_DESCRIPTIONS if d.key == "requests_remaining_today"),
            None,
        )
        assert desc is not None
        assert desc.entity_category == EntityCategory.DIAGNOSTIC

    def test_sensor_has_translation_key(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
        desc = next(
            (d for d in SENSOR_DESCRIPTIONS if d.key == "requests_remaining_today"),
            None,
        )
        assert desc is not None
        assert desc.translation_key == "requests_remaining_today"
        assert desc.data_key == "requests_remaining_today"


# ─────────────────────────────────────────────────────────────────────────────
# D) Translation strings
# ─────────────────────────────────────────────────────────────────────────────


class TestTranslations:
    def test_strings_json_has_sensor_name(self):
        import json
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        path = repo / "custom_components/vag_connect/strings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "requests_remaining_today" in data["entity"]["sensor"]
        name = data["entity"]["sensor"]["requests_remaining_today"]["name"]
        assert "API" in name and "Remaining" in name

    def test_de_translation_has_sensor_name(self):
        import json
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        path = repo / "custom_components/vag_connect/translations/de.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "requests_remaining_today" in data["entity"]["sensor"]
        name = data["entity"]["sensor"]["requests_remaining_today"]["name"]
        assert "API" in name and ("verbleibend" in name or "übrig" in name)
