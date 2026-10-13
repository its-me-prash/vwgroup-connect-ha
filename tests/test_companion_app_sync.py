# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vehicle Settings → "Synchronise now" on a timer; see fixtures/sources.json.

The poll interval only re-reads the app screen. This sync makes the car send
fresh data, on its own slider (60 … 240 min, off by default) on the settings device.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
from custom_components.vag_connect.companion.app_sync import find_sync_button
from custom_components.vag_connect.companion.channel import (
    _RATE_LIMIT_BACKOFF_S,
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.client import CompanionClient
from custom_components.vag_connect.companion.presets import ACTION_TO_COMMAND, PRESETS
from custom_components.vag_connect.companion.screen import find_node_for, parse_ui_dump
from custom_components.vag_connect.const import (
    CONF_COMPANION_APP_SYNC_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_STRATEGY,
    DOMAIN,
    STRATEGY_COMPANION_ADB,
)
from custom_components.vag_connect.coordinator import VagConnectCoordinator

FIXTURES = Path(__file__).parent / "fixtures" / "companion_app_sync"
BATTERY = Path(__file__).parent / "fixtures" / "companion_battery"
VW = PRESETS["volkswagen"]
STRINGS = {k: set(v) for k, v in json.loads((BATTERY / "vw_432_resources.json").read_text(encoding="utf-8")).items()}
SYNC_SPEC = next(a for a in VW.actions if a.action == "sync_vehicle")


def dump(name: str) -> str:
    path = FIXTURES / (name + ".xml")
    return (path if path.exists() else BATTERY / (name + ".xml")).read_text(encoding="utf-8")


def nodes(name: str):
    return parse_ui_dump(dump(name))


# ── the button ────────────────────────────────────────────────────────────────

def test_button_is_found_enabled_below_the_fold():
    button = find_sync_button(nodes("tiguan_settings_lower"))
    assert button is not None and button.enabled and button.text == "Synchronise now"


def test_button_is_disabled_while_the_app_waits_for_the_car():
    button = find_sync_button(nodes("tiguan_settings_syncing"))
    assert button is not None and not button.enabled


@pytest.mark.parametrize("name", ["tiguan_settings", "tiguan_overview_settings", "tiguan_overview"])
def test_no_button_on_other_screens(name):
    assert find_sync_button(nodes(name)) is None


def test_delete_vehicle_is_never_the_match():
    lower = nodes("tiguan_settings_lower")
    delete = next(n for n in lower if n.resource_id == "delete_cta")
    for found in (find_sync_button(lower), find_node_for(lower, SYNC_SPEC)):
        assert found is not None and found.resource_id == "subtitle_cta"
        assert found.bounds != delete.bounds
    # Without the sync button on screen, nothing else matches either.
    only_delete = [n for n in lower if n.resource_id != "subtitle_cta"]
    assert find_sync_button(only_delete) is None
    assert find_node_for(only_delete, SYNC_SPEC) is None


def test_language_does_not_matter():
    foreign = parse_ui_dump(dump("tiguan_settings_lower").replace("Synchronise now", "Jetzt synchronisieren"))
    assert find_sync_button(foreign) is not None


def test_preset_maps_the_sync_to_its_own_command():
    assert SYNC_SPEC.resource_id == "subtitle_cta"
    assert SYNC_SPEC.nav_read == "vehicle_settings"
    assert SYNC_SPEC.app_versions == ("4.6.4", "4.3.2")
    assert ACTION_TO_COMMAND["sync_vehicle"] == "command_sync_vehicle"


def test_fixtures_are_credited():
    sources = {s["fixture"] for s in json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))}
    assert {"tiguan_settings_lower.xml", "tiguan_settings_syncing.xml"} <= sources
    assert sources == {p.name for p in FIXTURES.iterdir() if p.name != "sources.json"}
    for name in sources:
        assert "inputText" not in (FIXTURES / name).read_text(encoding="utf-8")  # no vehicle name


# ── the walk ──────────────────────────────────────────────────────────────────

