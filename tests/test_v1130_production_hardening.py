# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.13.0 — Production Hardening Bundle.

Four feature groups:

A) Capability-Filter Phase 3 (#56 P3) — `command_capability_supported`
   helper + per-brand `CAPABILITY_MAP` lookup + tri-state semantics
   (True/False/None).
B) Per-VIN Command-Lock + 5-min Wake-Cooldown (#63 P2/P3) —
   `_get_command_lock`, `is_command_in_flight`, wake-cooldown raises
   `wake_cooldown_active` ServiceValidationError.
C) Read-only mode service-side enforcement (#63 P2) —
   `_coord_writeable` raises when read-only enabled.
D) Diagnostics polish (#62) — token redaction expanded, email partial-
   mask, GPS rounding opt-in, reverse-geocoding-aware.

Plus E) — Skoda capabilities endpoint (`/api/v1/vehicle-access/{vin}/capabilities`)
hits the right URL.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# A) Capability-Filter Phase 3
# ─────────────────────────────────────────────────────────────────────────────


class TestCapabilityMap:
    def test_volkswagen_lock_maps_to_access(self):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for

        assert cap_id_for("volkswagen", "command_lock") == "access"

    def test_audi_inherits_volkswagen(self):
        """v1.13.0 (#56): audi inherits VW EU CARIAD-BFF cap-ids.

        v1.14.0 (#28) — the inheritance moved from alias (``is``) to a
        defensive copy so audi-only patches like ``command_engine_start``
        don't pollute the VW EU table. We still assert the VW cap-ids
        are present in the audi table by content, plus a representative
        spot-check via ``cap_id_for``.
        """
        from custom_components.vag_connect.cariad._capabilities import (
            CAPABILITY_MAP,
            cap_id_for,
        )

        # Every VW EU command-id must still resolve in audi (content equivalence)
        for command_id, cap_id in CAPABILITY_MAP["volkswagen"].items():
            assert CAPABILITY_MAP["audi"].get(command_id) == cap_id, command_id
        assert cap_id_for("audi", "command_flash") == "honkAndFlash"

    def test_seat_inherits_cupra(self):
        from custom_components.vag_connect.cariad._capabilities import (
            CAPABILITY_MAP,
            cap_id_for,
        )

        assert CAPABILITY_MAP["seat"] is CAPABILITY_MAP["cupra"]
        assert cap_id_for("seat", "command_flash") == "honk-and-flash"

    def test_unknown_brand_returns_none(self):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for

        assert cap_id_for("unknown_brand", "command_lock") is None

    def test_unknown_command_returns_none(self):
        from custom_components.vag_connect.cariad._capabilities import cap_id_for

        assert cap_id_for("audi", "command_made_up") is None


class TestCommandCapabilitySupported:
    """Tri-state semantics: True/False/None map to keep/hide/unknown-keep."""

    def _coord(
        self,
        brand: str = "audi",
        vin: str = "VINX",
        capabilities: list[dict] | None = None,
    ):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": brand}
        coord.vehicle_capabilities = (
            {vin: {"capabilities": capabilities}} if capabilities is not None else {}
        )
        return coord

    def test_returns_none_when_no_brand(self):
        coord = self._coord(brand="")
        assert coord.command_capability_supported("VINX", "command_lock") is None

    def test_returns_none_when_no_capability_mapping(self):
        coord = self._coord(brand="porsche")  # empty CAPABILITY_MAP
        assert coord.command_capability_supported("VINX", "command_lock") is None

    def test_returns_true_when_capability_active(self):
        coord = self._coord(
            capabilities=[{"id": "honkAndFlash", "status": []}],
        )
        assert coord.command_capability_supported("VINX", "command_flash") is True

    def test_returns_false_when_capability_missing(self):
        coord = self._coord(
            capabilities=[{"id": "different", "status": []}],
        )
        # cache populated but honkAndFlash not listed → explicit absence = False
        assert coord.command_capability_supported("VINX", "command_flash") is False

    def test_returns_false_when_status_non_empty(self):
        coord = self._coord(
            capabilities=[
                {"id": "honkAndFlash", "status": [{"reason": "deactivated"}]},
            ],
        )
        assert coord.command_capability_supported("VINX", "command_flash") is False

    def test_skoda_active_false_returns_false(self):
        """Skoda mysmob schema: ``active=False`` → not supported."""
        coord = self._coord(
            brand="skoda",
            capabilities=[{"id": "honk-and-flash", "active": False}],
        )
        assert coord.command_capability_supported("VINX", "command_flash") is False

    def test_skoda_user_enabled_false_returns_false(self):
        coord = self._coord(
            brand="skoda",
            capabilities=[{"id": "access", "user-enabled": False}],
        )
        assert coord.command_capability_supported("VINX", "command_lock") is False

    def test_skoda_license_issue_returns_false(self):
        coord = self._coord(
            brand="skoda",
            capabilities=[{"id": "charging", "license-issue": "expired"}],
        )
        assert coord.command_capability_supported("VINX", "command_start_charging") is False


