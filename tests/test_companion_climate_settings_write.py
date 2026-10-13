# SPDX-License-Identifier: AGPL-3.0-or-later
"""Climate Settings switches written through the app's own Save.

Screens are the live VW 4.6.4 captures in fixtures/companion_climate_settings
(see its sources.json); the fake phone serves them, patching only the switch
states, the Zones value and the Save button the real dumps show changing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
from custom_components.vag_connect.companion.channel import CompanionChannel, CompanionWriteBlocked
from custom_components.vag_connect.companion.climate_settings import (
    find_save,
    find_toggle,
    find_zone_switch,
    find_zones_back,
    find_zones_row,
    on_settings_page,
    on_zones_page,
)
from custom_components.vag_connect.companion.client import CompanionClient
from custom_components.vag_connect.companion.presets import (
    ACTION_TO_COMMAND,
    CLIMATE_SETTING_ACTIONS,
    CLIMATE_SETTINGS_APP_VERSIONS,
    PRESETS,
)
from custom_components.vag_connect.companion.resources import read_climate_resources
from custom_components.vag_connect.companion.screen import parse_ui_dump, read_selectors
from custom_components.vag_connect.companion.transport import CompanionTransportError

FIXTURES = Path(__file__).parent / "fixtures" / "companion_climate_settings"
VW = PRESETS["volkswagen"]
SETTINGS_NAV = next(n for n in VW.nav_reads if n.name == "climate_settings")
STRINGS = {
    k: set(v) for k, v in json.loads(
        (Path(__file__).parent / "fixtures" / "companion_battery" / "vw_432_resources.json")
        .read_text(encoding="utf-8")
    ).items()
}


def dump(name: str) -> str:
    return (FIXTURES / (name + ".xml")).read_text(encoding="utf-8")


def nodes(name: str):
    return parse_ui_dump(dump(name))


# ── the captured screens ─────────────────────────────────────────────────────

def test_saved_page_has_both_switches_off_and_no_save():
    page = nodes("settings")
    assert on_settings_page(page)
    assert find_toggle(page, "climate_at_unlock").checked is False
    assert find_toggle(page, "window_heating_enabled").checked is False
    assert find_save(page) is None
    # The read path agrees with the finders.
    assert read_selectors(page, SETTINGS_NAV.values) == {
        "climate_at_unlock": False, "window_heating_enabled": False,
    }


@pytest.mark.parametrize(("name", "key"), [
    ("settings_aux_staged", "climate_at_unlock"),
    ("settings_wh_staged", "window_heating_enabled"),
])
def test_a_switched_toggle_stages_and_shows_save(name, key):
    page = nodes(name)
    assert find_toggle(page, key).checked is True
    save = find_save(page)
    assert save is not None and save.bounds == (916, 82, 1042, 208)


def test_switching_back_takes_save_away():
    page = nodes("settings_aux_unstaged")
    assert find_toggle(page, "climate_at_unlock").checked is False
    assert find_save(page) is None


def test_zones_row_is_the_clickable_box_around_its_title():
    row = find_zones_row(nodes("settings"), STRINGS)
    assert row is not None and row.bounds == (0, 918, 1080, 1270)
    # Without the app's labels nothing is guessed.
    assert find_zones_row(nodes("settings"), {}) is None


def test_zones_page_switches_and_back_arrow():
    page = nodes("zones")
    assert on_zones_page(page, STRINGS) and not on_settings_page(page)
    assert find_zone_switch(page, STRINGS, "climate_zone_front_left").checked is True
    assert find_zone_switch(page, STRINGS, "climate_zone_front_right").checked is False
    assert find_zone_switch(nodes("zones_fr_on"), STRINGS, "climate_zone_front_right").checked is True
    back = find_zones_back(page, STRINGS)
    assert back is not None and back.bounds == (22, 82, 148, 208)
    # The Settings page is not the Zones page, though its title row looks alike.
    assert find_zone_switch(nodes("settings"), STRINGS, "climate_zone_front_left") is None
    assert find_zones_back(nodes("settings"), STRINGS) is None


def test_zone_change_is_staged_on_settings_then_saved():
    staged = nodes("settings_2zones_staged")
    assert find_save(staged) is not None
    assert read_climate_resources(staged, STRINGS) == {
        "climate_zone_front_left": True, "climate_zone_front_right": True,
    }
    # Save closed Settings onto the sheet; reopening shows it saved.
    sheet = nodes("sheet_after_save")
    assert not on_settings_page(sheet)
    assert any(n.resource_id.endswith("clima_settings_compose_view") for n in sheet)
    saved = nodes("settings_2zones_saved")
    assert find_save(saved) is None
    assert read_climate_resources(saved, STRINGS)["climate_zone_front_right"] is True


def test_432_settings_page_is_the_same_layout():
    # Cross-check only: the 4.3.2 capture of the same page (no Zones page or
    # Save was captured on 4.3.2, so the write stays pinned to 4.6.4).
    page = parse_ui_dump(
        (Path(__file__).parent / "fixtures" / "companion_climate" / "tiguan_climate_settings.xml")
        .read_text(encoding="utf-8")
    )
    assert on_settings_page(page)
    assert find_toggle(page, "climate_at_unlock") is not None
    assert find_toggle(page, "window_heating_enabled").checked is True
    assert find_save(page) is None


def test_fixtures_are_credited_and_redacted():
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    assert {s["fixture"] for s in sources} == {p.name for p in FIXTURES.glob("*.xml")}
    for path in FIXTURES.glob("*.xml"):
        assert "Érd" not in path.read_text(encoding="utf-8")


# ── the fake phone ───────────────────────────────────────────────────────────

_SAVE_NODE = re.search(
    r'<node [^>]*resource-id="climatisationSettingsTrailing"[^>]*/>', dump("settings_aux_staged")
).group(0)
_AUX = "[890,283][1027,409]"
_WH = "[890,585][1027,711]"
_FL = "[890,677][1027,803]"
_FR = "[890,849][1027,975]"


def _set_checked(xml: str, bounds: str, value: bool) -> str:
    def fix(m: re.Match) -> str:
        return re.sub(r'checked="(?:true|false)"', f'checked="{str(value).lower()}"', m.group(0))
    return re.sub(rf'<node [^>]*checkable="true"[^>]*bounds="{re.escape(bounds)}"[^>]*>', fix, xml)


def _within(box: str, x: int, y: int) -> bool:
    left, top, right, bottom = map(int, re.findall(r"\d+", box))
    return left <= x <= right and top <= y <= bottom


class SettingsPhone:
    """Overview → sheet → Climate Settings → Zones, reacting like 4.6.4.

    A switch only stages; Save shows while staged differs from saved, sends,
    and closes Settings onto the sheet. The Zones page's arrow carries its
    change to Settings, Android BACK does not. Leaving Settings drops staging.
    """

    connected = True

    def __init__(self, *, aux=False, wh=False, fl=True, fr=False, version="4.6.4",
                 no_save=False, drop_save=False, limit_after_save=False):
        self.saved = {"aux": aux, "wh": wh, "fl": fl, "fr": fr}
        self.staged = dict(self.saved)
        self.zones_page: dict[str, bool] = {}
        self.version = version
        self.no_save = no_save          # the app never offers Save
        self.drop_save = drop_save      # Save closes the page but keeps nothing
        self.limit_after_save = limit_after_save
        self.screen = "overview"
        self.taps: list[str] = []

    async def connect(self):
        return None

    async def foreground_app(self, package):
        return None

    async def current_app_version(self, package):
        return self.version

    async def battery_strings(self, package):
        return STRINGS

    async def key_back(self):
        self.taps.append("BACK")
        if self.screen == "zones":
            self.screen = "settings"  # without the zone change
        elif self.screen == "settings":
            self._leave_settings()
        else:
            self.screen = "overview"

    def _leave_settings(self):
        self.staged = dict(self.saved)
        self.screen = "sheet"

    @property
    def dirty(self) -> bool:
        return self.staged != self.saved

    async def dump_ui(self) -> str:
        if self.screen == "overview":
            return dump("overview")
        if self.screen == "sheet":
            return dump("sheet")
        if self.screen == "limit":
            return ('<hierarchy><node index="0" text="Too many requests sent to the vehicle" '
                    'resource-id="" class="android.widget.TextView" content-desc="" checkable="false" '
                    'checked="false" clickable="false" enabled="true" bounds="[53,1300][1027,1400]" />'
                    '</hierarchy>')
        if self.screen == "zones":
            xml = dump("zones")
            xml = _set_checked(xml, _FL, self.zones_page["fl"])
            return _set_checked(xml, _FR, self.zones_page["fr"])
        xml = dump("settings")
        xml = _set_checked(xml, _AUX, self.staged["aux"])
        xml = _set_checked(xml, _WH, self.staged["wh"])
        fl, fr = self.staged["fl"], self.staged["fr"]
        value = "2 zones" if fl and fr else "Front left" if fl else "Front right" if fr else ""
        xml = xml.replace('text="Front left"', f'text="{value}"')
        if self.dirty and not self.no_save:
            xml = xml.replace("</hierarchy>", _SAVE_NODE + "</hierarchy>")
        return xml

    async def tap(self, x, y):
        name = self._hit(x, y)
        self.taps.append(name)
        if name == "tile":
            self.screen = "sheet"
        elif name == "sheet_up":
            self.screen = "overview"
        elif name == "settings_row":
            self.screen = "settings"
        elif name == "leading":
            self._leave_settings()
        elif name in ("aux", "wh"):
            self.staged[name] = not self.staged[name]
        elif name == "zones_row":
            self.zones_page = {"fl": self.staged["fl"], "fr": self.staged["fr"]}
            self.screen = "zones"
        elif name in ("fl", "fr"):
            self.zones_page[name] = not self.zones_page[name]
        elif name == "zones_back":
            self.staged.update(self.zones_page)
            self.screen = "settings"
        elif name == "save":
            if not self.drop_save:
                self.saved = dict(self.staged)
            self.staged = dict(self.saved)
            self.screen = "limit" if self.limit_after_save else "sheet"

    def _hit(self, x, y) -> str:
        targets = {
            "overview": [("tile", "[572,180][1027,626]")],
            "sheet": [("sheet_up", "[21,975][147,1101]"), ("settings_row", "[53,1772][1027,1941]")],
            "settings": [("leading", "[22,82][148,208]") if not (self.dirty and not self.no_save)
                         else ("save", "[916,82][1042,208]"),
                         ("leading", "[22,82][148,208]"),
                         ("aux", _AUX), ("wh", _WH), ("zones_row", "[0,918][1080,1270]")],
            "zones": [("zones_back", "[22,82][148,208]"), ("fl", _FL), ("fr", _FR)],
        }.get(self.screen, [])
        for name, box in targets:
            if _within(box, x, y):
                return name
        return f"miss@{x},{y}"


def _channel(phone: SettingsPhone, now=lambda: 10_000.0) -> CompanionChannel:
    return CompanionChannel(phone, VW, time_fn=now, nav_opt_ins={"climate_settings"})


# ── writes ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "flag", "switch"), [
    ("climate_at_unlock", "aux", "aux"),
    ("window_heating_enabled", "wh", "wh"),
])
async def test_toggle_is_switched_saved_and_read_back(key, flag, switch):
    phone = SettingsPhone()
    channel = _channel(phone)
    assert await channel.set_climate_setting(key, True) is True
    assert phone.saved[flag] is True
    assert phone.taps == ["tile", "settings_row", switch, "save", "settings_row",
                          "leading", "sheet_up"]
    assert phone.screen == "overview"
    assert channel._nav_cache[key] is True
    assert channel._last_write_at == 10_000.0
    # The readback refresh re-reads the settings page only.
    assert channel._nav_only == {"climate_settings"}


@pytest.mark.asyncio
async def test_value_already_in_place_sends_nothing():
    phone = SettingsPhone(aux=True)
    channel = _channel(phone)
    assert await channel.set_climate_setting("climate_at_unlock", True) is False
    assert "save" not in phone.taps and "aux" not in phone.taps
    assert channel._last_write_at is None
    assert phone.screen == "overview"


@pytest.mark.asyncio
async def test_no_save_offered_switches_back_and_leaves_nothing_staged():
    phone = SettingsPhone(no_save=True)
    channel = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="did not offer Save"):
        await channel.set_climate_setting("window_heating_enabled", True)
    assert phone.taps.count("wh") == 2  # staged, then put back
    assert "save" not in phone.taps
    assert phone.saved["wh"] is False and not phone.dirty
    assert phone.screen == "overview"
    assert channel._last_write_at is None


@pytest.mark.asyncio
async def test_save_that_did_not_keep_the_value_fails():
    phone = SettingsPhone(drop_save=True)
    channel = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="after saving"):
        await channel.set_climate_setting("climate_at_unlock", True)
    assert "climate_at_unlock" not in channel._nav_cache
    assert phone.screen == "overview"


@pytest.mark.asyncio
async def test_request_limit_after_save_pauses_commands():
    phone = SettingsPhone(limit_after_save=True)
    channel = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="request budget"):
        await channel.set_climate_setting("climate_at_unlock", True)
    assert channel._is_rate_limited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "key", "enabled", "saved"), [
    # Front left → "2 zones", as captured (64 → 65 → 66 → 67 → 71).
    ((True, False), "climate_zone_front_right", True, (True, True)),
    # "2 zones" → front left only (the second captured round trip).
    ((True, True), "climate_zone_front_right", False, (True, False)),
    ((True, False), "climate_zone_front_left", False, (False, False)),
    ((False, False), "climate_zone_front_left", True, (True, False)),
])
async def test_zone_is_carried_back_saved_and_read_back(start, key, enabled, saved):
    phone = SettingsPhone(fl=start[0], fr=start[1])
    channel = _channel(phone)
    assert await channel.set_climate_setting(key, enabled) is True
    assert (phone.saved["fl"], phone.saved["fr"]) == saved
    switch = "fl" if key.endswith("left") else "fr"
    assert phone.taps == [
        "tile", "settings_row", "zones_row", switch, "zones_back", "save",
        # Read back on the Zones page itself, then out: BACK, Leading, up.
        "settings_row", "zones_row", "BACK", "leading", "sheet_up",
    ]
    assert channel._nav_cache[key] is enabled
    assert phone.screen == "overview" and not phone.dirty


@pytest.mark.asyncio
async def test_zone_already_set_backs_out_of_zones_without_change():
    phone = SettingsPhone(fl=True)
    channel = _channel(phone)
    assert await channel.set_climate_setting("climate_zone_front_left", True) is False
    assert phone.taps == ["tile", "settings_row", "zones_row", "BACK", "leading", "sheet_up"]
    assert channel._last_write_at is None


@pytest.mark.asyncio
async def test_zone_save_not_offered_is_left_unsaved():
    phone = SettingsPhone(no_save=True)
    channel = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="did not offer Save"):
        await channel.set_climate_setting("climate_zone_front_right", True)
    assert "save" not in phone.taps
    assert phone.saved == {"aux": False, "wh": False, "fl": True, "fr": False}
    assert not phone.dirty and phone.screen == "overview"


@pytest.mark.asyncio
async def test_zones_need_the_app_labels():
    phone = SettingsPhone()

    async def no_strings(_package):
        return {}

    phone.battery_strings = no_strings
    channel = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="translation tables"):
        await channel.set_climate_setting("climate_zone_front_left", False)
    assert phone.taps == []


@pytest.mark.asyncio
async def test_older_app_is_refused_before_any_tap():
    assert CLIMATE_SETTINGS_APP_VERSIONS == ("4.6.4",)
    phone = SettingsPhone(version="4.3.2")
    with pytest.raises(CompanionWriteBlocked, match="not mapped for app version 4.3.2"):
        await _channel(phone).set_climate_setting("climate_at_unlock", True)
    assert phone.taps == []


@pytest.mark.asyncio
async def test_second_write_within_a_minute_is_refused():
    clock = [10_000.0]
    phone = SettingsPhone()
    channel = _channel(phone, now=lambda: clock[0])
    await channel.set_climate_setting("climate_at_unlock", True)
    clock[0] += 30
    with pytest.raises(CompanionWriteBlocked, match="keeps at least 60s"):
        await channel.set_climate_setting("window_heating_enabled", True)
    clock[0] += 31
    assert await channel.set_climate_setting("window_heating_enabled", True) is True


class DroppingPhone(SettingsPhone):
    """The direct ADB transport: a dump timeout after the switch closes the device."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.connected = True
        self.fail_next_dump = False
        self.connects = 0

    async def connect(self):
        self.connects += 1
        self.connected = True

    def _need(self):
        if not self.connected:
            raise CompanionTransportError("not connected")

    async def dump_ui(self):
        self._need()
        if self.fail_next_dump:
            self.fail_next_dump = False
            self.connected = False
            raise CompanionTransportError("the ADB connection failed (TimeoutError)")
        return await super().dump_ui()

    async def tap(self, x, y):
        self._need()
        await super().tap(x, y)
        if self.taps == ["tile", "settings_row", "aux"]:
            self.fail_next_dump = True  # only the first switch tap

    async def key_back(self):
        self._need()
        await super().key_back()


