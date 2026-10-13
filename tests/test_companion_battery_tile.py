# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Battery mapping grounded in #968 captures; see fixtures/sources.json."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel, CompanionWriteBlocked
from custom_components.vag_connect.companion.client import CompanionClient
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import (
    extract_app_strings,
    find_battery_control,
    find_battery_tile,
    read_battery_resources,
)
from custom_components.vag_connect.companion.screen import find_node_for, parse_ui_dump, read_fields, read_selectors
from custom_components.vag_connect.companion.transport import CompanionTransportError
from custom_components.vag_connect.switch import VagChargingSwitch

FIXTURES = Path(__file__).parent / "fixtures" / "companion_battery"
VW = PRESETS["volkswagen"]
CHARGE = next(nav for nav in VW.nav_reads if nav.name == "charge_detail")
STRINGS = {k: set(v) for k, v in json.loads((FIXTURES / "vw_432_resources.json").read_text(encoding="utf-8")).items()}


def dump(name: str) -> str:
    return (FIXTURES / (name + ".xml")).read_text(encoding="utf-8")


@pytest.mark.parametrize(("name", "expected"), [
    ("tiguan_charging", {"battery_soc": 70, "target_soc": 80, "charging_power_kw": 2.0,
                          "remaining_charge_time_min": 55, "is_charging": True}),
    ("tiguan_target_reached", {"battery_soc": 80, "target_soc": 80, "is_charging": False,
                              "charging_state": "Target charge level reached"}),
    ("gte_charging", {"battery_soc": 40, "is_charging": True, "remaining_charge_time_min": 135}),
    ("gte_stopped", {"battery_soc": 79, "is_charging": False}),
    ("id4_charging", {"battery_soc": 34, "target_soc": 90, "charging_power_kw": 10.0,
                       "remaining_charge_time_min": 270, "is_charging": True}),
    ("eup_charging", {"battery_soc": 13, "remaining_charge_time_min": 245, "is_charging": True}),
])
def test_contributors_charge_screens(name, expected):
    fields = read_selectors(parse_ui_dump(dump(name)), CHARGE.values)
    for key, value in expected.items():
        assert fields[key] == value
    assert "fuel_level" not in fields
    if name.startswith(("gte", "eup")):
        assert "target_soc" not in fields
        assert "charging_power_kw" not in fields


@pytest.mark.parametrize(("name", "ev", "fuel"), [
    ("tiguan_overview", 88, 410), ("gte_overview", 47, 676), ("id4_overview", 253, None),
])
def test_overview_separates_petrol_and_ev_range(name, ev, fuel):
    fields = read_fields(parse_ui_dump(dump(name)), VW)
    assert fields["electric_range_km"] == ev
    assert fields.get("combustion_range_km") == fuel
    assert "fuel_level" not in fields  # never calculate % from range


def test_installed_resource_templates_match_real_tiguan_dump():
    fields = read_battery_resources(parse_ui_dump(dump("tiguan_charging")), STRINGS)
    assert fields["battery_soc"] == 70
    assert fields["target_soc"] == 80
    assert fields["charging_power_kw"] == 2.0
    assert fields["charging_rate_kmh"] == 11
    assert fields["remaining_charge_time_min"] == 55
    assert fields["is_charging"] is True


def test_resource_names_work_with_an_unrecognised_language():
    # Synthetic labels, NOT claimed to be a real translated capture. The
    # algorithm must use resource names/templates, not English/German words.
    resources = {
        "acc_vehicle_tab_range_tile_value_battery_range_miles": {"AAA %s BBB"},
        "acc_vehicle_tab_range_tile_value_fuel_range_km": {"CCC %s DDD"},
        "acc_vehicle_tab_range_tile_value_petrol_level": {"EEE %s FFF"},
        "acc_range_modal_value_charge_level_reached": {"GGG"},
        "acc_range_modal_value_charging_target_charge_level": {"HHH %s III"},
        "acc_range_modal_label_cta_start": {"JJJ"},
        "acc_range_modal_hint_cta_start_disabled": {"KKK"},
    }
    nodes = parse_ui_dump('<hierarchy><node content-desc="AAA 29 BBB. CCC 410 DDD. EEE 49 FFF" />'
                          '<node resource-id="rangeArcBatterySoc" content-desc="GGG" />'
                          '<node content-desc="HHH 80 III" />'
                          '<node content-desc="JJJ" bounds="[0,0][100,100]" /></hierarchy>')
    fields = read_battery_resources(nodes, resources)
    assert fields == {"electric_range_km": 47, "combustion_range_km": 410, "fuel_level": 49,
                      "target_soc": 80, "charging_state": "Target charge level reached", "is_charging": False}
    assert find_battery_control(nodes, resources, "start_charging").tap_point == (50, 50)
    disabled = parse_ui_dump('<hierarchy><node content-desc="JJJ. KKK" bounds="[0,0][100,100]" /></hierarchy>')
    assert find_battery_control(disabled, resources, "start_charging") is None


