# SPDX-License-Identifier: AGPL-3.0-or-later
"""Departure timers: the 4.6.4 timer page read, the list switch and the page edit.

The page fixtures are @gszigethy's 4.6.4 captures (see sources.json). The
fake phone below reacts the way the 4.3.2 APK's EditDepartureTimerViewModel
and Android's spinner TimePicker do: a wheel tap moves one value, minutes past
:55 carry into the hour, hours across 11/12 flip AM/PM, a timer keeps at least
one day, a second day turns Repeat back on, Save and Cancel replace the title
only while something changed, and Save returns to the list.
"""
from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

import pytest

from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
from custom_components.vag_connect.companion.channel import CompanionChannel, CompanionWriteBlocked
from custom_components.vag_connect.companion.client import CompanionClient, _one_off_weekday
from custom_components.vag_connect.companion.departure import (
    WEEKDAYS,
    departure_rows,
    find_toolbar_text,
    page_fields,
    read_timer_page,
)
from custom_components.vag_connect.companion.presets import ACTION_TO_COMMAND, PRESETS
from custom_components.vag_connect.companion.resources import read_departure_timers
from custom_components.vag_connect.companion.screen import parse_ui_dump
from custom_components.vag_connect.companion.transport import CompanionTransportError

FIXTURES = Path(__file__).parent / "fixtures" / "companion_departure"
VW = PRESETS["volkswagen"]


def fixture(name: str):
    return parse_ui_dump((FIXTURES / f"{name}.xml").read_text(encoding="utf-8"))


# -- reading the 4.6.4 captures ---------------------------------------------


@pytest.mark.parametrize(("name", "clock", "days", "repeat"), [
    ("slot1_464", "07:25", ("mon", "tue", "wed", "thu", "fri"), True),
    ("slot2_464", "00:00", ("sat",), False),
    ("slot_onetime_464", "10:50", ("thu",), False),
])
def test_timer_page_reads_time_days_and_repeat(name, clock, days, repeat):
    page = read_timer_page(fixture(name))
    assert page is not None
    assert (page.time, page.weekdays, page.repeat, page.minute_step) == (clock, days, repeat, 5)
    assert page.meridiem_wheel is not None and page.meridiem_wheel.value == "AM"
    assert page_fields(page, 2) == {
        "departure_timer_2_weekdays": ",".join(days), "departure_timer_2_repeat": repeat,
    }


def test_list_and_page_are_told_apart():
    for name in ("list_464", "list_onetime_464", "tiguan_departure"):
        assert read_timer_page(fixture(name)) is None
    for name in ("slot1_464", "slot2_464"):
        assert departure_rows(fixture(name)) == []


def test_one_time_timer_on_the_list():
    out = read_departure_timers(fixture("list_onetime_464"))
    assert out["departure_timer_2_enabled"] is True and out["departure_timer_2_time"] == "10:50"
    assert out["departure_timer_enabled_count"] == 1


def test_row_opens_on_its_time_clear_of_the_switch():
    for row in departure_rows(fixture("list_464")):
        assert row.clock.bounds[2] < row.switch.bounds[0]


def test_save_is_found_only_in_the_toolbar_band():
    nodes = parse_ui_dump(page_xml(7, 25, {"mon"}, True, edit=True))
    page = read_timer_page(nodes)
    assert find_toolbar_text(nodes, {"save"}, page.top).text == "Save"
    assert find_toolbar_text(nodes, {"repeat"}, page.top) is None
    assert find_toolbar_text(fixture("slot1_464"), {"save"}, 457) is None


# -- a phone that behaves like the app ----------------------------------------


def _node(cls, *, rid="", text="", desc="", bounds, clickable=False, checkable=False,
          checked=False, selected=False):
    left, top, right, bottom = bounds
    return (f'<node index="0" text="{text}" resource-id="{rid}" class="{cls}" '
            f'package="com.volkswagen.weconnect" content-desc="{desc}" checkable="{str(checkable).lower()}" '
            f'checked="{str(checked).lower()}" clickable="{str(clickable).lower()}" enabled="true" '
            f'focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" '
            f'selected="{str(selected).lower()}" bounds="[{left},{top}][{right},{bottom}]" />')


