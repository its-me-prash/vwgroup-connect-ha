# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b17 — the auto-utility-meter opt-in toggle is CONDITIONAL in the options flow.

It is surfaced only when at least one utility_meter-eligible source sensor
(charged energy / odometer) is actually registered for one of the account's
cars — a non-EV with nothing to wrap never sees it, and neither does an entry
with no known vehicles yet. Mirrors the b11 remove-toggle gating tests.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.config_flow import VagConnectOptionsFlow
from custom_components.vag_connect.const import (
    CONF_AUTO_UTILITY_METERS,
    CONF_SCAN_INTERVAL,
)

VIN = "WVWZZZTESTVIN0001"
_UIDS = {
    f"{VIN}_total_charged_energy_kwh": "sensor.a_charged",
    f"{VIN}_odometer_km": "sensor.a_odo",
}


def _flow(data: dict, vehicles: dict | None) -> VagConnectOptionsFlow:
    entry = MagicMock()
    entry.entry_id = "E1"
    entry.data = data
    entry.options = {}
    entry.runtime_data.vehicles = vehicles
    flow = VagConnectOptionsFlow(entry)
    flow.hass = MagicMock()
    return flow


def _schema_keys(result: dict) -> set:
    return {getattr(k, "schema", None) for k in result["data_schema"].schema}


def _reg(resolver) -> MagicMock:
    reg = MagicMock()
    reg.async_get_entity_id.side_effect = resolver
    return reg


def test_toggle_shown_when_a_source_sensor_is_present() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5}, {VIN: MagicMock()})
    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=_reg(lambda d, i, uid: _UIDS.get(uid)),
    ):
        keys = _schema_keys(asyncio.run(flow.async_step_init(None)))
    assert CONF_AUTO_UTILITY_METERS in keys


def test_toggle_hidden_when_no_source_sensor_registered() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5}, {VIN: MagicMock()})
    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=_reg(lambda d, i, uid: None),
    ):
        keys = _schema_keys(asyncio.run(flow.async_step_init(None)))
    assert CONF_AUTO_UTILITY_METERS not in keys


def test_toggle_hidden_when_no_vehicles_known_yet() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5}, None)
    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=_reg(lambda d, i, uid: _UIDS.get(uid)),
    ):
        keys = _schema_keys(asyncio.run(flow.async_step_init(None)))
    assert CONF_AUTO_UTILITY_METERS not in keys