@pytest.mark.asyncio
async def test_dropped_connection_mid_walk_still_unstages_the_switch():
    phone = DroppingPhone()
    channel = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="TimeoutError"):
        await channel.set_climate_setting("climate_at_unlock", True)
    # The cleanup reconnected once, switched it back and left without Save.
    assert phone.connects == 1
    assert phone.taps.count("aux") == 2 and "save" not in phone.taps
    assert not phone.dirty and phone.screen == "overview"
    assert phone.saved["aux"] is False


@pytest.mark.asyncio
async def test_a_staged_switch_left_behind_is_never_saved_with_the_next_command():
    # An earlier walk was cut off with "climate at unlock" switched but not
    # saved, and its cleanup could not reach the phone either.
    phone = SettingsPhone()
    phone.screen = "settings"
    phone.staged["aux"] = True
    channel = _channel(phone)
    assert await channel.set_climate_setting("window_heating_enabled", True) is True
    # Home first (Leading drops the staged switch), then the usual walk.
    assert phone.taps[:2] == ["leading", "sheet_up"]
    assert "aux" not in phone.taps
    assert phone.saved == {"aux": False, "wh": True, "fl": True, "fr": False}


@pytest.mark.asyncio
async def test_a_command_is_refused_when_the_app_cannot_get_home():
    # A zone change left on the Zones page, and the app ignores every tap.
    phone = SettingsPhone()
    phone.screen = "zones"
    phone.zones_page = {"fl": True, "fr": True}

    async def ignored(*_args):
        phone.taps.append("ignored")

    phone.tap = phone.key_back = ignored
    with pytest.raises(CompanionWriteBlocked, match="did not return to its overview"):
        await _channel(phone).set_climate_setting("climate_at_unlock", True)
    assert phone.taps == ["ignored"] * 3  # bounded, and none of them a Save
    assert phone.saved == {"aux": False, "wh": False, "fl": True, "fr": False}


