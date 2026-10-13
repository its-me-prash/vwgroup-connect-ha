# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Air Conditioning tile: reads grounded in #968 captures (fixtures/sources.json)
and command walks against a fake phone that renders the same layouts."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import (
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.climate import (
    ClimateController,
    read_dial,
    snap_temperature,
)
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import (
    parse_ui_dump,
    read_fields,
    read_selectors,
)

FIXTURES = Path(__file__).parent / "fixtures" / "companion_climate"
VW = PRESETS["volkswagen"]
DETAIL = next(n for n in VW.nav_reads if n.name == "climate_detail")
SETTINGS = next(n for n in VW.nav_reads if n.name == "climate_settings")


# The VW 4.3.2 APK's string table, as the ADB transports read it from the phone.
STRINGS = {
    k: set(v) for k, v in json.loads(
        (Path(__file__).parent / "fixtures" / "companion_battery" / "vw_432_resources.json")
        .read_text(encoding="utf-8")
    ).items()
}


def dump(name: str) -> str:
    return (FIXTURES / (name + ".xml")).read_text(encoding="utf-8")


# ── reads, per contributor capture ───────────────────────────────────────────

@pytest.mark.parametrize(("name", "expected", "absent"), [
    # @gszigethy, Tiguan eHybrid, 4.3.2: picker layout, "Autom." window heating.
    ("tiguan_climate_idle", {
        "climatisation_active": False, "window_heating_front": False,
        "window_heating_enabled": True, "target_temperature": 22.0,
        "outside_temp": 23.0, "climate_remaining_time_min": 0,
    }, ()),
    # @plainmad, Mk8 Golf GTE, 4.3.2 idle: AC toggle checked, CTA Start.
    ("gte_climate_idle", {
        "climatisation_active": False, "window_heating_front": False,
        "target_temperature": 20.0, "outside_temp": 22.0,
    }, ("window_heating_enabled",)),
    # @plainmad, Mk8 Golf GTE, 4.3.2 while active: CTA Stop, AC "Active".
    ("gte_climate_active", {
        "climatisation_active": True, "window_heating_front": False,
        "target_temperature": 20.0,
    }, ("window_heating_enabled",)),
    # @plainmad, Mk8 Golf GTE, We Connect 4.2.1 idle: same ids as on 4.3.2.
    ("gte_421_climate_idle", {
        "climatisation_active": False, "window_heating_front": False,
        "target_temperature": 20.0, "outside_temp": 18.0,
    }, ("window_heating_enabled",)),
    # @kgroshert, ID.4, We Connect 4.2.1 (German): picker layout.
    ("id4_climate", {
        "climatisation_active": False, "target_temperature": 23.0, "outside_temp": 22.0,
    }, ()),
    # @kgroshert, e-up!, We Connect 4.2.1 (German): disabled picker, "Aus".
    ("eup_climate", {
        "climatisation_active": False, "target_temperature": 23.0, "outside_temp": 28.0,
    }, ()),
])
def test_contributor_climate_sheets(name, expected, absent):
    fields = read_selectors(parse_ui_dump(dump(name)), DETAIL.values)
    for key, value in expected.items():
        assert fields[key] == value, key
    for key in absent:
        assert key not in fields


@pytest.mark.parametrize(("name", "active"), [
    ("tiguan_overview", False),          # @gszigethy, 4.3.2
    ("gte_overview_climate_on", True),   # @plainmad, 4.3.2 "Overview Climate On"
    ("id4_overview_de", False),          # @kgroshert, 4.2.1 German "Vorklimatisierung. Aus."
])
def test_overview_tile(name, active):
    assert read_fields(parse_ui_dump(dump(name)), VW)["climatisation_active"] is active


def test_settings_sheet_reads_the_saved_settings():
    # @gszigethy Tiguan, live 4.3.2 climate Settings sheet.
    fields = read_selectors(parse_ui_dump(dump("tiguan_climate_settings")), SETTINGS.values)
    assert fields == {"climate_at_unlock": False, "window_heating_enabled": True}


def test_mode_picker_lists_air_conditioning_then_window_heating():
    # @gszigethy Tiguan, live 4.3.2 "Select mode": the controller chooses by
    # this position and verifies by the row's own title.
    nodes = parse_ui_dump(dump("tiguan_mode_picker"))
    rows = [n for n in nodes if n.checkable and n.clickable]
    assert [r.checked for r in rows] == [True, False]
    titles = [n.text for n in nodes if n.text in ("Air Conditioning", "Window heating")]
    assert titles == ["Air Conditioning", "Window heating"]


def test_settings_path_is_its_own_opt_in():
    assert SETTINGS.opt_in == "climate_settings"
    assert [s.action for s in SETTINGS.path] == ["open_climate_detail", "open_climate_settings"]
    assert SETTINGS.back_presses == 2


def test_fixture_sources_cover_every_fixture():
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    listed = {s["fixture"] for s in sources}
    assert listed == {p.name for p in FIXTURES.glob("*.xml")}
    for s in sources:
        assert s["contributor"] and s["source"].startswith("https://github.com/")


# ── the fake phone ───────────────────────────────────────────────────────────

def _node(rid="", text="", desc="", bounds="[0,0][1,1]", clickable=False,
          checkable=False, checked=False, enabled=True) -> str:
    def b(v: bool) -> str:
        return "true" if v else "false"
    return (
        f'<node index="0" text="{text}" resource-id="{rid}" class="android.view.View" '
        f'package="com.volkswagen.weconnect" content-desc="{desc}" '
        f'checkable="{b(checkable)}" checked="{b(checked)}" clickable="{b(clickable)}" '
        f'enabled="{b(enabled)}" bounds="{bounds}" />'
    )


def _label(value: float) -> str:
    if value == 15.5:
        return "LO"
    if value == 30.0:
        return "HI"
    return str(int(value)) if value == int(value) else str(value)


