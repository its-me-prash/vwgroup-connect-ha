# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1552 — three companion (ADB) fixes reported by @nekas123 on a VW ID.4.

1. EV entities never appeared even though SoC/range parsed fine: the companion
   channel builds VehicleData without setting ``has_battery``, so the
   ``condition == "electric"`` entity gate hid them. The multi-channel merge
   already infers ``has_battery`` from a present SoC/range, but a single-source
   companion read never reaches that path, so the flag is now set at the source.
2. The nav-read cache was re-applied BEFORE the "is a refresh due?" check, so
   ``_augment_via_nav`` saw every target already populated and skipped the detail
   walk forever after the first read. The refresh now runs first, against the
   true overview state, and the cache only backfills between refreshes.
3. The overnight interval doubling (22:00–05:00) is a cloud-quota saver; it does
   not apply to a local ADB read, EXCEPT that with the wake/sleep opt-in a slower
   night cadence also halves phone-screen wakes. So the doubling is skipped for a
   companion entry only when wake/sleep is off (a dedicated always-awake phone).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.client import CompanionClient
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.const import (
    CONF_COMPANION_WAKE_SLEEP,
    CONF_STRATEGY,
    STRATEGY_COMPANION_ADB,
)
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_VW = PRESETS["volkswagen"]


# --- Fix 1: has_battery inference at the companion source --------------------


class _FakeChannel:
    """Stands in for CompanionChannel: get_status only reads .read() plus two
    getattr-with-default attributes."""

    def __init__(self, fields: dict[str, object] | None) -> None:
        self._fields = fields

    async def read(self) -> dict[str, object] | None:
        return self._fields

    @property
    def writes_enabled(self) -> bool:
        return False

    @property
    def source_data_age_s(self) -> float | None:
        return None


def _client(fields: dict[str, object] | None) -> CompanionClient:
    client = CompanionClient.__new__(CompanionClient)
    client._channel = _FakeChannel(fields)  # type: ignore[assignment]
    client._source_channel = "companion_adb"
    client._last_data = None
    return client


class TestHasBatteryInference:
    @pytest.mark.asyncio
    async def test_soc_present_infers_has_battery(self) -> None:
        data = await _client({"battery_soc": 54, "electric_range_km": 206}).get_status(
            "wvwzzz1jzxw000001"
        )
        assert data.has_battery is True
        assert data.battery_soc == 54

    @pytest.mark.asyncio
    async def test_range_only_still_infers_has_battery(self) -> None:
        data = await _client({"electric_range_km": 206}).get_status("wvwzzz1jzxw000002")
        assert data.has_battery is True

    @pytest.mark.asyncio
    async def test_no_ev_fields_keeps_has_battery_false(self) -> None:
        # #1316-safe: a combustion companion read (no SoC, no e-range) must not
        # gain a phantom battery. Inference is one-directional (only ever True).
        data = await _client({"odometer_km": 1000, "outside_temp": 14}).get_status(
            "wvwzzz1jzxw000003"
        )
        assert data.has_battery is False


# --- Fix 2: the nav refresh runs before the cache backfill -------------------


class _StillTransport:
    """A phone whose overview carries none of the nav targets, so a nav read is
    the only way SoC/range could appear. It never advances; the walk itself is
    spied out, so only connect/foreground/version/dump are exercised."""

    def __init__(self, version: str = "4.3.2") -> None:
        self._version = version
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return self._version

    async def dump_ui(self) -> str:
        # A bare overview with no charge-detail targets on it.
        return (
            '<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
            '<node resource-id="" content-desc="Vehicle is locked" text="" '
            'class="android.widget.TextView" clickable="false" '
            'bounds="[0,0][100,50]" /></hierarchy>'
        )


class TestNavRefreshNotFrozenByCache:
    @pytest.mark.asyncio
    async def test_due_refresh_runs_against_uncached_overview(self) -> None:
        channel = CompanionChannel(
            _StillTransport(),  # type: ignore[arg-type]
            _VW,
            time_fn=lambda: 10_000.0,
            nav_opt_ins={"charge_detail"},
        )
        # (_version_ok, and thus nav_reads_enabled, is resolved inside read() once
        # the transport reports its app version; the "refresh ran" assertion below
        # is what proves the gate opened.)

        # A prior nav read left a value in the cache, and the cadence window has
        # elapsed (last_nav_at is None => due).
        channel._nav_cache = {"battery_soc": 41}

        seen: dict[str, object] = {}

        async def _spy(fields: dict[str, object]) -> None:
            # Record exactly what the refresh sees. With the bug (cache applied
            # first) battery_soc would already be here; the fix runs the refresh
            # first, so it must NOT be.
            seen["called"] = True
            seen["battery_soc_present_at_refresh"] = "battery_soc" in fields

        channel._augment_via_nav = _spy  # type: ignore[assignment]

        fields = await channel.read()

        assert seen.get("called") is True, "a due nav refresh must actually run"
        assert seen.get("battery_soc_present_at_refresh") is False, (
            "the cache must not be applied before the refresh (that is the freeze bug)"
        )
        # The cache still backfills afterwards, so the value survives the poll.
        assert fields is not None and fields.get("battery_soc") == 41


# --- Fix 3: nightly doubling skipped only for an awake companion phone --------


def _coord(data: dict, options: dict | None = None) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = SimpleNamespace(data=data, options=options or {})  # type: ignore[attr-defined]
    return coord


class TestNightlyReductionWakeSleepVariant:
    def test_awake_companion_skips_the_doubling(self) -> None:
        # strategy=companion_adb, wake/sleep absent => dedicated awake phone.
        coord = _coord({CONF_STRATEGY: STRATEGY_COMPANION_ADB})
        assert coord._companion_skips_nightly_reduction() is True

    def test_wake_sleep_companion_keeps_the_doubling(self) -> None:
        coord = _coord(
            {CONF_STRATEGY: STRATEGY_COMPANION_ADB, CONF_COMPANION_WAKE_SLEEP: True}
        )
        assert coord._companion_skips_nightly_reduction() is False

    def test_wake_sleep_via_options_is_honoured(self) -> None:
        # The Options flow writes to entry.options; the toggle must be read
        # options-then-data, exactly like the companion client reads it.
        coord = _coord(
            {CONF_STRATEGY: STRATEGY_COMPANION_ADB},
            {CONF_COMPANION_WAKE_SLEEP: True},
        )
        assert coord._companion_skips_nightly_reduction() is False

    def test_non_companion_entry_keeps_the_doubling(self) -> None:
        coord = _coord({CONF_STRATEGY: "cariad_bff"})
        assert coord._companion_skips_nightly_reduction() is False