_DAY_BOXES = dict(zip(WEEKDAYS, [(53 + i * 145, 1014, 158 + i * 145, 1119) for i in range(7)]))
_DAY_IDS = dict(zip(WEEKDAYS, ["cta_monday", "cta_tuesday", "cta_wednesday", "cta_thursday",
                               "cta_friday", "cta_saturday", "cta_sunday"]))
_DAY_TEXT = dict(zip(WEEKDAYS, ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]))


def page_xml(hour, minute, days, repeat, *, edit=False, h24=False):
    """The Set time page as the 4.6.4 capture lays it out."""
    out = ['<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">',
           _node("android.widget.FrameLayout", bounds=(0, 0, 1080, 2340))]
    if edit:
        out.append(_node("android.widget.Button", text="Cancel", bounds=(22, 82, 250, 208), clickable=True))
        out.append(_node("android.widget.Button", text="Save", bounds=(900, 82, 1058, 208), clickable=True))
    else:
        out.append(_node("android.widget.Button", bounds=(22, 82, 148, 208), clickable=True))
        out.append(_node("android.view.View", desc="Set time", bounds=(137, 116, 943, 173)))
    out.append(_node("android.widget.TimePicker", rid="time_picker", bounds=(53, 457, 1027, 1014)))

    def wheel(left, prev, cur, nxt):
        right = left + 168
        out.append(_node("android.widget.NumberPicker", bounds=(left, 499, right, 972)))
        if prev is not None:
            out.append(_node("android.widget.Button", text=prev, bounds=(left, 499, right, 672), clickable=True))
        out.append(_node("android.widget.EditText", rid="numberpicker_input", text=cur,
                         bounds=(left, 672, right, 798), clickable=True))
        if nxt is not None:
            out.append(_node("android.widget.Button", text=nxt, bounds=(left, 798, right, 972), clickable=True))

    if h24:
        wheel(246, f"{(hour - 1) % 24:02d}", f"{hour:02d}", f"{(hour + 1) % 24:02d}")
    else:
        h12 = hour % 12 or 12
        wheel(246, str((h12 - 2) % 12 + 1), str(h12), str(h12 % 12 + 1))
    out.append(_node("android.widget.TextView", rid="divider", text=":", bounds=(430, 710, 439, 761)))
    wheel(455, f"{(minute - 5) % 60:02d}", f"{minute:02d}", f"{(minute + 5) % 60:02d}")
    if not h24:
        wheel(665, None, "AM", "PM") if hour < 12 else wheel(665, "AM", "PM", None)
    for day in WEEKDAYS:
        out.append(_node("android.widget.Button", rid=_DAY_IDS[day], text=_DAY_TEXT[day],
                         bounds=_DAY_BOXES[day], clickable=True, selected=day in days))
    out.append(_node("android.widget.TextView", rid="repeat_label", text="Repeat", bounds=(222, 1210, 356, 1261)))
    out.append(_node("android.widget.Switch", rid="cta_repeat", text="ON" if repeat else "OFF",
                     bounds=(859, 1172, 985, 1298), clickable=True, checkable=True, checked=repeat))
    out.append("</hierarchy>")
    return "\n".join(out)


def test_the_fake_page_reads_like_the_capture():
    real = read_timer_page(fixture("slot1_464"))
    fake = read_timer_page(parse_ui_dump(page_xml(7, 25, {"mon", "tue", "wed", "thu", "fri"}, True)))
    assert (fake.time, fake.weekdays, fake.repeat, fake.minute_step, fake.top) == (
        real.time, real.weekdays, real.repeat, real.minute_step, real.top)
    for a, b in ((fake.hour_wheel, real.hour_wheel), (fake.minute_wheel, real.minute_wheel)):
        assert (a.value, a.previous.bounds, a.following.bounds) == (b.value, b.previous.bounds, b.following.bounds)


_OVERVIEW = ('<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
             + _node("android.view.View", rid="rangeTile", bounds=(0, 300, 1080, 700))
             + _node("android.view.View", desc="Departure times. Open details",
                     bounds=(0, 800, 1080, 1000), clickable=True)
             + "</hierarchy>")