def test_target_reached_button_is_disabled_despite_compose_enabled_flag():
    nodes = parse_ui_dump(dump("tiguan_target_reached"))
    assert find_battery_control(nodes, STRINGS, "start_charging") is None
    assert read_battery_resources(nodes, STRINGS)["is_charging"] is False


@pytest.mark.parametrize(("active", "state", "expected"), [
    (True, "Currently charging", True), (False, "charging", False),
    (None, "conservationCharging", True), (False, "conservationCharging", True),
])
def test_ha_charging_switch_uses_explicit_state_with_legacy_fallback(active, state, expected):
    switch = VagChargingSwitch.__new__(VagChargingSwitch)
    switch._vin = "VIN"
    switch.coordinator = SimpleNamespace(data={"VIN": {"is_charging": active, "charging_state": state}})
    assert switch.is_on is expected


def test_translated_tile_requires_details_hint_not_detail_arc():
    resources = {"acc_vehicle_tab_range_tile_label": {"AAA"}, "acc_common_hint_details": {"BBB"}}
    nodes = parse_ui_dump('<hierarchy><node content-desc="AAA. CCC. BBB" bounds="[0,0][100,100]" /></hierarchy>')
    assert find_battery_tile(nodes, resources) is not None
    nodes = parse_ui_dump('<hierarchy><node content-desc="AAA. CCC" bounds="[0,0][100,100]" /></hierarchy>')
    assert find_battery_tile(nodes, resources) is None


@pytest.mark.parametrize("data", [b"", b"garbage", b"\x02\x00\x0c\x00\xff\xff\xff\xff"])
def test_bad_resource_table_fails_closed(data):
    assert extract_app_strings(data) == {}


class Phone:
    connected = True

    def __init__(self, detail="gte_stopped", version="4.3.2"):
        self.screen = dump("gte_overview")
        self.detail = dump(detail)
        self.version = version
        self.taps = []
        self.fail_command = False

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return self.version

    async def battery_strings(self, package):
        return STRINGS

    async def dump_ui(self):
        return self.screen

    async def tap(self, x, y):
        self.taps.append((x, y))
        if len(self.taps) == 1:
            self.screen = self.detail
        elif self.fail_command and len(self.taps) == 2:
            raise CompanionTransportError("lost after delivery")
        elif len(self.taps) >= 3:
            self.screen = dump("gte_overview")

    async def key_back(self):
        self.screen = dump("gte_overview")


@pytest.mark.asyncio
async def test_start_walks_to_detail_and_returns_without_claiming_vehicle_success():
    phone = Phone()
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic)
    channel._nav_cache = {"battery_soc": 100, "odometer_km": 307}
    await channel.do_action("start_charging")
    tile = next(n for n in parse_ui_dump(dump("gte_overview")) if n.resource_id == "rangeTile")
    start = find_battery_control(parse_ui_dump(dump("gte_stopped")), STRINGS, "start_charging")
    assert phone.taps[:2] == [tile.tap_point, start.tap_point]
    assert len(phone.taps) == 3  # close the sheet
    # Only the charge sheet's own values are dropped and re-read next poll;
    # other paths keep their cache and cadence, so no walk of every screen.
    assert channel._nav_cache == {"odometer_km": 307}
    assert channel._nav_only == {"charge_detail"}
    with pytest.raises(CompanionWriteBlocked, match="between"):
        await channel.do_action("start_charging")
    assert len(phone.taps) == 3


@pytest.mark.asyncio
async def test_command_started_on_the_sheet_closes_it():
    # Review B12: a command begun with the sheet open leaves it closed. Since
    # every command starts from the overview (core C2), the gate closes the
    # sheet first, the walk reopens it from the tile, and the command closes
    # it again; the Start tap happens exactly once.
    phone = Phone()
    phone.screen = phone.detail
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic)
    sheet = parse_ui_dump(phone.detail)
    close = next(n for n in (find_node_for(sheet, s) for s in VW.up_controls) if n is not None)
    start = find_battery_control(sheet, STRINGS, "start_charging")
    assert close.tap_point != start.tap_point
    overview = dump("gte_overview")

    async def tap(x, y):
        phone.taps.append((x, y))
        if phone.screen == phone.detail:
            if (x, y) == close.tap_point:  # only the sheet's own Close leaves it
                phone.screen = overview
        else:  # the range tile opens the sheet
            phone.screen = phone.detail

    phone.tap = tap
    await channel.do_action("start_charging")
    assert phone.taps[0] == close.tap_point
    assert phone.taps[2:] == [start.tap_point, close.tap_point]
    assert phone.taps.count(start.tap_point) == 1
    assert phone.screen == overview