class FakePhone:
    """Renders overview / sheet / picker / dialog and reacts to taps like the app.

    ``layout`` is "pick" (Tiguan / ID.4) or "toggles" (Mk8 Golf GTE).
    """

    def __init__(self, *, layout="pick", version="4.3.2", temp=22.0, running=None,
                 mode="ac", off_grid=False, dial_locked=False, budget_used=False):
        self.layout = layout
        self._version = version
        self.temp = temp
        self.running = running  # None, "ac", "wh"
        self.mode = mode
        self.ac_toggle, self.wh_toggle = True, False
        self.off_grid = off_grid
        self.dial_locked = dial_locked
        self.budget_used = budget_used
        self.screen = "overview"
        self.connected = True
        self.taps: list[str] = []
        self.bursts: list[int] = []  # one entry per tap_burst shell call
        self.swipes: list[tuple] = []
        self.animating_until = -1.0
        # The app's 1000 ms dial debounce, on a fake clock: a dump takes 1 s,
        # a tap 0.3 s. A change that rests for 1 s, or is pending when the
        # sheet closes or Start is pressed, is one settings request.
        self.clock = 0.0
        self.pending = False
        self.changed_at = 0.0
        self.settings_requests = 0
        self.burst_gaps: list[float] | None = None
        self._targets: list[tuple[tuple[int, int, int, int], str]] = []

    # transport surface
    async def connect(self):
        self.connected = True

    async def foreground_app(self, package):
        return None

    async def current_app_version(self, package):
        return self._version

    def advance(self, seconds: float) -> None:
        self.clock += seconds
        if self.pending and self.clock - self.changed_at >= 1.0:
            self._flush()

    def _flush(self) -> None:
        if self.pending:
            self.settings_requests += 1
            self.pending = False

    async def key_back(self):
        self._flush()
        self.taps.append("BACK")
        self.screen = "sheet" if self.screen == "picker" else "overview"

    async def dump_ui(self) -> str:
        self.advance(1.0)
        return self._render()

    def _render(self) -> str:
        self._targets = []
        body = getattr(self, "_render_" + self.screen)()
        return f'<?xml version="1.0"?><hierarchy rotation="0">{body}</hierarchy>'

    async def tap(self, x, y):
        self.advance(0.3)
        self._hit(x, y)

    def _hit(self, x, y):
        hit = [
            (box, name) for box, name in self._targets
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]
        ]
        if not hit:
            self.taps.append(f"miss@{x},{y}")
            return
        box, name = min(hit, key=lambda h: (h[0][2] - h[0][0]) * (h[0][3] - h[0][1]))
        self.taps.append(name)
        getattr(self, "_on_" + name.split(":")[0])(name)

    async def tap_burst(self, x, y, count):
        # Taps chained like the old dial burst, 315 ms apart. On the real
        # dial a tap starts a 450 ms animation, and a touch during it stops
        # the animation instead of clicking: only the first tap moves it.
        self.bursts.append(count)
        for _ in range(count):
            self.advance(0.315)
            self._render()
            self._hit(x, y)
        return count

    # The dial pager: one step is the distance between two label slots.
    DIAL_PAGE = 441

    async def swipe(self, x1, y1, x2, y2, dur_ms):
        self.swipes.append((x1, y1, x2, y2, dur_ms))
        self.advance(dur_ms / 1000)
        if self.screen != "sheet" or not 1001 <= y1 <= 1322 or self.dial_locked:
            return
        pages = round((x1 - x2) / self.DIAL_PAGE)
        if abs(x1 - x2) * 1000 / dur_ms > 600:
            pages += 1 if pages > 0 else -1  # a fling runs past the target
        if pages:
            self.temp = min(30.0, max(15.5, self.temp + pages * 0.5))
            self.advance(0.45)  # the snap
            self.pending, self.changed_at = True, self.clock

    # rendering
    def _t(self, name, left, top, right, bottom, **kw) -> str:
        self._targets.append(((left, top, right, bottom), name))
        return _node(bounds=f"[{left},{top}][{right},{bottom}]", **kw)

    def _render_overview(self) -> str:
        state = "On" if self.running == "ac" else "Off"
        return (
            _node(rid="rangeTile", bounds="[53,758][508,1204]")
            + _node(desc="Range overview. Battery range: 96 kilometres. Open details",
                    bounds="[53,758][508,1204]")
            + self._t("tile", 572, 758, 1027, 1204, rid="climateTile")
            + _node(desc=f"Climate control. {state}. Open details", bounds="[572,758][1027,1204]")
        )

    def _render_sheet(self) -> str:
        out = self._t("up", 21, 801, 147, 927, rid="vwd_navigation_button", clickable=True)
        out += _node(rid="vwd_title", text="Air Conditioning", bounds="[367,835][713,893]")
        out += _node(text="Somewhere: 23°C", bounds="[464,896][617,941]")
        out += _node(rid="clima_compose_view", bounds="[0,1001][1080,1322]")
        for value, (x0, x1) in ((self.temp - 0.5, (0, 187)), (self.temp, (418, 616)),
                              (self.temp + 0.5, (859, 1080))):
            if 15.5 <= value <= 30.0:
                out += self._t(f"dial:{value}", x0, 1027, x1, 1180, text=_label(value))
        if self.layout == "pick":
            title = "Window heating" if self.mode == "wh" else "Air Conditioning"
            out += self._t("pick", 53, 1427, 1027, 1598, rid="clima_air_conditioning_pick",
                           clickable=not self.running)
            out += _node(rid="title", text=title, bounds="[201,1487][837,1538]")
            if self.running:
                desc = "Active • 10 min" if self.running == "ac" else "Active"
                out += _node(rid="description", text=desc, bounds="[851,1487][974,1538]")
            if self.mode == "ac":
                out += _node(rid="window_heating_title", text="Window heating",
                             bounds="[201,1661][815,1712]")
                out += _node(rid="window_heating_description", text="Autom.",
                             bounds="[836,1661][974,1712]", enabled=False)
        else:
            out += _node(rid="air_conditioning_title", text="Air conditioning",
                         bounds="[163,866][515,899]")
            if self.running:
                ac = "Active" if self.running == "ac" else "Off"
                wh = "Active" if self.running == "wh" else "Off"
                out += _node(rid="air_conditioning_description", text=ac, bounds="[558,866][634,899]")
                out += _node(rid="window_heating_description", text=wh, bounds="[595,1006][634,1039]")
            else:
                out += self._t("toggle:ac", 532, 855, 634, 912, rid="air_conditioning_toggle",
                               clickable=True, checkable=True, checked=self.ac_toggle)
                out += self._t("toggle:wh", 532, 995, 634, 1052, rid="window_heating_toggle",
                               clickable=True, checkable=True, checked=self.wh_toggle)
        if self.running:
            out += self._t("stop", 105, 2004, 975, 2130, rid="cta_stop", text="Stop", clickable=True)
        else:
            enabled = self.layout == "pick" or self.ac_toggle or self.wh_toggle
            out += self._t("start", 105, 2004, 975, 2130, rid="cta_start", text="Start",
                           clickable=True, enabled=enabled)
        return out

    def _render_picker(self) -> str:
        out = self._t("up", 21, 1121, 147, 1247, rid="vwd_navigation_button", clickable=True)
        out += _node(rid="vwd_title", text="Select mode", bounds="[406,1155][673,1213]")
        out += self._t("row:ac", 53, 1300, 1027, 1694, clickable=True, checkable=True,
                       checked=self.mode == "ac")
        out += _node(text="Air Conditioning", bounds="[222,1359][522,1410]")
        out += self._t("row:wh", 53, 1726, 1027, 2014, clickable=True, checkable=True,
                       checked=self.mode == "wh")
        out += _node(text="Window heating", bounds="[222,1785][532,1836]")
        return out

    def _render_budget(self) -> str:
        # The 4.3.2 app's alert (CapabilityStatusAlertDelegateImpl) when the
        # car's daily power budget is used up.
        return (
            _node(text="Too many requests sent to the vehicle", bounds="[53,1300][1027,1400]")
            + _node(text="Please restart the engine and try again.", bounds="[53,1420][1027,1500]")
            + self._t("ok", 53, 1800, 1027, 1900, text="OK", clickable=True)
        )

    def _render_dialog(self) -> str:
        return (
            _node(text="Activate air conditioning using battery?", bounds="[53,1300][1027,1400]")
            + self._t("activate", 53, 1800, 1027, 1900, text="Activate", clickable=True)
            + self._t("cancel", 53, 1950, 1027, 2050, text="Cancel", clickable=True)
        )

    # reactions
    def _on_tile(self, _):
        self.screen = "budget" if self.budget_used else "sheet"

    def _on_up(self, _):
        self._flush()  # closing the sheet sends a pending change
        self.screen = "sheet" if self.screen == "picker" else "overview"

    def _on_pick(self, _):
        self.screen = "picker"

    def _on_row(self, name):
        self.mode = name.split(":")[1]
        self.screen = "sheet"

    def _on_toggle(self, name):
        if name.endswith("ac"):
            self.ac_toggle = not self.ac_toggle
        else:
            self.wh_toggle = not self.wh_toggle

    def _on_dial(self, name):
        if self.clock < self.animating_until:
            return  # a touch during the animation only stops it
        if not self.dial_locked:
            self.temp = float(name.split(":")[1])
            self.animating_until = self.clock + 0.45
            self.pending, self.changed_at = True, self.clock + 0.45

    def _on_start(self, _):
        self._flush()  # Start sends a pending dial value first
        if self.off_grid:
            self.screen = "dialog"
            return
        if self.layout == "pick":
            self.running = self.mode
        else:
            self.running = "ac" if self.ac_toggle else "wh"
        self.screen = "overview"  # the sheet dismisses itself on success

    def _on_stop(self, _):
        self.running = None
        self.screen = "overview"

    def _on_activate(self, _):  # pragma: no cover - must never be pressed
        raise AssertionError("the off-grid confirmation must not be accepted")

    def _on_cancel(self, _):
        self.screen = "overview"


