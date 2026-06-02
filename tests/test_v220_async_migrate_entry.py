# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 PR #4 — async_migrate_entry stub tests.

Pre-empts the HA Core deprecation cliff that hit competitors:
- upstream #728 (Invalid Credentials after every Core update)
- mitch-dc/volkswagen_we_connect_id #303 (Cannot login after HAOS 16.1)

Both projects silently broke when HA Core changed ConfigEntry data
serialisation. Without ``async_migrate_entry``, HA falls back to
"invalid credentials" with no actionable hint.

"Suit up!"  — Barney, before every HA Core release-train cliff
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestAsyncMigrateEntryStub:
    """The stub returns True for every entry version (cap at VERSION=1
    today). Future v2 migration will add real logic here."""

    @pytest.mark.asyncio
    async def test_stub_returns_true_for_v1(self) -> None:
        from custom_components.vag_connect import async_migrate_entry
        hass = MagicMock()
        entry = MagicMock()
        entry.version = 1
        result = await async_migrate_entry(hass, entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_stub_returns_true_for_unknown_version(self) -> None:
        """Even if HA inserts a future-version entry (shouldn't happen
        but defensive), the stub doesn't crash."""
        from custom_components.vag_connect import async_migrate_entry
        hass = MagicMock()
        entry = MagicMock()
        entry.version = 99
        result = await async_migrate_entry(hass, entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_stub_returns_true_when_version_attr_missing(self) -> None:
        """Pre-HA-2024.10 entries may lack ``version`` attribute.
        ``getattr(entry, "version", 1)`` covers this — stub must not crash."""
        from custom_components.vag_connect import async_migrate_entry
        hass = MagicMock()
        # MagicMock auto-creates attributes; force missing via spec
        entry = MagicMock(spec=[])
        result = await async_migrate_entry(hass, entry)
        assert result is True


class TestRuntimeDataLookup:
    """``_get_coordinator`` defensive against entries not yet loaded
    (startup race) using ``getattr(..., None)``."""

    def test_get_coordinator_skips_entry_without_runtime_data(self) -> None:
        from custom_components.vag_connect import _get_coordinator
        hass = MagicMock()
        # Entry without runtime_data (e.g. mid-setup)
        loading_entry = MagicMock(spec=[])
        hass.config_entries.async_entries.return_value = [loading_entry]
        result = _get_coordinator(hass, "VIN123")
        assert result is None

    def test_get_coordinator_returns_match(self) -> None:
        from custom_components.vag_connect import _get_coordinator
        hass = MagicMock()
        coord = MagicMock()
        coord.vehicles = {"VIN_ALPHA": {}, "VIN_BETA": {}}
        loaded_entry = MagicMock()
        loaded_entry.runtime_data = coord
        hass.config_entries.async_entries.return_value = [loaded_entry]
        result = _get_coordinator(hass, "VIN_BETA")
        assert result is coord

    def test_get_coordinator_returns_none_when_vin_unknown(self) -> None:
        from custom_components.vag_connect import _get_coordinator
        hass = MagicMock()
        coord = MagicMock()
        coord.vehicles = {"OTHER_VIN": {}}
        entry = MagicMock()
        entry.runtime_data = coord
        hass.config_entries.async_entries.return_value = [entry]
        result = _get_coordinator(hass, "VIN_NOT_FOUND")
        assert result is None
