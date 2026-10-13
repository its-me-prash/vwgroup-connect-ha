# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Air Conditioning sheet read by the installed app's own translations.

Labels come from the VW 4.3.2 APK's string table (``vw_432_resources.json``);
the screens are the contributor captures of ``test_companion_climate_tile``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import CompanionWriteBlocked
from custom_components.vag_connect.companion.climate import read_dial
from custom_components.vag_connect.companion.resources import (
    climate_function_state,
    climate_mode_is_window_heating,
    read_climate_resources,
)
from custom_components.vag_connect.companion.screen import parse_ui_dump
from tests.test_companion_climate_tile import FakePhone, _controller, _node, dump

STRINGS = {
    k: set(v) for k, v in json.loads(
        (Path(__file__).parent / "fixtures" / "companion_battery" / "vw_432_resources.json")
        .read_text(encoding="utf-8")
    ).items()
}


def test_idle_tiguan_sheet():
    out = read_climate_resources(parse_ui_dump(dump("tiguan_climate_idle")), STRINGS)
    assert out == {
        "window_heating_enabled": True, "climate_start_mode": "air_conditioning",
        "climate_remaining_time_min": 0,
    }


def test_active_mk8_sheet():
    out = read_climate_resources(parse_ui_dump(dump("gte_climate_active")), STRINGS)
    assert out["climatisation_active"] is True
    assert out["window_heating_front"] is False
    assert "climate_start_mode" not in out  # the toggle layout has no mode row


def test_saved_zone_is_read_from_the_settings_row():
    out = read_climate_resources(parse_ui_dump(dump("tiguan_climate_settings")), STRINGS)
    assert out == {"climate_zone_front_left": True, "climate_zone_front_right": False}


def _settings(value: str | None) -> str:
    body = (
        _node(clickable=True, bounds="[0,918][1080,1270]")
        + _node(text="Zones", bounds="[53,977][166,1028]")
        + _node(text="Zones in your vehicle's interior", bounds="[53,1087][995,1238]")
    )
    if value is not None:
        body += _node(clickable=True, bounds="[799,940][1027,1066]")
        body += _node(text=value, bounds="[799,977][974,1028]")
    return f"<hierarchy>{body}</hierarchy>"


@pytest.mark.parametrize(("value", "expected"), [
    ("Front right", {"climate_zone_front_left": False, "climate_zone_front_right": True}),
    ("2 zones", {"climate_zone_front_left": True, "climate_zone_front_right": True}),
    ("3 zones", {}),
    ("Rear left", {"climate_zone_front_left": False, "climate_zone_front_right": False,
                   "climate_zone_rear_left": True}),
    (None, {"climate_zone_front_left": False, "climate_zone_front_right": False}),
    ("Something new", {}),
])
def test_zones_row_values(value, expected):
    assert read_climate_resources(parse_ui_dump(_settings(value)), STRINGS) == expected


def test_labels_by_resource_and_fallback():
    assert climate_function_state("Active • 10 min", STRINGS) is True
    assert climate_function_state("Off", STRINGS) is False
    assert climate_function_state("Autom.", STRINGS) is None
    assert climate_mode_is_window_heating("Window heating", STRINGS) is True
    assert climate_mode_is_window_heating("Air Conditioning", STRINGS) is False
    # No tables: the German/English patterns still read a German sheet.
    assert climate_function_state("Aus", {}) is False


def test_translated_lo_label():
    xml = dump("tiguan_climate_idle").replace('text="21.5"', 'text="BAS"')
    value, lower, _higher = read_dial(parse_ui_dump(xml), {"clima_temperature_low": {"BAS"}})
    assert value == 22.0 and lower.text == "BAS"


@pytest.mark.asyncio
async def test_window_heating_start_leaves_the_dial_alone():
    phone = FakePhone(temp=22.0, mode="wh")
    channel, ctrl = _controller(phone)
    channel._app_strings = STRINGS
    await ctrl.start(window_heating_only=True, temp_c=24.0)
    assert not any(t.startswith("dial") for t in phone.taps)
    assert phone.running == "wh"