@pytest.mark.asyncio
async def test_a_request_limit_alert_off_the_overview_pauses_before_any_tap():
    # The walk home would close the alert with BACK before anything saw it.
    phone = SettingsPhone()
    phone.screen = "limit"
    channel = _channel(phone)
    with pytest.raises(CompanionWriteBlocked, match="request budget"):
        await channel.set_climate_setting("climate_at_unlock", True)
    assert channel._is_rate_limited()
    assert phone.taps == [] and phone.saved["aux"] is False


@pytest.mark.asyncio
async def test_a_request_limit_alert_off_the_overview_pauses_a_poll_too():
    phone = SettingsPhone()
    phone.screen = "limit"
    channel = _channel(phone)
    await channel.read()
    assert channel._is_rate_limited()
    assert "save" not in phone.taps


@pytest.mark.asyncio
async def test_a_poll_on_an_unverified_app_version_does_not_walk_home():
    phone = SettingsPhone(version="0.0.0")
    phone.screen = "settings"
    phone.staged["aux"] = True
    channel = _channel(phone)
    assert await channel.read() == {}
    assert phone.taps == []
    assert phone.screen == "settings"


@pytest.mark.asyncio
async def test_unknown_setting_and_plain_action_path_are_refused():
    channel = _channel(SettingsPhone())
    with pytest.raises(CompanionWriteBlocked, match="not a climate setting"):
        await channel.set_climate_setting("climate_without_external_power", True)
    with pytest.raises(CompanionWriteBlocked, match="on/off value"):
        await channel.do_action("set_climate_at_unlock")