class SyncPhone:
    """Overview → Settings → swipe → Synchronise now, as on the live 4.3.2 app.

    The button turns disabled once tapped; the toolbar arrow goes back.
    """

    connected = True

    def __init__(self, *, version="4.3.2", syncing=False, accepts=True, limit_alert=None):
        self.version = version
        self.where = "overview"
        self.syncing = syncing
        self.accepts = accepts
        self.limit_alert = limit_alert
        self.taps: list[str] = []
        self.backs = 0

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return self.version

    strings = STRINGS

    async def battery_strings(self, package):
        return self.strings

    async def dump_ui(self):
        if self.where == "overview":
            return dump("tiguan_overview_settings")
        if self.where == "settings":
            return dump("tiguan_settings")
        if self.where == "alert":
            return dump("tiguan_settings_lower").replace(
                "Vehicle and app synchronise automatically on a regular basis. If necessary, "
                "you can trigger this manually here. The process may take a few minutes.",
                self.limit_alert)
        return dump("tiguan_settings_syncing" if self.syncing else "tiguan_settings_lower")

    def _on(self, rid_or_desc, x, y):
        for node in parse_ui_dump(self._current):
            if rid_or_desc in (node.resource_id, node.content_desc) and node.bounds:
                left, top, right, bottom = node.bounds
                if left <= x <= right and top <= y <= bottom:
                    return True
        return False

    async def tap(self, x, y):
        self._current = await self.dump_ui()
        if self.where == "overview" and self._on("Settings. Open details", x, y):
            self.taps.append("settings")
            self.where = "settings"
        elif self.where != "overview" and self._on("vwd_navigation_button", x, y):
            self.taps.append("toolbar")
            self.where = "overview"
        elif self.where == "lower" and self._on("delete_cta", x, y):
            self.taps.append("DELETE")
        elif self.where == "lower" and self._on("subtitle_cta", x, y):
            self.taps.append("sync")
            if self.limit_alert:
                self.where = "alert"
            elif self.accepts:
                self.syncing = True
        else:
            self.taps.append("miss")

    async def swipe(self, x1, y1, x2, y2, ms):
        self.taps.append("swipe")
        if self.where == "settings" and y2 < y1:
            self.where = "lower"

    async def key_back(self):
        self.backs += 1
        self.where = "overview"


def channel_for(phone):
    return CompanionChannel(phone, VW, time_fn=time.monotonic)


@pytest.mark.asyncio
async def test_sync_opens_settings_scrolls_taps_and_returns():
    phone = SyncPhone()
    channel = channel_for(phone)
    assert await channel.sync_vehicle() is True
    assert phone.taps == ["settings", "swipe", "sync", "toolbar"]
    assert phone.where == "overview" and phone.backs == 0
    assert channel._last_write_at is not None


@pytest.mark.asyncio
async def test_a_running_sync_is_not_tapped_again():
    phone = SyncPhone(syncing=True)
    channel = channel_for(phone)
    assert await channel.sync_vehicle() is False
    assert "sync" not in phone.taps and phone.where == "overview"
    assert channel._last_write_at is None


@pytest.mark.asyncio
async def test_a_tap_the_app_ignored_is_reported():
    phone = SyncPhone(accepts=False)
    with pytest.raises(CompanionWriteBlocked, match="did not start the vehicle sync"):
        await channel_for(phone).sync_vehicle()
    assert phone.taps.count("sync") == 1 and phone.where == "overview"


@pytest.mark.asyncio
async def test_request_limit_after_the_tap_pauses_the_channel():
    phone = SyncPhone(limit_alert="Too many requests sent to the vehicle")
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await channel.sync_vehicle()
    assert channel._is_rate_limited() and phone.where == "overview"
    assert channel.request_state == "restricted"
    # Other commands stay paused ...
    with pytest.raises(CompanionWriteBlocked, match="backed off"):
        await channel.set_charge_target(60)


@pytest.mark.asyncio
async def test_other_app_version_taps_nothing():
    phone = SyncPhone(version="4.4.0")
    with pytest.raises(CompanionWriteBlocked, match="app version"):
        await channel_for(phone).sync_vehicle()
    assert phone.taps == []


@pytest.mark.asyncio
async def test_back_to_back_syncs_keep_the_command_gap():
    phone = SyncPhone()
    channel = channel_for(phone)
    assert await channel.sync_vehicle() is True
    phone.syncing = False
    with pytest.raises(CompanionWriteBlocked, match="s ago"):
        await channel.sync_vehicle()
    assert phone.taps.count("sync") == 1


@pytest.mark.asyncio
async def test_generic_action_path_refuses_the_sync():
    with pytest.raises(CompanionWriteBlocked, match="sync_vehicle"):
        await channel_for(SyncPhone()).do_action("sync_vehicle")


@pytest.mark.asyncio
async def test_delete_vehicle_is_never_tapped_in_any_walk():
    for phone in (SyncPhone(), SyncPhone(syncing=True), SyncPhone(accepts=False)):
        try:
            await channel_for(phone).sync_vehicle()
        except CompanionWriteBlocked:
            pass
        assert "DELETE" not in phone.taps and "miss" not in phone.taps


# ── the client ────────────────────────────────────────────────────────────────

def _client(phone) -> CompanionClient:
    client = CompanionClient.__new__(CompanionClient)
    client._brand = "volkswagen"
    client._vin = "WVWZZZAUZFW805377"
    client._channel = channel_for(phone)
    return client


@pytest.mark.asyncio
async def test_client_exposes_the_sync_command():
    phone = SyncPhone()
    client = _client(phone)
    assert client.supports_command("command_sync_vehicle")
    assert await client.command_sync_vehicle(client._vin) is True


@pytest.mark.asyncio
async def test_client_turns_a_refusal_into_a_command_error():
    client = _client(SyncPhone(version="4.4.0"))
    with pytest.raises(VehicleCommandError):
        await client.command_sync_vehicle(client._vin)


# ── the coordinator ───────────────────────────────────────────────────────────