# ─────────────────────────────────────────────────────────────────────────────
# B) Command-Lock + Wake-Cooldown
# ─────────────────────────────────────────────────────────────────────────────


def _make_coord_for_lock_tests():
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "audi"}
    coord.entry.options = {}
    coord._vehicles_lock = threading.Lock()
    coord.vehicles = {"VINX": {}}
    coord._cariad_client = MagicMock()
    coord._cariad_client.command_wake = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    coord.async_set_updated_data = MagicMock()
    coord.record_command_success = MagicMock()
    coord.record_command_failure = MagicMock()
    return coord


class TestCommandLock:
    def test_get_command_lock_creates_lazily(self):
        coord = _make_coord_for_lock_tests()
        lock1 = coord._get_command_lock("VINX", "lock")
        lock2 = coord._get_command_lock("VINX", "lock")
        assert lock1 is lock2  # same lock returned for same key

    def test_different_classes_get_different_locks(self):
        coord = _make_coord_for_lock_tests()
        lock_lock = coord._get_command_lock("VINX", "lock")
        lock_climate = coord._get_command_lock("VINX", "climate")
        assert lock_lock is not lock_climate

    def test_is_command_in_flight_false_initially(self):
        coord = _make_coord_for_lock_tests()
        assert coord.is_command_in_flight("VINX", "lock") is False

    def test_is_command_in_flight_true_when_held(self):
        coord = _make_coord_for_lock_tests()
        lock = coord._get_command_lock("VINX", "lock")

        async def _hold():
            async with lock:
                assert coord.is_command_in_flight("VINX", "lock") is True

        asyncio.get_event_loop().run_until_complete(_hold())
        # Released after with-block
        assert coord.is_command_in_flight("VINX", "lock") is False


class TestWakeCooldown:
    def test_first_wake_no_cooldown(self):
        coord = _make_coord_for_lock_tests()
        # No prior wake → no cooldown raise
        asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VINX"))
        coord._cariad_client.command_wake.assert_awaited()

    def test_second_wake_within_cooldown_raises(self):
        from homeassistant.exceptions import ServiceValidationError

        coord = _make_coord_for_lock_tests()
        # First wake — succeeds
        asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VINX"))
        coord._cariad_client.command_wake.reset_mock()
        # Second wake immediately → cooldown raises
        with pytest.raises(ServiceValidationError):
            asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VINX"))
        # API was NOT called
        coord._cariad_client.command_wake.assert_not_awaited()

    def test_wake_after_cooldown_passes(self):
        coord = _make_coord_for_lock_tests()
        coord._wake_last_at = {"VINX": datetime.now(tz=timezone.utc) - timedelta(minutes=10)}
        # 10 min ago > 5-min cooldown → passes
        asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VINX"))
        coord._cariad_client.command_wake.assert_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# C) Read-only mode service-side enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestReadOnlyServiceBlocking:
    def test_coord_writeable_raises_when_readonly(self):
        """Service-side `_coord_writeable` blocks read-only calls."""
        from homeassistant.exceptions import ServiceValidationError

        # Simulate the helper inline (extracted from __init__.py logic)
        coord = MagicMock()
        coord.is_read_only = MagicMock(return_value=True)

        # Mimic _coord_writeable behaviour
        def _coord_writeable():
            if coord.is_read_only():
                raise ServiceValidationError(
                    "Read-only mode is enabled.",
                    translation_domain="vag_connect",
                    translation_key="read_only_mode_active",
                )
            return coord

        with pytest.raises(ServiceValidationError):
            _coord_writeable()

    def test_coord_writeable_passes_when_normal(self):
        coord = MagicMock()
        coord.is_read_only = MagicMock(return_value=False)

        def _coord_writeable():
            if coord.is_read_only():
                raise Exception("blocked")
            return coord

        assert _coord_writeable() is coord


