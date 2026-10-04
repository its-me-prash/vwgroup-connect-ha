# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Charge limit slider on VW vehicle Settings; see fixtures/sources.json."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
from custom_components.vag_connect.companion.channel import CompanionChannel, CompanionWriteBlocked
from custom_components.vag_connect.companion.charge_target import (
    TARGET_MAX,
    TARGET_MIN,
    find_charge_target_row,
    snap_target,
)
from custom_components.vag_connect.companion.client import CompanionClient
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import find_settings_entry
from custom_components.vag_connect.companion.screen import parse_ui_dump

FIXTURES = Path(__file__).parent / "fixtures" / "companion_battery"
VW = PRESETS["volkswagen"]
STRINGS = {k: set(v) for k, v in json.loads((FIXTURES / "vw_432_resources.json").read_text()).items()}

# The slider's real track on the live phone at three display densities: the
# GradientSlider's own bounds from ``dumpsys activity top``, less Material's
# 18 dp track inset at each end. The slider has no accessibility node, so the
# fixtures hold only its neighbours; these numbers are what they must predict.
TRUE_TRACK = {
    "tiguan_settings": (74 + 18 * 2.625, 850 - 18 * 2.625, 924),
    "tiguan_settings_dpi320": (56 + 18 * 2.0, 904 - 18 * 2.0, 721),
    "tiguan_settings_dpi560": (98 + 18 * 3.5, 774 - 18 * 3.5, 1199),
}


def dump(name: str) -> str:
    return (FIXTURES / (name + ".xml")).read_text()


def slider_value(x: float, track: tuple[float, float, float]) -> int:
    """What the Material slider does with a tap at ``x``: clamp, then snap."""
    start, end, _y = track
    fraction = min(1.0, max(0.0, (x - start) / (end - start)))
    return snap_target(TARGET_MIN + fraction * (TARGET_MAX - TARGET_MIN))


@pytest.mark.parametrize("name", sorted(TRUE_TRACK))
def test_track_is_derived_from_neighbours_at_any_density(name):
    row = find_charge_target_row(parse_ui_dump(dump(name)))
    start, end, y = TRUE_TRACK[name]
    assert row is not None and row.current == 80
    assert abs(row.track_start - start) <= 2 and abs(row.track_end - end) <= 2
    step_px = (end - start) / 5
    for target in range(TARGET_MIN, TARGET_MAX + 1, 10):
        x, tap_y = row.tap_point(target)
        assert tap_y == y
        assert slider_value(x, TRUE_TRACK[name]) == target
        # Well inside the step, not on the edge of the next one.
        assert abs(x - (start + (target - TARGET_MIN) / 50 * (end - start))) < step_px / 10


@pytest.mark.parametrize(("asked", "snapped"), [(80, 80), (73, 70), (75, 80), (45, 50), (10, 50), (120, 100)])
def test_target_snaps_to_what_the_slider_can_hold(asked, snapped):
    assert snap_target(asked) == snapped


def test_other_screens_have_no_charge_target_row():
    for name in ("tiguan_overview", "tiguan_overview_settings", "tiguan_target_reached"):
        assert find_charge_target_row(parse_ui_dump(dump(name))) is None


def test_settings_entry_comes_from_the_installed_translations():
    nodes = parse_ui_dump(dump("tiguan_overview_settings"))
    assert find_settings_entry(nodes, STRINGS).content_desc == "Settings. Open details"
    # A language the code has never seen: only the installed table names it.
    foreign = parse_ui_dump(dump("tiguan_overview_settings").replace(
        "Settings. Open details", "Paramètres. Afficher les détails"))
    labels = {"acc_vehicle_tab_label_settings": {"Paramètres"},
              "acc_common_hint_details": {"Afficher les détails"}}
    assert find_settings_entry(foreign, labels) is not None
    assert find_settings_entry(foreign, STRINGS) is None