def _coord(data=None, options=None, *, read_only=False, client=None):
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = SimpleNamespace(
        data={CONF_STRATEGY: STRATEGY_COMPANION_ADB, **(data or {})}, options=options or {}
    )
    coord.is_read_only = lambda: read_only
    coord._persist_companion_rate_limit = MagicMock()
    coord._cariad_client = client
    coord.vehicles = {}
    return coord


def test_interval_is_off_by_default():
    assert _coord().companion_app_sync_interval_s() == 0


@pytest.mark.parametrize(("stored", "seconds"), [
    (5, 3600), (60, 3600), (120, 7200), (1, 3600), (999, 14400), ("x", 0), (0, 0), (-5, 0),
])
def test_interval_is_read_live_and_clamped(stored, seconds):
    assert _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: stored}).companion_app_sync_interval_s() == seconds


def test_interval_ignores_the_poll_interval():
    coord = _coord(data={CONF_SCAN_INTERVAL: 5, CONF_COMPANION_APP_SYNC_INTERVAL: 120})
    assert coord.companion_app_sync_interval_s() == 7200


def _fake_client(result=True):
    client = MagicMock()
    client.supports_command = lambda name: name == "command_sync_vehicle"
    client.command_sync_vehicle = AsyncMock(return_value=result)
    return client


@pytest.mark.asyncio
async def test_sync_calls_the_client_and_persists_the_backoff():
    client = _fake_client()
    coord = _coord(client=client)
    assert await coord.async_companion_sync_vehicle() is True
    client.command_sync_vehicle.assert_awaited_once()
    coord._persist_companion_rate_limit.assert_called_once()


@pytest.mark.asyncio
async def test_sync_is_skipped_in_read_only_mode():
    client = _fake_client()
    assert await _coord(read_only=True, client=client).async_companion_sync_vehicle() is None
    client.command_sync_vehicle.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_is_skipped_for_a_cloud_entry():
    client = _fake_client()
    coord = _coord(client=client)
    coord.entry.data = {CONF_STRATEGY: "hybrid_full"}
    assert await coord.async_companion_sync_vehicle() is None
    client.command_sync_vehicle.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_refused_sync_never_raises():
    client = _fake_client()
    client.command_sync_vehicle.side_effect = VehicleCommandError("command_sync_vehicle", "nope")
    coord = _coord(client=client)
    assert await coord.async_companion_sync_vehicle() is False
    coord._persist_companion_rate_limit.assert_called_once()


@pytest.mark.asyncio
async def test_loop_waits_a_full_interval_then_syncs_and_reads_back(monkeypatch):
    import custom_components.vag_connect.coordinator as mod

    clock = [1000.0]
    sleeps: list[float] = []
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=_fake_client())
    coord._started = True
    coord.async_request_refresh = AsyncMock(side_effect=lambda: setattr(coord, "_started", False))

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    await coord._companion_app_sync_loop()
    # Wakes every minute (so a slider change applies), syncs only after 60 min,
    # then waits for the car before reading the app again.
    assert sleeps == [60.0] * 60 + [mod._APP_SYNC_READBACK_S]
    coord._cariad_client.command_sync_vehicle.assert_awaited_once()
    coord.async_request_refresh.assert_awaited_once()


# ── the slider ────────────────────────────────────────────────────────────────

_ENTRY_ID = "adb_hub_entry_1"


def _entry(options=None, data=None):
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.options = options or {}
    entry.data = {"brand": "volkswagen", CONF_STRATEGY: STRATEGY_COMPANION_ADB, **(data or {})}
    return entry


def _number(entry=None):
    from custom_components.vag_connect.number import VagConnectAppSyncIntervalNumber

    coord = MagicMock()
    coord.hass.config_entries.async_update_entry = MagicMock()
    return VagConnectAppSyncIntervalNumber(coord, entry or _entry())


def test_slider_range_step_and_default():
    num = _number()
    assert (num.native_min_value, num.native_max_value, num.native_step) == (0, 240, 5)
    assert num.native_value == 0
    assert num.native_unit_of_measurement == "min"


def test_slider_lives_on_the_settings_device_next_to_the_poll_interval():
    from homeassistant.helpers.device_registry import DeviceEntryType

    from custom_components.vag_connect.number import VagConnectScanIntervalNumber

    num = _number()
    poll = VagConnectScanIntervalNumber(num._coordinator, num._entry)
    assert num._attr_device_info["identifiers"] == {(DOMAIN, f"{_ENTRY_ID}_settings")}
    assert num._attr_device_info == poll._attr_device_info
    assert num._attr_device_info["entry_type"] == DeviceEntryType.SERVICE
    assert num.unique_id == f"{_ENTRY_ID}_app_sync_interval" != poll.unique_id


def test_slider_and_poll_interval_are_independent():
    from custom_components.vag_connect.number import VagConnectScanIntervalNumber

    entry = _entry(options={CONF_SCAN_INTERVAL: 15, CONF_COMPANION_APP_SYNC_INTERVAL: 120})
    num = _number(entry)
    poll = VagConnectScanIntervalNumber(num._coordinator, entry)
    assert (num.native_value, poll.native_value) == (120, 15)