_LIST = (FIXTURES / "list_464.xml").read_text(encoding="utf-8")
_ROWS = [  # (clock box, meridiem box, switch box) of the three rows in the capture
    ("[106,722][327,825]", "[332,764][394,815]", "[837,711][974,837]"),
    ("[106,964][327,1067]", "[332,1006][394,1057]", "[837,953][974,1079]"),
    ("[106,1206][327,1309]", "[332,1248][394,1299]", "[837,1195][974,1321]"),
]


def _set(xml, bounds, attr, value):
    pattern = re.compile(r'<node [^>]*?bounds="' + re.escape(bounds) + '"[^>]*>')
    return pattern.sub(lambda m: re.sub(f'{attr}="[^"]*"', f'{attr}="{value}"', m.group(0)), xml)


class Timer:
    def __init__(self, hour, minute, days, repeat, enabled=False):
        self.hour, self.minute, self.days, self.repeat, self.enabled = hour, minute, set(days), repeat, enabled

    def copy(self):
        return Timer(self.hour, self.minute, self.days, self.repeat, self.enabled)

    def key(self):
        return (self.hour, self.minute, frozenset(self.days), self.repeat)


class DeparturePhone:
    connected = True

    def __init__(self, *, version="4.6.4", save_fails=False, refuse_switch=False,
                 stuck_wheel=False, h24=False, save_shows=None):
        self.version = version
        self.saved = [Timer(7, 25, {"mon", "tue", "wed", "thu", "fri"}, True),
                      Timer(0, 0, {"sat"}, False), Timer(0, 0, {"sat"}, False)]
        self.where = "overview"
        self.slot = 0
        self.edit: Timer | None = None
        self.save_fails = save_fails
        self.refuse_switch = refuse_switch
        self.refuse_in = 0
        self.stuck_wheel = stuck_wheel
        self.h24 = h24
        self.save_shows = save_shows  # the app saves something else
        self.taps: list[str] = []
        self.backs = 0

    async def connect(self):
        pass

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return self.version

    async def battery_strings(self, package):
        return {}

    def render(self) -> str:
        if self.where == "overview":
            return _OVERVIEW
        if self.where == "page":
            t = self.edit
            return page_xml(t.hour, t.minute, t.days, t.repeat,
                            edit=t.key() != self.saved[self.slot].key(), h24=self.h24)
        xml = _LIST
        for timer, (clock, meridiem, switch) in zip(self.saved, _ROWS):
            h12 = timer.hour % 12 or 12
            xml = _set(xml, clock, "text", f"{h12:02d}:{timer.minute:02d}")
            xml = _set(xml, meridiem, "text", "AM" if timer.hour < 12 else "PM")
            xml = _set(xml, switch, "checked", str(timer.enabled).lower())
        return xml

    async def dump_ui(self):
        if self.where == "list" and self.refuse_in:
            self.refuse_in -= 1
            if not self.refuse_in:
                self.saved[self.slot].enabled = not self.saved[self.slot].enabled
        return self.render()

    def _hit(self, x, y):
        hits = [n for n in parse_ui_dump(self.render())
                if n.clickable and n.bounds and n.bounds[0] <= x <= n.bounds[2] and n.bounds[1] <= y <= n.bounds[3]]
        return min(hits, key=lambda n: (n.bounds[2] - n.bounds[0]) * (n.bounds[3] - n.bounds[1]), default=None)

    async def tap(self, x, y):
        node = self._hit(x, y)
        if self.where == "overview":
            assert node is not None and node.content_desc.startswith("Departure times")
            self.taps.append("tile")
            self.where = "list"
        elif self.where == "list":
            row = next(i for i, (_c, _m, sw) in enumerate(_ROWS) if 711 + 242 * i <= y <= 917 + 242 * i)
            if node is not None and node.checkable:
                self.taps.append(f"switch{row + 1}")
                self.saved[row].enabled = not self.saved[row].enabled
                self.slot = row
                if self.refuse_switch:
                    self.refuse_in = 2
            else:
                self.taps.append(f"open{row + 1}")
                self.where, self.slot, self.edit = "page", row, self.saved[row].copy()
        else:
            self._page_tap(node)

    def _page_tap(self, node):
        t = self.edit
        assert node is not None, "tap on nothing"
        rid = node.resource_id
        if node.text == "Save":
            self.taps.append("save")
            if self.save_fails:
                return
            self.saved[self.slot] = self.save_shows or t.copy()
            self.saved[self.slot].enabled = True
            self.where = "list"
        elif node.text == "Cancel":
            self.taps.append("cancel")
            self.edit = self.saved[self.slot].copy()
        elif rid in _DAY_IDS.values():
            day = next(d for d, r in _DAY_IDS.items() if r == rid)
            self.taps.append(day)
            days = t.days ^ {day}
            if days:  # the app refuses a timer without a day
                t.days = days
                if not t.repeat and len(days) > 1:
                    t.repeat = True
        elif rid == "cta_repeat":
            self.taps.append("repeat")
            t.repeat = not t.repeat
        else:
            self._wheel_tap(node)

    def _wheel_tap(self, node):
        t = self.edit
        left, top = node.bounds[0], node.bounds[1]
        forward = top >= 798
        self.taps.append("wheel")
        if left == 455:  # minutes, 5-minute steps; past :55 carries into the hour
            if self.stuck_wheel:
                return
            minute = (t.minute + (5 if forward else -5)) % 60
            if forward and minute == 0:
                t.hour = (t.hour + 1) % 24
            elif not forward and minute == 55:
                t.hour = (t.hour - 1) % 24
            t.minute = minute
        elif left == 246:
            if self.h24:
                t.hour = (t.hour + (1 if forward else -1)) % 24
                return
            pm = t.hour >= 12
            h12 = t.hour % 12 or 12
            new = h12 % 12 + 1 if forward else (h12 - 2) % 12 + 1
            if {h12, new} == {11, 12}:
                pm = not pm  # Android's spinner flips AM/PM across 11/12
            t.hour = new % 12 + (12 if pm else 0)
        else:  # AM/PM
            t.hour = (t.hour + 12) % 24

    async def key_back(self):
        self.backs += 1
        self.where = {"page": "list", "list": "overview"}.get(self.where, "overview")