# ── client and entities ──────────────────────────────────────────────────────

COMMANDS = {
    "command_set_climate_at_unlock": "climate_at_unlock",
    "command_set_window_heating_auto": "window_heating_enabled",
    "command_set_climate_zone_front_left": "climate_zone_front_left",
    "command_set_climate_zone_front_right": "climate_zone_front_right",
}


def test_every_setting_has_a_mapped_action_and_command():
    assert {ACTION_TO_COMMAND[a] for a in CLIMATE_SETTING_ACTIONS.values()} == set(COMMANDS)
    for action in CLIMATE_SETTING_ACTIONS.values():
        spec = next(a for a in VW.actions if a.action == action)
        assert spec.nav_read == "climate_settings"
        assert spec.app_versions == CLIMATE_SETTINGS_APP_VERSIONS


def _client() -> CompanionClient:
    client = CompanionClient.__new__(CompanionClient)
    client._brand = "volkswagen"
    client._vin = "VIN1"
    client._channel = MagicMock()
    client._channel.set_climate_setting = AsyncMock(return_value=True)
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(("command", "key"), sorted(COMMANDS.items()))
async def test_client_commands_reach_the_channel(command, key):
    client = _client()
    assert client.supports_command(command)
    await getattr(client, command)("VIN1", enabled=False)
    client._channel.set_climate_setting.assert_awaited_once_with(key, False)