_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN
_NOTE_FILES = [_COMPONENT / "strings.json", *sorted((_COMPONENT / "translations").glob("*.json"))]


def _sync_note(path: Path) -> str:
    strings = json.loads(path.read_text(encoding="utf-8"))
    note = strings["entity"]["number"]["app_sync_interval"]["state_attributes"]["note"]
    assert note["name"].strip()
    return note["state"]["battery_protection"]


def test_slider_note_is_a_translation_token():
    # HA translates the token in the more-info dialog (state_attributes.note).
    assert _number().extra_state_attributes == {"note": "battery_protection"}


def test_battery_protection_note_in_english():
    note = _sync_note(_COMPONENT / "strings.json")
    assert "battery protection" in note and "failsafe" in note and "next started" in note
    assert "Each sync wakes the car" in note and "Off by default" in note
    assert "0 to turn the sync off" in note
    assert _sync_note(_COMPONENT / "translations" / "en.json") == note


@pytest.mark.parametrize("path", _NOTE_FILES, ids=lambda path: path.name)
def test_battery_protection_note_in_every_language(path):
    note = _sync_note(path)
    assert "60" in note and "0" in note
    if path.stem not in {"en", "strings"}:
        assert note != _sync_note(_COMPONENT / "strings.json")


@pytest.mark.asyncio
@pytest.mark.parametrize(("asked", "stored"), [
    (60, 60), (62, 60), (63, 65), (0, 0), (2, 0), (3, 60), (5, 60), (55, 60), (500, 240), (-10, 0),
])
async def test_slider_writes_a_snapped_clamped_value(asked, stored):
    num = _number(_entry(options={CONF_SCAN_INTERVAL: 15}))
    num.async_write_ha_state = MagicMock()
    await num.async_set_native_value(asked)
    options = num._coordinator.hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert options == {CONF_SCAN_INTERVAL: 15, CONF_COMPANION_APP_SYNC_INTERVAL: stored}


def test_slider_only_for_a_companion_preset_with_the_button():
    from custom_components.vag_connect.number import _companion_can_sync

    coord = MagicMock()
    coord.is_companion.return_value = True
    assert _companion_can_sync(coord, _entry())
    assert not _companion_can_sync(coord, _entry(data={"brand": "skoda"}))
    coord.is_companion.return_value = False
    assert not _companion_can_sync(coord, _entry())


# ── b5: the sync as the probe that ends a request-limit pause ─────────────────