def channel_for(phone):
    return CompanionChannel(phone, VW, time_fn=time.monotonic)


def kinds(phone):
    return [t for t in phone.taps if t != "wheel"]


# -- reads ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nav_read_opens_each_page_and_backs_out():
    phone = DeparturePhone()
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic, nav_opt_ins={"departure_times"})
    channel._version_ok = True
    fields: dict[str, object] = {}
    nav = next(n for n in VW.nav_reads if n.name == "departure_times")
    await channel._read_nav_group([nav], fields)
    assert phone.taps == ["tile", "open1", "open2", "open3"]
    assert phone.where == "overview" and phone.backs == 4
    assert fields["departure_timer_1_weekdays"] == "mon,tue,wed,thu,fri"
    assert fields["departure_timer_1_repeat"] is True
    assert fields["departure_timer_2_weekdays"] == "sat" and fields["departure_timer_2_repeat"] is False
    assert fields["departure_timer_3_time"] == "00:00"
    assert all(phone.saved[i].key() == DeparturePhone().saved[i].key() for i in range(3))


# -- the list switch --------------------------------------------------------------


@pytest.mark.asyncio
async def test_switch_on_sends_once_and_is_read_back():
    phone = DeparturePhone()
    channel = channel_for(phone)
    await channel.set_departure_timer(2, enabled=True)
    assert phone.taps == ["tile", "switch2"]
    assert phone.saved[1].enabled is True and phone.where == "overview"
    assert channel._nav_cache["departure_timer_2_enabled"] is True
    with pytest.raises(CompanionWriteBlocked, match="between"):
        await channel.set_departure_timer(2, enabled=False)


@pytest.mark.asyncio
async def test_switch_already_there_sends_nothing():
    phone = DeparturePhone()
    channel = channel_for(phone)
    await channel.set_departure_timer(1, enabled=False)
    assert phone.taps == ["tile"] and channel._last_write_at is None