def _controller(phone: FakePhone, now=lambda: 10_000.0, strings=None):
    channel = CompanionChannel(phone, VW, time_fn=now, nav_opt_ins={"climate_detail"})
    # The dial is only walked on a mode the app's own labels confirm.
    channel._app_strings = STRINGS if strings is None else strings

    async def fake_sleep(seconds):
        phone.advance(seconds)

    return channel, ClimateController(channel, sleep=fake_sleep)


# ── commands ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_ac_on_the_picker_layout_taps_start_once_and_returns():
    phone = FakePhone(layout="pick")
    _ch, ctrl = _controller(phone)
    await ctrl.start()
    # Tile, Start, done: the mode picker is not opened for an AC start.
    assert phone.taps == ["tile", "start"]
    assert phone.running == "ac" and phone.screen == "overview"


@pytest.mark.asyncio
async def test_a_command_drops_only_the_climate_values_from_the_cache():
    phone = FakePhone(layout="pick")
    channel, ctrl = _controller(phone)
    channel._nav_cache = {"climatisation_active": False, "battery_soc": 80, "target_temperature": 22.0}
    await ctrl.start()
    assert channel._nav_cache == {"battery_soc": 80, "target_temperature": 22.0}
    assert phone.taps == ["tile", "start"]  # no walk of every opted-in screen


@pytest.mark.asyncio
async def test_start_when_already_running_sends_nothing():
    phone = FakePhone(layout="pick", running="ac")
    _ch, ctrl = _controller(phone)
    await ctrl.start()
    assert "start" not in phone.taps and "stop" not in phone.taps
    assert phone.screen == "overview"


@pytest.mark.asyncio
async def test_window_heating_on_the_picker_layout_selects_the_mode_first():
    phone = FakePhone(layout="pick")
    _ch, ctrl = _controller(phone)
    await ctrl.start(window_heating_only=True)
    assert phone.taps == ["tile", "pick", "row:wh", "start"]
    assert phone.running == "wh"


