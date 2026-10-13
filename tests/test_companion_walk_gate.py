# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Driving data, parking position and Vehicle Health: read when they can have changed.

Driving data and the parking position change only when a trip ends; Vehicle
Health with any data the car sends. The gate skips the walk on other polls,
with a 12 h refresh, a 6 h refresh while the Driving data tile is off the
overview, and a walk on request.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel, _WalkBasis
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import driving_tile_text
from custom_components.vag_connect.companion.screen import parse_ui_dump

FIXTURES = Path(__file__).parent / "fixtures"
OVERVIEW = (FIXTURES / "companion_overview" / "tiguan_overview_locked.xml").read_text(encoding="utf-8")
TILE = ("Driving data. Last driven: 3.0 kilometres. Average consumption: "
        "0 litres per 100 kilometres. Open details")
T0 = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
NAVS = {nav.name: nav for nav in PRESETS["volkswagen"].nav_reads}
H = 3600


def test_the_gated_walks():
    cadence = {name: nav.cadence for name, nav in NAVS.items() if nav.cadence != "poll"}
    assert cadence == {"driving_data": "trip", "parking_position": "trip", "vehicle_health": "car_data",
                       "charging_locations": "trip"}


# ── the Driving data tile ─────────────────────────────────────────────────────

def test_the_tile_is_read_from_the_overview():
    nodes = parse_ui_dump(OVERVIEW)
    assert driving_tile_text(nodes, {}) == TILE
    strings = {"acc_vehicle_tab_label_driving_data": {"Driving data"},
               "acc_common_hint_details": {"Open details"}}
    assert driving_tile_text(nodes, strings) == TILE


def test_no_tile_off_screen():
    assert driving_tile_text(parse_ui_dump(OVERVIEW.replace(TILE, "Departure times. Open details")), {}) is None


# ── the decision ──────────────────────────────────────────────────────────────

class Clock:
    def __init__(self):
        self.now = T0.timestamp()


def _channel(clock):
    return CompanionChannel(object(), PRESETS["volkswagen"], time_fn=lambda: 0.0,
                            wall_clock_fn=lambda: clock.now)


def _walked(channel, name, clock, *, trip=TILE, synced=T0 - timedelta(minutes=30), ranges=(80, 400)):
    channel._walk_basis[name] = _WalkBasis(
        at=clock.now, trip=trip, synced_at=synced, synced_precision_s=60, ranges=ranges)
    channel._trip_tile = channel._trip_tile_now = trip
    channel._seen_at = synced


FIELDS = {"electric_range_km": 80, "combustion_range_km": 400}


@pytest.mark.parametrize("name", ["driving_data", "parking_position", "vehicle_health", "charging_locations"])
def test_first_read_then_nothing_while_nothing_changes(name):
    clock = Clock()
    channel = _channel(clock)
    assert channel._walk_reason(NAVS[name], FIELDS) == "no earlier read"
    _walked(channel, name, clock)
    clock.now += 11 * H
    assert channel._walk_reason(NAVS[name], FIELDS) is None
    clock.now += H
    assert channel._walk_reason(NAVS[name], FIELDS) == "12 h refresh"


@pytest.mark.parametrize("name", ["driving_data", "parking_position", "vehicle_health", "charging_locations"])
def test_a_trip_end_changes_the_tile(name):
    clock = Clock()
    channel = _channel(clock)
    _walked(channel, name, clock)
    channel._trip_tile = channel._trip_tile_now = TILE.replace("3.0", "14.0")
    assert channel._walk_reason(NAVS[name], FIELDS) == "trip ended"


def test_a_tile_off_screen_keeps_the_last_one_seen():
    clock = Clock()
    channel = _channel(clock)
    _walked(channel, "driving_data", clock)
    channel._trip_tile_now = None  # scrolled off; the last seen one stays
    clock.now += 5 * H
    assert channel._walk_reason(NAVS["driving_data"], FIELDS) is None
    clock.now += H
    assert channel._walk_reason(NAVS["driving_data"], FIELDS) == "Driving data tile not on the overview"
    # Vehicle Health does not depend on the tile.
    _walked(channel, "vehicle_health", clock)
    channel._trip_tile_now = None
    clock.now += 6 * H
    assert channel._walk_reason(NAVS["vehicle_health"], FIELDS) is None


def _sync(channel, clock, minutes_ago):
    channel._seen_at = datetime.fromtimestamp(clock.now, tz=timezone.utc) - timedelta(minutes=minutes_ago)


def test_health_reads_new_car_data_once_it_has_settled():
    clock = Clock()
    channel = _channel(clock)
    _walked(channel, "vehicle_health", clock)
    clock.now += H
    _sync(channel, clock, 3)   # the car is still sending (on the move, or a sync)
    assert channel._walk_reason(NAVS["vehicle_health"], FIELDS) is None
    clock.now += 8 * 60
    assert channel._walk_reason(NAVS["vehicle_health"], FIELDS) == "new car data"


def test_a_narrowed_sync_time_is_not_new_data():
    clock = Clock()
    channel = _channel(clock)
    _walked(channel, "vehicle_health", clock)
    clock.now += H
    # Within the line's one-minute rounding: the same sync, read more exactly.
    channel._seen_at = channel._walk_basis["vehicle_health"].synced_at + timedelta(seconds=50)
    assert channel._walk_reason(NAVS["vehicle_health"], FIELDS) is None


@pytest.mark.parametrize("name", ["driving_data", "parking_position", "charging_locations"])
def test_a_trip_walk_needs_a_range_drop_with_the_new_data(name):
    clock = Clock()
    channel = _channel(clock)
    _walked(channel, name, clock)
    clock.now += H
    _sync(channel, clock, 15)
    # An hourly vehicle sync on a parked car: nothing to read.
    assert channel._walk_reason(NAVS[name], FIELDS) is None
    # The same tile, but the range went down: a trip like the last one.
    assert channel._walk_reason(NAVS[name], {**FIELDS, "electric_range_km": 66}) == "range dropped with new car data"
    assert channel._walk_reason(NAVS[name], {**FIELDS, "combustion_range_km": 380}) == "range dropped with new car data"
    # Not while charging, and not without new car data.
    assert channel._walk_reason(NAVS[name], {"electric_range_km": 66, "is_charging": True}) is None
    _sync(channel, clock, 3)
    assert channel._walk_reason(NAVS[name], {**FIELDS, "electric_range_km": 66}) is None


def test_ungated_walks_run_every_poll():
    clock = Clock()
    channel = _channel(clock)
    for name in ("charge_detail", "vehicle_settings", "climate_detail", "departure_times"):
        assert channel._walk_due(NAVS[name], FIELDS)


def test_turning_a_read_off_forgets_its_last_walk():
    clock = Clock()
    channel = _channel(clock)
    _walked(channel, "driving_data", clock)
    _walked(channel, "vehicle_health", clock)
    channel.set_nav_opt_in("driving_data", False)
    assert "driving_data" not in channel._walk_basis
    assert "vehicle_health" in channel._walk_basis


def test_a_requested_refresh_reaches_the_channel():
    from types import SimpleNamespace

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    asked = []
    coordinator = SimpleNamespace(_cariad_client=SimpleNamespace(walk_details_next_read=lambda: asked.append(1)))
    VagConnectCoordinator.companion_walk_details_next(coordinator)
    assert asked == [1]
    VagConnectCoordinator.companion_walk_details_next(SimpleNamespace(_cariad_client=object()))
