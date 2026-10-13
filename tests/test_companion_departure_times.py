# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Departure times screen, read by layout: each row's clock and switch."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import (
    DEPARTURE_TILE,
    find_tile_entry,
    read_departure_timers,
)
from custom_components.vag_connect.companion.screen import UiNode, parse_ui_dump

FIXTURE = Path(__file__).parent / "fixtures" / "companion_departure" / "tiguan_departure.xml"
VW = PRESETS["volkswagen"]
NAV = next(nav for nav in VW.nav_reads if nav.name == "departure_times")


def _tiguan(checked_first: bool = False) -> list[UiNode]:
    xml = FIXTURE.read_text(encoding="utf-8")
    if checked_first:
        xml = xml.replace('checked="false" clickable="true" enabled="true" focusable="true" '
                          'focused="false" scrollable="false" long-clickable="false" '
                          'password="false" selected="false" bounds="[837,711][974,837]"',
                          'checked="true" clickable="true" enabled="true" focusable="true" '
                          'focused="false" scrollable="false" long-clickable="false" '
                          'password="false" selected="false" bounds="[837,711][974,837]"')
    return parse_ui_dump(xml)


def test_tiguan_three_timers_in_24_hour_form():
    assert read_departure_timers(_tiguan()) == {
        "departure_timer_1_enabled": False, "departure_timer_1_time": "07:25",
        "departure_timer_2_enabled": False, "departure_timer_2_time": "00:00",
        "departure_timer_3_enabled": False, "departure_timer_3_time": "00:00",
        "departure_timer_enabled_count": 0,
    }


def test_a_checked_switch_is_an_enabled_timer():
    out = read_departure_timers(_tiguan(checked_first=True))
    assert out["departure_timer_1_enabled"] is True
    assert out["departure_timer_enabled_count"] == 1


def _row(top: int, clock: str, *, meridiem: str | None = None, on: bool = False) -> list[UiNode]:
    row = UiNode("", "", "", "android.view.View", True, (50, top, 1000, top + 200))
    nodes = [row, UiNode("", "", clock, "android.widget.TextView", False, (100, top + 40, 300, top + 140))]
    if meridiem:
        nodes.append(UiNode("", "", meridiem, "android.widget.TextView", False, (310, top + 80, 380, top + 140)))
    nodes.append(UiNode("", "", "", "android.view.View", True, (800, top + 30, 950, top + 160),
                        checkable=True, checked=on))
    return nodes


@pytest.mark.parametrize(("clock", "meridiem", "expected"), [
    ("18:05", None, "18:05"), ("6:05", "PM", "18:05"), ("12:30", "pm", "12:30"),
    ("12:00", "a.m.", "00:00"), ("07.15", None, "07:15"),
])
def test_clock_forms(clock, meridiem, expected):
    out = read_departure_timers(_row(100, clock, meridiem=meridiem, on=True))
    assert out == {"departure_timer_1_enabled": True, "departure_timer_1_time": expected}


def test_rows_without_a_clock_and_impossible_times_are_skipped():
    nodes = _row(100, "Home") + _row(400, "25:00") + _row(700, "13:00", meridiem="PM")
    assert read_departure_timers(nodes) == {}


def test_partial_screen_leaves_the_count_unknown():
    out = read_departure_timers(_row(400, "08:00") + _row(100, "07:00", on=True))
    assert out["departure_timer_1_time"] == "07:00" and out["departure_timer_1_enabled"] is True
    assert out["departure_timer_2_time"] == "08:00"
    assert "departure_timer_enabled_count" not in out


def test_tile_found_by_its_translated_label():
    strings = {DEPARTURE_TILE: {"Abfahrtszeiten"}, "acc_common_hint_details": {"Details öffnen"}}
    tile = UiNode("", "Abfahrtszeiten. Details öffnen", "", "android.view.View", False, (0, 0, 10, 10))
    assert find_tile_entry([tile], strings, DEPARTURE_TILE) is tile


@pytest.mark.asyncio
async def test_walk_runs_only_when_opted_in_and_until_all_six_values_are_known():
    walked = []

    async def fake_walk(path, here=None):
        walked.append(path[0].action)
        return None, 0

    off = CompanionChannel(object(), VW, time_fn=time.monotonic, nav_opt_ins=set())
    off._walk_to_detail = fake_walk
    off._return_to_overview = _noop
    await off._augment_via_nav({})
    assert walked == []

    on = CompanionChannel(object(), VW, time_fn=time.monotonic, nav_opt_ins={"departure_times"})
    on._walk_to_detail = fake_walk
    on._return_to_overview = _noop
    await on._augment_via_nav({})
    assert walked == ["open_departure_times"]
    known = {t: "x" for t in NAV.resource_targets}
    await on._augment_via_nav(known)
    assert walked == ["open_departure_times"]


async def _noop(*_a, **_k):
    return None


def test_repeat_sensors_need_a_companion_value_to_appear() -> None:
    # No cloud parser fills the Repeat switch, so a cloud entry that shows
    # empty entities must not get three permanently unknown sensors.
    from custom_components.vag_connect.binary_sensor import _DATA_PRESENT_REQUIRED

    for n in (1, 2, 3):
        assert f"departure_timer_{n}_repeat" in _DATA_PRESENT_REQUIRED