@pytest.mark.asyncio
async def test_ac_start_restores_the_ac_mode_when_window_heating_was_selected():
    phone = FakePhone(layout="pick", mode="wh")
    _ch, ctrl = _controller(phone)
    await ctrl.start()
    assert phone.taps == ["tile", "pick", "row:ac", "start"]
    assert phone.running == "ac"


@pytest.mark.asyncio
async def test_window_heating_on_the_toggle_layout_sets_both_toggles():
    phone = FakePhone(layout="toggles")
    _ch, ctrl = _controller(phone)
    await ctrl.start(window_heating_only=True)
    assert phone.taps == ["tile", "toggle:ac", "toggle:wh", "start"]
    assert phone.running == "wh"


@pytest.mark.asyncio
async def test_stop_taps_stop():
    phone = FakePhone(layout="toggles", running="ac")
    _ch, ctrl = _controller(phone)
    await ctrl.stop()
    assert phone.taps == ["tile", "stop"]
    assert phone.running is None


@pytest.mark.asyncio
async def test_window_heating_stop_refuses_to_end_running_air_conditioning():
    phone = FakePhone(layout="toggles", running="ac")
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="one Stop"):
        await ctrl.stop(window_heating_only=True)
    assert "stop" not in phone.taps and phone.running == "ac"


@pytest.mark.asyncio
async def test_off_grid_confirmation_is_never_accepted():
    phone = FakePhone(layout="pick", off_grid=True)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="unrecognised screen instead of a confirmation"):
        await ctrl.start()
    assert "activate" not in phone.taps


class _NoticePhone(FakePhone):
    """The tile opens something else: a notification over a screen with a place."""

    def _on_tile(self, _):
        self.screen = "notice"

    def _render_notice(self) -> str:
        return (
            _node(text="Somewhere: 23°C", bounds="[464,896][617,941]")
            + _node(text="Anna: see you at Somewhere Street 5", bounds="[53,100][1027,200]")
        )


@pytest.mark.asyncio
async def test_errors_never_carry_the_screen_text():
    # Maintainer rule 5: places and notification text stay out of errors.
    for phone in (_NoticePhone(layout="pick"), FakePhone(layout="pick", off_grid=True)):
        _ch, ctrl = _controller(phone)
        with pytest.raises(CompanionWriteBlocked) as err:
            await ctrl.start()
        text = str(err.value)
        assert "Somewhere" not in text and "Anna" not in text and "battery?" not in text
        assert "unrecognised screen" in text


@pytest.mark.asyncio
async def test_the_readback_walks_only_the_climate_sheet():
    phone = FakePhone(layout="pick")
    channel, ctrl = _controller(phone)
    await ctrl.start()
    assert channel._nav_only == {"climate_detail"}


class _FrenchPhone(FakePhone):
    """No translation tables, and a mode title in a language the fallback lacks."""

    def _render_sheet(self) -> str:
        return super()._render_sheet().replace(
            'text="Window heating"', 'text="Chauffage des vitres"'
        ).replace('text="Air Conditioning"', 'text="Climatisation"')


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["wh", "ac"])
async def test_an_unrecognised_mode_title_refuses_an_ac_start(mode):
    # The title may be window heating alone: Start would start the wrong thing.
    phone = _FrenchPhone(layout="pick", mode=mode)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="mode is not one this integration recognises"):
        await ctrl.start()
    assert "start" not in phone.taps and "pick" not in phone.taps
    assert phone.running is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("running", "wh_only", "match"), [
    ("wh", False, "window heating is already running"),
    ("ac", True, "air conditioning is already running"),
])
async def test_start_while_the_other_function_runs_says_so_and_sends_nothing(
    running, wh_only, match,
):
    phone = FakePhone(layout="pick", running=running, mode=running)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match=match):
        await ctrl.start(window_heating_only=wh_only)
    assert not any(t in phone.taps for t in ("start", "stop", "pick"))
    assert phone.running == running


@pytest.mark.asyncio
async def test_used_up_request_budget_pauses_commands_with_a_clear_reason():
    # Field test 2026-10-04 (@gszigethy): after a day of testing, tapping the
    # tile showed the app's "Too many requests sent to the vehicle" alert, and
    # the command failed only with "could not open the sheet".
    phone = FakePhone(layout="pick", budget_used=True)
    ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget.*Start the car"):
        await ctrl.start()
    assert phone.taps[0] == "tile" and "start" not in phone.taps
    assert phone.screen == "overview"  # the alert was closed on the way back
    with pytest.raises(CompanionWriteBlocked, match="rate limit"):
        await ctrl.start()
    assert phone.taps.count("tile") == 1


@pytest.mark.asyncio
async def test_other_app_versions_are_never_tapped():
    phone = FakePhone(version="4.2.1")
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="4.3.2"):
        await ctrl.start()
    assert phone.taps == []


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["4.6.4", "4.3.2"])
async def test_verified_builds_start_and_stop(version):
    # 4.6.4 climate sheet dumps carry the same cta_start, clima_compose_view and
    # clima_air_conditioning_pick ids as 4.3.2.
    phone = FakePhone(layout="pick", version=version)
    _ch, ctrl = _controller(phone)
    await ctrl.start()
    assert phone.taps == ["tile", "start"] and phone.running == "ac"
    phone = FakePhone(layout="pick", version=version, running="ac")
    _ch, ctrl = _controller(phone)
    await ctrl.stop()
    assert phone.taps == ["tile", "stop"] and phone.running is None


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["4.4.0", "4.6.3"])
async def test_unlisted_builds_below_4_6_4_are_never_tapped(version):
    phone = FakePhone(version=version)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="4.6.4/4.3.2"):
        await ctrl.start()
    assert phone.taps == []