@pytest.mark.asyncio
async def test_a_dial_outside_the_celsius_range_is_never_tapped():
    phone = FakePhone()
    _ch, ctrl = _controller(phone)
    # The fake only draws 15.5-30 labels; draw a °F-looking centre instead.
    phone._render_sheet = lambda: (
        _node(rid="clima_compose_view", bounds="[0,1001][1080,1322]")
        + phone._t("dial:71.5", 0, 1027, 187, 1180, text="71")
        + _node(text="72", bounds="[418,1027][616,1180]")
        + phone._t("start", 105, 2004, 975, 2130, rid="cta_start", text="Start", clickable=True)
    )
    with pytest.raises(CompanionWriteBlocked, match="outside"):
        await ctrl.start(temp_c=22.0)
    assert not any(t.startswith("dial") for t in phone.taps)


@pytest.mark.asyncio
async def test_a_dial_moving_the_wrong_way_is_reported_not_corrected():
    phone = FakePhone(temp=22.0)

    def backwards(_name):
        phone.temp -= 0.5  # the dial moves away from the tapped neighbour

    phone._on_dial = backwards
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="landed at 21.5 °C, not 22.5 °C"):
        await ctrl.start(temp_c=22.5)
    # One tap, one readback; no correcting tap and no Start.
    assert phone.taps == ["tile", "dial:22.5", "up"] and "start" not in phone.taps


@pytest.mark.asyncio
async def test_a_dial_at_lo_with_an_out_of_range_neighbour_is_never_tapped():
    # LO/HI map to 15.5/30 before any range check; a neighbour outside the °C
    # grid still marks the dial as unknown (maintainer rule 3).
    phone = FakePhone()
    channel, ctrl = _controller(phone)
    phone._render_sheet = lambda: (
        _node(rid="clima_compose_view", bounds="[0,1001][1080,1322]")
        + _node(text="LO", bounds="[418,1027][616,1180]")
        + phone._t("dial:61", 859, 1027, 1080, 1180, text="61")
        + phone._t("start", 105, 2004, 975, 2130, rid="cta_start", text="Start", clickable=True)
    )
    with pytest.raises(CompanionWriteBlocked, match="outside the 15.5-30 °C dial"):
        await ctrl.start(temp_c=22.0)
    assert not any(t.startswith(("dial", "start")) for t in phone.taps)
    assert channel._last_write_at is None


@pytest.mark.parametrize(("centre", "neighbour", "expected"), [
    ("LO", "16", 15.5), ("HI", "29.5", 30.0), ("22", "22.5", 22.0), ("BAS", "16", 15.5),
])
def test_target_temperature_reads_the_dial_ends(centre, neighbour, expected):
    from custom_components.vag_connect.companion.channel import CompanionChannel
    from tests.test_companion_climate_tile import DETAIL, VW

    xml = (
        dump("tiguan_climate_idle")
        .replace('text="21.5"', 'text="X"').replace('text="22"', f'text="{centre}"')
        .replace('text="22.5"', f'text="{neighbour}"').replace('text="X"', 'text=""')
    )
    channel = CompanionChannel(FakePhone(), VW, time_fn=lambda: 0.0, nav_opt_ins={"climate_detail"})
    channel._app_strings = {**STRINGS, "clima_temperature_low": {"LO", "BAS"}}
    fields: dict = {}
    channel._apply_nav_values(DETAIL, parse_ui_dump(xml), fields)
    assert fields["target_temperature"] == expected


def test_no_target_temperature_from_a_dial_outside_the_celsius_grid():
    from custom_components.vag_connect.companion.channel import CompanionChannel
    from tests.test_companion_climate_tile import DETAIL, VW

    xml = (
        dump("tiguan_climate_idle").replace('text="21.5"', 'text="71"')
        .replace('text="22"', 'text="72"').replace('text="22.5"', 'text="73"')
    )
    channel = CompanionChannel(FakePhone(), VW, time_fn=lambda: 0.0, nav_opt_ins={"climate_detail"})
    fields: dict = {}
    channel._apply_nav_values(DETAIL, parse_ui_dump(xml), fields)
    assert "target_temperature" not in fields