@pytest.mark.asyncio
async def test_active_screen_only_allows_stop():
    phone = Phone("gte_charging")
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic)
    with pytest.raises(CompanionWriteBlocked, match="could not find"):
        await channel.do_action("start_charging")
    assert len(phone.taps) == 2  # open, close; no vehicle command
    phone.taps.clear()
    phone.screen = dump("gte_overview")
    await channel.do_action("stop_charging")
    assert phone.taps[1] == find_battery_control(parse_ui_dump(phone.detail), STRINGS, "stop_charging").tap_point


@pytest.mark.asyncio
async def test_delivery_failure_unwinds_and_blocks_repeat():
    phone = Phone()
    phone.fail_command = True
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic)
    with pytest.raises(CompanionWriteBlocked, match="lost after delivery"):
        await channel.do_action("start_charging")
    assert len(phone.taps) == 3
    with pytest.raises(CompanionWriteBlocked, match="between"):
        await channel.do_action("start_charging")


@pytest.mark.asyncio
async def test_update_between_poll_and_command_rechecks_version():
    phone = Phone()
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic)
    await channel.read()
    phone.version = "4.3.3"
    with pytest.raises(CompanionWriteBlocked, match="app version"):
        await channel.do_action("start_charging")
    assert not phone.taps


@pytest.mark.asyncio
async def test_poll_and_command_cannot_move_the_same_screen_concurrently():
    phone = Phone()
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic)
    started, release = asyncio.Event(), asyncio.Event()
    original = phone.tap

    async def paused_tap(x, y):
        if not phone.taps:
            started.set()
            await release.wait()
        await original(x, y)

    phone.tap = paused_tap
    command = asyncio.create_task(channel.do_action("start_charging"))
    await started.wait()
    poll = asyncio.create_task(channel.read())
    await asyncio.sleep(0)
    assert not poll.done()
    release.set()
    await command
    await poll


@pytest.mark.asyncio
async def test_client_exposes_existing_phev_entities_and_charge_commands():
    client = CompanionClient(brand="volkswagen", vin="VIN", host="unused", port=5555,
                             adbkey_path="unused", time_fn=time.monotonic)
    client._channel = CompanionChannel(Phone(), VW, time_fn=time.monotonic)
    data = await client.get_status("VIN")
    assert data.has_battery and data.has_combustion and data.is_hybrid
    assert data.combustion_range_km == 676
    assert data.fuel_level is None
    assert client.supports_command("command_start_charging")
    assert client.supports_command("command_stop_charging")
    # Unmapped controls stay hidden. (Climate is mapped by its own change.)
    assert not client.supports_command("command_lock")
    # The charge limit is mapped on vehicle Settings (test_companion_charge_target).
    assert client.supports_command("command_set_target_soc")


@pytest.mark.parametrize("name", ["tiguan_overview", "gte_overview", "id4_overview"])
def test_overview_is_recognised_by_its_anchor_id(name):
    # The 4.3.2 ``rangeTile`` container has no text of its own; requiring one
    # meant the walk back after a charge command never knew it was home.
    from custom_components.vag_connect.companion.screen import has_anchor

    assert has_anchor(parse_ui_dump(dump(name)), VW)


@pytest.mark.asyncio
async def test_command_readback_walks_only_its_own_detail_path():
    phone = Phone()
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic,
                               nav_opt_ins={"charge_detail", "vehicle_health", "climate_detail"})
    channel._nav_only = {"charge_detail"}
    walked = []

    async def fake_walk(path, here=None):
        walked.append(path[0].action)
        return None, 0

    channel._walk_to_detail = fake_walk
    await channel._augment_via_nav({})
    assert walked == ["open_charge_detail"]
    assert channel._nav_only == set()


def test_settings_auto_release_switch_is_read():
    from custom_components.vag_connect.companion.resources import read_settings_resources

    nodes = parse_ui_dump(dump("tiguan_settings_switches"))
    assert read_settings_resources(nodes, STRINGS) == {"auto_unlock_when_charged": True}
    # The same screen still gives the charge limit, by the preset's selector.
    settings = next(nav for nav in VW.nav_reads if nav.name == "vehicle_settings")
    assert read_selectors(nodes, settings.values) == {"target_soc": 80}


def test_settings_switches_absent_without_their_rows():
    from custom_components.vag_connect.companion.resources import read_settings_resources

    assert read_settings_resources(parse_ui_dump(dump("tiguan_settings")), STRINGS) == {}