@pytest.mark.asyncio
async def test_switch_flipped_back_by_the_app_is_a_refusal():
    phone = DeparturePhone(refuse_switch=True)
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="did not accept"):
        await channel.set_departure_timer(3, enabled=True)
    assert phone.saved[2].enabled is False and phone.where == "overview"
    assert "departure_timer_3_enabled" not in channel._nav_cache


@pytest.mark.asyncio
async def test_switch_works_on_432_but_the_page_does_not():
    phone = DeparturePhone(version="4.3.2")
    await channel_for(phone).set_departure_timer(1, enabled=True)
    assert phone.saved[0].enabled is True
    phone = DeparturePhone(version="4.3.2")
    with pytest.raises(CompanionWriteBlocked, match="not mapped for app version 4.3.2"):
        await channel_for(phone).set_departure_timer(1, time="08:00")
    assert phone.taps == []


# -- the timer page ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["07:30", "06:55", "08:00", "11:55", "12:05", "19:40", "00:00", "23:55"])
@pytest.mark.parametrize("h24", [False, True])
async def test_time_is_stepped_saved_and_read_back(target, h24):
    phone = DeparturePhone(h24=h24)
    channel = channel_for(phone)
    channel._nav_cache = {"departure_timer_1_time": "07:25", "odometer_km": 1}
    await channel.set_departure_timer(1, time=target)
    hour, minute = map(int, target.split(":"))
    assert (phone.saved[0].hour, phone.saved[0].minute) == (hour, minute)
    assert phone.saved[0].days == {"mon", "tue", "wed", "thu", "fri"} and phone.saved[0].repeat
    assert kinds(phone) == ["tile", "open1", "save", "open1"]
    assert phone.where == "overview"
    assert channel._nav_cache["departure_timer_1_time"] == target
    assert channel._nav_cache["odometer_km"] == 1


@pytest.mark.asyncio
async def test_days_and_repeat_one_time_timer():
    phone = DeparturePhone()
    await channel_for(phone).set_departure_timer(1, weekdays=["THURSDAY"], repeat=False)
    assert phone.saved[0].days == {"thu"} and phone.saved[0].repeat is False
    # Add before removing, so the app never sees a timer without a day.
    assert kinds(phone) == ["tile", "open1", "mon", "tue", "wed", "fri", "repeat", "save", "open1"]


@pytest.mark.asyncio
async def test_moving_a_one_time_timer_to_another_day():
    # Picking a second day turns Repeat back on in the app; it is turned
    # off again once the old day is gone.
    phone = DeparturePhone()
    phone.saved[2] = Timer(18, 0, {"sat"}, False)  # told apart from timer 2 by its time
    await channel_for(phone).set_departure_timer(2, weekdays=["sun"], repeat=False, time="09:15")
    assert phone.saved[1].key() == (9, 15, frozenset({"sun"}), False)
    assert kinds(phone)[:5] == ["tile", "open2", "sun", "sat", "repeat"]


@pytest.mark.asyncio
async def test_unchanged_page_sends_nothing():
    phone = DeparturePhone()
    channel = channel_for(phone)
    await channel.set_departure_timer(1, time="07:25", weekdays=["mon", "tue", "wed", "thu", "fri"], repeat=True)
    assert kinds(phone) == ["tile", "open1"] and channel._last_write_at is None
    assert phone.where == "overview"


@pytest.mark.asyncio
async def test_time_and_switch_in_one_command():
    phone = DeparturePhone()
    phone.saved[2] = Timer(18, 0, {"sat"}, False)  # told apart from timer 2 by its time
    await channel_for(phone).set_departure_timer(3, time="06:00", enabled=True)
    assert phone.saved[2].hour == 6 and phone.saved[2].enabled is True


@pytest.mark.asyncio
async def test_wheel_that_does_not_move_is_cancelled_unsaved():
    phone = DeparturePhone(stuck_wheel=True)
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="nothing was saved"):
        await channel.set_departure_timer(1, time="07:40", weekdays=["mon"])
    assert "save" not in phone.taps and "cancel" in phone.taps
    assert phone.saved[0].key() == (7, 25, frozenset({"mon", "tue", "wed", "thu", "fri"}), True)
    assert phone.where == "overview" and channel._last_write_at is None