_SAVE = ('  <node index="0" text="Save" resource-id="vwd_save_button" class="android.widget.Button" '
         'package="com.volkswagen.weconnect" content-desc="" checkable="false" checked="false" '
         'clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" '
         'long-clickable="false" password="false" selected="false" bounds="[860,100][1059,190]" />\n')
_SYNC = ('  <node index="0" text="Synchronising ..." resource-id="vwd_progress_text" '
         'class="android.widget.TextView" package="com.volkswagen.weconnect" content-desc="" '
         'checkable="false" checked="false" clickable="false" enabled="true" focusable="false" '
         'focused="false" scrollable="false" long-clickable="false" password="false" selected="false" '
         'bounds="[400,116][700,174]" />\n')
_NOTE = ("<?xml version='1.0' encoding='utf-8'?>\n<hierarchy rotation=\"0\">\n"
         '  <node index="0" text="The optimal value of the Battery Care Mode is 80%." resource-id="" '
         'class="android.widget.TextView" package="com.volkswagen.weconnect" content-desc="" '
         'checkable="false" checked="false" clickable="false" enabled="true" focusable="false" '
         'focused="false" scrollable="false" long-clickable="false" password="false" selected="false" '
         'bounds="[53,900][1027,1100]" />\n</hierarchy>\n')


class SettingsPhone:
    """Overview → Settings, reacting like the 4.3.2 APK.

    A slider tap only changes the shown value and enters edit mode; Save
    sends, shows "Synchronising ..." and leaves edit mode; the toolbar's X
    cancels an unsaved change and its arrow goes back.
    """

    connected = True

    def __init__(self, *, saved=80, settings="tiguan_settings", version="4.3.2",
                 care_note=False, sync_dumps=1, drift_px=0.0, strings=STRINGS,
                 limit_alert=None):
        self.version = version
        self.settings_xml = dump(settings)
        self.track = TRUE_TRACK[settings]
        self.saved = saved
        self.shown = saved
        self.where = "overview"
        self.edit = False
        self.care_note = care_note
        self.sync_left = 0
        self.sync_dumps = sync_dumps
        self.drift_px = drift_px  # a layout the derivation did not foresee
        self.strings = strings
        self.limit_alert = limit_alert  # the app's alert instead of Settings
        self.taps: list[tuple[str, int, int]] = []
        self.backs = 0

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return self.version

    async def battery_strings(self, package):
        return self.strings

    async def dump_ui(self):
        return self._render(consume=True)

    def _render(self, *, consume: bool) -> str:
        if self.where == "overview":
            return dump("tiguan_overview_settings")
        if self.where == "note":
            return _NOTE
        if self.where == "alert":
            return _NOTE.replace("The optimal value of the Battery Care Mode is 80%.", self.limit_alert)
        xml = self.settings_xml.replace('text="80%"', f'text="{self.shown}%"')
        extra = ""
        if self.sync_left:
            extra = _SYNC
            if consume:
                self.sync_left -= 1
                if not self.sync_left:
                    self.saved, self.edit = self.shown, False
        elif self.edit:
            extra = _SAVE
        return xml.replace("</hierarchy>", extra + "</hierarchy>")

    def _hit(self, rid_or_desc, x, y):
        for node in parse_ui_dump(self.last):
            if rid_or_desc in (node.resource_id, node.content_desc) and node.bounds:
                left, top, right, bottom = node.bounds
                if left <= x <= right and top <= y <= bottom:
                    return True
        return False

    async def tap(self, x, y):
        self.last = self._render(consume=False)
        if self.where == "overview" and self._hit("Settings. Open details", x, y):
            self.taps.append(("settings", x, y))
            self.where = "alert" if self.limit_alert else "settings"
        elif self.where == "settings" and self._hit("vwd_save_button", x, y):
            self.taps.append(("save", x, y))
            self.sync_left = self.sync_dumps
        elif self.where == "settings" and self._hit("vwd_navigation_button", x, y):
            self.taps.append(("toolbar", x, y))
            if self.edit:
                self.edit, self.shown = False, self.saved  # cancel
            else:
                self.where = "overview"
        elif self.where == "settings" and abs(y - self.track[2]) <= 20:
            self.taps.append(("slider", x, y))
            self.shown = slider_value(x + self.drift_px, self.track)
            self.edit = self.shown != self.saved
            if self.care_note and self.shown > 80:
                self.care_note, self.where = False, "note"
        else:
            self.taps.append(("miss", x, y))

    async def key_back(self):
        self.backs += 1
        self.where = "settings" if self.where == "note" else "overview"


