# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#968 — the companion Force vehicle refresh button.

The button taps the app's "Synchronise now" and re-reads the app: once the car
has had time to answer when the sync was accepted, at once when it was refused.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.vag_connect.const import (
    CONF_READ_ONLY,
    CONF_STRATEGY,
    STRATEGY_COMPANION_ADB,
)


def _coord(*, brand: str = "volkswagen", read_only: bool = False):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {
        "brand": brand,
        CONF_STRATEGY: STRATEGY_COMPANION_ADB,
        CONF_READ_ONLY: read_only,
    }
    coord.entry.options = {}
    coord.vehicles = {"VINX": {"vin": "VINX", "model": "Test"}}
    coord._cariad_client = MagicMock()
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    coord.hass = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord._started = True
    return coord


def _buttons(coord) -> set[str]:
    from custom_components.vag_connect.button import async_setup_entry

    entry = MagicMock()
    entry.data = coord.entry.data
    entry.runtime_data = coord
    added: list = []
    asyncio.run(async_setup_entry(MagicMock(), entry, added.extend))
    return {type(e).__name__ for e in added}


class TestSpawn:
    def test_volkswagen_companion_gets_the_button(self) -> None:
        assert "VagCompanionForceRefreshButton" in _buttons(_coord())

    def test_brand_without_sync_in_its_preset_does_not(self) -> None:
        assert "VagCompanionForceRefreshButton" not in _buttons(_coord(brand="audi"))

    def test_read_only_entry_does_not(self) -> None:
        names = _buttons(_coord(read_only=True))
        assert "VagCompanionForceRefreshButton" not in names
        assert "VagCompanionRefreshButton" in names


class TestPress:
    @pytest.mark.asyncio
    async def test_accepted_sync_reads_back_later(self) -> None:
        coord = _coord()
        coord.async_companion_sync_vehicle = AsyncMock(return_value=True)
        tasks: list = []
        # entry-scoped, so HA cancels the read-back if the entry unloads first
        coord.entry.async_create_background_task = lambda _h, c, _n: tasks.append(c)
        await coord.async_companion_force_refresh()
        coord.async_request_refresh.assert_not_awaited()
        assert len(tasks) == 1
        with patch("custom_components.vag_connect.coordinator.asyncio.sleep", AsyncMock()) as sleep:
            await tasks[0]
        sleep.assert_awaited_once_with(180.0)
        coord.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_read_back_after_shutdown(self) -> None:
        coord = _coord()
        coord._started = False
        with patch("custom_components.vag_connect.coordinator.asyncio.sleep", AsyncMock()):
            await coord._companion_sync_readback()
        coord.async_request_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refused_sync_reads_now_and_fails_the_press(self) -> None:
        coord = _coord()
        coord.async_companion_sync_vehicle = AsyncMock(return_value=False)
        with pytest.raises(HomeAssistantError) as err:
            await coord.async_companion_force_refresh()
        assert err.value.translation_key == "companion_sync_refused"
        coord.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_attempt_still_reads(self) -> None:
        coord = _coord()
        coord.async_companion_sync_vehicle = AsyncMock(return_value=None)
        await coord.async_companion_force_refresh()
        coord.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_button_press_calls_the_coordinator(self) -> None:
        from custom_components.vag_connect.button import VagCompanionForceRefreshButton

        coord = _coord()
        coord.async_companion_force_refresh = AsyncMock()
        await VagCompanionForceRefreshButton(coord, "VINX").async_press()
        coord.async_companion_force_refresh.assert_awaited_once()


class TestPlacementAndNames:
    """The companion's two refresh buttons sit in Configuration, next to the
    reset button, under names that say what each refreshes."""

    def _entities(self, coord) -> dict:
        from custom_components.vag_connect.button import async_setup_entry

        entry = MagicMock()
        entry.data = coord.entry.data
        entry.runtime_data = coord
        added: list = []
        asyncio.run(async_setup_entry(MagicMock(), entry, added.extend))
        return {type(e).__name__: e for e in added}

    def test_all_three_companion_buttons_are_config(self) -> None:
        from homeassistant.const import EntityCategory

        found = self._entities(_coord())
        for name in (
            "VagCompanionRefreshButton",
            "VagCompanionForceRefreshButton",
            "VagCompanionResetButton",
        ):
            assert found[name].entity_category is EntityCategory.CONFIG, name
        assert "VagRefreshButton" not in found

    def test_companion_refresh_keeps_the_shared_unique_id(self) -> None:
        from custom_components.vag_connect.button import (
            VagCompanionRefreshButton,
            VagRefreshButton,
        )

        coord = _coord()
        assert (
            VagCompanionRefreshButton(coord, "VINX").unique_id
            == VagRefreshButton(coord, "VINX").unique_id
        )

    def test_names(self) -> None:
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
        for path in (root / "strings.json", root / "translations" / "en.json"):
            names = json.loads(path.read_text(encoding="utf-8"))["entity"]["button"]
            assert names["companion_refresh_button"]["name"] == "Refresh app screen data"
            assert names["companion_force_refresh_button"]["name"] == "Refresh vehicle data"
            assert names["refresh_button"]["name"] == "Refresh Data"