@pytest.mark.asyncio
async def test_unconfirmed_save_fails_without_a_second_save():
    phone = DeparturePhone(save_fails=True)
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="did not confirm"):
        await channel.set_departure_timer(1, time="08:00")
    assert phone.taps.count("save") == 1 and phone.where == "overview"
    assert channel._last_write_at is not None
    assert "departure_timer_1_time" not in channel._nav_cache


@pytest.mark.asyncio
async def test_saved_page_that_differs_is_reported():
    phone = DeparturePhone(save_shows=Timer(8, 0, {"mon"}, True))
    with pytest.raises(CompanionWriteBlocked, match="after saving"):
        await channel_for(phone).set_departure_timer(1, time="08:00")


@pytest.mark.asyncio
@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"time": "07:33"}, "5-minute steps"),
    ({"weekdays": ["mon", "tue"], "repeat": False}, "exactly one weekday"),
    ({"repeat": False}, "exactly one weekday"),  # timer 1 runs Mo-Fr
])
async def test_settings_the_app_cannot_hold_are_refused_before_any_change(kwargs, reason):
    phone = DeparturePhone()
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match=reason):
        await channel.set_departure_timer(1, **kwargs)
    assert kinds(phone) == ["tile", "open1"] and channel._last_write_at is None
    assert phone.where == "overview"


@pytest.mark.asyncio
@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"time": "25:00"}, "not a departure time"),
    ({"weekdays": ["funday"]}, "not a weekday"),
    ({"weekdays": []}, "at least one weekday"),
    ({}, "nothing to set"),
])
async def test_bad_requests_never_touch_the_phone(kwargs, reason):
    phone = DeparturePhone()
    with pytest.raises(CompanionWriteBlocked, match=reason):
        await channel_for(phone).set_departure_timer(1, **kwargs)
    assert phone.taps == []


@pytest.mark.asyncio
async def test_plain_action_path_refuses_the_departure_actions():
    for action in ("toggle_departure_timer", "edit_departure_timer"):
        with pytest.raises(CompanionWriteBlocked, match="set_departure_timer"):
            await channel_for(DeparturePhone()).do_action(action)


# -- the Home Assistant command ---------------------------------------------------


def _client(phone):
    client = CompanionClient(brand="volkswagen", vin="VIN", host="unused", port=5555,
                             adbkey_path="unused", time_fn=time.monotonic)
    client._channel = channel_for(phone)
    return client


def test_both_actions_are_the_departure_timer_command():
    assert ACTION_TO_COMMAND["toggle_departure_timer"] == "command_set_departure_timer"
    assert ACTION_TO_COMMAND["edit_departure_timer"] == "command_set_departure_timer"
    assert _client(DeparturePhone()).supports_command("command_set_departure_timer")


@pytest.mark.asyncio
async def test_command_maps_the_service_fields():
    phone = DeparturePhone()
    await _client(phone).command_set_departure_timer(
        "VIN", timer_id=1, enabled=True, departure_time="2026-10-09T06:30:00",
        recurring_on=["MONDAY", "WEDNESDAY"],
    )
    assert phone.saved[0].key() == (6, 30, frozenset({"mon", "wed"}), True)
    assert phone.saved[0].enabled is True


@pytest.mark.asyncio
async def test_command_refuses_what_the_page_does_not_have():
    phone = DeparturePhone()
    with pytest.raises(VehicleCommandError, match="no charging"):
        await _client(phone).command_set_departure_timer("VIN", timer_id=1, enabled=True,
                                                         departure_time=None, target_soc_pct=80)
    with pytest.raises(VehicleCommandError, match="next\\s+seven days"):
        await _client(phone).command_set_departure_timer("VIN", timer_id=1, enabled=True,
                                                         departure_time=None, one_off_day="1999-01-01")
    assert phone.taps == []


def test_one_off_day_is_the_next_such_weekday():
    today = date(2026, 10, 8)  # a Thursday
    assert _one_off_weekday("2026-10-08", today) == "thu"
    assert _one_off_weekday("2026-10-14", today) == "wed"
    assert _one_off_weekday("2026-10-15", today) is None  # a week on: not expressible
    assert _one_off_weekday("2026-10-07", today) is None
    assert _one_off_weekday("someday", today) is None