@pytest.mark.asyncio
async def test_client_reports_a_blocked_write_as_a_command_error():
    client = _client()
    client._channel.set_climate_setting = AsyncMock(side_effect=CompanionWriteBlocked("nope"))
    with pytest.raises(VehicleCommandError, match="nope"):
        await client.command_set_climate_at_unlock("VIN1", enabled=True)


def test_other_brands_do_not_offer_the_commands():
    client = _client()
    client._brand = "audi"
    assert not any(client.supports_command(c) for c in COMMANDS)


def test_switches_use_their_own_unique_ids_and_the_read_fields():
    from custom_components.vag_connect.switch import (
        COMPANION_CLIMATE_SETTINGS,
        VagCompanionClimateSettingSwitch,
    )

    assert {field for _k, field, _c, _i in COMPANION_CLIMATE_SETTINGS} == set(COMMANDS.values())
    assert {cmd for _k, _f, cmd, _i in COMPANION_CLIMATE_SETTINGS} == set(COMMANDS)
    # The read-only binary sensors keep the field names as their keys.
    assert all(key.endswith("_switch") and key != field
               for key, field, _c, _i in COMPANION_CLIMATE_SETTINGS)
    english = json.loads(
        (Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
         / "translations" / "en.json").read_text(encoding="utf-8")
    )["entity"]["switch"]
    for key, _f, _c, _i in COMPANION_CLIMATE_SETTINGS:
        assert english[key]["name"]

    coordinator = MagicMock()
    coordinator.data = {"VIN1": {"climate_zone_front_left": True}}
    coordinator._cariad_cmd_optimistic = AsyncMock()
    sw = VagCompanionClimateSettingSwitch(
        coordinator, "VIN1", "climate_zone_front_left_switch", "climate_zone_front_left",
        "command_set_climate_zone_front_left", "mdi:car-seat",
    )
    assert sw.unique_id == "VIN1_climate_zone_front_left_switch"
    assert sw.is_on is True
    coordinator.data = {"VIN1": {}}
    assert sw.is_on is None


@pytest.mark.asyncio
async def test_switch_turns_the_setting_off_through_the_coordinator():
    from custom_components.vag_connect.switch import VagCompanionClimateSettingSwitch

    coordinator = MagicMock()
    coordinator._cariad_cmd_optimistic = AsyncMock()
    sw = VagCompanionClimateSettingSwitch(
        coordinator, "VIN1", "climate_at_unlock_switch", "climate_at_unlock",
        "command_set_climate_at_unlock", "mdi:car-electric",
    )
    await sw.async_turn_off()
    coordinator._cariad_cmd_optimistic.assert_awaited_once_with(
        "VIN1", "command_set_climate_at_unlock",
        optimistic={"climate_at_unlock": False}, enabled=False,
    )