@pytest.mark.asyncio
async def test_commands_keep_the_minimum_interval():
    phone = FakePhone(layout="pick")
    _ch, ctrl = _controller(phone)
    await ctrl.start()
    with pytest.raises(CompanionWriteBlocked, match="between commands"):
        await ctrl.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "target", "taps", "drags"), [
    (22.0, 23.0, [], 1),                  # two steps: one drag
    (22.0, 21.0, [], 1),
    (22.0, 22.5, ["dial:22.5"], 0),       # one step: one tap
    (16.0, 15.5, ["dial:15.5"], 0),       # LO
    (29.5, 30.0, ["dial:30.0"], 0),       # HI
])
async def test_start_sets_the_dial_reads_it_back_then_starts(start, target, taps, drags):
    phone = FakePhone(temp=start)
    channel, ctrl = _controller(phone)
    await ctrl.start(temp_c=target)
    # The dial is set before Start, never after, with one gesture that
    # settles once, so the app's 1 s debounce sends one request.
    assert phone.taps == ["tile", *taps, "start"]
    assert len(phone.swipes) == drags and phone.bursts == []
    assert phone.temp == target and phone.running == "ac"
    assert phone.settings_requests == 1
    assert channel._nav_cache["target_temperature"] == target


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "target", "x1", "x2"), [
    (21.0, 20.0, 54, 936),    # lower: the dial is dragged to the right
    (20.0, 21.0, 1026, 144),  # higher: to the left
])
async def test_a_drag_is_measured_from_the_dump_and_slow(start, target, x1, x2):
    # Two label slots are 441 px apart on this 1080 px dial; the drag keeps
    # 5 % from the edges and stays at the centre label's height.
    phone = FakePhone(temp=start)
    _ch, ctrl = _controller(phone)
    await ctrl.start(temp_c=target)
    [(sx1, sy1, sx2, sy2, dur)] = phone.swipes
    assert (sx1, sx2) == (x1, x2) and sy1 == sy2 == (1027 + 1180) // 2
    assert abs(sx1 - sx2) * 1000 / dur <= 350  # no fling past the target
    assert phone.temp == target


@pytest.mark.asyncio
async def test_chained_taps_stop_the_dial_after_one_step():
    # Why the dial is dragged: a touch during the step animation stops it.
    phone = FakePhone(temp=21.0)
    _ch, _ctrl = _controller(phone)
    phone.screen = "sheet"
    phone._render()
    await phone.tap_burst(53, 1103, 2)
    assert phone.temp == 20.5


@pytest.mark.asyncio
async def test_start_with_the_dial_already_there_only_taps_start():
    phone = FakePhone(temp=21.5)
    _ch, ctrl = _controller(phone)
    await ctrl.start(temp_c=21.4)  # snaps to 21.5
    assert phone.taps == ["tile", "start"]


@pytest.mark.asyncio
async def test_a_locked_dial_is_reported_not_retried_and_start_is_not_pressed():
    phone = FakePhone(temp=22.0, dial_locked=True)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="landed at 22 °C, not 23 °C"):
        await ctrl.start(temp_c=24.0)
    # The first drag did not move it: the second is never made.
    assert phone.taps == ["tile", "up"] and len(phone.swipes) == 1
    assert phone.running is None


@pytest.mark.asyncio
async def test_start_sets_the_mode_before_the_dial():
    phone = FakePhone(layout="pick", mode="wh", temp=22.0)
    _ch, ctrl = _controller(phone)
    await ctrl.start(temp_c=23.0)
    assert phone.taps == ["tile", "pick", "row:ac", "start"] and len(phone.swipes) == 1
    assert phone.running == "ac" and phone.temp == 23.0


@pytest.mark.asyncio
async def test_window_heating_start_never_touches_the_dial():
    phone = FakePhone(layout="pick", temp=22.0)
    _ch, ctrl = _controller(phone)
    await ctrl.start(window_heating_only=True, temp_c=25.0)
    assert phone.taps == ["tile", "pick", "row:wh", "start"]
    assert phone.temp == 22.0 and phone.running == "wh"


@pytest.mark.asyncio
async def test_a_dial_that_springs_back_aborts_before_start():
    phone = FakePhone(temp=22.0)
    channel = CompanionChannel(phone, VW, time_fn=lambda: 10_000.0,
                               nav_opt_ins={"climate_detail"})
    channel._app_strings = STRINGS

    async def app_reverts(_s):
        phone.temp = 22.0  # the app settles back on the old target

    ctrl = ClimateController(channel, sleep=app_reverts)
    with pytest.raises(CompanionWriteBlocked, match=r"22 °C, not 23 °C.*Start was not pressed"):
        await ctrl.start(temp_c=23.0)
    # Read back once, never corrected: a correcting move is another request.
    assert phone.taps == ["tile", "up"] and len(phone.swipes) == 1
    assert phone.running is None
    assert phone.screen == "overview"


@pytest.mark.asyncio
async def test_a_mode_that_changes_under_the_dial_aborts_before_start():
    phone = FakePhone(layout="pick", temp=22.0)
    channel = CompanionChannel(phone, VW, time_fn=lambda: 10_000.0,
                               nav_opt_ins={"climate_detail"})
    channel._app_strings = STRINGS

    async def mode_flips(_s):
        phone.mode = "wh"

    ctrl = ClimateController(channel, sleep=mode_flips)
    with pytest.raises(CompanionWriteBlocked, match="other than air conditioning.*Start was not pressed"):
        await ctrl.start(temp_c=22.5)
    assert "start" not in phone.taps and phone.running is None


