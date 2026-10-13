# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bound companion nav cache age without extra navigation or car requests."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import json
import time
from pathlib import Path

import pytest

from custom_components.vag_connect import _async_update_listener
from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import find_request_limit
from custom_components.vag_connect.companion.screen import UiNode
from custom_components.vag_connect.entity_base import VagConnectEntity

FIXTURES = Path(__file__).parent / "fixtures"
VW = PRESETS["volkswagen"]
DAY = 24 * 60 * 60


@pytest.mark.asyncio
async def test_failed_nav_reads_expire_and_success_recovers(monkeypatch):
    now = [1000.0]
    phone = SimpleNamespace(connected=True, foreground_app=AsyncMock())
    channel = CompanionChannel(phone, VW, nav_opt_ins={"vehicle_health"},
                               time_fn=time.monotonic, wall_clock_fn=lambda: now[0])
    channel._version_ok = True
    channel._refresh_version_gate = AsyncMock()
    channel._dump_and_clear_overlays = AsyncMock(return_value=([], True))
    monkeypatch.setattr("custom_components.vag_connect.companion.channel.read_fields",
                        lambda *_: {"battery_soc": 80})
    nav = next(n for n in VW.nav_reads if n.name == "vehicle_health")
    values = {"odometer_km": 322, "warning_active": False, "latitude": 47.0,
              "longitude": 19.0, "service_inspection_days": 50, "last_trip_distance_km": 3.0}
    channel._apply_nav_values(nav, [], {}, values)
    channel._augment_via_nav = AsyncMock()  # later walks fail to return values
    now[0] += DAY - 1
    out = await channel.read()
    assert all(out[key] == val for key, val in values.items())
    now[0] += 1
    out = await channel.read()
    assert all(out.get(key) is None for key in values)
    assert channel.nav_read_at == dict.fromkeys(values, 1000.0)
    channel._apply_nav_values(nav, [], {}, {"warning_active": True})
    out = await channel.read()
    assert out["warning_active"] is True
    assert out.get("odometer_km") is None
    assert channel.nav_read_at["warning_active"] == now[0]
    assert channel._augment_via_nav.await_count == 3


@pytest.mark.parametrize("key", ["odometer_km", "warning_active", "position"])
@pytest.mark.parametrize("companion", [True, False])
def test_retained_values_become_unavailable_with_read_time(monkeypatch, key, companion):
    from custom_components.vag_connect import entity_base
    monkeypatch.setattr(entity_base, "time", SimpleNamespace(time=lambda: 1000 + DAY), raising=False)
    data_key = "latitude" if key == "position" else key
    vehicle = {data_key: 42, "companion_nav_read_at": {data_key: 1000.0}}
    entity = object.__new__(VagConnectEntity)
    entity._vin, entity._key = "VIN", key
    if key != "position":
        entity.entity_description = SimpleNamespace(data_key=data_key, key=key)
    entity.coordinator = SimpleNamespace(
        data={"VIN": vehicle}, last_update_success=True,
        is_vehicle_available=lambda _: True, is_companion=lambda: companion,
    )
    assert entity.available is (not companion)
    attrs = entity.extra_state_attributes or {}
    assert ("companion_read_at" in attrs) is companion
    vehicle["companion_nav_read_at"][data_key] += 1
    assert entity.available


@pytest.mark.parametrize("label", ["temporarily unavailable", "vorübergehend nicht verfügbar"])
def test_generic_unavailability_is_not_a_request_limit(label):
    channel = CompanionChannel(object(), VW, time_fn=time.monotonic)
    node = UiNode(label, label, "", "android.view.View", False, (0, 0, 10, 10))
    assert not channel._limit_on_screen([node])


@pytest.mark.parametrize("key", ["alert_daily_power_budget_title", "dialog_maxrequests_headline",
                                 "dialog_maxrequest_bff_error_headline"])
def test_fixture_limit_titles_are_matched_by_resource_key(key):
    strings = {k: set(v) for k, v in json.loads(
        (FIXTURES / "companion_battery/vw_432_resources.json").read_text(encoding="utf-8")
    ).items()}
    for title in strings[key]:
        nodes = [UiNode("", "", title, "android.widget.TextView", False, (0, 0, 10, 10))]
        assert find_request_limit(nodes, {key: strings[key]})


def test_all_battery_fixtures_have_provenance():
    folder = FIXTURES / "companion_battery"
    sources = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    assert {s["fixture"] for s in sources} == {p.name for p in folder.iterdir() if p.name != "sources.json"}


def test_climate_settings_provenance_states_publication_boundary():
    sources = json.loads((FIXTURES / "companion_climate_settings/sources.json").read_text(encoding="utf-8"))
    assert all(s.get("source") and "968" in s.get("related_issue", "") for s in sources)