def test_fixtures_are_credited():
    import json

    sources = {s["fixture"] for s in json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))}
    for name in ("list_464", "slot1_464", "slot2_464", "list_onetime_464", "slot_onetime_464"):
        assert name + ".xml" in sources


# -- write safety: identity, one send, discard on errors ------------------------


class UnreadableRowPhone(DeparturePhone):
    """Timer 2's clock is unreadable, so a positional row 2 would be timer 3."""

    def render(self) -> str:
        xml = super().render()
        return _set(xml, _ROWS[1][0], "text", "--:--") if self.where == "list" else xml


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"enabled": True}, {"time": "08:00"}, {"weekdays": ["sun"]}])
async def test_write_is_refused_unless_all_three_rows_read(kwargs):
    phone = UnreadableRowPhone()
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="all three"):
        await channel.set_departure_timer(2, **kwargs)
    assert phone.taps == ["tile"] and channel._last_write_at is None
    assert phone.where == "overview"


class WrongPagePhone(DeparturePhone):
    """The row opens a page that is not that row's timer."""

    async def tap(self, x, y):
        await super().tap(x, y)
        if self.where == "page" and self.taps[-1].startswith("open"):
            self.edit = Timer(9, 0, {"sun"}, True)


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"time": "08:00"}, {"weekdays": ["mon"]}, {"repeat": True}])
async def test_page_that_is_not_the_rows_timer_is_not_edited(kwargs):
    phone = WrongPagePhone()
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="does not match"):
        await channel.set_departure_timer(1, **kwargs)
    assert kinds(phone) == ["tile", "open1"] and channel._last_write_at is None
    assert phone.saved[0].key() == DeparturePhone().saved[0].key()
    assert phone.where == "overview"


@pytest.mark.asyncio
async def test_time_on_an_off_timer_is_one_send():
    # The app's Save sends the timer switched on (4.6.4 saveSettings), so the
    # time entity's enabled=True costs no second request.
    phone = DeparturePhone()
    phone.saved[2] = Timer(18, 0, {"sat"}, False)  # told apart from timer 2 by its time
    client = _client(phone)
    client._channel._nav_cache = {"departure_timer_2_enabled": False, "departure_timer_enabled_count": 0}
    await client.command_set_departure_timer("VIN", timer_id=2, enabled=True, departure_time="06:00")
    assert kinds(phone) == ["tile", "open2", "save", "open2"]
    assert phone.saved[1].hour == 6 and phone.saved[1].enabled is True
    assert "departure_timer_2_enabled" not in client._channel._nav_cache
    assert "departure_timer_enabled_count" not in client._channel._nav_cache


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"time": "08:00"}, {"weekdays": ["mon"]}, {"repeat": False}])
async def test_edit_with_switch_off_is_refused_before_any_tap(kwargs):
    # Save switches the timer on; switching it off again would be a second
    # request straight after the first.
    phone = DeparturePhone()
    with pytest.raises(CompanionWriteBlocked, match="switches the timer on"):
        await channel_for(phone).set_departure_timer(1, enabled=False, **kwargs)
    assert phone.taps == []