@pytest.mark.asyncio
async def test_toggle_layout_mismatch_aborts_before_start():
    phone = FakePhone(layout="toggles", temp=22.0)
    channel = CompanionChannel(phone, VW, time_fn=lambda: 10_000.0,
                               nav_opt_ins={"climate_detail"})
    channel._app_strings = STRINGS

    async def wh_toggle_on(_s):
        phone.wh_toggle = True

    ctrl = ClimateController(channel, sleep=wh_toggle_on)
    with pytest.raises(CompanionWriteBlocked, match="mode other than air conditioning"):
        await ctrl.start(temp_c=22.5)
    assert "start" not in phone.taps


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "target", "steps", "drags"), [
    (21.0, 20.0, [], 1),  # the reported case: 1 °C is one drag
    (22.0, 21.5, ["dial:21.5"], 0),
])
async def test_adjust_moves_a_running_air_conditioning_dial(start, target, steps, drags):
    phone = FakePhone(layout="pick", running="ac", temp=start)
    channel, ctrl = _controller(phone)
    assert await ctrl.adjust(target) is True
    # Dial only, in one gesture: no Start, no Stop, no mode change.
    assert phone.taps == ["tile", *steps, "up"] and len(phone.swipes) == drags
    assert phone.temp == target and phone.running == "ac"
    assert phone.settings_requests == 1  # the app sends the change once
    assert channel._nav_cache["target_temperature"] == target
    # It is a command: the next one waits the minimum interval.
    with pytest.raises(CompanionWriteBlocked, match="between commands"):
        await ctrl.adjust(start)


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ["pick", "toggles"])
async def test_adjust_leaves_an_idle_climate_alone(layout):
    phone = FakePhone(layout=layout, temp=22.0)
    _ch, ctrl = _controller(phone)
    assert await ctrl.adjust(24.0) is False
    assert not any(t.startswith("dial") for t in phone.taps)
    assert phone.temp == 22.0 and phone.settings_requests == 0


@pytest.mark.asyncio
async def test_adjust_leaves_window_heating_alone():
    # Window heating alone: the app disables the dial; the held value waits.
    phone = FakePhone(layout="pick", running="wh", mode="wh", temp=22.0)
    _ch, ctrl = _controller(phone)
    assert await ctrl.adjust(24.0) is False
    assert not any(t.startswith("dial") for t in phone.taps)
    assert phone.temp == 22.0


@pytest.mark.asyncio
async def test_adjust_on_the_target_sends_nothing():
    phone = FakePhone(layout="pick", running="ac", temp=21.0)
    _ch, ctrl = _controller(phone)
    assert await ctrl.adjust(21.0) is True
    assert not any(t.startswith("dial") for t in phone.taps)
    assert phone.settings_requests == 0


@pytest.mark.asyncio
async def test_adjust_reports_a_dial_that_did_not_land_without_start_wording():
    phone = FakePhone(layout="pick", running="ac", temp=22.0, dial_locked=True)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked) as err:
        await ctrl.adjust(23.0)
    assert "landed at 22 °C" in str(err.value) and "Start" not in str(err.value)
    assert phone.running == "ac"


@pytest.mark.asyncio
async def test_a_running_climate_is_not_re_applied():
    phone = FakePhone(layout="pick", running="ac", temp=22.0)
    _ch, ctrl = _controller(phone)
    await ctrl.start(temp_c=25.0)
    assert not any(t.startswith(("dial", "pick", "row")) for t in phone.taps)
    assert phone.temp == 22.0


def test_snap_to_the_app_grid():
    assert snap_temperature(21.26) == 21.5
    assert snap_temperature(10) == 15.5
    assert snap_temperature(35) == 30.0


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "target"), [(15.5, 30.0), (21.0, 24.0), (24.0, 21.5)])
async def test_a_change_of_more_than_2_degrees_is_refused_before_any_move(start, target):
    # Each drag is a car request: more than two of them is refused.
    phone = FakePhone(temp=start)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="at most 2 °C at a time"):
        await ctrl.start(temp_c=target)
    assert _no_dial_taps(phone) and "start" not in phone.taps
    assert phone.settings_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("landing", [23.5, None])
async def test_a_wrong_landing_is_reported_and_neither_corrected_nor_started(landing):
    phone = FakePhone(temp=22.0)
    channel = CompanionChannel(phone, VW, time_fn=lambda: 10_000.0,
                               nav_opt_ins={"climate_detail"})
    channel._app_strings = STRINGS

    async def overshoots(_s):
        if landing is None:
            phone.dial_locked = True
            phone._render_sheet = lambda: _node(rid="clima_compose_view",
                                                bounds="[0,1001][1080,1322]")
        else:
            phone.temp = landing

    ctrl = ClimateController(channel, sleep=overshoots)
    with pytest.raises(CompanionWriteBlocked, match="landed at .*not 23 °C.*not corrected"):
        await ctrl.start(temp_c=23.0)
    assert len(phone.swipes) == 1 and not any(t.startswith("dial") for t in phone.taps)
    assert "start" not in phone.taps and phone.running is None
    assert channel._last_write_at is not None  # the change counts as a request
    assert phone.settings_requests == 1  # and only one: nothing was corrected


def _no_dial_taps(phone: FakePhone) -> bool:
    return (
        not any(t.startswith("dial") for t in phone.taps)
        and phone.bursts == [] and phone.swipes == []
    )


@pytest.mark.asyncio
async def test_an_unrecognised_mode_refuses_before_any_dial_tap():
    phone = FakePhone(layout="pick", temp=22.0)
    _ch, ctrl = _controller(phone)
    render = phone._render_sheet
    # A mode title in no known language may be window heating alone.
    phone._render_sheet = lambda: render().replace('text="Air Conditioning"', 'text="Mode 1"')
    with pytest.raises(CompanionWriteBlocked, match="mode is not (recognised|one this)"):
        await ctrl.start(temp_c=24.0)
    assert _no_dial_taps(phone) and "start" not in phone.taps


@pytest.mark.asyncio
async def test_a_disabled_start_refuses_before_any_dial_tap():
    phone = FakePhone(layout="toggles", temp=22.0)
    _ch, ctrl = _controller(phone)
    render = phone._render_sheet
    phone._render_sheet = lambda: render().replace(
        'resource-id="cta_start" class="android.view.View" package="com.volkswagen.weconnect" '
        'content-desc="" checkable="false" checked="false" clickable="true" enabled="true"',
        'resource-id="cta_start" class="android.view.View" package="com.volkswagen.weconnect" '
        'content-desc="" checkable="false" checked="false" clickable="true" enabled="false"',
    )
    with pytest.raises(CompanionWriteBlocked, match="Start button is not available"):
        await ctrl.start(temp_c=24.0)
    assert _no_dial_taps(phone)