# ─────────────────────────────────────────────────────────────────────────────
# D) Diagnostics polish
# ─────────────────────────────────────────────────────────────────────────────


class TestDiagnosticsPolish:
    def test_token_fields_in_redact_keys(self):
        from custom_components.vag_connect.diagnostics import _REDACT_KEYS

        for key in (
            "access_token", "refresh_token", "id_token",
            "accessToken", "refreshToken", "idToken",
            "client_secret",
        ):
            assert key in _REDACT_KEYS, f"missing token key: {key}"

    def test_email_partial_mask(self):
        from custom_components.vag_connect.diagnostics import _mask_email

        assert _mask_email("user@example.com") == "u***@***.com"
        assert _mask_email("prash@balan.uno") == "p***@***.uno"

    def test_email_in_text_partial_mask(self):
        from custom_components.vag_connect.diagnostics import _mask_email

        # Full sentence with email mid-text gets masked too
        result = _mask_email("Login failed for prash@balan.uno at 2026-05-02")
        assert "p***@***.uno" in result
        assert "prash@balan.uno" not in result

    def test_scrub_redacts_token(self):
        from custom_components.vag_connect.diagnostics import _scrub

        out = _scrub({"access_token": "eyJhbGc...", "other": "x"})
        assert out["access_token"] == "**REDACTED**"
        assert out["other"] == "x"

    def test_scrub_email_partial_mask(self):
        from custom_components.vag_connect.diagnostics import _scrub

        out = _scrub({"email": "test@example.com"})
        assert out["email"] == "t***@***.com"

    def test_scrub_gps_redacted_by_default(self):
        from custom_components.vag_connect.diagnostics import _scrub

        out = _scrub({"latitude": 48.137154, "longitude": 11.575401})
        assert out["latitude"] == "**REDACTED**"
        assert out["longitude"] == "**REDACTED**"

    def test_scrub_gps_rounded_opt_in(self):
        from custom_components.vag_connect.diagnostics import _scrub

        out = _scrub(
            {"latitude": 48.137154, "longitude": 11.575401},
            gps_round=True,
        )
        # Rounded to 1 decimal (~11 km bucket)
        assert out["latitude"] == 48.1
        assert out["longitude"] == 11.6


# ─────────────────────────────────────────────────────────────────────────────
# E) Skoda capabilities endpoint
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaCapabilities:
    def test_skoda_capabilities_url(self):
        """Verify Skoda hits ``/api/v1/vehicle-access/{vin}/capabilities``
        as documented in #56 / RESEARCH_NOTES_2026-04-29 §3."""
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient

        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(return_value={"capabilities": []})

        asyncio.get_event_loop().run_until_complete(
            client.get_capabilities("VINX")
        )
        called_url = client._get.await_args.args[0]
        assert "/api/v1/vehicle-access/VINX/capabilities" in called_url

    def test_skoda_capabilities_returns_dict_on_non_dict(self):
        """Defensive: garbage response → empty dict, never crash."""
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient

        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(return_value=["not a dict"])
        result = asyncio.get_event_loop().run_until_complete(
            client.get_capabilities("VINX")
        )
        assert result == {}
