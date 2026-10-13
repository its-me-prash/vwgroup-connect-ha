"""#968 companion startup — a companion (ADB) entry must not hold config-entry
setup (and HA startup) open on its first read.

A companion read is a full app-screen walk plus every enabled nav-read opt-in,
which takes minutes. Setup now only connects + enumerates; the restored
snapshot (or a bare placeholder on a first-ever setup) stands until the
background poll loop's first tick, which for a companion runs immediately.
Every other strategy still reads inline and its poll loop still sleeps first.

Harness mirrors test_v2241_setup_data_loss_and_position_ttl (coordinator via
__new__, factory/client patched, ``asyncio.run(coord.async_setup())``) and
test_v2159_transient_and_interaction_deescalation (one real _poll_loop pass).
"""
from __future__ import annotations

import asyncio
import threading
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.const import (
    CONF_ADB_HOST,
    CONF_STRATEGY,
    CONF_VIN,
    STRATEGY_COMPANION_ADB,
)

VIN = "WVWZZZE1ZMP000968"


def _coord(entry_data: dict[str, Any], restored: dict[str, Any] | None = None) -> Any:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.hass.loop.call_soon_threadsafe = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.data = dict(entry_data)
    coord.entry.options = {}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = None
    coord._started = False
    coord._was_available = True
    coord.vehicles = {VIN: dict(restored)} if restored else {}
    coord.vehicle_success = {}
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    return coord


def _companion_entry() -> dict[str, Any]:
    return {
        "brand": "volkswagen",
        CONF_STRATEGY: STRATEGY_COMPANION_ADB,
        CONF_VIN: VIN,
        CONF_ADB_HOST: "192.0.2.10",
        "scan_interval": 5,
    }


def _portal_entry() -> dict[str, Any]:
    return {
        "brand": "volkswagen", "username": "u@t.de",
        "password": "pw", "spin": "", "scan_interval": 5,
    }


def _client(status: Any = None) -> MagicMock:
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.get_vehicles = AsyncMock(return_value=[VIN])
    client.get_status = AsyncMock(return_value=status or VehicleData(vin=VIN))
    return client


def _run_setup(coord: Any, client: MagicMock) -> bool:
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory

    with patch.object(CariadClientFactory, "create", return_value=client), \
         patch(
             "custom_components.vag_connect.companion.CompanionClient",
             return_value=client,
         ), \
         patch(
             "homeassistant.helpers.aiohttp_client.async_get_clientsession",
             return_value=MagicMock(),
         ):
        return asyncio.run(coord.async_setup())


def _close_background_coros(coord: Any) -> None:
    """The scheduled background coroutines never ran (hass is a mock)."""
    for call in coord.hass.async_create_background_task.call_args_list:
        coro = call.args[0]
        if asyncio.iscoroutine(coro):
            coro.close()


# ── setup ───────────────────────────────────────────────────────────────────


class TestCompanionSetupDoesNotRead:
    def test_setup_returns_true_without_get_status(self) -> None:
        coord = _coord(_companion_entry())
        client = _client()
        try:
            assert _run_setup(coord, client) is True
        finally:
            _close_background_coros(coord)
        client.authenticate.assert_awaited_once()
        client.get_status.assert_not_called()
        # the rest still runs in the background, never inline
        assert coord.hass.async_create_background_task.called
        coord.hass.async_create_task.assert_not_called()

    def test_first_ever_setup_seeds_a_placeholder(self) -> None:
        coord = _coord(_companion_entry())
        client = _client()
        try:
            assert _run_setup(coord, client) is True
        finally:
            _close_background_coros(coord)
        placeholder = coord.vehicles[VIN]
        assert placeholder["vin"] == VIN
        assert placeholder["_client"] is client
        assert placeholder["_poll_failed"] is False
        # nothing was read, so nothing counts as a successful read
        assert VIN not in coord.vehicle_success

    def test_restored_snapshot_is_kept(self) -> None:
        restored = {
            "vin": VIN, "battery_soc": 64, "odometer_km": 81234,
            "_restored": True, "_poll_failed": False,
        }
        coord = _coord(_companion_entry(), restored=restored)
        client = _client()
        try:
            assert _run_setup(coord, client) is True
        finally:
            _close_background_coros(coord)
        kept = coord.vehicles[VIN]
        assert kept["battery_soc"] == 64
        assert kept["odometer_km"] == 81234
        assert kept["_restored"] is True
        client.get_status.assert_not_called()

    def test_auth_failure_still_fails_setup(self) -> None:
        """The transport connect stays inline: a failure still fails setup."""
        coord = _coord(_companion_entry())
        client = _client()
        client.authenticate = AsyncMock(side_effect=OSError("no route"))
        assert _run_setup(coord, client) is False
        client.get_status.assert_not_called()
        coord.hass.async_create_background_task.assert_not_called()


class TestNonCompanionSetupUnchanged:
    def test_portal_setup_still_reads_inline(self) -> None:
        coord = _coord(_portal_entry())
        client = _client(VehicleData(vin=VIN, battery_soc=88))
        try:
            assert _run_setup(coord, client) is True
        finally:
            _close_background_coros(coord)
        client.get_status.assert_awaited_once_with(VIN)
        assert coord.vehicles[VIN]["battery_soc"] == 88
        assert coord.vehicle_success[VIN] is True


