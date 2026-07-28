# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.26.0 (ckomma #21/#22) — the coordinator wiring for the companion channel:

- Feature B: a rate-limit / lockout backoff (wall-clock, hours long) is PERSISTED
  to the config entry so it survives an HA restart. An account lockout must not
  be cleared just by restarting the way a TCP blip would be.
- Feature C: a user-facing reset clears a stuck failure/rate-limit backoff AND
  the persisted value, then re-reads.

These mirror the _persist_supplementary_cookies tests: build the coordinator via
__new__ so no HA runtime is needed, and assert on async_update_entry.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.const import (
    CONF_COMPANION_RATE_LIMIT_UNTIL,
    CONF_STRATEGY,
    STRATEGY_COMPANION_ADB,
)


def _coord(*, entry_data, rate_limited_until=0.0, reset_cb=None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    c.entry.data = dict(entry_data)
    c.hass = MagicMock()
    c.hass.config_entries = MagicMock()
    client = MagicMock()
    client.companion_rate_limited_until = rate_limited_until
    client.reset_cooldown = reset_cb or MagicMock()
    c._cariad_client = client
    return c


def _updated_data(c):
    call = c.hass.config_entries.async_update_entry.call_args
    return call.kwargs["data"] if call else None


# ── Feature B: persistence ───────────────────────────────────────────────────

class TestRateLimitPersist:
    def test_persists_a_new_backoff(self) -> None:
        c = _coord(
            entry_data={CONF_STRATEGY: STRATEGY_COMPANION_ADB},
            rate_limited_until=1_700_000_000.0,
        )
        c._persist_companion_rate_limit()
        data = _updated_data(c)
        assert data is not None
        assert data[CONF_COMPANION_RATE_LIMIT_UNTIL] == 1_700_000_000.0

    def test_noop_when_unchanged(self) -> None:
        c = _coord(
            entry_data={
                CONF_STRATEGY: STRATEGY_COMPANION_ADB,
                CONF_COMPANION_RATE_LIMIT_UNTIL: 1_700_000_000.0,
            },
            rate_limited_until=1_700_000_000.0,
        )
        c._persist_companion_rate_limit()
        c.hass.config_entries.async_update_entry.assert_not_called()

    def test_persists_a_cleared_backoff(self) -> None:
        # backoff was set, now cleared → 0.0 must be written back, not left stale.
        c = _coord(
            entry_data={
                CONF_STRATEGY: STRATEGY_COMPANION_ADB,
                CONF_COMPANION_RATE_LIMIT_UNTIL: 1_700_000_000.0,
            },
            rate_limited_until=0.0,
        )
        c._persist_companion_rate_limit()
        data = _updated_data(c)
        assert data is not None
        assert data[CONF_COMPANION_RATE_LIMIT_UNTIL] == 0.0

    def test_noop_when_not_a_companion_entry(self) -> None:
        c = _coord(entry_data={CONF_STRATEGY: "device_grant_portal"},
                   rate_limited_until=1_700_000_000.0)
        c._persist_companion_rate_limit()
        c.hass.config_entries.async_update_entry.assert_not_called()

    def test_missing_client_is_soft(self) -> None:
        c = _coord(entry_data={CONF_STRATEGY: STRATEGY_COMPANION_ADB})
        c._cariad_client = None
        # no client attr → treated as 0.0, no crash, no write (0 == 0 default)
        c._persist_companion_rate_limit()
        c.hass.config_entries.async_update_entry.assert_not_called()


# ── Feature C: reset ─────────────────────────────────────────────────────────

class TestResetCooldown:
    @pytest.mark.asyncio
    async def test_reset_clears_channel_and_persisted_value(self) -> None:
        reset_cb = MagicMock()
        c = _coord(
            entry_data={
                CONF_STRATEGY: STRATEGY_COMPANION_ADB,
                CONF_COMPANION_RATE_LIMIT_UNTIL: 1_700_000_000.0,
            },
            rate_limited_until=0.0,  # channel is cleared post-reset
            reset_cb=reset_cb,
        )
        c.async_request_refresh = AsyncMock()
        await c.async_reset_companion_cooldown()
        reset_cb.assert_called_once()
        # the stale persisted lockout is wiped so a restart won't restore it
        data = _updated_data(c)
        assert data is not None
        assert data[CONF_COMPANION_RATE_LIMIT_UNTIL] == 0.0
        c.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_is_safe_without_a_companion_client(self) -> None:
        c = _coord(entry_data={CONF_STRATEGY: STRATEGY_COMPANION_ADB})
        c._cariad_client = object()  # no reset_cooldown method
        c.async_request_refresh = AsyncMock()
        await c.async_reset_companion_cooldown()  # must not raise
        c.async_request_refresh.assert_awaited_once()


# ── is_companion helper ──────────────────────────────────────────────────────

class TestIsCompanion:
    def test_true_for_companion(self) -> None:
        c = _coord(entry_data={CONF_STRATEGY: STRATEGY_COMPANION_ADB})
        assert c.is_companion() is True

    def test_false_for_other(self) -> None:
        c = _coord(entry_data={CONF_STRATEGY: "device_grant_portal"})
        assert c.is_companion() is False

    def test_false_when_absent(self) -> None:
        c = _coord(entry_data={})
        assert c.is_companion() is False


# ── button platform: companion gets the reset button, not the portal one ─────

def _companion_button_coord(brand: str):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": brand, CONF_STRATEGY: STRATEGY_COMPANION_ADB}
    coord.entry.options = {}
    coord.vehicles = {"VINX": {"vin": "VINX", "model": "Test"}}
    coord._cariad_client = MagicMock()
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


class TestButtonSpawn:
    def _added_for(self, brand: str):
        import asyncio

        from custom_components.vag_connect.button import async_setup_entry

        coord = _companion_button_coord(brand)
        entry = MagicMock()
        entry.runtime_data = coord
        entry.async_on_unload = lambda x: None
        added: list = []
        asyncio.run(async_setup_entry(MagicMock(), entry, added.extend))
        return {type(e).__name__ for e in added}

    def test_companion_gets_reset_button_not_dataact(self) -> None:
        # unverified brand (audi has no companion preset → structurally read-only)
        names = self._added_for("audi")
        assert "VagCompanionResetButton" in names
        assert "VagDataActRequestButton" not in names
        assert "VagRefreshButton" in names

    def test_companion_verified_brand_also_gets_reset(self) -> None:
        # volkswagen preset is writable (not forced read-only), still a companion
        names = self._added_for("volkswagen")
        assert "VagCompanionResetButton" in names
        assert "VagDataActRequestButton" not in names
        # no flash/wake: the companion client implements neither command
        assert "VagFlashButton" not in names
        assert "VagWakeButton" not in names
