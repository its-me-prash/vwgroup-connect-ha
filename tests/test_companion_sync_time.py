# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The overview's "Synchronised … ago" line as the Companion stream's sync time.

The wording per age follows the 4.3.2 toolbar formatter; the strings are the
app's own (fixtures/companion_app_sync/vw_432_sync_strings.json).
"""
from __future__ import annotations

import json
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import extract_app_strings
from custom_components.vag_connect.companion.screen import parse_ui_dump
from custom_components.vag_connect.companion.sync_time import (
    SyncAge,
    find_sync_line,
    parse_sync_line,
)

FIXTURES = Path(__file__).parent / "fixtures" / "companion_app_sync"
STRINGS = {k: set(v) for k, v in json.loads((FIXTURES / "vw_432_sync_strings.json").read_text(encoding="utf-8")).items()}
OVERVIEW = (FIXTURES / "tiguan_overview_synchronised.xml").read_text(encoding="utf-8")
LINE = "Your vehicle: Tiguan. Synchronised 32 minutes ago"
M, H, D = 60, 3600, 86400


# ── the wording, bracket by bracket ───────────────────────────────────────────

@pytest.mark.parametrize(("shown", "age", "precision"), [
    ("Synchronised just now", 0, M),
    ("Synchronised One minute ago", M, M),
    ("Synchronised 32 minutes ago", 32 * M, M),
    ("Synchronised One hour ago", H, M),
    ("Synchronised One hour One minute ago", H + M, M),
    ("Synchronised 2 hours 15 minutes ago", 2 * H + 15 * M, M),
    ("Synchronised 23 hours 59 minutes ago", 23 * H + 59 * M, M),
    ("Synchronised One day ago", D, H),
    ("Synchronised 2 days 3 hours ago", 2 * D + 3 * H, H),
    ("Synchronised 4 days ago", 4 * D, H),
    ("Synchronised 5 days ago", 5 * D, D),
    ("Synchronised 6 days ago", 6 * D, D),
])
def test_every_formatter_bracket(shown, age, precision):
    assert parse_sync_line(f"Your vehicle: Tiguan. {shown}", STRINGS) == SyncAge(age, precision)


@pytest.mark.parametrize("shown", [
    "Synchronised: 12/09/2026",      # older than six days: a date only
    "Data no longer up-to-date",     # older than a year
    "Currently synchronising",       # a sync in progress
    "Range overview. Currently charging. Open details",
    "",
])
def test_lines_without_a_readable_age(shown):
    assert parse_sync_line(f"Your vehicle: Tiguan. {shown}", STRINGS) is None


def test_the_vehicle_name_cannot_fake_an_age():
    # A user can name the car anything; only the frame's own position counts.
    assert parse_sync_line("Your vehicle: 5 minutes. Synchronised 2 hours ago", STRINGS) == SyncAge(2 * H, M)


def test_any_app_language_through_its_own_tables():
    german = {
        "acc_vehicle_tab_value_vehicledata_last_update": {"Vor %s synchronisiert"},
        "acc_vehicle_tab_value_vehicledata_just_now": {"Gerade synchronisiert"},
        "duration_minutes_long_pluralised#one": {"einer Minute"},
        "duration_minutes_long_pluralised#other": {"%s Minuten"},
        "duration_hours_long_pluralised#other": {"%s Stunden"},
    }
    assert parse_sync_line("Dein Fahrzeug: Tiguan. Vor 3 Stunden 5 Minuten synchronisiert", german) == SyncAge(3 * H + 5 * M, M)
    assert parse_sync_line("Vor einer Minute synchronisiert", german) == SyncAge(M, M)
    assert parse_sync_line("Gerade synchronisiert", german) == SyncAge(0, M)
    assert parse_sync_line(LINE, german) is None


def test_without_the_app_tables_the_english_432_wording_is_used():
    nodes = parse_ui_dump(OVERVIEW)
    assert find_sync_line(nodes, {}) == SyncAge(32 * M, M)
    assert find_sync_line(nodes, STRINGS) == SyncAge(32 * M, M)


# ── the app's tables: plurals per quantity ────────────────────────────────────

def _pool(texts):
    body, offsets = b"", []
    for text in texts:
        raw = text.encode("utf-8")
        offsets.append(len(body))
        body += bytes([len(text), len(raw)]) + raw + b"\0"
    body += bytes(-len(body) % 4)
    head = 28 + 4 * len(texts)
    return struct.pack("<HHIIIIII", 1, 28, head + len(body), len(texts), 0, 0x100, head, 0) + b"".join(
        struct.pack("<I", o) for o in offsets) + body


def _plural_table(name, forms):
    # One plurals bag in a minimal standard table; no APK bytes are distributed.
    strings = _pool([text for _q, text in forms])
    types, keys = _pool(["plurals"]), _pool([name])
    entry = struct.pack("<HHIII", 16, 1, 0, 0, len(forms)) + b"".join(
        struct.pack("<IHBBI", quantity, 8, 0, 3, index) for index, (quantity, _t) in enumerate(forms))
    chunk = struct.pack("<HHIBBHII", 0x201, 48, 0, 1, 0, 0, 1, 52) + struct.pack("<I", 28) + bytes(24) + struct.pack("<I", 0) + entry
    chunk = chunk[:4] + struct.pack("<I", len(chunk)) + chunk[8:]
    package = bytearray(288)
    size = len(package) + len(types) + len(keys) + len(chunk)
    struct.pack_into("<HHII", package, 0, 0x200, 288, size, 0x7f)
    struct.pack_into("<I", package, 268, 288)
    struct.pack_into("<I", package, 276, 288 + len(types))
    body = strings + package + types + keys + chunk
    return struct.pack("<HHII", 2, 12, 12 + len(body), 1) + body


def test_plural_bags_are_read_per_quantity():
    table = _plural_table("duration_minutes_long_pluralised", [
        (0x01000005, "Zero minutes"), (0x01000006, "One minute"), (0x01000004, "%s minutes")])
    assert extract_app_strings(table) == {
        "duration_minutes_long_pluralised#zero": {"Zero minutes"},
        "duration_minutes_long_pluralised#one": {"One minute"},
        "duration_minutes_long_pluralised#other": {"%s minutes"},
    }


def test_unrelated_plurals_are_ignored():
    table = _plural_table("some_other_plural", [(0x01000004, "%s things")])
    assert extract_app_strings(table) == {}


# ── the channel: earliest time, forward only ──────────────────────────────────

class OverviewPhone:
    connected = True

    def __init__(self):
        self.line = "Synchronised 32 minutes ago"

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return "4.3.2"

    async def battery_strings(self, package):
        return STRINGS

    async def dump_ui(self):
        return OVERVIEW.replace("Synchronised 32 minutes ago", self.line)


T0 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_reads_close_in_from_below_and_never_go_back():
    phone, clock = OverviewPhone(), [T0.timestamp()]
    channel = CompanionChannel(phone, PRESETS["volkswagen"], time_fn=lambda: 0.0,
                               wall_clock_fn=lambda: clock[0])
    fields = await channel.read()
    # 32 minutes means 32–33 minutes old; the earliest is reported.
    assert fields["companion_app_synced_at"] == T0 - timedelta(minutes=33)
    clock[0] += 5 * M + 30
    phone.line = "Synchronised 37 minutes ago"
    assert (await channel.read())["companion_app_synced_at"] == T0 - timedelta(minutes=32, seconds=30)
    phone.line = "Currently synchronising"
    assert (await channel.read())["companion_app_synced_at"] == T0 - timedelta(minutes=32, seconds=30)
    clock[0] += 4 * M
    phone.line = "Synchronised just now"
    assert (await channel.read())["companion_app_synced_at"] == T0 + timedelta(minutes=8, seconds=30)
    phone.line = "Synchronised 2 hours ago"  # older than recorded: kept newer
    assert (await channel.read())["companion_app_synced_at"] == T0 + timedelta(minutes=8, seconds=30)


@pytest.mark.asyncio
async def test_no_line_no_time():
    phone = OverviewPhone()
    phone.line = "Data no longer up-to-date"
    channel = CompanionChannel(phone, PRESETS["volkswagen"], time_fn=lambda: 0.0,
                               wall_clock_fn=lambda: T0.timestamp())
    assert "companion_app_synced_at" not in await channel.read()


@pytest.mark.asyncio
async def test_the_time_reaches_vehicle_data():
    from custom_components.vag_connect.companion.client import CompanionClient

    client = CompanionClient.__new__(CompanionClient)
    client._brand, client._vin, client._last_data = "volkswagen", "WVWZZZAUZFW805377", None
    client._channel = CompanionChannel(OverviewPhone(), PRESETS["volkswagen"], time_fn=lambda: 0.0,
                                       wall_clock_fn=lambda: T0.timestamp())
    data = await client.get_status(client._vin)
    assert data.companion_app_synced_at == T0 - timedelta(minutes=33)
    assert data.last_seen_at is None  # the cloud streams own last_seen_at


# ── across a restart: the restored time is the floor ──────────────────────────

@pytest.mark.asyncio
async def test_a_restored_time_is_never_put_back_by_the_first_read():
    phone = OverviewPhone()
    channel = CompanionChannel(phone, PRESETS["volkswagen"], time_fn=lambda: 0.0,
                               wall_clock_fn=lambda: T0.timestamp())
    # Before the restart, reads had narrowed it to 32 min 10 s ago; the first
    # read of the new run alone only proves 33 minutes.
    channel.restore_synced_at(T0 - timedelta(minutes=32, seconds=10))
    assert (await channel.read())["companion_app_synced_at"] == T0 - timedelta(minutes=32, seconds=10)
    phone.line = "Synchronised just now"
    assert (await channel.read())["companion_app_synced_at"] == T0 - timedelta(minutes=1)


@pytest.mark.parametrize("restored", [
    T0 + timedelta(hours=1),                       # in the future: a clock step
    (T0 - timedelta(minutes=5)).replace(tzinfo=None),  # no time zone
])
@pytest.mark.asyncio
async def test_a_restored_time_that_cannot_be_right_is_ignored(restored):
    channel = CompanionChannel(OverviewPhone(), PRESETS["volkswagen"], time_fn=lambda: 0.0,
                               wall_clock_fn=lambda: T0.timestamp())
    channel.restore_synced_at(restored)
    assert (await channel.read())["companion_app_synced_at"] == T0 - timedelta(minutes=33)


@pytest.mark.parametrize("stored", [
    "2026-10-05T09:27:50+00:00",                   # from the JSON snapshot
    datetime(2026, 10, 5, 9, 27, 50, tzinfo=timezone.utc),
])
def test_setup_seeds_the_channel_from_the_snapshot(stored):
    from types import SimpleNamespace

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    seeded = []
    coordinator = SimpleNamespace(
        _cariad_client=SimpleNamespace(restore_synced_at=seeded.append),
        vehicles={"VIN1": {"companion_app_synced_at": stored}, "VIN2": {}},
    )
    VagConnectCoordinator._seed_companion_synced_at(coordinator, ["VIN1", "VIN2", "VIN3"])
    assert seeded == [datetime(2026, 10, 5, 9, 27, 50, tzinfo=timezone.utc)]


def test_setup_seeds_nothing_for_a_cloud_client():
    from types import SimpleNamespace

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coordinator = SimpleNamespace(_cariad_client=object(),
                                  vehicles={"VIN1": {"companion_app_synced_at": "2026-10-05T09:27:50+00:00"}})
    VagConnectCoordinator._seed_companion_synced_at(coordinator, ["VIN1"])


# ── new car data ends a request-limit pause ───────────────────────────────────

def _paused_channel(phone, clock):
    from custom_components.vag_connect.companion.channel import _RATE_LIMIT_BACKOFF_S

    channel = CompanionChannel(phone, PRESETS["volkswagen"], time_fn=lambda: 0.0,
                               wall_clock_fn=lambda: clock[0])
    # A pause restored after a restart: its start is the deadline minus 12 h.
    channel.restore_rate_limit(T0.timestamp() + _RATE_LIMIT_BACKOFF_S)
    return channel


@pytest.mark.asyncio
async def test_a_sync_after_the_alert_lifts_the_pause():
    phone, clock = OverviewPhone(), [T0.timestamp() + 3 * H]
    channel = _paused_channel(phone, clock)
    phone.line = "Synchronised 2 hours ago"  # the car was started after the alert
    await channel.read()
    assert channel.rate_limited_until == 0.0
    assert channel.request_state == "available"


@pytest.mark.parametrize("line", [
    "Synchronised 3 hours ago",   # data from before the alert
    "Synchronised 2 hours 59 minutes ago",  # could still be the minute of the alert
    "Currently synchronising",    # no time on screen
])
@pytest.mark.asyncio
async def test_older_or_unknown_car_data_keeps_the_pause(line):
    phone, clock = OverviewPhone(), [T0.timestamp() + 3 * H]
    channel = _paused_channel(phone, clock)
    phone.line = line
    await channel.read()
    assert channel.rate_limited_until > clock[0]
    assert channel.request_state == "restricted"


@pytest.mark.asyncio
async def test_a_restored_sync_time_alone_does_not_lift_the_pause():
    phone, clock = OverviewPhone(), [T0.timestamp() + 3 * H]
    channel = _paused_channel(phone, clock)
    channel.restore_synced_at(T0 + timedelta(hours=1))  # not read off the screen
    assert channel.rate_limited_until > clock[0]


# ── a new trip ends a request-limit pause ─────────────────────────────────────

class TripPhone(OverviewPhone):
    """The overview with a Driving data tile, the line older than the pause."""

    def __init__(self):
        super().__init__()
        self.line = "Synchronised 5 hours ago"
        self.trip: str | None = "Last driven: 11 kilometres."

    async def dump_ui(self):
        xml = await super().dump_ui()
        if self.trip is None:
            return xml
        tile = (
            f'<node index="0" text="" resource-id="" class="android.view.View" package="" '
            f'content-desc="Driving data. {self.trip}" checkable="false" checked="false" '
            f'clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" '
            f'long-clickable="false" password="false" selected="false" bounds="[53,1070][1027,1252]" />'
        )
        return xml.replace("</hierarchy>", tile + "</hierarchy>")


@pytest.mark.asyncio
async def test_a_new_trip_lifts_the_pause():
    phone, clock = TripPhone(), [T0.timestamp() + 3 * H]
    channel = _paused_channel(phone, clock)
    await channel.read()  # the trip as the pause found it
    assert channel._is_rate_limited()
    phone.trip = "Last driven: 4 kilometres."
    await channel.read()
    assert channel.rate_limited_until == 0.0
    assert channel.request_state == "available"


@pytest.mark.asyncio
async def test_the_same_trip_or_no_tile_keeps_the_pause():
    phone, clock = TripPhone(), [T0.timestamp() + 3 * H]
    channel = _paused_channel(phone, clock)
    await channel.read()
    await channel.read()
    phone.trip = None  # tile not on screen
    await channel.read()
    assert channel._is_rate_limited() and channel.request_state == "restricted"


@pytest.mark.asyncio
async def test_a_trip_already_new_on_the_tripping_read_is_the_baseline():
    # The car synced just before the alert: the first read in the pause shows
    # a trip HA had not seen, and that alone must not lift it.
    phone, clock = TripPhone(), [T0.timestamp() + 3 * H]
    channel = CompanionChannel(phone, PRESETS["volkswagen"], time_fn=lambda: 0.0,
                               wall_clock_fn=lambda: clock[0])
    await channel.read()  # before the pause
    from custom_components.vag_connect.companion.channel import _RATE_LIMIT_BACKOFF_S
    channel.restore_rate_limit(clock[0] + _RATE_LIMIT_BACKOFF_S)
    phone.trip = "Last driven: 4 kilometres."
    await channel.read()
    assert channel._is_rate_limited()