def channel_for(phone):
    return CompanionChannel(phone, VW, time_fn=time.monotonic)


def kinds(phone):
    return [kind for kind, _x, _y in phone.taps]


@pytest.mark.asyncio
async def test_set_target_taps_slider_saves_and_returns():
    phone = SettingsPhone()
    channel = channel_for(phone)
    channel._nav_cache = {"target_soc": 80, "odometer_km": 307}
    assert await channel.set_charge_target(60) == 60
    assert kinds(phone) == ["settings", "slider", "save", "toolbar"]
    assert phone.saved == 60 and phone.where == "overview" and phone.backs == 0
    assert channel._nav_cache == {"target_soc": 60, "odometer_km": 307}
    with pytest.raises(CompanionWriteBlocked, match="between"):
        await channel.set_charge_target(70)


@pytest.mark.asyncio
@pytest.mark.parametrize("settings", sorted(TRUE_TRACK))
async def test_every_step_at_every_density(settings):
    for target in range(TARGET_MIN, TARGET_MAX + 1, 10):
        phone = SettingsPhone(settings=settings, saved=80)
        assert await channel_for(phone).set_charge_target(target) == target
        assert phone.saved == target


@pytest.mark.asyncio
async def test_current_value_sends_nothing():
    phone = SettingsPhone(saved=80)
    channel = channel_for(phone)
    assert await channel.set_charge_target(78) == 80
    assert kinds(phone) == ["settings", "toolbar"]
    assert channel._last_write_at is None


@pytest.mark.asyncio
async def test_slider_readback_corrects_a_drifted_layout():
    # One full step of drift: the first tap shows the wrong value, the read
    # back sees it, and the corrected tap lands before anything is saved.
    phone = SettingsPhone(saved=50, drift_px=136)
    assert await channel_for(phone).set_charge_target(70) == 70
    assert kinds(phone) == ["settings", "slider", "slider", "save", "toolbar"]


@pytest.mark.asyncio
async def test_slider_that_never_reaches_target_is_cancelled_unsaved():
    phone = SettingsPhone(saved=50, drift_px=-2000)  # every tap lands on 50
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="nothing was saved"):
        await channel.set_charge_target(90)
    assert "save" not in kinds(phone)
    assert phone.saved == 50 and phone.where == "overview"
    assert channel._last_write_at is None  # nothing was sent


@pytest.mark.asyncio
async def test_battery_care_note_is_closed_then_saved():
    phone = SettingsPhone(saved=80, care_note=True)
    assert await channel_for(phone).set_charge_target(100) == 100
    assert phone.backs == 1
    assert kinds(phone) == ["settings", "slider", "save", "toolbar"]


@pytest.mark.asyncio
async def test_unconfirmed_save_fails_and_backs_out():
    phone = SettingsPhone(sync_dumps=10_000)
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="did not confirm"):
        await channel.set_charge_target(60)
    assert channel._last_write_at is not None  # Save was pressed: no repeat
    assert "target_soc" not in channel._nav_cache


@pytest.mark.asyncio
async def test_other_app_version_is_refused_before_any_tap():
    phone = SettingsPhone(version="4.3.3")
    with pytest.raises(CompanionWriteBlocked, match="app version"):
        await channel_for(phone).set_charge_target(60)
    assert phone.taps == []