class DroppingPhone(DeparturePhone):
    """The ADB link drops on the third wheel tap and stays down until reconnected."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.down = False
        self.connects = 0
        self.wheel_taps = 0

    @property
    def connected(self):
        return not self.down

    async def connect(self):
        self.connects += 1
        self.down = False

    async def dump_ui(self):
        if self.down:
            raise CompanionTransportError("link dropped")
        return await super().dump_ui()

    async def tap(self, x, y):
        if self.down:
            raise CompanionTransportError("link dropped")
        if self.where == "page" and self.edit is not None:
            node = self._hit(x, y)
            if node is not None and node.clazz.endswith("Button") and not node.resource_id \
                    and node.text not in ("Save", "Cancel"):
                self.wheel_taps += 1
                if self.wheel_taps == 3:
                    self.down = True
                    raise CompanionTransportError("link dropped")
        await super().tap(x, y)

    async def key_back(self):
        if self.down:
            raise CompanionTransportError("link dropped")
        await super().key_back()


@pytest.mark.asyncio
async def test_transport_error_mid_edit_reconnects_once_and_cancels():
    phone = DroppingPhone()
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="link dropped"):
        await channel.set_departure_timer(1, time="08:00")
    assert phone.connects == 1
    assert "cancel" in phone.taps and "save" not in phone.taps
    assert phone.saved[0].key() == DeparturePhone().saved[0].key()
    assert channel._last_write_at is None


# -- the service: enabled is optional on the companion ----------------------------


def _service_hass(companion: bool):
    import threading
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.vag_connect import _register_services
    from custom_components.vag_connect.const import CONF_STRATEGY, STRATEGY_COMPANION_ADB
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "volkswagen"}
    if companion:
        coord.entry.data[CONF_STRATEGY] = STRATEGY_COMPANION_ADB
    coord.entry.options = {}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = MagicMock()
    coord._cariad_client.command_set_departure_timer = AsyncMock()
    coord._started = True
    coord._was_available = True
    coord.vehicles = {"VIN": {}}
    coord.async_request_refresh = AsyncMock()
    entry = MagicMock()
    entry.runtime_data = coord
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.services.has_service = MagicMock(return_value=False)
    registered: dict = {}

    def _register(domain, name, handler, schema=None, supports_response=None):
        registered[name] = (handler, schema)

    hass.services.async_register = MagicMock(side_effect=_register)
    _register_services(hass)
    return coord, registered["set_departure_timer"]


@pytest.mark.asyncio
async def test_service_without_enabled_on_the_companion_sends_no_switch():
    from unittest.mock import MagicMock

    coord, (handler, schema) = _service_hass(companion=True)
    call = MagicMock()
    call.data = schema({"vin": "VIN", "timer_id": 1, "recurring_on": ["MONDAY"]})
    await handler(call)
    kwargs = coord._cariad_client.command_set_departure_timer.await_args.kwargs
    assert kwargs["enabled"] is None and kwargs["recurring_on"] == ["MONDAY"]
    # Backward compatible: enabled is still accepted.
    assert schema({"vin": "V", "timer_id": 2, "enabled": False})["enabled"] is False


@pytest.mark.asyncio
async def test_service_without_enabled_still_required_on_other_channels():
    from unittest.mock import MagicMock

    from homeassistant.exceptions import ServiceValidationError

    coord, (handler, schema) = _service_hass(companion=False)
    call = MagicMock()
    call.data = schema({"vin": "VIN", "timer_id": 1, "departure_time": "07:30"})
    with pytest.raises(ServiceValidationError):
        await handler(call)
    coord._cariad_client.command_set_departure_timer.assert_not_awaited()


@pytest.mark.asyncio
async def test_days_only_edit_on_the_channel_taps_no_switch():
    phone = DeparturePhone()
    await _client(phone).command_set_departure_timer("VIN", timer_id=1, recurring_on=["MONDAY"])
    assert not any(t.startswith("switch") for t in phone.taps)
    assert phone.saved[0].days == {"mon"}


class SwappedPagePhone(DeparturePhone):
    """Timer 2's row opens timer 3's page; both show 00:00 on the list."""

    async def tap(self, x, y):
        await super().tap(x, y)
        if self.where == "page" and self.taps[-1] == "open2":
            self.slot, self.edit = 2, self.saved[2].copy()


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", [2, 3])
@pytest.mark.parametrize("kwargs", [{"time": "08:00"}, {"weekdays": ["sun"]}, {"repeat": True}])
async def test_timers_with_the_same_time_are_not_edited(slot, kwargs):
    # The page shows no timer number, and its time alone cannot tell timer 2
    # from timer 3, so nothing is opened, let alone saved.
    phone = SwappedPagePhone()
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="same time"):
        await channel.set_departure_timer(slot, **kwargs)
    assert phone.taps == ["tile"] and channel._last_write_at is None
    assert [t.key() for t in phone.saved] == [t.key() for t in DeparturePhone().saved]
    assert phone.where == "overview"


@pytest.mark.asyncio
async def test_the_switch_alone_still_works_on_timers_with_the_same_time():
    phone = SwappedPagePhone()
    await channel_for(phone).set_departure_timer(3, enabled=True)
    assert phone.taps == ["tile", "switch3"] and phone.saved[2].enabled is True