@pytest.mark.asyncio
async def test_a_limit_alert_on_the_sheet_refuses_before_any_dial_tap():
    phone = FakePhone(temp=22.0)
    channel, ctrl = _controller(phone)
    render = phone._render_sheet
    phone._render_sheet = lambda: render() + _node(
        text="Too many requests sent to the vehicle", bounds="[53,1700][1027,1750]")
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await ctrl.start(temp_c=24.0)
    assert _no_dial_taps(phone) and channel._is_rate_limited()


@pytest.mark.asyncio
async def test_an_active_limit_pause_refuses_before_any_dial_tap():
    phone = FakePhone(temp=22.0)
    channel, ctrl = _controller(phone)
    original = channel._dump_and_clear_overlays

    async def trips_on_the_sheet():
        nodes, cleared = await original()
        if phone.screen == "sheet":
            channel._trip_rate_limit()  # e.g. an alert cleared on the way in
        return nodes, cleared

    channel._dump_and_clear_overlays = trips_on_the_sheet
    with pytest.raises(CompanionWriteBlocked, match="rate limit"):
        await ctrl.start(temp_c=24.0)
    assert _no_dial_taps(phone)


@pytest.mark.asyncio
async def test_a_build_newer_than_the_listed_ones_refuses_before_any_dial_tap():
    # Refused in the gate: not even the tile or the mode picker is tapped.
    phone = FakePhone(version="4.7.0", mode="wh", temp=22.0)
    _ch, ctrl = _controller(phone)
    # (The command gate adds the same pin, with its own message, earlier in the gate.)
    with pytest.raises(CompanionWriteBlocked, match="4.6.4/4.3.2 only|version 4.7.0"):
        await ctrl.start(temp_c=24.0)
    assert phone.taps == [] and phone.bursts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("target", "taps"), [(23.0, None), (22.5, ["dial:22.5"])])
async def test_a_connection_without_drag_refuses_more_than_one_step(target, taps):
    phone = FakePhone(temp=22.0)
    phone.swipe = None  # a transport that cannot drag
    _ch, ctrl = _controller(phone)
    if taps is None:
        with pytest.raises(CompanionWriteBlocked, match="cannot drag the dial"):
            await ctrl.start(temp_c=target)
        assert _no_dial_taps(phone) and "start" not in phone.taps
    else:
        await ctrl.start(temp_c=target)
        assert [t for t in phone.taps if t.startswith("dial")] == taps
        assert phone.running == "ac"


def test_transports_say_whether_they_can_tap_in_one_call():
    from custom_components.vag_connect.companion.addon_transport import AddOnAdbTransport
    from custom_components.vag_connect.companion.relay_transport import AgentRelayTransport
    from custom_components.vag_connect.companion.transport import NetworkAdbTransport

    assert NetworkAdbTransport.can_tap_burst and AddOnAdbTransport.can_tap_burst
    assert not AgentRelayTransport.can_tap_burst


@pytest.mark.asyncio
async def test_the_adb_burst_is_one_shell_call():
    from custom_components.vag_connect.companion import transport as tmod

    sent: list[tuple[str, float]] = []
    t = tmod.NetworkAdbTransport("phone", 5555, "")

    async def shell(cmd, timeout_s=10.0):
        sent.append((cmd, timeout_s))
        return "t\nt\nt\ntaps=3\n"

    t.shell = shell
    real_sleep = tmod.asyncio.sleep
    tmod.asyncio.sleep = lambda _s: real_sleep(0)
    try:
        made = await t.tap_burst(970, 1103, 3)
    finally:
        tmod.asyncio.sleep = real_sleep
    assert len(sent) == 1 and made == 3
    assert "input tap 970 1103" in sent[0][0] and "for i in 0 1 2;" in sent[0][0]


