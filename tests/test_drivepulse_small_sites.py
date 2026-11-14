# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Four small sites that must know values owned by a held push source.

A value owned by ``drivepulse`` (class ``_HELD_PUSH_SOURCES``) is an event
snapshot of a hand-linked dongle: it carries a real capture time, is not a live
read, and an owner switch of the state of charge is not a charging movement.
These tests pin the four places where that matters, each against a batch / live
owner whose behaviour must stay unchanged.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect import abrp, const, diagnostics
from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS, VagConnectSensor
from custom_components.vag_connect.trigger_detect import VehicleTransitionDetector

_STAMP = "2026-11-12T08:30:00+00:00"
_VIN = "WVWZZZFAKE0000001"
_DEVICE = "dp-device-secret-0042"


# --- 1. sensor freshness attributes -------------------------------------


def _soc_entity(owner: str, *, stamped: bool) -> Any:
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "battery_soc")
    vehicle: dict[str, Any] = {
        "battery_soc": 55,
        "field_sources": {"battery_soc": owner},
    }
    if stamped:
        vehicle["field_captured_ts"] = {"battery_soc": _STAMP}
    ent = VagConnectSensor.__new__(VagConnectSensor)
    ent.coordinator = MagicMock()
    ent.coordinator.data = {"V": vehicle}
    ent._vin = "V"
    ent._key = desc.key
    ent.entity_description = desc
    return ent


def test_held_value_with_stamp_reports_point_freshness() -> None:
    attrs = _soc_entity("drivepulse", stamped=True)._eu_da_freshness_attributes()
    assert attrs["data_captured_at"] == _STAMP
    assert attrs["freshness_source"] == "point"


def test_held_value_without_stamp_reports_dataset() -> None:
    attrs = _soc_entity("drivepulse", stamped=False)._eu_da_freshness_attributes()
    assert "data_captured_at" not in attrs
    assert attrs["freshness_source"] == "dataset"


@pytest.mark.parametrize("owner", ["eu_data_act"])
def test_batch_owner_unchanged(owner: str) -> None:
    attrs = _soc_entity(owner, stamped=True)._eu_da_freshness_attributes()
    assert attrs["freshness_source"] == "point"


@pytest.mark.parametrize("owner", ["cariad", "mbb", "skoda"])
def test_live_owner_still_gets_nothing(owner: str) -> None:
    assert _soc_entity(owner, stamped=True)._eu_da_freshness_attributes() == {}


# --- 2. ABRP -------------------------------------------------------------


def _veh(owner: str, **extra: Any) -> dict[str, Any]:
    veh: dict[str, Any] = {
        "battery_soc": 60,
        "electric_range_km": 210.0,
        "range_km": 300.0,
        "field_sources": {
            "battery_soc": owner,
            "electric_range_km": owner,
            "range_km": owner,
        },
    }
    veh.update(extra)
    return veh


def test_abrp_held_soc_is_not_sent() -> None:
    tlm = abrp.build_tlm(_veh("drivepulse"), 1)
    assert tlm["soc"] is None
    assert not abrp.has_sendable_soc(_veh("drivepulse"))


def test_abrp_held_range_is_dropped() -> None:
    tlm = abrp.build_tlm(_veh("drivepulse"), 1)
    assert "est_battery_range" not in tlm


def test_abrp_held_range_chosen_value_only() -> None:
    # electric range is live-owned, so it is the chosen value and is sent
    veh = _veh("eu_data_act")
    veh["field_sources"]["range_km"] = "drivepulse"
    assert abrp.build_tlm(veh, 1)["est_battery_range"] == 210.0
    # fallback range_km held -> dropped
    veh2 = _veh("eu_data_act", electric_range_km=None)
    veh2["field_sources"]["range_km"] = "drivepulse"
    assert "est_battery_range" not in abrp.build_tlm(veh2, 1)


@pytest.mark.parametrize("owner", ["eu_data_act", "cariad"])
def test_abrp_other_owners_unchanged(owner: str) -> None:
    tlm = abrp.build_tlm(_veh(owner), 1)
    assert tlm["soc"] == 60
    assert tlm["est_battery_range"] == 210.0
    assert abrp.has_sendable_soc(_veh(owner))


def test_abrp_without_field_sources_unchanged() -> None:
    veh = {"battery_soc": 40, "range_km": 100}
    assert abrp.build_tlm(veh, 1)["soc"] == 40
    assert abrp.has_sendable_soc(veh)


def test_send_refuses_payload_without_soc() -> None:
    session = MagicMock()
    with pytest.raises(abrp.AbrpError):
        asyncio.run(abrp.send_telemetry(session, "K", "T", {"utc": 1, "soc": None}))
    session.post.assert_not_called()


# --- 3. charge_target_reached -------------------------------------------


def _target_events(prev_owner: str, cur_owner: str) -> list[str]:
    d = VehicleTransitionDetector()
    fired: list[str] = []
    d.register("charge_target_reached", None, lambda p: fired.append(p["event"]))
    d.feed({"V": {
        "battery_soc": 70, "target_soc": 80,
        "field_sources": {"battery_soc": prev_owner},
    }})
    d.feed({"V": {
        "battery_soc": 85, "target_soc": 80,
        "field_sources": {"battery_soc": cur_owner},
    }})
    return fired


def test_target_not_reported_when_prev_owner_held() -> None:
    assert _target_events("drivepulse", "cariad") == []


def test_target_not_reported_when_cur_owner_held() -> None:
    assert _target_events("cariad", "drivepulse") == []


def test_target_unchanged_for_batch_owner() -> None:
    assert _target_events("eu_data_act", "eu_data_act") == ["charge_target_reached"]


def test_target_unchanged_without_field_sources() -> None:
    d = VehicleTransitionDetector()
    fired: list[str] = []
    d.register("charge_target_reached", None, lambda p: fired.append(p["event"]))
    d.feed({"V": {"battery_soc": 70, "target_soc": 80}})
    d.feed({"V": {"battery_soc": 85, "target_soc": 80}})
    assert fired == ["charge_target_reached"]


# --- 4. diagnostics ------------------------------------------------------


def test_drivepulse_links_redacted_in_scrub() -> None:
    out = diagnostics._scrub({const.CONF_DRIVEPULSE_LINKS: {_VIN: _DEVICE}})
    rendered = json.dumps(out)
    assert _DEVICE not in rendered
    assert _VIN not in rendered
    assert len(out[const.CONF_DRIVEPULSE_LINKS]) == 1
    assert list(out[const.CONF_DRIVEPULSE_LINKS].values()) == ["**REDACTED**"]


def test_drivepulse_links_redacted_in_scrub_raw() -> None:
    out = diagnostics._scrub_raw({const.CONF_DRIVEPULSE_LINKS: {_VIN: _DEVICE}})
    rendered = json.dumps(out)
    assert _DEVICE not in rendered
    assert _VIN not in rendered