@pytest.mark.asyncio
async def test_settings_walk_runs_for_its_switches_when_the_limit_is_known():
    channel = CompanionChannel(Phone(), VW, time_fn=time.monotonic, nav_opt_ins={"vehicle_health"})
    walked = []

    async def fake_walk(path, *_args):
        walked.append(path[0].action)
        return None, 0

    channel._walk_to_detail = fake_walk
    await channel._augment_via_nav({"target_soc": 80, "odometer_km": 1, "service_due_in_days": 1,
                                    "oil_service_due_in_days": 1})
    assert walked == ["open_vehicle_settings"]


@pytest.mark.asyncio
async def test_departure_timers_are_unknown_not_off():
    # Without the departure-times read "off" would be a value nobody read.
    client = CompanionClient(brand="volkswagen", vin="VIN", host="unused", port=5555,
                             adbkey_path="unused", time_fn=time.monotonic)
    client._channel = CompanionChannel(Phone(), VW, time_fn=time.monotonic)
    data = await client.get_status("VIN")
    assert data.departure_timer_1_enabled is None
    assert data.departure_timer_2_enabled is None
    assert data.departure_timer_3_enabled is None


def test_charge_mode_is_read_from_the_charging_method_row():
    # @gszigethy Tiguan: "Charging method. Immediate charging. Change charging
    # method"; Immediate charging is the APK's ChargeModes "manual".
    out = read_battery_resources(parse_ui_dump(dump("tiguan_target_reached")), STRINGS)
    assert out["charge_mode"] == "manual"


def test_charge_mode_uses_the_installed_language():
    # @kgroshert ID.4 (German): "Ladeverfahren. Sofortladen. Ladeverfahren ändern".
    german = {
        "acc_range_modal_label_charge_mode": {"Ladeverfahren"},
        "acc_range_modal_value_charge_mode_immediate_charging": {"Sofortladen"},
    }
    out = read_battery_resources(parse_ui_dump(dump("id4_charging")), german)
    assert out["charge_mode"] == "manual"


@pytest.mark.parametrize(("label", "wire"), [
    ("Charge at preferred times", "preferredChargingTimes"),
    ("Charge for departure time", "timer"),
    ("Charge/air condition for departure", "timerChargingWithClimatisation"),
    ("Charge using solar power", "onlyOwnCurrent"),
    ("Something new", None),
])
def test_charge_mode_labels_map_to_the_cloud_values(label, wire):
    from custom_components.vag_connect.companion.resources import read_charge_mode

    xml = (
        '<hierarchy><node text="" resource-id="" content-desc="Charging method. '
        f'{label}. Change charging method" bounds="[0,0][10,10]"/></hierarchy>'
    )
    assert read_charge_mode(parse_ui_dump(xml), STRINGS) == wire


@pytest.mark.parametrize(("raw", "shown"), [
    ("manual", "manual"), ("preferredChargingTimes", "preferred_charging_times"),
    ("timerChargingWithClimatisation", "timer_charging_climatization"), (None, None),
])
def test_companion_charge_mode_sensor_shows_the_select_options(raw, shown):
    from unittest.mock import MagicMock

    from custom_components.vag_connect.sensor import VagCompanionChargeModeSensor

    vin = "WVWZZZAUZFW805377"
    sensor = VagCompanionChargeModeSensor.__new__(VagCompanionChargeModeSensor)
    sensor._vin = vin
    sensor.coordinator = MagicMock()
    sensor.coordinator.data = {vin: {"vin": vin, "charge_mode": raw}}
    assert sensor.native_value == shown
    assert "manual" in sensor.options


def test_overview_while_charging_reports_a_state_not_the_tile_narration():
    nodes = parse_ui_dump(dump("tiguan_overview"))
    fields = read_fields(nodes, VW)
    fields.update(read_battery_resources(nodes, STRINGS))
    assert fields["charging_state"] == "Currently charging"
    assert fields["is_charging"] is True


@pytest.mark.asyncio
async def test_climate_sheet_and_its_settings_are_read_on_one_walk():
    channel = CompanionChannel(Phone(), VW, time_fn=time.monotonic,
                               nav_opt_ins={"climate_detail", "climate_settings"})
    sheet = parse_ui_dump('<hierarchy><node text="Air Conditioning" bounds="[0,0][10,10]"/></hierarchy>')
    walks, backs = [], []

    async def fake_walk(path, here=None):
        walks.append(([s.action for s in path], here))
        return (sheet if here is None else []), len(path)

    async def fake_back(presses=1):
        backs.append(presses)

    channel._walk_to_detail = fake_walk
    channel._return_to_overview = fake_back
    await channel._augment_via_nav({})
    # The tile is tapped once; Settings continues from the sheet just read.
    assert walks == [(["open_climate_detail"], None), (["open_climate_settings"], sheet)]
    assert backs == [2]