# ── poll loop first tick ────────────────────────────────────────────────────


def _poll_coord(entry_data: dict[str, Any]) -> tuple[Any, list[float]]:
    """A coordinator wired for exactly one real poll pass; returns the sleeps
    taken before that pass pushed its update."""
    from custom_components.vag_connect.cariad._error_reporter import ErrorRingBuffer
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.vehicles = {VIN: {"vin": VIN}}
    coord.error_buffer = ErrorRingBuffer()
    coord.vehicle_success = {}
    coord.vehicle_failure_count = {}
    coord.vehicle_last_good_at = {}
    coord._vehicles_lock = threading.Lock()
    coord._started = True
    coord.entry = types.SimpleNamespace(
        data=dict(entry_data), options={}, entry_id="e1",
    )

    reads: list[str] = []

    async def _get_status(vin: str) -> VehicleData:
        reads.append(vin)
        return VehicleData(vin=VIN, battery_soc=70)

    coord._cariad_client = types.SimpleNamespace(get_status=_get_status)
    coord._reads = reads
    sleeps: list[float] = []
    sleeps_before_push: list[float] = []

    async def _push(_data: Any, success: bool = True) -> None:
        sleeps_before_push.extend(sleeps)
        coord._started = False

    coord._async_push_update = _push
    coord._refresh_reporter_issues = lambda: None
    coord._save_vehicle_cache = lambda: None
    coord._update_data_act_no_data_repair = lambda: None
    coord._maybe_run_stale_watchdog = AsyncMock()
    coord.refresh_trip_statistics = AsyncMock()
    coord.refresh_charging_history = AsyncMock()
    coord.refresh_charging_profiles = AsyncMock()
    coord.refresh_battery_care = AsyncMock()
    coord._recorded_sleeps = sleeps
    return coord, sleeps_before_push


async def _run_one_poll(coord: Any, **kwargs: Any) -> None:
    import custom_components.vag_connect.coordinator as mod

    orig_sleep = mod.asyncio.sleep

    async def _fast_sleep(s: float) -> None:
        coord._recorded_sleeps.append(s)

    mod.asyncio.sleep = _fast_sleep  # type: ignore[assignment]
    try:
        await asyncio.wait_for(coord._poll_loop(**kwargs), timeout=5)
    finally:
        mod.asyncio.sleep = orig_sleep  # type: ignore[assignment]


class TestPollLoopFirstTick:
    @pytest.mark.asyncio
    async def test_companion_first_tick_does_not_sleep(self) -> None:
        coord, sleeps = _poll_coord(_companion_entry())
        await _run_one_poll(coord, first_immediate=True)
        assert sleeps == []
        assert coord._reads == [VIN]

    @pytest.mark.asyncio
    async def test_non_companion_still_sleeps_first(self) -> None:
        coord, sleeps = _poll_coord(_portal_entry())
        await _run_one_poll(coord)
        assert len(sleeps) == 1
        assert sleeps[0] > 0

    @pytest.mark.asyncio
    async def test_only_the_first_tick_is_immediate(self) -> None:
        coord, _ = _poll_coord(_companion_entry())
        passes = 0

        async def _push(_data: Any, success: bool = True) -> None:
            nonlocal passes
            passes += 1
            if passes == 2:
                coord._started = False

        coord._async_push_update = _push
        await _run_one_poll(coord, first_immediate=True)
        # second pass slept exactly once, the first did not
        assert passes == 2
        assert len(coord._recorded_sleeps) == 1


class TestBackgroundStart:
    def test_companion_poll_loop_started_immediate(self) -> None:
        coord = _coord(_companion_entry())
        coord._poll_loop = MagicMock(return_value=None)
        coord._companion_app_sync_loop = MagicMock(return_value=None)
        coord.refresh_capabilities = AsyncMock()
        coord.refresh_static_info = AsyncMock()
        coord._refresh_mbb_command_capabilities = AsyncMock()
        coord._ensure_data_act_custom_request_kickoff = AsyncMock()
        client = _client()
        assert _run_setup(coord, client) is True
        finish = coord.hass.async_create_background_task.call_args.args[0]
        asyncio.run(finish)
        coord._poll_loop.assert_called_once_with(first_immediate=True)
        # "Synchronise now" loop is started as before, untouched
        coord._companion_app_sync_loop.assert_called_once_with()

    def test_portal_poll_loop_started_with_sleep_first(self) -> None:
        coord = _coord(_portal_entry())
        coord._poll_loop = MagicMock(return_value=None)
        coord.refresh_capabilities = AsyncMock()
        coord.refresh_static_info = AsyncMock()
        coord._refresh_mbb_command_capabilities = AsyncMock()
        coord._ensure_data_act_custom_request_kickoff = AsyncMock()
        client = _client(VehicleData(vin=VIN, battery_soc=88))
        assert _run_setup(coord, client) is True
        finish = coord.hass.async_create_background_task.call_args.args[0]
        asyncio.run(finish)
        coord._poll_loop.assert_called_once_with(first_immediate=False)
