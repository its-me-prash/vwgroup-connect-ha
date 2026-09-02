# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-source connectivity binary_sensors (#1286) — which read channels a car is
connected to, active vs standby, how many of its readings each source provides.

Brand-agnostic: driven off the coordinator's armed-channel enumeration + the
per-field provenance (field_sources) that the multi-channel merge already writes.
The Škoda official channel is a FAILOVER whose data wears the brand token, so it is
reported as an armed standby source with no live count.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.vag_connect.binary_sensor import VagSourceConnectivitySensor
from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN = "TMBEL9NEXP1000001"


def _coord(entry_data: dict, client) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.data = dict(entry_data)
    c._cariad_client = client
    return c


def _client(**armed) -> SimpleNamespace:
    # only the attrs set to a truthy object count as "armed"
    defaults = dict(
        _supplementary_authproxy=None, _supplementary_eu_portal=None,
        _supplementary_tibber=None, _supplementary_official=None, _eu_portal=None,
    )
    defaults.update(armed)
    return SimpleNamespace(**defaults)


# ── armed-channel enumeration ───────────────────────────────────────────────

def test_armed_channels_skoda_native_plus_official() -> None:
    c = _coord({"brand": "skoda"}, _client(_supplementary_official=object()))
    assert c._armed_data_channels(VIN) == ["skoda", "skoda_official"]


def test_armed_channels_vw_portal_plus_vwde() -> None:
    c = _coord(
        {"brand": "volkswagen"},
        _client(_supplementary_eu_portal=object(), _supplementary_authproxy=object()),
    )
    got = c._armed_data_channels(VIN)
    assert got[0] == "volkswagen"  # primary
    assert set(got) == {"volkswagen", "eu_data_act", "website_authproxy"}


def test_armed_channels_deduped_when_primary_is_supplementary_token() -> None:
    # VW-EU whose PRIMARY is the portal + also a supplementary portal → one entry
    c = _coord({"brand": "volkswagen", "website_authproxy": True},
               _client(_supplementary_authproxy=object()))
    got = c._armed_data_channels(VIN)
    assert got.count("website_authproxy") == 1  # primary + supp collapse to one


# ── channel-status computation ──────────────────────────────────────────────

def test_status_active_counts_from_field_sources() -> None:
    c = _coord({"brand": "skoda"}, _client())
    data = {"field_sources": {"battery_soc": "skoda", "odometer": "skoda",
                              "range_km": "eu_data_act"}}
    st = c._compute_channel_status(VIN, data)
    assert st["skoda"]["active"] is True
    assert st["skoda"]["active_values"] == 2
    assert st["skoda"]["total_values"] == 3
    assert st["skoda"]["last_active"] is not None


def test_status_official_active_when_contributing_else_standby() -> None:
    c = _coord({"brand": "skoda"}, _client(_supplementary_official=object()))
    # idle this cycle: armed + failover, active False, and a REAL zero count now
    # (the official channel is an active live source, so it reports a live count
    # like every other channel — not the old sentinel None).
    st = c._compute_channel_status(VIN, {"field_sources": {"battery_soc": "skoda"}})
    assert st["skoda_official"]["armed"] is True
    assert st["skoda_official"]["failover"] is True
    assert st["skoda_official"]["active"] is False
    assert st["skoda_official"]["active_values"] == 0
    # contributing this cycle: its readings wear the skoda_official token → active
    st2 = c._compute_channel_status(
        VIN, {"field_sources": {"battery_soc": "skoda", "odometer_km": "skoda_official"}}
    )
    assert st2["skoda_official"]["active"] is True
    assert st2["skoda_official"]["active_values"] == 1
    assert st2["skoda_official"]["failover"] is True  # still the failover too


def test_status_portal_carries_health_attributes() -> None:
    c = _coord({"brand": "volkswagen"}, _client(_supplementary_eu_portal=object()))
    data = {"field_sources": {"battery_soc": "eu_data_act"},
            "portal_health": "ok", "minutes_since_last_snapshot": 7}
    st = c._compute_channel_status(VIN, data)
    assert st["eu_data_act"]["portal_health"] == "ok"
    assert st["eu_data_act"]["minutes_since_last_snapshot"] == 7


def test_status_last_active_carries_forward_when_idle() -> None:
    c = _coord({"brand": "skoda"}, _client())
    # poll 1: active → records a timestamp
    c._compute_channel_status(VIN, {"field_sources": {"soc": "skoda"}})
    ts = c._channel_last_active[VIN]["skoda"]
    # poll 2: nothing from skoda → still reports the last time it was active
    st = c._compute_channel_status(VIN, {"field_sources": {"soc": "eu_data_act"}})
    assert st["skoda"]["active"] is False
    assert st["skoda"]["last_active"] == ts


# ── the sensor ──────────────────────────────────────────────────────────────

def _sensor(token: str, channel_status: dict) -> VagSourceConnectivitySensor:
    s = VagSourceConnectivitySensor.__new__(VagSourceConnectivitySensor)
    s._token = token
    s._vin = VIN
    s.coordinator = SimpleNamespace(data={VIN: {"channel_status": channel_status}})
    return s


def test_sensor_on_when_armed_attrs_reflect_active() -> None:
    s = _sensor("skoda", {"skoda": {
        "armed": True, "active": True, "failover": False,
        "active_values": 12, "total_values": 40, "last_active": "2026-09-01T00:00:00Z",
    }})
    assert s.is_on is True
    a = s._platform_attributes()
    assert a["status"] == "active"
    assert a["active_entities"] == 12 and a["total_entities"] == 40


def test_sensor_standby_failover_label() -> None:
    s = _sensor("skoda_official", {"skoda_official": {
        "armed": True, "active": False, "failover": True, "active_values": None,
        "total_values": 40, "last_active": None,
    }})
    assert s.is_on is True
    assert s._platform_attributes()["status"] == "standby (failover)"
    # no live count for the failover
    assert "active_entities" not in s._platform_attributes()


def test_sensor_state_unknown_when_channel_gone() -> None:
    # token not in status → no longer armed → is_on None (HA state "unknown",
    # not "unavailable" and not a misleading "off")
    s = _sensor("tibber", {})
    assert s.is_on is None
    assert s._platform_attributes() is None