class BudgetPhone(SyncPhone):
    """The app with the car's power budget used up: Synchronise now answers
    with its two alerts, one after the other, and sends nothing."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.budget_used_up = True
        self.alerts: list[str] = []

    async def dump_ui(self):
        if self.alerts:
            return (FIXTURES / f"{self.alerts[0]}.xml").read_text(encoding="utf-8")
        return await super().dump_ui()

    async def tap(self, x, y):
        if self.where == "lower" and not self.alerts and self.budget_used_up:
            self._current = await super().dump_ui()
            if self._on("subtitle_cta", x, y):
                self.taps.append("sync")
                self.alerts = ["alert_power_budget", "alert_vehicle_data_unavailable"]
                return
        await super().tap(x, y)

    async def key_back(self):
        if self.alerts:
            self.alerts.pop(0)
            self.backs += 1
            return
        await super().key_back()


@pytest.mark.asyncio
async def test_a_restricted_sync_closes_both_alerts_and_marks_restricted():
    phone = BudgetPhone()
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await channel.sync_vehicle()
    assert channel.request_state == "restricted" and channel._is_rate_limited()
    assert phone.alerts == [] and phone.backs == 2 and phone.where == "overview"


# The 4.6.4 English tables: the app's local power-budget alert and the
# backend's 4295 "too many requests" dialog read exactly the same.
EN_464_LIMIT = {
    **STRINGS,
    "alert_daily_power_budget_footer": {"Please restart the engine and try again."},
    "dialog_maxrequests_text": {"Please restart the engine and try again."},
}
# Synthetic: a language in which the two differ, so the local alert is provable.
DISTINCT_LIMIT = {**EN_464_LIMIT, "dialog_maxrequests_text": {"Synthetic backend limit text"}}


def budget_channel(strings, phone=None):
    phone = phone or BudgetPhone()
    phone.strings = strings
    clock = [1_700_000_000.0]
    channel = CompanionChannel(
        phone, VW, time_fn=lambda: clock[0], wall_clock_fn=lambda: clock[0]
    )
    return phone, channel, clock


@pytest.mark.asyncio
async def test_a_power_budget_pause_lets_one_probe_through_per_window_and_lifts():
    phone, channel, clock = budget_channel(DISTINCT_LIMIT)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await channel.sync_vehicle()
    assert channel._limit_kind == "power_budget"
    clock[0] += 3 * 3600  # the next 3 h interval: still inside the probe window
    with pytest.raises(CompanionWriteBlocked, match="backed off"):
        await channel.sync_vehicle()
    assert phone.taps.count("sync") == 1
    clock[0] += 3600  # 4 h after the trip; the car has been started meanwhile
    phone.budget_used_up = False
    assert await channel.sync_vehicle() is True
    assert channel.request_state == "available" and not channel._is_rate_limited()
    assert phone.taps.count("sync") == 2


@pytest.mark.asyncio
async def test_a_still_restricted_probe_keeps_the_pause_and_restarts_the_window():
    phone, channel, clock = budget_channel(DISTINCT_LIMIT)
    for _ in range(2):
        with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
            await channel.sync_vehicle()
        clock[0] += 4 * 3600
    clock[0] -= 3600  # 3 h after the second trip
    with pytest.raises(CompanionWriteBlocked, match="backed off"):
        await channel.sync_vehicle()
    assert channel.request_state == "restricted" and phone.taps.count("sync") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("strings", [EN_464_LIMIT, STRINGS])
async def test_a_limit_the_screen_cannot_prove_local_is_never_probed(strings):
    # 4.6.4 in English (and the 4.3.2 fixture tables, which lack the footer):
    # the alert may be the backend's, where a tap is a request. No probe.
    phone, channel, clock = budget_channel(strings)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await channel.sync_vehicle()
    assert channel._limit_kind == "backend"
    clock[0] += 11 * 3600
    with pytest.raises(CompanionWriteBlocked, match="backed off"):
        await channel.sync_vehicle()
    assert phone.taps.count("sync") == 1


@pytest.mark.asyncio
async def test_an_http_429_pause_is_never_probed():
    phone, channel, clock = budget_channel(
        DISTINCT_LIMIT, SyncPhone(limit_alert="Request limit reached")
    )
    with pytest.raises(CompanionWriteBlocked):
        await channel.sync_vehicle()
    assert channel._is_rate_limited() and channel._limit_kind == "backend"
    phone.limit_alert = None
    for _ in range(2):  # at 5 h and 10 h into the 12 h pause
        clock[0] += 5 * 3600
        taps = list(phone.taps)
        with pytest.raises(CompanionWriteBlocked, match="backed off"):
            await channel.sync_vehicle()
        assert phone.taps == taps  # refused before any tap


@pytest.mark.asyncio
async def test_a_backend_limit_during_a_power_budget_pause_ends_the_probes():
    phone, channel, clock = budget_channel(DISTINCT_LIMIT)
    with pytest.raises(CompanionWriteBlocked):
        await channel.sync_vehicle()
    assert channel._limit_kind == "power_budget"
    assert channel._limit_on_screen(parse_ui_dump(
        dump("tiguan_settings_lower").replace("Delete vehicle", "Request limit reached")
    ))
    channel._trip_rate_limit()
    assert channel._limit_kind == "backend"
    clock[0] += 5 * 3600
    with pytest.raises(CompanionWriteBlocked, match="backed off"):
        await channel.sync_vehicle()
    assert phone.taps.count("sync") == 1


@pytest.mark.asyncio
async def test_a_read_closes_leftover_alerts_and_reads_on():
    phone = BudgetPhone()
    phone.alerts = ["alert_power_budget", "alert_vehicle_data_unavailable"]
    channel = channel_for(phone)
    fields = await channel.read()
    assert phone.alerts == [] and fields is not None
    assert channel._is_rate_limited()  # the alert still pauses commands


def test_known_alerts_are_recognised_through_the_app_tables():
    from custom_components.vag_connect.companion.resources import find_app_alert

    for name in ("alert_power_budget", "alert_vehicle_data_unavailable"):
        assert find_app_alert(parse_ui_dump((FIXTURES / f"{name}.xml").read_text(encoding="utf-8")), {})
    assert not find_app_alert(nodes("tiguan_settings_lower"), {})
    french = {"dialog_error_vehicledata_notavailable_headline": {"Données du véhicule indisponibles"}}
    alert = (FIXTURES / "alert_vehicle_data_unavailable.xml").read_text(encoding="utf-8")
    assert find_app_alert(parse_ui_dump(alert.replace("Vehicle data unavailable", "Données du véhicule indisponibles")), french)


@pytest.mark.asyncio
async def test_loop_reads_right_after_a_refused_sync(monkeypatch):
    import custom_components.vag_connect.coordinator as mod

    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    client = _fake_client()
    client.command_sync_vehicle.side_effect = VehicleCommandError("command_sync_vehicle", "limit")
    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=client)
    coord._started = True
    coord.async_request_refresh = AsyncMock(side_effect=lambda: setattr(coord, "_started", False))
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    await coord._companion_app_sync_loop()
    assert sleeps == [60.0] * 60  # no readback wait after a refusal
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_loop_does_nothing_while_off_and_restarts_the_count(monkeypatch):
    import custom_components.vag_connect.coordinator as mod

    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 0}, client=_fake_client())
    coord._started = True
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
        if len(sleeps) == 10:  # turned back on after ten minutes off
            coord.entry.options = {CONF_COMPANION_APP_SYNC_INTERVAL: 60}
        if len(sleeps) >= 90:
            coord._started = False

    coord.async_request_refresh = AsyncMock()
    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    await coord._companion_app_sync_loop()
    coord._cariad_client.command_sync_vehicle.assert_awaited()
    # Off for ten minutes, then a fresh 60 min interval counted from the last
    # "off" check (so within one wake-up of switching it back on).
    first_sync_sleeps = sleeps.index(mod._APP_SYNC_READBACK_S)
    assert 10 + 59 <= first_sync_sleeps <= 10 + 60


# ── b5: the two sensors ───────────────────────────────────────────────────────

def _sensor(cls, vehicle):
    vin = "WVWZZZAUZFW805377"
    sensor = cls.__new__(cls)
    sensor._vin = vin
    sensor.coordinator = MagicMock()
    sensor.coordinator.entry.data = {"brand": "volkswagen"}
    sensor.coordinator.data = {vin: {"vin": vin, **vehicle}}
    return sensor


@pytest.mark.parametrize("stored", [
    "2026-10-05T12:59:06+00:00", datetime(2026, 10, 5, 12, 59, 6, tzinfo=timezone.utc),
])
def test_last_vehicle_sync_shows_the_app_time_live_or_restored(stored):
    from custom_components.vag_connect.sensor import VagLastVehicleSyncSensor

    sensor = _sensor(VagLastVehicleSyncSensor, {"companion_app_synced_at": stored})
    assert sensor.native_value == datetime(2026, 10, 5, 12, 59, 6, tzinfo=timezone.utc)
    assert sensor.available


def test_last_vehicle_sync_ignores_the_cloud_last_seen_at():
    from custom_components.vag_connect.sensor import VagLastVehicleSyncSensor

    sensor = _sensor(VagLastVehicleSyncSensor, {"last_seen_at": "2026-10-04T16:09:36+00:00"})
    assert sensor.native_value is None


@pytest.mark.parametrize(("state", "shown"), [
    ("available", "available"), ("restricted", "restricted"), (None, None), ("odd", None),
])
def test_app_request_status_sensor(state, shown):
    from homeassistant.components.sensor import SensorDeviceClass

    from custom_components.vag_connect.sensor import VagAppRequestStatusSensor

    sensor = _sensor(VagAppRequestStatusSensor, {"companion_request_state": state})
    assert sensor.device_class == SensorDeviceClass.ENUM
    assert sensor.options == ["available", "restricted"]
    assert sensor.native_value == shown and sensor.available


@pytest.mark.asyncio
async def test_the_request_state_reaches_vehicle_data():
    phone = BudgetPhone()
    client = _client(phone)
    client._last_data = None
    with pytest.raises(VehicleCommandError):
        await client.command_sync_vehicle(client._vin)
    data = await client.get_status(client._vin)
    assert data.companion_request_state == "restricted"


def test_a_restored_pause_reads_as_restricted_until_the_first_sync():
    clock = [1_700_000_000.0]
    channel = CompanionChannel(SyncPhone(), VW, time_fn=time.monotonic, wall_clock_fn=lambda: clock[0])
    assert channel.request_state is None
    channel.restore_rate_limit(clock[0] + 3600)
    assert channel.request_state == "restricted"
    clock[0] += 3601  # the pause ran out with no sync yet
    assert channel.request_state is None


@pytest.mark.asyncio
async def test_a_restored_pause_is_never_probed():
    # Its kind is not persisted, so it could be an HTTP 429: wait it out.
    phone = SyncPhone()
    channel = channel_for(phone)
    channel.restore_rate_limit(time.time() + 3600)
    with pytest.raises(CompanionWriteBlocked, match="backed off"):
        await channel.sync_vehicle()
    assert phone.taps == [] and channel.request_state == "restricted"


# ── the sync counts only on positive evidence ────────────────────────────────

class LateAlertPhone(SyncPhone):
    """Takes the tap, then the limit alert draws on the third dump after it."""

    def __init__(self):
        super().__init__()
        self.dumps_after_tap: int | None = None

    async def dump_ui(self):
        if self.dumps_after_tap is not None and self.where == "lower":
            self.dumps_after_tap += 1
            if self.dumps_after_tap >= 3:
                self.where = "alert"
        return await super().dump_ui()

    async def tap(self, x, y):
        await super().tap(x, y)
        if self.taps[-1] == "sync":
            self.dumps_after_tap = 0
            self.limit_alert = "Too many requests sent to the vehicle"


@pytest.mark.asyncio
async def test_an_alert_on_the_third_dump_keeps_the_pause():
    phone = LateAlertPhone()
    channel = channel_for(phone)
    with pytest.raises(CompanionWriteBlocked, match="daily request budget"):
        await channel.sync_vehicle()
    assert channel._is_rate_limited() and channel.request_state == "restricted"
    assert phone.taps.count("sync") == 1 and phone.where == "overview"


# ── b7: the battery level during the pause ────────────────────────────────────

class TilePhone:
    """The Tiguan overview, whose range tile opens the charge sheet."""

    connected = True

    def __init__(self):
        self.screen = dump("tiguan_overview_synchronised")
        self.taps: list[tuple[int, int]] = []

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return "4.3.2"

    async def battery_strings(self, package):
        return STRINGS

    async def dump_ui(self):
        return self.screen

    async def tap(self, x, y):
        self.taps.append((x, y))
        # The range tile opens the sheet; the sheet's own close returns.
        on_sheet = self.screen == dump("tiguan_charging")
        self.screen = dump("tiguan_overview_synchronised" if on_sheet else "tiguan_charging")

    async def key_back(self):
        self.screen = dump("tiguan_overview_synchronised")


def test_the_overview_tile_does_not_narrate_the_battery_level():
    # 4.3.2 draws "Battery 77 %" on the tile but leaves it out of the tile's
    # accessibility sentence, so the charge sheet is the only place to read it.
    channel = CompanionChannel(TilePhone(), VW, time_fn=time.monotonic)
    channel._app_strings = STRINGS
    from custom_components.vag_connect.companion.resources import read_battery_resources
    from custom_components.vag_connect.companion.screen import read_fields

    overview = nodes("tiguan_overview_synchronised")
    fields = {**read_fields(overview, VW), **read_battery_resources(overview, STRINGS)}
    assert "battery_soc" not in fields and fields["electric_range_km"] == 84


@pytest.mark.asyncio
async def test_the_charge_sheet_is_still_read_during_the_request_limit_pause():
    phone = TilePhone()
    channel = CompanionChannel(phone, VW, time_fn=time.monotonic, nav_opt_ins={"charge_detail"})
    # Tripped just now, after the car's last sync: new car data would end it.
    channel.restore_rate_limit(time.time() + _RATE_LIMIT_BACKOFF_S)
    channel._nav_cache = {"battery_soc": 81}  # the value from before the pause
    fields = await channel.read()
    assert fields["battery_soc"] == 70  # read off the sheet, not the cache
    tile = next(n for n in nodes("tiguan_overview_synchronised") if n.resource_id == "rangeTile")
    assert phone.taps[0] == tile.tap_point
    assert phone.screen == dump("tiguan_overview_synchronised")  # and back again
    # The pause itself is untouched: commands still wait.
    assert channel._is_rate_limited() and not channel.writes_enabled


# ── opt-in: off by default, and a stored choice survives the upgrade ─────────

def _setup_entry(data=None, options=None, strategy=STRATEGY_COMPANION_ADB):
    entry = SimpleNamespace(data={CONF_STRATEGY: strategy, **(data or {})}, options=options or {})
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock(
        side_effect=lambda e, data: setattr(e, "data", data)
    )
    return hass, entry


def test_setup_pins_the_sync_off_for_a_companion_entry_without_a_value():
    from custom_components.vag_connect import _pin_companion_app_sync_off

    hass, entry = _setup_entry()
    _pin_companion_app_sync_off(hass, entry)
    assert entry.data[CONF_COMPANION_APP_SYNC_INTERVAL] == 0
    hass.config_entries.async_update_entry.reset_mock()
    _pin_companion_app_sync_off(hass, entry)  # once only
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize(("data", "options"), [
    ({}, {CONF_COMPANION_APP_SYNC_INTERVAL: 240}),
    ({CONF_COMPANION_APP_SYNC_INTERVAL: 240}, {}),
    ({CONF_COMPANION_APP_SYNC_INTERVAL: 180}, {CONF_COMPANION_APP_SYNC_INTERVAL: 240}),
])
def test_setup_keeps_a_value_the_user_set(data, options):
    from custom_components.vag_connect import _pin_companion_app_sync_off

    hass, entry = _setup_entry(data, options)
    _pin_companion_app_sync_off(hass, entry)
    hass.config_entries.async_update_entry.assert_not_called()
    assert _coord(data=entry.data, options=entry.options).companion_app_sync_interval_s() == 14400


def test_setup_leaves_other_channels_alone():
    from custom_components.vag_connect import _pin_companion_app_sync_off

    hass, entry = _setup_entry(strategy="hybrid_full")
    _pin_companion_app_sync_off(hass, entry)
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_loop_never_syncs_with_the_default_config(monkeypatch):
    import custom_components.vag_connect.coordinator as mod

    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    coord = _coord(client=_fake_client())
    coord._started = True
    coord.async_request_refresh = AsyncMock()

    async def fake_sleep(seconds):
        clock[0] += seconds
        if clock[0] > 1000.0 + 24 * 3600:
            coord._started = False

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    await coord._companion_app_sync_loop()
    coord._cariad_client.command_sync_vehicle.assert_not_awaited()


# ── one clock for the loop and the Force vehicle refresh button ──────────────

@pytest.mark.asyncio
async def test_a_button_press_restarts_the_loops_interval(monkeypatch):
    import custom_components.vag_connect.coordinator as mod

    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    client = _fake_client()
    synced_at: list[float] = []
    client.command_sync_vehicle = AsyncMock(side_effect=lambda vin: synced_at.append(clock[0]) or True)
    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=client)
    coord._started = True
    coord.async_request_refresh = AsyncMock(side_effect=lambda: setattr(coord, "_started", False))
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
        if len(sleeps) == 58:  # the user presses Force vehicle refresh at minute 58
            await coord.async_companion_sync_vehicle()

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    await coord._companion_app_sync_loop()
    assert len(synced_at) == 2
    assert synced_at[1] - synced_at[0] >= 3600  # a full interval after the press


@pytest.mark.asyncio
@pytest.mark.parametrize("skip", ["read_only", "unsupported"])
async def test_a_skipped_sync_still_waits_a_full_interval(monkeypatch, skip):
    # The loop must yield and sleep when no attempt is made, never spin.
    import custom_components.vag_connect.coordinator as mod

    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    client = _fake_client()
    if skip == "unsupported":
        client.supports_command = lambda name: False
    coord = _coord(
        options={CONF_COMPANION_APP_SYNC_INTERVAL: 60},
        read_only=skip == "read_only", client=client,
    )
    attempts = [0]
    inner = coord.async_companion_sync_vehicle

    async def counted():
        attempts[0] += 1
        if attempts[0] > 10:  # a spinning loop would get here without sleeping
            coord._started = False
        return await inner()

    coord.async_companion_sync_vehicle = counted
    coord._started = True
    coord.async_request_refresh = AsyncMock()
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
        if clock[0] >= 1000.0 + 3 * 3600:
            coord._started = False

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    await coord._companion_app_sync_loop()
    assert attempts[0] == 2  # one skipped attempt per hour, 3 h -> at 60 and 120 min
    assert len(sleeps) == 180 and set(sleeps) == {60.0}
    client.command_sync_vehicle.assert_not_awaited()
    coord.async_request_refresh.assert_not_awaited()


# ── the interval counts from the car's last data and the last tap ─────────────

WALL0 = 1_791_000_000.0


async def _run_loop(monkeypatch, coord, *, minutes=180, on_minute=None):
    """Run the loop on fake clocks; return the minutes at which it tapped."""
    import custom_components.vag_connect.coordinator as mod

    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0 + clock[0])
    monkeypatch.setattr(time, "time", lambda: WALL0 + clock[0])
    tapped: list[float] = []
    coord._cariad_client.command_sync_vehicle = AsyncMock(
        side_effect=lambda vin: tapped.append(clock[0] / 60) or True
    )
    coord._started = True
    coord.async_request_refresh = AsyncMock()

    async def fake_sleep(seconds):
        before = clock[0]
        clock[0] += seconds
        if on_minute is not None and int(before // 60) != int(clock[0] // 60):
            on_minute(int(clock[0] // 60))
        if clock[0] >= minutes * 60:
            coord._started = False

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    await coord._companion_app_sync_loop()
    return tapped


def _car_synced(coord, minutes_ago, now_min=0.0):
    at = datetime.fromtimestamp(WALL0 + (now_min - minutes_ago) * 60, tz=timezone.utc)
    coord.vehicles = {"VIN": {"companion_app_synced_at": at.isoformat()}}


@pytest.mark.asyncio
async def test_after_a_restart_an_overdue_sync_runs_at_once(monkeypatch):
    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=_fake_client())
    _car_synced(coord, minutes_ago=240)
    tapped = await _run_loop(monkeypatch, coord, minutes=10)
    assert tapped == [0.0]


@pytest.mark.asyncio
async def test_after_a_restart_a_recent_sync_is_waited_out(monkeypatch):
    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=_fake_client())
    _car_synced(coord, minutes_ago=20)
    tapped = await _run_loop(monkeypatch, coord, minutes=59)
    assert tapped and 40 <= tapped[0] < 41  # not at the restart, not a full hour later


@pytest.mark.asyncio
async def test_a_persisted_tap_the_car_never_answered_still_holds_the_next_one(monkeypatch):
    from custom_components.vag_connect.const import CONF_COMPANION_LAST_WRITE_AT

    coord = _coord(
        data={CONF_COMPANION_LAST_WRITE_AT: WALL0 - 10 * 60},
        options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=_fake_client(),
    )
    coord._cariad_client.companion_last_write_at = 0.0  # nothing tapped this run
    _car_synced(coord, minutes_ago=300)
    tapped = await _run_loop(monkeypatch, coord, minutes=55)
    assert tapped and 50 <= tapped[0] < 51


@pytest.mark.asyncio
async def test_car_data_arriving_on_its_own_skips_the_tap(monkeypatch):
    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=_fake_client())

    def drive(minute):
        if minute == 50:  # the car was driven and sent data
            _car_synced(coord, minutes_ago=0, now_min=50)

    tapped = await _run_loop(monkeypatch, coord, minutes=115, on_minute=drive)
    assert tapped and 110 <= tapped[0] < 111  # one interval after the car's data


@pytest.mark.asyncio
async def test_nothing_known_still_waits_a_full_interval_after_a_restart(monkeypatch):
    coord = _coord(options={CONF_COMPANION_APP_SYNC_INTERVAL: 60}, client=_fake_client())
    tapped = await _run_loop(monkeypatch, coord, minutes=59)
    assert tapped == []
