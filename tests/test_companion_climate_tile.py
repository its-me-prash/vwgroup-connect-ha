# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Air Conditioning tile: reads grounded in #968 captures (fixtures/sources.json)
and command walks against a fake phone that renders the same layouts."""
from __future__ import annotations

import json
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
    sources = json.loads((FIXTURES / "sources.json").read_text())
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
                 mode="ac", off_grid=False, dial_locked=False):
        self.layout = layout
        self._version = version
        self.temp = temp
        self.running = running  # None, "ac", "wh"
        self.mode = mode
        self.ac_toggle, self.wh_toggle = True, False
        self.off_grid = off_grid
        self.dial_locked = dial_locked
        self.screen = "overview"
        self.connected = True
        self.taps: list[str] = []
        self._targets: list[tuple[tuple[int, int, int, int], str]] = []

    # transport surface
    async def connect(self):
        self.connected = True

    async def foreground_app(self, package):
        return None

    async def current_app_version(self, package):
        return self._version

    async def key_back(self):
        self.taps.append("BACK")
        self.screen = "sheet" if self.screen == "picker" else "overview"

    async def dump_ui(self) -> str:
        self._targets = []
        body = getattr(self, "_render_" + self.screen)()
        return f'<?xml version="1.0"?><hierarchy rotation="0">{body}</hierarchy>'

    async def tap(self, x, y):
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

    def _render_dialog(self) -> str:
        return (
            _node(text="Activate air conditioning using battery?", bounds="[53,1300][1027,1400]")
            + self._t("activate", 53, 1800, 1027, 1900, text="Activate", clickable=True)
            + self._t("cancel", 53, 1950, 1027, 2050, text="Cancel", clickable=True)
        )

    # reactions
    def _on_tile(self, _):
        self.screen = "sheet"

    def _on_up(self, _):
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
        if not self.dial_locked:
            self.temp = float(name.split(":")[1])

    def _on_start(self, _):
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


def _controller(phone: FakePhone, now=lambda: 10_000.0):
    channel = CompanionChannel(phone, VW, time_fn=now, nav_opt_ins={"climate_detail"})

    async def no_sleep(_s):
        return None

    return channel, ClimateController(channel, sleep=no_sleep)


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
    channel._last_nav_at = 123.0
    await ctrl.start()
    assert channel._nav_cache == {"battery_soc": 80, "target_temperature": 22.0}
    assert channel._last_nav_at == 123.0  # no walk of every opted-in screen


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
    with pytest.raises(CompanionWriteBlocked, match="another screen"):
        await ctrl.start()
    assert "activate" not in phone.taps


@pytest.mark.asyncio
async def test_other_app_versions_are_never_tapped():
    phone = FakePhone(version="4.2.1")
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="4.3.2"):
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
@pytest.mark.parametrize(("start", "target", "steps"), [
    (22.0, 23.0, ["dial:22.5", "dial:23.0"]),
    (22.0, 21.0, ["dial:21.5", "dial:21.0"]),
    (16.0, 15.5, ["dial:15.5"]),          # LO
    (29.5, 30.0, ["dial:30.0"]),          # HI
])
async def test_set_temperature_steps_the_dial_and_reads_it_back(start, target, steps):
    phone = FakePhone(temp=start)
    channel, ctrl = _controller(phone)
    assert await ctrl.set_temperature(target) == target
    assert phone.taps == ["tile", *steps, "up"]
    assert phone.temp == target and phone.screen == "overview"
    assert channel._nav_cache["target_temperature"] == target


@pytest.mark.asyncio
async def test_set_temperature_already_there_sends_nothing():
    phone = FakePhone(temp=21.5)
    _ch, ctrl = _controller(phone)
    await ctrl.set_temperature(21.4)  # snaps to 21.5
    assert phone.taps == ["tile", "up"]


@pytest.mark.asyncio
async def test_a_locked_dial_is_reported_not_retried():
    phone = FakePhone(temp=22.0, dial_locked=True)
    _ch, ctrl = _controller(phone)
    with pytest.raises(CompanionWriteBlocked, match="did not move"):
        await ctrl.set_temperature(24.0)
    assert phone.taps == ["tile", "dial:22.5", "up"]


def test_snap_to_the_app_grid():
    assert snap_temperature(21.26) == 21.5
    assert snap_temperature(10) == 15.5
    assert snap_temperature(35) == 30.0


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

    async def set_temperature(self, temp_c):
        self.calls.append(("set_temperature", temp_c))
        return temp_c


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
    await client.command_set_climate_temperature("VIN", temp_c=21.5)
    assert ctrl.calls == [
        ("start", {}), ("start", {}), ("stop", {}),
        ("start", {"window_heating_only": True}), ("stop", {"window_heating_only": True}),
        ("set_temperature", 21.5),
    ]


@pytest.mark.asyncio
async def test_a_blocked_sheet_surfaces_as_a_command_error():
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    client = _client_with(_RecordingController(fail=True))
    with pytest.raises(VehicleCommandError, match="Start button"):
        await client.command_start_climate("VIN")


@pytest.mark.asyncio
async def test_coordinator_routes_the_temperature_to_the_companion_client():
    from types import SimpleNamespace

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    ctrl = _RecordingController()
    sent: list[tuple] = []

    async def fake_cmd(vin, method, **kwargs):
        sent.append((vin, method, kwargs))
        await getattr(_client_with(ctrl), method)(vin, **kwargs)

    coord = SimpleNamespace(_cariad_cmd=fake_cmd)
    await VagConnectCoordinator.async_set_climatisation_temperature(coord, "VIN", 22.5)
    assert sent == [("VIN", "command_set_climate_temperature", {"temp_c": 22.5})]
    assert ctrl.calls == [("set_temperature", 22.5)]


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
