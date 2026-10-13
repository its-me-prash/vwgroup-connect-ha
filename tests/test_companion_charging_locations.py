# SPDX-License-Identifier: AGPL-3.0-or-later
"""Charging-location captures and a read-only navigation walk."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest
from homeassistant.const import EntityCategory

from custom_components.vag_connect.binary_sensor import BINARY_DESCRIPTIONS
from custom_components.vag_connect.binary_sensor import _DATA_PRESENT_REQUIRED as BINARY_REQUIRED
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.charging_locations import (
    LOCATION_FIELDS,
    LOCATION_PARTS,
    active_timer_count,
    location_rows,
    location_settings,
    location_timers,
    recurrence_days,
    settings_icon,
)
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import CHARGING_PLURAL, DEPARTURE_TILE, extract_app_strings
from custom_components.vag_connect.companion.screen import UiNode, parse_ui_dump
from custom_components.vag_connect.companion.transport import CompanionTransportError
from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS
from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED as SENSOR_REQUIRED
from tests.test_companion_departure_writes import page_xml
from tests.test_companion_resources import pool, table

FIXTURES = Path(__file__).parent / "fixtures" / "companion_charging_locations"
VW = PRESETS["volkswagen"]
NAV = next(nav for nav in VW.nav_reads if nav.name == "charging_locations")
STRINGS = {
    DEPARTURE_TILE: {"Departure times"},
    "acc_common_hint_details": {"Open details"},
    "common_charging": {"Charging"},
    "common_status_active": {"Active"},
    f"{CHARGING_PLURAL}#zero": {"No active departure time"},
    f"{CHARGING_PLURAL}#one": {"1 active departure time"},
    f"{CHARGING_PLURAL}#other": {"%s active departure times"},
    "screen_charging_settings_title": {"Charging settings"},
    "screen_charging_settings_relatedlocation": {"Settings for this charging location:"},
    "vehiclesettingsscreen_reducedchargingspeed": {"Reduced AC charging current"},
    "vehiclesettingsscreen_automaticplugunlock": {"Automatically release AC connector"},
    "departure_timer_subscreen_every_day": {"Every day"},
    "departure_timer_subscreen_weekdays": {"Weekdays"},
    "departure_timer_subscreen_weekend": {"Weekends"},
    **{f"departure_timer_subscreen_{code}": {label} for code, label in zip(
        ("mon", "tue", "wed", "thu", "fri", "sat", "sun"), ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"))},
    **{f"weekday_{day.casefold()}": {day} for day in (
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")},
}


def fixture(name):
    return parse_ui_dump((FIXTURES / f"{name}_464.xml").read_text(encoding="utf-8"))


def xml(nodes):
    root = Element("hierarchy")
    for n in nodes:
        bounds = "" if n.bounds is None else f"[{n.bounds[0]},{n.bounds[1]}][{n.bounds[2]},{n.bounds[3]}]"
        SubElement(root, "node", {
            "resource-id": n.resource_id, "content-desc": n.content_desc, "text": n.text,
            "class": n.clazz, "bounds": bounds, "clickable": str(n.clickable).lower(),
            "checkable": str(n.checkable).lower(), "checked": str(n.checked).lower(),
            "enabled": str(n.enabled).lower(), "selected": str(n.selected).lower(),
        })
    return tostring(root, encoding="unicode")


def test_capture_rows_and_timers():
    rows = location_rows(fixture("list"), STRINGS)
    assert len(rows) == 1
    assert (rows[0].name.text, rows[0].active, rows[0].active_timers) == ("Otthon", True, 1)
    assert location_timers(fixture("location"), STRINGS, 1) == {
        "charging_location_1_timer_1_enabled": True, "charging_location_1_timer_1_time": "07:00",
        "charging_location_1_timer_1_weekdays": "mon,tue,wed,thu,fri",
        "charging_location_1_timer_2_enabled": False, "charging_location_1_timer_2_time": "09:00",
        "charging_location_1_timer_2_weekdays": "sat,sun",
        "charging_location_1_timer_3_enabled": False, "charging_location_1_timer_3_time": "07:00",
        "charging_location_1_timer_3_weekdays": "mon,tue,wed,thu,fri,sat,sun",
    }
    assert location_settings(fixture("settings"), STRINGS, 1, "Otthon") == {
        "charging_location_1_reduced_ac_current": False,
        "charging_location_1_auto_release_connector": False,
    }


@pytest.mark.parametrize(("label", "expected"), [
    ("Every day", "mon,tue,wed,thu,fri,sat,sun"), ("Weekdays", "mon,tue,wed,thu,fri"),
    ("Weekends", "sat,sun"), ("Thursday", "thu"), ("Mo, We, Fr", "mon,wed,fri"),
    ("Su, Tu", "tue,sun"), ("Something else", None), ("Mo, Unknown", None),
])
def test_recurrence_labels(label, expected):
    assert recurrence_days(label, STRINGS) == expected


@pytest.mark.parametrize(("label", "expected"), [
    ("No active departure time", 0), ("1 active departure time", 1),
    ("3 active departure times", 3), ("unknown", None),
])
def test_plural_text(label, expected):
    assert active_timer_count(label, STRINGS) == expected


def test_numbered_plural_placeholder_and_localised_labels():
    strings = {f"{CHARGING_PLURAL}#other": {"%1$s aktív időzítés"},
               "departure_timer_subscreen_weekdays": {"Hétköznapok"}}
    assert active_timer_count("2 aktív időzítés", strings) == 2
    assert recurrence_days("Hétköznapok", strings) == "mon,tue,wed,thu,fri"
    assert recurrence_days("Weekdays", strings) is None
    assert active_timer_count("2 active departure times", strings) is None


def test_chip_mismatch_and_unknown_recurrence_leave_values_unset():
    assert location_settings(fixture("settings"), STRINGS, 1, "Other") == {}
    timers = location_timers(fixture("location"), {}, 1)
    assert all(not key.endswith("weekdays") for key in timers)


def test_settings_icon_is_structural_and_ambiguous_icons_are_rejected():
    nodes = fixture("location")
    icon = settings_icon(nodes, "Otthon")
    assert icon is not None and icon.tap_point == (996, 145)
    assert settings_icon(nodes, "Other") is None
    assert settings_icon(nodes + [replace(icon, bounds=(950, 90, 1020, 180))], "Otthon") is None


def synthetic_list(names, start=600):
    nodes = [n for n in fixture("list") if n.bounds and (n.bounds[3] < 1800 or n.bounds[1] >= 2088)]
    for i, name in enumerate(names):
        top = start + i * 240
        nodes.extend([
            UiNode("", "", "", "android.view.View", True, (53, top, 1027, top + 200)),
            UiNode("", "", name, "android.widget.TextView", False, (106, top + 30, 400, top + 80)),
            UiNode("", "", "No active departure time", "android.widget.TextView", False,
                   (106, top + 80, 600, top + 130)),
        ])
    # Keep the title/navigation but remove the climate rows from this synthetic list.
    return [n for n in nodes if not n.checkable and not (n.text and n.text[0].isdigit())]


class LocationPhone:
    connected = True

    def __init__(self, *, lists=None, fail=None, mismatch=False):
        self.lists = lists or [fixture("list")]
        self.list_index = 0
        self.where = "overview"
        self.name = "Otthon"
        self.fail = fail
        self.mismatch = mismatch
        self.taps = []
        self.backs = 0
        self.swipes = 0

    def nodes(self):
        if self.where == "overview":
            return [UiNode("rangeTile", "", "", "android.view.View", False, (0, 300, 1080, 700)),
                    UiNode("", "Departure times. Open details", "", "android.view.View", True, (0, 800, 1080, 1000))]
        if self.where == "list":
            return self.lists[self.list_index]
        if self.where == "climate":
            return parse_ui_dump(page_xml(7, 25, {"mon", "tue", "wed", "thu", "fri"}, True))
        if self.where == "wrong":
            return [replace(n, content_desc="Wrong") if n.content_desc == "Otthon" else n for n in fixture("location")]
        if self.where == "location":
            return [replace(n, content_desc=self.name) if n.content_desc == "Otthon" else n for n in fixture("location")]
        return [replace(n, text="Other" if self.mismatch else self.name) if n.text == "Otthon" else n
                for n in fixture("settings")]

    async def dump_ui(self):
        return xml(self.nodes())

    async def tap(self, x, y):
        nodes = self.nodes()
        hits = [n for n in nodes if n.bounds and n.bounds[0] <= x <= n.bounds[2] and n.bounds[1] <= y <= n.bounds[3]]
        assert not any(n.checkable for n in hits)
        assert not any(n.text == "Active" for n in hits)
        badges = [n for n in nodes if n.text == "Active" and n.bounds]
        for hit in hits:
            if hit.clickable and hit.bounds:
                assert not any(hit.bounds[0] <= badge.bounds[0] <= badge.bounds[2] <= hit.bounds[2]
                               and hit.bounds[1] <= badge.bounds[1] <= badge.bounds[3] <= hit.bounds[3]
                               and hit.bounds[0] > 700 for badge in badges)
        if self.where == "settings":
            pytest.fail("No settings-page control may be tapped")
        if self.where == "overview":
            assert (x, y) == nodes[1].tap_point
            self.taps.append("tile")
            self.where = "list"
        elif self.where == "list":
            row = next((row for row in location_rows(nodes, STRINGS) if row.name.tap_point == (x, y)), None)
            if row is None:
                # The independent departure-times member opens its climate timer pages.
                from custom_components.vag_connect.companion.departure import departure_rows
                assert any(r.clock.tap_point == (x, y) for r in departure_rows(nodes))
                self.taps.append("climate")
                self.where = "climate"
                return
            self.taps.append(row.name.text)
            self.name = row.name.text
            self.where = "list" if self.fail == "location_no_open" else "wrong" if self.fail == "title" else "location"
        elif self.where == "location":
            assert (x, y) == settings_icon(nodes, self.name).tap_point
            self.taps.append("settings")
            if self.fail == "transport":
                raise CompanionTransportError("interrupted")
            self.where = "location" if self.fail == "settings_no_open" else "settings"
        else:
            pytest.fail(f"Unexpected tap on {self.where}")

    async def key_back(self):
        self.backs += 1
        self.where = {"settings": "location", "location": "list", "wrong": "list",
                      "climate": "list", "list": "overview"}[self.where]

    async def swipe(self, *_args):
        assert self.where == "list"
        self.swipes += 1
        if self.fail == "swipe":
            raise CompanionTransportError("swipe failed")
        self.list_index = min(self.list_index + 1, len(self.lists) - 1)


def channel(phone, opt_ins=None):
    out = CompanionChannel(phone, VW, time_fn=time.monotonic, nav_opt_ins={"charging_locations"} if opt_ins is None else opt_ins)
    out._app_strings = STRINGS
    return out


@pytest.mark.asyncio
async def test_full_walk_allowed_taps_backs_and_cleared_slots():
    phone = LocationPhone()
    ch = channel(phone)
    fields = {"auto_unlock_when_charged": True, "target_soc": 80, "charging_location_5_name": "Old"}
    await ch._augment_via_nav(fields)
    assert fields["charging_location_count"] == 1
    assert fields["charging_location_current"] == "Otthon"
    assert fields["charging_location_1_active_timers"] == 1
    assert fields["charging_location_1_reduced_ac_current"] is False
    assert fields["auto_unlock_when_charged"] is True and fields["target_soc"] == 80
    assert all(fields[f"charging_location_5_{part}"] is None for part in LOCATION_PARTS)
    assert ch._nav_cache["charging_location_5_name"] is None
    assert all(key.startswith("charging_location_") for key in ch._nav_cache)
    assert phone.taps == ["tile", "Otthon", "settings"]
    assert phone.backs == 3 and phone.where == "overview"


@pytest.mark.asyncio
async def test_five_locations_one_swipe_and_no_active_location():
    phone = LocationPhone(lists=[synthetic_list(["A", "B", "C", "D", "E"], start=1100), synthetic_list(["C", "D", "E"])])
    fields = {}
    await channel(phone)._augment_via_nav(fields)
    assert fields["charging_location_count"] == 5 and fields["charging_location_current"] == "none"
    assert [fields[f"charging_location_{n}_name"] for n in range(1, 6)] == list("ABCDE")
    assert phone.swipes == 1 and phone.backs == 11 and phone.where == "overview"
    assert phone.taps == ["tile", "A", "settings", "B", "settings", "C", "settings", "D", "settings", "E", "settings"]


@pytest.mark.parametrize(("failure", "backs", "timer_read"), [
    ("location_no_open", 1, False), ("title", 2, False),
    ("settings_no_open", 2, True), ("transport", 2, True), ("swipe", 3, True),
])
@pytest.mark.asyncio
async def test_partial_failure_preserves_values_and_returns(failure, backs, timer_read):
    phone = LocationPhone(fail=failure)
    fields = {"charging_location_5_name": "Old"}
    await channel(phone)._augment_via_nav(fields)
    assert fields["charging_location_1_name"] == "Otthon"
    assert (fields.get("charging_location_1_timer_1_time") is not None) == timer_read
    assert "charging_location_count" not in fields and "charging_location_current" not in fields
    assert fields["charging_location_5_name"] == "Old"
    assert phone.backs == backs and phone.where == "overview"


@pytest.mark.asyncio
async def test_settings_chip_mismatch_does_not_supply_settings():
    phone = LocationPhone(mismatch=True)
    fields = {}
    await channel(phone)._augment_via_nav(fields)
    assert fields["charging_location_1_timer_1_time"] == "07:00"
    assert fields.get("charging_location_1_reduced_ac_current") is None
    assert fields.get("charging_location_1_auto_release_connector") is None
    assert phone.backs == 3


@pytest.mark.asyncio
async def test_shared_departure_path_reads_both_once():
    phone = LocationPhone()
    fields = {}
    await channel(phone, {"departure_times", "charging_locations"})._augment_via_nav(fields)
    assert phone.taps.count("tile") == 1 and phone.taps.count("climate") == 3
    assert fields["departure_timer_1_time"] == "07:25"
    assert fields["departure_timer_1_weekdays"] == "mon,tue,wed,thu,fri"
    assert fields["charging_location_1_timer_1_time"] == "07:00"
    assert fields["charging_location_count"] == 1
    assert phone.backs == 6 and phone.where == "overview"


@pytest.mark.asyncio
async def test_opt_in_default_off_and_trip_refresh_gating():
    phone = LocationPhone()
    ch = channel(phone, set())
    await ch._augment_via_nav({})
    assert phone.taps == []
    ch.set_nav_opt_in("charging_locations", True)
    await ch._augment_via_nav({})
    assert phone.taps.count("tile") == 1
    await ch._augment_via_nav({})
    assert phone.taps.count("tile") == 1
    ch._trip_tile = "new trip"
    await ch._augment_via_nav({})
    assert phone.taps.count("tile") == 2
    ch._walk_basis[NAV.name] = replace(ch._walk_basis[NAV.name], at=ch._wall() - 12 * 3600)
    await ch._augment_via_nav({})
    assert phone.taps.count("tile") == 3
    ch.walk_details_next_read()
    await ch._augment_via_nav({})
    assert phone.taps.count("tile") == 4
    ch.set_nav_opt_in("charging_locations", False)
    assert not ch._nav_cache


@pytest.mark.asyncio
async def test_duplicate_names_stop_and_an_empty_list_changes_nothing():
    phone = LocationPhone(lists=[synthetic_list(["A"]), synthetic_list(["B", "B"])])
    fields = {}
    await channel(phone)._augment_via_nav(fields)
    assert fields["charging_location_1_name"] == "A" and "charging_location_count" not in fields
    phone = LocationPhone(lists=[synthetic_list([])])
    fields = {}
    await channel(phone)._augment_via_nav(fields)
    # An empty list may be missing data, not deleted locations: nothing is
    # claimed and nothing is cleared.
    assert not any(key.startswith("charging_location_") for key in fields)


def test_all_fields_nullable_entities_gated_and_translated():
    assert set(NAV.resource_targets) == set(LOCATION_FIELDS)
    data = VehicleData(vin="TEST")
    assert all(getattr(data, key) is None for key in LOCATION_FIELDS)
    descriptions = [desc for desc in (*SENSOR_DESCRIPTIONS, *BINARY_DESCRIPTIONS) if desc.key in LOCATION_FIELDS]
    assert {desc.key for desc in descriptions} == set(LOCATION_FIELDS)
    assert all(desc.condition == "electric" and desc.entity_category == EntityCategory.DIAGNOSTIC for desc in descriptions)
    assert set(LOCATION_FIELDS) <= SENSOR_REQUIRED | BINARY_REQUIRED
    root = Path(__file__).parents[1] / "custom_components" / "vag_connect"
    for path in [root / "strings.json", *(root / "translations").glob("*.json")]:
        entities = json.loads(path.read_text(encoding="utf-8"))["entity"]
        assert "companion_read_charging_locations" in entities["switch"]
        assert entities["sensor"]["charging_location_current"]["state"]["none"]
        assert set(LOCATION_FIELDS) <= entities["sensor"].keys() | entities["binary_sensor"].keys()


def test_new_single_resources_are_extracted(monkeypatch):
    from tests import test_companion_resources as resources_test
    for key in STRINGS:
        if "#" in key:
            continue
        monkeypatch.setattr(resources_test, "KEY", key)
        assert extract_app_strings(table("Localised")) == {key: {"Localised"}}


def test_active_timer_plural_resource_extraction():
    import struct
    # One plural entry with its zero form, using Android's standard map layout.
    globals_, types, keys = pool("No active departure time", True), pool("plurals", True), pool(CHARGING_PLURAL, True)
    entry = struct.pack("<HHIII", 16, 1, 0, 0, 1) + struct.pack("<IHBBI", 0x01000005, 8, 0, 3, 0)
    resource_type = struct.pack("<HHIBBHII", 0x201, 48, 52 + len(entry), 1, 0, 0, 1, 52) + struct.pack("<I", 28) + bytes(24) + bytes(4) + entry
    package = bytearray(288)
    struct.pack_into("<HHII", package, 0, 0x200, 288, 288 + len(types) + len(keys) + len(resource_type), 0x7f)
    struct.pack_into("<I", package, 268, 288)
    struct.pack_into("<I", package, 276, 288 + len(types))
    body = globals_ + package + types + keys + resource_type
    data = struct.pack("<HHII", 2, 12, 12 + len(body), 1) + body
    assert extract_app_strings(data) == {f"{CHARGING_PLURAL}#zero": {"No active departure time"}}


@pytest.mark.asyncio
async def test_changed_slot_does_not_keep_another_locations_settings():
    phone = LocationPhone(fail="title")
    ch = channel(phone)
    ch._nav_cache.update({"charging_location_1_name": "Old",
                          "charging_location_1_auto_release_connector": True})
    fields = {}
    await ch._augment_via_nav(fields)
    assert fields["charging_location_1_name"] == "Otthon"
    assert fields["charging_location_1_auto_release_connector"] is None
    assert ch._nav_cache["charging_location_1_auto_release_connector"] is None


@pytest.mark.asyncio
async def test_missing_resources_never_claim_an_empty_complete_list():
    phone = LocationPhone()
    ch = channel(phone)
    ch._app_strings = {}
    fields = {}
    await ch._augment_via_nav(fields)
    assert not fields and phone.taps == ["tile"] and phone.backs == 1


def test_a_location_row_with_a_switch_is_never_a_tap_target():
    nodes = fixture("list")
    rows = location_rows(nodes, STRINGS)
    switch = replace(rows[0].name, text="", clickable=True, checkable=True)
    assert location_rows(nodes + [switch], STRINGS) == []


def test_a_location_named_like_the_active_badge_is_not_active():
    rows = location_rows(synthetic_list(["Active"]), STRINGS)
    assert len(rows) == 1 and rows[0].name.text == "Active" and not rows[0].active


def test_client_accepts_the_new_opt_in_through_the_existing_constructor():
    from custom_components.vag_connect.companion.client import CompanionClient
    from custom_components.vag_connect.const import CONF_COMPANION_READ_CHARGING_LOCATIONS
    from custom_components.vag_connect.switch import COMPANION_READS

    client = CompanionClient(brand="volkswagen", vin="TEST", host="unused", port=5555,
                             adbkey_path="unused", time_fn=time.monotonic,
                             nav_opt_ins={"charging_locations"})
    assert client._channel.nav_opt_ins == {"charging_locations"}
    assert ("charging_locations", CONF_COMPANION_READ_CHARGING_LOCATIONS, "mdi:ev-plug-type2") in COMPANION_READS
    client.set_nav_opt_in("charging_locations", False)
    assert not client._channel.nav_opt_ins


@pytest.mark.asyncio
async def test_the_apps_empty_state_during_a_pause_changes_nothing():
    """Live 2026-10-10: during a request-limit pause the app showed no timers and
    no locations, as if none existed, while 'Otthon' was still in the car."""
    assert location_rows(fixture("list_empty"), STRINGS) == []
    phone = LocationPhone(lists=[fixture("list_empty")])
    fields = {"charging_location_1_name": "Otthon", "charging_location_count": 1}
    await channel(phone)._augment_via_nav(fields)
    assert fields == {"charging_location_1_name": "Otthon", "charging_location_count": 1}
    assert phone.where == "overview"