@pytest.mark.asyncio
async def test_unknown_language_reaches_settings_through_resources():
    phone = SettingsPhone(strings={"acc_vehicle_tab_label_settings": {"Paramètres"},
                                   "acc_common_hint_details": {"Afficher les détails"}})
    french = dump("tiguan_overview_settings").replace(
        "Settings. Open details", "Paramètres. Afficher les détails")
    original = phone.dump_ui

    async def dump_ui():
        xml = await original()
        return french if phone.where == "overview" else xml

    phone.dump_ui = dump_ui  # taps are still hit-tested on the same bounds
    assert await channel_for(phone).set_charge_target(90) == 90


@pytest.mark.asyncio
async def test_plain_action_path_refuses_the_valueless_command():
    with pytest.raises(CompanionWriteBlocked, match="target value"):
        await channel_for(SettingsPhone()).do_action("set_charge_target")


@pytest.mark.asyncio
async def test_client_exposes_the_command_with_the_slider_bounds():
    client = CompanionClient(brand="volkswagen", vin="VIN", host="unused", port=5555,
                             adbkey_path="unused", time_fn=time.monotonic)
    phone = SettingsPhone(version="4.3.3")
    client._channel = channel_for(phone)
    assert client.supports_command("command_set_target_soc")
    assert client.target_soc_bounds == (50, 100, 10)
    with pytest.raises(VehicleCommandError, match="app version"):
        await client.command_set_target_soc("VIN", target=60)


def test_number_entity_offers_exactly_the_slider_steps():
    from custom_components.vag_connect.number import NUMBER_DESCRIPTIONS, VagConnectNumber

    desc = next(d for d in NUMBER_DESCRIPTIONS if d.key == "target_soc")
    number = object.__new__(VagConnectNumber)
    number.entity_description = desc
    number.coordinator = SimpleNamespace(_cariad_client=SimpleNamespace(target_soc_bounds=(50, 100, 10)))
    assert (number.native_min_value, number.native_max_value, number.native_step) == (50, 100, 10)
    number.coordinator = SimpleNamespace(_cariad_client=SimpleNamespace())
    assert (number.native_min_value, number.native_max_value, number.native_step) == (
        desc.native_min_value, desc.native_max_value, desc.native_step)


def test_fixtures_are_credited():
    sources = {s["fixture"] for s in json.loads((FIXTURES / "sources.json").read_text())}
    for name in [*TRUE_TRACK, "tiguan_overview_settings"]:
        assert name + ".xml" in sources
    for name in TRUE_TRACK:
        assert not re.search(r"inputText|info", dump(name))


@pytest.mark.asyncio
@pytest.mark.parametrize("alert", ["Too many requests sent to the vehicle", "Request limit reached"])
async def test_used_up_request_budget_pauses_with_a_clear_reason(alert):
    # Field test 2026-10-04 (@gszigethy): the car's daily request budget ran
    # out; the app answers with an alert (APK 4.3.2 ErrorMapper /
    # CapabilityStatusAlertDelegateImpl) instead of the screen.
    phone = SettingsPhone(limit_alert=alert)
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget.*Start the car"):
        await channel.set_charge_target(60)
    assert kinds(phone) == ["settings"] and phone.backs == 1 and phone.where == "overview"
    assert channel._is_rate_limited()
    with pytest.raises(CompanionWriteBlocked, match="backed off"):
        await channel.set_charge_target(60)


def test_request_limit_alert_is_recognised_in_any_installed_language():
    from custom_components.vag_connect.companion.resources import find_request_limit

    nodes = parse_ui_dump(_NOTE.replace(
        "The optimal value of the Battery Care Mode is 80%.", "Trop de demandes envoyées au véhicule"))
    assert not find_request_limit(nodes, STRINGS)
    assert find_request_limit(nodes, {"alert_daily_power_budget_title": {"Trop de demandes envoyées au véhicule"}})
    channel = channel_for(SettingsPhone())
    channel._battery_strings = {"dialog_maxrequests_headline": {"Trop de demandes envoyées au véhicule"}}
    assert channel._limit_on_screen(nodes)