@pytest.mark.asyncio
async def test_client_read_times_survive_serialization_and_cooldown():
    from custom_components.vag_connect.companion.client import CompanionClient
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile

    client = object.__new__(CompanionClient)
    client._last_data = None
    client._source_channel = "companion_adb"
    client._channel = SimpleNamespace(
        read=AsyncMock(side_effect=[{"battery_soc": 80}, None]),
        nav_read_at={"odometer_km": 1000.0}, request_state=None,
        writes_enabled=False, source_data_age_s=None,
    )
    data = await client.get_status("VIN")
    assert (await client.get_status("VIN")) is data
    merged, _ = reconcile({"odometer_km": 322}, data.to_dict())
    assert merged["odometer_km"] == 322  # shared cache may retain the value
    assert merged["companion_nav_read_at"] == {"odometer_km": 1000.0}


@pytest.mark.asyncio
async def test_fresh_overview_value_updates_cache_value_and_time(monkeypatch):
    channel = CompanionChannel(
        SimpleNamespace(connected=True, foreground_app=AsyncMock()), VW,
        time_fn=time.monotonic, wall_clock_fn=lambda: 2000.0,
    )
    channel._nav_cache = {"battery_soc": 40}
    channel._nav_read_at = {"battery_soc": 1000.0}
    channel._refresh_version_gate = AsyncMock()
    channel._dump_and_clear_overlays = AsyncMock(return_value=([], True))
    monkeypatch.setattr("custom_components.vag_connect.companion.channel.read_fields",
                        lambda *_: {"battery_soc": 80})
    assert (await channel.read())["battery_soc"] == 80
    assert channel._nav_cache["battery_soc"] == 80
    assert channel.nav_read_at["battery_soc"] == 2000.0


@pytest.mark.parametrize("old,new", [(False, True), (True, False)])
@pytest.mark.parametrize("key", ["companion_wake_sleep", "companion_close_app"])
@pytest.mark.asyncio
async def test_transport_flags_apply_live_without_reload(key, old, new):
    applied = AsyncMock()
    coord = SimpleNamespace(
        is_companion=lambda: True, async_request_refresh=AsyncMock(),
        _apply_companion_transport_flags=applied,
    )
    entry = SimpleNamespace(
        entry_id="E1", data={key: old}, options={key: new}, runtime_data=coord,
    )
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    await _async_update_listener(hass, entry)
    hass.config_entries.async_reload.assert_not_awaited()  # keeps _last_write_at
    applied.assert_awaited_once()


@pytest.mark.asyncio
async def test_client_applies_flags_under_the_screen_lock():
    from custom_components.vag_connect.companion.client import CompanionClient
    client = object.__new__(CompanionClient)
    lock = __import__("asyncio").Lock()
    transport = SimpleNamespace(_wake_sleep=False, _close_app=False)
    client._channel = SimpleNamespace(_screen_lock=lock, _t=transport)
    await lock.acquire()
    task = __import__("asyncio").ensure_future(
        client.set_transport_flags(wake_sleep=True, close_app=True))
    await __import__("asyncio").sleep(0)
    assert transport._wake_sleep is False  # waits for the screen lock
    lock.release()
    await task
    assert transport._wake_sleep is True and transport._close_app is True


def test_reconcile_carries_read_time_with_restored_value():
    from custom_components.vag_connect.cariad.vehicle_cache import reconcile
    prev = {"odometer_km": 100, "companion_nav_read_at": {"odometer_km": 5.0}}
    merged, _ = reconcile(prev, {"odometer_km": None, "companion_nav_read_at": {}})
    assert merged["odometer_km"] == 100
    assert merged["companion_nav_read_at"] == {"odometer_km": 5.0}
    # a value this poll supplied itself is not tied to the old stamp
    merged, _ = reconcile(prev, {"odometer_km": 120, "companion_nav_read_at": {}})
    assert merged["companion_nav_read_at"] == {}
    # fresh stamps win
    merged, _ = reconcile(prev, {"odometer_km": None, "companion_nav_read_at": {"odometer_km": 9.0}})
    assert merged["companion_nav_read_at"] == {"odometer_km": 9.0}


@pytest.mark.parametrize("companion", [True, False])
def test_charging_mode_expires_with_its_read_time(monkeypatch, companion):
    """The sensor's key is ``charge_mode``, the field the walk stamps."""
    from custom_components.vag_connect import entity_base
    from custom_components.vag_connect.sensor import VagCompanionChargeModeSensor

    monkeypatch.setattr(entity_base, "time", SimpleNamespace(time=lambda: 1000 + DAY), raising=False)
    vehicle = {"charge_mode": "manual", "companion_nav_read_at": {"charge_mode": 1000.0}}
    entity = object.__new__(VagCompanionChargeModeSensor)
    entity._vin, entity._key = "VIN", "charge_mode"
    entity.coordinator = SimpleNamespace(
        data={"VIN": vehicle}, last_update_success=True,
        is_vehicle_available=lambda _: True, is_companion=lambda: companion,
    )
    assert entity.available is (not companion)
    assert ("companion_read_at" in (entity.extra_state_attributes or {})) is companion
    vehicle["companion_nav_read_at"]["charge_mode"] += 1  # a fresh read
    assert entity.available
