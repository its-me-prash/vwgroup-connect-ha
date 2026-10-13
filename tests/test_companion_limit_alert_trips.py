"""A request-limit alert always trips the companion pause, and the pause and the
command gap are persisted right after every command.

The alert can render about a second after the tap that caused it. Whatever
dump sees it first, a cleanup included, must trip the pause before BACK
closes it, or the next command or automation fires again.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.vag_connect.companion.channel import (
    LIMIT_POWER_BUDGET,
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.climate import ClimateController
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import parse_ui_dump
from custom_components.vag_connect.const import (
    CONF_COMPANION_LAST_WRITE_AT,
    CONF_COMPANION_RATE_LIMIT_UNTIL,
    CONF_STRATEGY,
    STRATEGY_COMPANION_ADB,
)
from tests.test_companion_app_sync import SyncPhone
from tests.test_companion_climate_tile import FakePhone as ClimatePhone

VW = PRESETS["volkswagen"]
WALL = 1_700_000_000.0
LIMIT_TEXT = "Too many requests sent to the vehicle"


def _d(body: str) -> str:
    return f'<?xml version="1.0"?><hierarchy>{body}</hierarchy>'


OVERVIEW = _d(
    '<node resource-id="rangeTile" content-desc="Range overview. Battery range: 300 kilometres. Open details" text="" class="V" '
    'clickable="true" bounds="[0,100][500,300]" />'
)
SHEET = _d(
    '<node resource-id="rangeArcBatterySoc" text="Battery 41 %" content-desc="" class="T" '
    'clickable="false" bounds="[0,0][100,50]" />'
    '<node content-desc="Start charging" text="" class="B" clickable="true" '
    'bounds="[0,400][200,460]" />'
)
ALERT = _d(
    f'<node text="{LIMIT_TEXT}" content-desc="" class="T" clickable="false" '
    'bounds="[0,0][500,80]" />'
)


class SeqPhone:
    """Hands out a fixed sequence of dumps; the last one repeats."""

    connected = True

    def __init__(self, seq):
        self.seq = list(seq)
        self.backs = 0
        self.taps: list[tuple[int, int]] = []

    async def connect(self):
        pass

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return "4.6.4"

    async def dump_ui(self):
        return self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]

    async def key_back(self):
        self.backs += 1

    async def tap(self, x, y):
        self.taps.append((x, y))


def _channel(phone, wall=WALL, now=1000.0):
    return CompanionChannel(phone, VW, time_fn=lambda: now, wall_clock_fn=lambda: wall)


# ── C1: one-tap commands ─────────────────────────────────────────────────────

def test_alert_after_start_charging_trips_and_fails_the_command():
    phone = SeqPhone([OVERVIEW, OVERVIEW, SHEET, SHEET, ALERT, OVERVIEW])
    ch = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        asyncio.run(ch.do_action("start_charging"))
    assert len(phone.taps) == 2  # the tile, then Start charging; nothing more
    assert ch.rate_limited_until == WALL + 12 * 3600
    assert ch.request_state == "restricted"


def test_no_alert_after_start_charging_keeps_writes_open():
    phone = SeqPhone([OVERVIEW, OVERVIEW, SHEET, SHEET, SHEET, SHEET, OVERVIEW])
    ch = _channel(phone)
    asyncio.run(ch.do_action("start_charging"))
    assert ch.rate_limited_until == 0.0


# ── C1: the cleanup helpers ──────────────────────────────────────────────────

def test_return_to_overview_trips_on_an_alert_before_closing_it():
    phone = SeqPhone([ALERT, OVERVIEW])
    ch = _channel(phone)
    asyncio.run(ch._return_to_overview(1))
    assert phone.backs == 1
    assert ch.rate_limited_until == WALL + 12 * 3600


def test_close_dialogs_trips_on_an_alert_before_closing_it():
    phone = SeqPhone([OVERVIEW])
    ch = _channel(phone)
    _nodes, closed = asyncio.run(ch._close_dialogs(parse_ui_dump(ALERT)))
    assert closed and phone.backs == 1
    assert ch.rate_limited_until == WALL + 12 * 3600


def test_the_sync_probe_closes_a_left_over_alert_without_tripping():
    phone = SeqPhone([OVERVIEW])
    ch = _channel(phone)
    _nodes, closed = asyncio.run(ch._close_dialogs(parse_ui_dump(ALERT), trip=False))
    assert closed and ch.rate_limited_until == 0.0


# ── C1: sync_vehicle ─────────────────────────────────────────────────────────

class LateAlertSyncPhone(SyncPhone):
    """The button turns disabled at once; the limit alert follows later."""

    def __init__(self, *, after_dumps: int):
        super().__init__()
        self.after_dumps = after_dumps
        self.tapped_dumps: int | None = None

    async def tap(self, x, y):
        await super().tap(x, y)
        if self.taps[-1] == "sync":
            self.tapped_dumps = 0

    async def dump_ui(self):
        if self.tapped_dumps is not None and self.where == "lower":
            self.tapped_dumps += 1
            if self.tapped_dumps > self.after_dumps:
                self.where = "alert"
                self.limit_alert = LIMIT_TEXT
        return await super().dump_ui()


@pytest.mark.asyncio
async def test_sync_alert_seen_only_by_the_cleanup_keeps_the_pause():
    phone = LateAlertSyncPhone(after_dumps=2)  # past the two settle dumps
    ch = CompanionChannel(phone, VW, time_fn=time.monotonic)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await ch.sync_vehicle()
    assert phone.taps.count("sync") == 1
    assert ch._is_rate_limited()
    assert ch.request_state == "restricted"
    assert phone.where == "overview"


@pytest.mark.asyncio
async def test_sync_probe_does_not_lift_a_pause_the_cleanup_confirms():
    phone = LateAlertSyncPhone(after_dumps=2)
    ch = CompanionChannel(phone, VW, time_fn=time.monotonic)
    ch.restore_rate_limit(time.time() + 3600)
    # Only a power-budget pause lets the sync probe through, and only once its
    # probe is due (a restored pause alone is never probed).
    ch._limit_kind = LIMIT_POWER_BUDGET
    ch._limit_probe_at = 0.0
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await ch.sync_vehicle()
    assert ch._is_rate_limited() and ch.request_state == "restricted"


# ── L6 / B9: the command gap survives a restart ─────────────────────────────

def test_a_command_stamps_the_wall_clock_for_persistence():
    phone = SeqPhone([OVERVIEW, OVERVIEW, SHEET, SHEET, SHEET, SHEET, OVERVIEW])
    ch = _channel(phone)
    asyncio.run(ch.do_action("start_charging"))
    assert ch.last_write_at == WALL


def test_a_restored_recent_write_keeps_the_gap():
    phone = SeqPhone([OVERVIEW])
    ch = _channel(phone)
    ch.restore_last_write(WALL - 20)
    with pytest.raises(CompanionWriteBlocked, match="20s ago"):
        asyncio.run(ch.do_action("start_charging"))
    assert phone.taps == []


def test_a_restored_old_write_does_not_block():
    ch = _channel(SeqPhone([OVERVIEW]))
    ch.restore_last_write(WALL - 600)
    assert ch._last_write_at is None and ch.last_write_at == 0.0


def test_a_restored_write_from_the_future_counts_as_just_now():
    ch = _channel(SeqPhone([OVERVIEW]))
    ch.restore_last_write(WALL + 3600)
    assert ch._last_write_at == 1000.0


# ── H3 / B9: persisted right after the command ───────────────────────────────

def _coord(entry_data, *, until=0.0, last=0.0):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    c.entry.data = dict(entry_data)
    c.hass = MagicMock()
    client = MagicMock()
    client.companion_rate_limited_until = until
    client.companion_last_write_at = last
    c._cariad_client = client
    return c


def _written(c):
    call = c.hass.config_entries.async_update_entry.call_args
    return call.kwargs["data"] if call else None


@pytest.mark.asyncio
async def test_a_command_that_trips_the_limit_is_persisted_without_a_poll():
    c = _coord({CONF_STRATEGY: STRATEGY_COMPANION_ADB}, until=WALL + 43200, last=WALL)
    c.is_read_only = lambda: False
    c._get_command_lock = lambda vin, cls: asyncio.Lock()
    c._dispatch_cmd_locked = AsyncMock(side_effect=RuntimeError("limit"))
    c.async_request_refresh = AsyncMock()
    with pytest.raises(RuntimeError):
        await c._cariad_cmd("VIN", "command_start_charging")
    c.async_request_refresh.assert_not_awaited()
    data = _written(c)
    assert data[CONF_COMPANION_RATE_LIMIT_UNTIL] == WALL + 43200
    assert data[CONF_COMPANION_LAST_WRITE_AT] == WALL


@pytest.mark.asyncio
async def test_read_only_mode_stops_a_command_from_a_control_created_before_it():
    # Read-only Mode applies without a reload, so a control created while the
    # entry was writable can still call in; the dispatch refuses it.
    c = _coord({CONF_STRATEGY: STRATEGY_COMPANION_ADB})
    c.is_read_only = lambda: True
    c._get_command_lock = lambda vin, cls: asyncio.Lock()
    c._dispatch_cmd_locked = AsyncMock()
    with pytest.raises(ServiceValidationError):
        await c._cariad_cmd("VIN", "command_start_charging")
    c._dispatch_cmd_locked.assert_not_awaited()


def test_the_last_write_is_persisted_on_its_own():
    c = _coord(
        {CONF_STRATEGY: STRATEGY_COMPANION_ADB, CONF_COMPANION_LAST_WRITE_AT: WALL - 900},
        last=WALL,
    )
    c._persist_companion_rate_limit()
    assert _written(c)[CONF_COMPANION_LAST_WRITE_AT] == WALL


def test_no_write_this_run_keeps_the_stored_time():
    c = _coord({CONF_STRATEGY: STRATEGY_COMPANION_ADB, CONF_COMPANION_LAST_WRITE_AT: WALL})
    c._persist_companion_rate_limit()
    c.hass.config_entries.async_update_entry.assert_not_called()


def test_other_channels_persist_nothing():
    c = _coord({CONF_STRATEGY: "device_grant_portal"}, until=WALL, last=WALL)
    c._persist_companion_rate_limit()
    c.hass.config_entries.async_update_entry.assert_not_called()


# ── review follow-ups: climate gap, late alerts after the readback ──────────

def _climate(phone, wall):
    ch = CompanionChannel(
        phone, VW, time_fn=time.monotonic, wall_clock_fn=lambda: wall,
        nav_opt_ins={"climate_detail"},
    )

    async def no_sleep(_s):
        return None

    return ch, ClimateController(ch, sleep=no_sleep)


@pytest.mark.asyncio
async def test_a_climate_start_keeps_the_gap_across_a_restart():
    phone = ClimatePhone(layout="pick")
    first, ctrl = _climate(phone, WALL)
    await ctrl.start()
    assert first.last_write_at == WALL
    # HA restarts ten seconds later and restores what was persisted.
    second, ctrl = _climate(phone, WALL + 10)
    second.restore_last_write(first.last_write_at)
    with pytest.raises(CompanionWriteBlocked, match="s ago"):
        await ctrl.stop()
    assert phone.taps.count("stop") == 0 and phone.running == "ac"


def test_an_alert_after_the_readback_still_fails_the_command():
    phone = SeqPhone(
        [OVERVIEW, OVERVIEW, SHEET, SHEET, SHEET, SHEET, SHEET, ALERT, OVERVIEW]
    )
    ch = _channel(phone)
    ch._request_state = "available"  # an earlier sync was accepted
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        asyncio.run(ch.do_action("start_charging"))
    assert len(phone.taps) == 2 and phone.backs == 1
    assert ch.rate_limited_until == WALL + 12 * 3600
    assert ch.request_state == "restricted"


class LateBudgetClimatePhone(ClimatePhone):
    """Start flips the sheet's CTA; the limit alert replaces it a dump later."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.after_start: int | None = None

    def _on_start(self, _):
        self.running = "ac"
        self.after_start = 0

    async def dump_ui(self) -> str:
        if self.after_start is not None and self.screen == "sheet":
            self.after_start += 1
            if self.after_start > 1:
                self.screen = "budget"
        return await super().dump_ui()


@pytest.mark.asyncio
async def test_a_late_alert_after_a_climate_start_fails_the_command():
    phone = LateBudgetClimatePhone(layout="pick")
    ch, ctrl = _climate(phone, WALL)
    ch._request_state = "available"
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await ctrl.start()
    assert phone.taps.count("start") == 1 and phone.screen == "overview"
    assert ch.rate_limited_until == WALL + 12 * 3600
    assert ch.request_state == "restricted"