@pytest.mark.skipif(
    not Path("/proc/uptime").exists() or shutil.which("sh") is None,
    reason="needs a POSIX sh and /proc/uptime",
)
@pytest.mark.parametrize(("gaps", "made"), [
    ([0.3] * 5, 5),                       # a normal phone: every tap
    ([0.3, 0.3, 0.9, 0.3, 0.3], 3),       # a late tap: stop after it
    ([1.2, 0.3, 0.3, 0.3, 0.3], 5),       # a slow FIRST tap has nothing pending
])
def test_the_burst_script_stops_after_a_late_tap(tmp_path, gaps, made):
    from custom_components.vag_connect.companion.transport import (
        parse_tap_burst,
        tap_burst_script,
    )

    gap_file = tmp_path / "gaps"
    gap_file.write_text("\n".join(str(g) for g in gaps) + "\n", encoding="utf-8")
    stub = f'exec 3<"{gap_file}"; input() {{ read g <&3; sleep "$g"; }}; '
    out = subprocess.run(
        ["sh", "-c", stub + tap_burst_script(1, 2, len(gaps))],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout
    assert parse_tap_burst(out) == made


@pytest.mark.asyncio
@pytest.mark.parametrize(("target", "drags", "taps", "requests"), [
    (23.0, 2, [], 2),             # 2 °C: two drags, two requests
    (22.5, 1, ["dial:22.5"], 2),  # 1.5 °C: a drag, then a tap
])
async def test_each_dial_move_is_one_settings_request(target, drags, taps, requests):
    phone = FakePhone(temp=21.0)
    _ch, ctrl = _controller(phone)
    await ctrl.start(temp_c=target)
    assert len(phone.swipes) == drags and phone.taps == ["tile", *taps, "start"]
    assert phone.temp == target and phone.running == "ac"
    assert phone.settings_requests == requests


def test_dial_reads_lo_and_hi():
    xml = dump("tiguan_climate_idle").replace('text="21.5"', 'text="LO"')
    value, lower, higher = read_dial(parse_ui_dump(xml))
    assert value == 22.0 and lower.text == "LO" and higher.text == "22.5"


# ── HA surface ───────────────────────────────────────────────────────────────

def test_client_exposes_exactly_the_mapped_climate_commands():
    from custom_components.vag_connect.companion.client import CompanionClient

    client = CompanionClient.__new__(CompanionClient)
    client._brand = "volkswagen"
    for command in ("command_start_climate", "command_stop_climate",
                    "command_start_window_heating", "command_stop_window_heating",
                    "command_set_climate_temperature"):
        assert client.supports_command(command), command
    assert not client.supports_command("command_lock")


class _RecordingController:
    def __init__(self, fail: bool = False):
        self.calls: list[tuple] = []
        self.fail = fail

    async def start(self, **kw):
        self.calls.append(("start", kw))
        if self.fail:
            raise CompanionWriteBlocked("the Start button is not available on the sheet")

    async def stop(self, **kw):
        self.calls.append(("stop", kw))

    async def adjust(self, temp_c):
        self.calls.append(("adjust", {"temp_c": temp_c}))
        return False  # the climate is off: nothing to move


def _client_with(ctrl):
    from custom_components.vag_connect.companion.client import CompanionClient

    client = CompanionClient.__new__(CompanionClient)
    client._brand = "volkswagen"
    client._channel = object()
    client.__dict__["_climate_ctrl"] = ctrl
    return client


@pytest.mark.asyncio
async def test_client_dispatches_each_climate_command_to_the_sheet():
    ctrl = _RecordingController()
    client = _client_with(ctrl)
    await client.command_start_climate("VIN")
    await client.command_start_climate_control("VIN", temp_c=21.0)
    await client.command_stop_climate("VIN")
    await client.command_start_window_heating("VIN")
    await client.command_stop_window_heating("VIN")
    await client.command_set_climate_temperature("VIN", temp_c=21.4)
    held = {"window_heating_only": False, "temp_c": None}
    # The rich start's temp_c becomes the held temperature.
    rich = {"window_heating_only": False, "temp_c": 21.0}
    assert ctrl.calls == [
        ("start", held), ("start", rich), ("stop", {}),
        ("start", {"window_heating_only": True}), ("stop", {"window_heating_only": True}),
        ("adjust", {"temp_c": 21.5}),
    ]
    # Setting the temperature stores it (snapped to the dial's grid) and asks
    # the sheet to move a running climate's dial; this one is off.
    assert client.climate_targets.temp_c == 21.5
    client.store_climate_start_mode(True)
    await client.command_start_climate("VIN")
    assert ctrl.calls[-1] == ("start", {"window_heating_only": True, "temp_c": 21.5})
    # The window-heating command is a one-off override; the held mode stays.
    client.store_climate_start_mode(False)
    await client.command_start_window_heating("VIN")
    assert ctrl.calls[-1] == ("start", {"window_heating_only": True})
    assert client.climate_targets.window_heating_only is False


@pytest.mark.asyncio
async def test_rich_start_refuses_what_the_sheet_cannot_set():
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    ctrl = _RecordingController()
    client = _client_with(ctrl)
    await client.command_start_climate_control("VIN", temp_c=24, ppe_mode=True)
    assert ctrl.calls == [("start", {"window_heating_only": False, "temp_c": 24.0})]
    for field in ("seat_fl", "glass_heating", "climatisation_at_unlock", "climatisation_mode"):
        with pytest.raises(VehicleCommandError, match=field):
            await client.command_start_climate_control("VIN", temp_c=20, **{field: True})
    assert len(ctrl.calls) == 1 and client.climate_targets.temp_c == 24.0


@pytest.mark.asyncio
async def test_a_blocked_sheet_surfaces_as_a_command_error():
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    client = _client_with(_RecordingController(fail=True))
    with pytest.raises(VehicleCommandError, match="Start button"):
        await client.command_start_climate("VIN")


@pytest.mark.asyncio
async def test_coordinator_stores_the_temperature_on_the_companion_client():
    from types import SimpleNamespace

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    ctrl = _RecordingController()
    client = _client_with(ctrl)
    sent: list[tuple] = []
    updates: list[bool] = []

    async def fake_cmd(vin, method, **kwargs):  # pragma: no cover - must not run
        sent.append((vin, method, kwargs))

    coord = SimpleNamespace(
        _cariad_cmd=fake_cmd, _cariad_client=client, is_companion=lambda: True,
        async_update_listeners=lambda: updates.append(True),
        data={"VIN": {"climatisation_active": False}},
    )
    await VagConnectCoordinator.async_set_climatisation_temperature(coord, "VIN", 22.5)
    # Climate off: no command, no refresh (which would read the phone).
    assert sent == [] and ctrl.calls == []
    assert client.climate_targets.temp_c == 22.5 and updates == [True]


@pytest.mark.asyncio
async def test_coordinator_sends_the_temperature_while_the_climate_runs():
    from types import SimpleNamespace

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    client = _client_with(_RecordingController())
    sent: list[tuple] = []

    async def fake_cmd(vin, method, **kwargs):
        sent.append((vin, method, kwargs))

    coord = SimpleNamespace(
        _cariad_cmd=fake_cmd, _cariad_client=client, is_companion=lambda: True,
        async_update_listeners=lambda: None,
        data={"VIN": {"climatisation_active": True}},
    )
    await VagConnectCoordinator.async_set_climatisation_temperature(coord, "VIN", 21.0)
    # Held first, then a command like any other (lock, gates, refresh).
    assert client.climate_targets.temp_c == 21.0
    assert sent == [("VIN", "command_set_climate_temperature", {"temp_c": 21.0})]


@pytest.mark.parametrize(("mode", "expected"), [("ac", False), ("wh", True)])
def test_window_heating_state_while_running(mode, expected):
    # Running in the AC mode: window heating is not on by itself. Running the
    # window-heating mode (picker title): it is.
    import asyncio

    phone = FakePhone(layout="pick", running=mode, mode=mode)
    phone.screen = "sheet"
    fields = read_selectors(parse_ui_dump(asyncio.run(phone.dump_ui())), DETAIL.values)
    assert fields["window_heating_front"] is expected
    assert fields["climatisation_active"] is (mode == "ac")
